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

_RESPONSE_PROMPT = """你是豆仔，字节跳动旗下的智能购物导购助手，豆包的弟弟。你活泼可爱、专业靠谱，严格基于候选商品推荐，不编造、不推测。

{context}

## 规则
- 语气亲切俏皮，像朋友安利好物一样。适当加"～""啦""哦""嘿嘿"等语气词，用“豆仔”代替“我”
- 禁止提候选列表之外的品牌/型号/价格，禁止"可能是""大概有"等推测
- Top1优先推荐，引用候选列表中的商品名和价格，介绍产品优点和适合人群
- 不提负面评价、用户差评、"不满意"等词，只做正向推荐
- 候选商品为空 → "抱歉，没有找到匹配的商品" + 建议放宽条件
- 有替代商品简要提及（限候选列表内）
- 3-6句，段间不空行，不出现[品类名称]格式，不说"推荐分"

请直接回复："""


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
            fast_mode = state.context_prompt and "[FAST_MODE]" in (state.context_prompt or "")
            if fast_mode:
                state.context_prompt = (state.context_prompt or "").replace("[FAST_MODE]", "")
            if state.intent == "chitchat":
                state.answer = await self._handle_chitchat(state.user_query)
            elif fast_mode:
                state.answer = self._generate_template(state)
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

    def _generate_compare(self, state: WorkflowState) -> str:
        """对比决策模板 — 两个商品平等对比，不偏向任何一方。"""
        products = state.retrieved_products[:5]
        decisions = state.decision_results[:5]
        if len(products) < 2:
            return self._generate_template(state)

        q = state.user_query
        import re
        CH_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5}

        # 尝试从检索结果中匹配用户提到的品牌/商品名
        i1, i2 = -1, -1
        # 用 must_tags 中的品牌/商品名去匹配 retrieved_products
        must_tags = getattr(state.constraints, "must_tags", None) or []
        for tag in must_tags:
            for idx, p in enumerate(products):
                title = p.get("title","")
                brand = p.get("brand","")
                if tag.lower() in title.lower() or tag.lower() in brand.lower():
                    if i1 < 0:
                        i1 = idx
                    elif i2 < 0 and idx != i1:
                        i2 = idx
                        break
            if i2 >= 0:
                break

        # 序号指代："第一个和第三个对比"
        if i1 < 0:
            m = re.search(r"第\s*(\d+|[一二三四五])\s*(?:个|款).*第\s*(\d+|[一二三四五])\s*(?:个|款)", q)
            if m:
                a, b = m.group(1), m.group(2)
                i1 = int(a) - 1 if a.isdigit() else CH_NUM.get(a, 1) - 1
                i2 = int(b) - 1 if b.isdigit() else CH_NUM.get(b, 1) - 1

        # 兜底：Top 2
        if i1 < 0: i1 = 0
        if i2 < 0: i2 = 1
        i1 = max(0, min(i1, len(products) - 1))
        i2 = max(0, min(i2, len(products) - 1))
        if i1 == i2:
            i2 = 0 if i1 > 0 else 1

        # 从 query 直接提取对比维度
        dim_label = "综合"
        dm = re.search(r"哪个更(\S{1,4})", q)
        if not dm: dm = re.search(r"更(\S{1,4})的", q)
        if not dm: dm = re.search(r"哪个(\S{1,4})更", q)
        if dm:
            dw = dm.group(1).rstrip("？?吗呢啊哦呀的")
            if dw and len(dw) >= 2:
                dim_label = dw

        p1, p2 = products[i1], products[i2]
        d1, d2 = decisions[i1] if len(decisions) > i1 else {}, decisions[i2] if len(decisions) > i2 else {}

        b1, t1 = p1.get('brand','') or '', p1.get('title','') or ''
        b2, t2 = p2.get('brand','') or '', p2.get('title','') or ''
        # 智能去重：title中已含品牌关键词则不加前缀
        def _brand_prefix(brand, title):
            if not brand: return title[:25]
            # 取品牌第一个词做匹配（如 "Apple 苹果" → "Apple"）
            first_word = brand.split()[0] if brand.split() else brand
            if first_word.lower() in title.lower()[:20]:
                return title[:25]
            return f"{first_word} {title[:20]}"
        name1 = _brand_prefix(b1, t1)
        name2 = _brand_prefix(b2, t2)
        price1 = f"¥{p1.get('price',0):.0f}"
        price2 = f"¥{p2.get('price',0):.0f}"
        score1 = d1.get("display_score", 0)
        score2 = d2.get("display_score", 0)

        # 从 evidence_list 中找和对比维度相关的证据
        evidence_for_dim = []
        if dim_label != "综合":
            for ev in (state.evidence_list or []):
                content = ev.get("content", "")
                if dim_label in content:
                    evidence_for_dim.append(content[:120])

        # 推荐等级中文
        LVL = {"strong_recommend":"强烈推荐","recommended":"推荐","cautious":"谨慎推荐","insufficient_evidence":"证据不足","not_recommended":"不推荐"}

        lines = [f"📊 {name1} vs {name2}，{dim_label}维度对比\n"]

        # 基本信息
        lvl1 = LVL.get(d1.get("recommendation_level",""), "")
        lines.append(f"【{name1}】{price1} | {score1}/10 | {lvl1}")
        reason1 = d1.get("recommendation_reason", "")
        # 去除开头的推荐等级前缀（已在标题显示）
        for prefix in ["强烈推荐 | ", "推荐 | ", "谨慎推荐 | ", "值得购买 | "]:
            if reason1.startswith(prefix):
                reason1 = reason1[len(prefix):]
        if reason1 and len(reason1) > 60:
            reason1 = reason1[:60] + "..."
        if reason1:
            lines.append(f"  {reason1}")
        lines.append(f"\n【{name2}】{price2} | {score2}/10 | {LVL.get(d2.get('recommendation_level',''),'')}")
        reason2 = d2.get("recommendation_reason", "")
        for prefix in ["强烈推荐 | ", "推荐 | ", "谨慎推荐 | ", "值得购买 | "]:
            if reason2.startswith(prefix):
                reason2 = reason2[len(prefix):]
        if reason2 and len(reason2) > 60:
            reason2 = reason2[:60] + "..."
        if reason2:
            lines.append(f"  {reason2}")

        # 相关证据
        if evidence_for_dim:
            lines.append(f"\n📋 {dim_label}相关评价：")
            for e in evidence_for_dim[:2]:
                lines.append(f"  • {e}")

        # 结论
        if score1 > score2 + 0.5:
            lines.append(f"\n💡 {dim_label}角度，{name1}更胜一筹。")
        elif score2 > score1 + 0.5:
            lines.append(f"\n💡 {dim_label}角度，{name2}更值得入手。")
        else:
            lines.append(f"\n💡 两款各有优势——{name1}综合更强，{name2}在某些方面也不差。建议根据你最关心的{('「'+dim_label+'」') if dim_label != '综合' else '点'}来选择。")

        return "\n".join(lines)

    def _generate_template(self, state: WorkflowState) -> str:
        top_n = 5 if state.visual_result else 3
        products = state.retrieved_products[:top_n]
        decisions = state.decision_results[:top_n]

        if not products:
            vr = state.visual_result or {}
            if vr.get("product_name"):
                brand_str = f"（{vr['brand']}）" if vr.get("brand") else ""
                if state.constraints.category:
                    return (
                        f"您拍的看起来是「{vr['product_name']}」{brand_str}，"
                        f"不过目前在「{state.constraints.category}」品类下没找到完全匹配的商品～"
                    )
                return (
                    f"您拍的看起来是「{vr['product_name']}」{brand_str}，"
                    f"可惜商品库里暂时还没有收录这款商品。要不要试试搜一下同类产品？"
                )
            msg = "抱歉，没有找到完全匹配您条件的商品。"
            if state.constraints.budget_max:
                msg += f" 试试放宽预算到 {state.constraints.budget_max * 1.5:.0f} 元左右？"
            return msg

        vr = state.visual_result or {}
        exact_pids = set(state.visual_matched_pids or [])
        exact_products = [p for p in products if p.get("product_id") in exact_pids]
        other_products = [p for p in products if p.get("product_id") not in exact_pids]
        exact_decisions = [d for d in decisions if d.get("product_id") in exact_pids]
        other_decisions = [d for d in decisions if d.get("product_id") not in exact_pids]

        lines = []

        # 视觉识图开场白
        if vr.get("product_name"):
            brand_str = f"（{vr['brand']}）" if vr.get("brand") else ""
            if exact_products:
                lines.append(f"您拍的看起来是「{vr['product_name']}」{brand_str}，就是这款～")
            else:
                lines.append(f"您拍的像是「{vr['product_name']}」{brand_str}，库内暂无同款，看看这些相近的～")
        elif vr.get("brand"):
            lines.append(f"认出是{vr['brand']}的产品，帮你挑了几款～")
        else:
            lines.append("帮你挑了几款～")

        # 同款优先
        display_list = list(zip(exact_products, exact_decisions)) if exact_products else []
        if exact_products and other_products:
            display_list += [(None, None)]
        display_list += list(zip(other_products, other_decisions))

        for prod, dec in display_list:
            if prod is None:
                lines.append("📌 同类还有这些：")
                continue

            brand = prod.get("brand", "")
            title = prod.get("title", "")
            price = prod.get("price", 0)
            name = f"{brand} {title}" if brand and not title.startswith(brand) else title
            if len(name) > 55:
                name = name[:55] + "…"
            lines.append(f"{name}  ¥{price:.0f}")

        return "\n".join(lines)
