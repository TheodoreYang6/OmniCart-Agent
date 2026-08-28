#!/usr/bin/env python
"""构建 V9 多视角商品 Chunk 索引（不覆盖旧 V6/V8 集合）。

用法：
  PYTHONPATH=backend python scripts/index_product_chunks_v9.py --recreate
  PYTHONPATH=backend python scripts/index_product_chunks_v9.py --limit 20 --local-only

V9 的本地缓存仅用于离线验证；线上以 Qdrant ``product_chunks_v9`` 为准。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import EMBEDDING_DIMENSION, MOCK_MODE, QDRANT_URL, USE_QDRANT, V9_CHUNK_COLLECTION_NAME
from app.model_gateway.gateway import get_model_gateway
from app.repositories.json_product_repo import JsonProductRepository
from app.schemas.product_chunk_v9 import build_chunks_v9
from app.services.product_facts import extract_product_facts
from index_product_chunks import EMBED_BATCH, UPSERT_BATCH, _embed_all, ensure_chunk_collection

CACHE_FILE = Path(__file__).resolve().parent.parent / "backend" / "data" / "product_chunk_embeddings_v9.json"


async def main() -> None:
    parser = argparse.ArgumentParser(description="build product_chunks_v9")
    parser.add_argument("--collection", default=V9_CHUNK_COLLECTION_NAME)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH)
    parser.add_argument("--no-hybrid", dest="hybrid", action="store_false")
    parser.set_defaults(hybrid=True)
    args = parser.parse_args()

    products = JsonProductRepository().list_all()
    if args.limit:
        products = products[:args.limit]
    chunks = []
    for product in products:
        facts = [fact.model_payload() for fact in extract_product_facts(product)]
        chunks.extend(build_chunks_v9(product, facts))
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
    print(f"V9: {len(products)} 件商品，{len(chunks)} 块：{counts}")

    embeddings = await _embed_all([chunk.text for chunk in chunks], args.batch_size)
    if len(embeddings) != len(chunks):
        raise RuntimeError("embedding 与 chunk 数量不一致")
    actual_dimension = len(embeddings[0]) if embeddings else EMBEDDING_DIMENSION
    if any(len(vector) != actual_dimension for vector in embeddings):
        raise RuntimeError("embedding 维度不一致，拒绝构建混合向量索引")
    if actual_dimension != EMBEDDING_DIMENSION:
        print(f"注意：当前 embedding 输出 {actual_dimension} 维，配置为 {EMBEDDING_DIMENSION} 维；将按实际维度建索引。")

    sparse_vecs: list[tuple[list[int], list[float]]] = []
    if args.hybrid:
        from app.retrieval import sparse_encoder as sparse
        stats = sparse.build_corpus_stats([chunk.text for chunk in chunks])
        sparse.save_stats(stats, Path(__file__).resolve().parent.parent / "backend" / "data" / "bm25_stats_v9.json")
        # v9 统计单独保存；避免悄悄覆盖旧集合统计。
        sparse_vecs = [sparse.encode_document(chunk.text, stats) for chunk in chunks]

    if not args.local_only and USE_QDRANT and QDRANT_URL:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, SparseVector

        client = QdrantClient(url=QDRANT_URL, timeout=90.0)
        ensure_chunk_collection(client, args.collection, actual_dimension, args.recreate, args.hybrid)
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True)):
            vectors: object = vector
            if args.hybrid:
                indices, values = sparse_vecs[index]
                vectors = {"dense": vector}
                if indices:
                    vectors["bm25"] = SparseVector(indices=indices, values=values)
            points.append(PointStruct(id=chunk.point_id(), vector=vectors, payload=chunk.to_qdrant_payload()))
        for start in range(0, len(points), UPSERT_BATCH):
            client.upsert(collection_name=args.collection, points=points[start:start + UPSERT_BATCH],
                          wait=start + UPSERT_BATCH >= len(points))
        print(f"Qdrant {args.collection}: {client.get_collection(args.collection).points_count} 点")
        client.close()
    else:
        print("跳过 Qdrant 写入（--local-only 或 QDRANT 未配置）")

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "version": "v9", "collection": args.collection, "dimension": actual_dimension,
        "count": len(chunks), "chunk_type_counts": counts,
        "chunks": [{"product_id": c.product_id, "chunk_id": c.chunk_id,
                    "chunk_type": c.chunk_type, "payload": c.to_qdrant_payload(),
                    "embedding": embeddings[i]} for i, c in enumerate(chunks)],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"本地验证缓存：{CACHE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
