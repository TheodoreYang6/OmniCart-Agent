"""Qwen Embedding — 原生 API (text-embedding-v4)"""
import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL


class QwenEmbedding:
    def __init__(self, model: str = "text-embedding-v4", dimensions: int = 1024):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self._base_url}/services/embeddings/text-embedding/text-embedding",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "input": {"texts": texts},
                "parameters": {"dimension": self._dimensions},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [e["embedding"] for e in data["output"]["embeddings"]]
