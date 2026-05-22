"""V1 Decision Agent — 约束求解 + 评分排序 + 风险识别。

流程:
1. 硬约束过滤（预算、品类、必备标签）
2. 加权评分（复用 DecisionScoring 7维公式）
3. 风险识别（低分评论、高价警告）
4. 绑定 evidence_ids
5. 排序输出
"""

from app.agents.base import BaseAgent
from app.decision.scoring import DecisionScoring
from app.repositories.product_repo import ProductRepository
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState


class DecisionAgent(BaseAgent):

    def __init__(self, repo: ProductRepository | None = None):
        super().__init__()
        self._repo = repo or ProductRepository()
        self._scorer = DecisionScoring()

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="decision",
            name="Decision Agent",
            description="约束求解 + 加权评分 + 风险识别 + 证据绑定",
            capabilities=["constraint_solving", "scoring", "risk_analysis", "evidence_binding"],
            input_schema={"retrieved_products": "list[dict]", "evidence_list": "list[dict]"},
            output_schema={"decision_results": "list[dict]"},
        )

    def execute(self, state: WorkflowState) -> WorkflowState:
        action = "constraint_scoring"
        self._start_trace(state, action,
                          f"candidates={len(state.retrieved_products)}, budget_max={state.constraints.budget_max}")

        try:
            results = []
            constraints = state.constraints

            for item in state.retrieved_products:
                product = self._repo.get_by_id(item["product_id"])
                if product is None:
                    continue

                # 硬约束过滤
                if not self._passes_hard_constraints(product, constraints):
                    continue

                # 评分
                decision = self._scorer.score(
                    product=product,
                    query=state.user_query,
                    keyword_score=item.get("score", 0.0),
                    budget_max=constraints.budget_max,
                    scenario=constraints.scenario,
                    visual_result=state.visual_result,
                )
                results.append(decision.model_dump())

            # 按 final_score 降序
            results.sort(key=lambda r: r["final_score"], reverse=True)
            state.decision_results = results

            # 风险统计
            risky = sum(1 for r in results if r["display_score"] < 5.0)
            high = sum(1 for r in results if r["display_score"] >= 8.0)

            summary = f"scored={len(results)}, high_score(≥8)={high}, risky(<5)={risky}"
            return self._finish_trace(state, summary)

        except Exception as e:
            return self._error_trace(state, str(e))

    def _passes_hard_constraints(self, product, constraints) -> bool:
        """硬约束判断 — 不满足则直接过滤"""
        # 预算硬上限 (超过2倍预算直接过滤)
        if constraints.budget_max and product.base_price > constraints.budget_max * 2:
            return False

        # 品类精确匹配（如果指定了）
        if constraints.category and product.category != constraints.category:
            return False

        # 必备标签
        for tag in constraints.must_tags:
            found = tag.lower() in product.title.lower()
            if product.rag_knowledge:
                found = found or tag.lower() in product.rag_knowledge.marketing_description.lower()
            if not found:
                return False

        # 排除标签
        for tag in constraints.exclude_tags:
            if tag.lower() in product.title.lower():
                return False

        return True
