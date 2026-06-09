"""RAG 全链路日志 — embedding → rerank → 最终候选，结构化 JSON 输出。

每轮对话写入一条 RAG trace 到 data/rag_traces.jsonl。
支持后续用脚本分析命中率、MRR、NDCG 等指标。
"""

import json
import time
from pathlib import Path
from typing import Any

_LOG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "rag_traces.jsonl"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_eval_queries: list[dict] = []  # 评测用的 golden set，启动时加载


def load_eval_queries():
    """加载评测 golden queries（data/eval_queries.json）。"""
    global _eval_queries
    eval_file = _LOG_PATH.parent / "eval_queries.json"
    if eval_file.exists():
        try:
            _eval_queries = json.loads(eval_file.read_text("utf-8"))
        except Exception:
            _eval_queries = []
    return _eval_queries


class RagTrace:
    """单次 RAG 调用的完整链路记录。"""

    def __init__(self, session_id: str = "", query: str = ""):
        self.trace = {
            "session_id": session_id,
            "query": query,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "embedding": {"query_vec_dims": 0, "candidates": [], "latency_ms": 0},
            "reranker": {"input_count": 0, "candidates": [], "scores": [], "latency_ms": 0},
            "final_top5": [],
            "evaluation": {},
        }

    def set_embedding(self, query_vec: list, candidates: list[dict], latency_ms: int):
        self.trace["embedding"]["query_vec_dims"] = len(query_vec) if query_vec else 0
        self.trace["embedding"]["latency_ms"] = latency_ms
        self.trace["embedding"]["candidates"] = [
            {
                "rank": i + 1,
                "product_id": c.get("product_id", ""),
                "title": (c.get("title") or "")[:60],
                "brand": c.get("brand", ""),
                "price": c.get("price", 0),
                "score": c.get("score", 0),
            }
            for i, c in enumerate(candidates[:15])
        ]

    def set_reranker(self, input_products: list[dict], ranked: list[dict], scores: list[float], latency_ms: int):
        self.trace["reranker"]["input_count"] = len(input_products)
        self.trace["reranker"]["latency_ms"] = latency_ms
        self.trace["reranker"]["candidates"] = [
            {
                "rank": i + 1,
                "product_id": p.get("product_id", ""),
                "title": (p.get("title") or "")[:60],
                "brand": p.get("brand", ""),
                "price": p.get("price", 0),
            }
            for i, p in enumerate(ranked[:10])
        ]
        self.trace["reranker"]["scores"] = [round(s, 4) for s in scores[:10]]

    def set_final(self, products: list[dict], decisions: list[dict]):
        self.trace["final_top5"] = []
        for i, p in enumerate(products[:5]):
            pid = p.get("product_id", "")
            dec = None
            for d in decisions:
                if d.get("product_id") == pid:
                    dec = d
                    break
            self.trace["final_top5"].append({
                "rank": i + 1,
                "product_id": pid,
                "title": (p.get("title") or "")[:60],
                "brand": p.get("brand", ""),
                "price": p.get("price", 0),
                "display_score": dec.get("display_score", 0) if dec else 0,
                "level": dec.get("recommendation_level", "") if dec else "",
            })

    def evaluate(self, golden_products: list[str] | None = None):
        """计算基本 RAG 指标。golden_products 是用户期望的商品 ID 列表。"""
        if not golden_products:
            # 尝试从 eval_queries 匹配
            for eq in _eval_queries:
                q_text = eq.get("query", "")
                if q_text and q_text in self.trace["query"]:
                    golden_products = eq.get("product_ids", [])
                    break
        if not golden_products:
            return

        final_ids = [p["product_id"] for p in self.trace["final_top5"]]
        rerank_ids = [p["product_id"] for p in self.trace["reranker"]["candidates"]]

        # Hit@K
        for k in [1, 3, 5]:
            hits = sum(1 for g in golden_products if g in final_ids[:k])
            self.trace["evaluation"][f"hit@{k}"] = min(hits, 1)  # 1 if any golden product in top K

        # MRR
        for g in golden_products:
            for i, pid in enumerate(final_ids):
                if pid == g:
                    self.trace["evaluation"]["mrr"] = round(1.0 / (i + 1), 4)
                    break

        # Recall@K (reranker 层面)
        for k in [5, 10]:
            hits = sum(1 for g in golden_products if g in rerank_ids[:k])
            self.trace["evaluation"][f"recall@{k}"] = round(hits / len(golden_products), 4)

        # Precision@K
        for k in [1, 3]:
            hits = sum(1 for pid in final_ids[:k] if pid in golden_products)
            self.trace["evaluation"][f"precision@{k}"] = round(hits / k, 4)

    def save(self):
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(self.trace, ensure_ascii=False) + "\n")
        except Exception:
            pass


def compute_rag_stats(traces_file: str | None = None) -> dict:
    """从 rag_traces.jsonl 计算全局 RAG 指标。"""
    path = Path(traces_file) if traces_file else _LOG_PATH
    if not path.exists():
        return {"error": "no traces found"}

    lines = path.read_text("utf-8").strip().split("\n")
    traces = [json.loads(l) for l in lines if l.strip()]

    stats = {
        "total_queries": len(traces),
        "queries_with_eval": 0,
        "avg_hit@1": 0.0,
        "avg_hit@3": 0.0,
        "avg_hit@5": 0.0,
        "avg_mrr": 0.0,
        "avg_recall@5": 0.0,
        "avg_recall@10": 0.0,
        "avg_precision@1": 0.0,
        "avg_precision@3": 0.0,
    }

    eval_traces = [t for t in traces if t.get("evaluation")]
    stats["queries_with_eval"] = len(eval_traces)
    if not eval_traces:
        return stats

    for key in ["hit@1", "hit@3", "hit@5", "mrr", "recall@5", "recall@10", "precision@1", "precision@3"]:
        vals = [t["evaluation"].get(key, 0) for t in eval_traces if t["evaluation"].get(key) is not None]
        if vals:
            stats[f"avg_{key}"] = round(sum(vals) / len(vals), 4)

    return stats
