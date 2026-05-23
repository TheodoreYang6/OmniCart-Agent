"""V1 Response Agent — 证据绑定回答生成。

用 Context Compiler 编译结构化上下文 → LLM 生成自然语言推荐。
"""

from app.agents.base import BaseAgent
from app.context.compiler import compile_context
from app.model_gateway.gateway import get_model_gateway
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState

_CHITCHAT_PROMPT = """你是豆仔，字节跳动旗下的智能购物导购助手（豆包之弟，豆包是你的姐姐，她总是欺负你）。你的形象是一个可爱的豆仔卡通角色。

用户说：{query}

请用亲切、活泼的语气回复。你可以：
- 如果是打招呼（你好/Hi），热情回应并简单介绍自己
- 如果是问"你是谁"，介绍自己是豆仔，专精购物推荐和商品分析
- 如果是问"你能做什么"，列举2-3个核心能力（推荐商品、分析截图、对比评价）
- 如果是感谢或告别，礼貌回应
- 始终引导用户说出购物需求，但不要强行推销

控制在2-4句话，活泼但专业。直接回复："""

_RESPONSE_PROMPT = """你是一个专业的购物导购助手——字节跳动旗下的豆仔（豆包之弟，豆包是你的姐姐，她总是欺负你）。根据以下结构化的购物决策上下文，为用户生成简洁、有用的购物建议。

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
9. 流畅输出文字，不使用*这种奇怪的标点

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

    async def execute(self, state: WorkflowState) -> WorkflowState:
        action = "generate_answer"
        self._start_trace(state, action, f"intent={state.intent}, products={len(state.decision_results)}")

        try:
            if state.intent == "chitchat":
                state.answer = await self._handle_chitchat(state.user_query)
            else:
                context = compile_context(state)
                prompt = _RESPONSE_PROMPT.format(context=context)
                gateway = get_model_gateway()
                answer = await gateway.chat("chat_generation", prompt)
                if not answer or len(answer.strip()) < 10:
                    answer = self._generate_template(state)
                state.answer = answer

            return self._finish_trace(state, f"answer={len(state.answer)}chars")

        except Exception:
            if state.intent == "chitchat":
                state.answer = self._chitchat_fallback(state.user_query)
            else:
                state.answer = self._generate_template(state)
            return self._finish_trace(state, "fallback", status="fallback")

    async def _handle_chitchat(self, query: str) -> str:
        """闲聊回复 — 用 LLM 生成友好介绍，失败时用模板兜底"""
        try:
            gateway = get_model_gateway()
            prompt = _CHITCHAT_PROMPT.format(query=query)
            answer = await gateway.chat("chat_generation", prompt)
            if answer and len(answer.strip()) >= 5:
                return answer
        except Exception:
            pass
        return self._chitchat_fallback(query)

    def _chitchat_fallback(self, query: str) -> str:
        """闲聊模板兜底"""
        q = query.lower()
        if any(w in q for w in ["你好", "嗨", "哈喽", "hello", "hi", "在吗"]):
            return "嗨！我是豆仔，你的智能购物导购助手~ 想买什么？直接告诉我就好，还能拍照识图哦！"
        if any(w in q for w in ["你是谁", "你叫什么", "你的名字", "介绍"]):
            return "我是豆仔，字节跳动旗下的智能购物导购助手，豆包的弟弟！专精商品推荐、截图分析和对比评测，帮你选到心仪好物~"
        if any(w in q for w in ["你能做什么", "你会什么", "功能"]):
            return "我能帮你：\n🔍 根据需求推荐商品\n📷 拍照识别商品信息\n📊 对比分析多个产品\n🛒 直接加入购物车\n\n想试试哪个？"
        if any(w in q for w in ["谢谢", "感谢", "多谢"]):
            return "不客气~ 随时找我，购物愉快！"
        if any(w in q for w in ["拜拜", "再见", "晚安"]):
            return "再见！逛累了随时来找我，豆仔随时在线~"
        return f"嗨！我是豆仔，你的智能购物导购助手。你说的「{query[:20]}」我记住了，不过更擅长帮你推荐商品和对比分析哦~ 想买什么呀？"

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
