"""V4 Evidence Scoring Helper — 从 state 提取 RAG 证据指标，替代 LLM relevance。

核心职责:
- 根据 evidence_list / retrieved_products 构建 ProductEvidenceProfile
- 计算 EvidenceMetrics (relevance/coverage/reliability/consistency/confidence)
- 提供 rag_relevance 替代旧的 LLM relevance
"""

import math
import re
import logging
from typing import Any

from app.schemas.evidence_metrics import (
    ComponentScore,
    EvidenceMetrics,
    ProductEvidenceProfile,
)

logger = logging.getLogger(__name__)

# ---- 证据类型归一化 ----

_SOURCE_TYPE_MAP: dict[str, str] = {
    "summary": "product_profile",
    "profile": "product_profile",
    "text_retrieval": "product_profile",
    "mkt": "marketing",
    "marketing": "marketing",
    "faq": "official_faq",
    "policy_faq": "official_faq",
    "policy": "official_faq",
    "rev": "user_review",
    "review": "user_review",
    "review_positive": "user_review_positive",
    "review_risk": "user_review_risk",
    "sku": "sku_structured",
    "sku_structured": "sku_structured",
    "visual": "visual_evidence",
}

_SOURCE_WEIGHTS: dict[str, float] = {
    "sku_structured": 0.95,
    "official_faq": 0.90,
    "product_profile": 0.85,
    "user_review_positive": 0.78,
    "user_review_risk": 0.80,
    "user_review": 0.75,
    "visual_evidence": 0.70,
    "marketing": 0.60,
    "unknown": 0.50,
}

# 各类 intent 所需的证据类型组 (OR 关系)
_REQUIRED_SOURCES = {
    "recommend": [
        ["product_profile", "marketing"],
        ["official_faq"],
        ["user_review_positive", "user_review", "user_review_risk"],
    ],
    "risk_check": [
        ["user_review_risk", "user_review"],
        ["official_faq"],
    ],
    "compatibility_check": [
        ["product_profile"],
        ["official_faq"],
        ["sku_structured", "visual_evidence"],
    ],
    "compare": [
        ["sku_structured"],
        ["official_faq"],
        ["product_profile"],
    ],
    "default": [
        ["product_profile", "marketing"],
        ["user_review", "official_faq"],
    ],
}

# Aspect 检测关键词
_ASPECT_KEYWORDS: dict[str, list[str]] = {
    "budget": ["预算", "以内", "以下", "元", "块钱", "便宜", "贵"],
    "scenario": ["出差", "通勤", "运动", "户外", "旅行", "办公", "游戏"],
    "risk": ["敏感", "刺痛", "泛红", "闭口", "过敏", "副作用", "发热", "爆炸"],
    "skin_type": ["敏感肌", "油皮", "干皮", "混油", "混干", "痘痘"],
    "storage": ["拍照", "摄像", "视频", "4k", "8k", "存储", "内存", "256", "512"],
    "size": ["尺码", "s码", "m码", "l码", "身高", "175", "180", "165"],
    "color": ["白色", "黑色", "蓝色", "红色", "颜色", "透明"],
    "taste": ["酸", "苦", "新手", "口味", "好喝", "浓郁"],
    "flight": ["飞机", "上飞机", "安检", "登机", "ml", "100wh", "托运"],
    "battery": ["充电", "电池", "续航", "快充", "mAh"],
    "camera": ["拍照", "摄像", "视频", "4k", "潜望", "长焦", "主摄", "夜拍"],
    "compatibility": ["兼容", "适配", "支持", "能不能"],
}

# Aspect → 支撑证据类型
_ASPECT_EVIDENCE: dict[str, list[str]] = {
    "budget": ["product_profile", "sku_structured"],
    "scenario": ["marketing", "official_faq", "user_review"],
    "risk": ["user_review_risk"],
    "skin_type": ["official_faq", "user_review_risk"],
    "storage": ["sku_structured", "official_faq"],
    "size": ["sku_structured", "official_faq"],
    "color": ["sku_structured", "official_faq"],
    "taste": ["official_faq", "user_review"],
    "flight": ["official_faq", "user_review"],
    "battery": ["product_profile", "official_faq"],
    "camera": ["product_profile", "official_faq"],
    "compatibility": ["product_profile", "official_faq", "sku_structured"],
}


def normalize_source_type(raw_type: str) -> str:
    """将 chunk_type / source_type 归一化。"""
    if not raw_type:
        return "unknown"
    return _SOURCE_TYPE_MAP.get(raw_type.lower(), "unknown")


def normalize_relevance_score(x: float | None) -> float:
    """统一相关度分数到 0~1。

    注意: RRF 融合分数 (如 0.016) 是排序分不是绝对相关度,
    低于 0.05 的视为无有效信号, 返回 0.0 让调用方降级到关键词匹配。
    """
    if x is None or x <= 0:
        return 0.0
    # RRF 排序分区间 (0, 0.05) → 不是有效相关度信号, 不采用
    if 0 < x < 0.05:
        return 0.0
    # Reranker 或其他 0-1 校准分数
    if 0 < x <= 1.0:
        return max(0.0, min(1.0, x))
    # > 1.0 的关键词匹配分使用对数映射
    return min(1.0, 0.45 + 0.28 * math.log10(max(1, x)))


