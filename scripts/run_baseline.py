#!/usr/bin/env python
"""V1 Baseline 对比脚本 — OmniCart Agent vs 纯 Qwen LLM vs 纯文本检索。

用法:
  python scripts/run_baseline.py                    # 运行全部 golden queries
  python scripts/run_baseline.py --limit 5           # 只测前 5 条
  python scripts/run_baseline.py --scenario shoes    # 只测特定场景
"""

import argparse
import json
import time
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

GOLDEN_QUERIES = [
    {"query": "推荐一款蓝牙耳机，预算500以内", "expected_category": "数码电子", "min_products": 2},
    {"query": "适合夏天用的防晒霜", "expected_category": "美妆护肤", "min_products": 2},
    {"query": "跑步穿的透气运动鞋", "expected_category": "服饰运动", "min_products": 2},
    {"query": "推荐一款咖啡豆", "expected_category": "食品饮料", "min_products": 1},
    {"query": "适合送女朋友的口红", "expected_category": "美妆护肤", "min_products": 2},
    {"query": "出差用的充电宝，要能带上飞机", "expected_category": "数码电子", "min_products": 2},
    {"query": "100元以内的T恤", "expected_category": "服饰运动", "min_products": 2},
    {"query": "好吃的坚果零食", "expected_category": "食品饮料", "min_products": 1},
    {"query": "适合油皮的洗面奶", "expected_category": "美妆护肤", "min_products": 2},
    {"query": "手机快充头推荐", "expected_category": "数码电子", "min_products": 1},
]


def _format_time(ms: float) -> str:
    return f"{ms:.0f}ms"


def evaluate(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_latency = sum(r["latency_ms"] for r in results) / max(total, 1)
    avg_products = sum(r["product_count"] for r in results) / max(total, 1)
    category_accuracy = sum(1 for r in results if r["category_match"]) / max(total, 1)

    return {
        "total": total, "passed": passed, "pass_rate": f"{passed}/{total} ({passed/max(total,1)*100:.1f}%)",
        "avg_latency_ms": f"{avg_latency:.0f}",
        "avg_products": f"{avg_products:.1f}",
        "category_accuracy": f"{category_accuracy*100:.1f}%",
    }


def main():
    parser = argparse.ArgumentParser(description="OmniCart Agent Baseline 评测")
    parser.add_argument("--limit", type=int, default=0, help="最多测试 N 条 query")
    parser.add_argument("--scenario", type=str, default="", help="只测特定场景")
    args = parser.parse_args()

    queries = GOLDEN_QUERIES
    if args.scenario:
        queries = [q for q in queries if args.scenario in q["expected_category"]]
    if args.limit > 0:
        queries = queries[:args.limit]

    print(f"\n{'='*60}")
    print(f"OmniCart Agent Baseline 评测")
    print(f"测试条数: {len(queries)}")
    print(f"{'='*60}\n")

    results = []
    for i, gq in enumerate(queries):
        query = gq["query"]
        print(f"[{i+1}/{len(queries)}] {query[:50]}...")

        t0 = time.time()
        try:
            from app.repositories.product_repo import get_product_repo
            from app.retrieval.text_retriever import HybridRetriever
            from app.model_gateway.gateway import get_model_gateway

            repo = get_product_repo()
            retriever = HybridRetriever(repo)
            gateway = get_model_gateway()

            # OmniCart: Hybrid Search
            retrieved = retriever.hybrid_search(query, top_k=10)
            latency = (time.time() - t0) * 1000

            # 品类匹配检查
            categories = {p.get("category", "") for p in retrieved}
            category_match = gq["expected_category"] in categories or any(
                gq["expected_category"][:2] in c for c in categories
            )
            enough = len(retrieved) >= gq["min_products"]
            passed = category_match and enough

            results.append({
                "query": query,
                "expected_category": gq["expected_category"],
                "category_match": category_match,
                "product_count": len(retrieved),
                "min_required": gq["min_products"],
                "enough_products": enough,
                "passed": passed,
                "latency_ms": round(latency),
                "categories_found": list(categories),
            })

            status = "PASS" if passed else "FAIL"
            print(f"  {status} | 品类: {list(categories)} | 结果数: {len(retrieved)} | 耗时: {_format_time(latency)}")

        except Exception as e:
            latency = (time.time() - t0) * 1000
            results.append({
                "query": query, "passed": False, "product_count": 0,
                "latency_ms": round(latency), "error": str(e),
            })
            print(f"  FAIL | Error: {e}")

    # 汇总
    print(f"\n{'='*60}")
    print("评测汇总")
    print(f"{'='*60}")
    summary = evaluate(results)
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # 保存结果
    out = PROJECT_DIR / "data" / "baseline_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "details": results}, ensure_ascii=False, indent=2))
    print(f"\n结果已保存至: {out}")


if __name__ == "__main__":
    main()
