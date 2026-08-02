"""LLM 关键词改写器 —— 实现 framework 的 QueryRewriter 协议。

平移自 ``retrieval_agent._text_channel`` 的 rich/slow 双路径 +
``_llm_extract_keywords``（含 30min Redis 缓存）：

- rich 路径：Router 已产出品类/must_tags 等结构化字段 → 直接拼接检索串，跳过 LLM（省 ~600ms）。
- slow 路径：Router 信息不足（泛查询）→ 调 LLM 提取关键词（带会话上下文做指代消解）。
"""

from __future__ import annotations

import logging

from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_REWRITE
from app.framework.registry import component
from app.framework.retrieval.types import RetrievalQuery

logger = logging.getLogger(__name__)


@component(kind="query_rewriter", name="llm_keyword", priority=10)
class LLMKeywordRewriter:
    """基于 Qwen 的检索关键词改写器。"""

    name = "llm_keyword"

    async def rewrite(self, query: RetrievalQuery) -> str:
        # rich 路径：有品类或 must_tags 即视为信息充足
        router_rich = bool(query.category or (query.must_tags and len(query.must_tags) >= 1))
        if router_rich:
            parts = [query.query]
            if query.category:
                parts.append(query.category)
            if query.sub_category:
                parts.append(query.sub_category)
            if query.must_tags:
                parts.append(" ".join(query.must_tags))
            if query.spec_keywords:
                parts.append(" ".join(query.spec_keywords))
            return " ".join(parts)

        # slow 路径：LLM 关键词提取（带会话上下文）
        return await self._llm_extract_keywords(query.query, (query.context or "")[:200])

    async def _llm_extract_keywords(self, user_query: str, context: str = "") -> str:
        """用 Qwen 从口语查询提取搜索关键词，失败退回原 query，结果缓存 30 分钟。"""
        cache_key = make_key("rewrite", user_query, context[:80])

        async def _do_rewrite() -> str:
            from app.prompts.service_prompts import build_keyword_extract_prompt

            prompt = build_keyword_extract_prompt(user_query, context)
            try:
                from app.model_gateway.gateway import get_model_gateway

                gateway = get_model_gateway()
                result = await gateway.chat("chat_generation", prompt)
                keywords = result.strip()
                if keywords and len(keywords) >= 2:
                    logger.info("LLM keywords: %r -> %r", user_query, keywords)
                    return keywords
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM keyword extraction failed: %s", exc)
            return user_query

        return await cached(cache_key, REDIS_CACHE_TTL_REWRITE, _do_rewrite)
