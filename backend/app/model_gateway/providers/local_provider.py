"""Local ModelProvider —— embedding / reranker 走本地权重，chat / vision 委托 Qwen。

背景：本地只有 Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B 两个模型，覆盖
``embed`` / ``rerank`` 两个能力；``chat`` / ``chat_stream`` / ``vision`` 无本地权重，
组合一个内嵌的 ``QwenModelProvider`` 继续走 API，从而在不改 gateway 的前提下让整条
购物决策链路照常工作（混合/组合式 Provider）。

契约对齐（关键）：
- ``embed`` 返回 L2 归一化的 1024 维向量，与索引脚本共用同一函数，保证查询/文档同空间。
- ``rerank`` 把本地 reranker 的 log-odds 经 sigmoid 映射到 [0,1] 后返回
  ``{"index", "document", "relevance_score"}``，其中 ``index`` 为输入 ``documents`` 的原始
  下标——``RerankFusion`` 以 ``0.68 + 0.38*relevance_score`` 校准回填，要求分数落在 [0,1]。

依赖懒加载：torch 等重依赖只在实际调用 embed/rerank 时经 ``local_backend`` 载入。
"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import AsyncIterator


def _sigmoid(x: float) -> float:
    # 数值稳定的 sigmoid，把无界 log-odds 压到 (0,1)，保序不改变排序
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class LocalModelProvider:
    """本地 embedding / reranker + Qwen chat/vision 的组合式 Provider。"""

    is_mock = False
    name = "local"
    # 真实本地权重名（供 gateway 可观测日志展示，区别于 config 里的 API 模型名）
    embed_model = "Qwen3-Embedding-0.6B"

    @property
    def rerank_model(self) -> str:
        """当前实际生效的精排模型名（bge / qwen3 由权重与环变量决定）。

        修复：旧硬编码 "Qwen3-Reranker-0.6B" 与实际跑的 bge 不符，导致日志误导。
        """
        from app.model_gateway import local_backend as lb

        return lb.active_reranker_name()

    def __init__(self) -> None:
        self._qwen = None  # 懒实例化，chat/chat_stream/vision 委托

    def _qwen_provider(self):
        if self._qwen is None:
            from app.model_gateway.providers.qwen_provider import QwenModelProvider

            self._qwen = QwenModelProvider()
        return self._qwen

    # ---- 本地能力：embedding ----

    async def embed(self, *, texts: list[str], model: str, dimensions: int,
                    is_query: bool = False) -> list[list[float]]:
        from app.model_gateway import local_backend as lb

        # 非对称编码：查询侧加 Qwen3-Embedding 官方 instruct 前缀，文档侧不加
        return await asyncio.to_thread(lb.embed_texts, texts, 32, is_query)

    # ---- 本地能力：reranker ----

    async def rerank(self, *, query: str, documents: list[str], model: str, top_n: int) -> list[dict]:
        if not documents:
            return []
        from app.model_gateway import local_backend as lb

        logits = await asyncio.to_thread(lb.rerank_logits, query, documents)
        scored = [
            {"index": i, "document": documents[i], "relevance_score": _sigmoid(lg)}
            for i, lg in enumerate(logits)
        ]
        # top_n 截断：默认全量返回（RerankFusion 传 top_n=len(products) 需要全覆盖）
        if top_n and top_n < len(scored):
            scored = sorted(scored, key=lambda x: x["relevance_score"], reverse=True)[:top_n]
        return scored

    # ---- 委托 Qwen API：chat / chat_stream / chat_with_tools / vision ----

    async def chat(self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        return await self._qwen_provider().chat(
            model=model, prompt=prompt, system=system, temperature=temperature, max_tokens=max_tokens
        )

    async def chat_with_tools(self, *, model: str, messages: list[dict], tools: list[dict],
                              system: str = "", temperature: float = 0.1,
                              max_tokens: int = 512) -> dict:
        """委托 Qwen。修复：此前漏委托 → USE_LOCAL_MODELS=true 时 gateway getattr 拿不到
        本方法静默 skipped，function calling / OmniAgent Loop 全部空转。"""
        return await self._qwen_provider().chat_with_tools(
            model=model, messages=messages, tools=tools, system=system,
            temperature=temperature, max_tokens=max_tokens
        )

    async def chat_stream(
        self, *, model: str, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        async for token in self._qwen_provider().chat_stream(
            model=model, prompt=prompt, system=system, temperature=temperature, max_tokens=max_tokens
        ):
            yield token

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
        return await self._qwen_provider().vision(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt=prompt,
            system=system,
            image_path=image_path,
            image_bytes=image_bytes,
            content_type=content_type,
            image_info=image_info,
        )

    async def health_check(self) -> bool:
        # 轻量存活性：模型目录存在即视为可用（不加载权重，避免拖慢健康检查）。
        from app.model_gateway import local_backend as lb

        return os.path.isdir(lb.emb_path()) and os.path.isdir(lb.rr_path())
