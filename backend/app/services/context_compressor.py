"""ContextCompressor — 对话历史增量摘要。

用 qwen-turbo 将多轮对话压缩为 ≤120 字要点摘要。
每次对话后异步触发，不阻塞主链路。

两层上下文架构:
  Layer 1 (热): 最近一轮原文 — FollowUpEngine 直接读取
  Layer 2 (冷): conversation_summary — 历史对话压缩摘要
"""

import json
import logging
import re

from app.framework.context import Tier, TierSelector
from app.prompts.service_prompts import build_compression_user, get_compression_system

_log = logging.getLogger(__name__)

# 摘要块的 token 预算：低于该量的内容走 L0（跳过 LLM、增量拼接省延迟）。
_SUMMARY_TOKEN_BUDGET = 150


class ContextCompressor:
    """增量对话摘要器 — 分级压缩（借鉴 amap context_compaction 的 TierSelector）。

    按 token 用量选择档位：L0 内容很短 → 跳过 LLM 直接增量拼接（省延迟）；
    L1/L2/L3 → 调 qwen-turbo 摘要。
    """

    def __init__(self) -> None:
        self._selector = TierSelector(token_budget=_SUMMARY_TOKEN_BUDGET)

    async def compress(
        self,
        prev_summary: str,
        last_query: str,
        last_answer: str,
        pending_question: str | None = None,
    ) -> dict:
        """执行一轮压缩，返回 {"summary": str, "open_question": str|None}。

        prev_summary: 上次压缩结果（空字符串表示首轮）
        返回的 dict 可直接合并写入 context_snapshot。
        """
        if not last_query:
            return {"summary": prev_summary or "", "open_question": None}

        # 分级：内容很短(L0) → 跳过 LLM，直接增量拼接
        combined = f"{prev_summary}\n{last_query}\n{(last_answer or '')[:200]}"
        if self._selector.select(combined) == Tier.L0:
            return self._fallback(prev_summary, last_query, last_answer, pending_question)

        p_summary = prev_summary or "（首轮对话）"
        p_answer = (last_answer or "")[:200]
        p_pending = pending_question or "无"

        prompt = build_compression_user(
            prev_summary=p_summary,
            last_query=last_query[:200],
            last_answer=p_answer,
            pending_question=p_pending,
        )

        try:
            from app.model_gateway.gateway import get_model_gateway
            gateway = get_model_gateway()
            response = await gateway.chat(
                capability="context_compression",
                prompt=prompt,
                system=get_compression_system(),
            )
            return self._parse(response, prev_summary or "")
        except Exception as e:
            _log.debug(f"ContextCompressor LLM failed, fallback to truncated: {e}")
            return self._fallback(prev_summary, last_query, last_answer, pending_question)

    @staticmethod
    def _parse(response: str, fallback_summary: str) -> dict:
        if not response:
            return {"summary": fallback_summary, "open_question": None}
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", response)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    return {"summary": fallback_summary, "open_question": None}
            else:
                return {"summary": fallback_summary, "open_question": None}
        return {
            "summary": str(data.get("summary", fallback_summary))[:150],
            "open_question": data.get("open_question") or None,
        }

    @staticmethod
    def _fallback(
        prev_summary: str,
        last_query: str,
        last_answer: str,
        pending_question: str | None,
    ) -> dict:
        """LLM 不可用时的简单拼接降级。"""
        new_line = last_query[:80]
        if prev_summary and new_line not in prev_summary:
            summary = prev_summary + " | " + new_line
        elif not prev_summary:
            summary = new_line
        else:
            summary = prev_summary
        return {
            "summary": summary[:150],
            "open_question": pending_question or None,
        }


# ---- Singleton ----

_compressor: ContextCompressor | None = None


def get_context_compressor() -> ContextCompressor:
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor()
    return _compressor
