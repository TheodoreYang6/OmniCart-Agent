"""V1 Router Agent — 意图识别、约束抽取、检索计划生成。

使用 Qwen LLM (intent_understanding capability) 从自然语言中抽取结构化购物需求。
"""

import json
import logging

from app.agents.base import BaseAgent
from app.model_gateway.gateway import get_model_gateway
from app.prompts.agent_prompts import build_router_prompt
from app.schemas.a2a import AgentCard
from app.schemas.workflow import Constraints, RetrievalPlan, SubQuery, WorkflowState

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"数码电子", "美妆护肤", "服饰运动", "食品饮料",
                    "家居用品", "母婴用品", "运动户外", "个护清洁"}


def _parse_qu_json(raw: str) -> dict:
    """解析 QU LLM 的 JSON 输出（兼容 markdown 围栏）。"""
    raw = (raw or "").strip()
    if "```" in raw:
        block = raw.split("```")[1]
        if block.startswith("json"):
            block = block[4:]
        raw = block.strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        return {}


async def aunderstand_query(query: str, context: str = "") -> dict:
    """QU V2 结构化理解（意图+约束+sub_queries 拆分）—— Router 与 OmniAgent 共用。

    缓存 key 维持 query 粒度（双链路同 query 零成本共享）；失败返回 {} 由调用方降级。
    """
    from app.core.cache import cached, make_key
    from app.core.config import REDIS_CACHE_TTL_REWRITE

    cache_key = make_key("router_intent", query)

    async def _do():
        gateway = get_model_gateway()
        prompt = build_router_prompt(context, query)
        raw = await gateway.chat("intent_understanding", prompt)
        parsed = _parse_qu_json(raw)
        if not parsed:
            logger.warning(f"QU LLM returned unparseable response: {raw[:200]}")
        return parsed or {}

    return await cached(cache_key, REDIS_CACHE_TTL_REWRITE, _do)


def validate_sub_queries(raw_sq) -> list[SubQuery]:
    """sub_queries 合并校验：非 list 丢弃；query 空跳过；坏 category 置 None；
    最多 5 条；仅 1 条视为不拆（清空）。校验失败降级 = 现状单查询行为。"""
    if not isinstance(raw_sq, list):
        return []
    out: list[SubQuery] = []
    for item in raw_sq[:5]:
        if not isinstance(item, dict) or not str(item.get("query") or "").strip():
            continue
        cat = item.get("category")
        if cat not in VALID_CATEGORIES:
            cat = None
        try:
            bh = float(item["budget_hint"]) if item.get("budget_hint") is not None else None
        except (TypeError, ValueError):
            bh = None
        out.append(SubQuery(role=str(item.get("role") or "")[:20],
                            query=str(item["query"]).strip()[:40],
                            category=cat, budget_hint=bh))
    return out if len(out) >= 2 else []


