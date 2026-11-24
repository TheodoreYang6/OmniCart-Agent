"""Select one checked answer for transport and conversation history."""

import logging
from decimal import Decimal

from app.services.recommendation_brief import build_recommendation_brief

logger = logging.getLogger(__name__)


def finalize_response(state, candidate: str, guard, *, cards: list[dict] | None = None) -> str:
    products = state.retrieved_products or []
    if cards is None:
        cards, _ = build_recommendation_brief(state)
    card_ids = {product.get("product_id") for product in cards}
    guard_state = state.model_copy(update={
        "answer": candidate.strip(),
        "retrieved_products": cards + [item for item in products if item.get("product_id") not in card_ids],
        "answer_cited_pids": list(card_ids),
    })
    try:
        guard.check(guard_state)
        report = dict(guard_state.harness_report or {})
    except Exception:
        logger.exception("Answer verification failed")
        report = {"passed": False, "failure_source": "response_guard"}
    if candidate.strip() and report.get("passed") and (cards or not products):
        answer = candidate.strip()
    else:
        report["fallback_used"] = True
        if cards:
            facts = [
                f"- {item.get('title') or item.get('brand') or '商品'}，目录参考价 ¥{Decimal(str(item['price'])):.2f}"
                for item in cards if item.get("price") is not None
            ]
            answer = "以下是本轮卡片中可核对的商品与价格。\n" + "\n".join(facts) if facts else (
                "可以查看本轮商品卡。现有资料不足以给出进一步结论。"
            )
        elif state.needs_clarification and state.clarification_question:
            answer = state.clarification_question
        else:
            answer = "暂时没有找到符合条件的商品。可以补充用途或调整预算后再试。"
    state.harness_report = report
    state.answer = answer
    return answer
