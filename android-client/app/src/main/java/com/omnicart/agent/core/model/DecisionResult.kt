package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class DecisionResult(
    @SerializedName("product_id")
    val productId: String = "",
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
    @SerializedName("match_label")
    val matchLabel: String = "",
    @SerializedName("evidence_label")
    val evidenceLabel: String = "",
    @SerializedName("why_it_fits")
    val whyItFits: String = "",
    @SerializedName("caution")
    val caution: String = "",
    @SerializedName("support_evidence_ids")
    val supportEvidenceIds: List<String> = emptyList(),
    @SerializedName("recommendation_score")
    val recommendationScore: RecommendationScore? = null,
)

data class RecommendationScore(
    val version: String = "",
    val label: String = "欧米适配指数",
    val score: Int = 0,
    @SerializedName("match_label")
    val matchLabel: String = "",
    @SerializedName("recommendation_level")
    val recommendationLevel: String = "",
    @SerializedName("evidence_label")
    val evidenceLabel: String = "",
    @SerializedName("information_status")
    val informationStatus: String = "",
    @SerializedName("source_types")
    val sourceTypes: List<String> = emptyList(),
    val dimensions: List<RecommendationScoreDimension> = emptyList(),
    val explanation: String = "",
)

data class RecommendationScoreDimension(
    val key: String = "",
    val label: String = "",
    val score: Int? = null,
    val detail: String = "",
)
