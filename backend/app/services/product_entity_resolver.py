"""Precise catalog identity resolution for explicitly named products.

This service intentionally searches only product identity/alias fields. Marketing
copy and review text belong to semantic retrieval and must not decide whether a
user has named a specific product.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from app.core.database import get_session_sync
from app.models.product import ProductModel
from app.models.product_identity import ProductAliasModel, ProductIdentityModel

_BRAND_REWRITES = {
    "苹果": "apple",
    "愛蘋果": "apple",
    "爱疯": "iphone",
    "爱凤": "iphone",
}
_LINE_REWRITES = {"苹果手机": "iphone", "苹果iphone": "iphone"}
_IPHONE_RE = re.compile(r"iphone\s*(\d{1,2})(?:\s*(pro\s*max|pro|max|plus|mini))?", re.I)
_IPHONE_ACCESSORY_TERMS = ("保护壳", "手机壳", "壳", "膜", "充电", "数据线", "支架", "镜头", "配件")
_ALIAS_SPECIFICITY = {
    "manual_reordered_model": 6,
    "manual_model": 6,
    "variant": 5,
    "model": 4,
    "full_name": 3,
    "title": 2,
    "product_line": 1,
    "brand": 0,
}
_CHINESE_IPHONE_GENERATIONS = {
    "十一": "11",
    "十二": "12",
    "十三": "13",
    "十四": "14",
    "十五": "15",
    "十六": "16",
    "十七": "17",
    "十八": "18",
    "十九": "19",
    "二十": "20",
}


def normalize_identity(value: str) -> str:
    """Normalize human product mentions without relying on tokenization quality."""
    text = (value or "").strip().lower()
    text = (
        text.replace("ｉ", "i")
        .replace("ｐ", "p")
        .replace("ｈ", "h")
        .replace("ｏ", "o")
        .replace("ｎ", "n")
        .replace("ｅ", "e")
    )
    text = text.replace("＋", "+").replace("－", "-")
    for source, target in _LINE_REWRITES.items():
        text = text.replace(source, target)
    for source, target in _BRAND_REWRITES.items():
        text = text.replace(source, target)
    for source, target in _CHINESE_IPHONE_GENERATIONS.items():
        text = text.replace(source, target)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def identity_forms(value: str) -> set[str]:
    """Extract compact identity mentions from a natural-language sentence.

    Keeping the full normalized sentence is useful for exact full-name aliases, but
    named models must also become their own form; otherwise polite prefixes and
    suffixes make exact lookup silently fall back to fuzzy matching.
    """
    normalized = normalize_identity(value)
    forms = {normalized} if normalized else set()
    if "iphone" in normalized:
        forms.add("iphone")
    if "appleiphone" in normalized:
        forms.add("iphone")
    for match in re.finditer(r"iphone(\d{1,2})(promax|pro|max|plus|mini)?", normalized):
        forms.add("iphone" + match.group(1) + (match.group(2) or ""))
    for match in re.finditer(r"apple(\d{1,2})(promax|pro|max|plus|mini)?", normalized):
        forms.add("iphone" + match.group(1) + (match.group(2) or ""))
        forms.add("apple" + match.group(1) + (match.group(2) or ""))
    for match in re.finditer(r"(\d{1,2})代iphone", normalized):
        forms.add("iphone" + match.group(1))
    for match in re.finditer(r"(\d{1,2})(promax|pro|max|plus|mini)iphone", normalized):
        forms.add("iphone" + match.group(1) + match.group(2))
    return forms


def _iphone_fields(value: str) -> tuple[str, str, str, str] | None:
    normalized = normalize_identity(value)
    match = _IPHONE_RE.search(value) or re.search(r"iphone(\d{1,2})(promax|pro|max|plus|mini)?", normalized)
    # In Chinese shopping language “苹果15” normally means iPhone 15; keeping
    # this rewrite here avoids requiring the user to say the brand in English.
    match = match or re.search(r"apple(\d{1,2})(promax|pro|max|plus|mini)?", normalized)
    if not match:
        return None
    generation = match.group(1)
    edition = re.sub(r"\s+", "", match.group(2) or "").lower()
    model = f"iphone{generation}{edition}"
    return "apple", "iphone", f"apple:iphone:{generation}:{edition or 'base'}", model


def build_identity_record(product: Any) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Create deterministic first-pass identity fields and aliases for one product."""
    title = str(getattr(product, "title", "") or "")
    brand = str(getattr(product, "brand", "") or "")
    product_id = str(getattr(product, "product_id", "") or "")
    parsed = _iphone_fields(f"{brand} {title}")
    aliases: set[tuple[str, str]] = set()

    if parsed:
        brand_key, line_key, family_key, model_key = parsed
        generation = re.search(r"iphone(\d{1,2})", model_key).group(1)
        aliases.update(
            {
                ("iphone", "product_line"),
                ("苹果手机", "product_line"),
                (f"iphone{generation}", "model"),
                (f"苹果{generation}", "model"),
                (model_key, "model"),
                (title, "title"),
                (brand, "brand"),
            }
        )
    else:
        brand_key = normalize_identity(brand)
        line_key = ""
        model_key = normalize_identity(title)
        family_key = f"product:{product_id}"
        aliases.update({(title, "title"), (brand, "brand")})
        # Brand + concise title keeps a usable deterministic fallback for all catalog rows.
        aliases.add((f"{brand}{title}", "full_name"))

    # SKU labels are genuine identity information; do not index marketing description/reviews.
    for sku in getattr(product, "skus", None) or []:
        props = sku.get("properties", {}) if isinstance(sku, dict) else getattr(sku, "properties", {})
        if isinstance(props, dict):
            label = " ".join(str(v) for v in props.values() if v)
            if label:
                aliases.add((f"{title} {label}", "variant"))

    record = {
        "product_id": product_id,
        "brand_key": brand_key,
        "product_line_key": line_key,
        "family_key": family_key,
        "model_key": model_key,
        "variant_key": "",
        "identity_text": f"{brand} {title}",
        "source": "generated",
    }
    # One product can have title/model aliases that normalize to the same key. Keep
    # the most precise type deterministically, rather than depending on set order.
    priority = {"product_line": 4, "model": 4, "variant": 3, "full_name": 2, "title": 1, "brand": 0}
    deduped: dict[str, tuple[str, str]] = {}
    for value, kind in aliases:
        normalized = normalize_identity(value)
        if not normalized:
            continue
        previous = deduped.get(normalized)
        if previous is None or priority.get(kind, 0) > priority.get(previous[1], 0):
            deduped[normalized] = (value, kind)
    return record, [deduped[key] for key in sorted(deduped)]


