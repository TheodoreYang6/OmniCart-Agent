"""Qwen Embedding — 原生 API (text-embedding-v4)"""
import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


class QwenEmbedding:
    def __init__(self, model: str = "text-embedding-v4", dimensions: int = 1024):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = _get_client()
        resp = await client.post(
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
        )
        resp.raise_for_status()
        data = resp.json()
        return [e["embedding"] for e in data["output"]["embeddings"]]
