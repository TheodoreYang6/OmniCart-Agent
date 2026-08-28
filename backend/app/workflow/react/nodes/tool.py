"""共享节点 execute_tools —— 同轮多工具执行。

``ToolRegistry.invoke`` 已经是"统一执行入口：权限 -> 弹性超时 -> 追踪 -> 黑板"。
本节点把调用交给受控运行时：策略校验、隔离执行、结果归并与收敛判定都不散落在工具里。
"""

from __future__ import annotations

from app.schemas.workflow import WorkflowState
from app.workflow.react.runtime import ToolRuntime

__all__ = ["execute_tools"]


async def execute_tools(state: WorkflowState) -> WorkflowState:
    """执行 ``state.pending_tool_calls``，结果以 role=tool 回填进 messages。

    只有 Router 明确为独立目标的 search 会并行，且使用隔离快照并按调用顺序归并；
    所有写操作与共享主体分析都串行。失败会作为受控工具结果回填，不覆盖已有成功结果。
    """
    calls = state.pending_tool_calls
    if not calls:
        return state
    return await ToolRuntime.execute_batch(state, calls)
