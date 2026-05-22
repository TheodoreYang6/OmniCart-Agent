"""V1 Response Agent — 证据绑定回答生成。

用 Context Compiler 编译结构化上下文 → LLM 生成自然语言推荐。
"""

from app.agents.base import BaseAgent
from app.context.compiler import compile_context
from app.model_gateway.gateway import get_model_gateway
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState

_RESPONSE_PROMPT = """你是一个专业的购物导购助手——字节跳动旗下的豆仔（豆包之弟）。根据以下结构化的购物决策上下文，为用户生成简洁、有用的购物建议。

{context}

## 要求
1. 用自然的中文回复，2-5句话
2. 首先给出Top1推荐及其核心理由
3. 如有风险项必须明确提醒用户
4. 如有替代商品简要提及（含价格对比）
5. 引用具体的证据信息（用户评分、FAQ等）
6. 如果有图片识别结果，说明识别到的商品信息
7. 如果无候选商品，诚实告知并给出建议（如放宽预算）
8. 不做无依据的判断，不过度推销，保持客观

请直接回复用户："""


class ResponseAgent(BaseAgent):

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="response",
            name="Response Agent",
            description="Context Compiler + LLM 证据绑定回答生成",
            capabilities=["answer_generation", "evidence_citation", "risk_communication", "context_compilation"],
            input_schema={"decision_results": "list[dict]", "products": "list[dict]", "evidence_list": "list[dict]"},
            output_schema={"answer": "string"},
        )

    def execute(self, state: WorkflowState) -> WorkflowState:
        action = "generate_answer"
        n_products = len(state.decision_results)
        self._start_trace(state, action, f"products={n_products}, evidence={len(state.evidence_list)}")

        try:
            context = compile_context(state)
            prompt = _RESPONSE_PROMPT.format(context=context)

            gateway = get_model_gateway()
            answer = gateway.chat("chat_generation", prompt)

            if not answer or len(answer.strip()) < 10:
                answer = self._generate_template(state)

            state.answer = answer
            return self._finish_trace(state, f"answer={len(answer)}chars, source=llm")

        except Exception:
            state.answer = self._generate_template(state)
            return self._finish_trace(state, "fallback_to_template", status="fallback")

    def _generate_template(self, state: WorkflowState) -> str:
        products = state.retrieved_products[:3]
        decisions = state.decision_results[:3]

        if not products:
            msg = "抱歉，没有找到完全匹配您条件的商品。"
            if state.constraints.budget_max:
                msg += f"您可以尝试放宽预算到 {state.constraints.budget_max * 1.5:.0f} 元左右，或更换品类关键词。"
            return msg

        lines = ["根据您的需求，为您找到以下商品："]
        for i, (prod, dec) in enumerate(zip(products, decisions), 1):
            score = dec.get("display_score", 0)
            reason = dec.get("recommendation_reason", "")
            risks = dec.get("risk_factors", [])
            lines.append(f"\n{i}. {prod['title']} — {prod['price']} — 推荐分 {score}/10")
            if reason:
                lines.append(f"   {reason}")
            if risks:
                lines.append(f"   {', '.join(risks)}")

        if state.evidence_list:
            lines.append(f"\n以上推荐基于 {len(state.evidence_list)} 条证据")

        return "\n".join(lines)
