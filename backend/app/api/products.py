"""商品列表 + 详情 API — V4: 增加 review_summary, keyword 搜索, 图片服务"""

import os
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from app.repositories.product_repo import get_product_repo
from app.repositories.pg_product_repo import PgProductRepository

router = APIRouter()
_repo = get_product_repo()
_is_pg = isinstance(_repo, PgProductRepository)

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
    if _is_pg:
        p = await _repo._aget_by_id(product_id)
    else:
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
    if _is_pg:
        products = await _repo._afilter_by(
            category=category, sub_category=sub_category,
            price_min=price_min, price_max=price_max,
        )
    else:
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
    if _is_pg:
        p = await _repo._aget_by_id(product_id)
    else:
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


# ---- Spotlight AI 小总结（spec §3.2）----

_SUMMARY_TTL = 3600  # 同商品+同 query 缓存 1h，命中直接回放


@router.post("/api/products/{product_id}/ai-summary")
async def product_ai_summary(product_id: str, body: dict | None = None):
    """商品 AI 小总结（SSE 流式）——Spotlight 面板异步加载。

    结合会话上下文（用户最近 query）生成 80-120 字选购向总结：
    贴合需求点讲、正向促单、诚实提及主要注意点一条。
    Redis 缓存 (pid, query 归一 hash) TTL 1h；命中时按块快速回放保打字机观感。
    """
    import asyncio
    import hashlib
    import json as _json

    from fastapi.responses import StreamingResponse

    from app.core.redis_client import get_redis
    from app.model_gateway.gateway import get_model_gateway

    if _is_pg:
        p = await _repo._aget_by_id(product_id)
    else:
        p = _repo.get_by_id(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")

    query = ((body or {}).get("query") or "").strip()[:120]
    qh = hashlib.md5(query.encode()).hexdigest()[:12]
    cache_key = f"ai_summary:v1:{product_id}:{qh}"

    def _sse(text: str) -> str:
        return f"data: {_json.dumps({'text': text}, ensure_ascii=False)}\n\n"

    async def _gen():
        redis = await get_redis()
        # 缓存命中：按块回放（保留打字机观感但更快）
        if redis is not None:
            try:
                cached_text = await redis.get(cache_key)
                if cached_text:
                    for i in range(0, len(cached_text), 8):
                        yield _sse(cached_text[i : i + 8])
                        await asyncio.sleep(0.01)
                    yield "event: done\ndata: {}\n\n"
                    return
            except Exception:
                pass

        rk = p.rag_knowledge
        reviews = rk.user_reviews if rk else []
        good = sum(1 for r in reviews if r.rating >= 4)
        neg = [r.content[:40] for r in reviews if r.rating <= 2][:1]
        faq = [f"{f.question[:30]}：{f.answer[:50]}" for f in (rk.official_faq if rk else [])[:2]]
        sku_str = " / ".join(
            " ".join(f"{v}" for v in (s.properties or {}).values()) for s in p.skus[:3])

        prompt = (
            f"你是购物智能体欧米。用户正在看这个商品，请给出 80-120 字的选购小总结。\n"
            f"{'用户需求：' + query if query else ''}\n"
            f"商品：{p.brand} {p.title} ¥{p.base_price}\n"
            f"规格：{sku_str}\n"
            f"评价：{len(reviews)} 条，{good} 条好评" + (f"；典型差评：{neg[0]}" if neg else "") + "\n"
            f"FAQ：{'；'.join(faq)}\n"
            "要求：①紧贴用户需求讲亮点（有需求时）②语气亲切促单③诚实提一条主要注意点"
            "④不编造信息，不说'可能''大概'⑤直接输出正文不加标题"
        )

        full = ""
        try:
            gateway = get_model_gateway()
            async for tok in gateway.chat_stream("chat_generation", prompt):
                full += tok
                yield _sse(tok)
        except Exception:
            if not full:
                fallback = (f"{p.brand} {p.title}，¥{p.base_price}。"
                            f"{len(reviews)} 条评价中 {good} 条好评，口碑在线～")
                full = fallback
                yield _sse(fallback)
        if full and redis is not None:
            try:
                await redis.set(cache_key, full, ex=_SUMMARY_TTL)
            except Exception:
                pass
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
