"""standard 图装配 —— 6 节点纯 ReAct，并持有两档共享的 ``build()``。

对齐 amap ``standard/standard.py``：该文件同时是 standard 图的构图入口和
共享装配/路由的宿主（amap 的 ``max/max.py`` 也从 standard.py 导入路由函数）。

拓扑（amap 8 节点去掉 build_prompt 合入 prepare、暂不做 recover）::

    entry: prepare
    prepare          -> check_iteration
    check_iteration  -[continue]-> invoke_llm   -[exit]-> finalize
    invoke_llm       -[tool_use]-> execute_tools -[else]-> check_completion
    execute_tools    -> check_iteration | check_completion
    check_completion -> check_iteration | finalize
    finalize         -> END
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, StateGraph

from app.schemas.workflow import WorkflowState
from app.workflow.react.nodes.finalize import finalize
from app.workflow.react.nodes.guard import check_iteration
from app.workflow.react.nodes.prepare import prepare
from app.workflow.react.nodes.tool import execute_tools
from app.workflow.react.routing import (
    route_after_check_completion,
    route_after_check_iteration,
    route_after_execute_tools_standard,
    route_after_invoke_llm,
)
from app.workflow.react.standard.completion import check_completion
from app.workflow.react.standard.reasoning import invoke_llm

__all__ = ["STANDARD_NODES", "build", "get_graph"]

# 节点映射即"档位差异"的唯一载体。amap 用同名不同模块的节点类表达同一件事；
# 本移植是单体服务，用 dict 映射更直接，不必为同构而造同名类。
STANDARD_NODES: dict[str, Callable] = {
    "prepare": prepare,
    "check_iteration": check_iteration,
    "invoke_llm": invoke_llm,
    "execute_tools": execute_tools,
    "check_completion": check_completion,
    "finalize": finalize,
}


def build(nodes: dict[str, Callable], *, route_after_tools: Callable) -> StateGraph:
    """两档共享的装配函数 —— 走同一个函数才能保证拓扑不漂移。

    节点用 ``_traced`` 包裹复用现有观测套壳（timing 兜底 + 异常记 trace 后 re-raise）。
    局部 import 是刻意的：``workflow.graph`` 体量大且在 import 时注册能力管道，
    放模块顶层会让 react 包的 import 代价和顺序都变得敏感。
    """
    from app.workflow.graph import _traced

    graph = StateGraph(WorkflowState)
    for name, fn in nodes.items():
        graph.add_node(name, _traced(name, fn))

    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "check_iteration")
    graph.add_conditional_edges(
        "check_iteration", route_after_check_iteration,
        {"continue": "invoke_llm", "exit": "finalize"},
    )
    graph.add_conditional_edges(
        "invoke_llm", route_after_invoke_llm,
        {"execute_tools": "execute_tools", "check_completion": "check_completion"},
    )
    graph.add_conditional_edges(
        "execute_tools", route_after_tools,
        {"check_iteration": "check_iteration", "check_completion": "check_completion"},
    )
    graph.add_conditional_edges(
        "check_completion", route_after_check_completion,
        {"check_iteration": "check_iteration", "exit": "finalize"},
    )
    graph.add_edge("finalize", END)
    return graph


def get_graph() -> StateGraph:
    """standard 档未编译图。编译与缓存由 ``react/__init__.py`` 统一负责。"""
    return build(STANDARD_NODES, route_after_tools=route_after_execute_tools_standard)
