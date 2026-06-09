"""商品列表 + 详情 API — V4: 增加 review_summary, keyword 搜索, 图片服务"""

import os
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from app.repositories.product_repo import get_product_repo

router = APIRouter()
_repo = get_product_repo()

# Dataset 根目录 (用于图片服务)
_DATASET_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ecommerce_agent_dataset"


def _build_review_summary(product) -> dict:
    """构建 review_summary。"""
    reviews = product.rag_knowledge.user_reviews if product.rag_knowledge else []
    if not reviews:
        return {"avg_rating": 0.0, "positive_count": 0, "negative_count": 0,
                "risk_tags": [], "total_count": 0}
    ratings = [r.rating for r in reviews]
    avg = sum(ratings) / len(ratings)
    positive = sum(1 for r in ratings if r >= 4)
    negative = sum(1 for r in ratings if r <= 2)
    risk_tags = []
    if negative >= 2:
        risk_tags.append("多差评风险")
    elif negative == 1:
        risk_tags.append("个别差评")
    if len(ratings) >= 3 and avg < 3.5:
        risk_tags.append("综合评分偏低")
    return {
        "avg_rating": round(avg, 1),
        "positive_count": positive,
        "negative_count": negative,
        "risk_tags": risk_tags,
        "total_count": len(ratings),
    }


def _normalize_image_url(product_id: str, image_path: str) -> str:
    """生成可访问的图片 URL。"""
    if not image_path:
        return ""
    # image_path 形如 "1_美妆护肤/images/p_beauty_001_live.jpg"
    return f"/api/products/{product_id}/image"


@router.get("/api/products/{product_id}/image")
async def get_product_image(product_id: str):
    """商品图片服务 — 从本地数据集读取并返回。"""
    p = _repo.get_by_id(product_id)
    if not p:
        raise HTTPException(404, "product not found")

    image_path = p.image_path
    if not image_path:
        raise HTTPException(404, "no image")

    # 直接路径
    full_path = _DATASET_DIR / image_path
    if full_path.exists():
        return FileResponse(str(full_path))

    # 文件名匹配: 数据集中 images/ 目录下的文件名
    fname = Path(image_path).name
    # Also try with _live suffix
    fname_live = fname.replace(".jpg", "_live.jpg").replace("_live_live", "_live")
    candidates_names = [fname, fname_live]
    for cat_dir in sorted(_DATASET_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        images_dir = cat_dir / "images"
        if images_dir.is_dir():
            for name in candidates_names:
                candidate = images_dir / name
                if candidate.exists():
                    return FileResponse(str(candidate))

    raise HTTPException(404, f"image file not found: {fname}")


@router.get("/api/products")
async def list_products(
    category: str | None = Query(None),
    sub_category: str | None = Query(None),
    keyword: str | None = Query(None),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=50),
):
    products = _repo.filter_by(
        category=category, sub_category=sub_category,
        price_min=price_min, price_max=price_max,
    )

    # 关键词过滤
    if keyword:
        kw = keyword.lower()
        products = [p for p in products
                    if kw in p.title.lower() or kw in p.brand.lower()
                    or kw in p.sub_category.lower()]

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
                "image_urls": [_normalize_image_url(p.product_id, p.image_path)],
                "avg_rating": (
                    round(sum(r.rating for r in p.rag_knowledge.user_reviews) / len(p.rag_knowledge.user_reviews), 1)
                    if p.rag_knowledge and p.rag_knowledge.user_reviews else 0.0
                ),
                "review_count": (
                    len(p.rag_knowledge.user_reviews)
                    if p.rag_knowledge and p.rag_knowledge.user_reviews else 0
                ),
            }
            for p in items
        ],
    }


@router.get("/api/products/{product_id}")
async def get_product(product_id: str):
    p = _repo.get_by_id(product_id)
    if not p:
        return {"error": "product not found"}

    rk = p.rag_knowledge
    return {
        "product_id": p.product_id,
        "title": p.title,
        "brand": p.brand,
        "category": p.category,
        "sub_category": p.sub_category,
        "price": p.base_price,
        "image_urls": [_normalize_image_url(p.product_id, p.image_path)],
        "skus": [s.model_dump() for s in p.skus],
        "marketing_description": rk.marketing_description if rk else "",
        "official_faq": [{"question": f.question, "answer": f.answer}
                         for f in rk.official_faq] if rk else [],
        "user_reviews": [{"nickname": r.nickname, "rating": r.rating, "content": r.content}
                         for r in rk.user_reviews] if rk else [],
        "review_summary": _build_review_summary(p),
    }
