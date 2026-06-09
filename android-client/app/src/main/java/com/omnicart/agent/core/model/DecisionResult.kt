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
    @SerializedName("component_scores")
    val componentScores: Map<String, Map<String, Any?>>? = null,
    @SerializedName("evidence_ids")
    val evidenceIds: List<String> = emptyList(),
    @SerializedName("risk_factors")
    val riskFactors: List<String> = emptyList(),
    @SerializedName("recommendation_reason")
    val recommendationReason: String = "",
    @SerializedName("llm_relevance")
    val llmRelevance: Double = 0.0,
    @SerializedName("llm_reasoning")
    val llmReasoning: String = "",
    @SerializedName("llm_verdict")
    val llmVerdict: String = "",
    @SerializedName("recommendation_level")
    val recommendationLevel: String = "",
    @SerializedName("evidence_confidence")
    val evidenceConfidence: Double = 0.0,
    @SerializedName("support_evidence_ids")
    val supportEvidenceIds: List<String> = emptyList(),
)

/**
 * V4 ScoreBreakdown — 旧 7 维命名（保留向后兼容）。
 * 注意: visual_similarity 实际存的是 relevance (RAG相关度), availability_score 实际存的是 value_score (性价比)。
 * 新代码优先使用 component_scores (9维结构化输出)。
 */
data class ScoreBreakdown(
    @SerializedName("budget_fit")
    val budgetFit: Double = 0.0,
    @SerializedName("scenario_fit")
    val scenarioFit: Double = 0.0,
    @SerializedName("spec_match")
    val specMatch: Double = 0.0,
    @SerializedName("review_confidence")
    val reviewConfidence: Double = 0.0,
    @SerializedName("visual_similarity")   // 实际: relevance (RAG相关度)
    val visualSimilarity: Double = 0.0,
    @SerializedName("availability_score")   // 实际: value_score (性价比)
    val availabilityScore: Double = 0.0,
    @SerializedName("risk_penalty")
    val riskPenalty: Double = 0.0
)
