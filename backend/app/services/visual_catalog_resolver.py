"""Deterministic catalog matching for visual entity extraction.

This module intentionally never queries product descriptions, reviews, or any
vector index.  A photo is useful for extracting identity clues, not for claiming
that a look-alike is the exact catalog product.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services.product_entity_resolver import ProductEntityResolver, ResolutionResult, identity_forms, normalize_identity


class VisualCatalogResolver:
    """Resolve a structured visual result against the catalog identity layer only."""

    EXACT_THRESHOLD = 0.82
    EXACT_MARGIN = 0.12

    def __init__(self) -> None:
        self._identity = ProductEntityResolver()

    async def resolve(self, visual: dict[str, Any] | None) -> ResolutionResult:
        visual = visual or {}
        confidence = float(visual.get("confidence") or 0.0)
        if confidence < 0.35 or visual.get("image_quality") == "poor":
            return self._none("图片信息不足，暂未锁定具体商品")

        fields = ("brand", "product_name", "product_line", "model", "specs", "visible_text")
        visual_text = " ".join(
            " ".join(value) if isinstance(value := visual.get(key), list) else str(value or "")
            for key in fields
        )
        forms = identity_forms(visual_text)
        # Generic catalog titles are not all covered by identity_forms; full visual
        # identity remains a valid alias lookup key.
        normalized = normalize_identity(visual_text)
        if normalized:
            forms.add(normalized)
        if not forms:
            return self._none("未识别到可核验的品牌、名称或型号")

        candidates = await self._identity._find_candidates(forms)
        if not candidates:
            return self._none("暂未在商品目录中确认具体型号")

        ranked = []
        for candidate in candidates:
            score = self._score(visual, candidate)
            candidate = dict(candidate)
            candidate["score"] = score
            ranked.append(candidate)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        top, second = ranked[0], ranked[1] if len(ranked) > 1 else None
        top_score = float(top["score"])
        margin = top_score - float(second["score"]) if second else 1.0

        if top_score >= self.EXACT_THRESHOLD and margin >= self.EXACT_MARGIN:
            resolved = await self._identity._scoped("exact_product", top, ranked)
            return self._decorate(resolved, visual, len(ranked), margin)

        family = str(top["identity"].family_key or "")
        same_family = [item for item in ranked if str(item["identity"].family_key or "") == family]
        if family and len(same_family) >= 2 and top_score >= 0.58:
            resolved = await self._identity._scoped("product_family", top, same_family)
            return self._decorate(resolved, visual, len(ranked), margin)

        # Only a close, plausible decision is sent to an LLM, and its answer stays
        # closed over the identity candidates. A weak/low-quality recognition must
        # not trigger this costly or risky step.
        if top_score >= 0.65 and margin < self.EXACT_MARGIN:
            chosen = await self._identity._llm_adjudicate(visual_text, ranked[:6])
            selected = next((item for item in ranked if item["product"]["product_id"] == chosen), None)
            if selected:
                resolved = await self._identity._scoped("exact_product", selected, ranked)
                return self._decorate(resolved, visual, len(ranked), margin, adjudicated=True)
        return self._ambiguous(visual, top_score, len(ranked), margin)

    @staticmethod
    def _score(visual: dict[str, Any], candidate: dict[str, Any]) -> float:
        product = candidate["product"]
        identity = candidate["identity"]
        alias = normalize_identity(str(candidate.get("alias") or ""))
        title = normalize_identity(str(product.get("title") or ""))
        brand = normalize_identity(str(product.get("brand") or ""))
        model = normalize_identity(str(getattr(identity, "model_key", "") or ""))
        visual_brand = normalize_identity(str(visual.get("brand") or ""))
        visual_model = normalize_identity(str(visual.get("model") or ""))
        visual_name = normalize_identity(" ".join(str(visual.get(key) or "") for key in ("product_name", "product_line")))
        visual_specs = normalize_identity(str(visual.get("specs") or ""))
        visual_category = str(visual.get("category") or "").strip()

        score = 0.0
        if visual_model and (visual_model == model or visual_model in alias or visual_model in title):
            score += 0.55
        if visual_brand and (visual_brand == brand or visual_brand in brand or brand in visual_brand):
            score += 0.20
        if visual_name:
            similarity = max(SequenceMatcher(None, visual_name, value).ratio() for value in (alias, title) if value)
            if visual_name in alias or alias in visual_name or visual_name in title or title in visual_name:
                similarity = max(similarity, 0.95)
            score += 0.25 * similarity
        if visual_specs:
            sku_text = normalize_identity(" ".join(str(sku) for sku in (product.get("skus") or [])))
            if visual_specs in title or visual_specs in sku_text:
                score += 0.10
        if visual_category and visual_category == str(product.get("category") or ""):
            score += 0.10
        # Alias match is a small support signal only; a single generic title alias
        # cannot outrank an explicit model or brand disagreement.
        score += min(0.10, float(candidate.get("score") or 0.0) * 0.10)
        return min(1.0, round(score, 4))

    @staticmethod
    def _decorate(result: ResolutionResult, visual: dict[str, Any], candidates: int, margin: float, adjudicated: bool = False) -> ResolutionResult:
        result.payload.update({
            "source": "visual_catalog",
            "visual_result": _public_visual(visual),
            "visual_candidate_count": candidates,
            "visual_score_margin": round(margin, 3),
            "visual_adjudicated": adjudicated,
        })
        return result

    @staticmethod
    def _none(label: str) -> ResolutionResult:
        return ResolutionResult(
            payload={"match_type": "no_match", "retrieval_scope": "broad", "resolved_product_ids": [], "label": label, "source": "visual_catalog"},
            products=[], evidence=[],
        )

    @staticmethod
    def _ambiguous(visual: dict[str, Any], score: float, candidates: int, margin: float) -> ResolutionResult:
        return ResolutionResult(
            payload={
                "match_type": "ambiguous", "retrieval_scope": "broad", "resolved_product_ids": [],
                "confidence": round(score, 3), "label": "识别到了商品线索，但暂未确认具体型号，已为你找同类。",
                "source": "visual_catalog", "visual_result": _public_visual(visual),
                "visual_candidate_count": candidates, "visual_score_margin": round(margin, 3),
            }, products=[], evidence=[],
        )


def _public_visual(visual: dict[str, Any]) -> dict[str, Any]:
    return {key: visual.get(key) for key in (
        "brand", "product_name", "product_line", "model", "specs", "category", "sub_category", "image_quality", "confidence"
    ) if visual.get(key) not in (None, "", [])}
