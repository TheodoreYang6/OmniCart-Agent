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
        val demoProducts = listOf(
            Product(
                productId = "p_digital_007",
                title = "Apple AirPods Pro 3 主动降噪真无线蓝牙耳机",
                brand = "Apple", category = "数码电子", subCategory = "真无线耳机",
                price = 1899.0,
                imageUrls = listOf("https://picsum.photos/seed/earphone1/400/400"),
                skus = listOf(Sku("s1", mapOf("颜色" to "白色"), 1899.0), Sku("s2", mapOf("颜色" to "黑色"), 1899.0)),
                ragKnowledge = RagKnowledge(
                    marketingDescription = "Apple旗舰TWS耳机，H3芯片，自适应降噪",
                    userReviews = listOf(ReviewItem("小明", 5, "降噪效果一流"), ReviewItem("小红", 4, "音质不错但价格偏高"), ReviewItem("小刚", 5, "苹果生态无缝切换"))
                ),
                description = "Apple旗舰TWS耳机，H3芯片，自适应降噪"
            ),
            Product(
                productId = "p_digital_009",
                title = "华为 FreeBuds Pro 5 主动降噪真无线蓝牙耳机",
                brand = "华为", category = "数码电子", subCategory = "真无线耳机",
                price = 1499.0,
                imageUrls = listOf("https://picsum.photos/seed/earphone2/400/400"),
                skus = listOf(Sku("s1", mapOf("颜色" to "陶瓷白"), 1499.0), Sku("s2", mapOf("颜色" to "冰霜银"), 1599.0)),
                ragKnowledge = RagKnowledge(
                    marketingDescription = "华为旗舰TWS，静谧通话3.0，Hi-Res认证",
                    userReviews = listOf(ReviewItem("Alice", 5, "通话质量极好"), ReviewItem("Bob", 4, "续航不错"), ReviewItem("Charlie", 5, "性价比高"))
                ),
                description = "华为旗舰TWS，静谧通话3.0，Hi-Res认证"
            ),
            Product(
                productId = "p_digital_011",
                title = "小米 Buds 5 Pro 降噪蓝牙耳机",
                brand = "小米", category = "数码电子", subCategory = "真无线耳机",
                price = 799.0,
                imageUrls = listOf("https://picsum.photos/seed/earphone3/400/400"),
                skus = listOf(Sku("s1", mapOf("颜色" to "黑色"), 799.0)),
                ragKnowledge = RagKnowledge(
                    marketingDescription = "小米旗舰TWS，50dB深度降噪，空间音频",
                    userReviews = listOf(ReviewItem("Dave", 4, "价格亲民"), ReviewItem("Eve", 5, "降噪很强"))
                ),
                description = "小米旗舰TWS，50dB深度降噪，空间音频"
            )
        )

        val demoDecisions = listOf(
            DecisionResult("p_digital_007", 0.89, 8.9,
                ScoreBreakdown(0.80, 0.95, 0.90, 0.93, 0.80, 1.0, 0.15),
                listOf("E-MKT-p_digital_007", "R-p_digital_007-0"),
                listOf("价格较高", "仅适配苹果生态"), "苹果生态最佳TWS，H3芯片+自适应降噪"),
            DecisionResult("p_digital_009", 0.86, 8.6,
                ScoreBreakdown(0.88, 0.90, 0.88, 0.87, 0.75, 1.0, 0.12),
                listOf("E-MKT-p_digital_009", "R-p_digital_009-0"),
                listOf("部分用户反馈佩戴不稳"), "华为旗舰TWS，Hi-Res认证+静谧通话"),
            DecisionResult("p_digital_011", 0.83, 8.3,
                ScoreBreakdown(0.95, 0.85, 0.82, 0.82, 0.72, 1.0, 0.08),
                listOf("E-MKT-p_digital_011", "R-p_digital_011-0"),
                listOf("高频表现一般"), "799元50dB降噪，性价比炸裂")
        )

        val assistantMessage = ChatMessage(
            role = MessageRole.Assistant,
            text = "以下是为您推荐的蓝牙耳机（Demo 模式）：",
            products = demoProducts,
            decisionResults = demoDecisions,
        )
        _uiState.update {
            it.copy(isLoading = false, messages = it.messages + assistantMessage)
        }
    }
}
