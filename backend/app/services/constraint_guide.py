"""约束引导服务 — 基于数据集真实数据生成追问，缩小候选范围。

设计原则:
- 所有选项来自数据集 (sub_category / concern / budget 分档)
- 最多 2-3 轮追问后触发推荐
- 追问顺序: sub_category → concern/场景 → budget
- 已有约束的维度不再追问
"""

import logging
from dataclasses import dataclass, field

from app.repositories.product_repo import get_product_repo

_log = logging.getLogger(__name__)

# 各品类关联词 → 从商品描述/FAQ/评价中匹配
CONCERN_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "美妆护肤": [
        ("修护维稳", "修护|维稳|屏障|泛红|敏感|舒缓|过敏"),
        ("美白淡斑", "美白|淡斑|提亮|暗沉|焕白|焕亮|祛斑"),
        ("抗老紧致", "抗老|紧致|淡纹|皱纹|抗皱|抗初老|提拉|弹润"),
        ("控油保湿", "控油|保湿|补水|滋润|水润|清爽|平衡油脂"),
        ("防晒隔离", "防晒|隔离|紫外线|SPF|PA"),
        ("洁面卸妆", "洁面|卸妆|清洁|净化|毛孔"),
    ],
    "数码电子": [
        ("拍照影像", "拍照|摄像|影像|潜望|长焦|超广角|主摄|夜拍"),
        ("游戏性能", "游戏|电竞|高刷|低延迟|帧率|处理器|芯片"),
        ("商务办公", "办公|商务|轻薄|续航|便携|生产力|会议"),
        ("影音娱乐", "看剧|追剧|音质|Hi-Res|屏幕|大屏|沉浸"),
        ("降噪耳机", "降噪|ANC|通透|入耳|半入耳|无线"),
        ("快充续航", "快充|续航|电池|充电|长续航|GaN"),
    ],
    "服饰运动": [
        ("跑步训练", "跑步|跑鞋|缓震|回弹|碳板|竞速|训练"),
        ("户外登山", "登山|户外|防水|GORE-TEX|徒步|攀爬"),
        ("瑜伽健身", "瑜伽|健身|紧身|弹力|训练|速干"),
        ("篮球实战", "篮球|实战|缓震|支撑|变相|抓地"),
        ("日常休闲", "休闲|通勤|日常|百搭|基础|经典"),
    ],
    "食品饮料": [
        ("咖啡茶饮", "咖啡|茶|拿铁|美式|乌龙|绿茶|红茶|茉莉"),
        ("零食坚果", "零食|坚果|膨化|饼干|薯片|肉松|巧克力"),
        ("奶制品", "牛奶|酸奶|奶|乳制品|发酵|纯牛奶"),
        ("功能饮料", "功能饮料|能量|牛磺酸|咖啡因|维生素"),
        ("方便速食", "方便面|速食|泡面|杯面|即食|米线"),
    ],
}


@dataclass
class ConstraintOption:
    label: str
    value: str
    dim: str  # sub_category | concern | budget


@dataclass
class GuideResult:
    answer: str = ""
    options: list[ConstraintOption] = field(default_factory=list)
    should_recommend: bool = False
    locked_category: str = ""
    locked_sub_category: str = ""
    locked_concern: str = ""
    budget_max: float | None = None
    budget_min: float | None = None


