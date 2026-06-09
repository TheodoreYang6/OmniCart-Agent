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


class DecisionResult(BaseModel):
    product_id: str
    final_score: float = 0.0
    display_score: float = 0.0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
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

