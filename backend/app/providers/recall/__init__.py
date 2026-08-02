"""内置召回源清单（对齐 amap ``commons/knowledge_providers`` 的 ``builtin()``）。

``RetrievalAgent`` 用 ``SourceRegistry.default(builtin=lambda: builtin(repo))`` 显式装配。
新增/替换召回源只需改动本清单，无需触碰框架层与编排器。
"""

from __future__ import annotations

from app.framework.retrieval.source import RecallSource
from app.providers.recall.enrich_sources import PolicyRecallSource, ReviewRecallSource
from app.providers.recall.keyword_rewriter import LLMKeywordRewriter
from app.providers.recall.keyword_source import KeywordRecallSource
from app.providers.recall.semantic_source import SemanticRecallSource
from app.providers.recall.supplementary_source import SupplementaryRecallSource

__all__ = [
    "SemanticRecallSource",
    "KeywordRecallSource",
    "SupplementaryRecallSource",
    "ReviewRecallSource",
    "PolicyRecallSource",
    "LLMKeywordRewriter",
    "builtin",
    "default_rewriter",
]


def builtin(repo=None) -> list[RecallSource]:
    """返回全部内置召回源实例（供 SourceRegistry 装配）。

    顺序即 priority 升序：semantic(10, recall/向量) → keyword(20, recall/词面)
    → supplementary(30, fallback) → review(40, enrich) → policy(50, enrich)。
    semantic + keyword 两路 recall 由 RRFFusion 融合。
    """
    return [
        SemanticRecallSource(repo),
        KeywordRecallSource(repo),
        SupplementaryRecallSource(),
        ReviewRecallSource(),
        PolicyRecallSource(),
    ]


def default_rewriter() -> LLMKeywordRewriter:
    """默认查询改写器。"""
    return LLMKeywordRewriter()
