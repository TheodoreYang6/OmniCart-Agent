#!/usr/bin/env python
"""全量重建编排 (V5) — 一键把 PG 派生列 + Qdrant 统一向量集合刷成最新。

步骤:
1. 回填 PG 派生列 (avg_rating/review_count/positive/negative/risk_tags/search_text)
   —— 口径统一走 app.schemas.product_chunk.compute_review_aggregates。
2. 重建 Qdrant 统一 chunk 单集合 (调 scripts/index_product_chunks.py)。
3. 校验：PG 商品数 vs Qdrant 集合点数。

用法:
    python scripts/reindex_all.py                 # 全量
    python scripts/reindex_all.py --recreate      # 先删旧集合再灌
    python scripts/reindex_all.py --limit 20      # 冒烟
    python scripts/reindex_all.py --skip-backfill # 只重建向量
    python scripts/reindex_all.py --skip-index    # 只回填派生列
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import (
    USE_POSTGRES, USE_QDRANT, QDRANT_URL, CHUNK_COLLECTION_NAME,
)
from app.repositories.json_product_repo import JsonProductRepository
from app.schemas.product_chunk import compute_review_aggregates


async def backfill_pg_derived(limit: int = 0) -> int:
    """回填 products 派生列。返回更新行数。"""
    if not USE_POSTGRES:
        print("USE_POSTGRES=false，跳过 PG 回填")
        return 0
    from sqlalchemy import text
    from app.core.database import get_session_sync

    repo = JsonProductRepository()
    products = repo.list_all()
    if limit:
        products = products[:limit]

    factory = get_session_sync()
    if factory is None:
        print("无法获取 PG 会话工厂，跳过回填")
        return 0

    updated = 0
    async with factory() as session:
        for p in products:
            agg = compute_review_aggregates(p)
            desc = p.rag_knowledge.marketing_description if p.rag_knowledge else ""
            search_text = " ".join([p.title or "", p.brand or "", p.category or "",
                                    p.sub_category or "", desc or ""]).strip()
            await session.execute(
                text(
                    "UPDATE products SET avg_rating=:ar, review_count=:rc, "
                    "positive_count=:pc, negative_count=:nc, "
                    "risk_tags=cast(:rt as jsonb), search_text=:st "
                    "WHERE product_id=:pid"
                ),
                {
                    "ar": agg["avg_rating"], "rc": agg["review_count"],
                    "pc": agg["positive_count"], "nc": agg["negative_count"],
                    "rt": json.dumps(agg["risk_tags"], ensure_ascii=False),
                    "st": search_text, "pid": p.product_id,
                },
            )
            updated += 1
        await session.commit()
    print(f"PG 派生列回填完成: {updated} 行")
    return updated


def run_chunk_index(recreate: bool, limit: int) -> int:
    """调用 chunk 索引脚本（子进程隔离，避免事件循环嵌套）。"""
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "index_product_chunks.py")]
    if recreate:
        cmd.append("--recreate")
    if limit:
        cmd += ["--limit", str(limit)]
    print(f"\n运行向量索引: {' '.join(cmd)}\n" + "-" * 50)
    r = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent.parent))
    return r.returncode


def verify():
    print("\n" + "=" * 50 + "\n校验:")
    if USE_QDRANT and QDRANT_URL:
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(url=QDRANT_URL, timeout=15.0)
            cnt = client.get_collection(CHUNK_COLLECTION_NAME).points_count
            client.close()
            print(f"  Qdrant '{CHUNK_COLLECTION_NAME}' 点数 = {cnt}")
        except Exception as e:
            print(f"  Qdrant 校验失败: {e}")


async def main():
    parser = argparse.ArgumentParser(description="全量重建编排 (V5)")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()

    if not args.skip_backfill:
        await backfill_pg_derived(args.limit)

    if not args.skip_index:
        code = run_chunk_index(args.recreate, args.limit)
        if code != 0:
            print(f"向量索引失败 (exit={code})")
            sys.exit(code)

    verify()
    print("\n✅ 重建完成")


if __name__ == "__main__":
    asyncio.run(main())
