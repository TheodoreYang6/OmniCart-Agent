package com.omnicart.agent.feature.chat

import android.net.Uri
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.EvidenceItem
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.RecommendResponse
import com.omnicart.agent.core.model.TraceStepItem
import java.util.UUID

enum class MessageRole { User, Assistant }

data class ChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: MessageRole,
    val text: String = "",
    val products: List<Product> = emptyList(),
    val decisionResults: List<DecisionResult> = emptyList(),
    val evidenceList: List<EvidenceItem> = emptyList(),
    val traceSteps: List<TraceStepItem> = emptyList(),
    val harnessReport: Map<String, Any?>? = null,
    val timestamp: Long = System.currentTimeMillis(),
    val isVoice: Boolean = false,
    val isTranscribing: Boolean = false,
    val voiceAudioUrl: String? = null,
) {
    val hasProducts: Boolean get() = products.isNotEmpty()
}

data class ChatUiState(
    val queryText: String = "",
    val sessionId: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val isDemoMode: Boolean = false,
    val selectedProductIndex: Int = -1,
    val selectedProductId: String? = null,
    val selectedImageUri: Uri? = null,
    val uploadedImageUrl: String? = null,
    val lastSentImageUri: Uri? = null,
    val addToCartSuccess: String? = null,
    val lastResponse: RecommendResponse? = null,
    // 语音状态
    val isRecording: Boolean = false,
    val showVoiceOverlay: Boolean = false,
    val recordingSeconds: Int = 0,
    val voiceAudioUrl: String? = null,
    val voicePlaying: Boolean = false,
) {
    val lastUserMessage: ChatMessage?
        get() = messages.lastOrNull { it.role == MessageRole.User }

    val lastAssistantMessage: ChatMessage?
        get() = messages.lastOrNull { it.role == MessageRole.Assistant }
}
