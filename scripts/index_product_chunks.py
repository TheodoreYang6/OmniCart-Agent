#!/usr/bin/env python
"""产品分块 Embedding 索引 (V5) — 统一 chunk 单集合。

将每件商品拆分为 summary/mkt/faq/rev 块，用真实 qwen3.7-text-embedding 生成 1024 维向量，
写入版本化单集合 (CHUNK_COLLECTION_NAME) + 建 payload 索引 + 本地缓存降级。

字段拆分/映射统一走 app.schemas.product_chunk（避免重复维护）。

用法:
    python scripts/index_product_chunks.py                 # 全量重建
    python scripts/index_product_chunks.py --local-only    # 仅本地缓存，不写 Qdrant
    python scripts/index_product_chunks.py --limit 20      # 只处理前 20 件（冒烟）
    python scripts/index_product_chunks.py --recreate      # 先删旧集合再重建
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from app.core.config import (
    QDRANT_URL, USE_QDRANT, MOCK_MODE, EMBEDDING_DIMENSION, CHUNK_COLLECTION_NAME,
)
from app.repositories.json_product_repo import JsonProductRepository
from app.model_gateway.gateway import get_model_gateway
from app.schemas.product_chunk import build_chunks, chunk_point_id

CACHE_DIR = Path(__file__).resolve().parent.parent / "backend" / "data"
CACHE_FILE = CACHE_DIR / "product_chunk_embeddings.json"

EMBED_BATCH = 10      # Qwen API 单批上限（本地模型路径由 local_backend 内部再批 32）
UPSERT_BATCH = 256    # Qdrant 批量写入
EMBED_CONCURRENCY = 4  # V6: 批间并发度（实测单进程串行后吞吐仅 ~4.7 批/分）


def ensure_chunk_collection(client, collection: str, dim: int, recreate: bool = False,
                           hybrid: bool = True):
    """确保集合存在（版本化命名）+ 建 payload 索引（过滤字段）。

    hybrid=True（V7）：命名向量 ``dense``（语义）+ 稀疏向量 ``bm25``（词面），
    供 Qdrant 服务端 Prefetch+RRF 混合检索（spec §1.2）。
    hybrid=False：单匿名向量（V6 形态，兼容旧集合重建）。
    """
    from qdrant_client.models import (
        Distance,
        PayloadSchemaType,
        SparseIndexParams,
        SparseVectorParams,
        VectorParams,
    )

    if recreate:
        try:
            client.delete_collection(collection)
            print(f"  已删除旧集合: {collection}")
        except Exception:
            pass

    exists = True
    try:
        client.get_collection(collection)
    except Exception:
        exists = False

    if not exists:
        if hybrid:
            client.create_collection(
                collection_name=collection,
                vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
                sparse_vectors_config={"bm25": SparseVectorParams(index=SparseIndexParams())},
            )
            print(f"  已创建混合集合: {collection} (dense={dim}/Cosine + sparse=bm25)")
        else:
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            print(f"  已创建集合: {collection} (dim={dim}, Cosine)")

    # payload 索引：过滤字段（幂等；V6 增 avg_rating 支持口碑过滤）
    index_fields = {
        "product_id": PayloadSchemaType.KEYWORD,
        "chunk_type": PayloadSchemaType.KEYWORD,
        "category": PayloadSchemaType.KEYWORD,
        "sub_category": PayloadSchemaType.KEYWORD,
        "brand": PayloadSchemaType.KEYWORD,
        "price": PayloadSchemaType.FLOAT,
        "avg_rating": PayloadSchemaType.FLOAT,
    }
    for field_name, schema in index_fields.items():
        try:
            client.create_payload_index(collection, field_name=field_name, field_schema=schema)
        except Exception:
            pass  # 已存在则忽略
    print(f"  payload 索引就绪: {', '.join(index_fields)}")


async def _embed_all(chunk_texts: list[str], batch_size: int,
                     concurrency: int = EMBED_CONCURRENCY) -> list[list[float]]:
    """批量真实 embedding（V6：按 provider 选策略 + 指数退避重试 + 按序回填）。

    - 本地模型（local provider）：单并发 + 大批 256（encode 内部自带 batch 32；
      多线程并发在单卡/MPS 上无收益，且曾触发单例竞态 4 份模型重复加载）；
    - API：批 10（单批上限）× 并发 4。
    失败批重试 3 次（1s/2s/4s）后仍失败则整体报错终止——绝不跳批，
    避免向量与块错位（index_products.py 旧版 continue 错位 Bug 的教训）。
    文档侧编码 is_query=False（非对称编码的索引侧）。MOCK 降级随机向量。
    """
    if MOCK_MODE:
        print("MOCK_MODE=true → 随机占位向量")
        import random
        random.seed(42)
        return [[random.random() for _ in range(EMBEDDING_DIMENSION)] for _ in chunk_texts]

    # 按 provider 选批量策略：本地模型大批串行，API 小批并发
    from app.model_gateway.providers import get_provider

    plabel = getattr(get_provider(False), "name", "qwen")
    if plabel == "local":
        batch_size, concurrency = 256, 1

    batches = [chunk_texts[i : i + batch_size] for i in range(0, len(chunk_texts), batch_size)]
    print(f"调用 embedding 生成 {len(chunk_texts)} 个向量 "
          f"(provider={plabel}, dim={EMBEDDING_DIMENSION}, {len(batches)} 批 × 并发 {concurrency})...")
    gateway = get_model_gateway()
    results: list[list[list[float]] | None] = [None] * len(batches)
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(bi: int, batch: list[str]):
        nonlocal done
        async with sem:
            for attempt in range(3):
                try:
                    results[bi] = await gateway.embed(batch, "text_embedding")
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        raise RuntimeError(f"batch {bi} 三次失败: {e}") from e
                    await asyncio.sleep(2 ** attempt)  # 1s/2s/4s 指数退避
            done += 1
            if done % 20 == 0 or done == len(batches):
                print(f"\r  进度: {done}/{len(batches)} 批", end="", flush=True)

    await asyncio.gather(*[_one(i, b) for i, b in enumerate(batches)])
    print()
    all_embeddings: list[list[float]] = []
    for bi, r in enumerate(results):
        if r is None or len(r) != len(batches[bi]):
            raise RuntimeError(f"batch {bi} 结果缺失/长度不符，终止（防错位）")
        all_embeddings.extend(r)
    return all_embeddings


async def main_async():
    parser = argparse.ArgumentParser(description="产品分块 Embedding 索引 (V5)")
    parser.add_argument("--local-only", action="store_true", help="仅生成本地缓存")
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH)
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 件（0=全部）")
    parser.add_argument("--recreate", action="store_true", help="先删旧集合再重建")
    parser.add_argument("--collection", default=CHUNK_COLLECTION_NAME, help="目标集合名")
    parser.add_argument("--product-ids", default="",
                        help="增量模式：逗号分隔的 product_id（只重算这些商品的块）")
    parser.add_argument("--product-ids-file", default="",
                        help="增量模式：每行一个 product_id 的文件")
    parser.add_argument("--no-hybrid", dest="hybrid", action="store_false",
                        help="只写 dense 单向量（V6 形态）；默认写 dense+bm25 混合集合")
    parser.set_defaults(hybrid=True)
    args = parser.parse_args()

    # ---- 增量模式目标解析 ----
    target_ids: set[str] = set()
    if args.product_ids:
        target_ids |= {x.strip() for x in args.product_ids.split(",") if x.strip()}
    if args.product_ids_file:
        target_ids |= {ln.strip() for ln in Path(args.product_ids_file).read_text(
            encoding="utf-8").splitlines() if ln.strip()}
    incremental = bool(target_ids)
    if incremental and args.recreate:
        raise SystemExit("--recreate 与增量模式互斥（会删掉其余商品的块）")

    repo = JsonProductRepository()
    products = repo.list_all()
    if incremental:
        found = {p.product_id for p in products}
        missing = target_ids - found
        if missing:
            raise SystemExit(f"以下 product_id 不存在于数据集: {sorted(missing)}")
        products = [p for p in products if p.product_id in target_ids]
        print(f"增量模式：{len(products)} 件商品 → 集合 '{args.collection}'")
    else:
        if args.limit:
            products = products[: args.limit]
        print(f"加载 {len(products)} 件产品 → 集合 '{args.collection}'")

    all_chunks = []
    for p in products:
        all_chunks.extend(build_chunks(p))

    type_counts: dict[str, int] = {}
    for c in all_chunks:
        type_counts[c.chunk_type] = type_counts.get(c.chunk_type, 0) + 1
    print(f"生成 {len(all_chunks)} 个块: {type_counts}")

    embeddings = await _embed_all([c.text for c in all_chunks], args.batch_size)
    if len(embeddings) != len(all_chunks):
        raise RuntimeError(f"向量数({len(embeddings)}) != 块数({len(all_chunks)})")

    # ---- BM25 稀疏向量（混合检索词面侧，spec §1.2）----
    sparse_vecs: list[tuple[list[int], list[float]]] = []
    if args.hybrid:
        from app.retrieval import sparse_encoder as _se

        if incremental:
            # 增量：复用已有语料统计（否则 df/idf 会被少量文档带偏）
            _se.reset_stats_cache()
            stats = _se.load_stats()
            print(f"  BM25: 复用已有语料统计（{stats.n_docs} 文档 / {len(stats.df)} 词项）")
        else:
            stats = _se.build_corpus_stats([c.text for c in all_chunks])
            p = _se.save_stats(stats)
            print(f"  BM25: 语料统计已建 {stats.n_docs} 文档 / {len(stats.df)} 词项 → {p.name}")
            _se.reset_stats_cache()
        sparse_vecs = [_se.encode_document(c.text, stats) for c in all_chunks]
        _empty = sum(1 for i, _ in sparse_vecs if not i)
        print(f"  BM25: 稀疏向量 {len(sparse_vecs)} 个（空向量 {_empty} 个）")

    # ---- 写入 Qdrant ----
    if not args.local_only and USE_QDRANT and QDRANT_URL:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        client = QdrantClient(url=QDRANT_URL, timeout=60.0)
        ensure_chunk_collection(client, args.collection, EMBEDDING_DIMENSION, args.recreate,
                                hybrid=args.hybrid)

        # 增量模式：先删目标商品的旧块（商品 FAQ/评价变少时，uuid5 幂等 upsert
        # 不会自动清理多余块 → 会遗留孤儿点）
        if incremental:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            client.delete(
                collection_name=args.collection,
                points_selector=Filter(must=[FieldCondition(
                    key="product_id", match=MatchAny(any=sorted(target_ids)))]),
                wait=True,
            )
            print(f"  已清理 {len(target_ids)} 个商品的旧块")

        if args.hybrid:
            # V7 双向量：命名 dense（语义）+ 稀疏 bm25（词面）
            from qdrant_client.models import SparseVector

            points = []
            for c, vec, (s_idx, s_val) in zip(all_chunks, embeddings, sparse_vecs, strict=True):
                vectors: dict = {"dense": vec}
                if s_idx:  # 空稀疏向量不写（Qdrant 不接受空 indices）
                    vectors["bm25"] = SparseVector(indices=s_idx, values=s_val)
                points.append(PointStruct(id=chunk_point_id(c.chunk_id), vector=vectors,
                                         payload=c.to_qdrant_payload()))
        else:
            points = [
                PointStruct(id=chunk_point_id(c.chunk_id), vector=vec, payload=c.to_qdrant_payload())
                for c, vec in zip(all_chunks, embeddings, strict=True)
            ]
        for i in range(0, len(points), UPSERT_BATCH):
            # V6: wait=False 提吞吐，收尾再用 wait=True + 点数校验保一致性
            last = i + UPSERT_BATCH >= len(points)
            client.upsert(collection_name=args.collection, points=points[i : i + UPSERT_BATCH],
                          wait=last)
            print(f"\r  Qdrant 写入: {min(i + UPSERT_BATCH, len(points))}/{len(points)}", end="", flush=True)
        print()
        cnt = client.get_collection(args.collection).points_count
        client.close()
        print(f"  Qdrant 完成: 集合点数 = {cnt}")
        if incremental:
            # 增量模式下校验目标商品的块数（全库点数含其余商品，不能直接比）
            print(f"  增量写入 {len(points)} 块（目标商品 {len(products)} 件）")
        elif cnt != len(points):
            raise RuntimeError(f"点数校验失败: 集合 {cnt} != 块数 {len(points)}")
    else:
        print(f"跳过 Qdrant 写入 ({'--local-only' if args.local_only else 'QDRANT 未配置'})")

    # ---- 本地缓存（降级路径）----
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    new_entries = [
        {
            "chunk_id": c.chunk_id,
            "product_id": c.product_id,
            "chunk_type": c.chunk_type,
            "payload": c.to_qdrant_payload(),
            "embedding": embeddings[i],
        }
        for i, c in enumerate(all_chunks)
    ]

    if incremental and CACHE_FILE.exists():
        # 增量：旧缓存中剔除目标商品的块，合并新块（与 Qdrant 删旧+写新对齐）
        old = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        kept = [ch for ch in old.get("chunks", []) if ch.get("product_id") not in target_ids]
        merged_chunks = kept + new_entries
        type_counts = {}
        pids = set()
        for ch in merged_chunks:
            type_counts[ch["chunk_type"]] = type_counts.get(ch["chunk_type"], 0) + 1
            pids.add(ch["product_id"])
        cache = {
            "dimension": EMBEDDING_DIMENSION,
            "count": len(merged_chunks),
            "product_count": len(pids),
            "chunk_type_counts": type_counts,
            "collection": args.collection,
            "chunks": merged_chunks,
        }
        print(f"本地缓存增量合并: 保留 {len(kept)} + 新写 {len(new_entries)} = {len(merged_chunks)} 块")
    else:
        cache = {
            "dimension": EMBEDDING_DIMENSION,
            "count": len(all_chunks),
            "product_count": len(products),
            "chunk_type_counts": type_counts,
            "collection": args.collection,
            "chunks": new_entries,
        }
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"本地缓存: {CACHE_FILE} ({CACHE_FILE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    asyncio.run(main_async())
