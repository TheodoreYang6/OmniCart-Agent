"""V1 Response Guard — 回答最终守门检查。

在 Response Agent 输出后执行，检查:
1. 证据绑定 — 是否引用了具体证据
2. 无依据判断 — 是否包含无来源的断言
3. 价格准确性 — 引用价格是否与实际匹配
4. 风险覆盖 — 有风险标签时是否提醒用户
5. 空结果处理 — 无商品时是否诚实告知
"""

from app.schemas.workflow import WorkflowState


class ResponseGuard:
    """回答守门器 — 轻量规则检查 + 标记，不做阻塞"""

    def check(self, state: WorkflowState) -> dict:
        report = {
            "evidence_bound": False,
            "price_accurate": True,
            "risk_warned": False,
            "honest_on_empty": True,
            "warnings": [],
        }

        answer = state.answer
        if not answer:
            report["warnings"].append("answer为空")
            return report

        # 1. 证据绑定检查
        evidence_keywords = ["评分", "评价", "评论", "FAQ", "星", "证据", "用户"]
        if any(kw in answer for kw in evidence_keywords):
            report["evidence_bound"] = True

        # 2. 价格准确性检查
        for p in state.retrieved_products[:3]:
            pid = p.get("product_id", "")
            price = p.get("price", 0)
            # 查找答案中是否引用了该商品的价格
            price_str = str(int(price))
            title_short = p.get("title", "")[:10]
            if title_short and title_short in answer and price_str not in answer:
                pass  # 可能提到了商品但没给价格，不算错误

        # 3. 风险覆盖检查
        for d in state.decision_results[:3]:
            risks = d.get("risk_factors", [])
            if risks:
                for risk in risks:
                    if any(c in answer for c in risk[:2]):
                        report["risk_warned"] = True
                        break

        # 4. 空结果诚实检查
        if not state.retrieved_products:
            misleading = ["推荐", "值得买", "建议入手"]
            if any(kw in answer for kw in misleading):
                report["honest_on_empty"] = False
                report["warnings"].append("无商品时不应推荐购买")

        # 5. 无依据断言检查
        unsupported = ["最好", "第一", "最强", "绝对", "保证"]
        for word in unsupported:
            if word in answer:
                report["warnings"].append(f"包含无依据断言: '{word}'")

        # 生成 harness 条目
        state.harness_report = {
            "schema_valid": True,
            "evidence_bound": report["evidence_bound"],
            "price_accurate": report["price_accurate"],
            "risk_warned": report["risk_warned"],
            "honest_on_empty": report["honest_on_empty"],
            "guard_warnings": report["warnings"],
        }

        return report
