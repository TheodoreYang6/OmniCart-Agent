"""V4 Evidence-Grounded Scoring Schemas — 证据驱动的评分数据结构。

新增:
- ComponentScore: 每个评分维度的分数、方法、证据绑定
- EvidenceMetrics: RAG 证据质量评价
- ProductEvidenceProfile: 按 product_id 聚合的 RAG evidence 快照
"""

from pydantic import BaseModel, Field


class ComponentScore(BaseModel):
    """单个评分维度的可解释分数。"""
    score: float = 0.0
    weight: float | None = None
    method: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class EvidenceMetrics(BaseModel):
    """RAG 证据质量评价结果。"""
    evidence_relevance: float = 0.0       # retrieval/rerank 分数归一化后的相关度
    source_quality: float = 0.0           # source_weight 平均值 (证据类型质量)
    source_coverage: float = 0.0          # 必需证据类型组命中比例
    aspect_coverage: float = 0.0          # 用户关心方面的证据覆盖比例
    source_reliability: float = 0.0       # 证据来源可信度均值
    evidence_consistency: float = 1.0     # 证据内部一致性
    evidence_confidence: float = 0.0      # 综合置信度
    selected_evidence_ids_by_type: dict[str, list[str]] = Field(default_factory=dict)
    missing_evidence_types: list[str] = Field(default_factory=list)
    relevance_source: str = ""
    support_evidence_ids: list[str] = Field(default_factory=list)


class ProductEvidenceProfile(BaseModel):
    """按 product_id 聚合的 RAG evidence 快照。"""
    product_id: str = ""
    evidence_count_by_type: dict[str, int] = Field(default_factory=dict)
    evidence_ids_by_type: dict[str, list[str]] = Field(default_factory=dict)
    top_evidence_ids: list[str] = Field(default_factory=list)
    positive_review_ids: list[str] = Field(default_factory=list)
    risk_review_ids: list[str] = Field(default_factory=list)
    faq_ids: list[str] = Field(default_factory=list)
    marketing_ids: list[str] = Field(default_factory=list)
    summary_ids: list[str] = Field(default_factory=list)
    sku_ids: list[str] = Field(default_factory=list)
    avg_retrieval_score: float = 0.0
    avg_rerank_score: float = 0.0
    max_retrieval_score: float = 0.0
    max_rerank_score: float = 0.0
    source_reliability: float = 0.0
