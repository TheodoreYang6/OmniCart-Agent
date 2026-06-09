#!/usr/bin/env python
"""V3 Baseline 对比脚本 — 支持产品级检索 vs 分块检索对比。

用法:
  python scripts/run_baseline.py                    # 默认产品级检索
  python scripts/run_baseline.py --chunked           # 块级检索
  python scripts/run_baseline.py --compare           # 两种方式并排对比
  python scripts/run_baseline.py --limit 5           # 只测前 5 条
  python scripts/run_baseline.py --scenario 数码电子  # 按品类过滤
"""

import argparse
import asyncio
import json
import time
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

# Windows asyncio 兼容
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

_GOLDEN_PATH = PROJECT_DIR / "data" / "golden_queries.json"

_GOLDEN_FALLBACK = [
    {"query_id": "X001", "user_query": "推荐一款蓝牙耳机，预算500以内", "expected_category": "数码电子", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X002", "user_query": "适合夏天用的防晒霜", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X003", "user_query": "跑步穿的透气运动鞋", "expected_category": "服饰运动", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X004", "user_query": "推荐一款咖啡豆", "expected_category": "食品饮料", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X005", "user_query": "适合送女朋友的口红", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X006", "user_query": "出差用的充电宝，要能带上飞机", "expected_category": "数码电子", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X007", "user_query": "100元以内的T恤", "expected_category": "服饰运动", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X008", "user_query": "好吃的坚果零食", "expected_category": "食品饮料", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X009", "user_query": "适合油皮的洗面奶", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X010", "user_query": "手机快充头推荐", "expected_category": "数码电子", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
]


def _load_golden():
    if _GOLDEN_PATH.exists():
        try:
            data = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    return _GOLDEN_FALLBACK


def _format_time(ms: float) -> str:
    return f"{ms:.0f}ms"


def _calc_metrics(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms", 0) > 0]
    r10_vals = [r.get("recall_at_10") for r in results if r.get("recall_at_10") is not None]
    mrr_vals = [r.get("mrr") for r in results if r.get("mrr") is not None]
    ndcg_vals = [r.get("ndcg_at_10") for r in results if r.get("ndcg_at_10") is not None]

    m = {
        "total": total, "passed": passed,
        "pass_rate": f"{passed}/{total} ({passed / max(total, 1) * 100:.1f}%)",
        "avg_latency_ms": f"{sum(latencies) / max(len(latencies), 1):.0f}",
        "avg_products": f"{sum(r.get('product_count', 0) for r in results) / max(total, 1):.1f}",
        "category_accuracy": f"{sum(1 for r in results if r.get('category_match')) / max(total, 1) * 100:.1f}%",
    }
    if r10_vals:
        m["avg_recall_at_10"] = f"{sum(r10_vals) / len(r10_vals) * 100:.1f}%"
    if mrr_vals:
        m["avg_mrr"] = f"{sum(mrr_vals) / len(mrr_vals):.3f}"
    if ndcg_vals:
        m["avg_ndcg_at_10"] = f"{sum(ndcg_vals) / len(ndcg_vals):.3f}"

    return m


async def run_queries(queries: list[dict], chunked: bool, aggregation: str) -> list[dict]:
    from app.repositories.product_repo import get_product_repo
    from app.retrieval.text_retriever import TextRetriever
    from app.eval.metrics import recall_at_k, mrr, ndcg_at_k

    repo = get_product_repo()
    retriever = TextRetriever(repo)
    results = []

    label = "分块检索" if chunked else "产品检索"
    for i, gq in enumerate(queries):
        query = gq.get("user_query", gq.get("query", ""))
        expected_category = gq.get("expected_category", "")
        min_products = gq.get("min_products", 1)
        relevant = set(gq.get("relevant_products", []))
        grades = gq.get("relevance_grades", {})

        t0 = time.time()
        try:
            if chunked:
                retrieved = await retriever.search_chunked(
                    query, top_k=10, aggregation=aggregation,
                )
            else:
                retrieved = await retriever.search(query, top_k=10)

            latency = (time.time() - t0) * 1000
            categories = {p.get("category", "") for p in retrieved}
            cat_match = expected_category in categories or any(
                expected_category[:2] in c for c in categories
            )
            enough = len(retrieved) >= min_products
            retrieved_ids = [p["product_id"] for p in retrieved]

            result = {
                "query": query,
                "expected_category": expected_category,
                "category_match": cat_match,
                "product_count": len(retrieved),
                "min_required": min_products,
                "enough_products": enough,
                "passed": cat_match and enough,
                "latency_ms": round(latency),
                "categories_found": list(categories),
            }
            if relevant:
                result["recall_at_10"] = round(recall_at_k(retrieved_ids, relevant, 10), 4)
                result["mrr"] = round(mrr(retrieved_ids, relevant), 4)
            if grades:
                result["ndcg_at_10"] = round(ndcg_at_k(retrieved_ids, grades, 10), 4)

            results.append(result)

            status = "PASS" if result["passed"] else "FAIL"
            extras = ""
            if "recall_at_10" in result:
                extras += f" | R@10: {result['recall_at_10']*100:.0f}%"
            if "mrr" in result:
                extras += f" | MRR: {result['mrr']:.3f}"
            print(f"  [{label}] {status} | 品类: {list(categories)} | 结果数: {len(retrieved)} | {_format_time(latency)}{extras}")

        except Exception as e:
            latency = (time.time() - t0) * 1000
            results.append({
                "query": query, "passed": False, "product_count": 0,
                "latency_ms": round(latency), "error": str(e),
            })
            print(f"  [{label}] FAIL | Error: {e}")

    return results


async def main():
    parser = argparse.ArgumentParser(description="OmniCart Agent Baseline 评测")
    parser.add_argument("--limit", type=int, default=0, help="最多测试 N 条 query")
    parser.add_argument("--scenario", type=str, default="", help="只测特定场景（匹配 expected_category）")
    parser.add_argument("--chunked", action="store_true", help="使用块级检索")
    parser.add_argument("--aggregation", type=str, default="max_score", help="块聚合策略: max_score | weighted")
    parser.add_argument("--compare", action="store_true", help="并排对比产品检索 vs 块检索")
    args = parser.parse_args()

    golden = _load_golden()
    queries = golden
    if args.scenario:
        queries = [q for q in queries if args.scenario in q.get("expected_category", "")]
    if args.limit > 0:
        queries = queries[:args.limit]

    print(f"\n{'='*60}")
    print(f"OmniCart Agent V3 Baseline 评测")
    print(f"测试条数: {len(queries)}")
    print(f"{'='*60}\n")

    if args.compare:
        # 并排对比
        print(">>> 产品级检索 (default)\n")
        results_default = await run_queries(queries, chunked=False, aggregation=args.aggregation)

        print(f"\n{'─'*60}\n")
        print(">>> 块级检索 (chunked, aggregation={})\n".format(args.aggregation))
        results_chunked = await run_queries(queries, chunked=True, aggregation=args.aggregation)

        print(f"\n{'='*60}")
        print("对比汇总")
        print(f"{'='*60}")
        print(f"\n{'指标':<20} {'产品检索':<25} {'块检索':<25}")
        print(f"{'─'*70}")

        m1 = _calc_metrics(results_default)
        m2 = _calc_metrics(results_chunked)
        for key in m1:
            v1 = m1.get(key, "--")
            v2 = m2.get(key, "--")
            print(f"{key:<20} {v1:<25} {v2:<25}")

        # 保存对比结果
        out = PROJECT_DIR / "data" / "baseline_compare.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "default": {"summary": m1, "details": results_default},
            "chunked": {"summary": m2, "details": results_chunked},
        }, ensure_ascii=False, indent=2))
        print(f"\n对比结果已保存至: {out}")
    else:
        results = await run_queries(queries, chunked=args.chunked, aggregation=args.aggregation)

        print(f"\n{'='*60}")
        print("评测汇总")
        print(f"{'='*60}")
        summary = _calc_metrics(results)
        for k, v in summary.items():
            print(f"  {k}: {v}")

        out = PROJECT_DIR / "data" / "baseline_results.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "details": results}, ensure_ascii=False, indent=2))
        print(f"\n结果已保存至: {out}")


if __name__ == "__main__":
    asyncio.run(main())