class RouterAgent(BaseAgent):

    def _build_card(self) -> AgentCard:
        return AgentCard(
            agent_id="router",
            name="Router Agent",
            description="意图识别 & 约束抽取 & 检索计划生成",
            capabilities=["intent_recognition", "constraint_extraction", "retrieval_planning"],
            input_schema={"user_query": "string"},
            output_schema={"intent": "string", "constraints": "object", "retrieval_plan": "object"},
        )

    async def execute(self, state: WorkflowState) -> WorkflowState:
        action = "intent_and_constraints"
        self._start_trace(state, action, state.user_query[:120])

        # 快速路径: 如果约束已由引导流程预填 (category + sub_category)，跳过 LLM
        c = state.constraints
        has_prefilled = bool(c.category and c.sub_category)

        # 规则解析作为可靠基础
        rule_result = _rule_based_parse(state.user_query)

        # 构建会话上下文（供 LLM 理解追问）
        context = self._build_session_context(state)

        # 欧米问了问题，用户回复简短肯定词 → 从 pending_question 推断搜索意图
        _AFFIRMATIVE = {"要", "好", "行", "可以", "对", "是的", "嗯", "买", "要的", "好的", "行的", "对啊", "是", "要买", "想看", "想买", "想看下", "看看吧", "试试", "来一个", "整一个", "搞一个"}
        if "欧米上一轮问了用户一个问题" in (context or "") and state.user_query.strip() in _AFFIRMATIVE:
            # 从 pending_question 提取品类关键词，替换 query
            import re
            pq_match = re.search(r"「(.+?)」", context)
            if pq_match:
                pending_q = pq_match.group(1)
                # 用 pending_question 作为实际搜索 query
                state.user_query = pending_q
                rule_result = _rule_based_parse(pending_q)

        # lite 档或预填约束：跳过 LLM，只用规则（P2-1：state.mode 替代 [FAST_MODE] 字符串）
        fast_mode = state.mode == "lite"
        llm_result = {}
        if not has_prefilled and not fast_mode:
            try:
                llm_result = await aunderstand_query(state.user_query, context)
            except Exception as e:
                logger.warning(f"Router LLM failed, falling back to rules: {e}")

        # 合并：LLM 增强规则，但高置信度规则意图不被 LLM 覆盖
        llm_filtered = {k: v for k, v in llm_result.items() if v}
        merged = {**rule_result, **llm_filtered}

        # 品类安全校验: LLM 返回的 category 必须在已知品类中, 否则回退到规则结果
        # 过滤 LLM 返回的字符串 "null" / "none" / "" 等无效值
        llm_filtered = {k: v for k, v in llm_filtered.items()
                        if v and str(v).lower() not in ("null", "none", "")}
        llm_cat = llm_filtered.get("category")
        if llm_cat and llm_cat not in VALID_CATEGORIES:
            logger.warning(f"Router LLM returned invalid category '{llm_cat}', falling back to rule: {rule_result.get('category')}")
            merged["category"] = rule_result.get("category")  # None is fine — no category filter

        # 规则强检测的意图不被 LLM 覆盖 (词库匹配比 LLM 语义判断更可靠)
        # compare 同属词库强检测（"对比/比较/vs"）：不保护会被 LLM 降级为 recommend，
        # 导致动态编排的 compare_retrieval 多目标检索永远不触发（灰度手测实锤）
        # QU V2: bundle/replenish 同为强词表（"搭一套/再来一"）；gift/knowledge 词易误判，允许 LLM 纠正
        HIGH_CONFIDENCE_INTENTS = {"chitchat", "risk_check", "shop_action", "compare",
                                   "bundle", "replenish"}
        # 规则强检测的意图不被 LLM 覆盖
        if rule_result.get("intent") in HIGH_CONFIDENCE_INTENTS:
            merged["intent"] = rule_result["intent"]
            if rule_result["intent"] == "chitchat":
                merged["category"] = None
                merged["sub_category"] = None
                merged["budget_max"] = None
                merged["retrieval_channels"] = []
        # LLM 不能把明确的购物意图降级为闲聊 — 但仅当规则解析有明确购物信号时才拦截
        # (规则默认 intent="recommend"，无信号时 LLM 的 chitchat 判断应生效)
        if rule_result.get("intent") == "recommend" and merged.get("intent") == "chitchat":
            rule_has_signal = bool(
                rule_result.get("category")
                or rule_result.get("budget_max")
                or (rule_result.get("spec_keywords") and len(rule_result.get("spec_keywords", [])) >= 2)
                or rule_result.get("must_have")
                or state.image_url  # 有图片→用户想搜商品，不是闲聊
            )
            if rule_has_signal:
                merged["intent"] = "recommend"
            # 否则保持 LLM 的 chitchat 判断

        # 如果引导流程预填了约束，直接沿用，不被规则/LLM覆盖
        if has_prefilled:
            merged["category"] = c.category
            merged["sub_category"] = c.sub_category
            if c.budget_max is not None:
                merged["budget_max"] = c.budget_max
            if c.budget_min is not None:
                merged["budget_min"] = c.budget_min
        # Profile 偏好中的避雷标签始终合并（不被 LLM 覆盖）
        prefill_avoid = getattr(c, "exclude_tags", None) or []
        if prefill_avoid:
            merged["avoid"] = list(set((merged.get("avoid") or []) + prefill_avoid))

        state.intent = merged.get("intent", "recommend")
        # QU V2: gift_profile 仅 gift 意图透传（dict 且非空）
        gift_profile = merged.get("gift_profile")
        if state.intent != "gift" or not isinstance(gift_profile, dict) or not gift_profile:
            gift_profile = None
        state.constraints = Constraints(
            category=merged.get("category"),
            sub_category=merged.get("sub_category"),
            budget_max=merged.get("budget_max"),
            budget_min=merged.get("budget_min"),
            scenario=merged.get("scenario"),
            scenario_keywords=merged.get("scenario_keywords") or [],
            spec_keywords=merged.get("spec_keywords") or [],
            must_tags=merged.get("must_have") or [],
            exclude_tags=merged.get("avoid") or [],
            gift_profile=gift_profile,
        )
        if gift_profile:
            # 送礼视角注入 Response（prompt 规则：上下文含[送礼场景]时以送礼视角组织）
            state.context_prompt = (state.context_prompt or "") + (
                f"\n[送礼场景] 对象:{gift_profile.get('recipient', '未知')} "
                f"场合:{gift_profile.get('occasion', '未知')}")

        channels = merged.get("retrieval_channels", ["text", "review"])
        if state.intent == "chitchat":
            channels = []  # 闲聊不需要检索
        else:
            if "text" not in channels:
                channels.insert(0, "text")
            if "review" not in channels:
                channels.append("review")
        if merged.get("need_policy_check"):
            if "policy" not in channels:
                channels.append("policy")

        state.retrieval_plan = RetrievalPlan(
            channels=channels,
            category=merged.get("category"),
            sub_category=merged.get("sub_category"),
            top_k=10 if merged.get("intent") == "compare" else (8 if merged.get("avoid") else 5),
            priority="coverage" if merged.get("intent") == "compare" else "balanced",
            sub_queries=validate_sub_queries(merged.get("sub_queries")),
        )

        llm_used = "rule+llm" if llm_result else "rule_only"
        summary = f"[{llm_used}] intent={state.intent}, cat={state.constraints.category}, budget={state.constraints.budget_max}, channels={channels}"
        return self._finish_trace(state, summary)

    def _parse_llm(self, raw: str) -> dict:
        """解析 LLM JSON 输出"""
        raw = raw.strip()
        if "```" in raw:
            block = raw.split("```")[1]
            if block.startswith("json"):
                block = block[4:]
            raw = block.strip()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return {}

    def _build_session_context(self, state: WorkflowState) -> str:
        """从 context_snapshot 构建上下文段落，注入 Router prompt。

        包含: 约束、欧米待答问题、上一轮对话、最近3轮摘要。
        """
        if not state.conversation_id:
            return ""
        try:
            from app.services.conversation_service import get_conversation_service
            svc = get_conversation_service()
            snapshot = svc.get_context_snapshot_sync(state.conversation_id)
            if not snapshot:
                return ""
            parts = []
            acc = snapshot.get("constraints", {})
            last_q = snapshot.get("last_query", "")
            last_intent = snapshot.get("last_intent", "")
            last_answer = snapshot.get("last_answer", "")
            pending_q = snapshot.get("pending_question", "")
            products = snapshot.get("last_products", [])

            # 欧米待答问题 (最高优先级 — 帮助 LLM 理解用户可能在回答什么)
            if pending_q and pending_q != last_q:
                parts.append(f"⚠️ 欧米上一轮问了用户一个问题: 「{pending_q}」")
                parts.append("→ 用户当前回复很可能是在回答这个问题。请从问题内容推断意图和品类，忽略下方旧话题约束。")

            if last_q and last_q != state.user_query:
                parts.append(f"上一轮用户说了: 「{last_q}」")
            if last_answer:
                answer_short = last_answer[-200:] if len(last_answer) > 200 else last_answer
                parts.append(f"上一轮欧米回复: 「{answer_short}」")
            if last_intent:
                parts.append(f"上一轮意图: {last_intent}")
            if acc.get("category"):
                parts.append(f"当前话题品类: {acc['category']}")
            if acc.get("sub_category"):
                # 仅当当前 query 仍包含子品类关键词时才继承，防止话题已切换但子品类锁死
                from app.decision.rules import detect_sub_category
                cur_sub = detect_sub_category(state.user_query, acc.get("category"))
                if cur_sub:
                    parts.append(f"当前话题子品类: {cur_sub}")
                # 否则不注入旧子品类，让 LLM 自由判断
            if acc.get("budget_max") is not None:
                parts.append(f"当前预算上限: ¥{acc['budget_max']}")
            if acc.get("scenario"):
                parts.append(f"当前场景: {acc['scenario']}")

            # 结构化商品摘要 (供指代解析)
            if products:
                product_summary = "、".join(
                    f"#{i+1} {p.get('brand','')} {p.get('title','')[:30]}"
                    if isinstance(p, dict)
                    else f"#{i+1} {p}"
                    for i, p in enumerate(products[:3])
                )
                parts.append(f"上一轮推荐商品: {product_summary}")

            # 最近多轮摘要
            recent = snapshot.get("recent_turns", [])
            if isinstance(recent, list) and len(recent) > 1:
                prev_turns = recent[:-1]  # exclude current turn
                if prev_turns:
                    parts.append(f"最近{len(prev_turns)}轮对话摘要:")
                    for i, t in enumerate(prev_turns[-2:]):
                        uq = t.get("user_query", "")[:80]
                        aa = t.get("assistant_answer", "")[:80]
                        parts.append(f"  第{i+1}轮 — 用户: 「{uq}」→ 欧米: 「{aa}」")

            if parts:
                return "## 对话上下文\n" + "\n".join(f"- {p}" for p in parts) + "\n"
            return ""
        except Exception:
            return ""


