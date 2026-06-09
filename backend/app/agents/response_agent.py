"""V3 Response Agent — 压缩上下文 + 超时兜底 + FAST_MODE 模板优先。

FAST_MODE=true: 模板回答 → LLM 可选润色 (≤6s)
FAST_MODE=false: LLM 生成 → 模板兜底 (≤6s timeout)
"""

import asyncio
import time

from app.agents.base import BaseAgent
from app.context.compiler import compile_context
from app.core.config import FAST_MODE
from app.model_gateway.gateway import get_model_gateway
from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState

_CHITCHAT_PROMPT = """你是豆仔，字节跳动旗下的智能购物导购助手（豆包之弟，豆包是你的姐姐，她总是欺负你）。你的形象是一个可爱的豆仔卡通角色。

用户说：{query}

请用亲切、活泼的语气回复。规则：
- 先回应情绪：用户说"想你""爱你"→ 撒个娇说也想ta；用户说"累""困""饿""无聊"→ 先关心一下
- 再顺势引导：回完人话后，自然地提到可以帮ta推荐相关商品。比如用户说饿了→ 推荐零食；说累了→ 推荐放松好物；说无聊→ 推荐新奇有趣的东西
- 如果是打招呼/自我介绍/感谢/告别 → 热情回应并简单介绍自己
- 不要强行推销，要像朋友聊天一样自然过渡到购物话题
- 只推荐品类方向，不要提到具体品牌或价格

控制在2-4句话，活泼自然。直接回复："""

