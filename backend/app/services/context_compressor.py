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

_log = logging.getLogger(__name__)

# 压缩 prompt — 低温，结构化输出
_COMPRESSION_SYSTEM = (
    "你是购物对话摘要器。将对话历史压缩为 ≤120 字的要点摘要。\n\n"
    "规则：\n"
    "1. 只保留事实：用户需求、约束、偏好、已推荐商品、风险提示、态度反馈\n"
    "2. 不编造、不推测、不评价用户的选择\n"
    "3. 如果用户表达了对推荐的态度（喜欢/不喜欢/太贵/不合适），必须记录\n"
    "4. 如果有豆仔提出但用户尚未回答的问题，记录为 open_question\n"
    "5. 输出 JSON 格式，不要其他内容\n\n"
    '格式: {"summary": "摘要", "open_question": "未回答问题"|null}'
)

_COMPRESSION_USER = (
    "历史摘要: {prev_summary}\n"
    "本轮用户: {last_query}\n"
    "豆仔回复: {last_answer}\n"
    "待回答: {pending_question}\n\n"
    "请更新摘要 JSON:"
)


class ContextCompressor:
    """增量对话摘要器 — 每轮调用 qwen-turbo 更新 summary。"""

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

        p_summary = prev_summary or "（首轮对话）"
        p_answer = (last_answer or "")[:200]
        p_pending = pending_question or "无"

        prompt = _COMPRESSION_USER.format(
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
                system=_COMPRESSION_SYSTEM,
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
