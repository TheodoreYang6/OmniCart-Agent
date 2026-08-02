"""Context 框架层核心契约（借鉴 amap ``libs/context_store``）。

- :class:`ContextProvider`：一路上下文来源（用户画像/时间/追问等），ContextManager
  并行采集的单元。``fetch`` 产出 :class:`ContextSlice`。
- :class:`ContextSlice` / :class:`ContextBundle`：单片 / 融合后的上下文包。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextTrigger:
    """上下文采集触发信号。"""

    query: str = ""
    user_id: str = ""
    conversation_id: str = ""
    category: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSlice:
    """单个 Provider 产出的上下文切片。"""

    provider_name: str
    content: dict[str, Any] = field(default_factory=dict)
    formatted_text: str = ""
    priority: int = 100
    token_estimate: int = 0


@dataclass
class ContextBundle:
    """融合 + 裁剪后的上下文包。"""

    slices: list[ContextSlice] = field(default_factory=list)
    total_tokens: int = 0
    dropped: list[str] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def text(self) -> str:
        """按 priority 升序拼接所有切片的 formatted_text。"""
        parts = [s.formatted_text for s in self.slices if s.formatted_text]
        return "\n".join(parts)


class ContextProvider(ABC):
    """上下文 Provider 抽象基类。"""

    name: str = ""
    priority: int = 100
    max_latency_ms: int = 2000

    def should_activate(self, trigger: ContextTrigger) -> bool:
        return True

    @abstractmethod
    async def fetch(self, trigger: ContextTrigger) -> ContextSlice:
        """采集上下文切片。"""
        ...

    def format_content(self, slice_: ContextSlice) -> str:
        """把 content 格式化为可注入 prompt 的文本。默认返回已有 formatted_text。"""
        return slice_.formatted_text