def _rule_based_parse(query: str) -> dict:
    """规则兜底 — 不依赖 LLM 的约束解析。

    注意: 此函数无法访问上下文，对于单字肯定回复("要""好"等)无法推断意图。
    但返回 intent="recommend" 而不是 "chitchat"，让 LLM (非Mock模式) 或
    MockChat 智能推断覆盖。当 LLM 不可用时，短文本默认走推荐流程。
    """
    import re
    q = query.lower()
    result = {
        "intent": "recommend",
        "category": None,
        "sub_category": None,
        "budget_max": None,
        "budget_min": None,
        "scenario": None,
        "scenario_keywords": [],
        "spec_keywords": [],
        "must_have": [],
        "avoid": [],
        "need_visual": False,
        "need_policy_check": False,
        "need_compatibility_check": False,
        "retrieval_channels": ["text", "review"],
    }

    # 欧米问了用户一个问题，用户回答"要/好/行" → 从问题中提取搜索意图
    # 在 _build_session_context 中已传递 pending_question，此处做规则兜底
    # (实际替换逻辑在 execute() 中根据上下文完成)

    # 词库快速拦截: 命中→直接chitchat省LLM调用, 未命中→LLM Router判断
    chitchat_patterns = [
        # 纯礼貌
        "你好", "嗨", "哈喽", "hello", "hi", "在吗", "早", "早上好", "下午好", "晚上好",
        "谢谢", "感谢", "多谢", "拜拜", "再见", "晚安", "回头见",
        # 问身份/能力
        "你是谁", "你叫什么", "你的名字", "你是什么", "介绍一下自己",
        "你能做什么", "你会什么", "你有什么功能", "你能干嘛", "你能干什么",
        "你是AI", "你是机器人", "你是人工",
        # AI/助手相关闲聊
        "豆包", "欧米", "豆包和", "你和豆包", "豆包是谁", "claude", "gpt", "chatgpt",
        "你是哪个模型", "模型", "大模型", "基于什么",
        # 日常情感
        "想你", "爱你", "喜欢你", "摸摸", "抱抱", "贴贴",
        "好累", "好困", "好饿", "好无聊", "好烦", "好难过", "好开心",
        "无聊", "累了", "困了", "饿了", "烦死了", "郁闷", "崩溃",
        "吃饭", "想吃", "想喝", "喝奶茶", "喝咖啡",
        "天气", "心情", "开心", "难过", "烦", "郁闷",
        "聊天", "笑话", "讲笑话", "唱歌", "故事", "讲故事", "背诗",
        # 测试/开发相关
        "测试", "test", "你能收到", "听到吗", "在不在",
        # 单字闲聊 (不要误判为商品搜索)
        "哈哈", "呵呵", "嘿嘿", "哦", "嗯", "啊", "哎",
        # emoji/符号类
        "？", "？？", "？？？", "。。。", "...", "。", ".", "!", "！",
    ]
    # "喜欢XX品牌"可能被个别模式(如"苹果")误判 → 含品牌/品类词的跳过
    chitchat_hit = any(w in q for w in chitchat_patterns)
    if chitchat_hit:
        has_product_context = any(w in q for w in ["喜欢", "想要", "买", "推荐", "品牌", "降噪",
            "耳机", "手机", "衣服", "鞋", "精华", "面霜", "数码", "护肤", "充电", "健身"])
        if not has_product_context:
            result["intent"] = "chitchat"
        result["category"] = None
        result["retrieval_channels"] = []
        return result

    # Intent
    # 购物车操作 (最高优先级，避免被其他意图误判)
    if any(w in q for w in ["加入购物车", "加到购物车", "加购物车", "下单", "结算", "结账",
                              "删掉第", "删除第", "去掉第", "移除第", "清空购物车",
                              "地址用默认", "默认地址"]):
        result["intent"] = "shop_action"
        result["retrieval_channels"] = []
    elif any(w in q for w in ["搭一套", "搭配一套", "成套", "一整套", "配齐", "搭配一身"]):
        result["intent"] = "bundle"
    elif any(w in q for w in ["再来一", "回购", "补货"]) or ("上次买" in q and "再" in q):
        result["intent"] = "replenish"
    elif any(w in q for w in ["对比", "比较", "vs", "哪个好", "选哪个"]):
        result["intent"] = "compare"
    elif any(w in q for w in ["风险", "副作用", "安全", "过敏", "发热", "爆炸"]):
        result["intent"] = "risk_check"
        result["retrieval_channels"] = ["text", "review"]
    elif any(w in q for w in ["兼容", "适配", "支持", "能不能用", "能不能配"]):
        result["intent"] = "compatibility_check"
        result["need_compatibility_check"] = True
    elif any(w in q for w in ["替代", "代替", "换一个", "其他", "别的", "类似"]):
        result["intent"] = "alternative"
    elif ("送" in q and any(w in q for w in ["礼物", "生日礼", "情人节", "母亲节", "父亲节"])) \
            or any(w in q for w in ["送女朋友", "送男朋友", "送爸妈", "送妈妈", "送爸爸"]):
        # gift 词易误判（"送货"等），仅作规则默认，不进高置信，允许 LLM 纠正
        result["intent"] = "gift"
    elif any(w in q for w in ["什么区别", "有啥区别", "怎么选", "什么是", "科普一下"]):
        # knowledge 同理仅规则默认
        result["intent"] = "knowledge"

    # Category / Budget / Scenario — 统一使用共享规则模块
    from app.decision.rules import detect_category, detect_budget, detect_scenario, detect_sub_category

    result["category"] = detect_category(query)
    result["sub_category"] = detect_sub_category(query, result["category"])
    result["budget_max"] = detect_budget(query)
    result["scenario"] = detect_scenario(query)

    # 排除关键词: 严格匹配 "不要XX"/"不想买XX"/"排除XX"
    # 常见的非品牌噪音词 — 被正则抓到但不应作为避雷标签
    _NOISE_TAGS = {"东西", "商品", "这些", "那些", "这个", "那个", "什么", "一点",
                   "贵的", "便宜的", "太贵", "太便宜", "国产", "进口", "的"}
    exclude_patterns = [
        r'不要\s*([^\s，。,]+)',      # "不要小米" "不要含酒精的"
        r'不想[买要]\s*([^\s，。,]+)', # "不想买索尼"
        r'排除\s*([^\s，。,]+)',      # "排除华为"
        r'除了\s*([^\s，。，]+)(?:以外|之外|不要[买要]?)',  # "除了兰蔻以外/不要" (排除)
    ]
    for pat in exclude_patterns:
        for m in re.finditer(pat, q):
            tag = m.group(1).strip().rstrip('，。、的')
            # 严格门槛: ≥2字符 且 不是无意义噪音词
            if tag and len(tag) >= 2 and tag not in _NOISE_TAGS and tag not in result["avoid"]:
                result["avoid"].append(tag)

    # 展开品牌中英文别名 (用户说"不要Nike" → 同时排除 "Nike" 和 "耐克")
    from app.decision.rules import expand_brand_aliases
    result["avoid"] = expand_brand_aliases(result["avoid"])

    return result
