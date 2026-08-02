"""召回源注册中心（借鉴 amap ``libs/knowledge_base/registry.py`` 的 SourceRegistry）。

在通用 :class:`app.framework.registry.ComponentRegistry` 之上做 RAG 语义封装：
- 只接受 :class:`RecallSource` 实例；
- ``default(builtin=...)`` 用显式清单装配（对齐 amap ``SourceRegistry.default
  (provider_builtin=...)``），清单由 ``app.providers.recall.builtin()`` 维护；
- 支持按 ``stage`` 过滤，供编排器分阶段调度。
"""

from __future__ import annotations

from collections.abc import Callable

from app.framework.registry import ComponentRegistry
from app.framework.retrieval.source import RecallSource


class SourceRegistry:
    """召回源注册中心。"""

    def __init__(self) -> None:
        self._registry = ComponentRegistry(kind="recall_source")

    @classmethod
    def default(
        cls,
        *,
        builtin: Callable[[], list[RecallSource]],
        include: set[str] | None = None,
    ) -> SourceRegistry:
        """从 ``builtin()`` 清单装配注册中心。

        Args:
            builtin: 返回 RecallSource 实例列表的工厂（``providers.recall.builtin``）。
            include: 可选白名单（按 source.name）。``None`` 注册全部。
        """
        registry = cls()
        for source in builtin():
            if include is not None and source.name not in include:
                continue
            registry.register(source)
        return registry

    def register(self, source: RecallSource) -> None:
        self._registry.register(source, name=source.name)

    def get(self, name: str) -> RecallSource:
        return self._registry.get(name)

    def get_all(self) -> list[RecallSource]:
        """按 priority 升序返回全部召回源。"""
        return list(self._registry.get_all())

    def by_stage(self, stage: str) -> list[RecallSource]:
        """返回指定阶段的召回源（按 priority 升序）。"""
        return [s for s in self.get_all() if getattr(s, "stage", "") == stage]

    def names(self) -> list[str]:
        return self._registry.names()

    def __len__(self) -> int:
        return len(self._registry)
