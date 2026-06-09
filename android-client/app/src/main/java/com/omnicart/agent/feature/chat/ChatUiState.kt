package com.omnicart.agent.feature.chat

import android.net.Uri
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.EvidenceItem
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.RecommendResponse
import com.omnicart.agent.core.model.TraceStepItem
import com.omnicart.agent.core.network.ConversationItem
import java.util.UUID

enum class MessageRole { User, Assistant }

data class ConstraintOption(
    val label: String,
    val value: String,
    val dim: String,  // sub_category | concern | budget
)

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
    val imageUri: android.net.Uri? = null,
    // 问问豆仔对比数据
    val targetProductAnalysis: Map<String, Any?>? = null,
    val comparisonTable: Map<String, Any?>? = null,
    val alternativeProducts: List<Map<String, Any?>>? = null,
    val crossCategory: List<Map<String, Any?>>? = null,
) {
    val hasProducts: Boolean get() = products.isNotEmpty()
    val hasComparison: Boolean get() = targetProductAnalysis != null || comparisonTable != null
}

data class ChatUiState(
    val queryText: String = "",
    val sessionId: String = "",
    val conversationId: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val isDemoMode: Boolean = false,
    val selectedProductIndex: Int = -1,
    val selectedProductId: String? = null,
    val selectedImageUri: Uri? = null,
    val uploadedImageUrl: String? = null,
    val addToCartSuccess: String? = null,
    val lastResponse: RecommendResponse? = null,
    // 语音状态
    val isRecording: Boolean = false,
    val showVoiceOverlay: Boolean = false,
    val recordingSeconds: Int = 0,
    val voiceAudioUrl: String? = null,
    val voicePlaying: Boolean = false,
    val voiceCancelling: Boolean = false,  // 滑动到取消区域
    // 加载状态文案 (不同场景显示不同提示)
    val loadingMessage: String = "",
    // 打字机流式
    val isStreamingText: Boolean = false,
    val streamingText: String = "",
    // 约束引导
    val guideOptions: List<ConstraintOption> = emptyList(),
    val lockedCategory: String = "",
    val lockedSubCategory: String = "",
    val lockedConcern: String = "",
    val guideRound: Int = 0,
    val isGuiding: Boolean = false,
    val budgetMax: Double? = null,
    val budgetMin: Double? = null,
    // 历史聊天 (Memory Lite P3)
    val showHistorySheet: Boolean = false,
    val conversations: List<ConversationItem> = emptyList(),
    val isLoadingHistory: Boolean = false,
    val isLoadingConversation: Boolean = false,
    // 地址表单
    val showAddressForm: Boolean = false,
    // 长期偏好
    val profileEnabled: Boolean = false,
) {
    val lastUserMessage: ChatMessage?
        get() = messages.lastOrNull { it.role == MessageRole.User }

    val lastAssistantMessage: ChatMessage?
        get() = messages.lastOrNull { it.role == MessageRole.Assistant }
}
