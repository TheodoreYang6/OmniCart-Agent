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

PROMPT_SYSTEM = """你是一个电商购物导购助手，专门从商品截图中提取关键信息。
请仔细观察用户上传的商品截图，提取所有可见的商品参数。"""

PROMPT_USER = """请从这张商品截图中提取以下信息，以 JSON 格式返回（只返回 JSON，不要其他内容）：

{
  "product_name": "商品名称（优先提取中文名，如只有英文则保留英文）",
  "brand": "品牌名（优先提取中文名，如只有英文则保留英文）",
  "category": "商品类别（如：精华/面霜/防晒/手机/耳机/充电宝/T恤/跑鞋/咖啡/零食等）",
  "price": 价格数字（只提取数字，不含货币符号）,
  "specs": "关键规格（如容量30ml、重量200g、尺码M等）",
  "highlights": ["卖点标签（中文优先），如抗初老、淡化细纹、夜间修护、保湿"]],
  "confidence": 0.0到1.0之间的数值
}

规则：
- 只能提取截图中明确可见的信息
- product_name和brand有中文就优先输出中文
- category根据商品外观/包装/描述判断，输出中文类别词
- 无法识别的字段设为 null 或 []
- confidence 根据图片清晰度和字段完整度估算，模糊图片低于 0.5"""


class VisualAgent:
    def __init__(self):
        self._gateway = get_model_gateway()

    async def parse(self, image_url: str, user_query: str = "") -> VisualResult:
        # 将 /api/uploads/xxx.png 转为本地路径
        filename = image_url.rsplit("/", 1)[-1]
        filepath = _UPLOAD_DIR / filename

        if not filepath.exists():
            return VisualResult(confidence=0.0, raw_response="", fallback_level=4)

        image_bytes = filepath.read_bytes()
        ext = filepath.suffix.lower()
        content_type = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
        }.get(ext, "image/png")

        # 缓存键：视觉解析结果由图片内容 + 用户问题决定
        img_hash = hashlib.md5(image_bytes).hexdigest()[:12]
        cache_key = make_key("visual", img_hash, user_query[:80])

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

        return await cached(cache_key, REDIS_CACHE_TTL_VISUAL, _do_parse)

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