def _product_dict(product: ProductModel) -> dict[str, Any]:
    return {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": float(product.base_price),
        "base_price": float(product.base_price),
        # App clients must use the image API.  `image_path` is a dataset-internal
        # filesystem path and cannot be loaded directly by a browser or device.
        "image_urls": [f"/api/products/{product.product_id}/image"],
        "image_path": product.image_path or "",
        "skus": product.skus or [],
        "rag_knowledge": product.rag_knowledge or {},
    }


@dataclass
class ResolutionResult:
    payload: dict[str, Any]
    products: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


class ProductEntityResolver:
    """PostgreSQL-backed identity resolver with bounded LLM disambiguation."""

    async def resolve_product_id(self, product_id: str) -> ResolutionResult:
        """Lock a product-focused request to its explicit catalog subject.

        This path deliberately does not infer from the user's prose: the caller has
        already supplied a trusted catalog id.  At most two true same-family variants
        may accompany it, which keeps an analysis card from being diluted by semantic
        or same-category candidates.
        """
        factory = get_session_sync()
        if factory is None or not product_id:
            return self._none()
        async with factory() as session:
            row = await session.execute(
                select(ProductModel, ProductIdentityModel)
                .join(ProductIdentityModel, ProductIdentityModel.product_id == ProductModel.product_id)
                .where(ProductModel.product_id == product_id)
            )
            found = row.first()
            if found is None:
                return self._none()
            product, identity = found
        selected = {"product": _product_dict(product), "identity": identity, "alias": product.title, "score": 1.0}
        return await self._scoped("exact_product", selected, [selected])

    async def resolve(self, query: str, visual: dict[str, Any] | None = None) -> ResolutionResult:
        visual = visual or {}
        visual_text = " ".join(str(visual.get(k) or "") for k in ("brand", "product_name", "specs"))
        forms = identity_forms(query) | identity_forms(visual_text)
        if not forms:
            return self._none()

        candidates = await self._find_candidates(forms)
        if not candidates:
            return self._none()

        result = await self._decide(query, candidates, visual, visual_text)
        if result.payload["match_type"] == "ambiguous":
            return result
        return result

    async def _find_candidates(self, forms: set[str]) -> list[dict[str, Any]]:
        factory = get_session_sync()
        if factory is None:
            return []
        async with factory() as session:
            exact = await session.execute(
                select(ProductModel, ProductIdentityModel, ProductAliasModel)
                .join(ProductIdentityModel, ProductIdentityModel.product_id == ProductModel.product_id)
                .join(ProductAliasModel, ProductAliasModel.product_id == ProductModel.product_id)
                .where(ProductAliasModel.alias_normalized.in_(forms))
                .limit(24)
            )
            rows = [(p, identity, alias, 1.0) for p, identity, alias in exact.all()]
            # Fuzzy lookup is deliberately constrained to aliases, never search_text.
            for form in forms:
                if len(form) < 4:
                    continue
                sim = func.word_similarity(form, ProductAliasModel.alias_normalized)
                fuzzy = await session.execute(
                    select(ProductModel, ProductIdentityModel, ProductAliasModel, sim.label("sim"))
                    .join(ProductIdentityModel, ProductIdentityModel.product_id == ProductModel.product_id)
                    .join(ProductAliasModel, ProductAliasModel.product_id == ProductModel.product_id)
                    # %% uses the GIN trigram index for candidate pruning. It is
                    # intentionally paired with word_similarity for ranking: <%%
                    # has a server-default threshold of 0.6 and misses a common
                    # one-character transposition such as "iphnoe15pro".
                    .where(ProductAliasModel.alias_normalized.op("%")(form), sim >= 0.42)
                    .order_by(sim.desc())
                    .limit(16)
                )
                rows.extend((p, identity, alias, float(score or 0)) for p, identity, alias, score in fuzzy.all())

        merged: dict[str, dict[str, Any]] = {}
        for product, identity, alias, score in rows:
            current = merged.get(product.product_id)
            specificity = _ALIAS_SPECIFICITY.get(alias.alias_type, 0)
            current_specificity = int(current.get("alias_specificity", -1)) if current else -1
            if (
                current is None
                or score > current["score"]
                or (score == current["score"] and specificity > current_specificity)
            ):
                merged[product.product_id] = {
                    "product": _product_dict(product),
                    "identity": identity,
                    "alias": alias.alias_display,
                    "alias_type": alias.alias_type,
                    "alias_specificity": specificity,
                    "score": score,
                }
        return sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:12]

    async def _decide(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        visual: dict[str, Any],
        visual_text: str,
    ) -> ResolutionResult:
        top = candidates[0]
        families = {str(c["identity"].family_key) for c in candidates if c["identity"].family_key}
        top_score = float(top["score"])
        # An explicit iPhone-like mention with same-family candidates is safe to lock deterministically.
        query_norm = normalize_identity(query)
        visual_norm = normalize_identity(visual_text)
        decision_norm = query_norm + visual_norm
        line_hit = "iphone" in decision_norm or bool(re.search(r"apple\d{1,2}", decision_norm))
        # "iPhone 保护壳/充电器" is a category request, not an instruction to lock
        # the phone itself. Let semantic retrieval handle it unless an accessory
        # title itself was matched exactly.
        visual_has_explicit_model = bool(re.search(r"(?:iphone|apple)\d{1,2}(?:promax|pro|max|plus|mini)", visual_norm))
        if line_hit and not visual_has_explicit_model and any(term in query for term in _IPHONE_ACCESSORY_TERMS):
            return self._none()

        decision_forms = " ".join(identity_forms(query) | identity_forms(visual_text))
        recognition_text = decision_norm + decision_forms
        iphone_model = re.search(r"(?:iphone|apple)(\d{1,2})(promax|pro|max|plus|mini)", recognition_text)
        iphone_generation = re.search(r"(?:iphone|apple)(\d{1,2})", recognition_text)
        if line_hit and not iphone_generation:
            return await self._line_scoped(top, "iphone")
        if top_score >= 0.84 and iphone_model:
            return await self._scoped("exact_product", top, candidates)
        if top_score >= 0.84 and iphone_generation:
            return await self._generation_scoped(top, iphone_generation.group(1))
        # A typo still needs a conservative floor, but when the alias candidates
        # all belong to exactly one family it is safer and more useful to lock that
        # family than to ask a needless clarification question.
        if top_score >= 0.50 and len(families) == 1:
            return await self._scoped("product_family", top, candidates)

        # Only ambiguous cross-family candidates are submitted to the LLM, and its output is bounded.
        chosen = await self._llm_adjudicate(query, candidates)
        if chosen:
            selected = next((c for c in candidates if c["product"]["product_id"] == chosen), None)
            if selected:
                return await self._scoped("exact_product", selected, candidates)
        return ResolutionResult(
            payload={
                "match_type": "ambiguous",
                "retrieval_scope": "ambiguous",
                "product_id": "",
                "family_key": "",
                "resolved_product_ids": [],
                "confidence": round(top_score, 3),
                "label": "欧米找到了多个可能的商品，想确认一下你指的是哪一款？",
            },
            products=[],
            evidence=[],
        )

    async def _scoped(self, scope: str, selected: dict[str, Any], candidates: list[dict[str, Any]]) -> ResolutionResult:
        identity = selected["identity"]
        family = str(identity.family_key or "")
        products = await self._family_products(family, selected["product"])
        if scope == "exact_product":
            products = [selected["product"]] + [
                p for p in products if p["product_id"] != selected["product"]["product_id"]
            ][:2]
        else:
            products = products[:3]
        ids = [p["product_id"] for p in products]
        label = f"已锁定：{selected['product']['brand']} {selected['product']['title'][:28]}"
        if scope == "product_family":
            label = f"已锁定：{identity.product_line_key or '同系列'} 商品"
        evidence = [
            {
                "evidence_id": f"CAT-{pid}",
                "source_type": "catalog_identity",
                "source_id": pid,
                "product_id": pid,
                "content": "商品名称、品牌、型号与别名已在商品目录中核对",
                "modality": "text",
                "confidence": 1.0,
            }
            for pid in ids
        ]
        return ResolutionResult(
            payload={
                "match_type": scope,
                "retrieval_scope": scope,
                "product_id": selected["product"]["product_id"],
                "family_key": family,
                "resolved_product_ids": ids,
                "confidence": round(float(selected["score"]), 3),
                "label": label,
                "matched_alias": selected["alias"],
            },
            products=products,
            evidence=evidence,
        )

    async def _family_products(self, family_key: str, fallback: dict[str, Any]) -> list[dict[str, Any]]:
        if not family_key:
            return [fallback]
        factory = get_session_sync()
        if factory is None:
            return [fallback]
        async with factory() as session:
            rows = await session.execute(
                select(ProductModel)
                .join(ProductIdentityModel)
                .where(ProductIdentityModel.family_key == family_key)
                .order_by(ProductModel.base_price.asc())
                .limit(3)
            )
            products = [_product_dict(row) for row in rows.scalars()]
        return products or [fallback]

    async def _line_scoped(self, selected: dict[str, Any], line_key: str) -> ResolutionResult:
        """Resolve a named product line (e.g. ``iPhone``) without guessing a model."""
        factory = get_session_sync()
        products: list[dict[str, Any]] = []
        if factory is not None:
            async with factory() as session:
                rows = await session.execute(
                    select(ProductModel)
                    .join(ProductIdentityModel)
                    .where(ProductIdentityModel.product_line_key == line_key)
                    .order_by(ProductModel.base_price.asc())
                    .limit(3)
                )
                products = [_product_dict(row) for row in rows.scalars()]
        products = products or [selected["product"]]
        ids = [p["product_id"] for p in products]
        return ResolutionResult(
            payload={
                "match_type": "product_family",
                "retrieval_scope": "product_family",
                "product_id": selected["product"]["product_id"],
                "family_key": f"line:{line_key}",
                "resolved_product_ids": ids,
                "confidence": round(float(selected["score"]), 3),
                "label": "已锁定：iPhone 系列",
                "matched_alias": selected["alias"],
            },
            products=products,
            evidence=[
                {
                    "evidence_id": f"CAT-{pid}",
                    "source_type": "catalog_identity",
                    "source_id": pid,
                    "product_id": pid,
                    "content": "商品名称、品牌与产品线已在商品目录中核对",
                    "modality": "text",
                    "confidence": 1.0,
                }
                for pid in ids
            ],
        )

    async def _generation_scoped(self, selected: dict[str, Any], generation: str) -> ResolutionResult:
        """Resolve ``iPhone 15`` to that generation, without silently choosing Pro/Max."""
        factory = get_session_sync()
        products: list[dict[str, Any]] = []
        family_prefix = f"apple:iphone:{generation}:"
        if factory is not None:
            async with factory() as session:
                rows = await session.execute(
                    select(ProductModel)
                    .join(ProductIdentityModel)
                    .where(ProductIdentityModel.family_key.like(f"{family_prefix}%"))
                    .order_by(ProductModel.base_price.asc())
                    .limit(3)
                )
                products = [_product_dict(row) for row in rows.scalars()]
        products = products or [selected["product"]]
        ids = [p["product_id"] for p in products]
        return ResolutionResult(
            payload={
                "match_type": "product_family",
                "retrieval_scope": "product_family",
                "product_id": selected["product"]["product_id"],
                "family_key": f"generation:{generation}",
                "resolved_product_ids": ids,
                "confidence": round(float(selected["score"]), 3),
                "label": f"已锁定：iPhone {generation} 系列",
                "matched_alias": selected["alias"],
            },
            products=products,
            evidence=[
                {
                    "evidence_id": f"CAT-{pid}",
                    "source_type": "catalog_identity",
                    "source_id": pid,
                    "product_id": pid,
                    "content": "商品名称、品牌与型号代际已在商品目录中核对",
                    "modality": "text",
                    "confidence": 1.0,
                }
                for pid in ids
            ],
        )

    async def _llm_adjudicate(self, query: str, candidates: list[dict[str, Any]]) -> str | None:
        prompt_candidates = [
            {
                "product_id": c["product"]["product_id"],
                "brand": c["product"]["brand"],
                "title": c["product"]["title"],
                "alias": c["alias"],
            }
            for c in candidates[:8]
        ]
        prompt = (
            "判断用户是否明确指定了一个商品。只能返回 JSON："
            '{"product_id":"候选ID或空字符串"}。若无法唯一判断，product_id 必须为空。\n'
            f"用户：{query}\n候选：{json.dumps(prompt_candidates, ensure_ascii=False)}"
        )
        try:
            from app.model_gateway.gateway import get_model_gateway

            raw = await asyncio.wait_for(get_model_gateway().chat("chat_generation", prompt), timeout=2.5)
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            pid = str(data.get("product_id", ""))
            return pid if pid in {c["product"]["product_id"] for c in candidates} else None
        except Exception:
            return None

    @staticmethod
    def _none() -> ResolutionResult:
        return ResolutionResult(
            payload={"match_type": "no_match", "retrieval_scope": "broad", "resolved_product_ids": [], "label": ""},
            products=[],
            evidence=[],
        )
