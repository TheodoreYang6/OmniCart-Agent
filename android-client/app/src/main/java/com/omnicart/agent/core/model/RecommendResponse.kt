package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class RecommendResponse(
    @SerializedName("session_id")
    val sessionId: String = "",
    @SerializedName("answer")
    val answer: String = "",
    @SerializedName("products")
    val products: List<Product> = emptyList(),
    @SerializedName("decision_results")
    val decisionResults: List<DecisionResult> = emptyList(),
    @SerializedName("evidence_list")
    val evidenceList: List<EvidenceItem> = emptyList(),
    @SerializedName("trace_steps")
    val traceSteps: List<TraceStepItem> = emptyList(),
    @SerializedName("harness_report")
    val harnessReport: Map<String, Any?>? = null,
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