class ConstraintGuide:
    """基于数据集约束分析的引导追问服务。"""

    def __init__(self):
        from app.repositories.json_product_repo import JsonProductRepository
        self._repo = JsonProductRepository()  # 始终用 JSON (内存)，避免 PG 连接开销

    def guide(
        self,
        user_query: str,
        category: str = "",
        sub_category: str = "",
        concern: str = "",
        budget_max: float | None = None,
        budget_min: float | None = None,
        round_num: int = 0,
    ) -> GuideResult:
        """根据当前已知约束，决定下一轮追问或触发推荐。

        round_num: 已追问的轮数 (0-based)
        """
        result = GuideResult(
            locked_category=category,
            locked_sub_category=sub_category,
            locked_concern=concern,
            budget_max=budget_max,
            budget_min=budget_min,
        )

        # 轮数限制: 最多追问 3 轮
        if round_num >= 3:
            result.should_recommend = True
            return result

        # 第 0 轮: 问品类 (如果没有检测到)
        if not category:
            cat_opts = self._get_category_options()
            if len(cat_opts) >= 2:
                result.answer = "你想买哪类商品？"
                result.options = cat_opts
                return result

        # 优先级: sub_category → concern → budget

        # 第 1 轮: 问 sub_category
        if category and not sub_category:
            sub_opts = self._get_sub_category_options(category)
            if len(sub_opts) >= 2:
                result.answer = self._pick_question("sub_category", category)
                result.options = sub_opts[:6]  # 最多显示 6 个
                return result

        # 第 2 轮: 问 concern/场景
        if category and sub_category and not concern:
            concern_opts = self._get_concern_options(category, sub_category)
            if len(concern_opts) >= 2:
                result.answer = self._pick_question("concern", category)
                result.options = concern_opts[:6]
                return result

        # 第 3 轮: 问 budget (如果没指定)
        if category and sub_category and budget_max is None and budget_min is None:
            budget_opts = self._get_budget_options(category, sub_category)
            if len(budget_opts) >= 2:
                result.answer = "你的预算大概是多少？"
                result.options = budget_opts
                return result

        # 约束足够 → 推荐
        result.should_recommend = True
        return result

    # ---- 选项生成 ----

    def _get_category_options(self) -> list[ConstraintOption]:
        """返回四大品类选项（按商品数量降序）。"""
        counts: dict[str, int] = {}
        for p in self._repo.list_all():
            if p.category:
                counts[p.category] = counts.get(p.category, 0) + 1
        sorted_cats = sorted(counts.items(), key=lambda x: -x[1])
        return [ConstraintOption(label=name, value=name, dim="category") for name, _ in sorted_cats]

    def _get_sub_category_options(self, category: str) -> list[ConstraintOption]:
        """从数据集获取某品类下的子品类选项（按商品数量降序）。"""
        products = self._repo.filter_by(category=category)
        counts: dict[str, int] = {}
        for p in products:
            if p.sub_category:
                counts[p.sub_category] = counts.get(p.sub_category, 0) + 1
        sorted_subs = sorted(counts.items(), key=lambda x: -x[1])
        return [ConstraintOption(label=name, value=name, dim="sub_category") for name, _ in sorted_subs]

    def _get_concern_options(self, category: str, sub_category: str = "") -> list[ConstraintOption]:
        """从商品描述/FAQ/评价中提取关联词选项。"""
        keywords = CONCERN_KEYWORDS.get(category, [])
        if not keywords:
            return []

        products = self._repo.filter_by(category=category, sub_category=sub_category or None)
        if not products:
            products = self._repo.filter_by(category=category)

        # 统计每个关联词命中的商品数
        hit_counts: dict[str, int] = {}
        for label, pattern in keywords:
            count = 0
            import re
            regex = re.compile(pattern, re.IGNORECASE)
            for p in products:
                text = p.title + " "
                if p.rag_knowledge:
                    text += p.rag_knowledge.marketing_description + " "
                    for faq in p.rag_knowledge.official_faq:
                        text += faq.question + " " + faq.answer + " "
                    for rev in p.rag_knowledge.user_reviews:
                        text += rev.content + " "
                if regex.search(text):
                    count += 1
            if count > 0:
                hit_counts[label] = count

        sorted_concerns = sorted(hit_counts.items(), key=lambda x: -x[1])
        return [ConstraintOption(label=name, value=name, dim="concern") for name, _ in sorted_concerns]

    def _get_budget_options(self, category: str, sub_category: str = "") -> list[ConstraintOption]:
        """根据子品类商品实际价格分布生成预算选项。"""
        products = self._repo.filter_by(category=category, sub_category=sub_category or None)
        if not products:
            products = self._repo.filter_by(category=category)
        if not products:
            return []

        prices = sorted([p.base_price for p in products])
        if len(prices) < 3:
            return [ConstraintOption(label="不限预算", value="", dim="budget")]

        # 按价格分 3-4 档
        p_min, p_max = prices[0], prices[-1]
        if p_max - p_min < 50:
            return [ConstraintOption(label=f"约 ¥{p_min:.0f}", value=f"0-{p_max+50:.0f}", dim="budget")]

        opts = []
        # 低档
        low_cut = sorted([p for p in prices if p <= (p_min + p_max) / 3])
        if low_cut:
            opts.append(ConstraintOption(
                label=f"¥{low_cut[0]:.0f} - ¥{low_cut[-1]:.0f}",
                value=f"0-{low_cut[-1]:.0f}",
                dim="budget",
            ))
        # 中档
        mid_cut = sorted([p for p in prices if (p_min + p_max) / 3 < p <= (p_min + p_max) * 2 / 3])
        if mid_cut:
            opts.append(ConstraintOption(
                label=f"¥{mid_cut[0]:.0f} - ¥{mid_cut[-1]:.0f}",
                value=f"{mid_cut[0]:.0f}-{mid_cut[-1]:.0f}",
                dim="budget",
            ))
        # 高档
        high_cut = sorted([p for p in prices if p > (p_min + p_max) * 2 / 3])
        if high_cut:
            opts.append(ConstraintOption(
                label=f"¥{high_cut[0]:.0f} - ¥{high_cut[-1]:.0f}",
                value=f"{high_cut[0]:.0f}-{high_cut[-1]:.0f}",
                dim="budget",
            ))
        # 不限
        opts.append(ConstraintOption(label="不限预算", value="", dim="budget"))
        return opts

    def _pick_question(self, dim: str, category: str) -> str:
        if dim == "sub_category":
            cat_questions = {
                "美妆护肤": "你想找哪类护肤品？",
                "数码电子": "想买哪种数码产品？",
                "服饰运动": "想找什么类型的？",
                "食品饮料": "想买哪类食品？",
            }
            return cat_questions.get(category, "你想找哪种类型的？")
        if dim == "concern":
            return "你比较看重哪些方面？"
        return "还有什么偏好吗？"


# 单例
_guide: ConstraintGuide | None = None


def get_constraint_guide() -> ConstraintGuide:
    global _guide
    if _guide is None:
        _guide = ConstraintGuide()
    return _guide
