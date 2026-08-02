import hashlib
import json
import random
import re


class MockChat:
    """Mock chat model — 轻量规则引擎，不调用 API，模拟 LLM 输出。

    按 capability 区分：
    - intent_understanding → 返回 JSON (Router Agent 消费)
    - chat_generation → 返回自然语言 (Response Agent 消费)
    """

    # ---- chitchat 检测词 ----
    _CHITCHAT_PATTERNS = [
        "你好", "嗨", "哈喽", "hello", "hi", "在吗", "谢谢", "感谢", "多谢",
        "拜拜", "再见", "晚安", "你是谁", "你叫什么", "你的名字", "你能做什么",
        "你会什么", "想你", "爱你", "喜欢你", "好累", "好困", "好饿", "饿了",
        "好无聊", "无聊", "累了", "困了", "天气", "心情", "开心", "难过",
        "烦", "郁闷", "聊天", "笑话", "讲笑话", "唱歌", "故事",
        "吃饭", "想吃", "想喝", "喝奶茶", "喝咖啡",
    ]

    # ---- 品类关键词映射 ----
    _CATEGORY_KEYWORDS = {
        # 新品类关键词更具体，放在前面优先匹配
        "母婴用品": ["纸尿裤", "尿不湿", "奶瓶", "奶嘴", "婴儿", "宝宝", "孕妇", "辅食",
                    "安全座椅", "吸奶器", "绘本", "积木", "母婴"],
        "个护清洁": ["洗发水", "护发素", "沐浴露", "身体乳", "牙膏", "牙刷", "洗衣液",
                    "洗洁精", "消毒液", "剃须刀", "脱毛仪", "吹风机", "卷发棒", "直发器", "卫生巾"],
        "运动户外": ["帐篷", "睡袋", "登山杖", "瑜伽垫", "哑铃", "跳绳", "篮球", "足球",
                    "球拍", "泳镜", "泳衣", "滑板", "轮滑", "露营", "骑行"],
        "家居用品": ["保温杯", "四件套", "枕头", "被子", "毛巾", "收纳", "锅", "餐具",
                    "砧板", "台灯", "香薰", "花瓶", "窗帘", "地毯", "挂钩"],
        "食品饮料": ["零食", "吃的", "好吃", "饿了", "想吃", "喝", "饮料", "咖啡", "牛奶",
                    "辣条", "薯片", "饼干", "巧克力", "糖果", "坚果", "方便面", "泡面",
                    "香喷喷", "酥脆", "软糯", "酸甜", "蛋糕", "面包"],
        "数码电子": ["耳机", "手机", "充电", "蓝牙", "平板", "笔记本", "电脑", "手表",
                    "音箱", "数据线", "降噪", "快充"],
        "美妆护肤": ["口红", "唇釉", "粉底", "精华", "面霜", "面膜", "防晒", "卸妆",
                    "化妆", "美妆", "护肤", "丝绒", "哑光"],
        "服饰运动": ["鞋", "衣服", "T恤", "裤子", "运动", "跑鞋", "瑜伽", "登山",
                    "羽绒服"],
    }

    # ---- 品类关键词 → sub_category 映射 ----
    _SUB_CATEGORY_MAP = {
        "零食": "零食/膨化", "吃的": "零食/膨化", "辣条": "零食/膨化", "薯片": "零食/膨化",
        "饼干": "零食/膨化", "巧克力": "零食/膨化", "糖果": "零食/膨化", "坚果": "零食/膨化",
        "方便面": "零食/膨化", "泡面": "零食/膨化", "蛋糕": "零食/膨化", "面包": "零食/膨化",
        "饮料": "碳酸饮料", "咖啡": "咖啡/速溶", "牛奶": "牛奶",
        "耳机": "真无线耳机", "手机": "智能手机", "平板": "平板电脑",
        "口红": "口红", "唇釉": "口红", "粉底": "粉底液", "精华": "精华",
        "面霜": "面霜", "面膜": "面膜", "跑步": "跑步鞋", "运动": "运动鞋",
    }

    # ---- 单字肯定回复 (需从上下文推断意图) ----
    _AFFIRMATIVE_WORDS = {"要", "好", "行", "可以", "嗯", "是的", "对", "想", "买"}

    def generate(self, prompt: str, system: str = "") -> str:
        """根据 prompt 内容智能返回 Mock 结果。"""

        # 检测是否为 Router JSON 请求
        if '当前支持的品类' in prompt or '"intent"' in prompt or 'intent_understanding' in system:
            return self._generate_intent_json(prompt)

        # 执行计划编排（LLM Planner）→ 确定性计划 JSON（MOCK 全链可演示/可测）
        if '执行计划编排器' in prompt:
            return self._generate_plan_json(prompt)

        # 关键词提取 / 通用生成 → 直接返回用户查询中的关键词
        if '关键词提取' in prompt or '搜索关键词' in prompt:
            return self._extract_query(prompt)

        # 闲聊生成
        return self._generate_chitchat(prompt)

    @staticmethod
    def _generate_plan_json(prompt: str) -> str:
        """确定性计划：query 含「订单」走工具+回答，否则标准检索链。"""
        if "订单" in prompt:
            return json.dumps({
                "steps": [
                    {"id": "s1", "capability": "tool:order.list", "depends_on": []},
                    {"id": "s2", "capability": "response", "depends_on": ["s1"]},
                ],
                "rationale": "mock: 查订单后回答",
            }, ensure_ascii=False)
        return json.dumps({
            "steps": [
                {"id": "s1", "capability": "retrieval", "depends_on": []},
                {"id": "s2", "capability": "reranker", "depends_on": ["s1"]},
                {"id": "s3", "capability": "evidence_check", "depends_on": ["s2"]},
                {"id": "s4", "capability": "decision", "depends_on": ["s3"]},
                {"id": "s5", "capability": "response", "depends_on": ["s4"]},
            ],
            "rationale": "mock: 标准检索链",
        }, ensure_ascii=False)

    # ================================================================
    # Intent JSON (Router)
    # ================================================================

    def _generate_intent_json(self, prompt: str) -> str:
        # 提取用户查询 — prompt 的最后部分是用户输入
        query = self._extract_query(prompt)
        q_lower = query.lower().strip()

        # 1. 查 chitchat
        for pat in self._CHITCHAT_PATTERNS:
            if pat in q_lower:
                return json.dumps({
                    "intent": "chitchat", "category": None, "sub_category": None,
                    "budget_max": None, "budget_min": None, "scenario": None,
                    "scenario_keywords": [], "spec_keywords": [], "must_have": [],
                    "avoid": [], "need_visual": False, "need_policy_check": False,
                    "retrieval_channels": [],
                }, ensure_ascii=False)

        # 2. 单字肯定回复 → 从上一轮欧米回复推断品类
        if q_lower in self._AFFIRMATIVE_WORDS:
            return self._infer_from_last_answer(prompt, q_lower)

        # 2.5 对比意图（与 rule_based_parse 对齐，避免 MOCK 下 compare 被降级为 recommend）
        is_compare = any(w in q_lower for w in ["对比", "比较", "vs", "哪个好", "选哪个"])

        # 3. 提取品类/预算
        cat, sub = self._detect_category(query)
        budget = self._detect_budget(query)

        # 3.5 QU V2 确定性脚本：bundle/replenish/knowledge/gift（MOCK 全链可演示/可测）
        if any(w in query for w in ("搭一套", "搭配一套", "搭配", "配齐")) and not is_compare:
            base = {"intent": "bundle", "category": cat or "服饰运动", "sub_category": sub,
                    "budget_max": budget, "budget_min": None, "scenario": None,
                    "scenario_keywords": [], "spec_keywords": ["舒适", "百搭"],
                    "must_have": [], "avoid": [], "retrieval_channels": ["text", "review"],
                    "rewritten_query": "休闲穿搭",
                    "sub_queries": [
                        {"role": "上衣", "query": "休闲上衣", "category": "服饰运动",
                         "budget_hint": round(budget * 0.35) if budget else None},
                        {"role": "裤子", "query": "休闲长裤", "category": "服饰运动",
                         "budget_hint": round(budget * 0.35) if budget else None},
                        {"role": "鞋", "query": "休闲鞋", "category": "服饰运动",
                         "budget_hint": round(budget * 0.3) if budget else None},
                    ]}
            return json.dumps(base, ensure_ascii=False)
        if any(w in query for w in ("再来一", "回购")) or ("上次买" in query and "再" in query):
            return json.dumps({
                "intent": "replenish", "category": cat, "sub_category": sub,
                "budget_max": budget, "budget_min": None, "scenario": None,
                "scenario_keywords": [], "spec_keywords": ["好用"], "must_have": [],
                "avoid": [], "retrieval_channels": ["text", "review"],
                "rewritten_query": sub or query[:12],
            }, ensure_ascii=False)
        if any(w in query for w in ("什么区别", "有啥区别", "怎么选", "科普一下")):
            return json.dumps({
                "intent": "knowledge", "category": cat, "sub_category": sub,
                "budget_max": None, "budget_min": None, "scenario": None,
                "scenario_keywords": [], "spec_keywords": ["参数", "原理"], "must_have": [],
                "avoid": [], "retrieval_channels": ["text", "review"],
                "rewritten_query": query[:12],
            }, ensure_ascii=False)
        if "送" in query and any(w in query for w in ("礼物", "生日", "母亲节", "情人节")):
            recipient = "妈妈" if "妈" in query else ("女朋友" if "女朋友" in query else "好友")
            occasion = "母亲节" if "母亲节" in query else ("生日" if "生日" in query else "送礼")
            return json.dumps({
                "intent": "gift", "category": cat, "sub_category": sub,
                "budget_max": budget, "budget_min": None, "scenario": None,
                "scenario_keywords": [], "spec_keywords": ["高颜值", "送礼体面"],
                "must_have": [], "avoid": [], "retrieval_channels": ["text", "review"],
                "rewritten_query": query[:12],
                "gift_profile": {"recipient": recipient, "occasion": occasion},
            }, ensure_ascii=False)

        return json.dumps({
            "intent": "compare" if is_compare else "recommend",
            "category": cat, "sub_category": sub,
            "budget_max": budget, "budget_min": None,
            "scenario": None, "scenario_keywords": [],
            "spec_keywords": [], "must_have": [], "avoid": [],
            "need_visual": False, "need_policy_check": False,
            "retrieval_channels": ["text", "review"],
        }, ensure_ascii=False)

    def _extract_query(self, prompt: str) -> str:
        """从 prompt 中提取用户输入文本。支持多种 prompt 格式。"""
        # 格式1: Router prompt → ## 用户输入\n{query}
        m = re.search(r'## 用户输入\s*\n(.+?)\n', prompt, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 格式2: 关键词提取 prompt → 用户说：{query}
        m = re.search(r'用户说：(.+?)(?:\n|关键词)', prompt)
        if m:
            return m.group(1).strip()
        # 格式3: 回复 prompt → 回复用户: {query}
        m = re.search(r'回复用户[：:]\s*(.+?)(?:\n|$)', prompt)
        if m:
            return m.group(1).strip()
        # Fallback: 取最后一行有意义的文本
        lines = [l for l in prompt.strip().split('\n') if l.strip() and not l.startswith('#')]
        return lines[-1].strip() if lines else ""

    def _infer_from_last_answer(self, prompt: str, query: str) -> str:
        """单字肯定回复 → 从上下文推断品类线索。

        优先检查 pending_question (显式标记的问句)，
        其次检查 欧米回复 全文。
        """
        # 1. 优先: pending_question
        m = re.search(r'欧米上一轮问了用户一个问题.*?「(.+?)」', prompt, re.DOTALL)
        search_text = m.group(1) if m else ""

        # 2. 次选: 上一轮欧米回复
        if not search_text:
            m = re.search(r'上一轮欧米回复.*?「(.+?)」', prompt, re.DOTALL)
            search_text = m.group(1) if m else ""

        if not search_text:
            return json.dumps({
                "intent": "recommend", "category": None, "sub_category": None,
                "budget_max": None, "budget_min": None, "scenario": None,
                "scenario_keywords": [], "spec_keywords": [], "must_have": [],
                "avoid": [], "need_visual": False, "need_policy_check": False,
                "retrieval_channels": ["text", "review"],
            }, ensure_ascii=False)

        search_lower = search_text.lower()

        # 扫描品类关键词
        for cat, keywords in self._CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in search_lower:
                    sub = self._SUB_CATEGORY_MAP.get(kw)
                    return json.dumps({
                        "intent": "recommend",
                        "category": cat,
                        "sub_category": sub,
                        "budget_max": None, "budget_min": None,
                        "scenario": None, "scenario_keywords": [],
                        "spec_keywords": [kw] if kw else [],
                        "must_have": [], "avoid": [],
                        "need_visual": False, "need_policy_check": False,
                        "retrieval_channels": ["text", "review"],
                    }, ensure_ascii=False)

        return json.dumps({
            "intent": "recommend", "category": None, "sub_category": None,
            "budget_max": None, "budget_min": None, "scenario": None,
            "scenario_keywords": [], "spec_keywords": [], "must_have": [],
            "avoid": [], "need_visual": False, "need_policy_check": False,
            "retrieval_channels": ["text", "review"],
        }, ensure_ascii=False)

    def _detect_category(self, query: str) -> tuple:
        """品类检测 — 返回 (category, sub_category) 或 (None, None)。"""
        q_lower = query.lower()
        for cat, keywords in self._CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in q_lower:
                    sub = self._SUB_CATEGORY_MAP.get(kw)
                    return cat, sub
        return None, None

    def _detect_budget(self, query: str) -> int | None:
        """预算检测 — 返回数字或 None。"""
        m = re.search(r'(\d+)\s*[块元]', query)
        if m:
            return int(m.group(1))
        m = re.search(r'[以不超]{1,2}\s*(\d+)', query)
        if m:
            return int(m.group(1))
        return None

    # ================================================================
    # Chitchat (Response)
    # ================================================================

    def _generate_chitchat(self, prompt: str) -> str:
        query = self._extract_query(prompt)
        q = query.lower()

        if any(w in q for w in ["你好", "嗨", "哈喽", "hello", "hi", "在吗"]):
            return "嗨喵～我是欧米，你的多模态购物智能体！想买什么直接告诉我就好！"
        if any(w in q for w in ["你是谁", "你叫什么", "你的名字"]):
            return "我是欧米，你的专属多模态购物智能体！专精商品推荐与对比评测，带你探索未来购物新范式喵～"
        if any(w in q for w in ["你能做什么", "你会什么", "功能"]):
            return "我能帮你推荐商品、拍照识别、对比分析、直接加购！想试试哪个？"
        if any(w in q for w in ["谢谢", "感谢"]):
            return "不客气~ 随时找我！"
        if any(w in q for w in ["想你", "爱你", "喜欢你"]):
            return "哎呀我也想你呀～欧米一直在等你来逛呢！想买点什么？"
        if any(w in q for w in ["好累", "累了", "好困", "困了", "好饿", "饿了", "吃饭", "想吃"]):
            return "辛苦啦！饿了可不能拖～要不要一起挑点香喷喷的零食？酥脆的、软糯的、酸酸甜甜的……欧米都帮你盯着呢！"
        if any(w in q for w in ["无聊", "好无聊"]):
            return "无聊的时候最适合逛好东西啦！要不要欧米给你推荐点新奇有趣的小玩意儿？"

        return f"诶？没太看懂～不过欧米更擅长帮你挑商品！想买什么呀？直接说就行～"


class MockEmbedding:
    """Mock embedding — returns deterministic pseudo-vectors from text hash.

    NOT semantically meaningful. Used only for running the retriever pipeline
    during development when Qwen API is unavailable.
    """

    DIM = 128

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            rng = random.Random(seed)
            vectors.append([rng.random() for _ in range(self.DIM)])
        return vectors


def mock_vision_parse(image_url: str) -> dict | None:
    """Mock visual parse for development / fallback testing.

    Returns a plausible VisualResult-like dict for the multimodal fallback chain.
    """
    return {
        "product_name": "Unknown Product",
        "brand": "Unknown Brand",
        "category": None,
        "price": None,
        "specs": None,
        "highlights": [],
        "confidence": 0.3,
    }
