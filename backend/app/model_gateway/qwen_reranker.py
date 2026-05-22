"""Qwen Reranker — 兼容 API (qwen3-rerank)"""
import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL


class QwenReranker:
    def __init__(self, model: str = "qwen3-rerank"):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/").replace("/api/v1", "/compatible-api/v1")
        self._model = model

    def rerank(self, query: str, documents: list[str], top_n: int = 10) -> list[dict]:
        resp = httpx.post(
            f"{self._base_url}/reranks",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"index": r["index"], "document": documents[r["index"]],
             "relevance_score": r["relevance_score"]}
            for r in data["results"]
        ]
