#!/usr/bin/env python
"""产品文本嵌入索引脚本 — 将所有产品写入 Qdrant。

用法:
    python scripts/seed_qdrant.py

前置条件:
    - QDRANT_URL 已在 .env 中配置
    - QWEN_API_KEY 可用（调用 text-embedding-v4 生成嵌入）
    - 后端运行在本地或 Qdrant Cloud 可达
"""

import sys
import time
from pathlib import Path

# 确保 backend 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import QDRANT_URL, USE_QDRANT, MOCK_MODE
from app.repositories.json_product_repo import JsonProductRepository
from app.repositories.qdrant_vector_repo import QdrantVectorRepository
from app.model_gateway.gateway import get_model_gateway
from qdrant_client import QdrantClient


import asyncio


async def main_async():
    if not USE_QDRANT:
        print("QDRANT_URL is empty — 请先在 .env 中配置 QDRANT_URL")
        sys.exit(1)

    if MOCK_MODE:
        print("MOCK_MODE=true — 无法生成真实嵌入向量，请设 OMNICART_MOCK_MODE=false")
        sys.exit(1)

    print(f"连接 Qdrant: {QDRANT_URL}")
    client = QdrantClient(url=QDRANT_URL, timeout=30.0)
    vector_repo = QdrantVectorRepository(client)

    if not vector_repo.health_check():
        print(f"Qdrant 连接失败或 collection 不存在")
        # 尝试创建
        from app.core.config import EMBEDDING_DIMENSION, QDRANT_COLLECTION_NAME
        from qdrant_client.models import Distance, VectorParams
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
        )
        print(f"已创建 collection: {QDRANT_COLLECTION_NAME} (dim={EMBEDDING_DIMENSION})")

    # 加载所有产品
    repo = JsonProductRepository()
    products = repo.list_all()
    print(f"加载 {len(products)} 件产品")

    # 批量生成嵌入
    gateway = get_model_gateway()
    batch_size = 10
    total = 0

    for i in range(0, len(products), batch_size):
        batch = products[i : i + batch_size]
        texts = []
        for p in batch:
            rk = p.rag_knowledge
            text_parts = [
                p.title or "",
                p.brand or "",
                p.category or "",
                p.sub_category or "",
                rk.marketing_description if rk else "",
            ]
            # Qdrant 存储格式: "product_id | 拼接文本"
            texts.append(f"{p.product_id} | {' '.join(t for t in text_parts if t)}")

        try:
            embeddings = await gateway.embed(texts, "text_embedding")
        except Exception as e:
            print(f"嵌入 API 调用失败 (batch {i // batch_size + 1}): {e}")
            time.sleep(2)
            continue

        vector_repo.store_embeddings(texts, embeddings)
        total += len(batch)
        print(f"\r索引进度: {total}/{len(products)}", end="", flush=True)
        time.sleep(0.3)  # API 限速缓冲

    print(f"\n索引完成! 共 {total} 件商品写入 Qdrant")
    client.close()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
