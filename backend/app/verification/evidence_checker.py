"""V1 Evidence Sufficiency Checker — 检查检索证据是否足够支撑推荐结论。

在 Retrieval 之后、Decision 之前执行。
如果证据不足，降低后续推荐的置信度标记。
"""

from app.schemas.workflow import WorkflowState


class EvidenceSufficiencyChecker:
    """证据充足性检查器"""

    # 不同意图所需的最少证据类型
    MIN_EVIDENCE_TYPES = {
        "recommend": {"text_retrieval", "review_positive"},
        "risk_check": {"review_risk"},
        "compare": {"text_retrieval", "review_positive"},
        "compatibility_check": {"policy_faq"},
        "alternative": {"text_retrieval"},
    }

    def check(self, state: WorkflowState) -> dict:
        report = {
            "total_evidence": len(state.evidence_list),
            "evidence_types": set(),
            "sufficient": True,
            "missing_types": [],
            "suggestion": "",
        }

        for e in state.evidence_list:
            t = e.get("source_type", "other")
            report["evidence_types"].add(t)

        required = self.MIN_EVIDENCE_TYPES.get(state.intent, {"text_retrieval"})
        missing = required - report["evidence_types"]

        if missing:
            report["sufficient"] = False
            report["missing_types"] = list(missing)
            report["suggestion"] = self._generate_suggestion(missing, state)

        return report

    def _generate_suggestion(self, missing: set, state: WorkflowState) -> str:
        suggestions = {
            "review_positive": "缺少用户好评证据，建议补充用户评价来源",
            "review_risk": "缺少差评风险证据，建议搜索用户负面评论",
            "policy_faq": "缺少政策/FAQ证据，建议查询官方规则",
            "text_retrieval": "缺少商品文本匹配证据，建议调整搜索关键词",
        }
        parts = [suggestions.get(m, f"缺少{m}类型证据") for m in missing]
        return "; ".join(parts)
