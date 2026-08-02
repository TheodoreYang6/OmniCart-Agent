"""证据内容抽取 + 置信度换算 —— 从 ``retrieval_agent`` 平移，供召回源复用。

保持与原实现逐字节一致，确保重构后 ``evidence_list`` 内容不变。
"""

from __future__ import annotations

import math
from typing import Any


def text_confidence(raw_score: float) -> float:
    """把检索原始分换算为证据置信度（复现 ``_text_channel`` 的计算）。

    - 余弦/校准分 (<=1.0)：直接四舍五入。
    - 关键词命中数 (>1)：对数映射到 [0.35, 1.0]。
    """
    if raw_score <= 1.0:
        return round(raw_score, 4)
    return round(min(1.0, 0.35 + 0.25 * math.log10(max(1, raw_score))), 4)


def evidence_content_for_id(eid: str, rag_knowledge: Any, raw_score: float) -> str:
    """根据 evidence_id 前缀从 rag_knowledge 提取可读正文。

    直接平移自 ``retrieval_agent._evidence_content_for_id``（行为不变）。
    """
    rk = rag_knowledge or {}
    if isinstance(rk, dict):
        # E-MKT-{pid}-{i} -> 营销描述
        if eid.startswith("E-MKT-"):
            mkt = rk.get("marketing_description", "")
            if mkt:
                return f"[营销] {str(mkt)[:150]}"
        # POL-{pid}-{i} -> FAQ
        elif eid.startswith("POL-"):
            idx = 0
            parts = eid.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    idx = int(parts[1])
                except ValueError:
                    pass
            faqs = rk.get("official_faq", [])
            if isinstance(faqs, list) and idx < len(faqs):
                faq = faqs[idx]
                if isinstance(faq, dict):
                    q = faq.get("question", "")
                    a = faq.get("answer", "")
                    if q:
                        return f"[FAQ] Q: {str(q)[:80]} A: {str(a)[:100]}"
        # R-{pid}-{i} -> 用户评论
        elif eid.startswith("R-"):
            idx = 0
            parts = eid.rsplit("-", 1)
            if len(parts) == 2:
                try:
                    idx = int(parts[1])
                except ValueError:
                    pass
            revs = rk.get("user_reviews", [])
            if isinstance(revs, list) and idx < len(revs):
                rev = revs[idx]
                if isinstance(rev, dict):
                    nickname = rev.get("nickname", "")
                    rating = rev.get("rating", 0)
                    content = rev.get("content", "")
                    if content:
                        return f"[用户] {str(nickname)}({rating}星): {str(content)[:120]}"
    # 兜底
    if raw_score <= 1.0:
        return f"余弦相似度: {raw_score:.4f}"
    return f"Text match score: {raw_score}"
