package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class DecisionResult(
    @SerializedName("product_id")
    val productId: String = "",
    @SerializedName("final_score")
    val finalScore: Double = 0.0,
    @SerializedName("display_score")
    val displayScore: Double = 0.0,
    @SerializedName("score_breakdown")
    val scoreBreakdown: ScoreBreakdown? = null,
    @SerializedName("evidence_ids")
    val evidenceIds: List<String> = emptyList(),
    @SerializedName("risk_factors")
    val riskFactors: List<String> = emptyList(),
    @SerializedName("recommendation_reason")
    val recommendationReason: String = ""
)

data class ScoreBreakdown(
    @SerializedName("budget_fit")
    val budgetFit: Double = 0.0,
    @SerializedName("scenario_fit")
    val scenarioFit: Double = 0.0,
    @SerializedName("spec_match")
    val specMatch: Double = 0.0,
    @SerializedName("review_confidence")
    val reviewConfidence: Double = 0.0,
    @SerializedName("visual_similarity")
    val visualSimilarity: Double = 0.0,
    @SerializedName("availability_score")
    val availabilityScore: Double = 0.0,
    @SerializedName("risk_penalty")
    val riskPenalty: Double = 0.0
)
