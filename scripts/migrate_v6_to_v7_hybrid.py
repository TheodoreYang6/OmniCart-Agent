#!/usr/bin/env python3
"""V6 → V7 混合集合迁移：复用已有 dense 向量，仅新增 BM25 稀疏向量。

spec: 混合检索与四bug根治 §1.2（实施优化）

为什么不用 index_product_chunks.py --recreate：本地 embedding 重算 10066 块需约 4 小时
（V6 时期是 API 并发路径，现本地模型串行）。dense 向量在 v6 集合里已经存在且与
V7 完全同源（同模型、同 chunk schema），scroll 出来直接搬即可——省掉全部 embedding，
只补词面侧稀疏向量。

用法（仓库根）：
    PYTHONPATH=backend python scripts/migrate_v6_to_v7_hybrid.py
    PYTHONPATH=backend python scripts/migrate_v6_to_v7_hybrid.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

SRC = "product_chunks_v6_1024"
DST = "product_chunks_v7_hybrid"
BATCH = 256


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--dst", default=DST)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, SparseVector

    from app.core.config import EMBEDDING_DIMENSION, QDRANT_URL
    from app.retrieval import sparse_encoder as se

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from index_product_chunks import ensure_chunk_collection

    client = QdrantClient(url=QDRANT_URL, timeout=120.0)
    src_count = client.get_collection(args.src).points_count
    print(f"源集合 {args.src}: {src_count} 点 → 目标 {args.dst}（复用 dense + 补 bm25）")

    # 1) 全量 scroll 取出 payload（用于建 BM25 语料统计）与 dense 向量
    points_raw: list = []
    offset = None
    while True:
        batch, offset = client.scroll(args.src, limit=BATCH, offset=offset,
                                     with_payload=True, with_vectors=True)
        points_raw.extend(batch)
        print(f"\r  读取: {len(points_raw)}/{src_count}", end="", flush=True)
        if offset is None:
            break
    print()

    texts = [(p.payload or {}).get("text", "") for p in points_raw]
    stats = se.build_corpus_stats(texts)
    print(f"  BM25 语料统计: {stats.n_docs} 文档 / {len(stats.df)} 词项 / avgdl={stats.avgdl:.1f}")
    if args.dry_run:
        print("  [dry-run] 未写入")
        return 0
    se.save_stats(stats)
    se.reset_stats_cache()

    # 2) 建混合集合 + 逐批写入（dense 搬运 + sparse 新算）
    ensure_chunk_collection(client, args.dst, EMBEDDING_DIMENSION, recreate=True, hybrid=True)

    written = 0
    for i in range(0, len(points_raw), BATCH):
        chunk = points_raw[i : i + BATCH]
        pts = []
        for p in chunk:
            vec = p.vector
            # v6 为匿名向量（list）；兼容已命名情况
            dense = vec if isinstance(vec, list) else (vec or {}).get("dense") or next(
                iter((vec or {}).values()), None)
            if not dense:
                continue
            payload = p.payload or {}
            s_idx, s_val = se.encode_document(payload.get("text", ""), stats)
            vectors: dict = {"dense": dense}
            if s_idx:
                vectors["bm25"] = SparseVector(indices=s_idx, values=s_val)
            pts.append(PointStruct(id=p.id, vector=vectors, payload=payload))
        last = i + BATCH >= len(points_raw)
        client.upsert(collection_name=args.dst, points=pts, wait=last)
        written += len(pts)
        print(f"\r  写入: {written}/{len(points_raw)}", end="", flush=True)
    print()

    cnt = client.get_collection(args.dst).points_count
    print(f"  完成: {args.dst} 点数 = {cnt}")
    if cnt != src_count:
        print(f"  ⚠️ 点数不一致（源 {src_count}）——请检查")
        return 1
    client.close()
    print("迁移成功：dense 复用 + bm25 稀疏向量已就位")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
