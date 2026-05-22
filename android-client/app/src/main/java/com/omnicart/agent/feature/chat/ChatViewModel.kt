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
