from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    budget_fit: float = 0.0
    scenario_fit: float = 0.0
    spec_match: float = 0.0
    review_confidence: float = 0.0
    visual_similarity: float = 0.0
    availability_score: float = 1.0
    risk_penalty: float = 0.0


class DecisionResult(BaseModel):
    product_id: str
    final_score: float = 0.0
    display_score: float = 0.0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    recommendation_reason: str = ""
