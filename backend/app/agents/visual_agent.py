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

PROMPT_SYSTEM = """你是电商商品识别助手。根据图片准确识别商品，从以下商品库支持的类别中选择最匹配的：

数码电子：真无线耳机、智能手机、平板电脑、笔记本电脑、移动电源、充电器/数据线
美妆护肤：精华、面霜、防晒、化妆水、眼霜、面膜、粉底液、蜜粉、唇釉、眉笔、洁面、卸妆
服饰运动：跑步鞋、篮球鞋、徒步鞋、短袖T恤、速干T恤、卫衣、运动长裤、运动短裤、户外裤、瑜伽裤、背包、帽子
食品饮料：咖啡、牛奶、酸奶、碳酸饮料、功能饮料、茶饮、方便食品、坚果/零食、调味品

如果图片中的商品不在以上类别中，confidence 应设为 0.3 以下。"""

PROMPT_USER = """请识别这张商品图片，只返回 JSON：

{
  "product_name": "商品完整名称",
  "brand": "品牌名",
  "category": "从支持类别中选择最接近的（如：真无线耳机/精华/跑步鞋/咖啡/智能手机/面霜 等）",
  "sub_category": "更细的子类（如：降噪耳机/抗老精华/缓震跑鞋/速溶咖啡 等）",
  "specs": "规格（如30ml、250ml、L码、28L 等）",
  "highlights": ["特征标签（如：降噪、保湿、透气、0糖 等）"],
  "confidence": 0.0到1.0
}

规则：
- 仔细观察图片中的文字、logo、包装、形状来判断品类
- 电子产品的数据线/充电头/接口、护肤品的瓶身质地、服饰的面料纹理都是重要线索
- 不在支持类别内的商品（鼠标、键盘、家电、家具等）→ confidence 设为 0.2-0.3
- 图片模糊或无法辨认时 confidence < 0.3"""


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
