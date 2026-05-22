"""V1 Counterfactual Recommendation — 检索无结果时的反事实建议。

当硬约束过滤后无商品返回，或检索结果过少时，
生成替代建议帮助用户调整查询。
"""


class CounterfactualRecommender:
    """反事实推荐器 — 0 结果时提供替代方向。"""

    STRATEGIES = {
        "relax_budget": "可以尝试放宽预算范围，或查看相近价位商品",
        "broaden_category": "可以尝试更广泛的品类，或查看相关品类推荐",
        "remove_tags": "可以尝试去除部分偏好标签，扩大搜索范围",
        "popular_alternative": "以下为当前热门商品，虽然不完全匹配您的需求",
        "rephrase_query": "建议用更通用的关键词重新描述需求",
    }

    def generate(self, user_query: str, constraints: dict, result_count: int) -> dict:
        """根据结果数量生成反事实建议。"""
        alternatives: list[str] = []
        relaxed: list[str] = []

        if result_count == 0:
            # 完全无结果 → 激进放宽
            if constraints.get("budget_max"):
                alternatives.append(self.STRATEGIES["relax_budget"])
                relaxed.append("budget_max")

            if constraints.get("category"):
                alternatives.append(self.STRATEGIES["broaden_category"])
                relaxed.append("category")

            if constraints.get("must_tags"):
                alternatives.append(self.STRATEGIES["remove_tags"])
                relaxed.append("must_tags")

            alternatives.append(self.STRATEGIES["rephrase_query"])

        elif result_count <= 2:
            alternatives.append(self.STRATEGIES["popular_alternative"])

        return {
            "query": user_query,
            "result_count": result_count,
            "alternatives": alternatives,
            "relaxed_constraints": relaxed,
            "suggestion": "; ".join(alternatives) if alternatives else "",
        }
