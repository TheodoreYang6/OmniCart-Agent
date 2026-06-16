"""Evaluation API — 检索评测 + RAG生成评测 + 参数实验。

检索指标: Recall@K / MRR / NDCG@K
RAG指标: Faithfulness / Context Precision / Context Recall
"""

import asyncio
import itertools
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

_EVAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "eval_runs"
_EVAL_DIR.mkdir(parents=True, exist_ok=True)

_GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "golden_queries.json"

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


# ── RAG 生成侧评测 ──────────────────────────────────────────────

_RAG_EVAL_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "rag_eval_dataset.json"
_RAG_EVAL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "rag_eval_runs"
_RAG_EVAL_DIR.mkdir(parents=True, exist_ok=True)


def _load_rag_dataset() -> list[dict]:
    if _RAG_EVAL_PATH.exists():
        try:
            data = json.loads(_RAG_EVAL_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass
    return []


# 共享的检索+生成基础设施, 避免每次 query 重复创建
_rag_retriever = None
_rag_repo = None


def _get_rag_retriever():
    global _rag_retriever, _rag_repo
    if _rag_retriever is None:
        from app.repositories.product_repo import get_product_repo
        from app.retrieval.text_retriever import TextRetriever
        _rag_repo = get_product_repo()
        _rag_retriever = TextRetriever(_rag_repo)
    return _rag_retriever, _rag_repo


async def _do_retrieve_and_generate(
    user_query: str,
    top_k: int,
    context_products: int,
    gateway,
) -> tuple[list[dict], str]:
    """执行检索+生成, 返回 (retrieved_products, answer)。"""
    from app.eval.rag_metrics import _build_response_context

    retriever, repo = _get_rag_retriever()

    # 检索
    if repo.total_count > 0:
        retrieved = await retriever.search_chunked(query=user_query, top_k=top_k)
    else:
        retrieved = await retriever.search(user_query, top_k=top_k)

    # 生成
    answer = ""
    try:
        context_prompt = _build_response_context(retrieved, user_query, context_products)
        answer = await gateway.chat("chat_generation",
            f"{context_prompt}\n\n请基于以上候选商品为用户推荐合适的商品。"
            f"引用具体证据(品牌/价格/功能/评价), 200字以内。")
    except Exception:
        if retrieved:
            top = retrieved[0]
            answer = f"为您推荐{top.get('brand','')}{top.get('title','')}，价格¥{top.get('price',0)}。"
        else:
            answer = "抱歉，未找到匹配的商品。"

    return retrieved, answer


@router.post("/api/eval/rag/run")
async def run_rag_eval(
    top_k: int = Query(10, ge=1, le=30, description="候选商品数"),
    enable_rerank: bool = Query(True, description="是否启用Reranker"),
    context_products: int = Query(5, ge=1, le=10, description="送入Response LLM的候选商品数"),
    dataset_limit: int = Query(0, ge=0, le=200, description="限制数据集条数, 0=全部"),
):
    """运行 RAG 全链路评测 — 6项指标 (3检索 + 3生成)。

    GET /api/eval/rag/run?top_k=10&context_products=5
    """
    from app.eval.rag_metrics import evaluate_one, compute_retrieval_metrics
    from app.model_gateway.gateway import get_model_gateway

    dataset = _load_rag_dataset()
    if not dataset:
        return {"error": "rag_eval_dataset.json not found or empty"}

    if dataset_limit > 0:
        dataset = dataset[:dataset_limit]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-rag-" + uuid.uuid4().hex[:4]
    gateway = get_model_gateway()
    results = []

    for gq in dataset:
        user_query = gq.get("user_query", "")
        t0 = time.perf_counter()

        try:
            retrieved, answer = await _do_retrieve_and_generate(
                user_query, top_k, context_products, gateway,
            )

            # Rerank模拟: 截断候选列表
            if enable_rerank and len(retrieved) > context_products:
                retrieved = retrieved[:context_products]

            eval_result = await evaluate_one(
                query_data=gq,
                state_or_products=retrieved,
                answer=answer,
                gateway=gateway,
            )
            eval_result["latency_ms"] = round((time.perf_counter() - t0) * 1000)
            results.append(eval_result)

        except Exception as e:
            logger.error(f"RAG eval failed for {gq.get('query_id','?')}: {e}")
            results.append({
                "query_id": gq.get("query_id", ""),
                "user_query": gq.get("user_query", ""),
                "error": str(e),
                "faithfulness": 0.0, "context_precision": 0.0, "context_recall": 0.0,
                "recall_at_5": 0.0, "recall_at_10": 0.0, "mrr": 0.0, "ndcg_at_10": 0.0,
            })

    # 汇总
    total = len(results)
    def _avg(key): return round(sum(r.get(key, 0) for r in results) / max(total, 1), 4)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {"top_k": top_k, "enable_rerank": enable_rerank, "context_products": context_products},
        "total_queries": total,
        # 检索指标
        "avg_recall_at_5": _avg("recall_at_5"),
        "avg_recall_at_10": _avg("recall_at_10"),
        "avg_mrr": _avg("mrr"),
        "avg_ndcg_at_10": _avg("ndcg_at_10"),
        # 生成指标
        "avg_faithfulness": _avg("faithfulness"),
        "avg_context_precision": _avg("context_precision"),
        "avg_context_recall": _avg("context_recall"),
        "avg_latency_ms": round(sum(r.get("latency_ms", 0) for r in results) / max(total, 1)),
        "details": results,
    }

    fp = _RAG_EVAL_DIR / f"{run_id}.json"
    fp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


