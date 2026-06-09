"""Qdrant 客户端单例管理器。"""

import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import QDRANT_URL, QDRANT_COLLECTION_NAME, EMBEDDING_DIMENSION, USE_QDRANT

_client: QdrantClient | None = None


def _ensure_no_proxy():
    """绕过系统代理直连本地服务，修复 Windows 上 httpx 走代理导致 Qdrant 连接失败。"""
    if not os.environ.get("NO_PROXY"):
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    if not os.environ.get("no_proxy"):
        os.environ["no_proxy"] = "localhost,127.0.0.1,::1"


def get_qdrant() -> QdrantClient | None:
    global _client
    if not USE_QDRANT or not QDRANT_URL:
        return None
    if _client is None:
        _ensure_no_proxy()
        _client = QdrantClient(url=QDRANT_URL, timeout=30.0)
    return _client


async def init_qdrant():
    """确保 collection 存在，维度与 model_config.yaml 中一致。"""
    if not USE_QDRANT:
        return
    client = get_qdrant()
    if client is None:
        return
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
        )


async def close_qdrant():
    global _client
    if _client:
        _client.close()
        _client = None
