"""Evaluation API — 运行评测 + 查询结果 + 历史趋势。

V3: 支持块级检索评测 + Recall@K/MRR/NDCG@K 指标。
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter()

_EVAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "eval_runs"
_EVAL_DIR.mkdir(parents=True, exist_ok=True)

_GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "golden_queries.json"

# 硬编码兜底（当 golden_queries.json 不存在时使用）
_GOLDEN_FALLBACK = [
    {"query_id": "X001", "user_query": "推荐一款蓝牙耳机，预算500以内", "expected_category": "数码电子", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"budget_max": 500}},
    {"query_id": "X002", "user_query": "适合夏天用的防晒霜", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"scenario": ["summer"]}},
    {"query_id": "X003", "user_query": "跑步穿的透气运动鞋", "expected_category": "服饰运动", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"scenario": ["running"]}},
    {"query_id": "X004", "user_query": "推荐一款咖啡豆", "expected_category": "食品饮料", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X005", "user_query": "适合送女朋友的口红", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"scenario": ["gift"]}},
    {"query_id": "X006", "user_query": "出差用的充电宝，要能带上飞机", "expected_category": "数码电子", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"scenario": ["business_trip", "flight"]}},
    {"query_id": "X007", "user_query": "100元以内的T恤", "expected_category": "服饰运动", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"budget_max": 100}},
    {"query_id": "X008", "user_query": "好吃的坚果零食", "expected_category": "食品饮料", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {}},
    {"query_id": "X009", "user_query": "适合油皮的洗面奶", "expected_category": "美妆护肤", "min_products": 2, "relevant_products": [], "relevance_grades": {}, "constraints": {"needs": ["oily_skin"]}},
    {"query_id": "X010", "user_query": "手机快充头推荐", "expected_category": "数码电子", "min_products": 1, "relevant_products": [], "relevance_grades": {}, "constraints": {"needs": ["fast_charge"]}},
]


def _load_golden() -> list[dict]:
    if _GOLDEN_PATH.exists():
        try:
            data = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    return _GOLDEN_FALLBACK


class EvalResult(BaseModel):
    run_id: str = ""
    timestamp: str = ""
    method: str = "default"
    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    avg_latency_ms: float = 0
    avg_products: float = 0
    category_accuracy: float = 0
    avg_recall_at_5: float | None = None
    avg_recall_at_10: float | None = None
    avg_mrr: float | None = None
    avg_ndcg_at_10: float | None = None
    details: list = []


@router.post("/api/eval/run")
async def run_eval(
    method: str = Query("default", description="'default' | 'chunked'"),
    aggregation: str = Query("max_score", description="chunk 聚合策略: max_score | weighted"),
):
    """运行全量 golden query 评测并保存结果"""
    from app.repositories.product_repo import get_product_repo
    from app.retrieval.text_retriever import TextRetriever
    from app.eval.metrics import recall_at_k, mrr, ndcg_at_k

    repo = get_product_repo()
    retriever = TextRetriever(repo)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    golden = _load_golden()
    results = []

    for gq in golden:
        query = gq.get("user_query", gq.get("query", ""))
        expected_category = gq.get("expected_category", "")
        min_products = gq.get("min_products", 1)
        relevant = set(gq.get("relevant_products", []))
        grades = gq.get("relevance_grades", {})

        t0 = time.perf_counter()
        try:
            if method == "chunked":
                retrieved = await retriever.search_chunked(
                    query, top_k=10, aggregation=aggregation,
                )
            else:
                retrieved = await retriever.search(query, top_k=10)

            latency = round((time.perf_counter() - t0) * 1000)
            categories = {p.get("category", "") for p in retrieved}
            cat_match = expected_category in categories or any(
                expected_category[:2] in c for c in categories
            )
            enough = len(retrieved) >= min_products
            retrieved_ids = [p["product_id"] for p in retrieved]

            detail = {
                "query_id": gq.get("query_id", ""),
                "query": query,
                "expected_category": expected_category,
                "category_match": cat_match,
                "product_count": len(retrieved),
                "min_required": min_products,
                "enough_products": enough,
                "passed": cat_match and enough,
                "latency_ms": latency,
                "categories_found": list(categories),
                "top_products": [p["title"][:30] for p in retrieved[:3]],
            }

            if relevant:
                detail["recall_at_5"] = round(recall_at_k(retrieved_ids, relevant, 5), 4)
                detail["recall_at_10"] = round(recall_at_k(retrieved_ids, relevant, 10), 4)
                detail["mrr"] = round(mrr(retrieved_ids, relevant), 4)
            if grades:
                detail["ndcg_at_10"] = round(ndcg_at_k(retrieved_ids, grades, 10), 4)

            results.append(detail)
        except Exception as e:
            results.append({
                "query_id": gq.get("query_id", ""),
                "query": query, "passed": False, "product_count": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000), "error": str(e),
            })

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms", 0) > 0]
    has_relevant = any(r.get("recall_at_5") is not None for r in results)
    has_grades = any(r.get("ndcg_at_10") is not None for r in results)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / max(total, 1), 4),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1)),
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0,
        "avg_products": round(sum(r.get("product_count", 0) for r in results) / max(total, 1), 1),
        "category_accuracy": round(sum(1 for r in results if r.get("category_match")) / max(total, 1), 4),
        "details": results,
    }

    if has_relevant:
        r5_vals = [r["recall_at_5"] for r in results if r.get("recall_at_5") is not None]
        r10_vals = [r["recall_at_10"] for r in results if r.get("recall_at_10") is not None]
        mrr_vals = [r["mrr"] for r in results if r.get("mrr") is not None]
        summary["avg_recall_at_5"] = round(sum(r5_vals) / max(len(r5_vals), 1), 4) if r5_vals else None
        summary["avg_recall_at_10"] = round(sum(r10_vals) / max(len(r10_vals), 1), 4) if r10_vals else None
        summary["avg_mrr"] = round(sum(mrr_vals) / max(len(mrr_vals), 1), 4) if mrr_vals else None

    if has_grades:
        ndcg_vals = [r["ndcg_at_10"] for r in results if r.get("ndcg_at_10") is not None]
        summary["avg_ndcg_at_10"] = round(sum(ndcg_vals) / max(len(ndcg_vals), 1), 4) if ndcg_vals else None

    # 保存
    fp = _EVAL_DIR / f"{run_id}.json"
    fp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


@router.get("/api/eval/results")
async def list_results(limit: int = Query(10, ge=1, le=100)):
    """获取历史评测记录列表"""
    runs = []
    for fp in sorted(_EVAL_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            runs.append({
                "run_id": data.get("run_id", fp.stem),
                "timestamp": data.get("timestamp", ""),
                "method": data.get("method", "default"),
                "total": data.get("total", 0),
                "passed": data.get("passed", 0),
                "pass_rate": data.get("pass_rate", 0),
                "avg_latency_ms": data.get("avg_latency_ms", 0),
                "avg_products": data.get("avg_products", 0),
                "category_accuracy": data.get("category_accuracy", 0),
                "avg_recall_at_5": data.get("avg_recall_at_5"),
                "avg_recall_at_10": data.get("avg_recall_at_10"),
                "avg_mrr": data.get("avg_mrr"),
                "avg_ndcg_at_10": data.get("avg_ndcg_at_10"),
            })
        except Exception:
            pass
    return {"total_runs": len(runs), "runs": runs}


@router.get("/api/eval/results/{run_id}")
async def get_result(run_id: str):
    """获取某次评测的完整结果"""
    import re
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
        return {"error": "invalid run_id"}
    fp = _EVAL_DIR / f"{run_id}.json"
    if not fp.exists():
        return {"error": "run not found"}
    return json.loads(fp.read_text(encoding="utf-8"))


@router.get("/api/eval/golden")
async def get_golden_queries():
    """返回 golden queries 列表（从文件加载）"""
    queries = _load_golden()
    return {"total": len(queries), "queries": queries}
