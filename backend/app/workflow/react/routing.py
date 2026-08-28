"""ReAct 图的共享路由函数（standard / max 两档复用）。

对齐 amap `standard/standard.py` 的路由设计：**路由是纯函数，只读 state 的决策
字段，不含任何业务逻辑**。决策由节点写入 ``transition`` / ``response_route``，
路由只负责把字段翻译成边名。这样"下一步去哪"永远能从 state 单独复现，
调试时不必重放节点副作用。

两档差异只有 ``route_after_execute_tools_*`` 一处（对齐 amap 的
``route_after_execute_tools_standard`` / ``_pro``）。
"""

from __future__ import annotations

from app.schemas.workflow import WorkflowState

__all__ = [
    "route_after_check_completion",
    "route_after_check_iteration",
    "route_after_execute_tools_max",
    "route_after_execute_tools_standard",
    "route_after_invoke_llm",
]


def route_after_check_iteration(state: WorkflowState) -> str:
    """预算耗尽或已判定收尾 -> 退出；否则继续下一轮推理。"""
    return "exit" if state.transition == "finalize" else "continue"


def route_after_invoke_llm(state: WorkflowState) -> str:
    """LLM 要调工具 -> execute_tools；否则进收敛判定。"""
    return "execute_tools" if state.response_route == "tool_use" else "check_completion"


def route_after_execute_tools_standard(state: WorkflowState) -> str:
    """standard：工具执行完回预算守卫，进入下一轮 ReAct。

    ``transition == "finalize"`` 时先过 check_completion 而不是直接 finalize——
    收敛判定要有机会把 answer_draft 落定。
    """
    return "check_completion" if state.transition == "finalize" else "check_iteration"


def route_after_execute_tools_max(state: WorkflowState) -> str:
    """max：todo 推进中时先过收敛判定（更新 todo 完成度）再决定是否回环。

    这是与 standard 的实质差异点，对齐 amap ``route_after_execute_tools_pro``
    的 ``_has_active_in_progress_plan`` 判断：计划驱动的档位必须每轮回看
    todo 状态，否则会在计划已完成时还继续空转。
    """
    if state.transition == "finalize":
        return "check_completion"
    if state.deliberation.is_active() and state.deliberation.plan_status == "in_progress":
        return "check_completion"
    return "check_iteration"


def route_after_check_completion(state: WorkflowState) -> str:
    """需要再来一轮模型交互 -> 回预算守卫；否则收尾。"""
    return "check_iteration" if state.transition == "next_turn" else "exit"
