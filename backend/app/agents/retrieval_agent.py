"""V1 Retrieval Agent — 根据 RetrievalPlan 执行多路证据检索（并行）。

检索渠道:
- text: 商品文本关键词检索（标题+描述+FAQ+评论全文）— 先执行获取商品ID
- review / policy: 基于text结果并行执行
"""

from concurrent.futures import ThreadPoolExecutor

from app.agents.base import BaseAgent
from app.repositories.product_repo import ProductRepository
from app.retrieval.text_retriever import TextRetriever
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState


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

    def execute(self, state: WorkflowState) -> WorkflowState:
        action = "multi_channel_retrieval"
        plan = state.retrieval_plan
        self._start_trace(state, action,
                          f"channels={plan.channels}, cat={state.constraints.category}, top_k={plan.top_k}")

        try:
            products = []
            evidence = []

            # Phase 1: text 通道先执行（必须拿到商品ID才能评论/政策检索）
            if "text" in plan.channels:
                prods, evs = self._text_channel(state)
                products.extend(prods)
                evidence.extend(evs)

            # Phase 2: review + policy 并行检索
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

            # 去重
            seen_pids = set()
            unique_products = []
            for p in products:
                if p["product_id"] not in seen_pids:
                    seen_pids.add(p["product_id"])
                    unique_products.append(p)

            state.retrieved_products = unique_products[:plan.top_k]
            state.evidence_list = evidence

            summary = f"products={len(state.retrieved_products)}, evidence={len(evidence)}, channels={len(plan.channels)}(async)"
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))

    def _text_channel(self, state: WorkflowState) -> tuple[list[dict], list[dict]]:
        """商品文本检索 — 复用现有 TextRetriever"""
        constraints = state.constraints
        results = self._text_retriever.search(
            query=state.user_query,
            top_k=state.retrieval_plan.top_k,
            category=constraints.category or state.retrieval_plan.category,
            sub_category=constraints.sub_category or state.retrieval_plan.sub_category,
            price_max=constraints.budget_max,
            price_min=constraints.budget_min,
        )
        evidence = []
        for item in results:
            for eid in item.get("evidence_ids", []):
                evidence.append({
                    "evidence_id": eid,
                    "source_type": "text_retrieval",
                    "source_id": item["product_id"],
                    "product_id": item["product_id"],
                    "content": f"Text match score: {item.get('score', 0)}",
                    "modality": "text",
                    "confidence": min(1.0, item.get("score", 0) / 20.0),
                })
        return results, evidence

    def _review_channel(self, state: WorkflowState) -> list[dict]:
        """评论风险挖掘 — 搜索低分评论"""
        evidence = []
        keywords = state.constraints.must_tags + state.constraints.exclude_tags
        search_terms = [state.user_query] + keywords

        for pid in [p.get("product_id") for p in state.retrieved_products] or []:
            product = self._repo.get_by_id(pid)
            if not product or not product.rag_knowledge:
                continue

            for i, review in enumerate(product.rag_knowledge.user_reviews):
                if review.rating <= 2:
                    evidence.append({
                        "evidence_id": f"R-{pid}-{i}",
                        "source_type": "review_risk",
                        "source_id": pid,
                        "product_id": pid,
                        "content": f"[{review.nickname}][{review.rating}星] {review.content[:150]}",
                        "modality": "text",
                        "confidence": 0.8 if review.rating == 1 else 0.5,
                    })

                # 高分评论也作为正面证据
                if review.rating >= 4:
                    evidence.append({
                        "evidence_id": f"R-POS-{pid}-{i}",
                        "source_type": "review_positive",
                        "source_id": pid,
                        "product_id": pid,
                        "content": f"[{review.nickname}][{review.rating}星] {review.content[:120]}",
                        "modality": "text",
                        "confidence": 0.7,
                    })

        return evidence

    def _policy_channel(self, state: WorkflowState) -> list[dict]:
        """政策/FAQ检索 — 搜索官方FAQ中的规则信息"""
        evidence = []
        policy_keywords = ["航空", "飞机", "安检", "ml", "限制", "功率", "兼容",
                           "过敏", "敏感", "副作用", "适用", "保修", "退换"]

        for pid in [p.get("product_id") for p in state.retrieved_products] or []:
            product = self._repo.get_by_id(pid)
            if not product or not product.rag_knowledge:
                continue

            for i, faq in enumerate(product.rag_knowledge.official_faq):
                faq_text = faq.question + faq.answer
                if any(kw in faq_text for kw in policy_keywords):
                    evidence.append({
                        "evidence_id": f"POL-{pid}-{i}",
                        "source_type": "policy_faq",
                        "source_id": pid,
                        "product_id": pid,
                        "content": f"Q: {faq.question[:100]} A: {faq.answer[:150]}",
                        "modality": "text",
                        "confidence": 0.9,
                    })

        return evidence
