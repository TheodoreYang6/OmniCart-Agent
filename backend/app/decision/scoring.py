"""V5 Decision Scoring — 匹配排序与证据可信度分离。

Design principles:
- relevance 来自原始 RAG 精排分数，不把“排序校准分”当真实相关度
- 预算、评价、场景只在用户提出或数据确实存在时才有主要权重
- final_score 是候选的内部匹配排序分；evidence_confidence 独立决定证据状态
- 缺少证据只标注“信息有限”，不会把高匹配候选伪装成 4.5 分的“不推荐”
- risk_penalty 绑定 evidence_ids

Formula:
  raw = 0.45 * relevance            # RAG 语义相关度
      + 0.20 * budget_fit           # 价格合适度
      + 0.12 * user_sat             # 用户口碑
      + 0.10 * value_score          # 性价比
      + 0.08 * spec_quality         # 技术规格 (LLM关键词+richness)
      + 0.05 * scenario_fit         # 场景适配
      - risk_penalty                # 风险扣分 + 证据绑定

Display: display_score = round(final * 10, 1)  →  0.0 ~ 10.0
"""

import logging
from typing import Any
from app.schemas.decision_result import DecisionResult, ScoreBreakdown
from app.schemas.product import Product
from app.schemas.visual import VisualResult

# Optional import for evidence scoring
try:
    from app.schemas.evidence_metrics import EvidenceMetrics, ProductEvidenceProfile
    _HAS_EVIDENCE_SCHEMAS = True
except ImportError:
    _HAS_EVIDENCE_SCHEMAS = False

logger = logging.getLogger(__name__)

# Sub-category price benchmarks: (median_expected_price, quality_multiplier)
# quality_multiplier > 1.0 means "you get more quality per yuan in this category"
CATEGORY_BENCHMARKS = {
    "真无线耳机": (800, 1.1),
    "智能手机": (4000, 0.9),
    "平板电脑": (3000, 1.0),
    "笔记本电脑": (6000, 1.0),
    "移动电源": (150, 1.3),
    "跑步鞋": (600, 1.2),
    "运动鞋": (600, 1.2),
    "徒步鞋": (500, 1.1),
    "精华": (400, 1.0),
    "乳液": (200, 1.1),
    "面霜": (300, 1.0),
    "眼霜": (300, 1.0),
    "防晒": (150, 1.2),
    "粉底液": (300, 1.0),
    "卸妆": (120, 1.1),
    "面膜": (100, 1.3),
    "爽肤水": (150, 1.2),
    "口红": (200, 1.1),
    "眉笔": (80, 1.3),
    "瑜伽": (300, 1.1),
    "运动T恤": (150, 1.3),
    "运动短裤": (150, 1.2),
    "牛奶": (50, 1.4),
    "咖啡/速溶": (60, 1.3),
    "碳酸饮料": (30, 1.5),
    "零食/膨化": (30, 1.4),
    "登山": (800, 1.0),
    "高尔夫": (2000, 0.9),
}


