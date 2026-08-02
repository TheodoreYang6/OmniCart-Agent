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

from app.core.config import QDRANT_COLLECTION_NAME, CHUNK_COLLECTION_NAME
from app.repositories.base_vector_repo import BaseVectorRepository

logger = logging.getLogger(__name__)


class QdrantVectorRepository(BaseVectorRepository):
    """Qdrant 向量仓库 — 真实向量检索。"""

    def __init__(self, client: QdrantClient):
        self._client = client
        self._collection = QDRANT_COLLECTION_NAME

    def search_similar(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        """DEPRECATED (V6): 旧产品级 products 集合检索已退役，主链统一走
        search_chunks（chunk 集合）。保留仅防外部引用破坏，不再维护。"""
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
        """DEPRECATED (V6): 随产品级集合退役，写入路径统一走 index_product_chunks.py。"""
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

    # ---- V5 统一 chunk 单集合检索 ----

    def search_chunks(
        self,
        query_vector: list[float],
        top_k: int = 30,
        filters: dict | None = None,
        chunk_types: list[str] | None = None,
        sparse: tuple[list[int], list[float]] | None = None,
    ) -> list[dict]:
        """块级向量检索 — 查统一 chunk 集合 + 服务端 payload 过滤。

        sparse 不为空且集合为 V7 双向量形态时 → dense+bm25 混合检索 + 服务端 RRF
        （spec §1.3）；否则走单向量路径。混合失败自动降级纯 dense。
        """
        qfilter = self._build_filter(filters or {}, chunk_types)

        # ---- 混合检索（dense + BM25 sparse，服务端 RRF 融合）----
        if sparse and sparse[0]:
            try:
                from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

                results = self._client.query_points(
                    collection_name=CHUNK_COLLECTION_NAME,
                    prefetch=[
                        Prefetch(query=query_vector, using="dense", limit=top_k,
                                 filter=qfilter),
                        Prefetch(query=SparseVector(indices=sparse[0], values=sparse[1]),
                                 using="bm25", limit=top_k, filter=qfilter),
                    ],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                )
                hits = self._to_hits(results)
                if hits:
                    return hits
            except Exception as e:  # noqa: BLE001 — 混合失败（如旧单向量集合）降级 dense
                logger.info(f"hybrid 检索不可用，降级纯 dense: {e}")

        # ---- 单向量路径（V6 匿名向量 / V7 命名 dense 均兼容）----
        try:
            try:
                results = self._client.query_points(
                    collection_name=CHUNK_COLLECTION_NAME,
                    query=query_vector, using="dense", limit=top_k,
                    query_filter=qfilter, with_payload=True,
                )
            except Exception:
                # V6 匿名向量集合：不带 using
                results = self._client.query_points(
                    collection_name=CHUNK_COLLECTION_NAME,
                    query=query_vector, limit=top_k,
                    query_filter=qfilter, with_payload=True,
                )
            return self._to_hits(results)
        except Exception as e:
            logger.warning(f"Qdrant chunk search failed: {e}")
            return []

    @staticmethod
    def _to_hits(results) -> list[dict]:
        """Qdrant 响应 → 统一 hit dict（dense/hybrid 共用）。"""
        hits = []
        for hit in results.points:
            payload = hit.payload or {}
            pid = payload.get("product_id", "")
            if not pid:
                continue
            hits.append({
                "product_id": pid,
                "chunk_id": payload.get("chunk_id", ""),
                "chunk_type": payload.get("chunk_type", ""),
                "category": payload.get("category", ""),
                "sub_category": payload.get("sub_category", ""),
                "price": payload.get("price", 0),
                "score": hit.score,
                "payload": payload,
            })
        return hits

    @staticmethod
    def _build_filter(filters: dict, chunk_types: list[str] | None):
        """构建 Qdrant Filter（品类/子品类/品牌/价格区间/口碑下限/块类型）。"""
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range

        must = []
        if filters.get("category"):
            must.append(FieldCondition(key="category", match=MatchValue(value=filters["category"])))
        if filters.get("sub_category"):
            sub = filters["sub_category"]
            # 支持单值或值列表（子品类别名归一一对多：充电宝→充电宝/移动电源）
            if isinstance(sub, (list, tuple, set)):
                must.append(FieldCondition(key="sub_category", match=MatchAny(any=list(sub))))
            else:
                must.append(FieldCondition(key="sub_category", match=MatchValue(value=sub)))
        brand = filters.get("brand")
        if brand:
            # V6：支持单品牌或品牌列表（compare 多路检索服务端按品牌过滤）
            if isinstance(brand, (list, tuple, set)):
                must.append(FieldCondition(key="brand", match=MatchAny(any=list(brand))))
            else:
                must.append(FieldCondition(key="brand", match=MatchValue(value=str(brand))))
        pmin, pmax = filters.get("price_min"), filters.get("price_max")
        if pmin is not None or pmax is not None:
            must.append(FieldCondition(key="price", range=Range(gte=pmin, lte=pmax)))
        if filters.get("rating_min") is not None:
            # V6：“口碑好/高分”服务端过滤（avg_rating 随块 payload 入库）
            must.append(FieldCondition(key="avg_rating", range=Range(gte=float(filters["rating_min"]))))
        if chunk_types:
            must.append(FieldCondition(key="chunk_type", match=MatchAny(any=list(chunk_types))))
        return Filter(must=must) if must else None

    def ensure_payload_indexes(self) -> None:
        """确保过滤字段建有 payload 索引（幂等）。"""
        from qdrant_client.models import PayloadSchemaType
        fields = {
            "product_id": PayloadSchemaType.KEYWORD,
            "chunk_type": PayloadSchemaType.KEYWORD,
            "category": PayloadSchemaType.KEYWORD,
            "sub_category": PayloadSchemaType.KEYWORD,
            "brand": PayloadSchemaType.KEYWORD,
            "price": PayloadSchemaType.FLOAT,
            "avg_rating": PayloadSchemaType.FLOAT,
        }
        for name, schema in fields.items():
            try:
                self._client.create_payload_index(CHUNK_COLLECTION_NAME, field_name=name, field_schema=schema)
            except Exception:
                pass
