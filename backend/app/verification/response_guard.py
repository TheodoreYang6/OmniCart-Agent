"""V1 Response Guard — 回答守门检查。

ResponseAgent 输出后执行，轻量规则不阻塞回答。
标记硬失败（幻觉/编造），写入 harness_report 供前端展示。
"""

import re
import logging
from app.schemas.workflow import WorkflowState

_log = logging.getLogger(__name__)


class ResponseGuard:
    """回答守门器 — 轻量规则检查 + 标记。"""

    # 常见品牌列表（幻觉检测用）
    _KNOWN_BRANDS = [
        "Anker", "安克", "Baseus", "倍思", "小米", "华为", "Apple", "苹果",
        "Samsung", "三星", "Sony", "索尼", "Bose", "JBL", "Sennheiser",
        "雅诗兰黛", "兰蔻", "SK-II", "资生堂", "科颜氏", "欧莱雅", "理肤泉",
        "Nike", "耐克", "Adidas", "阿迪达斯", "优衣库", "李宁",
        "雀巢", "三顿半", "蒙牛", "伊利", "元气森林", "可口可乐",
        "漫步者", "Edifier", "QCY", "小米", "Redmi", "AirPods",
        "迪卡侬", "华为", "HUAWEI", "农夫山泉", "东方树叶",
    ]

    def check(self, state: WorkflowState) -> dict:
        answer = state.answer or ""
        products = state.retrieved_products or []
        context = state.context_prompt or ""
        user_query = state.user_query or ""

        report = {
            "evidence_bound": self._check_evidence(answer, products),
            "price_accurate": self._check_price(answer, products),
            "risk_warned": self._check_risk(answer, state.decision_results or []),
            "honest_on_empty": self._check_empty(answer, products),
            "hallucination": self._check_hallucination(answer, products, context, user_query),
            "warnings": [],
        }

        # 汇总
        if not report["evidence_bound"]:
            report["warnings"].append("回答未引用证据（评价/FAQ等）")
        if not report["risk_warned"] and self._has_risks(state.decision_results or []):
            report["warnings"].append("存在风险项但回答未提醒")
        if not report["price_accurate"]:
            report["warnings"].append("价格引用不准确")
        if report["hallucination"]:
            report["warnings"].append(f"幻觉风险: {report['hallucination']}")

        has_warnings = len(report["warnings"]) > 0
        hard_fail = (
            not report["honest_on_empty"]  # 无商品时编造推荐
            or bool(report["hallucination"])  # 提到了不存在的品牌
        )

        state.harness_report = {
            "schema_valid": True,
            "evidence_bound": report["evidence_bound"],
            "price_accurate": report["price_accurate"],
            "risk_warned": report["risk_warned"],
            "honest_on_empty": report["honest_on_empty"],
            "guard_warnings": report["warnings"],
            "passed": not hard_fail,
            "failure_source": None if not hard_fail else "response_guard",
        }

        if hard_fail:
            _log.warning(f"ResponseGuard FAILED: {report['warnings']}")

        return report

    # ---- 各项检查 ----

    def _check_evidence(self, answer: str, products: list[dict]) -> bool:
        """证据绑定：回答是否引用了具体证据内容。

        不再只看关键词，改为检查是否引用了任意商品的关键证据关键词。
        """
        if not products:
            return True  # 无商品时不检查
        # 从证据列表中提取关键短语
        evidence_snippets = set()
        for p in products[:3]:
            title_words = re.findall(r'[一-鿿]{2,4}', p.get("title", ""))
            evidence_snippets.update(title_words[:3])
        # 回答中是否出现了商品标题中的关键词
        hits = sum(1 for s in evidence_snippets if s in answer)
        return hits >= 1

    def _check_price(self, answer: str, products: list[dict]) -> bool:
        """价格准确：如果提到了商品名，价格是否正确。"""
        for p in products[:2]:
            title_short = p.get("title", "")[:6]
            price = int(p.get("price", 0))
            price_strs = [str(price), f"¥{price}", f"￥{price}"]
            if title_short and title_short in answer:
                if not any(ps in answer for ps in price_strs):
                    return False
        return True

    def _check_risk(self, answer: str, decisions: list[dict]) -> bool:
        """风险覆盖：有风险标签时，回答是否提及。"""
        all_risks = set()
        for d in decisions[:3]:
            for r in d.get("risk_factors", []):
                # 提取风险关键词（取完整词而非前2字）
                keywords = re.findall(r'[一-鿿]{2,4}', r)
                all_risks.update(keywords)
        if not all_risks:
            return True  # 无风险项，pass
        # 至少命中一个风险关键词
        return any(kw in answer for kw in all_risks)

    def _check_empty(self, answer: str, products: list[dict]) -> bool:
        """空结果诚实：无商品时不应推荐具体品牌/型号。"""
        if products:
            return True
        misleading = ["推荐", "值得买", "建议入手", "可以考虑", "这款", "那个",
                      "Anker", "Baseus", "倍思", "紫米", "绿联"]
        return not any(kw in answer for kw in misleading)

    def _check_hallucination(
        self, answer: str, products: list[dict], context: str, user_query: str
    ) -> str:
        """幻觉检测：回答是否引用了不在检索结果中的品牌。

        排除用户自己提到的品牌（来自 query 或 context）。
        """
        if not products:
            return ""
        # 检索结果中的品牌
        product_brands = set(p.get("brand", "").lower() for p in products)
        # 用户已提及的品牌（来自 query + context）
        mentioned = set(user_query.lower() + " " + context.lower())

        for brand in self._KNOWN_BRANDS:
            if brand in answer and brand.lower() not in product_brands:
                if brand.lower() not in mentioned:
                    return f"提到了非检索结果的品牌 '{brand}'"
        return ""

    def _has_risks(self, decisions: list[dict]) -> bool:
        return any(d.get("risk_factors") for d in decisions)
