"""Evaluation API — 运行评测 + 查询结果 + 历史趋势"""

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

# 评测数据目录
_EVAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "eval_runs"
_EVAL_DIR.mkdir(parents=True, exist_ok=True)

# Golden queries — 10 条覆盖 4 品类
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


class EvalResult(BaseModel):
    run_id: str = ""
    timestamp: str = ""
    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    avg_latency_ms: float = 0
    avg_products: float = 0
    category_accuracy: float = 0
    details: list = []


@router.post("/api/eval/run")
async def run_eval():
    """运行全量 golden query 评测并保存结果"""
    from app.repositories.product_repo import get_product_repo
    from app.retrieval.text_retriever import TextRetriever

    repo = get_product_repo()
    retriever = TextRetriever(repo)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    results = []

    for gq in GOLDEN_QUERIES:
        query = gq["query"]
        t0 = time.perf_counter()
        try:
            retrieved = await retriever.search(query, top_k=10)
            latency = round((time.perf_counter() - t0) * 1000)
            categories = {p.get("category", "") for p in retrieved}
            cat_match = gq["expected_category"] in categories or any(
                gq["expected_category"][:2] in c for c in categories
            )
            enough = len(retrieved) >= gq["min_products"]
            results.append({
                "query": query,
                "expected_category": gq["expected_category"],
                "category_match": cat_match,
                "product_count": len(retrieved),
                "min_required": gq["min_products"],
                "enough_products": enough,
                "passed": cat_match and enough,
                "latency_ms": latency,
                "categories_found": list(categories),
                "top_products": [p["title"][:30] for p in retrieved[:3]],
            })
        except Exception as e:
            results.append({
                "query": query, "passed": False, "product_count": 0,
                "latency_ms": round((time.perf_counter() - t0) * 1000), "error": str(e),
            })

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / max(total, 1), 4),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1)),
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0,
        "avg_products": round(sum(r.get("product_count", 0) for r in results) / max(total, 1), 1),
        "category_accuracy": round(sum(1 for r in results if r.get("category_match")) / max(total, 1), 4),
        "details": results,
    }

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
                "total": data.get("total", 0),
                "passed": data.get("passed", 0),
                "pass_rate": data.get("pass_rate", 0),
                "avg_latency_ms": data.get("avg_latency_ms", 0),
                "avg_products": data.get("avg_products", 0),
                "category_accuracy": data.get("category_accuracy", 0),
            })
        except Exception:
            pass
    return {"total_runs": len(runs), "runs": runs}


@router.get("/api/eval/results/{run_id}")
async def get_result(run_id: str):
    """获取某次评测的完整结果"""
    fp = _EVAL_DIR / f"{run_id}.json"
    if not fp.exists():
        return {"error": "run not found"}
    return json.loads(fp.read_text(encoding="utf-8"))


@router.get("/api/eval/golden")
async def get_golden_queries():
    """返回 golden queries 列表"""
    return {"total": len(GOLDEN_QUERIES), "queries": GOLDEN_QUERIES}