class DecisionScoring:

    def score_with_evidence(
        self,
        product: Product,
        query: str,
        keyword_score: float = 0.0,
        budget_max: float | None = None,
        scenario: str | None = None,
        visual_result: VisualResult | None = None,
        used_memories: list[dict] | None = None,
        llm_relevance: float = 0.0,
        llm_reasoning: str = "",
        llm_verdict: str = "",
        llm_strengths: list[str] | None = None,
        llm_risks: list[str] | None = None,
        force_rag_relevance: float | None = None,
        relevance_source: str = "legacy",
        evidence_metrics: Any = None,
        support_evidence_ids: list[str] | None = None,
        global_evidence_sufficient: bool = True,
        scenario_keywords: list[str] | None = None,
        spec_keywords: list[str] | None = None,
        preferred_brands: list[str] | None = None,
    ) -> DecisionResult:
        """V4: RAG 证据驱动评分。默认使用 force_rag_relevance，不再依赖 LLM。"""
        used_memories = used_memories or []
        preferred_brands = preferred_brands or []
        sub_cat = product.sub_category or ""

        # Relevance: 优先用原始 RAG 精排相关度。
        if force_rag_relevance is not None and force_rag_relevance > 0:
            relevance = force_rag_relevance
        elif llm_relevance > 0:
            relevance = llm_relevance
        else:
            relevance = self._calc_keyword_match(product, query, keyword_score)

        budget_fit = self._calc_budget_fit(product, budget_max)
        user_sat = self._calc_user_satisfaction(product)
        value_sc = self._calc_value_score(product, sub_cat)
        spec_q = self._calc_spec_quality(product, sub_cat, query, spec_keywords)
        scenario_fit = self._calc_scenario_fit(product, scenario, query, scenario_keywords)

        risk_penalty, risk_evidence_ids = self._calc_risk_penalty_with_evidence(product)

        # P2-1: Memory-aware scoring — 从 used_memories 计算偏好加成和避雷惩罚
        preference_bonus = 0.0
        avoid_penalty = 0.0
        memory_evidence_ids = []

        # 品牌偏好加成（从 user_preference_entries 提取，weight=0.08）
        preferred = preferred_brands or []
        if preferred:
            product_brand = product.brand or ""
            for pb in preferred:
                if pb.lower() in product_brand.lower():
                    preference_bonus += 0.08
                    break

        for mem in used_memories:
            mem_type = mem.get("memory_type", "")
            sv = mem.get("structured_value", {}) or {}
            conf = mem.get("confidence", 0.5)

            if mem_type == "category":
                mem_cat = sv.get("category", "")
                if mem_cat and mem_cat == product.category:
                    preference_bonus += 0.03 * conf
                    memory_evidence_ids.append(mem.get("memory_id", ""))

            elif mem_type == "brand":
                mem_brand = sv.get("brand", "")
                if mem_brand and mem_brand.lower() in product.brand.lower():
                    preference_bonus += 0.02 * conf
                    memory_evidence_ids.append(mem.get("memory_id", ""))

            elif mem_type == "scenario":
                mem_scenario = sv.get("scenario", "")
                if mem_scenario and scenario and mem_scenario == scenario:
                    preference_bonus += 0.02 * conf
                    memory_evidence_ids.append(mem.get("memory_id", ""))

            elif mem_type == "negative_preference":
                avoid_tag = sv.get("avoid", "")
                if avoid_tag and (
                    avoid_tag.lower() in product.title.lower()
                    or avoid_tag.lower() in product.brand.lower()
                ):
                    avoid_penalty += 0.05 * conf
                    memory_evidence_ids.append(mem.get("memory_id", ""))

        # Clamp modifiers
        preference_bonus = min(preference_bonus, 0.10)
        avoid_penalty = min(avoid_penalty, 0.10)

        # 没有预算/场景/评价数据时，旧算法仍给这些维度几乎满分，导致无关商品也
        # 常落在 7~9 分。现在按“该信号是否真的存在”动态归一化权重。
        has_reviews = bool(product.rag_knowledge and product.rag_knowledge.user_reviews)
        has_budget = bool(budget_max and budget_max > 0)
        has_scenario = bool(scenario or scenario_keywords)
        weights = {
            "relevance": 0.58,
            "budget_fit": 0.18 if has_budget else 0.04,
            "user_sat": 0.12 if has_reviews else 0.02,
            "value_score": 0.05,
            "spec_quality": 0.06,
            "scenario_fit": 0.08 if has_scenario else 0.02,
        }
        weighted_sum = (
            weights["relevance"] * relevance
            + weights["budget_fit"] * budget_fit
            + weights["user_sat"] * user_sat
            + weights["value_score"] * value_sc
            + weights["spec_quality"] * spec_q
            + weights["scenario_fit"] * scenario_fit
        )
        raw = weighted_sum / sum(weights.values()) + preference_bonus - risk_penalty - avoid_penalty
        final_score = max(0.0, min(1.0, raw))

        # Evidence confidence cap
        ev_conf = evidence_metrics.evidence_confidence if evidence_metrics else 0.50  # V1 API无证据指标时中性默认
        rec_level = self._determine_recommendation_level(
            final_score, ev_conf, risk_penalty,
            hard_constraint_failed=False,
            global_evidence_sufficient=global_evidence_sufficient,
        )
        display_score = round(final_score * 10, 1)

        breakdown = ScoreBreakdown(
            budget_fit=budget_fit,
            scenario_fit=scenario_fit,
            spec_match=spec_q,
            review_confidence=user_sat,
            visual_similarity=relevance,
            availability_score=value_sc,
            risk_penalty=risk_penalty,
        )

        # Build component_scores — structured dict for frontend display
        support = support_evidence_ids or []
        component_scores = {
            "relevance": {"score": round(relevance, 4), "weight": weights["relevance"],
                          "method": relevance_source, "evidence_ids": support[:3]},
            "budget_fit": {"score": round(budget_fit, 4), "weight": weights["budget_fit"],
                           "method": "structured_price_rule", "evidence_ids": []},
            "user_sat": {"score": round(user_sat, 4), "weight": weights["user_sat"],
                         "method": "review_rating_avg_v4", "evidence_ids": []},
            "value_score": {"score": round(value_sc, 4), "weight": weights["value_score"],
                            "method": "subcategory_price_benchmark", "evidence_ids": []},
            "spec_quality": {"score": round(spec_q, 4), "weight": weights["spec_quality"],
                             "method": "spec_signal_match", "evidence_ids": []},
            "scenario_fit": {"score": round(scenario_fit, 4), "weight": weights["scenario_fit"],
                             "method": "scenario_keyword_match", "evidence_ids": []},
            "risk_penalty": {"score": round(risk_penalty, 4), "weight": None,
                             "method": "negative_review_and_low_rating",
                             "evidence_ids": risk_evidence_ids},
            "preference_bonus": {"score": round(preference_bonus, 4), "weight": None,
                                 "method": "memory_category_brand_scenario_match",
                                 "evidence_ids": memory_evidence_ids[:3]},
            "avoid_penalty": {"score": round(avoid_penalty, 4), "weight": None,
                              "method": "memory_negative_preference",
                              "evidence_ids": memory_evidence_ids[-3:]},
        }

        # Build reason
        if llm_reasoning:
            reason = llm_reasoning
        else:
            reason = self._build_reason(product, final_score, user_sat)
        if preference_bonus > 0.01:
            reason += f" (匹配您{len(memory_evidence_ids)}条偏好记忆)"
        if avoid_penalty > 0:
            reason += f" (命中{int(avoid_penalty/0.05)}条避雷项)"

        risks = self._gather_risk_factors(product)
        if llm_risks:
            for r in llm_risks:
                if r not in risks:
                    risks.append(r)

        return DecisionResult(
            product_id=product.product_id,
            final_score=round(final_score, 4),
            display_score=display_score,
            score_breakdown=breakdown,
            evidence_ids=(
                list(support_evidence_ids) if support_evidence_ids
                else [f"R-{product.product_id}-{i}" for i in range(
                    len(product.rag_knowledge.user_reviews) if product.rag_knowledge else 0)]
                     + [f"POL-{product.product_id}-{i}" for i in range(
                    len(product.rag_knowledge.official_faq) if product.rag_knowledge else 0)]
            ),
            risk_factors=risks[:5],
            positive_signal=self._positive_signal(product),
            recommendation_reason=reason,
            memory_contributions=[],
            llm_relevance=llm_relevance,
            llm_reasoning=llm_reasoning,
            llm_verdict=llm_verdict,
            score_version="evidence_scoring_v2",
            evidence_confidence=round(ev_conf, 4),
            component_scores=component_scores,
            support_evidence_ids=support,
            recommendation_level=rec_level,
            hard_constraint_status="pass",
            scoring_debug={
                "relevance_source": relevance_source,
                "force_rag_relevance": force_rag_relevance,
                "ranking_score_before_modifiers": round(weighted_sum / sum(weights.values()), 4),
                "active_weights": weights,
            },
        )

    @staticmethod
    def _determine_recommendation_level(
        final_score: float, evidence_confidence: float, risk_penalty: float,
        hard_constraint_failed: bool = False,
        global_evidence_sufficient: bool = True,
    ) -> str:
        if hard_constraint_failed:
            return "not_recommended"
        # 宽松阈值: <0.25 才标记证据不足，避免普通查询全被过滤
        if evidence_confidence < 0.25:
            return "insufficient_evidence"
        # 全局证据不足 → 仅记录，不强制降级 (避免因单一证据类型缺失封顶全部商品)
        if risk_penalty >= 0.20:
            return "cautious"
        if final_score >= 0.80 and evidence_confidence >= 0.50 and risk_penalty < 0.10:
            return "strong_recommend"
        if final_score >= 0.65:
            return "recommended"
        if final_score >= 0.55:
            return "cautious"
        # “不推荐”只用于硬约束失败；分低只是当前需求下匹配较弱。
        return "cautious"

    @staticmethod
    def _apply_confidence_cap(final_score: float, recommendation_level: str) -> float:
        # V5: final_score 是排序分而非证据分。不能因资料少就改写匹配程度；
        # 资料不足由 recommendation_level/evidence_confidence 单独交付给用户。
        if recommendation_level == "cautious":
            return min(final_score, 0.80)
        return final_score

    def score(
        self,
        product: Product,
        query: str,
        keyword_score: float = 0.0,
        budget_max: float | None = None,
        scenario: str | None = None,
        visual_result: VisualResult | None = None,
        used_memories: list[dict] | None = None,
        llm_relevance: float = 0.0,
        llm_reasoning: str = "",
        llm_verdict: str = "",
        llm_strengths: list[str] | None = None,
        llm_risks: list[str] | None = None,
    ) -> DecisionResult:
        """旧版兼容入口，内部委托给 score_with_evidence。"""
        return self.score_with_evidence(
            product=product, query=query, keyword_score=keyword_score,
            budget_max=budget_max, scenario=scenario,
            visual_result=visual_result, used_memories=used_memories,
            llm_relevance=llm_relevance, llm_reasoning=llm_reasoning,
            llm_verdict=llm_verdict, llm_strengths=llm_strengths,
            llm_risks=llm_risks,
        )

    # ============================================================
    # Dimension 1: Keyword Match (0.28) — 搜索相关性
    # ============================================================

    def _calc_keyword_match(self, product: Product, query: str, keyword_score: float) -> float:
        """语义相关度 — 从检索分数映射到商业可读的 0-1 区间。

        自动检测分数类型。这里的结果是“需求匹配信号”，不是促销用展示分：
        - 0~1 的原始语义相关度不再用高基线抬升
        - 无检索分数时只使用文本重合的保守兜底
        """
        import math
        lexical = self._calc_lexical_overlap(product, query)
        if keyword_score <= 0:
            return lexical
        elif keyword_score < 1.0:
            # 原始余弦/重排分：保留差异，少量词面重合只能作为补充。
            kw_norm = min(1.0, 0.15 + 0.85 * keyword_score)
        else:
            # 旧格式关键词命中数 (>1): 对数映射
            kw_norm = min(1.0, 0.35 + 0.22 * math.log10(max(1, keyword_score)))

        return min(1.0, 0.85 * kw_norm + 0.15 * lexical)

    @staticmethod
    def _calc_lexical_overlap(product: Product, query: str) -> float:
        """无向量信号时的保守词面兜底，避免所有候选被默认抬到高分。"""
        query_lower = (query or "").lower().strip()
        if not query_lower:
            return 0.30
        product_text = " ".join(filter(None, [
            product.title, product.brand, product.category, product.sub_category,
            getattr(product.rag_knowledge, "marketing_description", "") if product.rag_knowledge else "",
        ])).lower()
        if not product_text:
            return 0.25

        if any("一" <= c <= "鿿" for c in query_lower):
            grams = {query_lower[i:i + 2] for i in range(len(query_lower) - 1)
                     if query_lower[i:i + 2].strip()}
            if not grams:
                return 0.30
            hits = sum(1 for gram in grams if gram in product_text)
            return min(0.80, 0.25 + 0.55 * hits / len(grams))

        terms = {term for term in query_lower.split() if len(term) >= 2}
        if not terms:
            return 0.30
        hits = sum(1 for term in terms if term in product_text)
        return min(0.80, 0.25 + 0.55 * hits / len(terms))

    # ============================================================
    # Dimension 2: Budget Fit (0.22) — 价格合适度
    # ============================================================

    def _calc_budget_fit(self, product: Product, budget_max: float | None) -> float:
        """预算匹配 — 无约束时接近满分，有约束时合理扣分。"""
        price = product.base_price
        if budget_max is None or budget_max <= 0:
            return 0.98  # No constraint → near-perfect fit
        if price <= budget_max:
            ratio = price / max(budget_max, 1)
            if ratio < 0.3:
                return 0.98
            elif ratio < 0.6:
                return 0.93
            else:
                return 0.92
        else:
            overage = (price - budget_max) / budget_max
            if overage < 0.2:
                return 0.80
            elif overage < 0.5:
                return 0.60
            else:
                return max(0.0, 0.45 - overage)

    # ============================================================
    # Dimension 3: User Satisfaction (0.18) — 用户口碑
    # ============================================================

    def _calc_user_satisfaction(self, product: Product) -> float:
        """用户满意度 — 有评论奖励、好评文本加分，推高下单信心。"""
        if not product.rag_knowledge or not product.rag_knowledge.user_reviews:
            return 0.80  # 无评论不惩罚

        reviews = product.rag_knowledge.user_reviews
        ratings = [r.rating for r in reviews]
        avg = sum(ratings) / len(ratings)
        score = avg / 5.0

        # Bayesian连续平滑: C=3条虚拟评论，prior=0.80
        C = 3
        score = (score * len(reviews) + 0.80 * C) / (len(reviews) + C)

        # 评论数量微奖励 — 经过市场验证的商品值得加分
        n = len(reviews)
        if n >= 20:
            score += 0.08
        elif n >= 5:
            score += 0.05
        elif n >= 2:
            score += 0.03

        # 好评文本关键词加分
        positive_keywords = ["推荐", "好用", "满意", "回购", "值得", "不错",
                            "好评", "喜欢", "性价比", "赞", "棒"]
        positive_count = 0
        for r in reviews:
            content = r.content.lower() if r.content else ""
            for kw in positive_keywords:
                if kw in content:
                    positive_count += 1
                    break
        if positive_count >= 3:
            score += 0.03

        return max(0.0, min(1.0, score))

    # ============================================================
    # Dimension 4: Value Score (0.14) — 性价比
    # ============================================================

    def _calc_value_score(self, product: Product, sub_category: str) -> float:
        """性价比 — 品质分 / 价格分，高评分低价 = 高性价比。"""
        price = product.base_price
        if price <= 0:
            return 0.65

        benchmark = CATEGORY_BENCHMARKS.get(sub_category, (price, 1.0))
        median_price, quality_mult = benchmark

        # Quality score from reviews
        quality = 0.65  # default
        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            ratings = [r.rating for r in product.rag_knowledge.user_reviews]
            quality = 0.55 + 0.45 * (sum(ratings) / len(ratings)) / 5.0

        # Price score: cheaper than median = good
        if price <= median_price * 0.5:
            price_score = 0.95
        elif price <= median_price * 0.8:
            price_score = 0.88
        elif price <= median_price:
            price_score = 0.82
        elif price <= median_price * 1.5:
            price_score = 0.72
        else:
            price_score = 0.58

        value = quality_mult * (0.5 * quality + 0.5 * price_score)
        return min(1.0, max(0.3, value))

    # ============================================================
    # Dimension 5: Scenario Fit (0.10) — 场景适配
    # ============================================================

    def _calc_scenario_fit(self, product: Product, scenario: str | None, query: str,
                           scenario_keywords: list[str] | None = None) -> float:
        """场景匹配 — LLM 动态关键词 + 字典兜底 + query语义匹配。

        权重已提至 10%，有场景时不再惩罚。
        """
        # 构建搜索文本：标题 + 描述 + 部分评论 + 部分FAQ
        parts = [product.title]
        if product.rag_knowledge:
            if product.rag_knowledge.marketing_description:
                parts.append(product.rag_knowledge.marketing_description)
            for rev in (product.rag_knowledge.user_reviews or [])[:3]:
                parts.append(getattr(rev, 'content', str(rev)))
            for faq in (product.rag_knowledge.official_faq or [])[:2]:
                parts.append(getattr(faq, 'question', str(faq)))
                parts.append(getattr(faq, 'answer', str(faq)))
        search_text = " ".join(str(p) for p in parts).lower()
        query_lower = query.lower()

        hits = 0
        # Query 文本匹配
        for i in range(max(1, len(query_lower) - 1)):
            bigram = query_lower[i:i+2]
            if len(bigram) == 2 and bigram in search_text:
                hits += 1

        # Scenario 关键词匹配（如有）
        scenario_kw_map = {
            "flight": ["航空", "飞机", "安检", "登机", "随身", "托运", "100wh"],
            "commute": ["轻便", "便携", "无线", "降噪", "小巧", "通勤", "日常"],
            "travel": ["便携", "快充", "大容量", "航空", "轻", "旅行", "长续航"],
            "business_trip": ["便携", "快充", "大容量", "商务", "航空", "安检", "出差"],
            "office": ["静音", "舒适", "专业", "商务", "办公", "桌面"],
            "sport": ["防水", "防汗", "运动", "无线", "轻量", "透气", "训练"],
            "running": ["透气", "缓震", "回弹", "轻量", "碳板", "跑步", "竞速"],
            "fitness": ["弹力", "速干", "训练", "透气", "健身", "吸汗", "运动"],
            "outdoor": ["防水", "耐用", "耐磨", "防滑", "透气", "户外", "登山", "轻量", "防泼水"],
            "gaming": ["低延迟", "RGB", "高刷", "HDR", "散热", "游戏", "电竞"],
            "music": ["Hi-Res", "降噪", "音质", "LDAC", "无损", "重低音"],
            "desk": ["静音", "专业", "商务", "办公", "舒适", "桌面"],
        }
        if scenario:
            keywords = scenario_keywords if scenario_keywords else scenario_kw_map.get(scenario, [])
            for kw in keywords:
                if kw.lower() in search_text:
                    hits += 2

        base = 0.70  # 统一基线，有场景关键词命中加分，无命中不惩罚
        return min(1.0, base + hits * 0.08)

    # ============================================================
    # Dimension 6: Spec Quality (0.08) — 规格品质
    # ============================================================

    def _calc_spec_quality(self, product: Product, sub_category: str, query: str = "",
                           spec_keywords: list[str] | None = None) -> float:
        """规格品质 — LLM spec_keywords 优先匹配，兜底自动检测描述文本规格丰富度。"""
        if not product.rag_knowledge:
            return 0.65

        desc = product.rag_knowledge.marketing_description.lower()
        title = product.title.lower()
        full_text = title + " " + desc
        query_lower = query.lower()

        # LLM spec_keywords 优先 — 品类全覆盖，零字典
        if spec_keywords:
            score = 0.82
            for s in spec_keywords:
                if s.lower() in full_text:
                    if query_lower and s.lower() in query_lower:
                        score += 0.12
                    else:
                        score += 0.08
            return min(1.0, score)

        # 兜底: 描述文本规格丰富度自动评分 — 品类无关，无限可扩展
        return self._calc_spec_richness(full_text)

    @staticmethod
    def _calc_spec_richness(text: str) -> float:
        """自动检测描述文本中的规格信号密度 — 零字典，品类无关。"""
        import re

        # 数字+单位 (30ml/100W/5G/5000mAh/120hz等)
        num_unit = len(re.findall(
            r'\d+\.?\d*\s*(ml|g|kg|w|hz|k|mm|cm|m|mah|a|v|db|'
            r'小时|分钟|天|月|年|颗|片|瓶|元|块|粒|滴)',
            text
        ))
        # 技术句式标记
        tech_markers = len(re.findall(
            r'(支持|搭载|采用|配备|内置|含|添加|注入|融合|升级|全新|'
            r'专业|旗舰|高端|精选)',
            text
        ))
        # 百分比 / 倍数 / 范围
        pct_range = len(re.findall(r'\d+\.?\d*\s*%|\d+\s*倍|\d+[-~]\d+', text))
        # 规格缩写 (ANC/LDAC/IP68/SPF50/PA+++/OLED等)
        tech_abbr = len(re.findall(r'\b[a-z]{2,}\+*\d*\b', text))

        total = num_unit + tech_markers + pct_range + tech_abbr

        if total >= 10:
            return 0.96
        elif total >= 6:
            return 0.90
        elif total >= 3:
            return 0.84
        elif total >= 1:
            return 0.78
        else:
            return 0.74

    # ============================================================
    # Risk (subtractive) — 风险扣分
    # ============================================================

    def _calc_risk_penalty(self, product: Product) -> float:
        """风险扣分 — V4: 返回 (penalty, risk_evidence_ids)。"""
        penalty, _ = self._calc_risk_penalty_with_evidence(product)
        return penalty

    def _calc_risk_penalty_with_evidence(self, product: Product) -> tuple[float, list[str]]:
        """风险扣分 + 风险证据ID绑定。"""
        penalty = 0.0
        risk_ids: list[str] = []

        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            reviews = product.rag_knowledge.user_reviews
            ratings = [r.rating for r in reviews]

            very_low = sum(1 for r in ratings if r <= 2)
            # 记录风险证据
            if very_low > 0:
                for i, r in enumerate(reviews):
                    if r.rating <= 2:
                        risk_ids.append(f"R-{product.product_id}-{i}")

            if very_low >= 3:
                penalty += 0.08
            elif very_low >= 1:
                penalty += 0.02

            if len(ratings) >= 3:
                avg = sum(ratings) / len(ratings)
                if avg < 3.0:
                    penalty += 0.05
                elif avg < 3.5:
                    penalty += 0.02

        return min(0.20, penalty), risk_ids

    def _calc_risk_bonus(self, product: Product) -> float:
        """额外加分 — 特别优秀的商品获得加成。"""
        bonus = 0.0

        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            reviews = product.rag_knowledge.user_reviews
            ratings = [r.rating for r in reviews]

            if len(ratings) >= 5:
                avg = sum(ratings) / len(ratings)
                if avg >= 4.8:
                    bonus += 0.05  # Outstanding reviews
                elif avg >= 4.5:
                    bonus += 0.02  # Very good reviews

            # Many reviews with high ratings = trusted product
            if len(ratings) >= 10 and sum(ratings) / len(ratings) >= 4.5:
                bonus += 0.03

        return bonus

    # ============================================================
    # Helpers
    # ============================================================

    def _gather_risk_factors(self, product: Product) -> list[str]:
        """风险项收紧版（促单原则，用户拍板）。

        旧规则"有 1 条 ≤2 星差评就警告"在本数据集下形同虚设——实盘 998/1000 商品
        含差评，所有卡 100% 亮同一条黄警，零区分度纯噪音。收紧为：差评 ≥2 条
        或均分 <3.5 才亮，且文案带事实（诚实底线）。好评信号见 _positive_signal。
        """
        risks = []
        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            reviews = product.rag_knowledge.user_reviews
            low_reviews = [r for r in reviews if r.rating <= 2]
            if len(low_reviews) >= 2:
                risks.append(f"{len(reviews)} 条评价中 {len(low_reviews)} 条差评")
            ratings = [r.rating for r in reviews]
            if len(ratings) >= 3 and sum(ratings) / len(ratings) < 3.5:
                risks.append("综合评分偏低")
        return risks[:3]

    @staticmethod
    def _positive_signal(product: Product) -> str:
        """好评率正向信号（促单）：评论 ≥3 条且好评率 ≥60% 时输出事实文案。"""
        if not (product.rag_knowledge and product.rag_knowledge.user_reviews):
            return ""
        reviews = product.rag_knowledge.user_reviews
        if len(reviews) < 3:
            return ""
        good = sum(1 for r in reviews if r.rating >= 4)
        rate = good / len(reviews)
        if rate < 0.6:
            return ""
        return f"{len(reviews)} 条评价 {round(rate * 100)}% 好评"

    def _build_reason(self, product: Product, score: float, user_sat: float) -> str:
        if score >= 0.80:
            tier = "强烈推荐"
        elif score >= 0.65:
            tier = "值得购买"
        elif score >= 0.50:
            tier = "可以考虑"
        else:
            tier = "仅供参考"

        review_str = ""
        if product.rag_knowledge and product.rag_knowledge.user_reviews:
            ratings = [r.rating for r in product.rag_knowledge.user_reviews]
            avg = sum(ratings) / len(ratings)
            review_str = f"，用户评分{avg:.1f}/5({len(ratings)}人)"

        return f"{tier} | {product.brand} {product.title[:25]} | ¥{product.base_price}{review_str}"