class EvidenceScoringHelper:
    """从 RAG 证据中提取评分所需的所有指标。"""

    def build_profiles(
        self,
        evidence_list: list[dict],
        retrieved_products: list[dict],
    ) -> dict[str, ProductEvidenceProfile]:
        """按 product_id 聚合 evidence。"""
        profiles: dict[str, ProductEvidenceProfile] = {}

        # 收集所有 product_id
        all_pids = set()
        for p in retrieved_products:
            pid = p.get("product_id", "")
            if pid:
                all_pids.add(pid)
        for e in evidence_list:
            pid = e.get("product_id", "")
            if pid:
                all_pids.add(pid)

        for pid in all_pids:
            profiles[pid] = ProductEvidenceProfile(product_id=pid)

        # 归类 evidence
        for e in evidence_list:
            pid = e.get("product_id", "")
            if not pid or pid not in profiles:
                continue
            pf = profiles[pid]
            eid = e.get("evidence_id", "") or e.get("chunk_id", "") or ""
            raw_type = e.get("source_type", "") or e.get("chunk_type", "") or "unknown"
            norm = normalize_source_type(raw_type)

            pf.evidence_count_by_type[norm] = pf.evidence_count_by_type.get(norm, 0) + 1
            if eid:
                pf.evidence_ids_by_type.setdefault(norm, []).append(eid)

            if norm == "user_review_positive":
                pf.positive_review_ids.append(eid)
            elif norm == "user_review_risk":
                pf.risk_review_ids.append(eid)
            elif norm == "official_faq":
                pf.faq_ids.append(eid)
            elif norm == "marketing":
                pf.marketing_ids.append(eid)
            elif norm == "product_profile":
                pf.summary_ids.append(eid)
            elif norm == "sku_structured":
                pf.sku_ids.append(eid)

            # 分数统计
            score = e.get("score", 0) or e.get("retrieval_score", 0) or 0
            conf = e.get("confidence", 0) or 0
            if score > 0:
                if score > pf.max_retrieval_score:
                    pf.max_retrieval_score = score
                pf.avg_retrieval_score = (
                    pf.avg_retrieval_score * (pf.evidence_count_by_type.get(norm, 1) - 1) + score
                ) / pf.evidence_count_by_type.get(norm, 1)

            if norm in ("user_review_positive", "user_review_risk", "official_faq", "sku_structured"):
                pf.top_evidence_ids.append(eid)

        # 计算 source_reliability
        for pf in profiles.values():
            weights = []
            for etype, count in pf.evidence_count_by_type.items():
                w = _SOURCE_WEIGHTS.get(etype, 0.5)
                weights.extend([w] * count)
            pf.source_reliability = sum(weights) / len(weights) if weights else 0.5

        return profiles

    def compute_rag_relevance(
        self,
        product_item: dict,
        profile: ProductEvidenceProfile,
        query: str = "",
    ) -> tuple[float, str]:
        """计算 RAG 相关度 (不依赖 LLM)。

        优先级: reranker_score > retrieval_score > chunk_score > keyword_fallback
        注意: RRF排序分(0.01-0.02)会被 normalize_relevance_score 过滤为0, 自动降级。
        """
        # 1. reranker score
        rr = product_item.get("reranker_score") or product_item.get("relevance_score")
        if rr is not None and rr > 0:
            norm = normalize_relevance_score(rr)
            if norm > 0:
                return norm, "reranker_score"

        # 2. evidence profile 中的 max_rerank
        if profile.max_rerank_score > 0:
            norm = normalize_relevance_score(profile.max_rerank_score)
            if norm > 0:
                return norm, "profile_max_rerank"

        # 3. product item 中的 score (关键词匹配分, 通常 > 1)
        raw_score = product_item.get("score", 0) or product_item.get("retrieval_score", 0)
        if raw_score > 0:
            norm = normalize_relevance_score(raw_score)
            if norm > 0:
                return norm, "retrieval_score"

        # 4. evidence profile avg
        if profile.avg_retrieval_score > 0:
            norm = normalize_relevance_score(profile.avg_retrieval_score)
            if norm > 0:
                return norm, "profile_avg_retrieval"

        return 0.0, "no_evidence"

    def compute_metrics(
        self,
        product_id: str,
        profile: ProductEvidenceProfile,
        query: str = "",
        constraints: Any = None,
        intent: str = "",
    ) -> EvidenceMetrics:
        """计算证据质量指标 (V4.1 修正)。"""
        available_types = set(profile.evidence_ids_by_type.keys())

        # 1. evidence_relevance: 来自 retrieval/rerank 分数 (修正命名)
        if profile.max_rerank_score > 0:
            ev_rel = normalize_relevance_score(profile.max_rerank_score)
        elif profile.max_retrieval_score > 0:
            ev_rel = normalize_relevance_score(profile.max_retrieval_score)
        elif profile.avg_retrieval_score > 0:
            ev_rel = normalize_relevance_score(profile.avg_retrieval_score)
        else:
            ev_rel = 0.0

        # 2. source_quality: source_weight 平均值 (原 evidence_relevance 的正确含义)
        quality_scores = [_SOURCE_WEIGHTS.get(t, 0.5) for t in available_types if available_types]
        src_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        # 3. source_coverage: 基础 required groups + 动态 aspect required groups
        aspects = self._detect_aspects(query, constraints)
        required_groups = self._build_required_groups(intent, aspects)
        matched = 0
        for group in required_groups:
            if any(t in available_types for t in group):
                matched += 1
        source_cov = matched / len(required_groups) if required_groups else 0.5
        missing = []
        for group in required_groups:
            if not any(t in available_types for t in group):
                missing.append(group[0])

        # 4. aspect_coverage
        if not aspects:
            aspect_cov = 0.75
        else:
            covered = 0
            for aspect in aspects:
                req_types = _ASPECT_EVIDENCE.get(aspect, [])
                if any(t in available_types for t in req_types):
                    covered += 1
            aspect_cov = covered / len(aspects)

        # 5. source_reliability
        src_rel = profile.source_reliability if profile.source_reliability > 0 else 0.5

        # 6. evidence_consistency
        consistency = 1.0
        constraints_dict = constraints.model_dump() if hasattr(constraints, "model_dump") else (constraints or {})
        budget_max = constraints_dict.get("budget_max") if isinstance(constraints_dict, dict) else None
        if budget_max and not profile.sku_ids:
            consistency -= 0.10
        if profile.positive_review_ids and profile.risk_review_ids:
            consistency = 0.90

        # 7. evidence_confidence (修正公式)
        evidence_conf = (
            0.25 * ev_rel
            + 0.20 * source_cov
            + 0.20 * aspect_cov
            + 0.15 * src_quality
            + 0.10 * src_rel
            + 0.10 * consistency
        )

        support_ids = self.select_support_evidence_ids(profile, limit=5)

        return EvidenceMetrics(
            evidence_relevance=round(ev_rel, 4),
            source_quality=round(src_quality, 4),
            source_coverage=round(source_cov, 4),
            aspect_coverage=round(aspect_cov, 4),
            source_reliability=round(src_rel, 4),
            evidence_consistency=round(consistency, 4),
            evidence_confidence=round(evidence_conf, 4),
            selected_evidence_ids_by_type={
                k: v[:3] for k, v in profile.evidence_ids_by_type.items()
            },
            missing_evidence_types=missing,
            relevance_source="rag_evidence",
            support_evidence_ids=support_ids,
        )

    def _build_required_groups(self, intent: str, aspects: list[str]) -> list[list[str]]:
        """构建 required groups (基础 + 动态aspect要求)。"""
        base = _REQUIRED_SOURCES.get(intent, _REQUIRED_SOURCES["default"])
        groups = [list(g) for g in base]  # deep copy

        # 动态追加: 根据 aspect 增加必需证据类型
        risk_signals = {"risk", "skin_type"}
        flight_signals = {"flight"}
        budget_signals = {"budget"}
        structured_signals = {"size", "color", "storage", "taste"}

        detected = set(aspects)
        if detected & risk_signals:
            if not any("user_review_risk" in g or "user_review" in g for g in groups):
                groups.append(["user_review_risk", "user_review"])
        if detected & flight_signals:
            if not any("official_faq" in g for g in groups):
                groups.append(["official_faq", "policy_faq"])
        if detected & budget_signals:
            if not any("product_profile" in g or "sku_structured" in g for g in groups):
                groups.append(["product_profile", "sku_structured"])
        if detected & structured_signals:
            if not any("sku_structured" in g or "official_faq" in g for g in groups):
                groups.append(["sku_structured", "official_faq"])

        return groups

    def select_support_evidence_ids(
        self,
        profile: ProductEvidenceProfile,
        limit: int = 5,
    ) -> list[str]:
        """选取顶层支撑证据 ID。"""
        result = []
        # 优先级: faq > positive_review > summary > marketing
        for ids in [profile.faq_ids, profile.positive_review_ids,
                     profile.summary_ids, profile.marketing_ids]:
            for eid in ids:
                if eid not in result:
                    result.append(eid)
                    if len(result) >= limit:
                        return result
        return result[:limit]

    def _detect_aspects(self, query: str, constraints: Any) -> list[str]:
        """规则检测用户关心的方面，不调 LLM。"""
        aspects = []
        q = query.lower()
        c = constraints
        if hasattr(c, "budget_max") and c.budget_max:
            aspects.append("budget")
        elif any(kw in q for kw in _ASPECT_KEYWORDS["budget"]):
            aspects.append("budget")

        if hasattr(c, "scenario") and c.scenario:
            aspects.append("scenario")
        elif any(kw in q for kw in _ASPECT_KEYWORDS["scenario"]):
            aspects.append("scenario")

        for aspect in ["risk", "skin_type", "storage", "size", "color",
                        "taste", "flight", "battery", "camera", "compatibility"]:
            if any(kw in q for kw in _ASPECT_KEYWORDS[aspect]):
                if aspect not in aspects:
                    aspects.append(aspect)

        return aspects
