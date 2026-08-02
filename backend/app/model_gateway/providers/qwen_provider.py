"""Qwen ModelProvider —— 包裹既有 QwenChat/QwenEmbedding/QwenVision/QwenReranker。

弹性默认值刻意保持「与现网关一致」：``timeout_s=None`` + ``retry_attempts=1``（不额外
超时、不额外重试，沿用 httpx 客户端自带超时），仅叠加 CircuitBreaker——连续失败达阈值后
在冷却期快速失败，避免故障期雪崩。正常运行时熔断器从不打开，行为与重构前一致。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from app.model_gateway.resilience import CircuitBreaker, call_with_timeout, retry_async

T = TypeVar("T")


class QwenModelProvider:
    """通义千问真实模型 Provider。"""

    is_mock = False

    def __init__(self, *, timeout_s: float | None = None, retry_attempts: int = 1) -> None:
        self._timeout = timeout_s
        self._attempts = retry_attempts
        self._breaker = CircuitBreaker(fail_threshold=5, reset_timeout_s=30.0)

    async def _guard(self, fn: Callable[[], Awaitable[T]]) -> T:
        async def _timed() -> T:
            return await call_with_timeout(fn(), self._timeout)

        return await self._breaker.call(lambda: retry_async(_timed, attempts=self._attempts))

    async def chat(self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        from app.model_gateway.qwen_chat import QwenChat

        chat = QwenChat(model=model, temperature=temperature, max_tokens=max_tokens)
        return await self._guard(lambda: chat.generate(prompt, system))

    async def chat_stream(
        self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        # 流式不做重试/整体超时（会破坏增量语义），直接透传底层流。
        from app.model_gateway.qwen_chat import QwenChat

        chat = QwenChat(model=model, temperature=temperature, max_tokens=max_tokens)
        async for token in chat.generate_stream(prompt, system):
            yield token

    async def chat_with_tools(self, *, model: str, messages: list[dict], tools: list[dict],
                              system: str, temperature: float, max_tokens: int) -> dict:
        from app.model_gateway.qwen_chat import QwenChat

        chat = QwenChat(model=model, temperature=temperature, max_tokens=max_tokens)
        return await self._guard(lambda: chat.generate_with_tools(messages, tools, system))

    async def embed(self, *, texts: list[str], model: str, dimensions: int,
                    is_query: bool = False) -> list[list[float]]:
        from app.model_gateway.qwen_embedding import QwenEmbedding

        emb = QwenEmbedding(model=model, dimensions=dimensions)
        return await self._guard(lambda: emb.embed(texts, is_query=is_query))

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
    ) -> str:
        from app.model_gateway.qwen_vision import QwenVision

        vis = QwenVision(model=model, temperature=temperature, max_tokens=max_tokens)
        if image_bytes:
            return await self._guard(lambda: vis.analyze_bytes(image_bytes, content_type, prompt, system))
        return await self._guard(lambda: vis.analyze(image_path or "", prompt, system))

    async def rerank(self, *, query: str, documents: list[str], model: str, top_n: int) -> list[dict]:
        from app.model_gateway.qwen_reranker import QwenReranker

        ranker = QwenReranker(model=model)
        return await self._guard(lambda: ranker.rerank(query, documents, top_n or 10))

    async def health_check(self) -> bool:
        # 轻量存活性：有 API Key 即视为可用（不发真实请求以免产生费用）。
        from app.core.config import QWEN_API_KEY

        return bool(QWEN_API_KEY)
