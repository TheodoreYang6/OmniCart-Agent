"""Qwen Embedding — 原生 API (qwen3.7-text-embedding)"""
import httpx
from app.core.config import QWEN_API_KEY, QWEN_BASE_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


class QwenEmbedding:
    def __init__(self, model: str = "qwen3.7-text-embedding", dimensions: int = 1024):
        self._api_key = QWEN_API_KEY
        self._base_url = QWEN_BASE_URL.rstrip("/")
        self._model = model
        self._dimensions = dimensions

    async def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
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
                # 非对称编码（DashScope 协议）：查询侧 text_type=query，文档索引侧 document
                "parameters": {"dimension": self._dimensions,
                               "text_type": "query" if is_query else "document"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return [e["embedding"] for e in data["output"]["embeddings"]]
