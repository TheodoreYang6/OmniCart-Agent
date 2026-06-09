"""RAG 评测指标: Recall@K, MRR, NDCG@K."""

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Recall@K = |retrieved[:k] ∩ relevant| / |relevant|."""
    if not relevant:
        return 0.0
    retrieved_k = set(retrieved[:k])
    return len(retrieved_k & relevant) / len(relevant)


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank = 1 / rank_of_first_relevant.

    返回单条查询的 RR 值（多条查询时需外层取平均）。
    """
    if not relevant:
        return 0.0
    for i, pid in enumerate(retrieved):
        if pid in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved: list[str], relevance_grades: dict[str, int], k: int) -> float:
    """NDCG@K with graded relevance (0-3 scale).

    relevance_grades: {product_id: grade}, grade 0=irrelevant, 3=perfect.
    """
    if not relevance_grades:
        return 0.0

    dcg = 0.0
    for i, pid in enumerate(retrieved[:k]):
        rel = relevance_grades.get(pid, 0)
        dcg += (2 ** rel - 1) / math.log2(i + 2)

    ideal_rels = sorted(relevance_grades.values(), reverse=True)[:k]
    idcg = sum((2 ** rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

    return dcg / idcg if idcg > 0 else 0.0
