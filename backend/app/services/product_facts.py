"""Derive and use source-backed catalog facts.

The raw competition dataset stores important purchase attributes inside title,
marketing copy and FAQ.  This module makes only *explicit* catalog claims
queryable.  It never learns facts from user reviews, which prevents a review
such as "I lost weight" from becoming a retrieval condition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class ProductFact:
    product_id: str
    fact_key: str
    value_text: str = "true"
    value_number: float | None = None
    unit: str = ""
    source_type: str = "catalog"
    source_text: str = ""
    source_ref: dict | None = None
    verified: bool = True
    extractor: str = "rule_v1"

    def model_payload(self) -> dict:
        return asdict(self)


_FOOD_BOOLEAN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nutrition.zero_sugar", (r"0\s*糖", r"无糖", r"零糖")),
    ("nutrition.low_sugar", (r"低糖", r"少糖")),
    ("nutrition.zero_fat", (r"0\s*脂", r"无脂", r"零脂")),
    ("nutrition.low_fat", (r"低脂",)),
    ("nutrition.zero_calorie", (r"0\s*(?:卡|kcal|千卡)", r"零卡")),
    ("nutrition.low_calorie", (r"低卡", r"低热量", r"轻卡")),
    ("nutrition.high_protein", (r"高蛋白", r"高\s*蛋白")),
    ("nutrition.no_added_sugar", (r"0\s*添加蔗糖", r"不添加蔗糖", r"无添加糖")),
)

_NUMERIC_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("nutrition.protein_per_100g", re.compile(r"每\s*100\s*(?:g|克|ml)[^。；，,]{0,28}?(?:蛋白质|蛋白)\s*(?:含量)?\s*(?:≥|约|为|:|：)?\s*(\d+(?:\.\d+)?)\s*g", re.I), "g/100g"),
    ("nutrition.sugar_per_100g", re.compile(r"每\s*100\s*(?:g|克|ml)[^。；，,]{0,28}?(?:糖|碳水)\s*(?:含量)?\s*(?:≤|约|为|:|：)?\s*(\d+(?:\.\d+)?)\s*g", re.I), "g/100g"),
    ("nutrition.fat_per_100g", re.compile(r"每\s*100\s*(?:g|克|ml)[^。；，,]{0,28}?脂肪\s*(?:含量)?\s*(?:≤|约|为|:|：)?\s*(\d+(?:\.\d+)?)\s*g", re.I), "g/100g"),
    ("nutrition.energy_per_100g", re.compile(r"每\s*100\s*(?:g|克|ml)[^。；，,]{0,28}?(?:能量|热量)\s*(?:≤|约|为|:|：)?\s*(\d+(?:\.\d+)?)\s*(?:kcal|千卡|卡)", re.I), "kcal/100g"),
)


def _catalog_sources(product) -> Iterable[tuple[str, str, dict]]:
    """Yield only title/description/FAQ source material, never reviews."""
    if getattr(product, "title", ""):
        yield "title", product.title, {"field": "title"}
    knowledge = getattr(product, "rag_knowledge", None)
    if not knowledge:
        return
    description = getattr(knowledge, "marketing_description", "") or ""
    if description:
        yield "marketing", description, {"field": "marketing_description"}
    for i, faq in enumerate(getattr(knowledge, "official_faq", None) or []):
        text = f"{getattr(faq, 'question', '')} {getattr(faq, 'answer', '')}".strip()
        if text:
            yield "faq", text, {"field": "official_faq", "index": i}


def _snippet(text: str, match: re.Match[str]) -> str:
    return text[max(0, match.start() - 36): min(len(text), match.end() + 80)].strip()


def extract_product_facts(product) -> list[ProductFact]:
    """Extract explicit, source-addressable facts from one product.

    This deliberately favours precision over recall.  Unknown is represented by
    no fact, not a guessed false value.
    """
    pid = getattr(product, "product_id", "")
    if not pid:
        return []
    out: list[ProductFact] = []
    seen: set[tuple[str, str, str]] = set()

    def add(key: str, source_type: str, source_text: str, source_ref: dict,
            *, value: str = "true", number: float | None = None, unit: str = ""):
        identity = (key, value, source_text)
        if identity in seen:
            return
        seen.add(identity)
        out.append(ProductFact(pid, key, value, number, unit, source_type, source_text,
                               source_ref, True))

    for source_type, text, source_ref in _catalog_sources(product):
        for key, patterns in _FOOD_BOOLEAN_PATTERNS:
            for pattern in patterns:
                hit = re.search(pattern, text, re.I)
                if hit:
                    add(key, source_type, _snippet(text, hit), source_ref)
                    break
        for key, pattern, unit in _NUMERIC_PATTERNS:
            hit = pattern.search(text)
            if hit:
                add(key, source_type, _snippet(text, hit), source_ref,
                    value=hit.group(1), number=float(hit.group(1)), unit=unit)

    # SKU dimensions are genuine structured catalog facts and work across all categories.
    for sku in getattr(product, "skus", None) or []:
        for key, value in (getattr(sku, "properties", None) or {}).items():
            value = str(value).strip()
            if value:
                add(f"spec.{str(key).strip().lower()}", "sku", f"{key}: {value}",
                    {"field": "skus"}, value=value)
    return out


def fact_keys(product) -> set[str]:
    return {f.fact_key for f in extract_product_facts(product)}


def build_discovery_text(product, facts: list[ProductFact] | None = None) -> str:
    """A compact, review-free document for the discovery index."""
    facts = facts if facts is not None else extract_product_facts(product)
    labels = {
        "nutrition.zero_sugar": "0糖", "nutrition.low_sugar": "低糖",
        "nutrition.zero_fat": "0脂", "nutrition.low_fat": "低脂",
        "nutrition.zero_calorie": "0卡", "nutrition.low_calorie": "低卡",
        "nutrition.high_protein": "高蛋白", "nutrition.no_added_sugar": "不添加蔗糖",
    }
    fact_text = " ".join(labels.get(f.fact_key, f"{f.fact_key}:{f.value_text}") for f in facts[:16])
    specs = " ".join(f.source_text for f in facts if f.fact_key.startswith("spec."))[:260]
    return " | ".join(x for x in [
        f"[商品] {getattr(product, 'title', '')}",
        f"[品牌] {getattr(product, 'brand', '')}",
        f"[品类] {getattr(product, 'category', '')}>{getattr(product, 'sub_category', '')}",
        f"[价格] {getattr(product, 'base_price', 0)}",
        f"[可验证属性] {fact_text}" if fact_text else "",
        f"[规格] {specs}" if specs else "",
    ] if x)


def food_constraint_groups(query: str, must_tags: list[str] | None = None) -> list[set[str]]:
    text = " ".join([query or "", *(must_tags or [])]).lower()
    required: list[set[str]] = []
    if re.search(r"(?:0|零)\s*糖|无糖", text):
        required.append({"nutrition.zero_sugar"})
    elif "低糖" in text:
        required.append({"nutrition.zero_sugar", "nutrition.low_sugar"})
    if re.search(r"(?:0|零)\s*脂|无脂", text):
        required.append({"nutrition.zero_fat"})
    elif "低脂" in text:
        required.append({"nutrition.zero_fat", "nutrition.low_fat"})
    if "高蛋白" in text:
        required.append({"nutrition.high_protein"})
    if re.search(r"(?:0|零)\s*(?:卡|kcal)|无热量", text):
        required.append({"nutrition.zero_calorie"})
    elif any(x in text for x in ("低卡", "轻卡", "低热量")):
        required.append({"nutrition.zero_calorie", "nutrition.low_calorie"})
    return required


def filter_products_by_facts(products: list, query: str, must_tags: list[str] | None = None) -> tuple[list, dict]:
    """Return hard-filtered food candidates and an auditable filter report.

    A "light choice" request is intentionally a positive preference, not a
    medical claim: a product only needs one catalog-backed light attribute.
    """
    required_groups = food_constraint_groups(query, must_tags)
    light_request = any(x in (query or "") for x in ("不想长胖", "控卡", "轻负担", "减脂"))
    if not required_groups and not light_request:
        return products, {"applied": False, "required": [], "reason": "no_food_fact_constraint"}
    eligible = []
    for product in products:
        if getattr(product, "category", "") != "食品饮料":
            # This function remains generally reusable.  The discovery layer
            # scopes nutrition queries to food before reaching here; callers
            # passing a mixed catalog without such scope keep legacy behavior.
            eligible.append(product)
            continue
        keys = fact_keys(product)
        required_ok = all(bool(keys & alternatives) for alternatives in required_groups)
        light_ok = bool(keys & {
            "nutrition.zero_sugar", "nutrition.low_sugar", "nutrition.zero_fat",
            "nutrition.low_fat", "nutrition.zero_calorie", "nutrition.low_calorie",
            "nutrition.high_protein",
        }) if light_request else True
        if required_ok and light_ok:
            eligible.append(product)
    return eligible, {
        "applied": True, "required": [sorted(group) for group in required_groups], "light_request": light_request,
        "matched": len(eligible), "reason": "source_backed_food_facts",
    }
