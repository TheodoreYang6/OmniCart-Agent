"""商品列表 API"""

from fastapi import APIRouter, Query
from app.repositories.product_repo import get_product_repo

router = APIRouter()
_repo = get_product_repo()


@router.get("/api/products")
async def list_products(
    category: str | None = Query(None),
    sub_category: str | None = Query(None),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=50),
):
    products = _repo.filter_by(
        category=category, sub_category=sub_category,
        price_min=price_min, price_max=price_max,
    )
    total = len(products)
    start = (page - 1) * page_size
    end = start + page_size
    items = products[start:end]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "product_id": p.product_id,
                "title": p.title,
                "brand": p.brand,
                "category": p.category,
                "sub_category": p.sub_category,
                "price": p.base_price,
                "image_urls": [_repo.resolve_image_url(p.product_id)],
                "skus": [s.model_dump() for s in p.skus],
                "tags": p.rag_knowledge.user_reviews[0].content[:60] if p.rag_knowledge and p.rag_knowledge.user_reviews else "",
            }
            for p in items
        ],
    }


@router.get("/api/products/{product_id}")
async def get_product(product_id: str):
    p = _repo.get_by_id(product_id)
    if not p:
        return {"error": "product not found"}
    return {
        "product_id": p.product_id,
        "title": p.title,
        "brand": p.brand,
        "category": p.category,
        "sub_category": p.sub_category,
        "price": p.base_price,
        "image_urls": [_repo.resolve_image_url(p.product_id)],
        "skus": [s.model_dump() for s in p.skus],
        "rag_knowledge": p.rag_knowledge.model_dump() if p.rag_knowledge else None,
    }
