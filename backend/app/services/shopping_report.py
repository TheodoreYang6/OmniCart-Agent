"""Build a reproducible shopping report from the catalog before offering a quote."""

from statistics import mean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductModel

REPORT_TITLE = "欧米选购报告"


async def list_report_categories(session: AsyncSession) -> list[str]:
    result = await session.scalars(
        select(ProductModel.sub_category)
        .where(ProductModel.sub_category != "")
        .distinct()
        .order_by(ProductModel.sub_category)
    )
    return list(result)


async def build_shopping_report(session: AsyncSession, category: str, budget_fen: int) -> dict | None:
    products = await session.scalars(
        select(ProductModel)
        .where(
            ProductModel.sub_category == category,
            ProductModel.base_price > 0,
            ProductModel.base_price <= budget_fen / 100,
        )
        .order_by(ProductModel.base_price, ProductModel.product_id)
    )
    candidates = []
    for product in products:
        knowledge = product.rag_knowledge or {}
        reviews = knowledge.get("user_reviews") or []
        faq = knowledge.get("official_faq") or []
        rating = round(mean(review["rating"] for review in reviews), 1) if reviews else None
        price_fen = round(product.base_price * 100)
        candidates.append({
            "product_id": product.product_id,
            "title": product.title,
            "brand": product.brand,
            "price_fen": price_fen,
            "budget_left_fen": budget_fen - price_fen,
            "average_rating": rating,
            "review_count": len(reviews),
            "description": (knowledge.get("marketing_description") or "")[:280],
            "faq": [{"question": item["question"], "answer": item["answer"]} for item in faq[:2]],
            "review": max(reviews, key=lambda review: len(review.get("content", "")), default={}).get("content", "")[:180],
        })
    if len(candidates) < 2:
        return None

    cheapest = candidates[0]
    others = sorted(
        candidates[1:],
        key=lambda item: (-(item["average_rating"] or 0), -item["review_count"], item["price_fen"], item["product_id"]),
    )
    best_reviewed = others[0]
    shortlist = [cheapest, best_reviewed, *others[1:2]]
    cheapest["comparison_role"] = "目录参考价最低"
    best_reviewed["comparison_role"] = "其他候选中样本均分最高" if best_reviewed["average_rating"] else "同预算备选"
    if len(shortlist) == 3:
        shortlist[2]["comparison_role"] = "同预算备选"

    return {
        "category": category,
        "budget_fen": budget_fen,
        "candidate_count": len(candidates),
        "products": shortlist,
        "limitations": "价格、FAQ 和评价来自欧米商品数据集。下单前请核对实时价格、规格和库存。",
    }
