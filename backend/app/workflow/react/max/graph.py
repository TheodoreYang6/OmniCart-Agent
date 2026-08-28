"""max 图装配 —— 与 standard 拓扑同构，只换两个节点实现。

对齐 amap ``max/max.py``：复用 standard 的装配函数与共享节点，只替换
``invoke_llm`` / ``check_completion``，并改用 ``route_after_execute_tools_max``。

这三处就是两档的全部差异。任何在此之外的分歧都会让"同构"失真，
``tests/unit/test_react_graph.py`` 里的同构断言就是为此设的护栏。
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import StateGraph

from app.workflow.react.max.completion import check_completion
from app.workflow.react.max.reasoning import invoke_llm
from app.workflow.react.routing import route_after_execute_tools_max
from app.workflow.react.standard.graph import STANDARD_NODES, build

__all__ = ["MAX_NODES", "get_graph"]

MAX_NODES: dict[str, Callable] = {
    **STANDARD_NODES,
    "invoke_llm": invoke_llm,
    "check_completion": check_completion,
}


def get_graph() -> StateGraph:
    """max 档未编译图。编译与缓存由 ``react/__init__.py`` 统一负责。"""
    return build(MAX_NODES, route_after_tools=route_after_execute_tools_max)
