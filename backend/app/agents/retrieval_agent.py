"""V1 Retrieval Agent — 根据 RetrievalPlan 执行多路证据检索（并行）。

检索渠道:
- text: 商品文本语义检索（LLM查询改写 + Embedding语义搜索）
- review / policy: 基于text结果并行执行
"""

import logging
import math
from concurrent.futures import ThreadPoolExecutor

from app.agents.base import BaseAgent
from app.repositories.product_repo import ProductRepository
from app.retrieval.text_retriever import TextRetriever
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState
from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_REWRITE

logger = logging.getLogger(__name__)


class RetrievalAgent(BaseAgent):

    def __init__(self, repo: ProductRepository | None = None):
        super().__init__()
        self._repo = repo or ProductRepository()
        self._text_retriever = TextRetriever(self._repo)

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="retrieval",
            name="Retrieval Agent",
            description="多路证据检索：文本检索 + 评论挖掘 + 政策查询",
            capabilities=["text_retrieval", "review_mining", "policy_search", "evidence_collection"],
            input_schema={"retrieval_plan": "RetrievalPlan", "constraints": "Constraints"},
            output_schema={"retrieved_products": "list[dict]", "evidence_list": "list[dict]"},
        )

    async def execute(self, state: WorkflowState) -> WorkflowState:
        action = "multi_channel_retrieval"
        plan = state.retrieval_plan
        self._start_trace(state, action,
                          f"channels={plan.channels}, cat={state.constraints.category}, top_k={plan.top_k}")

        try:
            products = []
            evidence = []

            # Phase 1: text 通道先执行（必须拿到商品ID才能评论/政策检索）
            if "text" in plan.channels:
                prods, evs = await self._text_channel(state)
                products.extend(prods)
                evidence.extend(evs)

            # P2-4: 补充证据通道 — 独立搜索 faq/rev chunk 发现更多商品
            if len(products) < 3:
                supp_products, supp_evidence = await self._supplementary_evidence_search(state)
                existing_pids = {p["product_id"] for p in products}
                for sp in supp_products:
                    if sp["product_id"] not in existing_pids:
                        products.append(sp)
                        existing_pids.add(sp["product_id"])
                evidence.extend(supp_evidence)

            # 去重
            seen_pids = set()
            unique_products = []
            for p in products:
                if p["product_id"] not in seen_pids:
                    seen_pids.add(p["product_id"])
                    unique_products.append(p)

            state.retrieved_products = unique_products[:plan.top_k]

            # Phase 2: review + policy 并行检索（必须在 state.retrieved_products 填充之后）
            secondary_channels = [c for c in plan.channels if c in ("review", "policy")]
            if secondary_channels:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = []
                    if "review" in secondary_channels:
                        futures.append(executor.submit(self._review_channel, state))
                    if "policy" in secondary_channels:
                        futures.append(executor.submit(self._policy_channel, state))
                    for f in futures:
                        evidence.extend(f.result())

            state.evidence_list = evidence

            summary = f"products={len(state.retrieved_products)}, evidence={len(evidence)}, channels={len(plan.channels)}(async)"
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))

    async def _llm_extract_keywords(self, user_query: str) -> str:
        """用 Qwen LLM 从口语查询中提取搜索关键词。失败时退回原 query。结果缓存 30 分钟。"""
        cache_key = make_key("rewrite", user_query)

        async def _do_rewrite() -> str:
            prompt = (
                "你是一个搜索关键词提取器。将用户的购物口语转化为商品搜索引擎友好的关键词，"
                "用空格分隔。提取品类、品牌、属性、场景等核心词。最多输出10个词。\n\n"
                f"用户说：{user_query}\n关键词："
            )
            try:
                from app.model_gateway.gateway import get_model_gateway
                gateway = get_model_gateway()
                result = await gateway.chat("chat_generation", prompt)
                keywords = result.strip()
                if keywords and len(keywords) >= 2:
                    logger.info(f"LLM keywords: {user_query!r} → {keywords!r}")
                    return keywords
            except Exception as e:
                logger.warning(f"LLM keyword extraction failed: {e}")
            return user_query

        return await cached(cache_key, REDIS_CACHE_TTL_REWRITE, _do_rewrite)

    async def _text_channel(self, state: WorkflowState) -> tuple[list[dict], list[dict]]:
        """商品文本检索 — 优先用 Router 结构化字段，不足时 LLM 补全。

        策略:
        - Router 已产出 sub_category + must_tags/spec_keywords → 跳过 LLM（省~600ms）
        - Router 产出不足（泛查询如"推荐一下"）→ 调 LLM 提取关键词（保准确率）
        """
        constraints = state.constraints

        # 判断 Router 产出是否足够丰富
        router_rich = bool(
            (constraints.sub_category and (
                constraints.must_tags or constraints.spec_keywords
            ))
            or (constraints.must_tags and len(constraints.must_tags) >= 2)
        )

        if router_rich:
            # 快速路径: Router 已提供足够的搜索词
            search_parts = [state.user_query]
            if constraints.category:
                search_parts.append(constraints.category)
            if constraints.sub_category:
                search_parts.append(constraints.sub_category)
            if constraints.must_tags:
                search_parts.append(" ".join(constraints.must_tags))
            if constraints.spec_keywords:
                search_parts.append(" ".join(constraints.spec_keywords))
            search_query = " ".join(search_parts)
        else:
            # 慢路径: Router 信息不足，LLM 提取关键词
            search_query = await self._llm_extract_keywords(state.user_query)
            if search_query != state.user_query:
                state.trace_steps.append({
                    "step_id": f"T{len(state.trace_steps) + 1:03d}",
                    "agent_name": "Retrieval Agent (LLM Rewrite)",
                    "action": "query_rewrite",
                    "input_summary": state.user_query[:60],
                    "output_summary": search_query[:80],
                    "latency_ms": 0,
                    "status": "success",
                })

        # 优先使用块级检索（语义匹配更精准），自动降级到产品级
        async def _do_search(sub_cat=None):
            try:
                return await self._text_retriever.search_chunked(
                    query=search_query,
                    top_k=state.retrieval_plan.top_k,
                    category=constraints.category or state.retrieval_plan.category,
                    sub_category=sub_cat,
                    price_max=constraints.budget_max,
                    price_min=constraints.budget_min,
                )
            except Exception:
                return await self._text_retriever.search(
                    query=search_query,
                    top_k=state.retrieval_plan.top_k,
                    category=constraints.category or state.retrieval_plan.category,
                    sub_category=sub_cat,
                    price_max=constraints.budget_max,
                    price_min=constraints.budget_min,
                )

        sub_cat = constraints.sub_category or state.retrieval_plan.sub_category
        results = await _do_search(sub_cat)

        # sub_category 无结果时自动放宽（Router 提取的 sub_category 可能与数据集不一致）
        if not results and sub_cat:
            results = await _do_search(None)
        evidence = []
        for item in results:
            raw_score = item.get("score", 0)
            if raw_score <= 1.0:
                confidence = round(raw_score, 4)
            else:
                confidence = round(min(1.0, 0.35 + 0.25 * math.log10(max(1, raw_score))), 4)
            rk = item.get("rag_knowledge")
            for eid in item.get("evidence_ids", []):
                # R-* 评论证据由 review_channel 负责，text_channel 只处理营销/FAQ
                if eid.startswith("R-"):
                    continue
                content = _evidence_content_for_id(eid, rk, raw_score)
                evidence.append({
                    "evidence_id": eid,
                    "source_type": "text_retrieval",
                    "source_id": item["product_id"],
                    "product_id": item["product_id"],
                    "content": content[:200],
                    "modality": "text",
                    "confidence": confidence,
                })
        return results, evidence

    def _review_channel(self, state: WorkflowState) -> list[dict]:
        """评论风险挖掘 — 从已检索结果中直接提取，无需再次 DB 查询"""
        evidence = []
        for item in state.retrieved_products or []:
            pid = item.get("product_id", "")
            if not pid:
                continue
            rk = item.get("rag_knowledge")
            if not rk:
                continue
            reviews = rk.get("user_reviews", []) if isinstance(rk, dict) else []
            if not reviews and hasattr(rk, "user_reviews"):
                reviews = rk.user_reviews

            for i, review in enumerate(reviews):
                rating = review.get("rating", 3) if isinstance(review, dict) else getattr(review, "rating", 3)
                nickname = review.get("nickname", "") if isinstance(review, dict) else getattr(review, "nickname", "")
                content = review.get("content", "") if isinstance(review, dict) else getattr(review, "content", "")
                if rating <= 2:
                    source_type, confidence = "review_risk", 0.8 if rating == 1 else 0.5
                elif rating == 3:
                    source_type, confidence = "review_neutral", 0.4
                else:
                    source_type, confidence = "review_positive", 0.7
                evidence.append({
                    "evidence_id": f"R-{pid}-{i}",
                    "source_type": source_type,
                    "source_id": pid,
                    "product_id": pid,
                    "content": f"[{nickname}][{rating}星] {content[:150]}",
                    "modality": "text",
                    "confidence": confidence,
                })

        return evidence

    def _policy_channel(self, state: WorkflowState) -> list[dict]:
        """政策/FAQ检索 — 从 top 商品中提取全部 FAQ（不再按关键词过滤）。"""
        evidence = []
        for item in (state.retrieved_products or [])[:3]:
            pid = item.get("product_id", "")
            if not pid:
                continue
            rk = item.get("rag_knowledge")
            if not rk:
                continue
            faqs = rk.get("official_faq", []) if isinstance(rk, dict) else []
            if not faqs and hasattr(rk, "official_faq"):
                faqs = rk.official_faq

            for i, faq in enumerate(faqs):
                question = faq.get("question", "") if isinstance(faq, dict) else getattr(faq, "question", "")
                answer = faq.get("answer", "") if isinstance(faq, dict) else getattr(faq, "answer", "")
                evidence.append({
                    "evidence_id": f"POL-{pid}-{i}",
                    "source_type": "policy_faq",
                    "source_id": pid,
                    "product_id": pid,
                    "content": f"Q: {question[:100]} A: {answer[:150]}",
                    "modality": "text",
                    "confidence": 0.9,
                })

        return evidence

    async def _supplementary_evidence_search(
        self, state: WorkflowState
    ) -> tuple[list[dict], list[dict]]:
        """P2-4: 独立 review/policy 证据检索通道。

        当主 text 检索结果 < 3 时，搜索 faq/rev chunk 反向发现遗漏商品。
        V2: 使用 embedding 余弦相似度替代关键词子串匹配。
        """
        constraints = state.constraints
        query = state.user_query
        products: list[dict] = []
        evidence: list[dict] = []

        try:
            import json
            import math
            from pathlib import Path
            cache_path = (
                Path(__file__).resolve().parent.parent.parent
                / "backend" / "data" / "product_chunk_embeddings.json"
            )
            if not cache_path.exists():
                return products, evidence

            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            chunks = cache_data.get("chunks", [])

            evidence_chunks = [
                c for c in chunks
                if c.get("chunk_type") in ("faq", "rev")
            ]
            if not evidence_chunks:
                return products, evidence

            # V2: Embedding语义搜索，替代关键词子串匹配
            query_vec = None
            try:
                from app.model_gateway.gateway import get_model_gateway
                gateway = get_model_gateway()
                embeddings = await gateway.embed([query], "text_embedding")
                query_vec = embeddings[0]
            except Exception:
                pass  # Embedding失败时降级为关键词匹配

            matched_pids: dict[str, float] = {}
            if query_vec and len(query_vec) == cache_data.get("dimension", 1024):
                # 语义搜索: 余弦相似度
                for chunk in evidence_chunks:
                    emb = chunk.get("embedding")
                    if not emb or len(emb) != len(query_vec):
                        continue
                    dot = sum(x * y for x, y in zip(query_vec, emb))
                    mag_q = math.sqrt(sum(x * x for x in query_vec))
                    mag_c = math.sqrt(sum(x * x for x in emb))
                    sim = dot / (mag_q * mag_c) if mag_q > 0 and mag_c > 0 else 0.0
                    if sim > 0.35:  # 最低相似度阈值
                        pid = chunk.get("payload", {}).get("product_id", "")
                        if pid:
                            matched_pids[pid] = max(matched_pids.get(pid, 0), sim)
            else:
                # 降级: 关键词子串匹配（兼容无embedding环境）
                query_lower = query.lower()
                query_words = [w for w in query_lower.split() if len(w) >= 2]
                for chunk in evidence_chunks:
                    payload = chunk.get("payload", {})
                    text = (
                        f"{payload.get('title', '')} {payload.get('brand', '')} "
                        f"{payload.get('category', '')} {payload.get('sub_category', '')}"
                    ).lower()
                    score = sum(1.0 for w in query_words if w in text)
                    if score > 0:
                        pid = payload.get("product_id", "")
                        if pid:
                            matched_pids[pid] = max(matched_pids.get(pid, 0), score)

            if matched_pids:
                top_pids = sorted(matched_pids, key=matched_pids.get, reverse=True)[:5]
                for pid in top_pids:
                    for c in evidence_chunks:
                        p = c.get("payload", {})
                        if p.get("product_id") == pid and pid not in {
                            ep.get("product_id") for ep in products
                        }:
                            if constraints.category and p.get("category") != constraints.category:
                                continue
                            products.append({
                                "product_id": pid,
                                "title": p.get("title", ""),
                                "brand": p.get("brand", ""),
                                "category": p.get("category", ""),
                                "sub_category": p.get("sub_category", ""),
                                "price": p.get("price", 0),
                                "score": matched_pids.get(pid, 0),
                                "source_channel": "evidence_supplement",
                                "image_urls": [f"/api/products/{pid}/image"],
                                "rag_knowledge": {},
                                "skus": [],
                            })
                            break

                    src_type = "policy_faq" if any(
                        c.get("chunk_type") == "faq" and c.get("payload", {}).get("product_id") == pid
                        for c in evidence_chunks
                    ) else "review_positive"

                    evidence.append({
                        "evidence_id": f"E-SUPP-{pid}",
                        "source_type": src_type,
                        "source_id": "supplementary_evidence",
                        "product_id": pid,
                        "content": f"Supplementary evidence match for: {query[:60]}",
                        "modality": "text",
                        "confidence": round(min(0.65, matched_pids.get(pid, 0.35)), 4),
                    })
        except Exception as e:
            logger.debug(f"Supplementary evidence search skipped: {e}")

        return products, evidence


def _evidence_content_for_id(eid: str, rag_knowledge, raw_score: float) -> str:
    """根据 evidence_id 前缀从 rag_knowledge 提取对应的可读正文。"""
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
                try: idx = int(parts[1])
                except ValueError: pass
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
                try: idx = int(parts[1])
                except ValueError: pass
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
