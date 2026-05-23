package com.omnicart.agent.feature.chat

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.RagKnowledge
import com.omnicart.agent.core.model.ReviewItem
import com.omnicart.agent.core.model.Sku
import com.omnicart.agent.core.model.RecommendRequest
import com.omnicart.agent.core.model.ScoreBreakdown
import com.omnicart.agent.core.network.AgentActionRequest
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.model.RecommendResponse
import com.omnicart.agent.feature.demo.MockDemoData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(
        ChatUiState(sessionId = java.util.UUID.randomUUID().toString().take(8))
    )
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    fun onQueryChange(text: String) {
        _uiState.update { it.copy(queryText = text) }
    }

    fun onSend() {
        val query = _uiState.value.queryText.trim()
        val hasImage = _uiState.value.selectedImageUri != null

        if (query.isBlank() && !hasImage) return

        val finalQuery = if (query.isBlank()) "请帮我分析这个商品" else query

        val sentImageUri = _uiState.value.selectedImageUri
        val sentImageUrl = _uiState.value.uploadedImageUrl

        // 追加用户消息
        val userMessage = ChatMessage(role = MessageRole.User, text = finalQuery)
        _uiState.update { it.copy(
            messages = it.messages + userMessage,
            queryText = "",
            selectedImageUri = null,
            uploadedImageUrl = null,
            lastSentImageUri = sentImageUri,
        ) }

        if (_uiState.value.isDemoMode) {
            loadDemoData(finalQuery)
            return
        }

        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                var imageUrl: String? = sentImageUrl

                if (sentImageUri != null && imageUrl == null) {
                    val uploadResult = uploadImage(sentImageUri)
                    if (uploadResult != null) {
                        imageUrl = uploadResult
                    }
                }

                if (sentImageUri != null && imageUrl.isNullOrBlank()) {
                    _uiState.update {
                        it.copy(isLoading = false, errorMessage = "图片上传失败，请检查网络连接")
                    }
                    return@launch
                }

                val response = ApiClient.api.recommend(
                    RecommendRequest(
                        userQuery = finalQuery,
                        imageUrl = imageUrl,
                        sessionId = _uiState.value.sessionId,
                    )
                )
                val assistantMessage = ChatMessage(
                    role = MessageRole.Assistant,
                    text = response.answer,
                    products = response.products,
                    decisionResults = response.decisionResults,
                    evidenceList = response.evidenceList,
                    traceSteps = response.traceSteps,
                    harnessReport = response.harnessReport?.mapValues { it.value },
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        messages = it.messages + assistantMessage,
                        lastResponse = response,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        errorMessage = e.message ?: "网络请求失败，请检查后端是否运行"
                    )
                }
            }
        }
    }

    private suspend fun uploadImage(uri: Uri): String? {
        return try {
            val resolver = getApplication<Application>().contentResolver
            val inputStream = resolver.openInputStream(uri) ?: return null
            val bytes = inputStream.use { it.readBytes() }
            val fileName = "photo_${System.currentTimeMillis()}.jpg"

            val requestBody = okhttp3.RequestBody.create(
                "image/jpeg".toMediaTypeOrNull(), bytes
            )
            val part = okhttp3.MultipartBody.Part.createFormData("file", fileName, requestBody)
            val response = ApiClient.api.uploadImage(part)
            response.imageUrl
        } catch (e: Exception) {
            null
        }
    }

    fun onNewConversation() {
        _uiState.update {
            ChatUiState(sessionId = java.util.UUID.randomUUID().toString().take(8))
        }
    }

    fun onProductClick(productId: String) {
        val index = _uiState.value.messages
            .flatMap { it.products }
            .indexOfFirst { it.productId == productId }
        _uiState.update { it.copy(selectedProductIndex = index, selectedProductId = productId) }
    }

    fun onDismissDetail() {
        _uiState.update { it.copy(selectedProductIndex = -1, selectedProductId = null) }
    }

    fun onAddToCart(productId: String, productTitle: String) {
        viewModelScope.launch {
            try {
                ApiClient.api.agentAction(
                    AgentActionRequest(
                        action = "add_to_cart",
                        productId = productId,
                    )
                )
                _uiState.update { it.copy(addToCartSuccess = productTitle) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(errorMessage = "加购失败: ${e.message}")
                }
            }
        }
    }

    fun dismissAddToCartSuccess() {
        _uiState.update { it.copy(addToCartSuccess = null) }
    }

    fun onImageSelected(uri: Uri) {
        _uiState.update { it.copy(selectedImageUri = uri, uploadedImageUrl = null, errorMessage = null) }
    }

    fun onImageRemoved() {
        _uiState.update { it.copy(selectedImageUri = null, uploadedImageUrl = null) }
    }

    // ---- 语音 ----

    private val voiceRecorder = VoiceRecorder(getApplication())
    private var recordingTimer: kotlinx.coroutines.Job? = null

    fun startRecording() {
        if (voiceRecorder.isRecording) return
        try {
            voiceRecorder.start()
            _uiState.update { it.copy(isRecording = true, recordingSeconds = 0, showVoiceOverlay = true) }
            // 启动计时器
            recordingTimer = viewModelScope.launch {
                while (voiceRecorder.isRecording) {
                    kotlinx.coroutines.delay(1000)
                    _uiState.update { it.copy(recordingSeconds = it.recordingSeconds + 1) }
                }
            }
        } catch (e: Exception) {
            _uiState.update { it.copy(errorMessage = "录音启动失败: ${e.message}") }
        }
    }

    fun stopRecordingAndSend() {
        if (!voiceRecorder.isRecording) return
        recordingTimer?.cancel()
        val file = voiceRecorder.stop() ?: return
        _uiState.update { it.copy(isRecording = false, showVoiceOverlay = false) }

        viewModelScope.launch {
            try {
                val bytes = file.readBytes()
                if (bytes.size < 100) {
                    _uiState.update {
                        it.copy(errorMessage = "录音太短，请至少录制1秒")
                    }
                    return@launch
                }

                // Step 0: 立即显示"语音识别中"占位消息，让用户知道在处理
                val pendingId = java.util.UUID.randomUUID().toString()
                val pendingMsg = ChatMessage(
                    id = pendingId,
                    role = MessageRole.User,
                    text = "",
                    isVoice = true,
                    isTranscribing = true,
                )
                _uiState.update {
                    it.copy(messages = it.messages + pendingMsg)
                }

                val audioBody = okhttp3.RequestBody.create(
                    "audio/m4a".toMediaTypeOrNull(), bytes
                )
                val audioPart = okhttp3.MultipartBody.Part.createFormData(
                    "audio", "voice.m4a", audioBody
                )

                // Step 1: ASR 转文字
                val asr = ApiClient.api.voiceTranscribe(audioPart)
                val transcribed = if (asr.fallback || asr.text.isBlank()) {
                    "[语音消息]"
                } else {
                    asr.text.trim()
                }

                // Step 2: 替换占位消息为真实转写文字 + 开启 loading
                val userMsg = ChatMessage(
                    role = MessageRole.User,
                    text = transcribed,
                    isVoice = true,
                )
                _uiState.update {
                    it.copy(
                        isLoading = true,
                        messages = it.messages.map { m -> if (m.id == pendingId) userMsg else m },
                        queryText = "",
                        errorMessage = null,
                    )
                }

                // Step 3: 走推荐链路（跟文字输入一致）
                val response = ApiClient.api.recommend(
                    RecommendRequest(
                        userQuery = transcribed,
                        imageUrl = null,
                        sessionId = _uiState.value.sessionId,
                    )
                )
                val assistantMsg = ChatMessage(
                    role = MessageRole.Assistant,
                    text = response.answer.ifBlank { "好的，请告诉我你想买什么~" },
                    products = response.products,
                    decisionResults = response.decisionResults,
                    evidenceList = response.evidenceList,
                    traceSteps = response.traceSteps,
                    harnessReport = response.harnessReport?.mapValues { it.value },
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        messages = it.messages + assistantMsg,
                        lastResponse = response,
                    )
                }
            } catch (e: Exception) {
                // 替换占位消息为错误提示
                _uiState.update {
                    val cleaned = it.messages.map { m ->
                        if (m.isTranscribing) m.copy(text = "[语音识别失败]", isTranscribing = false) else m
                    }
                    it.copy(
                        isLoading = false,
                        showVoiceOverlay = false,
                        messages = cleaned,
                    )
                }
            } finally {
                file.delete()
            }
        }
    }

    fun cancelRecording() {
        recordingTimer?.cancel()
        voiceRecorder.cancel()
        _uiState.update { it.copy(isRecording = false, showVoiceOverlay = false) }
    }

    fun dismissVoiceOverlay() {
        _uiState.update { it.copy(showVoiceOverlay = false) }
    }

    fun clearVoiceAudio() {
        _uiState.update { it.copy(voiceAudioUrl = null) }
    }

    fun toggleDemoMode(enabled: Boolean) {
        _uiState.update {
            it.copy(
                isDemoMode = enabled,
                errorMessage = null,
                messages = emptyList(),
                selectedProductIndex = -1,
                selectedProductId = null,
                selectedImageUri = null,
                uploadedImageUrl = null,
            )
        }
    }

    private fun loadDemoData(query: String) {
        val assistantMessage = ChatMessage(
            role = MessageRole.Assistant,
            text = "以下是为您推荐的蓝牙耳机（Demo 一键演示模式）：",
            products = MockDemoData.buildDemoProducts(),
            decisionResults = MockDemoData.buildDemoDecisions(),
            evidenceList = MockDemoData.buildDemoEvidence(),
            traceSteps = MockDemoData.buildDemoTraces(),
            harnessReport = MockDemoData.buildDemoHarness(),
        )
        val demoResponse = RecommendResponse(
            sessionId = _uiState.value.sessionId,
            answer = assistantMessage.text,
            products = MockDemoData.buildDemoProducts(),
            decisionResults = MockDemoData.buildDemoDecisions(),
            evidenceList = MockDemoData.buildDemoEvidence(),
            traceSteps = MockDemoData.buildDemoTraces(),
            harnessReport = MockDemoData.buildDemoHarness(),
            retrievalPlan = mapOf("intent" to "recommend", "channels" to listOf("text", "review", "policy"), "category" to "数码电子", "top_k" to 10, "priority" to "balanced"),
            constraints = mapOf("category" to "数码电子", "budget_max" to 2000.0, "scenario" to "commute"),
            sufficiencyReport = mapOf("total_evidence" to 4, "sufficient" to true, "evidence_types" to listOf("text_retrieval", "review_positive", "review_risk", "policy_faq")),
            fallbackStatus = mapOf("level" to 0, "description" to "全链路正常运行"),
        )
        _uiState.update {
            it.copy(isLoading = false, messages = it.messages + assistantMessage, lastResponse = demoResponse)
        }
    }
}
