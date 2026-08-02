"""能力注册表 —— 可被计划派发的编排能力（capability）的框架层注册中心。

从 ``workflow/graph.py`` 下沉（spec: docs/架构升级方案-借鉴amap治理与编排.md §1 P0-1）：
注册表是框架机制，编排层（graph）是注册方，providers 层工具（如 shopping.deep_search
子管线）按名消费——依赖方向由 providers → workflow 反向，纠正为双方 → framework 单向。

- ``register_capability(name)``：声明式注册节点函数（sync/async 均可）；
- ``get_capability(name)``：按名获取（治理校验 / supervisor 派发用）；
- ``run_capability_pipeline(names, state)``：顺序执行一串能力构成的子管线，
  自动兼容同步/异步节点函数。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

__all__ = ["register_capability", "get_capability", "run_capability_pipeline"]

# 可注册能力表（Phase 4 动态编排）：supervisor 执行器按 ExecutionPlan 派发这些能力。
_CAPABILITIES: dict[str, Callable] = {}


def register_capability(name: str):
    """声明式注册一个可被计划派发的能力（节点函数）。"""

    def _deco(fn):
        _CAPABILITIES[name] = fn
        return fn

    return _deco


def get_capability(name: str) -> Callable | None:
    """按名获取能力函数（治理校验 / 派发用）。"""
    return _CAPABILITIES.get(name)


async def run_capability_pipeline(names: list[str], state: Any) -> Any:
    """顺序执行能力子管线（如 retrieval → reranker → evidence_check → decision）。

    未注册的能力名直接抛 KeyError（fail-fast：管线引用漂移在调用点立刻显形，
    与 check_governance 的静态校验互为兜底）。
    """
    for name in names:
        fn = _CAPABILITIES.get(name)
        if fn is None:
            raise KeyError(f"capability {name!r} 未注册（已注册: {sorted(_CAPABILITIES)}）")
        result = fn(state)
        state = await result if inspect.isawaitable(result) else result
    return state
