"""Qdrant 向量仓库 — 真正实现语义搜索。

连接本地或云端 Qdrant 实例，支持：
- search_similar: ANN 向量搜索
- store_embeddings: 批量写入向量
- health_check: 连通性检查
"""

import uuid
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.core.config import QDRANT_COLLECTION_NAME
from app.repositories.base_vector_repo import BaseVectorRepository

logger = logging.getLogger(__name__)


class QdrantVectorRepository(BaseVectorRepository):
    """Qdrant 向量仓库 — 真实向量检索。"""

    def __init__(self, client: QdrantClient):
        self._client = client
        self._collection = QDRANT_COLLECTION_NAME

    def search_similar(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        try:
            results = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                limit=top_k,
            )
            return [
                {
                    "product_id": hit.payload.get("product_id", "") if hit.payload else "",
                    "score": hit.score,
                    "payload": hit.payload,
                }
                for hit in results.points
            ]
        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return []

    def store_embeddings(self, texts: list[str], embeddings: list[list[float]]):
        points = []
        for text, vector in zip(texts, embeddings):
            # text 格式: "product_id | title + brand + ... 拼接文本"
            parts = text.split(" | ", 1)
            pid = parts[0] if parts else ""
            payload = {
                "product_id": pid,
                "text": parts[1] if len(parts) > 1 else text,
            }
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, pid))
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        self._client.upsert(collection_name=self._collection, points=points)

    def health_check(self) -> bool:
        try:
            self._client.get_collection(self._collection)
            return True
        except Exception:
            return False
