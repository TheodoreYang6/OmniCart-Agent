"""Visual Agent — 调用 Qwen-VL 解析商品截图，输出结构化 VisualResult"""

import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

from app.model_gateway.gateway import get_model_gateway
from app.schemas.visual import VisualResult, VisualEvidence
from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_VISUAL

_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads"

PROMPT_SYSTEM = """你是欧米的商品视觉实体提取器，不负责推荐，也不能猜测看不见的信息。
只根据包装、Logo、型号、规格和图片中的文字提取可核验线索。商品库目录大类只能是：
数码电子、美妆护肤、服饰运动、食品饮料、家居用品、母婴用品、运动户外、个护清洁。
细类可写商品本身的具体类型。型号、价格、功效若无法从图片确认必须为空；不要把相似外观当作同一商品。"""

PROMPT_USER = """请识别这张商品图片，只返回 JSON：

{
  "product_name": "可见的商品名称；不确定留空",
  "brand": "可见品牌；不确定留空",
  "product_line": "可见产品线；不确定留空",
  "model": "可见型号；不确定留空",
  "category": "目录大类，只能是八个大类之一；不确定留空",
  "sub_category": "商品细类，如防晒、跑步鞋、咖啡；不确定留空",
  "specs": "可见规格，如30ml、250ml、L码；不确定留空",
  "visible_text": ["图片中能辨认的关键文字，最多6条"],
  "highlights": ["仅由图片确认的特征，最多4条"],
  "confidence": 0.0到1.0
}

规则：
- 文字、Logo、型号和规格优先于外观；不允许推测价格、成分、疗效或型号
- 图片模糊、遮挡或只能判断大类时，具体字段留空且 confidence < 0.5
- 只输出 JSON，不要 Markdown。"""


class VisualAgent:
    def __init__(self):
        self._gateway = get_model_gateway()

    async def parse(self, image_url: str, user_query: str = "") -> VisualResult:
        # 解析文件名: /api/uploads/xxx.png 或 /api/uploads/xxx.png?t=123
        from urllib.parse import urlparse
        path = urlparse(image_url).path
        filename = path.rsplit("/", 1)[-1]
        if not filename:
            return VisualResult(confidence=0.0, raw_response="", fallback_level=4)
        filepath = _UPLOAD_DIR / filename

        if not filepath.exists():
            return VisualResult(confidence=0.0, raw_response="", fallback_level=4)

        image_bytes = filepath.read_bytes()
        ext = filepath.suffix.lower()
        content_type = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
        }.get(ext, "image/png")

        image_bytes, content_type, quality = self._prepare_image(image_bytes, content_type)
        # 缓存键：处理后的内容 + 用户问题 + 模型和 Prompt 版本（换模型/改 prompt 自动失效）
        model = self._gateway.get_capability_config("visual_understanding").get("model", "qwen-vl-plus")
        img_hash = hashlib.md5(image_bytes).hexdigest()[:12]
        prompt_hash = hashlib.md5(PROMPT_USER.encode()).hexdigest()[:8]
        cache_key = make_key("visual", model, img_hash, prompt_hash, user_query[:80])

        async def _do_parse() -> VisualResult:
            prompt = PROMPT_USER
            if user_query:
                prompt = f"用户问题：{user_query}\n\n" + PROMPT_USER
            try:
                raw = await self._gateway.vision(
                    capability="visual_understanding",
                    image_bytes=image_bytes,
                    content_type=content_type,
                    prompt=prompt,
                    system=PROMPT_SYSTEM,
                )
            except Exception:
                return VisualResult(confidence=0.0, raw_response="", fallback_level=3)

            result = self._parse_json(raw)
            result.raw_response = raw
            result.image_quality = quality
            return result

        return await cached(
            cache_key, REDIS_CACHE_TTL_VISUAL, _do_parse,
            serializer=lambda v: json.dumps(v.model_dump(), ensure_ascii=False),
            deserializer=lambda s: VisualResult(**json.loads(s)),
        )

    @staticmethod
    def _prepare_image(image_bytes: bytes, content_type: str) -> tuple[bytes, str, str]:
        """修正 EXIF、截取 GIF 首帧并限制发送尺寸；Pillow 缺失时安全原样退回。"""
        try:
            from PIL import Image, ImageOps

            with Image.open(BytesIO(image_bytes)) as source:
                source.seek(0)
                image = ImageOps.exif_transpose(source).convert("RGB")
                width, height = image.size
                quality = "good" if min(width, height) >= 480 else ("usable" if min(width, height) >= 240 else "poor")
                image.thumbnail((1600, 1600))
                output = BytesIO()
                image.save(output, format="JPEG", quality=88, optimize=True)
                return output.getvalue(), "image/jpeg", quality
        except Exception:
            return image_bytes, content_type, "unknown"

    def _parse_json(self, raw: str) -> VisualResult:
        # 尝试提取 JSON（可能被 markdown 代码块包裹）
        json_str = raw
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            json_str = m.group(0)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return VisualResult(raw_response=raw, confidence=0.0, fallback_level=2)

        evidence_list = []
        text_fields = {
            "product_name": "product_name", "brand": "brand",
            "product_line": "product_line", "model": "model",
            "category": "category", "sub_category": "sub_category", "specs": "specs",
            "capacity": "capacity", "power": "power",
        }
        for key, field_name in text_fields.items():
            val = data.get(key)
            if val and isinstance(val, str):
                evidence_list.append(VisualEvidence(
                    field=field_name, value=val,
                    confidence=data.get("confidence", 0.5),
                    evidence_id=f"V-{field_name}",
                ))

        price = data.get("price")
        if price is not None:
            try:
                price = float(price)
                evidence_list.append(VisualEvidence(
                    field="price", value=str(price),
                    confidence=data.get("confidence", 0.5),
                    evidence_id="V-price",
                ))
            except (ValueError, TypeError):
                price = None

        ports = data.get("ports", [])
        if not isinstance(ports, list):
            ports = []

        highlights = data.get("highlights")
        if not isinstance(highlights, list):
            highlights = []

        specs = data.get("specs")
        if isinstance(specs, list):
            specs = "，".join(str(s) for s in specs)

        visible_text = data.get("visible_text")
        if not isinstance(visible_text, list):
            visible_text = []

        confidence = data.get("confidence", 0.0) or 0.0
        try:
            confidence = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        return VisualResult(
            product_name=data.get("product_name"),
            brand=data.get("brand"),
            product_line=data.get("product_line"),
            model=data.get("model"),
            category=data.get("category"),
            sub_category=data.get("sub_category"),
            specs=specs,
            visible_text=[str(item)[:80] for item in visible_text[:6] if item],
            price=price,
            capacity=data.get("capacity"),
            power=data.get("power"),
            ports=ports,
            highlights=highlights,
            confidence=confidence,
            evidence_list=evidence_list,
            fallback_level=0,
        )
