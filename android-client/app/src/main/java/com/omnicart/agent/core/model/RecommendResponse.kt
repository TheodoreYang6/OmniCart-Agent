package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class RecommendResponse(
    @SerializedName("session_id")
    val sessionId: String = "",
    @SerializedName("conversation_id")
    val conversationId: String = "",
    @SerializedName("answer")
    val answer: String = "",
    @SerializedName("products")
    val products: List<Product> = emptyList(),
    @SerializedName("primary_products")
    val primaryProducts: List<Product> = emptyList(),
    @SerializedName("alternative_products")
    val recommendationAlternatives: List<Product> = emptyList(),
    @SerializedName("recommendation_brief")
    val recommendationBrief: List<Map<String, Any?>> = emptyList(),
    @SerializedName("product_resolution")
    val productResolution: Map<String, Any?>? = null,
    @SerializedName("retrieval_scope")
    val retrievalScope: String = "broad",
    @SerializedName("resolved_product_ids")
    val resolvedProductIds: List<String> = emptyList(),
    @SerializedName("product_dossier")
    val productDossier: Map<String, Any?>? = null,
    @SerializedName("retrieval_groups")
    val retrievalGroups: List<RetrievalGroup> = emptyList(),
    @SerializedName("decision_results")
    val decisionResults: List<DecisionResult> = emptyList(),
    @SerializedName("evidence_list")
    val evidenceList: List<EvidenceItem> = emptyList(),
    @SerializedName("trace_steps")
    val traceSteps: List<TraceStepItem> = emptyList(),
    @SerializedName("harness_report")
    val harnessReport: Map<String, Any?>? = null,
    @SerializedName("visual_result")
    val visualResult: Map<String, Any?>? = null,
    @SerializedName("fallback_status")
    val fallbackStatus: Map<String, Any?>? = null,
    @SerializedName("retrieval_plan")
    val retrievalPlan: Map<String, Any?>? = null,
    @SerializedName("sufficiency_report")
    val sufficiencyReport: Map<String, Any?>? = null,
    @SerializedName("constraints")
    val constraints: Map<String, Any?>? = null,
    @SerializedName("used_memories")
    val usedMemories: List<Map<String, Any?>>? = null,
    @SerializedName("blocked_memories")
    val blockedMemories: List<Map<String, Any?>>? = null,
    @SerializedName("memory_trace")
    val memoryTrace: Map<String, Any?>? = null,
    @SerializedName("target_product_analysis")
    val targetProductAnalysis: Map<String, Any?>? = null,
    @SerializedName("analysis_alternatives")
    val analysisAlternatives: List<Map<String, Any?>>? = null,
    @SerializedName("comparison_table")
    val comparisonTable: Map<String, Any?>? = null,
    /** Canonical v1 same-category comparison payload. */
    @SerializedName("comparison")
    val comparison: Map<String, Any?>? = null,
    @SerializedName("focus_analysis")
    val focusAnalysis: Map<String, Any?>? = null,
    @SerializedName("shop_card")
    val shopCard: Map<String, Any?>? = null,
    @SerializedName("cross_category")
    val crossCategory: List<Map<String, Any?>>? = null,
    @SerializedName("timing")
    val timing: Map<String, Any?>? = null,
    @SerializedName("needs_clarification")
    val needsClarification: Boolean = false,
    @SerializedName("clarification_question")
    val clarificationQuestion: String = "",
    @SerializedName("clarification_options")
    val clarificationOptions: List<Map<String, Any?>>? = null,
    @SerializedName("shop_action")
    val shopAction: Boolean = false,
    @SerializedName("actions")
    val actions: List<Map<String, Any?>>? = null,
)

data class RetrievalGroup(
    @SerializedName("group_id") val groupId: String = "",
    @SerializedName("role") val role: String = "",
    @SerializedName("query") val query: String = "",
    @SerializedName("product_ids") val productIds: List<String> = emptyList(),
    @SerializedName("status") val status: String = "pending",
    @SerializedName("missing_reason") val missingReason: String = "",
)

data class EvidenceItem(
    @SerializedName("evidence_id")
    val evidenceId: String = "",
    @SerializedName("source_type")
    val sourceType: String = "",
    @SerializedName("source_id")
    val sourceId: String = "",
    @SerializedName("product_id")
    val productId: String? = null,
    @SerializedName("content")
    val content: String = "",
    @SerializedName("modality")
    val modality: String = "text",
    @SerializedName("confidence")
    val confidence: Double = 0.0,
)

data class TraceStepItem(
    @SerializedName("step_id")
    val stepId: String = "",
    @SerializedName("agent_name")
    val agentName: String = "",
    @SerializedName("action")
    val action: String = "",
    @SerializedName("input_summary")
    val inputSummary: String = "",
    @SerializedName("output_summary")
    val outputSummary: String = "",
    @SerializedName("latency_ms")
    val latencyMs: Int = 0,
    @SerializedName("status")
    val status: String = "pending",
)