@router.post("/api/eval/rag/experiment")
async def run_rag_experiment(
    dataset_limit: int = Query(0, ge=0, le=200, description="限制数据集条数, 0=全部"),
):
    """RAG 参数网格搜索实验 — top_k × rerank × context_products 全组合。

    参数网格: top_k ∈ {3,5,10,20} × rerank ∈ {true,false} × context ∈ {3,5,10}
    共 4×2×3 = 24 组, 按综合得分 = faith×0.4 + precision×0.2 + recall×0.4 排名。
    """
    from app.eval.rag_metrics import evaluate_one
    from app.model_gateway.gateway import get_model_gateway

    dataset = _load_rag_dataset()
    if not dataset:
        return {"error": "rag_eval_dataset.json not found or empty"}

    if dataset_limit > 0:
        dataset = dataset[:dataset_limit]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-exp-" + uuid.uuid4().hex[:4]
    gateway = get_model_gateway()

    top_k_values = [3, 5, 10, 20]
    rerank_values = [True, False]
    context_values = [3, 5, 10]

    configs = list(itertools.product(top_k_values, rerank_values, context_values))
    total_experiments = len(configs) * len(dataset)

    experiment_results = []
    best_config = None
    best_composite = -1.0

    for top_k, rerank, ctx_n in configs:
        config_label = f"topk={top_k}_rerank={rerank}_ctx={ctx_n}"
        logger.info(f"实验 [{config_label}] 开始 ({len(dataset)} queries)...")

        config_results = []
        for gq in dataset:
            user_query = gq.get("user_query", "")
            t0 = time.perf_counter()

            try:
                retrieved, answer = await _do_retrieve_and_generate(
                    user_query, top_k, ctx_n, gateway,
                )

                if rerank and len(retrieved) > ctx_n:
                    retrieved = retrieved[:ctx_n]

                eval_result = await evaluate_one(
                    query_data=gq, state_or_products=retrieved,
                    answer=answer, gateway=gateway,
                )
                eval_result["latency_ms"] = round((time.perf_counter() - t0) * 1000)
                config_results.append(eval_result)
            except Exception as e:
                config_results.append({
                    "query_id": gq.get("query_id", ""),
                    "error": str(e),
                    "faithfulness": 0.0, "context_precision": 0.0, "context_recall": 0.0,
                    "recall_at_5": 0.0, "recall_at_10": 0.0, "mrr": 0.0, "ndcg_at_10": 0.0,
                })

        def _avg(key): return round(sum(r.get(key, 0) for r in config_results) / max(len(config_results), 1), 4)

        avg_f = _avg("faithfulness")
        avg_p = _avg("context_precision")
        avg_r = _avg("context_recall")

        composite = round(avg_f * 0.4 + avg_p * 0.2 + avg_r * 0.4, 4)

        exp_entry = {
            "config": {"top_k": top_k, "enable_rerank": rerank, "context_products": ctx_n},
            "config_label": config_label,
            "avg_faithfulness": avg_f,
            "avg_context_precision": avg_p,
            "avg_context_recall": avg_r,
            "avg_recall_at_5": _avg("recall_at_5"),
            "avg_recall_at_10": _avg("recall_at_10"),
            "avg_mrr": _avg("mrr"),
            "avg_ndcg_at_10": _avg("ndcg_at_10"),
            "composite_score": composite,
            "avg_latency_ms": round(sum(r.get("latency_ms", 0) for r in config_results) / max(len(config_results), 1)),
            "query_count": len(dataset),
        }
        experiment_results.append(exp_entry)

        if composite > best_composite:
            best_composite = composite
            best_config = exp_entry

    experiment_results.sort(key=lambda x: x["composite_score"], reverse=True)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_size": len(dataset),
        "total_configs": len(configs),
        "total_evaluations": total_experiments,
        "best_config": best_config,
        "all_results": experiment_results,
    }

    fp = _RAG_EVAL_DIR / f"{run_id}.json"
    fp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


@router.get("/api/eval/rag/results")
async def list_rag_results(limit: int = Query(10, ge=1, le=100)):
    """获取 RAG 评测历史记录"""
    runs = []
    for fp in sorted(_RAG_EVAL_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            runs.append({
                "run_id": data.get("run_id", fp.stem),
                "timestamp": data.get("timestamp", ""),
                "config": data.get("config", {}),
                "total_queries": data.get("total_queries", data.get("dataset_size", 0)),
                "avg_recall_at_5": data.get("avg_recall_at_5"),
                "avg_recall_at_10": data.get("avg_recall_at_10"),
                "avg_mrr": data.get("avg_mrr"),
                "avg_ndcg_at_10": data.get("avg_ndcg_at_10"),
                "avg_faithfulness": data.get("avg_faithfulness"),
                "avg_context_precision": data.get("avg_context_precision"),
                "avg_context_recall": data.get("avg_context_recall"),
                "best_config": data.get("best_config"),
            })
        except Exception:
            pass
    return {"total_runs": len(runs), "runs": runs}


@router.get("/api/eval/rag/results/{run_id}")
async def get_rag_result(run_id: str):
    """获取某次 RAG 评测的完整结果"""
    import re
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
        return {"error": "invalid run_id"}
    fp = _RAG_EVAL_DIR / f"{run_id}.json"
    if not fp.exists():
        return {"error": "run not found"}
    return json.loads(fp.read_text(encoding="utf-8"))
