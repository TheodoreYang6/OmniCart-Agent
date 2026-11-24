"""Reuse the local V9 index across queries and reload on atomic replacement."""

from functools import lru_cache
import json
from pathlib import Path
from threading import Lock

import numpy as np

_lock = Lock()


def _stamp(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


@lru_cache(maxsize=1)
def _read(path: Path, stamp: tuple[int, int, int]):
    with path.open(encoding="utf-8") as stream:
        raw = json.load(stream)
    dimension = int(raw["dimension"])
    rows, vectors = [], []
    for chunk in raw.get("chunks", []):
        vector = chunk.get("embedding") or []
        if len(vector) == dimension:
            rows.append(chunk.get("payload") or {})
            vectors.append(vector)
    matrix = np.asarray(vectors, dtype=np.float32).reshape((-1, dimension))
    norms = np.linalg.norm(matrix, axis=1)
    valid = norms > 0
    np.divide(matrix, norms[:, None], out=matrix, where=valid[:, None])
    return dimension, rows, matrix, valid


def index(path: Path):
    with _lock:
        return _read(path, _stamp(path))


def dimension(path: Path) -> int:
    _, size, mtime_ns = _stamp(path)
    try:
        with path.with_suffix(".meta.json").open(encoding="utf-8") as stream:
            metadata = json.load(stream)
        if metadata["cache_size"] == size and metadata["cache_mtime_ns"] == mtime_ns:
            return int(metadata["dimension"])
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return index(path)[0]


def hits(path: Path, vector: list[float], filters: dict) -> list[dict]:
    dims, payloads, matrix, valid = index(path)
    if len(vector) != dims:
        return []
    query = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(query)
    if not np.isfinite(norm) or not norm:
        return []
    scores = matrix @ (query / norm)
    category, sub_category = filters.get("category"), filters.get("sub_category")
    sub_categories = set(sub_category if isinstance(sub_category, (list, tuple, set)) else [sub_category])
    low, high = filters.get("price_min"), filters.get("price_max")
    results = []
    for pos in np.argsort(-scores, kind="stable"):
        payload = payloads[pos]
        if not valid[pos] or not payload.get("product_id"):
            continue
        if category and payload.get("category") != category:
            continue
        if sub_category and payload.get("sub_category") not in sub_categories:
            continue
        price = float(payload.get("price") or 0)
        if (low is not None and price < float(low)) or (high is not None and price > float(high)):
            continue
        results.append({"product_id": payload["product_id"], "score": float(scores[pos]),
                        "payload": payload, "chunk_type": payload.get("chunk_type", "")})
        if len(results) == 100:
            break
    return results
