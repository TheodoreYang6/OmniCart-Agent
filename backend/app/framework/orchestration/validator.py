"""PlanValidator —— LLM 生成计划的硬校验（计划层 harness）。

封闭动作空间原则：LLM 只能在「已注册 pipeline 能力 + llm_exposed 工具白名单」内
排列组合，任何越界即整体拒绝（由调用方降级 RulePlanner），不做局部修补。
唯一宽容项：末步缺 response 时自动追加（保证必有用户回复）。
"""

from __future__ import annotations

import logging

from app.framework.orchestration.plan import ExecutionPlan, PlanStep

logger = logging.getLogger(__name__)

__all__ = ["PIPELINE_CAPABILITIES", "PlanValidator"]

# 与 graph.py @register_capability 注册名保持一致（治理校验兜底防漂移）
PIPELINE_CAPABILITIES = {"visual", "retrieval", "compare_retrieval", "multi_query_retrieval", "reranker",
                         "evidence_check", "decision", "response"}

MAX_PLAN_STEPS = 8


class PlanValidator:
    """校验 LLM 输出的计划 JSON，通过则组装 ExecutionPlan，失败返回 None。"""

    def __init__(self, allowed_tools: set[str]):
        self._allowed_tools = allowed_tools   # llm_exposed 白名单工具名（B1 过滤产物）

    def validate(self, raw: dict, intent: str, trigger: str) -> ExecutionPlan | None:
        steps_raw = (raw or {}).get("steps")
        if not isinstance(steps_raw, list) or not (1 <= len(steps_raw) <= MAX_PLAN_STEPS):
            return self._reject(f"steps 数量非法: {len(steps_raw) if isinstance(steps_raw, list) else steps_raw}")

        steps: list[PlanStep] = []
        seen_ids: list[str] = []
        group_deps: dict[str, list[str]] = {}
        for i, s in enumerate(steps_raw):
            if not isinstance(s, dict):
                return self._reject(f"step[{i}] 非对象")
            sid = str(s.get("id") or s.get("step_id") or "").strip()
            cap = str(s.get("capability") or "").strip()
            deps = s.get("depends_on") or []
            group = s.get("parallel_group") or None
            if not sid or sid in seen_ids:
                return self._reject(f"step[{i}] id 缺失或重复: {sid!r}")
            # 能力封闭词表：pipeline 能力 或 tool:<白名单工具>
            if cap.startswith("tool:"):
                if cap[len("tool:"):] not in self._allowed_tools:
                    return self._reject(f"受限/未知工具: {cap!r}")
            elif cap not in PIPELINE_CAPABILITIES:
                return self._reject(f"未知 capability: {cap!r}")
            # 依赖只允许引用先序 id（天然无环）
            if not isinstance(deps, list) or any(d not in seen_ids for d in deps):
                return self._reject(f"step {sid!r} 依赖非法（只能引用先序步骤）: {deps}")
            # 并行组内依赖必须一致（supervisor gather 语义要求）
            if group is not None:
                group = str(group)
                if group in group_deps and sorted(group_deps[group]) != sorted(deps):
                    return self._reject(f"并行组 {group!r} 内依赖不一致")
                group_deps.setdefault(group, list(deps))
            steps.append(PlanStep(step_id=sid, capability=cap,
                                  depends_on=[str(d) for d in deps], parallel_group=group))
            seen_ids.append(sid)

        # 唯一宽容项：末步必须是 response，缺失自动追加（依赖最后一步）
        if steps[-1].capability != "response":
            if len(steps) >= MAX_PLAN_STEPS:
                return self._reject("末步非 response 且已达步数上限")
            steps.append(PlanStep(step_id="s_auto_response", capability="response",
                                  depends_on=[steps[-1].step_id]))

        try:
            max_reflects = int((raw or {}).get("max_reflects", 1))
        except (TypeError, ValueError):
            max_reflects = 1
        plan = ExecutionPlan(
            intent=intent, steps=steps,
            max_reflects=max(0, min(2, max_reflects)),
            rationale=str((raw or {}).get("rationale", ""))[:200],
        )
        plan.meta["planner"] = "llm"
        plan.meta["trigger"] = trigger
        return plan

    @staticmethod
    def _reject(reason: str) -> None:
        logger.warning(f"LLM plan rejected: {reason}")
        return None
