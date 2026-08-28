"""ReAct 图（standard / max 两档同构，移植 amap chat_agent 的编排结构）。

档位调度与编译缓存收在本模块；两档各自的构图在 ``standard/graph.py`` 与
``max/graph.py``，节点实现在各自的 ``reasoning.py`` / ``completion.py``，
共享节点在 ``nodes/``。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型标注用，避免运行时提前加载 langgraph
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

__all__ = ["get_react_workflow", "run_config"]

_MODES = ("standard", "max")
_compiled: dict[str, object] = {}


def _graph_factory(mode: str) -> Callable:
    """按档位取构图函数。延迟 import，避免加载未用到的那一档。"""
    if mode == "max":
        from app.workflow.react.max.graph import get_graph
    else:
        from app.workflow.react.standard.graph import get_graph
    return get_graph


def run_config(mode: str = "standard") -> dict:
    """invoke/astream 用的 config，把 recursion_limit 与轮次预算绑定。

    LangGraph 不指定时默认 25 个 superstep。而 ``check_iteration`` 才是本图唯一应该
    生效的终止条件 —— 若框架的限制先触发，抛的是 GraphRecursionError，在 SSE 层被
    当成普通异常降级回 pipeline，报错信息指向框架而不是预算，极难定位。

    每轮的 superstep 消耗按**最坏情况**算四步：
    ``check_iteration -> invoke_llm -> execute_tools -> check_completion``。
    四步只在 max 档持有活跃计划时出现（``route_after_execute_tools_max`` 会先过
    check_completion 推进 todo），standard 档是三步；但预算守卫的正确性不能依赖
    “当前跑的是哪一档”，所以两档统一按四步上界算。

    外加 6 步余量：prepare + 收尾的 check_iteration/check_completion/finalize，
    再留两步缓冲（将来加 recover 节点不致于立刻越界）。

    历史教训：此处曾按三步算（``budget * 3 + 4``），max 档拿到 5 项 todo 的真实计划时
    必抛 GraphRecursionError —— 而多步任务正是 max 档存在的意义。
    """
    from app.workflow.react.nodes.guard import budget_for

    return {"recursion_limit": budget_for(mode) * 4 + 6}


def get_react_workflow(mode: str = "standard") -> CompiledStateGraph:
    """按档位取已编译图（进程内缓存，编译一次）。

    未知档位回退 standard 而不是抛错：档位来自请求参数，非法值不该 500。
    """
    if mode not in _MODES:
        logger.warning("unknown react mode %r, falling back to standard", mode)
        mode = "standard"
    if mode not in _compiled:
        _compiled[mode] = _graph_factory(mode)().compile()
    return _compiled[mode]
