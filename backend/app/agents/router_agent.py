"""V1 Router Agent — 意图识别、约束抽取、检索计划生成。

使用 Qwen LLM (intent_understanding capability) 从自然语言中抽取结构化购物需求。
"""

import json

from app.agents.base import BaseAgent
from app.model_gateway.gateway import get_model_gateway
from app.schemas.a2a import AgentCard
from app.schemas.workflow import Constraints, RetrievalPlan, WorkflowState

_ROUTER_PROMPT = """你是一个购物决策路由Agent。分析用户的购物需求，提取结构化信息。

## 任务
从用户输入中提取以下信息，只输出JSON，不要多余内容：

{
  "intent": "chitchat|recommend|compare|risk_check|compatibility_check|alternative",
  "category": "数码电子|美妆护肤|服饰运动|食品饮料|null（chitchat时必须为null）",
  "sub_category": "如 真无线耳机、精华、跑步鞋、咖啡 等，不确定则为null",
  "budget_max": 最高预算金额(数字)或null,
  "budget_min": 最低预算金额(数字)或null,
  "scenario": "commute|business_trip|flight|sport|outdoor|desk|travel|null",
  "must_have": [必须满足的关键词列表],
  "avoid": [要避免的关键词列表],
  "need_visual": true或false,
  "need_policy_check": true或false,
  "need_compatibility_check": true或false,
  "retrieval_channels": ["text","review","policy"] 中至少包含"text"
}

## 用户输入
{query}

## 当前支持的品类
- 数码电子：手机、耳机、笔记本、平板、手表、音箱、充电宝等
- 美妆护肤：精华、面霜、防晒、洁面、面膜、粉底等
- 服饰运动：T恤、跑鞋、羽绒服、瑜伽裤、登山鞋等
- 食品饮料：咖啡、零食、饮料、保健品、方便食品等

请输出JSON："""


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

    def execute(self, state: WorkflowState) -> WorkflowState:
        action = "intent_and_constraints"
        self._start_trace(state, action, state.user_query[:120])

        # 规则解析作为可靠基础
        rule_result = _rule_based_parse(state.user_query)

        # 尝试 LLM 增强（失败时静默降级到规则结果）
        llm_result = {}
        try:
            gateway = get_model_gateway()
            prompt = _ROUTER_PROMPT.format(query=state.user_query)
            raw = gateway.chat("intent_understanding", prompt)
            llm_result = self._parse_llm(raw)
        except Exception:
            pass  # LLM 不可用时静默降级

        # 合并：规则优先（category/budget/intent 以规则为准，LLM 仅补充 sub_category/scenario/tags）
        llm_filtered = {k: v for k, v in llm_result.items() if v}
        merged = {**llm_filtered, **rule_result}  # 规则覆盖 LLM，确保品类/预算/意图不被 LLM 带偏

        state.intent = merged.get("intent", "recommend")
        state.constraints = Constraints(
            category=merged.get("category"),
            sub_category=merged.get("sub_category"),
            budget_max=merged.get("budget_max"),
            budget_min=merged.get("budget_min"),
            scenario=merged.get("scenario"),
            must_tags=merged.get("must_have") or [],
            exclude_tags=merged.get("avoid") or [],
        )

        channels = merged.get("retrieval_channels", ["text"])
        if state.intent == "chitchat":
            channels = []  # 闲聊不需要检索
        elif "text" not in channels:
            channels.insert(0, "text")
        if merged.get("need_policy_check"):
            if "policy" not in channels:
                channels.append("policy")
        if merged.get("intent") in ("risk_check",):
            if "review" not in channels:
                channels.insert(1, "review")

        state.retrieval_plan = RetrievalPlan(
            channels=channels,
            category=merged.get("category"),
            sub_category=merged.get("sub_category"),
            top_k=10 if merged.get("intent") == "compare" else 5,
            priority="coverage" if merged.get("intent") == "compare" else "balanced",
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


def _rule_based_parse(query: str) -> dict:
    """规则兜底 — 不依赖 LLM 的约束解析"""
    result = {
        "intent": "recommend",
        "category": None,
        "sub_category": None,
        "budget_max": None,
        "budget_min": None,
        "scenario": None,
        "must_have": [],
        "avoid": [],
        "need_visual": False,
        "need_policy_check": False,
        "need_compatibility_check": False,
        "retrieval_channels": ["text"],
    }

    q = query.lower()

    # 闲聊检测（问候/自我介绍/能力询问/感谢/告别）→ 不走商品检索
    chitchat_patterns = [
        "你好", "嗨", "哈喽", "hello", "hi", "在吗", "在不在",
        "你是谁", "你叫什么", "你的名字", "介绍自己", "自我介绍",
        "你能做什么", "你会什么", "你有什么功能", "你能帮我什么", "你怎么用",
        "谢谢", "感谢", "多谢", "辛苦了", "拜拜", "再见", "晚安", "回头见",
        "什么是", "怎么用", "如何使用", "怎么操作",
    ]
    if any(w in q for w in chitchat_patterns):
        result["intent"] = "chitchat"
        result["category"] = None
        result["retrieval_channels"] = []
        return result

    # Intent
    if any(w in q for w in ["对比", "比较", "vs", "哪个好", "选哪个"]):
        result["intent"] = "compare"
    elif any(w in q for w in ["风险", "副作用", "安全", "过敏", "发热", "爆炸"]):
        result["intent"] = "risk_check"
        result["retrieval_channels"] = ["text", "review"]
    elif any(w in q for w in ["兼容", "适配", "支持", "能不能用", "能不能配"]):
        result["intent"] = "compatibility_check"
        result["need_compatibility_check"] = True
    elif any(w in q for w in ["替代", "代替", "换一个", "其他", "别的", "类似"]):
        result["intent"] = "alternative"

    # Category
    cat_rules = [
        # 数码电子（新增：电脑配件、智能家电、游戏设备、摄影器材、办公数码）
        ("数码电子", [
            "手机", "iphone", "安卓", "华为", "小米", "苹果", "oppo", "vivo", "荣耀",
            "耳机", "蓝牙耳机", "降噪耳机", "有线耳机", "airpods", "音箱", "智能音箱",
            "笔记本", "笔记本电脑", "游戏本", "轻薄本", "台式机", "电脑", "主机", "一体机",
            "平板", "平板电脑", "ipad", "手表", "智能手表", "手环", "运动手环", "iwatch",
            "相机", "单反", "微单", "拍立得", "无人机", "云台", "三脚架", "镜头", "存储卡",
            "充电", "充电器", "充电宝", "数据线", "快充", "无线充", "充电头", "移动电源",
            "键盘", "鼠标", "机械键盘", "电竞鼠标", "显示器", "显卡", "cpu", "内存条", "硬盘", "ssd",
            "游戏机", "switch", "ps5", "xbox", "掌机", "游戏手柄", "vr", "ar",
            "投影仪", "打印机", "扫描仪", "复印机", "kindle", "电子书", "阅读器",
            "扫地机器人", "吸尘器", "空气净化器", "加湿器", "除湿机", "智能门锁", "摄像头"
        ]),

        # 美妆护肤（新增：护肤全品类、彩妆全品类、美发护发、身体护理、美妆工具）
        ("美妆护肤", [
            "精华", "面霜", "防晒", "防晒霜", "防晒乳", "防晒喷雾", "隔离", "隔离霜",
            "洁面", "洗面奶", "洁面乳", "卸妆", "卸妆油", "卸妆水", "卸妆膏",
            "面膜", "贴片面膜", "睡眠面膜", "泥膜", "眼膜", "唇膜", "爽肤水", "乳液", "眼霜",
            "粉底", "粉底液", "气垫", "bb霜", "cc霜", "遮瑕", "遮瑕膏", "散粉", "定妆粉", "粉饼",
            "口红", "唇釉", "唇泥", "唇线笔", "眼影", "眼线", "睫毛膏", "假睫毛", "眉笔", "眉粉",
            "腮红", "高光", "修容", "妆前乳", "定妆喷雾", "化妆刷", "美妆蛋", "粉扑", "睫毛夹",
            "护肤", "美妆", "彩妆", "香水", "香氛", "身体乳", "护手霜", "润唇膏", "磨砂膏", "去角质",
            "洗发水", "护发素", "发膜", "精油", "染发剂", "烫发剂", "发胶", "发蜡", "发泥",
            "化妆棉", "棉签", "眉刀", "美甲", "指甲油", "甲油胶", "医美", "护肤品", "化妆品"
        ]),

        # 服饰运动（新增：全品类服饰、鞋靴、配饰、运动器材、户外装备）
        ("服饰运动", [
            "t恤", "短袖", "长袖", "衬衫", "卫衣", "毛衣", "针织衫", "外套", "夹克", "风衣",
            "羽绒", "羽绒服", "棉服", "大衣", "马甲", "背心", "吊带", "连衣裙", "半身裙", "短裙",
            "裤子", "牛仔裤", "休闲裤", "运动裤", "阔腿裤", "紧身裤", "打底裤", "短裤", "卫裤",
            "鞋", "运动鞋", "跑鞋", "篮球鞋", "足球鞋", "板鞋", "帆布鞋", "皮鞋", "马丁靴", "雪地靴",
            "凉鞋", "拖鞋", "人字拖", "长靴", "短靴", "老爹鞋", "休闲鞋", "徒步鞋", "登山鞋",
            "袜子", "船袜", "长袜", "短袜", "丝袜", "内裤", "内衣", "文胸", "睡衣", "家居服", "泳衣",
            "帽子", "棒球帽", "鸭舌帽", "渔夫帽", "贝雷帽", "围巾", "手套", "腰带", "皮带", "领带",
            "背包", "双肩包", "单肩包", "斜挎包", "手提包", "腰包", "钱包", "行李箱", "拉杆箱",
            "瑜伽", "健身", "跑步", "登山", "户外", "徒步", "露营", "滑雪", "游泳", "骑行",
            "瑜伽垫", "哑铃", "杠铃", "跑步机", "动感单车", "健身器材", "速干衣", "运动服",
            "护腕", "护膝", "头盔", "帐篷", "睡袋", "登山杖", "冲锋衣", "抓绒衣", "羽毛球拍", "篮球", "足球"
        ]),

        # 食品饮料（新增：生鲜、预制菜、调味品、保健品、酒水、粮油米面）
        ("食品饮料", [
            "咖啡", "速溶咖啡", "挂耳咖啡", "咖啡豆", "拿铁", "美式", "奶茶", "果茶",
            "零食", "饼干", "薯片", "膨化食品", "糖果", "巧克力", "坚果", "果干", "蜜饯",
            "肉干", "肉松", "辣条", "方便面", "泡面", "螺蛳粉", "米线", "米粉", "面条",
            "面包", "蛋糕", "糕点", "甜品", "果冻", "布丁", "酸奶", "奶酪", "芝士", "黄油",
            "饮料", "碳酸饮料", "果汁", "气泡水", "矿泉水", "苏打水", "功能饮料", "运动饮料",
            "牛奶", "羊奶", "奶粉", "豆浆", "豆奶", "鸡蛋", "生鲜", "水果", "蔬菜", "肉类", "海鲜",
            "茶", "绿茶", "红茶", "乌龙茶", "普洱茶", "花茶", "白茶", "黑茶", "茶叶",
            "保健", "保健品", "维生素", "钙片", "鱼油", "益生菌", "蛋白粉", "代餐",
            "大米", "面粉", "杂粮", "燕麦", "麦片", "食用油", "酱油", "醋", "盐", "调料",
            "火锅底料", "预制菜", "半成品", "冷冻食品", "速冻食品", "啤酒", "白酒", "红酒", "葡萄酒",
            "食品", "食物", "吃的", "喝的", "吃", "喝", "早餐", "午餐", "晚餐", "宵夜", "便当"
        ]),
    ]
    for cat, kws in cat_rules:
        if any(k in q for k in kws):
            result["category"] = cat
            break

    # Budget: "500元", "500以内", "500以下", "300-500元"
    import re
    budget_patterns = [
        (r'(\d+)\s*元?\s*以\s*[内下]', lambda m: float(m.group(1))),  # 500以内
        (r'(\d+)\s*[元块]', lambda m: float(m.group(1))),  # 500元
        (r'¥\s*(\d+)', lambda m: float(m.group(1))),  # ¥500
    ]
    for pattern, extract in budget_patterns:
        match = re.search(pattern, q)
        if match:
            result["budget_max"] = extract(match)
            break

    # Scenario
    scn_map = {
        "出差": "business_trip", "飞机": "flight", "通勤": "commute",
        "户外": "outdoor", "露营": "outdoor", "跑步": "sport",
        "健身": "sport", "办公": "desk", "旅行": "travel",
    }
    for cn, en in scn_map.items():
        if cn in q:
            result["scenario"] = en
            break

    return result
