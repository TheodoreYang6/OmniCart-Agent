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


def _safe_spotlight_summary(product, query: str) -> str:
    """为商品聚光页生成一份只依赖商品档案的简短说明。

    此接口过去又调用了一次自由生成模型，既绕开了推荐链路的 Guard，也可能
    和聊天中的结论不一致。聚光页本质是商品详情的补充说明，应该优先保证
    可追溯与稳定，而不是把营销长文二次扩写成新的性能承诺。
    """
    title = " ".join(str(product.title or "").split())
    brand = str(product.brand or "").strip()
    if brand and title.startswith(brand):
        title = title[len(brand):].lstrip(" -·")
    for marker in ("（", "("):
        if marker in title:
            title = title.split(marker, 1)[0].rstrip()
    title = title[:32].rstrip("，、。；; ") or "这件商品"
    rk = product.rag_knowledge
    reviews = list(rk.user_reviews or []) if rk else []
    faq_count = len(rk.official_faq or []) if rk else 0
    specs: list[str] = []
    for sku in product.skus or []:
        for value in (sku.properties or {}).values():
            value = str(value).strip()
            if value and value not in specs:
                specs.append(value)
    spec_text = "、".join(specs[:5]) or "以详情页规格为准"
    sentences = [f"{brand}{title}，当前价格¥{float(product.base_price):g}，可用规格包括{spec_text}。"]
    if query and any(word in query.lower() for word in ("海边", "户外", "暴晒", "下水", "出汗")):
        sentences.append("如果用于户外，请按详情页说明使用；长时间日晒、出汗或下水后应及时补充防护。")
    if faq_count:
        sentences.append(f"商品资料中有{faq_count}条官方问答，可继续核对使用方式与规格差异。")
    if reviews:
        avg = sum(review.rating for review in reviews) / len(reviews)
        sentences.append(f"现有{len(reviews)}条用户评价，平均{avg:.1f}/5；样本量有限，建议结合自己的使用场景判断。")
    else:
        sentences.append("目前用户评价较少，购买前建议重点确认适配性、规格和售后规则。")
    return "".join(sentences)


def _spotlight_fact_pack(product) -> str:
    """Create the only LLM-visible dossier for a product spotlight analysis."""
    lines = [
        f"商品：{product.brand} {product.title}",
        f"品类：{product.category}/{product.sub_category}",
        f"基础价格：¥{float(product.base_price):g}",
    ]
    sku_lines: list[str] = []
    for sku in product.skus or []:
        attrs = "、".join(f"{key}:{value}" for key, value in (sku.properties or {}).items())
        if attrs:
            sku_lines.append(f"{attrs}（¥{float(sku.price or product.base_price):g}）")
    if sku_lines:
        lines.append("可售规格：" + "；".join(sku_lines[:4]))

    knowledge = product.rag_knowledge
    if not knowledge:
        return "\n".join(lines + ["官方问答：无", "用户评价：无"])

    faqs = list(knowledge.official_faq or [])
    if faqs:
        faq_text = "；".join(
            f"问：{str(item.question)[:72]} 答：{str(item.answer)[:110]}"
            for item in faqs[:3]
        )
        lines.append("官方问答：" + faq_text)
    else:
        lines.append("官方问答：无")

    reviews = list(knowledge.user_reviews or [])
    if reviews:
        average = sum(float(item.rating or 0) for item in reviews) / len(reviews)
        snippets = "；".join(
            f"{float(item.rating or 0):g}/5：{str(item.content)[:100]}" for item in reviews[:3]
        )
        lines.append(f"用户评价：{len(reviews)} 条，均分 {average:.1f}/5；{snippets}")
    else:
        lines.append("用户评价：无")
    return "\n".join(lines)


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


# ---- Spotlight 商品档案摘要（spec §3.2）----

_SUMMARY_TTL = 3600  # 同商品+同 query 缓存 1h，命中直接回放


@router.post("/api/products/{product_id}/ai-summary")
async def product_ai_summary(product_id: str, body: dict | None = None):
    """Evidence-bound LLM supplement for the product spotlight panel (SSE)."""
    import asyncio
    import hashlib
    import json as _json

    from fastapi.responses import StreamingResponse

    from app.core.redis_client import get_redis

    if _is_pg:
        p = await _repo._aget_by_id(product_id)
    else:
        p = _repo.get_by_id(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")

    query = ((body or {}).get("query") or "").strip()[:120]
    qh = hashlib.md5(query.encode()).hexdigest()[:12]
    # New version is model-written from a controlled dossier; never reuse the
    # old deterministic-template cache under the same product/query key.
    cache_key = f"ai_summary:v4:{product_id}:{qh}"

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

        full = ""
        try:
            from app.core.config import RESPONSE_LLM_TIMEOUT
            from app.model_gateway.gateway import get_model_gateway
            from app.prompts.agent_prompts import (
                PRODUCT_SPOTLIGHT_ANALYSIS_SYSTEM,
                build_product_spotlight_analysis_prompt,
            )

            prompt = build_product_spotlight_analysis_prompt(_spotlight_fact_pack(p), query)
            full = (await asyncio.wait_for(
                get_model_gateway().chat("chat_generation", prompt, PRODUCT_SPOTLIGHT_ANALYSIS_SYSTEM),
                timeout=RESPONSE_LLM_TIMEOUT,
            )).strip()
            # The LLM is presentation only. Keep the panel compact and prevent
            # stray formatting from making this a second, incompatible UI path.
            full = full.replace("*", "").replace("#", "").strip()[:360]
            if len(full) < 30:
                full = ""
        except Exception:
            full = ""
        if not full:
            full = _safe_spotlight_summary(p, query)
        for i in range(0, len(full), 12):
            yield _sse(full[i : i + 12])
            await asyncio.sleep(0.01)
        if full and redis is not None:
            try:
                await redis.set(cache_key, full, ex=_SUMMARY_TTL)
            except Exception:
                pass
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
