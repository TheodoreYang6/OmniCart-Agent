"""轻量组件注册表 + 声明式装饰器。

借鉴 amap-ai-agent ``libs/agent_graph/app/providers.py`` 的 ``ProviderRegistry``
思想（``@<kind>_component`` 装饰器声明式装配 + 统一注册中心），但**剔除其
``pkgutil.walk_packages`` 运行时全包扫描**——那是为 bazel/monorepo 多命名空间
服务的重实现。OmniCart 是单体，采用更简单可控的**显式 ``builtin()`` 清单**装配
（对齐 amap ``SourceRegistry.default(provider_builtin=...)`` / ``MemoryBank.default
(builtin_providers=...)`` 的清单式发现）。

用法::

    # 1) 声明式打标（可选，主要用于治理校验 + 元数据）
    @component(kind="recall_source", name="semantic", priority=10)
    class SemanticRecallSource: ...

    # 2) 显式清单装配
    registry = ComponentRegistry("recall_source")
    for cls in builtin():          # providers 侧维护的 builtin() 清单
        registry.register(cls())

    src = registry.get("semantic")
    for s in registry.get_all():   # 按 priority 升序
        ...
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, TypeVar

__all__ = [
    "component",
    "component_kind",
    "component_name",
    "component_priority",
    "ComponentRegistry",
    "DuplicateComponentError",
    "ComponentNotFoundError",
]

_T = TypeVar("_T")

# 装饰器写入类对象的元数据属性名（避免与业务字段冲突，用双下划线私有约定）。
_KIND_ATTR = "__component_kind__"
_NAME_ATTR = "__component_name__"
_PRIORITY_ATTR = "__component_priority__"


class DuplicateComponentError(ValueError):
    """同一 registry 内注册了重名组件。"""


class ComponentNotFoundError(LookupError):
    """按名称查找组件失败。"""


def component(
    *,
    kind: str,
    name: str | None = None,
    priority: int = 100,
) -> Callable[[type[_T]], type[_T]]:
    """声明式组件装饰器。

    仅在类对象上挂载元数据（kind / name / priority），**不做任何全局副作用注册**，
    因此 import 顺序无关、可测试。真正的装配由各子系统用 ``builtin()`` 清单 +
    :class:`ComponentRegistry` 显式完成。

    Args:
        kind: 组件类别，如 ``recall_source`` / ``memory_provider`` / ``context_provider``
            / ``agent``。
        name: 组件唯一名（同 kind 内唯一）。缺省用类名转 snake_case。
        priority: 排序优先级，越小越靠前（影响结果拼接/召回顺序）。
    """

    def _decorator(cls: type[_T]) -> type[_T]:
        setattr(cls, _KIND_ATTR, kind)
        setattr(cls, _NAME_ATTR, name or _snake_case(cls.__name__))
        setattr(cls, _PRIORITY_ATTR, priority)
        return cls

    return _decorator


def component_kind(obj: Any) -> str | None:
    """读取实例/类上的组件 kind 元数据。"""
    return getattr(obj, _KIND_ATTR, None)


def component_name(obj: Any) -> str | None:
    """读取组件 name：优先实例属性 ``name``，其次装饰器元数据。"""
    inst_name = getattr(obj, "name", None)
    if isinstance(inst_name, str) and inst_name:
        return inst_name
    meta = getattr(obj, _NAME_ATTR, None)
    return meta if isinstance(meta, str) and meta else None


def component_priority(obj: Any) -> int:
    """读取组件 priority：优先实例属性 ``priority``，其次装饰器元数据，默认 100。"""
    inst = getattr(obj, "priority", None)
    if isinstance(inst, int):
        return inst
    meta = getattr(obj, _PRIORITY_ATTR, None)
    return meta if isinstance(meta, int) else 100


class ComponentRegistry:
    """按名称索引的组件注册中心（单 kind，实例存储）。

    存储的是**组件实例**（RecallSource / Provider / Agent），支持：注册、去重、
    按名查询、按 priority 排序遍历。刻意保持简单——它是所有子系统注册表的通用底座，
    RAG 的 SourceRegistry、Memory 的 ProviderManager 均可直接复用或包装它。
    """

    def __init__(self, kind: str = "") -> None:
        self._kind = kind
        self._items: dict[str, Any] = {}

    @property
    def kind(self) -> str:
        return self._kind

    def register(self, obj: Any, *, name: str | None = None, override: bool = False) -> None:
        """注册一个组件实例。

        Args:
            obj: 组件实例（需可通过实例 ``name`` 属性或装饰器元数据解析出名称）。
            name: 显式名称，覆盖自动解析。
            override: 允许同名覆盖（便于测试 mock / 业务自定义胜出）。
        """
        resolved = name or component_name(obj)
        if not resolved:
            raise ValueError(
                f"component of type {type(obj).__name__!r} has no resolvable name; "
                f"declare a 'name' attribute or use @component(name=...)"
            )
        if resolved in self._items and not override:
            raise DuplicateComponentError(f"component {resolved!r} already registered in kind={self._kind!r}")
        self._items[resolved] = obj

    def register_all(self, objs: list[Any], *, override: bool = False) -> None:
        """批量注册。"""
        for obj in objs:
            self.register(obj, override=override)

    def unregister(self, name: str) -> None:
        if name not in self._items:
            raise ComponentNotFoundError(name)
        del self._items[name]

    def get(self, name: str) -> Any:
        if name not in self._items:
            raise ComponentNotFoundError(f"component {name!r} not found in kind={self._kind!r}")
        return self._items[name]

    def get_optional(self, name: str) -> Any | None:
        return self._items.get(name)

    def get_all(self) -> list[Any]:
        """按 priority 升序返回全部组件实例。"""
        return sorted(self._items.values(), key=component_priority)

    def names(self) -> list[str]:
        return list(self._items.keys())

    def reset(self) -> None:
        self._items.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.get_all())


def _snake_case(name: str) -> str:
    """PascalCase / camelCase 转 snake_case。"""
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
