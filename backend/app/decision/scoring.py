"""V0 Decision Scoring — formula-based, now using official dataset rag_knowledge.

Formula:
  raw_score = 0.22*budget_fit + 0.24*scenario_fit + 0.20*spec_match
            + 0.14*review_confidence + 0.10*visual_similarity
            + 0.10*availability_score - 0.15*risk_penalty
"""

from app.schemas.decision_result import DecisionResult, ScoreBreakdown
from app.schemas.product import Product
from app.schemas.visual import VisualResult


class DecisionScoring:

    def score(
        self,
        product: Product,
        query: str,
        keyword_score: float = 0.0,
        budget_max: float | None = None,
        scenario: str | None = None,
        visual_result: VisualResult | None = None,
    ) -> DecisionResult:
        review_conf = self._calc_review_confidence(product)
        visual_sim = self._calc_visual_similarity(product, visual_result)
        spec_match = self._calc_spec_match(product, query, visual_result)

        breakdown = ScoreBreakdown(
            budget_fit=self._calc_budget_fit(product, budget_max),
            scenario_fit=self._calc_scenario_fit(product, scenario, query),
            spec_match=spec_match,
            review_confidence=review_conf,
            visual_similarity=visual_sim,
            availability_score=1.0,  # dataset doesn't track stock; default available
            risk_penalty=self._calc_risk_penalty(product),
        )

        raw_score = (
            0.22 * breakdown.budget_fit
            + 0.24 * breakdown.scenario_fit
            + 0.20 * breakdown.spec_match
            + 0.14 * breakdown.review_confidence
            + 0.10 * breakdown.visual_similarity
            + 0.10 * breakdown.availability_score
            - 0.15 * breakdown.risk_penalty
        )
        final_score = max(0.0, min(1.0, raw_score))
        display_score = round(final_score * 10, 1)

        evidence_ids = [f"E-KW-{product.product_id}"]
        if product.rag_knowledge:
            for i in range(len(product.rag_knowledge.official_faq)):
                evidence_ids.append(f"POL-{product.product_id}-{i}")
            for i in range(len(product.rag_knowledge.user_reviews)):
                evidence_ids.append(f"R-{product.product_id}-{i}")

        risk_factors = self._gather_risk_factors(product)

        return DecisionResult(
            product_id=product.product_id,
            final_score=round(final_score, 4),
            display_score=display_score,
            score_breakdown=breakdown,
            evidence_ids=evidence_ids,
            risk_factors=risk_factors,
            recommendation_reason=self._build_reason(product, final_score, review_conf),
        )

    def _calc_budget_fit(self, product: Product, budget_max: float | None) -> float:
        price = product.base_price
        if budget_max is None:
            return 0.8
        if price <= budget_max:
            return 1.0 - 0.05 * (price / budget_max)
        else:
            overage = (price - budget_max) / budget_max
            return max(0.0, 1.0 - 2.0 * overage)

    def _calc_scenario_fit(self, product: Product, scenario: str | None, query: str) -> float:
        """Search query keywords in product title + marketing_description for scenario fit."""
        search_text = product.title
        if product.rag_knowledge:
            search_text += " " + product.rag_knowledge.marketing_description

        search_lower = search_text.lower()
        query_lower = query.lower()

        hits = 0
        for kw in query_lower.split():
            if len(kw) >= 2 and kw in search_lower:
                hits += 1

        if scenario:
            if scenario.replace("_", " ") in search_lower:
                hits += 2

        return min(1.0, hits * 0.2)

    def _calc_spec_match(self, product: Product, query: str, visual_result: VisualResult | None = None) -> float:
        """Match query terms against product title, category, sub_category, and rag_knowledge."""
        text_parts = [product.title, product.category, product.sub_category]
        if product.rag_knowledge:
            text_parts.append(product.rag_knowledge.marketing_description)

        spec_text = " ".join(t.lower() for t in text_parts)
        query_lower = query.lower()

        hits = sum(1 for kw in query_lower.split() if len(kw) >= 2 and kw in spec_text)
        return min(1.0, hits * 0.2)

    def _calc_review_confidence(self, product: Product) -> float:
        """Use real user review ratings to compute confidence."""
        if not product.rag_knowledge or not product.rag_knowledge.user_reviews:
            return 0.5

        reviews = product.rag_knowledge.user_reviews
        ratings = [r.rating for r in reviews]
        avg_rating = sum(ratings) / len(ratings)

        normalized = avg_rating / 5.0

        count_bonus = min(0.15, len(reviews) * 0.03)

        return min(1.0, normalized + count_bonus)

    def _calc_visual_similarity(self, product: Product, visual_result: VisualResult | None) -> float:
        if visual_result is None or visual_result.confidence == 0:
            return 0.5

        score = 0.5
        p_title = product.title.lower()

        if visual_result.product_name and visual_result.product_name.lower() in p_title:
            score += 0.3
        if visual_result.brand and visual_result.brand.lower() in product.brand.lower():
            score += 0.2

        return min(1.0, score)

    def _calc_risk_penalty(self, product: Product) -> float:
        penalty = 0.0

        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            reviews = product.rag_knowledge.user_reviews
            low_ratings = sum(1 for r in reviews if r.rating <= 2)
            if low_ratings > 0:
                penalty += min(0.5, low_ratings * 0.12)

        if product.base_price > 1000:
            penalty += 0.2
        elif product.base_price > 500:
            penalty += 0.1

        return min(1.0, penalty)

    def _gather_risk_factors(self, product: Product) -> list[str]:
        risks = []

        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            low_reviews = [r for r in product.rag_knowledge.user_reviews if r.rating <= 2]
            if len(low_reviews) >= 2:
                risks.append(f"有{len(low_reviews)}条差评")
            elif len(low_reviews) == 1:
                risks.append("有用户反馈不满意")

        if product.base_price > 2000:
            risks.append("价格较高，需慎重考虑")
        elif product.base_price > 800:
            risks.append("价格偏高")

        return risks[:3]

    def _build_reason(self, product: Product, score: float, review_conf: float) -> str:
        """Build recommendation reason using review signals."""
        if score >= 0.8:
            tier = "综合推荐度高"
        elif score >= 0.5:
            tier = "综合推荐度中等"
        else:
            tier = "综合推荐度偏低"

        detail = ""
        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            ratings = [r.rating for r in product.rag_knowledge.user_reviews]
            avg = sum(ratings) / len(ratings)
            detail = f"，用户评分{avg:.1f}/5"
        elif product.rag_knowledge:
            detail = "，暂无用户评价"

        return f"{product.brand} {product.title[:30]} — {tier}{detail}"
