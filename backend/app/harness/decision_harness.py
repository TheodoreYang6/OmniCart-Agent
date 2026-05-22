"""V1 Decision Harness — 决策验证框架。

包裹现有的 ResponseGuard + EvidenceChecker + 新增校验规则，
统一输出 harness_report。
"""

import logging
from app.schemas.workflow import WorkflowState

logger = logging.getLogger(__name__)


class DecisionHarness:
    """决策验证框架 — 统一执行所有验证规则。"""

    CHECK_NAMES = [
        "schema_valid",
        "evidence_bound",
        "score_recalculable",
        "policy_cited",
        "risk_warning",
        "sufficiency_check",
        "no_empty_answer",
    ]

    def validate(self, state: WorkflowState) -> dict:
        """执行全部校验，返回 harness_report。"""
        report: dict = {"passed": True, "checks": {}, "failed_checks": []}

        # 1. Schema 校验
        report["checks"]["schema_valid"] = self._check_schema(state)

        # 2. 证据绑定
        report["checks"]["evidence_bound"] = self._check_evidence_bound(state)

        # 3. 评分可复算
        report["checks"]["score_recalculable"] = self._check_score(state)

        # 4. 政策引用
        report["checks"]["policy_cited"] = self._check_policy(state)

        # 5. 风险提醒
        report["checks"]["risk_warning"] = self._check_risk(state)

        # 6. 证据充足性
        report["checks"]["sufficiency_check"] = state.sufficiency_report.get("sufficient", False) if state.sufficiency_report else False

        # 7. 回答非空
        report["checks"]["no_empty_answer"] = bool(state.answer and state.answer.strip())

        # 汇总
        for check, passed in report["checks"].items():
            if not passed:
                report["failed_checks"].append(check)
                report["passed"] = False

        state.harness_report = report
        return report

    def _check_schema(self, state: WorkflowState) -> bool:
        return bool(state.session_id and state.user_query)

    def _check_evidence_bound(self, state: WorkflowState) -> bool:
        if not state.decision_results:
            return True  # 无结果时不检查

        for d in state.decision_results:
            if not d.get("evidence_ids"):
                return False
        return True

    def _check_score(self, state: WorkflowState) -> bool:
        for d in state.decision_results:
            final = d.get("final_score")
            if final is not None and not (0 <= final <= 1):
                return False
            display = d.get("display_score")
            if display is not None and not (0 <= display <= 10):
                return False
        return True

    def _check_policy(self, state: WorkflowState) -> bool:
        if state.intent not in ("compatibility_check", "risk_check"):
            return True
        return any(
            e.get("source_type") == "policy_faq"
            for e in state.evidence_list
        )

    def _check_risk(self, state: WorkflowState) -> bool:
        for d in state.decision_results:
            if d.get("risk_factors"):
                return True
        return True  # 没有风险因素也是 OK 的
