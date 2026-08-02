"""查询改写协议（借鉴 amap ``libs/knowledge_base/queryrewrite.py``）。

把现 ``retrieval_agent._llm_extract_keywords`` 从检索逻辑里抽出，成为管线中一个
独立、可插拔的阶段。框架层只定义协议 + 无操作默认实现；真正的 LLM 改写
（含 30min Redis 缓存、rich/slow 双路径）作为业务实现放在 ``app.providers.recall``。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.framework.retrieval.types import RetrievalQuery


@runtime_checkable
class QueryRewriter(Protocol):
    """查询改写器协议。

    返回**用于向量检索的最终查询串**（编排器会写入 ``query.rewritten_query``）。
    """

    async def rewrite(self, query: RetrievalQuery) -> str: ...


class NoopQueryRewriter:
    """无操作改写器 —— 直接返回原始 query。"""

    async def rewrite(self, query: RetrievalQuery) -> str:
        return query.query
