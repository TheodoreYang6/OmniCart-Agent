"""max 档 check_completion —— todo 完成度驱动收敛。

对齐 amap ``max/nodes/completion.py``。
"""

from __future__ import annotations

from app.schemas.workflow import WorkflowState

__all__ = ["check_completion"]


def _mark_progress(state: WorkflowState) -> None:
    """把第一个未完成的 todo 标记完成。

    用"每完成一轮工具调用就推进一项"的近似策略，而不是让 LLM 显式回报完成了哪一项
    —— 后者要额外一次结构化输出，成本翻倍且 LLM 常报不准。近似策略的代价是 todo 进度
    只是"大致对齐"，但它只用于给 LLM 提示和给用户外显，不参与正确性判定：真正的终止
    条件仍是 check_iteration 的轮次预算。
    """
    for todo in state.deliberation.todos:
        if not todo.get("done"):
            todo["done"] = True
            return


async def check_completion(state: WorkflowState) -> WorkflowState:
    """todo 逐项推进，全部完成后再给一轮让 LLM 收口。

    ``transition`` 已是 finalize（预算耗尽或防循环）时不覆盖。
    """
    if state.transition == "finalize":
        return state

    plan = state.deliberation
    if plan.is_active() and plan.plan_status == "in_progress":
        # 刚执行过一轮工具 -> 推进一项
        if state.response_route == "tool_use":
            _mark_progress(state)
        if all(t.get("done") for t in plan.todos):
            # 计划跑完不直接 finalize，而是再给一轮：此刻 LLM 手上有全部工具记录，
            # 是产结论最好的时机（progress_hint 会提示"所有项完成后直接给出最终回答"）。
            # 直接 finalize 会让 answer_draft 为空，只能退回 ResponseAgent 模板统稿。
            plan.plan_status = "done"
        state.transition = "next_turn"
        return state

    # 计划已完成，或本就无计划（规划失败 / 单步请求）-> 同 standard 语义：
    # 进到这里说明 LLM 不再调工具（或已被预算/防循环判停），本身就是终止信号。
    state.transition = "finalize"
    return state
