"""共享节点 check_iteration —— 唯一的预算守卫点。

对齐 amap ``standard/nodes/guard.py``：所有回环（execute_tools /
check_completion，以及将来的 recover）都汇聚到这里，预算判定**只有这一处**。

为什么要单一汇聚点：原 ``OmniAgent`` 用 ``for round_no in range(1, max_rounds+1)``
内联控制轮次，轮次判定和业务逻辑纠缠在同一个函数里；改成图之后如果每条回环各自
判预算，就会出现"某条路径漏判导致死循环"这类只在特定分支触发的故障。
汇聚成一个节点后，死循环的防线只有一处，可以单测穷尽。
"""

from __future__ import annotations

from app.core.config import AGENT_LOOP_DEEP_ROUNDS, AGENT_LOOP_MAX_ROUNDS
from app.schemas.workflow import WorkflowState

__all__ = ["budget_for", "check_iteration"]

# 即使部署环境遗留了旧的 3 / 8 轮配置，也不能让一次请求无边界地反复调工具。
# 常规模式的两轮分别覆盖“拿到候选”和“必要的补充核对”；深度思考最多五轮。
_STANDARD_HARD_MAX_ROUNDS = 2
_DEEP_HARD_MAX_ROUNDS = 5


def budget_for(mode: str) -> int:
    """档位 -> 轮次预算，并对部署配置施加不可绕过的性能上限。"""
    if mode == "max":
        return max(1, min(AGENT_LOOP_DEEP_ROUNDS, _DEEP_HARD_MAX_ROUNDS))
    return max(1, min(AGENT_LOOP_MAX_ROUNDS, _STANDARD_HARD_MAX_ROUNDS))


async def check_iteration(state: WorkflowState) -> WorkflowState:
    """递增轮次并判预算。超预算写 ``transition="finalize"`` 让路由退出到 finalize。

    注意 ``transition`` 必须显式清空（而非只在超预算时赋值）：上一轮
    check_completion 可能写过 ``next_turn``，不清会让 route_after_check_iteration
    读到陈旧值。
    """
    # prepare / ToolRuntime 已经给出可信收敛结论时不应清掉 finalize，再发一轮
    # LLM 去试探已禁止的工具调用。
    if state.transition == "finalize":
        return state
    state.round_no += 1
    state.transition = "finalize" if state.round_no > budget_for(state.mode) else ""
    return state
