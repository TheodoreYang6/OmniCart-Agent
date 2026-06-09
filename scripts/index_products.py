#!/usr/bin/env python
"""产品级富文本 Embedding 索引 — 将所有产品写入 Qdrant + 本地缓存。

与旧 seed_qdrant.py 的区别:
- embedding 文本包含完整 FAQ + 评价摘要 + 关键卖点
- 同时写入 Qdrant 和本地 JSON 缓存（供 Qdrant 不可用时降级）
- 每件商品生成单个向量（产品级索引，不分块）

用法:
    python scripts/index_products.py
    python scripts/index_products.py --local-only   # 仅生成本地缓存，不写 Qdrant
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import QDRANT_URL, USE_QDRANT, MOCK_MODE, EMBEDDING_DIMENSION, QDRANT_COLLECTION_NAME
from app.repositories.json_product_repo import JsonProductRepository
from app.model_gateway.gateway import get_model_gateway

CACHE_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"
CACHE_FILE = CACHE_DIR / "product_embeddings.json"


def build_embedding_text(product) -> str:
    """为单件商品构建富文本 embedding 描述。

    包含: 标题、品牌、品类层级、价格、描述摘要、FAQ 关键问答、评价摘要。
    这是语义检索的核心——embedding 文本的质量直接决定检索效果。
    """
    rk = product.rag_knowledge
    parts = []

    # 基础信息
    parts.append(f"[产品] {product.title}")
    parts.append(f"[品牌] {product.brand}")
    parts.append(f"[品类] {product.category} > {product.sub_category}")
    parts.append(f"[价格] ¥{product.base_price:.0f}")

    # 营销描述（截取前300字保留核心卖点）
    if rk and rk.marketing_description:
        desc = rk.marketing_description.strip()
        parts.append(f"[描述] {desc[:300]}")

    # FAQ 摘要（问题和答案都纳入，这是用户决策关键信息）
    if rk and rk.official_faq:
        faq_lines = ["[常见问题]"]
        for faq in rk.official_faq[:5]:
            q = faq.question.strip()
            a = faq.answer.strip()[:120]
            faq_lines.append(f"Q: {q} A: {a}")
        parts.append(" ".join(faq_lines))

    # 评价摘要
    if rk and rk.user_reviews:
        ratings = [r.rating for r in rk.user_reviews]
        avg_r = sum(ratings) / len(ratings)
        review_lines = [f"[用户评价] 均分{avg_r:.1f}/5 ({len(ratings)}条)"]

        # 好评摘录（4-5星）
        positive = [r for r in rk.user_reviews if r.rating >= 4]
        if positive:
            pos_texts = [r.content.strip()[:100] for r in positive[:2]]
            review_lines.append("好评: " + " | ".join(pos_texts))

        # 差评摘录（1-2星）
        negative = [r for r in rk.user_reviews if r.rating <= 2]
        if negative:
            neg_texts = [r.content.strip()[:100] for r in negative[:2]]
            review_lines.append("差评: " + " | ".join(neg_texts))

        parts.append(" ".join(review_lines))

    return " ".join(parts)


async def main_async():
    import asyncio
    parser = argparse.ArgumentParser(description="产品 Embedding 索引工具")
    parser.add_argument("--local-only", action="store_true", help="仅生成本地缓存")
    parser.add_argument("--batch-size", type=int, default=10, help="批量大小")
    args = parser.parse_args()

    # 加载产品
    repo = JsonProductRepository()
    products = repo.list_all()
    print(f"加载 {len(products)} 件产品")

    # 构建 embedding 文本
    embedding_texts = []
    for p in products:
        text = build_embedding_text(p)
        # Qdrant 存储格式: "product_id | text"
        embedding_texts.append(f"{p.product_id} | {text}")

    # 生成嵌入向量
    if MOCK_MODE:
        print("MOCK_MODE=true，生成随机向量作为占位")
        import random
        random.seed(42)
        all_embeddings = [
            [random.random() for _ in range(EMBEDDING_DIMENSION)]
            for _ in embedding_texts
        ]
    else:
        print(f"调用 Qwen Embedding API 生成 {len(products)} 个向量 (dim={EMBEDDING_DIMENSION})...")
        gateway = get_model_gateway()
        all_embeddings = []
        for i in range(0, len(embedding_texts), args.batch_size):
            batch = embedding_texts[i : i + args.batch_size]
            try:
                embeddings = await gateway.embed([t.split(" | ", 1)[1] for t in batch], "text_embedding")
                all_embeddings.extend(embeddings)
            except Exception as e:
                print(f"  batch {i // args.batch_size + 1} 失败: {e}")
                time.sleep(2)
                continue
            print(f"\r  进度: {min(i + args.batch_size, len(products))}/{len(products)}", end="", flush=True)
            time.sleep(0.3)
        print()

    # ---- 写入 Qdrant ----
    if not args.local_only and USE_QDRANT and QDRANT_URL:
        print(f"写入 Qdrant: {QDRANT_URL}")
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        import uuid

        client = QdrantClient(url=QDRANT_URL, timeout=30.0)

        # 确保 collection 存在
        try:
            client.get_collection(QDRANT_COLLECTION_NAME)
        except Exception:
            client.create_collection(
                collection_name=QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
            )
            print(f"  已创建 collection: {QDRANT_COLLECTION_NAME}")

        # 批量 upsert
        points = []
        for text, vector in zip(embedding_texts, all_embeddings):
            parts = text.split(" | ", 1)
            pid = parts[0]
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, pid)),
                vector=vector,
                payload={
                    "product_id": pid,
                    "text": parts[1] if len(parts) > 1 else text,
                },
            ))

        client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=points)
        client.close()
        print(f"  Qdrant 写入完成: {len(points)} 条")
    else:
        print("跳过 Qdrant 写入" + (" (--local-only)" if args.local_only else " (QDRANT_URL 未配置)"))

    # ---- 本地缓存 ----
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "dimension": EMBEDDING_DIMENSION,
        "count": len(products),
        "products": [
            {
                "product_id": p.product_id,
                "embedding_text": embedding_texts[i].split(" | ", 1)[1],
                "embedding": all_embeddings[i],
            }
            for i, p in enumerate(products)
        ],
    }
    CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"本地缓存: {CACHE_FILE} ({CACHE_FILE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main_async())
