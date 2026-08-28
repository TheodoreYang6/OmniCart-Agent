#!/usr/bin/env python
"""Evaluate the review-free v8 discovery collection before enabling it.

This creates a repeatable 240-case, full-category identity/discovery baseline:
15 evenly sampled products × two natural catalogue queries across eight
categories.  It deliberately measures only candidate recall; evidence quality
is evaluated after candidates are locked, not mixed into this metric.

Usage (run in the configured backend service environment)::

    $env:OMNICART_USE_DISCOVERY_V8='true'
    PYTHONPATH=backend python scripts/evaluate_discovery_v8.py --tag shadow-v8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

SAMPLE_PER_CATEGORY = 15
TOP_K = 10


def build_cases() -> list[dict]:
    from app.repositories.json_product_repo import JsonProductRepository

    by_category: dict[str, list] = {}
    for product in JsonProductRepository().list_all():
        by_category.setdefault(product.category, []).append(product)
    cases: list[dict] = []
    for category, products in sorted(by_category.items()):
        step = max(1, len(products) // SAMPLE_PER_CATEGORY)
        for product in products[::step][:SAMPLE_PER_CATEGORY]:
            # The first is an identity-like discovery request; the second is a
            # category/brand shopping request.  Both must find the catalogue
            # product in the top ten without relying on a review chunk.
            cases.extend((
                {"kind": "identity", "query": f"{product.brand} {product.title}",
                 "category": category, "expect_pid": product.product_id},
                {"kind": "shopping", "query": f"{product.brand} {product.sub_category}",
                 "category": category, "expect_pid": product.product_id},
            ))
    return cases


async def run(tag: str) -> dict:
    from app.core.config import USE_DISCOVERY_V8, USE_QDRANT
    from app.repositories.json_product_repo import JsonProductRepository
    from app.retrieval.discovery_retriever import DiscoveryRetriever

    if not (USE_DISCOVERY_V8 and USE_QDRANT):
        raise RuntimeError("Set OMNICART_USE_DISCOVERY_V8=true and configure Qdrant before evaluating v8")
    cases = build_cases()
    retriever = DiscoveryRetriever(JsonProductRepository())
    hits, misses = 0, []
    t0 = time.perf_counter()
    for index, case in enumerate(cases, 1):
        products, report = await retriever.search(case["query"], category=case["category"], top_k=TOP_K)
        pids = [item.get("product_id") for item in products]
        if case["expect_pid"] in pids:
            hits += 1
        else:
            misses.append({**case, "got": pids[:5], "filter": report})
        if index % 40 == 0:
            print(f"{index}/{len(cases)}")
    return {
        "tag": tag,
        "cases": len(cases),
        "discovery_recall@10": round(hits / max(len(cases), 1), 4),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "miss_count": len(misses),
        "misses_sample": misses[:30],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--show-case-count", action="store_true")
    args = parser.parse_args()
    if args.show_case_count:
        print(len(build_cases()))
        return
    report = asyncio.run(run(args.tag))
    out = ROOT / "data" / "rag_eval_runs" / f"discovery-v8-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "misses_sample"}, ensure_ascii=False, indent=2))
    print(f"报告: {out}")


if __name__ == "__main__":
    main()
