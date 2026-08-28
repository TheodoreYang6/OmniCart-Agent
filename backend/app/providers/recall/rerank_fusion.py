"""RerankFusion —— LLM 语义精排 + 分数校准 + 视觉置顶钩子。

收敛自 ``graph._node_reranker`` 的内联逻辑（spec §三），行为逐字节保持：
1. 用商品文本 + rag_knowledge + 证据片段拼 rerank 文档；
2. 调 gateway.rerank 得原始相关度并保留；另生成仅用于排序稳定性的 ``reranker_score``；
3. 按校准分降序重排；
4. **视觉精确匹配商品锁定 0.99**（视觉置顶钩子）。

graph 节点只保留 FAST_MODE 守卫 + trace/timing 包装，精排逻辑全部下沉到此。
"""

from __future__ import annotations

from typing import Any

from app.framework.registry import component


@component(kind="reranker", name="llm_rerank_fusion", priority=10)
class RerankFusion:
    """商品语义精排器。"""

    name = "llm_rerank_fusion"

    def __init__(self, gateway: Any = None) -> None:
        self._gateway = gateway

    def _get_gateway(self) -> Any:
        if self._gateway is None:
            from app.model_gateway.gateway import get_model_gateway

            self._gateway = get_model_gateway()
        return self._gateway

    async def rerank(
        self,
        *,
        query: str,
        products: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        visual_matched_pids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if len(products) <= 1:
            return products

        ev_by_pid: dict[str, list[str]] = {}
        for ev in evidence or []:
            pid = ev.get("product_id", "")
            content = ev.get("content", "")
            if pid and content and "余弦相似度" not in str(content) and "Text match" not in str(content):
                ev_by_pid.setdefault(pid, []).append(str(content)[:300])

        documents = [self._build_doc(p, ev_by_pid) for p in products]

        ranked = await self._rerank_cached(query, documents,
                                           [str(p.get("product_id", "")) for p in products])

        # ``reranker_score`` 历史上带有很高的展示基线（甚至可超过 1），只能用于
        # 稳定排序；决策评分必须读取未经抬升的 ``relevance_score``，否则弱相关候选
        # 也会被当成高度匹配。
        raw_relevance = {
            r["index"]: max(0.0, min(1.0, float(r["relevance_score"])))
            for r in ranked
        }
        index_map = {idx: 0.68 + 0.38 * score for idx, score in raw_relevance.items()}
        for idx, p in enumerate(products):
            p["reranker_score"] = index_map.get(idx, 0.0)
            p["relevance_score"] = raw_relevance.get(idx, 0.0)

        # V6.1 噪声带量化 + 稳定排序：cross-encoder 对同质候选（同品牌同品类多款）
        # 的分差常在噪声量级，直接按原始分排会无据换序打乱召回序（评测实证
        # title 形态 hit@1 下降）。将分数量化到 0.05 档位，同档内保留召回序
        # （sorted 稳定性）：只有显著更相关才能提前。
        def _band(idx: int) -> float:
            return round(index_map.get(idx, 0.0) / 0.05)

        reordered = [p for _, p in sorted(enumerate(products), key=lambda x: -_band(x[0]))]

        # 视觉置顶钩子：精确匹配商品锁定最高分
        visual_pids = set(visual_matched_pids or [])
        for p in reordered:
            if p.get("product_id") in visual_pids:
                p["reranker_score"] = 0.99
                p["relevance_score"] = 0.99

        return reordered

    async def _rerank_cached(self, query: str, documents: list[str], pids: list[str]) -> list[dict]:
        """rerank 结果 Redis 短缓存 — 同 (query, 候选集) 重复精排直接命中（本地模型秒级开销）。"""
        from app.core.cache import cached, make_key
        from app.core.config import REDIS_CACHE_TTL_SEARCH

        # d2 版本盐：doc 拼法变更（V6.1 命中块入 doc）后不命中旧缓存
        key = make_key("rerank", "d2", query, "|".join(pids))

        async def _do() -> list[dict]:
            return await self._get_gateway().rerank(query=query, documents=documents, top_n=len(documents))

        return await cached(key, REDIS_CACHE_TTL_SEARCH, _do)

    @staticmethod
    def _build_doc(p: dict[str, Any], ev_by_pid: dict[str, list[str]]) -> str:
        """拼精排文档 — 标题+品类 基础信号 + 召回命中块文本（V6.1）。

        V6.1 评测实证：doc 缺失召回命中信号时 reranker 负增益（faq 形态 hit@1
        0.969→0.766）——FAQ 问法的匹配证据在 faq 块里，cross-encoder 看不到就会
        把召回已排对的结果打乱。故优先拼入 matched_chunks（检索层现成返回的
        命中块正文），再补营销描述；总长控制 ~450 字。"""
        doc = f"{p.get('title', '')} {p.get('category', '')} {p.get('sub_category', '')}"

        # 召回命中块（faq/rev/mkt 文本）——reranker 能看到“为什么被召回”
        budget = 300
        for ch in (p.get("matched_chunks") or [])[:2]:
            text = str((ch.get("payload") or {}).get("text", ""))
            if not text:
                continue
            piece = text[: min(150, budget)]
            doc += f" {piece}"
            budget -= len(piece)
            if budget <= 0:
                break

        if budget > 0:
            desc = p.get("description", "")
            if not desc:
                rk = p.get("rag_knowledge") or {}
                if isinstance(rk, dict):
                    desc = str(rk.get("marketing_description", "") or "")
            if desc:
                doc += f" {desc[:budget]}"
        return doc
