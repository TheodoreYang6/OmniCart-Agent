"""Agent 生命周期管理器（借鉴 amap ``libs/agent_graph/agents`` 的 AgentManager）。

在通用 :class:`ComponentRegistry` 之上做 Agent 语义封装：按名注册/获取 + 批量
``init_all`` / ``shutdown_all``（Agent 若实现了可选的 ``init`` / ``shutdown`` 协程则调用）。
用于把 graph.py 里硬编码的模块级单例替换为「注册表装配 + 按名获取」。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.framework.registry import ComponentRegistry

logger = logging.getLogger(__name__)


class AgentManager:
    """Agent 注册表 + 生命周期管理。"""

    def __init__(self) -> None:
        self._registry = ComponentRegistry(kind="agent")

    @classmethod
    def default(cls, *, builtin: Callable[[], dict[str, Any]]) -> AgentManager:
        """从 ``builtin()`` 清单（{name: agent}）装配。"""
        mgr = cls()
        for name, agent in builtin().items():
            mgr.register(name, agent)
        return mgr

    def register(self, name: str, agent: Any, *, override: bool = False) -> None:
        self._registry.register(agent, name=name, override=override)

    def get(self, name: str) -> Any:
        return self._registry.get(name)

    def names(self) -> list[str]:
        return self._registry.names()

    async def init_all(self) -> None:
        """调用所有 Agent 的可选 ``init`` 协程。"""
        for agent in self._registry.get_all():
            init = getattr(agent, "init", None)
            if callable(init):
                try:
                    await init()
                except Exception:  # noqa: BLE001
                    logger.exception("agent init failed: %s", type(agent).__name__)

    async def shutdown_all(self) -> None:
        """调用所有 Agent 的可选 ``shutdown`` 协程。"""
        for agent in self._registry.get_all():
            shutdown = getattr(agent, "shutdown", None)
            if callable(shutdown):
                try:
                    await shutdown()
                except Exception:  # noqa: BLE001
                    logger.exception("agent shutdown failed: %s", type(agent).__name__)
