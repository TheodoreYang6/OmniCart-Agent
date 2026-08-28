from typing import Optional
from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    budget_fit: float = 0.0
    scenario_fit: float = 0.0
    spec_match: float = 0.0
    review_confidence: float = 0.0
    visual_similarity: float = 0.0
    availability_score: float = 1.0
    risk_penalty: float = 0.0
    # P2: Memory-aware dimensions
    preference_match_score: float = 0.0
    device_compatibility_score: float = 0.0
    brand_preference_boost: float = 0.0
    avoid_tag_penalty: float = 0.0


class RecommendationScoreDimension(BaseModel):
    """用户可见的评分维度；全部可由本轮请求快照确定性重算。"""

    key: str
    label: str
    score: int | None = None
    detail: str = ""


class RecommendationScore(BaseModel):
    version: str = "omi_recommendation_v1"
    label: str = "欧米适配指数"
    score: int = 0
    match_label: str = ""
    recommendation_level: str = ""
    evidence_label: str = "信息有限"
    information_status: str = "资料有限"
    source_types: list[str] = Field(default_factory=list)
    dimensions: list[RecommendationScoreDimension] = Field(default_factory=list)
    explanation: str = ""


class DecisionResult(BaseModel):
    product_id: str
    final_score: float = 0.0
    display_score: float = 0.0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    # 正向信号（好评率展示，促单）：如 "12 条评价 92% 好评"；无足够评论或好评率低时为空
    positive_signal: str = ""
    recommendation_reason: str = ""
    # P2: Memory trace reference
    memory_contributions: list[dict] = Field(default_factory=list)
    # V2: LLM Evidence Evaluation
    llm_relevance: float = 0.0
    llm_reasoning: str = ""
    llm_verdict: str = ""  # strong_recommend | recommend | consider | avoid
    # V4: Evidence-Grounded Scoring
    score_version: str = "evidence_scoring_v1"
    suitability_score: Optional[float] = None
    evidence_confidence: Optional[float] = None
    component_scores: dict = Field(default_factory=dict)
    support_evidence_ids: list[str] = Field(default_factory=list)
    recommendation_level: str = ""
    hard_constraint_status: str = "pass"
    scoring_debug: dict = Field(default_factory=dict)
    # V9 新展示评分。final_score/display_score 仅保留给旧回退接口，不再下发给客户端。
    recommendation_score: RecommendationScore | None = None
