"""ModelProvider 抽象（借鉴 amap 多模型网关 SDK 的 BaseProvider）。

把「MOCK 还是真实模型」的选择从 gateway 每个方法内联的 ``if MOCK_MODE`` 收敛为
Provider 多态。gateway 只保留能力路由 + 可观测 trace/audit，原始调用委托给 Provider。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    """统一模型 Provider 契约。"""

    is_mock: bool

    async def chat(self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str: ...

    def chat_stream(
        self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]: ...

    async def embed(self, *, texts: list[str], model: str, dimensions: int,
                    is_query: bool = False) -> list[list[float]]: ...

    async def vision(
        self,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        prompt: str,
        system: str,
        image_path: str | None,
        image_bytes: bytes | None,
        content_type: str,
        image_info: str,
    ) -> str: ...

    async def rerank(self, *, query: str, documents: list[str], model: str, top_n: int) -> list[dict]: ...

    async def health_check(self) -> bool: ...
