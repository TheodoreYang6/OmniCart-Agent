#!/usr/bin/env python
"""产品分块 Embedding 索引 — 将每件商品拆分为 summary/mkt/faq/rev 块写入 Qdrant + 本地缓存。

与 index_products.py 的区别:
- 每件商品生成 10-11 个块（而非 1 个向量）
- 块类型: summary, mkt, faq (每条FAQ一个), rev (每条评论一个)
- 检索时在块级别搜索，然后聚合到产品级别
- 兼容旧 collection (products) 作为降级路径

用法:
    python scripts/index_product_chunks.py
    python scripts/index_product_chunks.py --local-only   # 仅生成本地缓存，不写 Qdrant
    python scripts/index_product_chunks.py --batch-size 50
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

# Windows asyncio 兼容
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from app.core.config import (
    QDRANT_URL, USE_QDRANT, MOCK_MODE, EMBEDDING_DIMENSION,
    CHUNKED_COLLECTION_NAME,
)
from app.repositories.json_product_repo import JsonProductRepository
from app.model_gateway.gateway import get_model_gateway

CACHE_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"
CACHE_FILE = CACHE_DIR / "product_chunk_embeddings.json"


def _base_payload(product, chunk_type: str, chunk_index: int) -> dict:
    """构建所有块共有的基础 payload 字段（约束过滤无需回查商品）。"""
    return {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "sub_category": product.sub_category,
        "price": product.base_price,
        "chunk_type": chunk_type,
        "chunk_index": chunk_index,
        "chunk_id": f"{product.product_id}|{chunk_type}|{chunk_index}",
    }


def build_chunks(product) -> list[dict]:
    """将单件商品拆分为多个块。返回 [{chunk_id, chunk_type, text, payload}, ...]。

    块类型:
    - summary (1块): 产品基本标识信息
    - mkt (1块): 完整营销描述
    - faq (N块): 每条 FAQ 独立成块
    - rev (N块): 每条用户评论独立成块
    """
    chunks = []
    rk = product.rag_knowledge

    # ---- summary ----
    summary_text = (
        f"[产品] {product.title} | [品牌] {product.brand} | "
        f"[品类] {product.category} > {product.sub_category} | [价格] ¥{product.base_price:.0f}"
    )
    chunks.append({
        "chunk_id": f"{product.product_id}|summary|0",
        "chunk_type": "summary",
        "text": summary_text,
        "payload": _base_payload(product, "summary", 0),
    })

    # ---- mkt ----
    if rk and rk.marketing_description:
        chunks.append({
            "chunk_id": f"{product.product_id}|mkt|0",
            "chunk_type": "mkt",
            "text": rk.marketing_description.strip(),
            "payload": _base_payload(product, "mkt", 0),
        })

    # ---- faq (每条独立) ----
    if rk and rk.official_faq:
        for i, faq in enumerate(rk.official_faq):
            text = f"Q: {faq.question.strip()} A: {faq.answer.strip()[:200]}"
            payload = _base_payload(product, "faq", i)
            payload["faq_question"] = faq.question.strip()
            chunks.append({
                "chunk_id": f"{product.product_id}|faq|{i}",
                "chunk_type": "faq",
                "text": text,
                "payload": payload,
            })

    # ---- rev (每条独立) ----
    if rk and rk.user_reviews:
        for i, rev in enumerate(rk.user_reviews):
            text = f"[{rev.nickname}] 评分{rev.rating}/5: {rev.content.strip()[:200]}"
            payload = _base_payload(product, "rev", i)
            payload["review_rating"] = rev.rating
            payload["review_nickname"] = rev.nickname
            chunks.append({
                "chunk_id": f"{product.product_id}|rev|{i}",
                "chunk_type": "rev",
                "text": text,
                "payload": payload,
            })

    return chunks


def _format_chunk_text(chunk: dict) -> str:
    """Qdrant 存储格式: chunk_id | text（与旧格式保持一致）。"""
    return f"{chunk['chunk_id']} | {chunk['text']}"


async def main_async():
    import asyncio
    parser = argparse.ArgumentParser(description="产品分块 Embedding 索引工具")
    parser.add_argument("--local-only", action="store_true", help="仅生成本地缓存")
    parser.add_argument("--batch-size", type=int, default=10, help="批量大小（Qwen Embedding API 上限 ~10-15）")
    args = parser.parse_args()

    repo = JsonProductRepository()
    products = repo.list_all()
    print(f"加载 {len(products)} 件产品")

    all_chunks = []
    for p in products:
        chunks = build_chunks(p)
        all_chunks.extend(chunks)

    chunk_type_counts = {}
    for c in all_chunks:
        chunk_type_counts[c["chunk_type"]] = chunk_type_counts.get(c["chunk_type"], 0) + 1

    print(f"生成 {len(all_chunks)} 个块: {chunk_type_counts}")

    chunk_texts = [_format_chunk_text(c) for c in all_chunks]

    if MOCK_MODE:
        print("MOCK_MODE=true，生成随机向量作为占位")
        import random
        random.seed(42)
        all_embeddings = [
            [random.random() for _ in range(EMBEDDING_DIMENSION)]
            for _ in chunk_texts
        ]
    else:
        print(f"调用 Qwen Embedding API 生成 {len(all_chunks)} 个向量 (dim={EMBEDDING_DIMENSION})...")
        gateway = get_model_gateway()
        all_embeddings = []
        for i in range(0, len(chunk_texts), args.batch_size):
            batch = chunk_texts[i : i + args.batch_size]
            try:
                batch_texts = [t.split(" | ", 1)[1] for t in batch]
                embeddings = await gateway.embed(batch_texts, "text_embedding")
                all_embeddings.extend(embeddings)
            except Exception as e:
                print(f"  batch {i // args.batch_size + 1} 失败: {e}")
                time.sleep(1)
                continue
            progress = min(i + args.batch_size, len(chunk_texts))
            print(f"\r  进度: {progress}/{len(chunk_texts)}", end="", flush=True)
            time.sleep(0.3)
        print()

        # API 全失败降级 → 使用随机 mock 向量
        if not all_embeddings:
            print("所有 embedding API 调用失败，降级为随机 mock 向量")
            import random
            random.seed(42)
            all_embeddings = [
                [random.random() for _ in range(EMBEDDING_DIMENSION)]
                for _ in chunk_texts
            ]

    # ---- 写入 Qdrant ----
    if not args.local_only and USE_QDRANT and QDRANT_URL:
        print(f"写入 Qdrant: {QDRANT_URL} → collection '{CHUNKED_COLLECTION_NAME}'")
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        import uuid

        client = QdrantClient(url=QDRANT_URL, timeout=30.0)

        try:
            client.get_collection(CHUNKED_COLLECTION_NAME)
        except Exception:
            client.create_collection(
                collection_name=CHUNKED_COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
            )
            print(f"  已创建 collection: {CHUNKED_COLLECTION_NAME}")

        points = []
        for chunk, vector in zip(all_chunks, all_embeddings):
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"])),
                vector=vector,
                payload=chunk["payload"],
            ))

        client.upsert(collection_name=CHUNKED_COLLECTION_NAME, points=points)
        client.close()
        print(f"  Qdrant 写入完成: {len(points)} 条")
    else:
        reason = "(--local-only)" if args.local_only else "(QDRANT_URL 未配置)"
        print(f"跳过 Qdrant 写入 {reason}")

    # ---- 本地缓存 ----
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "dimension": EMBEDDING_DIMENSION,
        "count": len(all_chunks),
        "product_count": len(products),
        "chunk_type_counts": chunk_type_counts,
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "product_id": chunk["payload"]["product_id"],
                "chunk_type": chunk["chunk_type"],
                "payload": chunk["payload"],
                "embedding": all_embeddings[i],
            }
            for i, chunk in enumerate(all_chunks)
        ],
    }
    CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = CACHE_FILE.stat().st_size / 1024
    print(f"本地缓存: {CACHE_FILE} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main_async())
