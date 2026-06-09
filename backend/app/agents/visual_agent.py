"""Visual Agent — 调用 Qwen-VL 解析商品截图，输出结构化 VisualResult"""

import hashlib
import json
import re
from pathlib import Path

from app.model_gateway.gateway import get_model_gateway
from app.schemas.visual import VisualResult, VisualEvidence
from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_VISUAL

_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads"

PROMPT_SYSTEM = """你是一个专业的电商商品识别助手。你的任务是仔细观察商品图片，准确提取商品信息。
特别注意同一品牌下的不同产品线（如精华 vs 粉底液、面霜 vs 防晒），要根据包装文字、瓶身颜色、质地等细节严格区分。"""

PROMPT_USER = """请从这张商品图片中提取以下信息，只返回 JSON：

{
  "product_name": "完整商品名（中文优先，包含产品线关键词如'特润修护精华'vs'持妆粉底液'）",
  "brand": "品牌名",
  "category": "精确类别（精华/面霜/防晒/粉底液/化妆水/口红/面膜/眼霜/洁面等）",
  "price": 价格数字,
  "specs": "规格（如30ml、50g）",
  "highlights": ["卖点标签"],
  "confidence": 0.0到1.0
}

关键规则：
- 同一品牌常有外观相似的多个产品线，务必根据包装上的产品名文字严格区分
- 金棕色/深色瓶身≠精华液，仔细辨识瓶身或包装上印的具体产品名
- 无法确认时降低 confidence，不要猜测"""


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

        # 缓存键：图片内容 + 用户问题 + 模型名（换模型/改prompt自动失效旧缓存）
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
            return result

        return await cached(
            cache_key, REDIS_CACHE_TTL_VISUAL, _do_parse,
            serializer=lambda v: json.dumps(v.model_dump(), ensure_ascii=False),
            deserializer=lambda s: VisualResult(**json.loads(s)),
        )

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
            "category": "category", "specs": "specs",
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

        return VisualResult(
            product_name=data.get("product_name"),
            brand=data.get("brand"),
            category=data.get("category"),
            specs=specs,
            price=price,
            capacity=data.get("capacity"),
            power=data.get("power"),
            ports=ports,
            highlights=highlights,
            confidence=data.get("confidence", 0.0) or 0.0,
            evidence_list=evidence_list,
            fallback_level=0,
        )
