#!/usr/bin/env python
"""Build independent v8 discovery and evidence Qdrant collections.

The discovery collection contains exactly one review-free purchase document per
product.  Evidence remains searchable, but cannot create a primary candidate.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import EMBEDDING_DIMENSION, QDRANT_URL, USE_QDRANT
from app.model_gateway.gateway import get_model_gateway
from app.repositories.json_product_repo import JsonProductRepository
from app.retrieval.sparse_encoder import build_corpus_stats, encode_document
from app.services.discovery_documents import build_discovery_document, build_evidence_documents


async def _embed(texts: list[str]) -> list[list[float]]:
    gateway = get_model_gateway()
    out = []
    for i in range(0, len(texts), 128):
        out.extend(await gateway.embed(texts[i : i + 128], "text_embedding", is_query=False))
    return out


def _ensure(client, name: str, recreate: bool):
    from qdrant_client.models import Distance, PayloadSchemaType, SparseIndexParams, SparseVectorParams, VectorParams

    if recreate:
        try:
            client.delete_collection(name)
        except Exception:
            pass
    try:
        client.get_collection(name)
    except Exception:
        client.create_collection(
            name,
            vectors_config={"dense": VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams(index=SparseIndexParams())},
        )
    for field, schema in {
        "product_id": PayloadSchemaType.KEYWORD,
        "category": PayloadSchemaType.KEYWORD,
        "sub_category": PayloadSchemaType.KEYWORD,
        "brand": PayloadSchemaType.KEYWORD,
        "price": PayloadSchemaType.FLOAT,
        "source_type": PayloadSchemaType.KEYWORD,
        "fact_keys": PayloadSchemaType.KEYWORD,
    }.items():
        try:
            client.create_payload_index(name, field, schema)
        except Exception:
            pass


async def main_async(discovery: str, evidence: str, recreate: bool) -> None:
    if not (USE_QDRANT and QDRANT_URL):
        raise RuntimeError("Qdrant is not configured")
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    products = JsonProductRepository().list_all()
    discovery_docs = [build_discovery_document(p) for p in products]
    evidence_docs = [d for p in products for d in build_evidence_documents(p)]
    client = QdrantClient(url=QDRANT_URL, timeout=60.0)
    try:
        _ensure(client, discovery, recreate)
        _ensure(client, evidence, recreate)
        for collection, docs in ((discovery, discovery_docs), (evidence, evidence_docs)):
            vectors = await _embed([d.text for d in docs])
            stats = build_corpus_stats([d.text for d in docs])
            points = []
            for d, vector in zip(docs, vectors, strict=True):
                sparse_i, sparse_v = encode_document(d.text, stats)
                point_vector = {"dense": vector}
                if sparse_i:
                    from qdrant_client.models import SparseVector

                    point_vector["bm25"] = SparseVector(indices=sparse_i, values=sparse_v)
                identity = getattr(d, "evidence_id", "") or f"{d.product_id}|discovery"
                points.append(
                    PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, identity)), vector=point_vector, payload=d.payload
                    )
                )
            for i in range(0, len(points), 256):
                client.upsert(collection, points[i : i + 256], wait=i + 256 >= len(points))
            print(f"{collection}: {len(points)} points")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", default="product_discovery_v8")
    parser.add_argument("--evidence", default="product_evidence_v8")
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.discovery, args.evidence, args.recreate))
