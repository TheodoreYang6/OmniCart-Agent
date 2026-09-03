"""ExecutionPlan —— 运行时执行计划（Plan-and-Execute 模式的数据契约）。

Planner 按 intent 生成计划；supervisor 执行器按依赖/并行组循环派发。
capability 取值为 graph.py 中注册的节点能力名（"retrieval"/"reranker"/...），
或 ``tool:<name>`` 表示派发 ToolRegistry 中的工具。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["PlanStep", "ExecutionPlan"]


class PlanStep(BaseModel):
    """单个计划步骤。"""

    step_id: str
    capability: str  # "visual"/"retrieval"/"reranker"/"evidence_check"/"decision"/"response" 或 "tool:<name>"
    depends_on: list[str] = Field(default_factory=list)
    parallel_group: str | None = None
    optional: bool = False  # 失败/跳过不致命


class ExecutionPlan(BaseModel):
    """执行计划：步骤 + 依赖 + 并行组 + 反思预算。"""

    intent: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    max_reflects: int = 1
    rationale: str = ""  # planner 依据（进 trace）
    meta: dict = Field(default_factory=dict)  # 计划级参数（如 compare_targets），供 capability 读取

    def next_ready(self, done: set[str]) -> list[PlanStep]:
        """返回依赖已满足且未完成的下一批步骤。

        - 无 parallel_group：只返回按计划顺序遇到的第一个就绪步骤（串行语义）；
        - 有 parallel_group：返回该组内所有就绪步骤（供 gather 并发）。
        """
        for step in self.steps:
            if step.step_id in done:
                continue
            if any(dep not in done for dep in step.depends_on):
                continue
            if step.parallel_group:
                group = [
                    s
                    for s in self.steps
                    if s.parallel_group == step.parallel_group
                    and s.step_id not in done
                    and all(dep in done for dep in s.depends_on)
                ]
                return group
            return [step]
        return []