_RESPONSE_PROMPT = """你是一个严谨的购物导购助手——字节跳动旗下的豆仔。你的回答必须严格基于下方提供的候选商品和证据，不得编造、推测或提及候选列表之外的任何商品。

{context}

## 红线（违反即为失败）
- 禁止提及候选商品列表中不存在的品牌、型号、价格
- 禁止说"可能是""大概有""市场上还有"等推测性表述
- 如果候选商品列表为空，只能说"抱歉，没有找到匹配的商品"，不得自行推荐
- 引用具体证据时用自然语言融入（如"用户评价提到..."），不要输出证据ID和推荐分数（这些在商品卡片中已展示）

## 要求
1. 用自然的中文回复，3-6句话
2. 首先给出Top1推荐，必须引用候选列表中的 exact 商品名和价格
3. 如有风险项必须明确提醒用户
4. 如有替代商品简要提及（必须是候选列表中的其他商品）
5. 引用具体的证据信息（用户评价、FAQ等）
6. 如果候选商品列表为空，只说：抱歉，没有找到完全匹配您条件的商品 + 建议放宽条件
7. 不要输出推荐分数（如"推荐分6.3/10"），用户在商品卡片中已能看到
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

    async def execute(self, state: WorkflowState) -> WorkflowState:
        action = "generate_answer"
        self._start_trace(state, action, f"intent={state.intent}, products={len(state.decision_results)}, fast={FAST_MODE}")

        try:
            if state.intent == "chitchat":
                state.answer = await self._handle_chitchat(state.user_query)
            elif not state.retrieved_products:
                state.answer = self._generate_template(state)
            elif FAST_MODE:
                state.answer = await self._generate_with_optional_llm(state)
            else:
                state.answer = await self._generate_with_llm_fallback(state)

            return self._finish_trace(state, f"answer={len(state.answer)}chars")

        except Exception:
            if state.intent == "chitchat":
                state.answer = self._chitchat_fallback(state.user_query)
            else:
                state.answer = self._generate_template(state)
            return self._finish_trace(state, "fallback", status="fallback")

    async def _generate_with_llm_fallback(self, state: WorkflowState) -> str:
        """LLM 生成 + 6s 超时 → 模板兜底。"""
        context = compile_context(state)
        prompt = _RESPONSE_PROMPT.format(context=context)
        try:
            gateway = get_model_gateway()
            answer = await asyncio.wait_for(
                gateway.chat("chat_generation", prompt),
                timeout=6.0,
            )
            if not answer or len(answer.strip()) < 10:
                return self._generate_template(state)
            if not self._answer_cites_products(answer, state.retrieved_products):
                return self._generate_template(state)
            return answer
        except (asyncio.TimeoutError, Exception):
            return self._generate_template(state)

    async def generate_stream(self, state: WorkflowState):
        """流式生成 — async generator，每个 token yield。

        调用方用 async for token in agent.generate_stream(state) 接收。
        流失败时 yield 模板结果作为兜底。
        """
        if state.intent == "chitchat":
            # 闲聊也用流式
            try:
                gateway = get_model_gateway()
                prompt = _CHITCHAT_PROMPT.format(query=state.user_query)
                async for token in gateway.chat_stream("chat_generation", prompt):
                    yield token
                return
            except Exception:
                for ch in self._chitchat_fallback(state.user_query):
                    yield ch
                return

        if not state.retrieved_products:
            for ch in self._generate_template(state):
                yield ch
            return

        if FAST_MODE:
            for ch in self._generate_template(state):
                yield ch
            return

        # LLM 流式生成
        full = ""
        try:
            context = compile_context(state)
            prompt = _RESPONSE_PROMPT.format(context=context)
            gateway = get_model_gateway()
            async for token in gateway.chat_stream("chat_generation", prompt):
                full += token
                yield token
            # 流完成后校验
            if len(full.strip()) < 10 or not self._answer_cites_products(full, state.retrieved_products):
                for ch in self._generate_template(state):
                    yield ch
        except Exception:
            for ch in self._generate_template(state):
                yield ch

    async def _generate_with_optional_llm(self, state: WorkflowState) -> str:
        """FAST_MODE: 纯模板回答，不调 LLM。"""
        return self._generate_template(state)

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
        """闲聊模板兜底 — 先回人话再顺势推荐"""
        q = query.lower().strip()
        if any(w in q for w in ["你好", "嗨", "哈喽", "hello", "hi", "在吗", "早", "早上好", "下午好", "晚上好"]):
            return "嗨！我是豆仔，你的智能购物导购助手~ 想买什么？直接告诉我就好，还能拍照识图哦！"
        if any(w in q for w in ["你是谁", "你叫什么", "你的名字", "介绍你自己", "介绍一下", "你是什么"]):
            return "我是豆仔，字节跳动旗下的智能购物导购助手，豆包的弟弟！专精商品推荐、截图分析和对比评测，帮你选到心仪好物~"
        if any(w in q for w in ["你是ai", "你是机器人", "你是人工", "你是哪个模型", "模型", "大模型", "基于什么"]):
            return "我是基于通义千问大模型的AI购物助手～豆包的弟弟豆仔！专门帮你挑好物的，想买什么尽管问我！"
        if any(w in q for w in ["豆包", "豆包是谁", "你和豆包", "豆包和你"]):
            return "豆包是我哥！他是全能AI助手，我是他弟弟，专精购物导购～想买什么？我帮你挑！"
        if any(w in q for w in ["豆仔"]):
            return "嘿嘿，豆仔就是我呀～你的专属购物导购！想买什么？零食、数码、美妆、运动装备，我都帮你挑！"
        if any(w in q for w in ["claude", "gpt", "chatgpt"]):
            return "我是豆仔，字节跳动旗下的购物导购AI，基于通义千问大模型～不是Claude也不是GPT哦！但我一样能帮你挑到好东西！"
        if any(w in q for w in ["你能做什么", "你会什么", "功能", "你能干嘛"]):
            return "我能帮你：\n🔍 根据需求推荐商品\n📷 拍照识别商品信息\n📊 对比分析多个产品\n🛒 直接加入购物车\n\n想试试哪个？"
        if any(w in q for w in ["谢谢", "感谢", "多谢"]):
            return "不客气~ 随时找我，购物愉快！"
        if any(w in q for w in ["拜拜", "再见", "晚安", "回头见"]):
            return "再见！逛累了随时来找我，豆仔随时在线~"
        if any(w in q for w in ["想你", "爱你", "喜欢你", "摸摸", "抱抱", "贴贴"]):
            return "哎呀我也想你呀～豆仔一直在等你来逛呢！想买点什么？零食、咖啡、还是新衣服？"
        if any(w in q for w in ["好累", "累了", "好困", "困了", "好饿", "饿了"]):
            return "辛苦啦！饿了可不能拖～要不要一起挑点香喷喷的零食？酥脆的、软糯的、酸酸甜甜的……豆仔都帮你盯着呢！"
        if any(w in q for w in ["吃饭", "想吃", "想喝"]):
            return "想吃点啥？豆仔这里有零食、饮料、方便食品，帮你挑～"
        if any(w in q for w in ["无聊", "好无聊", "好烦", "烦死了", "郁闷", "崩溃"]):
            return "无聊的时候最适合逛好东西啦！要不要豆仔给你推荐点新奇有趣的小玩意儿？"
        if any(w in q for w in ["天气", "心情", "开心", "难过"]):
            return "不管心情怎么样，购物都能治愈！想看点啥？美食、美妆还是数码好物？"
        if any(w in q for w in ["测试", "test", "你能收到", "听到吗", "在不在"]):
            return "在的在的！豆仔随时待命～想买什么直接说，我帮你推荐！"
        if any(w in q for w in ["哈哈", "呵呵", "嘿嘿"]):
            return "哈哈，看来心情不错呀！要不要趁心情好逛一逛？零食、数码、美妆，豆仔帮你推荐～"
        if any(w in q for w in ["唱歌", "故事", "讲故事", "背诗", "笑话", "讲笑话"]):
            return "哈哈，豆仔更擅长帮你挑商品哦～不过你要是想听，我可以推荐你买本有趣的书或音箱来听歌！"
        # 看起来像乱打/手滑/纯符号
        if len(query) <= 3 and not any('一' <= c <= '鿿' for c in query):
            return "诶？没太看懂你想说啥～不过没关系！我是豆仔，你的购物导购助手，想买什么直接告诉我就好！"
        return "诶？没太看懂～不过豆仔更擅长帮你挑商品！想买什么呀？直接说就行～"

    @staticmethod
    def _answer_cites_products(answer: str, products: list[dict]) -> bool:
        """验证 LLM 回答是否引用了至少一个检索到的商品名/品牌。

        如果回答中没有任何候选商品的关键词 → 判定为幻觉，回退到模板。
        """
        if not products:
            return False
        for p in products[:5]:
            title = p.get("title", "")
            brand = p.get("brand", "")
            # 检查商品名至少连续3个字出现，或品牌名出现
            for token in [title[:6], title[-6:], brand]:
                if token and len(token) >= 2 and token in answer:
                    return True
            # 检查完整标题中的长词
            for word in title.split():
                if len(word) >= 3 and word in answer:
                    return True
        return False

    def _generate_template(self, state: WorkflowState) -> str:
        top_n = 5 if state.visual_result else 3
        products = state.retrieved_products[:top_n]
        decisions = state.decision_results[:top_n]

        if not products:
            vr = state.visual_result or {}
            if vr.get("product_name"):
                # 有识图结果但没搜到：品类过滤问题 vs 真的没有
                if state.constraints.category:
                    msg = (
                        f"您拍的看起来是「{vr['product_name']}」"
                        + (f"（{vr.get('brand', '')}）" if vr.get("brand") else "")
                        + f"。当前在「{state.constraints.category}」品类下没有找到匹配商品"
                        + "，可能是品类范围太窄，已为您扩大搜索。"
                    )
                else:
                    msg = (
                        f"您拍的看起来是「{vr['product_name']}」"
                        + (f"（{vr.get('brand', '')}）" if vr.get("brand") else "")
                        + "。抱歉，目前商品库里还没有收录这款商品。"
                    )
            else:
                msg = "抱歉，没有找到完全匹配您条件的商品。"
            if state.constraints.budget_max:
                msg += f"您可以尝试放宽预算到 {state.constraints.budget_max * 1.5:.0f} 元左右，或更换品类关键词。"
            return msg

        # 视觉识别结果优先展示：同款在前，同类在后
        vr = state.visual_result or {}
        visual_note = ""
        # 区分是否有精确匹配
        exact_pids = set(state.visual_matched_pids or [])
        exact_products = [p for p in products if p.get("product_id") in exact_pids]
        other_products = [p for p in products if p.get("product_id") not in exact_pids]
        exact_decisions = [d for d in decisions if d.get("product_id") in exact_pids]
        other_decisions = [d for d in decisions if d.get("product_id") not in exact_pids]

        if vr.get("product_name"):
            if exact_products:
                visual_note = (
                    f"您拍的看起来是「{vr['product_name']}」"
                    + (f"（{vr.get('brand', '')}）" if vr.get('brand') else "")
                    + "。这就是这款商品👇"
                )
            else:
                visual_note = (
                    f"您拍的看起来是「{vr['product_name']}」"
                    + (f"（{vr.get('brand', '')}）" if vr.get('brand') else "")
                    + "。商品库暂无同款，为您推荐同类商品👇"
                )
        elif vr.get("brand"):
            visual_note = f"您拍的品牌是{vr['brand']}，为您找到以下商品："

        # 用户偏好上下文
        profile_note = ""
        if state.context_prompt and "[用户偏好]" in state.context_prompt:
            profile_note = state.context_prompt.split("\n")[0].strip() + "\n\n"

        # 等级中文映射
        level_cn = {
            "strong_recommend": "强烈推荐", "recommended": "推荐",
            "cautious": "谨慎推荐", "insufficient_evidence": "证据不足，仅供参考",
            "not_recommended": "不推荐",
        }

        lines = [profile_note + (visual_note or "根据您的需求，为您找到以下商品：")]
        # 同款优先，再同类推荐
        display_list = list(zip(exact_products, exact_decisions)) if exact_products else []
        if exact_products and other_products:
            display_list += [(None, None)]  # 分隔标记
        display_list += list(zip(other_products, other_decisions))
        idx = 0
        for prod, dec in display_list:
            if prod is None:
                lines.append("\n📌 同类推荐：")
                continue
            idx += 1
            score = dec.get("display_score", 0)
            reason = dec.get("recommendation_reason", "")
            risks = dec.get("risk_factors", [])
            level = dec.get("recommendation_level", "")
            level_label = level_cn.get(level, "")

            title = prod.get("title", "")
            # 标题截断: 中英文混合的手机名太长，保留前30字
            title_short = title[:30] + ("..." if len(title) > 30 else "")

            header = f"\n{idx}. {title_short} — ¥{prod.get('price', 0)}"
            if level_label:
                header += f" [{level_label}]"
            lines.append(header)
            if reason and not reason.startswith(("强烈推荐", "值得购买", "可以考虑", "仅供参考")):
                lines.append(f"   {reason[:120]}")
            if risks:
                lines.append(f"   ⚠ {', '.join(risks[:2])}")

        return "\n".join(lines)
