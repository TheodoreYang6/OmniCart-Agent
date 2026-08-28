package com.omnicart.agent.feature.chat

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.EvidenceItem
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.TraceStepItem
import com.omnicart.agent.core.model.RagKnowledge
import com.omnicart.agent.core.model.ReviewItem
import com.omnicart.agent.core.model.Sku
import com.omnicart.agent.core.model.RecommendRequest
import com.omnicart.agent.core.network.AddToCartRequest
import com.omnicart.agent.core.network.AgentActionRequest
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.AgentStreamClient
import com.omnicart.agent.core.network.AddressCreateRequest
import com.omnicart.agent.core.network.GuideRequest
import com.omnicart.agent.core.model.RecommendResponse
import com.omnicart.agent.feature.auth.AuthManager
import com.omnicart.agent.feature.demo.MockDemoData
import com.google.gson.Gson
import com.google.gson.JsonObject
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

    init {
        cleanOldCameraFiles()
    }

    /** 清理超过 24 小时的相机缓存文件，避免堆积。 */
    private fun cleanOldCameraFiles() {
        try {
            val cacheDir = getApplication<android.app.Application>().cacheDir
            val cutoff = System.currentTimeMillis() - 24 * 60 * 60 * 1000L
            cacheDir.listFiles()?.filter { it.name.startsWith("camera_") && it.lastModified() < cutoff }
                ?.forEach { it.delete() }
        } catch (_: Exception) { }
    }

    fun setSessionId(id: String) {
        _uiState.update { it.copy(sessionId = id) }
    }

    /** 用户切换时重置整个聊天状态，避免旧用户消息残留。 */
    fun onUserChanged() {
        _uiState.update {
            ChatUiState(sessionId = java.util.UUID.randomUUID().toString().take(8))
        }
        checkProfileEnabled()
    }

    /** 开始新对话 — 清空 conversationId 和消息历史 */
    fun startNewConversation() {
        _uiState.update {
            ChatUiState(sessionId = java.util.UUID.randomUUID().toString().take(8))
        }
    }

    fun checkProfileEnabled() {
        val uid = AuthManager.userId
        if (uid.isBlank()) return
        viewModelScope.launch {
            try {
                val response = ApiClient.api.getProfile(uid)
                if (response.isSuccessful) {
                    val profile = response.body()
                    _uiState.update { it.copy(profileEnabled = profile != null && profile.enabled) }
                }
            } catch (_: Exception) { }
        }
    }

    fun onQueryChange(text: String) {
        _uiState.update { it.copy(queryText = text) }
    }

    fun onSend() {
        // 统一走 SSE 流式输出
        onSendStream()
    }

    /** 直接推荐 (有图片时) */
    private fun sendDirectRecommend(query: String, imageUrl: String?) {
        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val url = imageUrl ?: _uiState.value.uploadedImageUrl
                val response = ApiClient.api.recommend(
                    RecommendRequest(
                        userQuery = query, imageUrl = url,
                        sessionId = _uiState.value.sessionId,
                        userId = AuthManager.effectiveUserId,
                        conversationId = _uiState.value.conversationId,
                    )
                )
                appendAssistant(response)
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, errorMessage = e.message ?: "网络请求失败") }
            }
        }
    }

    /** 约束引导式推荐 */
    private fun sendGuide(query: String) {
        val state = _uiState.value
        _uiState.update { it.copy(isLoading = true, isGuiding = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val response = ApiClient.api.recommendGuide(
                    GuideRequest(
                        userQuery = query,
                        sessionId = state.sessionId,
                        userId = if (AuthManager.isLoggedIn) AuthManager.userId else "",
                        conversationId = if (AuthManager.isLoggedIn) state.conversationId else "",
                        category = state.lockedCategory,
                        subCategory = state.lockedSubCategory,
                        concern = state.lockedConcern,
                        budgetMax = state.budgetMax,
                        budgetMin = state.budgetMin,
                        roundNum = state.guideRound,
                    )
                )

                if (response.shouldRecommend) {
                    // 约束足够 → 展示推荐结果
                    val assistantMessage = ChatMessage(
                        role = MessageRole.Assistant,
                        text = response.answer,
                        products = response.products,
                        decisionResults = response.decisionResults,
                        evidenceList = response.evidenceList,
                        traceSteps = response.traceSteps,
                    )
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            isGuiding = false,
                            messages = it.messages + assistantMessage,
                            guideOptions = emptyList(),
                            lockedCategory = "",
                            lockedSubCategory = "",
                            lockedConcern = "",
                            guideRound = 0,
                            conversationId = if (AuthManager.isLoggedIn) {
                                response.conversationId.ifBlank { it.conversationId }
                            } else "",
                        )
                    }
                } else {
                    // 追问 → 展示选项
                    val assistantMessage = ChatMessage(
                        role = MessageRole.Assistant,
                        text = response.answer,
                    )
                    val options = response.options.map {
                        com.omnicart.agent.feature.chat.ConstraintOption(it.label, it.value, it.dim)
                    }
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            isGuiding = true,
                            messages = it.messages + assistantMessage,
                            guideOptions = options,
                            lockedCategory = response.lockedCategory.ifBlank { it.lockedCategory },
                            lockedSubCategory = response.lockedSubCategory.ifBlank { it.lockedSubCategory },
                            lockedConcern = response.lockedConcern.ifBlank { it.lockedConcern },
                            guideRound = it.guideRound + 1,
                            conversationId = response.conversationId.ifBlank { it.conversationId },
                        )
                    }
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, isGuiding = false, errorMessage = e.message ?: "网络请求失败")
                }
            }
        }
    }

    /** 用户点击约束按钮 → 发送选项值并继续引导 */
    fun onConstraintSelected(option: ConstraintOption) {
        val state = _uiState.value
        // 用户选择作为文本消息发出
        val userMessage = ChatMessage(role = MessageRole.User, text = option.label)
        _uiState.update { it.copy(messages = it.messages + userMessage, guideOptions = emptyList()) }

        // 更新锁定约束
        val newLockedCategory = when (option.dim) {
            "category" -> option.value
            "sub_category" -> state.lockedCategory
            else -> state.lockedCategory
        }
        val newLockedSubCategory = if (option.dim == "sub_category") option.value else state.lockedSubCategory
        val newLockedConcern = if (option.dim == "concern") option.value else state.lockedConcern
        val newBudgetMax = if (option.dim == "budget") {
            val parts = option.value.split("-")
            if (parts.size == 2) parts[1].toDoubleOrNull() else null
        } else state.budgetMax
        val newBudgetMin = if (option.dim == "budget") {
            val parts = option.value.split("-")
            if (parts.size == 2) parts[0].toDoubleOrNull() else null
        } else state.budgetMin

        _uiState.update {
            it.copy(
                lockedCategory = newLockedCategory,
                lockedSubCategory = newLockedSubCategory,
                lockedConcern = newLockedConcern,
                budgetMax = newBudgetMax,
                budgetMin = newBudgetMin,
            )
        }

        // 继续引导
        sendGuide(option.value)
    }

    private fun appendAssistant(response: RecommendResponse) {
        val assistantMessage = ChatMessage(
            role = MessageRole.Assistant,
            text = response.answer,
            products = response.primaryProducts.ifEmpty { response.products },
            recommendationAlternatives = response.recommendationAlternatives,
            productResolution = response.productResolution,
            decisionResults = response.decisionResults,
            evidenceList = response.evidenceList,
            traceSteps = response.traceSteps,
            harnessReport = response.harnessReport?.mapValues { it.value },
            targetProductAnalysis = response.targetProductAnalysis,
            comparisonTable = response.comparisonTable,
            comparison = response.comparison,
            focusAnalysis = response.focusAnalysis,
            shopCard = response.shopCard,
            actions = response.actions.orEmpty(),
            needsClarification = response.needsClarification,
            clarificationQuestion = response.clarificationQuestion,
            clarificationOptions = response.clarificationOptions.orEmpty(),
            analysisAlternatives = response.analysisAlternatives,
            crossCategory = response.crossCategory,
        )
        _uiState.update {
            it.copy(
                isLoading = false,
                isGuiding = false,
                guideOptions = emptyList(),
                messages = it.messages + assistantMessage,
                lastResponse = response,
                conversationId = response.conversationId.ifBlank { it.conversationId },
            )
        }
    }

    /** SSE 流式发送 — 文字逐字到达并实时显示。 */
    /**
     * All text-like input (keyboard and ASR) enters this one SSE path.  The
     * source flag is presentation-only: it lets the user inspect exactly what
     * ASR submitted without changing routing, context, or recommendation logic.
     */
    fun onSendStream(isVoiceInput: Boolean = false) {
        val query = _uiState.value.queryText.trim()
        val hasImage = _uiState.value.selectedImageUri != null
        if (query.isBlank() && !hasImage) return

        val finalQuery = query.ifBlank { "请帮我分析这个商品" }
        val sentImageUri = _uiState.value.selectedImageUri
        val sentImageUrl = _uiState.value.uploadedImageUrl

        val userMessage = ChatMessage(
            role = MessageRole.User,
            text = finalQuery,
            imageUri = sentImageUri,
            isVoice = isVoiceInput,
        )
        _uiState.update { it.copy(
            messages = it.messages + userMessage,
            queryText = "",
            selectedImageUri = null,
            uploadedImageUrl = null,
            isStreamingText = true,
            streamingText = "",
            streamingPrimaryProducts = emptyList(),
            streamingAlternatives = emptyList(),
            streamingDecisionResults = emptyList(),
            recommendationStage = "",
            streamingResolutionLabel = "",
            streamingVisualResult = null,
            streamingVisualResolution = null,
            errorMessage = null,
            lastResponse = null,
            loadingMessage = if (_uiState.value.deepThink) "欧米正在认真帮你挑选…" else "欧米正在帮你找合适的商品…",
        ) }

        viewModelScope.launch {
            try {
                // 上传图片（如有）
                var imageUrl = sentImageUrl
                if (sentImageUri != null && imageUrl == null) {
                    imageUrl = uploadImage(sentImageUri)
                }

                val obj = JsonObject().apply {
                    addProperty("session_id", _uiState.value.sessionId)
                    if (AuthManager.isLoggedIn) {
                        addProperty("user_id", AuthManager.userId)
                        addProperty("conversation_id", _uiState.value.conversationId)
                    }
                    addProperty("message", finalQuery)
                    if (imageUrl != null) addProperty("image_url", imageUrl)
                    addProperty("deep_think", _uiState.value.deepThink)
                }

                var fullText = ""
                var resultData: JsonObject? = null

                AgentStreamClient.connect(Gson().toJson(obj)).collect { event ->
                    when (event.type) {
                        "token" -> {
                            val text = try {
                                com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("text")?.asString ?: ""
                            } catch (_: Exception) { "" }
                            fullText += text
                            _uiState.update { it.copy(streamingText = fullText) }
                        }
                        "stage" -> {
                            val label = try {
                                com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("text")?.asString ?: ""
                            } catch (_: Exception) { "" }
                            _uiState.update { it.copy(recommendationStage = label, loadingMessage = label) }
                        }
                        "recommendations" -> {
                            try {
                                val preview = Gson().fromJson(event.data, RecommendResponse::class.java)
                                _uiState.update { it.copy(
                                    streamingPrimaryProducts = preview.primaryProducts,
                                    streamingAlternatives = preview.recommendationAlternatives,
                                    streamingDecisionResults = preview.decisionResults,
                                    streamingResolutionLabel = preview.productResolution
                                        ?.get("label")?.toString().orEmpty(),
                                ) }
                            } catch (_: Exception) { }
                        }
                        "visual_result" -> {
                            try {
                                val payload = com.google.gson.JsonParser.parseString(event.data).asJsonObject
                                val visual = Gson().fromJson(payload.get("visual_result"), Map::class.java)
                                val resolution = Gson().fromJson(payload.get("product_resolution"), Map::class.java)
                                _uiState.update { it.copy(
                                    streamingVisualResult = visual as? Map<String, Any?>,
                                    streamingVisualResolution = resolution as? Map<String, Any?>,
                                ) }
                            } catch (_: Exception) { }
                        }
                        "result" -> {
                            try {
                                resultData = com.google.gson.JsonParser.parseString(event.data).asJsonObject
                            } catch (_: Exception) { }
                        }
                        "error" -> {
                            val msg = try {
                                com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("message")?.asString
                            } catch (_: Exception) { null }
                            _uiState.update { it.copy(errorMessage = msg ?: "服务异常") }
                        }
                        "done" -> {
                            _uiState.update { it.copy(isStreamingText = false) }
                        }
                    }
                }

                // 流结束，完整反序列化 RecommendResponse（含 Memory 2.0 + V4 全部字段）
                val gson = Gson()
                val response: RecommendResponse? = if (resultData != null) {
                    try { gson.fromJson(resultData, RecommendResponse::class.java) }
                    catch (_: Exception) { null }
                } else null

                // A transport/provider failure must not become a fake assistant
                // reply.  Web keeps the failed turn retryable; Android now does
                // the same rather than appending a misleading template bubble.
                if (fullText.isBlank() && response?.answer.isNullOrBlank()) {
                    _uiState.update {
                        it.copy(
                            isStreamingText = false,
                            streamingText = "",
                            streamingPrimaryProducts = emptyList(),
                            streamingAlternatives = emptyList(),
                            streamingDecisionResults = emptyList(),
                            recommendationStage = "",
                            streamingResolutionLabel = "",
                            streamingVisualResult = null,
                            streamingVisualResolution = null,
                            errorMessage = it.errorMessage ?: "没有收到欧米的回答，请重试",
                        )
                    }
                    return@launch
                }
                val answer = fullText.ifBlank { response?.answer.orEmpty() }

                val msg = ChatMessage(
                    role = MessageRole.Assistant,
                    text = answer,
                    products = response?.let { it.primaryProducts.ifEmpty { it.products } }.orEmpty(),
                    recommendationAlternatives = response?.recommendationAlternatives ?: emptyList(),
                    productResolution = response?.productResolution,
                    visualResult = response?.visualResult,
                    decisionResults = response?.decisionResults ?: emptyList(),
                    evidenceList = response?.evidenceList ?: emptyList(),
                    traceSteps = response?.traceSteps ?: emptyList(),
                    harnessReport = response?.harnessReport?.mapValues { it.value },
                    targetProductAnalysis = response?.targetProductAnalysis,
                    comparisonTable = response?.comparisonTable,
                    comparison = response?.comparison,
                    focusAnalysis = response?.focusAnalysis,
                    shopCard = response?.shopCard,
                    actions = response?.actions.orEmpty(),
                    needsClarification = response?.needsClarification == true,
                    clarificationQuestion = response?.clarificationQuestion.orEmpty(),
                    clarificationOptions = response?.clarificationOptions.orEmpty(),
                    analysisAlternatives = response?.analysisAlternatives,
                    crossCategory = response?.crossCategory,
                )
                val convId = response?.conversationId ?: ""
                _uiState.update { it.copy(
                    isStreamingText = false,
                    streamingText = "",
                    streamingPrimaryProducts = emptyList(),
                    streamingAlternatives = emptyList(),
                    streamingDecisionResults = emptyList(),
                    recommendationStage = "",
                    streamingResolutionLabel = "",
                    streamingVisualResult = null,
                    streamingVisualResolution = null,
                    messages = it.messages + msg,
                    lastResponse = response?.copy(answer = answer),
                    conversationId = if (AuthManager.isLoggedIn) convId.ifBlank { it.conversationId } else "",
                ) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isStreamingText = false, isLoading = false, errorMessage = "连接失败: ${e.message}") }
            }
        }
    }

    private suspend fun uploadImage(uri: Uri): String? {
        return try {
            val resolver = getApplication<Application>().contentResolver
            val inputStream = resolver.openInputStream(uri) ?: return null
            val bytes = inputStream.use { it.readBytes() }
            val fileName = "photo_${System.currentTimeMillis()}.jpg"

            val requestBody = bytes.toRequestBody("image/jpeg".toMediaTypeOrNull())
            val part = okhttp3.MultipartBody.Part.createFormData("file", fileName, requestBody)
            val response = ApiClient.api.uploadImage(part)
            response.imageUrl
        } catch (e: Exception) {
            null
        }
    }

    /** 问问小O：发送 product_focused_analysis */
    fun sendAskDouzai(productId: String, title: String, comparison: Boolean = false) {
        val query = if (comparison) {
            "请把「${title}」与同类商品横向对比，说明主要差异、分别适合谁，以及我该怎么选。"
        } else {
            "帮我分析一下「${title}」"
        }
        val userMessage = ChatMessage(role = MessageRole.User, text = query)
        _uiState.update { it.copy(
            messages = it.messages + userMessage,
            isStreamingText = true, streamingText = "", errorMessage = null,
            isLoading = true,
            streamingPrimaryProducts = emptyList(), streamingAlternatives = emptyList(),
            streamingDecisionResults = emptyList(), recommendationStage = "", streamingResolutionLabel = "",
            streamingVisualResult = null, streamingVisualResolution = null,
            loadingMessage = if (comparison) "欧米正在横向比较「${title.take(15)}」…" else "欧米正在分析「${title.take(15)}」…",
        ) }
        viewModelScope.launch {
            try {
                val obj = JsonObject().apply {
                    addProperty("session_id", _uiState.value.sessionId)
                    if (AuthManager.isLoggedIn) {
                        addProperty("user_id", AuthManager.userId)
                        addProperty("conversation_id", _uiState.value.conversationId)
                    }
                    addProperty("message", query)
                    addProperty("mode", if (comparison) "same_category_comparison" else "product_focused_analysis")
                    addProperty("target_product_id", productId)
                    // 单品聚焦默认只讲当前商品；用户明确要对比时再扩展同类。
                    addProperty("allow_same_category_comparison", comparison)
                    addProperty("deep_think", _uiState.value.deepThink)
                }
                var fullText = ""
                var resultData: JsonObject? = null
                AgentStreamClient.connect(Gson().toJson(obj)).collect { event ->
                    when (event.type) {
                        "token" -> {
                            val text = try { com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("text")?.asString ?: "" } catch (_: Exception) { "" }
                            fullText += text
                            _uiState.update { it.copy(streamingText = fullText, isLoading = false) }
                        }
                        "stage" -> {
                            val label = try { com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("text")?.asString ?: "" } catch (_: Exception) { "" }
                            _uiState.update { it.copy(recommendationStage = label, loadingMessage = label, isLoading = false) }
                        }
                        "recommendations" -> {
                            try {
                                val preview = Gson().fromJson(event.data, RecommendResponse::class.java)
                                _uiState.update { it.copy(
                                    streamingPrimaryProducts = preview.primaryProducts,
                                    streamingAlternatives = preview.recommendationAlternatives,
                                    streamingDecisionResults = preview.decisionResults,
                                    streamingResolutionLabel = preview.productResolution?.get("label")?.toString().orEmpty(),
                                    isLoading = false,
                                ) }
                            } catch (_: Exception) { }
                        }
                        "focus_analysis", "comparison", "visual_result" -> {
                            // The canonical payload is also delivered in result;
                            // receiving it early keeps both clients on the same
                            // event contract without creating a second state path.
                            if (event.type == "visual_result") {
                                try {
                                    val payload = com.google.gson.JsonParser.parseString(event.data).asJsonObject
                                    val visual = Gson().fromJson(payload.get("visual_result"), Map::class.java)
                                    val resolution = Gson().fromJson(payload.get("product_resolution"), Map::class.java)
                                    _uiState.update { it.copy(
                                        streamingVisualResult = visual as? Map<String, Any?>,
                                        streamingVisualResolution = resolution as? Map<String, Any?>,
                                    ) }
                                } catch (_: Exception) { }
                            }
                        }
                        "result" -> { try { resultData = com.google.gson.JsonParser.parseString(event.data).asJsonObject } catch (_: Exception) { } }
                        "error" -> {
                            val msg = try { com.google.gson.JsonParser.parseString(event.data).asJsonObject.get("message")?.asString } catch (_: Exception) { null }
                            _uiState.update { it.copy(errorMessage = msg ?: "服务异常") }
                        }
                        "done" -> {
                            _uiState.update { it.copy(isStreamingText = false) }
                        }
                    }
                }
                val gson = Gson()
                val response: RecommendResponse? = if (resultData != null) {
                    try { gson.fromJson(resultData, RecommendResponse::class.java) }
                    catch (_: Exception) { null }
                } else null
                if (fullText.isBlank() && response?.answer.isNullOrBlank()) {
                    _uiState.update {
                        it.copy(
                            isStreamingText = false,
                            streamingText = "",
                            streamingPrimaryProducts = emptyList(),
                            streamingAlternatives = emptyList(),
                            streamingDecisionResults = emptyList(),
                            recommendationStage = "",
                            streamingResolutionLabel = "",
                            streamingVisualResult = null,
                            streamingVisualResolution = null,
                            errorMessage = it.errorMessage ?: "没有收到欧米的分析结果，请重试",
                        )
                    }
                    return@launch
                }
                val answer = fullText.ifBlank { response?.answer.orEmpty() }
                val msg = ChatMessage(
                    role = MessageRole.Assistant,
                    text = answer,
                    products = response?.let { it.primaryProducts.ifEmpty { it.products } }.orEmpty(),
                    recommendationAlternatives = response?.recommendationAlternatives ?: emptyList(),
                    productResolution = response?.productResolution,
                    visualResult = response?.visualResult,
                    decisionResults = response?.decisionResults ?: emptyList(),
                    evidenceList = response?.evidenceList ?: emptyList(),
                    traceSteps = response?.traceSteps ?: emptyList(),
                    harnessReport = response?.harnessReport?.mapValues { it.value },
                    targetProductAnalysis = response?.targetProductAnalysis,
                    comparisonTable = response?.comparisonTable,
                    comparison = response?.comparison,
                    focusAnalysis = response?.focusAnalysis,
                    shopCard = response?.shopCard,
                    actions = response?.actions.orEmpty(),
                    needsClarification = response?.needsClarification == true,
                    clarificationQuestion = response?.clarificationQuestion.orEmpty(),
                    clarificationOptions = response?.clarificationOptions.orEmpty(),
                    analysisAlternatives = response?.analysisAlternatives,
                    crossCategory = response?.crossCategory,
                )
                val convId = response?.conversationId ?: ""
                _uiState.update { it.copy(
                    isStreamingText = false,
                    streamingText = "",
                    streamingPrimaryProducts = emptyList(),
                    streamingAlternatives = emptyList(),
                    streamingDecisionResults = emptyList(),
                    recommendationStage = "",
                    streamingResolutionLabel = "",
                    streamingVisualResult = null,
                    streamingVisualResolution = null,
                    messages = it.messages + msg,
                    lastResponse = response?.copy(answer = answer),
                    conversationId = if (AuthManager.isLoggedIn) convId.ifBlank { it.conversationId } else "",
                ) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isStreamingText = false, isLoading = false, errorMessage = "连接失败: ${e.message}") }
            }
        }
    }

    fun toggleDeepThink() {
        _uiState.update { it.copy(deepThink = !it.deepThink) }
    }

    fun onNewConversation() {
        _uiState.update {
            it.copy(
                sessionId = java.util.UUID.randomUUID().toString().take(8),
                conversationId = "",
                messages = emptyList(),
                lastResponse = null,
                selectedProductIndex = -1,
                selectedProductId = null,
                selectedImageUri = null,
                uploadedImageUrl = null,
                guideOptions = emptyList(),
                lockedCategory = "",
                lockedSubCategory = "",
                lockedConcern = "",
                guideRound = 0,
                budgetMax = null,
                budgetMin = null,
            )
        }
    }

    // ---- 历史聊天 (Memory Lite P3) ----

    fun toggleHistorySheet() {
        val show = !_uiState.value.showHistorySheet
        _uiState.update { it.copy(showHistorySheet = show) }
        if (show) {
            loadConversationList()
        }
    }

    fun loadConversationList() {
        val userId = AuthManager.effectiveUserId
        if (userId.isBlank()) return
        _uiState.update { it.copy(isLoadingHistory = true) }
        viewModelScope.launch {
            try {
                val response = ApiClient.api.getConversations(userId)
                _uiState.update {
                    it.copy(
                        conversations = response.conversations,
                        isLoadingHistory = false,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoadingHistory = false, errorMessage = "加载历史失败: ${e.message}")
                }
            }
        }
    }

    fun deleteConversation(conversationId: String) {
        viewModelScope.launch {
            try {
                ApiClient.api.deleteConversation(conversationId)
                // 重新加载列表
                loadConversationList()
                // 如果删除的是当前对话，清空当前聊天
                if (_uiState.value.conversationId == conversationId) {
                    onNewConversation()
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(errorMessage = "删除失败: ${e.message}") }
            }
        }
    }

    fun loadConversation(conversationId: String) {
        _uiState.update { it.copy(isLoadingConversation = true, showHistorySheet = false) }
        viewModelScope.launch {
            try {
                val response = ApiClient.api.getConversationMessages(conversationId)
                val productsMap = response.products ?: emptyMap()
                val historyMessages = response.messages.map { item ->
                    val pids = item.productRefs
                    val prods = pids.mapNotNull { productsMap[it] }.map { p ->
                        com.omnicart.agent.core.model.Product(
                            productId = p["product_id"]?.toString() ?: "",
                            title = p["title"]?.toString() ?: "",
                            brand = p["brand"]?.toString() ?: "",
                            price = (p["price"] as? Number)?.toDouble() ?: 0.0,
                            imageUrls = (p["image_urls"] as? List<*>)?.mapNotNull { it?.toString() } ?: emptyList(),
                        )
                    }
                    ChatMessage(
                        role = if (item.role == "user") MessageRole.User else MessageRole.Assistant,
                        text = item.content,
                        products = prods,
                        imageUri = if (!item.imageUrl.isNullOrBlank()) android.net.Uri.parse(item.imageUrl) else null,
                    )
                }
                _uiState.update {
                    it.copy(
                        conversationId = conversationId,
                        messages = historyMessages,
                        isLoadingConversation = false,
                        lastResponse = null,
                        selectedProductIndex = -1,
                        selectedProductId = null,
                        selectedImageUri = null,
                        uploadedImageUrl = null,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoadingConversation = false, errorMessage = "加载对话失败: ${e.message}")
                }
            }
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

    fun onAddToCart(productId: String, productTitle: String,
                    skuId: String? = null, skuLabel: String = "", skuPrice: Double = 0.0) {
        if (!AuthManager.isLoggedIn) {
            _uiState.update { it.copy(errorMessage = "登录后即可把「${productTitle.take(18)}」加入购物车") }
            return
        }
        viewModelScope.launch {
            try {
                ApiClient.api.addToCart(
                    item = AddToCartRequest(
                        productId = productId,
                        skuId = skuId,
                        quantity = 1,
                    ),
                    userId = AuthManager.effectiveUserId,
                    sessionId = _uiState.value.sessionId,
                    conversationId = _uiState.value.conversationId,
                )
                val label = if (skuLabel.isNotBlank()) "$productTitle ($skuLabel)" else productTitle
                _uiState.update { it.copy(addToCartSuccess = label) }
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
            _uiState.update { it.copy(isRecording = true, recordingSeconds = 0, showVoiceOverlay = true, voiceCancelling = false) }
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

    fun setVoiceCancelling(cancelling: Boolean) {
        _uiState.update { it.copy(voiceCancelling = cancelling) }
    }

    fun stopRecordingAndSend() {
        if (!voiceRecorder.isRecording) return
        recordingTimer?.cancel()
        val file = voiceRecorder.stop() ?: return
        _uiState.update { it.copy(isRecording = false, showVoiceOverlay = false, voiceCancelling = false) }

        // 滑动取消或录音太短 → 不发送
        if (_uiState.value.voiceCancelling || file.length() < 500) {
            file.delete()
            return
        }

        viewModelScope.launch {
            val pendingId = java.util.UUID.randomUUID().toString()
            try {
                val bytes = file.readBytes()
                if (bytes.size < 800) {
                    _uiState.update { it.copy(errorMessage = "录音太短，请至少录制 1 秒") }
                    return@launch
                }
                _uiState.update { it.copy(messages = it.messages + ChatMessage(
                    id = pendingId, role = MessageRole.User, text = "", isVoice = true, isTranscribing = true,
                )) }
                val audioPart = okhttp3.MultipartBody.Part.createFormData(
                    "audio", "voice.m4a", bytes.toRequestBody("audio/m4a".toMediaTypeOrNull()),
                )
                val asr = ApiClient.api.voiceTranscribe(audioPart)
                if (asr.fallback || asr.text.isBlank()) {
                    _uiState.update { it.copy(messages = it.messages.filter { message -> message.id != pendingId }, errorMessage = "没有听清，请再说一次") }
                    return@launch
                }
                // Remove the temporary ASR bubble, then delegate to the exact same
                // text sender. This keeps SSE stages/cards/errors in one code path.
                _uiState.update { it.copy(
                    messages = it.messages.filter { message -> message.id != pendingId },
                    queryText = asr.text.trim(), errorMessage = null,
                ) }
                onSendStream(isVoiceInput = true)
            } catch (e: Exception) {
                _uiState.update { it.copy(
                    messages = it.messages.filter { message -> message.id != pendingId },
                    errorMessage = "语音识别失败：${e.message ?: "请重试"}",
                ) }
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
        _uiState.update { it.copy(voiceAudioUrl = null, voicePlaying = false) }
    }

    /** TTS 语音播报：调用后端 /api/voice/tts，下载后直接用 MediaPlayer 播放 */
    fun playTTS(text: String) {
        val ttsText = text.take(300).trim()
        if (ttsText.isBlank()) return
        viewModelScope.launch {
            try {
                _uiState.update { it.copy(voicePlaying = true) }
                val response = ApiClient.api.voiceTTS(
                    com.omnicart.agent.core.network.TTSRequest(ttsText)
                )
                if (!response.isSuccessful || response.body() == null) {
                    _uiState.update { it.copy(voicePlaying = false) }
                    return@launch
                }
                val audioBytes = response.body()!!.bytes()
                if (audioBytes.size < 100) {
                    _uiState.update { it.copy(voicePlaying = false) }
                    return@launch
                }
                // 写入文件并直接用 MediaPlayer 播放
                val ctx = getApplication<android.app.Application>()
                val file = java.io.File(ctx.filesDir, "tts_reply.wav")
                file.writeBytes(audioBytes)

                val player = android.media.MediaPlayer()
                player.setDataSource(file.absolutePath)
                player.setOnCompletionListener {
                    it.release()
                    _uiState.update { s -> s.copy(voicePlaying = false) }
                }
                player.setOnErrorListener { mp, _, _ ->
                    try { mp.release() } catch (_: Exception) {}
                    _uiState.update { s -> s.copy(voicePlaying = false) }
                    true
                }
                player.prepare()
                player.start()
            } catch (e: Exception) {
                _uiState.update { it.copy(voicePlaying = false) }
            }
        }
    }

    fun onAudioPlaybackComplete() {
        _uiState.update { it.copy(voicePlaying = false) }
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

    override fun onCleared() {
        super.onCleared()
        recordingTimer?.cancel()
        if (voiceRecorder.isRecording) {
            voiceRecorder.stop()
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
