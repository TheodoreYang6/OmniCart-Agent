package com.omnicart.agent.core.network

import com.google.gson.annotations.SerializedName
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.EvidenceItem
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.RecommendRequest
import com.omnicart.agent.core.model.RecommendResponse
import com.omnicart.agent.core.model.TraceStepItem
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface OmniCartApi {

    // ---- 健康 ----
    @GET("api/health")
    suspend fun health(): HealthResponse

    // ---- 商品 ----
    @GET("api/products")
    suspend fun getProducts(
        @Query("category") category: String? = null,
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 50,
    ): ProductListResponse

    @GET("api/products/{product_id}")
    suspend fun getProduct(
        @Path("product_id") productId: String,
    ): ProductDetailResponse

    // ---- 推荐 ----
    @POST("api/recommend/v2")
    suspend fun recommend(@Body request: RecommendRequest): RecommendResponse

    // ---- 约束引导式推荐 ----
    @POST("api/recommend/guide")
    suspend fun recommendGuide(@Body request: GuideRequest): GuideResponse

    // ---- 对话历史 (Memory Lite P3) ----
    @GET("api/conversations")
    suspend fun getConversations(
        @Query("user_id") userId: String,
    ): ConversationListResponse

    @GET("api/conversations/{conversation_id}/messages")
    suspend fun getConversationMessages(
        @Path("conversation_id") conversationId: String,
    ): ConversationMessagesResponse

    @DELETE("api/conversations/{conversation_id}")
    suspend fun deleteConversation(
        @Path("conversation_id") conversationId: String,
    ): OkResponse

    // ---- 上传 ----
    @Multipart
    @POST("api/upload")
    suspend fun uploadImage(@Part file: MultipartBody.Part): UploadResponse

    // ---- 购物车 ----
    @GET("api/cart")
    suspend fun getCart(
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): CartResponse

    @POST("api/cart/items")
    suspend fun addToCart(
        @Body item: AddToCartRequest,
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): CartItemResponse

    @PUT("api/cart/items/{cart_item_id}")
    suspend fun updateCartItem(
        @Path("cart_item_id") cartItemId: String,
        @Body update: UpdateCartRequest,
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): CartItemResponse

    @DELETE("api/cart/items/{cart_item_id}")
    suspend fun removeCartItem(
        @Path("cart_item_id") cartItemId: String,
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): OkResponse

    @POST("api/cart/select-all")
    suspend fun selectAllCart(
        @Query("selected") selected: Boolean = true,
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): OkResponse

    @DELETE("api/cart/clear")
    suspend fun clearCart(
        @Query("user_id") userId: String = "",
        @Query("session_id") sessionId: String = "",
        @Query("conversation_id") conversationId: String = "",
    ): OkResponse

    // ---- 结算 ----
    @POST("api/checkout")
    suspend fun checkout(@Body request: CheckoutRequest): CheckoutResponse

    // ---- 订单 ----
    @GET("api/orders")
    suspend fun getOrders(
        @Query("user_id") userId: String,
    ): OrderListResponse

    // ---- Agent 操作 ----
    @POST("api/agent/action")
    suspend fun agentAction(@Body request: AgentActionRequest): AgentActionResponse

    // ---- Auth ----
    @POST("api/auth/register")
    suspend fun register(@Body request: RegisterRequest): AuthResponse

    @POST("api/auth/login")
    suspend fun login(@Body request: LoginRequest): AuthResponse

    @GET("api/auth/profile")
    suspend fun profile(): AuthResponse

    // ---- 地址 ----
    @GET("api/addresses")
    suspend fun getAddresses(
        @Query("user_id") userId: String = "",
    ): AddressListResponse

    @POST("api/addresses")
    suspend fun createAddress(
        @Body request: AddressCreateRequest,
        @Query("user_id") userId: String = "",
    ): AddressItem

    @PUT("api/addresses/{address_id}")
    suspend fun updateAddress(
        @Path("address_id") addressId: String,
        @Body request: AddressUpdateRequest,
        @Query("user_id") userId: String = "",
    ): AddressItem

    @DELETE("api/addresses/{address_id}")
    suspend fun deleteAddress(
        @Path("address_id") addressId: String,
        @Query("user_id") userId: String = "",
    ): OkResponse

    // ---- 偏好 ----
    @GET("api/preferences")
    suspend fun getPreferences(
        @Query("session_id") sessionId: String,
        @Query("user_id") userId: String = "",
    ): Map<@JvmSuppressWildcards String, @JvmSuppressWildcards Any?>

    @PUT("api/preferences")
    suspend fun updatePreferences(
        @Query("session_id") sessionId: String,
        @Query("user_id") userId: String = "",
        @Body body: Map<@JvmSuppressWildcards String, @JvmSuppressWildcards Any?>,
    ): Map<@JvmSuppressWildcards String, @JvmSuppressWildcards Any?>

    // ---- 长期偏好条目 (V3) ----
    @GET("api/preferences/entries")
    suspend fun getPreferenceEntries(
        @Query("user_id") userId: String,
    ): PreferenceEntriesResponse

    @POST("api/preferences/parse")
    suspend fun parsePreference(
        @Body request: ParseRequest,
    ): ParseResultResponse

    @PUT("api/preferences/entries")
    suspend fun savePreferenceEntry(
        @Body request: PreferenceSaveRequest,
    ): PreferenceSaveResultResponse

    @DELETE("api/preferences/entries/{entry_id}")
    suspend fun deletePreferenceEntry(
        @Path("entry_id") entryId: String,
        @Query("user_id") userId: String,
    ): OkResponse

    // ---- 长期偏好画像 (Profile, 旧兼容) ----
    @GET("api/preferences/profile")
    suspend fun getProfile(
        @Query("user_id") userId: String,
    ): retrofit2.Response<ProfileResponse?>

    @PUT("api/preferences/profile")
    suspend fun saveProfile(
        @Body request: ProfileSaveRequest,
    ): retrofit2.Response<ProfileResponse?>

    @DELETE("api/preferences/profile")
    suspend fun resetProfile(
        @Query("user_id") userId: String,
    ): OkResponse

    @PUT("api/preferences/profile/toggle")
    suspend fun toggleProfile(
        @Query("user_id") userId: String,
        @Query("enabled") enabled: Boolean = true,
    ): ToggleResponse

    @DELETE("api/preferences/profile/field")
    suspend fun deleteProfileField(
        @Query("user_id") userId: String,
        @Query("field") field: String,
        @Query("value") value: String,
    ): OkResponse

    // ---- 记忆 (旧 P1-4, 已废弃) ----
    @GET("api/memories")
    suspend fun getMemories(
        @Query("user_id") userId: String,
    ): MemoryListResponse

    @DELETE("api/memories/{memory_id}")
    suspend fun deleteMemory(
        @Path("memory_id") memoryId: String,
        @Query("user_id") userId: String,
    ): Map<@JvmSuppressWildcards String, @JvmSuppressWildcards Any?>

    // ---- 语音 ----
    @Multipart
    @POST("api/voice/transcribe")
    suspend fun voiceTranscribe(
        @Part audio: MultipartBody.Part,
    ): TranscribeResponse

    @POST("api/voice/tts")
    suspend fun voiceTTS(
        @Body request: TTSRequest,
    ): retrofit2.Response<okhttp3.ResponseBody>

    @Multipart
    @POST("api/voice/chat/v2")
    suspend fun voiceChat(
        @Part audio: MultipartBody.Part,
        @Part("query") query: okhttp3.RequestBody,
    ): VoiceChatResponse
}

// ---- Voice ----

data class TTSRequest(
    val text: String,
    val voice: String = "Cherry",
)

data class TranscribeResponse(
    val text: String = "",
    val fallback: Boolean = false,
)

// ---- Voice ----

data class VoiceChatResponse(
    @SerializedName("session_id")
    val sessionId: String = "",
    val text: String = "",
    @SerializedName("audio_url")
    val audioUrl: String = "",
    @SerializedName("audio_format")
    val audioFormat: String = "wav",
    val voice: String = "",
    @SerializedName("tokens_input")
    val tokensInput: Int = 0,
    @SerializedName("tokens_output")
    val tokensOutput: Int = 0,
    @SerializedName("latency_ms")
    val latencyMs: Int = 0,
    val fallback: Boolean = false,
    @SerializedName("fallback_reason")
    val fallbackReason: String = "",
    @SerializedName("transcribed_text")
    val transcribedText: String = "",
    val products: List<Product> = emptyList(),
    @SerializedName("decision_results")
    val decisionResults: List<DecisionResult> = emptyList(),
    @SerializedName("evidence_list")
    val evidenceList: List<EvidenceItem> = emptyList(),
    @SerializedName("trace_steps")
    val traceSteps: List<TraceStepItem> = emptyList(),
)

// ---- Constraint Guide ----

data class GuideRequest(
    @SerializedName("user_query") val userQuery: String,
    @SerializedName("session_id") val sessionId: String = "",
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("conversation_id") val conversationId: String = "",
    @SerializedName("category") val category: String = "",
    @SerializedName("sub_category") val subCategory: String = "",
    @SerializedName("concern") val concern: String = "",
    @SerializedName("budget_max") val budgetMax: Double? = null,
    @SerializedName("budget_min") val budgetMin: Double? = null,
    @SerializedName("round_num") val roundNum: Int = 0,
)

data class GuideOption(
    @SerializedName("label") val label: String = "",
    @SerializedName("value") val value: String = "",
    @SerializedName("dim") val dim: String = "",
)

data class GuideResponse(
    @SerializedName("session_id") val sessionId: String = "",
    @SerializedName("conversation_id") val conversationId: String = "",
    @SerializedName("answer") val answer: String = "",
    @SerializedName("should_recommend") val shouldRecommend: Boolean = false,
    @SerializedName("options") val options: List<GuideOption> = emptyList(),
    @SerializedName("locked_category") val lockedCategory: String = "",
    @SerializedName("locked_sub_category") val lockedSubCategory: String = "",
    @SerializedName("locked_concern") val lockedConcern: String = "",
    @SerializedName("budget_max") val budgetMax: Double? = null,
    @SerializedName("budget_min") val budgetMin: Double? = null,
    @SerializedName("products") val products: List<Product> = emptyList(),
    @SerializedName("decision_results") val decisionResults: List<DecisionResult> = emptyList(),
    @SerializedName("evidence_list") val evidenceList: List<EvidenceItem> = emptyList(),
    @SerializedName("trace_steps") val traceSteps: List<TraceStepItem> = emptyList(),
)

// ---- Data Classes ----

data class HealthResponse(
    val status: String,
    val service: String,
    val version: String
)

data class ProductListResponse(
    val total: Int = 0,
    val page: Int = 1,
    @SerializedName("page_size")
    val pageSize: Int = 20,
    val items: List<Product> = emptyList(),
)

data class ProductDetailResponse(
    @SerializedName("product_id")
    val productId: String = "",
    val title: String = "",
    val brand: String = "",
    val category: String = "",
    @SerializedName("sub_category")
    val subCategory: String = "",
    val price: Double = 0.0,
    @SerializedName("image_urls")
    val imageUrls: List<String> = emptyList(),
    val skus: List<SkuDto> = emptyList(),
    @SerializedName("marketing_description")
    val marketingDescription: String = "",
    @SerializedName("official_faq")
    val officialFaq: List<FaqDto> = emptyList(),
    @SerializedName("user_reviews")
    val userReviews: List<ReviewDto> = emptyList(),
    @SerializedName("review_summary")
    val reviewSummary: ReviewSummaryDto? = null,
)

data class SkuDto(
    @SerializedName("sku_id") val skuId: String = "",
    val properties: Map<String, String> = emptyMap(),
    val price: Double = 0.0,
)

data class FaqDto(
    val question: String = "",
    val answer: String = "",
)

data class ReviewDto(
    val nickname: String = "",
    val rating: Int = 0,
    val content: String = "",
)

data class ReviewSummaryDto(
    @SerializedName("avg_rating") val avgRating: Double = 0.0,
    @SerializedName("positive_count") val positiveCount: Int = 0,
    @SerializedName("negative_count") val negativeCount: Int = 0,
    @SerializedName("risk_tags") val riskTags: List<String> = emptyList(),
    @SerializedName("total_count") val totalCount: Int = 0,
)

data class UploadResponse(
    @SerializedName("file_id")
    val fileId: String = "",
    val filename: String = "",
    @SerializedName("image_url")
    val imageUrl: String = "",
    @SerializedName("size_bytes")
    val sizeBytes: Long = 0,
    @SerializedName("content_type")
    val contentType: String = "",
)

// ---- Cart ----

data class CartItemResponse(
    @SerializedName("cart_item_id")
    val cartItemId: String = "",
    @SerializedName("user_id")
    val userId: String = "",
    @SerializedName("product_id")
    val productId: String = "",
    @SerializedName("sku_id")
    val skuId: String? = null,
    @SerializedName("sku_label")
    val skuLabel: String = "",
    val title: String = "",
    val brand: String = "",
    val price: Double = 0.0,
    @SerializedName("image_url")
    val imageUrl: String = "",
    val quantity: Int = 1,
    val selected: Boolean = true,
)

data class CartResponse(
    @SerializedName("user_id")
    val userId: String = "",
    val items: List<CartItemResponse> = emptyList(),
    @SerializedName("total_price")
    val totalPrice: Double = 0.0,
    @SerializedName("total_count")
    val totalCount: Int = 0,
)

data class AddToCartRequest(
    @SerializedName("product_id")
    val productId: String,
    @SerializedName("sku_id")
    val skuId: String? = null,
    val quantity: Int = 1,
)

data class UpdateCartRequest(
    val quantity: Int? = null,
    val selected: Boolean? = null,
)

// ---- Checkout ----

data class CheckoutRequest(
    @SerializedName("user_id")
    val userId: String = "",
    @SerializedName("item_ids")
    val itemIds: List<String> = emptyList(),
    @SerializedName("session_id")
    val sessionId: String = "",
    @SerializedName("conversation_id")
    val conversationId: String = "",
)

// ---- Order ----

data class OrderItemDto(
    @SerializedName("cart_item_id") val cartItemId: String = "",
    @SerializedName("product_id") val productId: String = "",
    val title: String = "",
    val brand: String = "",
    val price: Double = 0.0,
    @SerializedName("image_url") val imageUrl: String = "",
    val quantity: Int = 1,
    @SerializedName("sku_label") val skuLabel: String = "",
)

data class OrderDto(
    @SerializedName("order_id") val orderId: String = "",
    @SerializedName("user_id") val userId: String = "",
    val items: List<OrderItemDto> = emptyList(),
    @SerializedName("total_price") val totalPrice: Double = 0.0,
    val status: String = "",
    @SerializedName("created_at") val createdAt: String = "",
)

data class OrderListResponse(
    @SerializedName("user_id") val userId: String = "",
    val orders: List<OrderDto> = emptyList(),
    val count: Int = 0,
)

data class CheckoutResponse(
    @SerializedName("order_id")
    val orderId: String = "",
    @SerializedName("user_id")
    val userId: String = "",
    val items: List<CartItemResponse> = emptyList(),
    @SerializedName("total_price")
    val totalPrice: Double = 0.0,
    val status: String = "",
    val message: String = "",
)

// ---- Agent Action ----

data class AgentActionRequest(
    val action: String,
    @SerializedName("product_id")
    val productId: String,
    @SerializedName("user_id")
    val userId: String = "",
    @SerializedName("session_id")
    val sessionId: String = "",
    @SerializedName("conversation_id")
    val conversationId: String = "",
)

data class AgentActionResponse(
    val status: String = "",
    val action: String = "",
    @SerializedName("product_title")
    val productTitle: String = "",
    @SerializedName("cart_item")
    val cartItem: CartItemResponse? = null,
    @SerializedName("cart_count")
    val cartCount: Int = 0,
)

data class OkResponse(
    val ok: Boolean = false,
)

// ---- Auth ----

data class RegisterRequest(
    val username: String,
    val password: String,
    val email: String = "",
    val phone: String = "",
)

data class LoginRequest(
    val username: String,
    val password: String,
)

data class AuthResponse(
    @SerializedName("user_id")
    val userId: String = "",
    val username: String = "",
    val token: String = "",
    val email: String = "",
    val phone: String = "",
    @SerializedName("avatar_url")
    val avatarUrl: String = "",
    val error: String? = null,
)

// ---- Address ----

data class AddressItem(
    @SerializedName("address_id")
    val addressId: String = "",
    @SerializedName("user_id")
    val userId: String = "",
    val name: String = "",
    val phone: String = "",
    val province: String = "",
    val city: String = "",
    val district: String = "",
    val detail: String = "",
    @SerializedName("is_default")
    val isDefault: Boolean = false,
)

data class AddressListResponse(
    val addresses: List<AddressItem> = emptyList(),
)

data class AddressCreateRequest(
    val name: String,
    val phone: String,
    val province: String = "",
    val city: String = "",
    val district: String = "",
    val detail: String = "",
    @SerializedName("is_default")
    val isDefault: Boolean = false,
)

data class AddressUpdateRequest(
    val name: String? = null,
    val phone: String? = null,
    val province: String? = null,
    val city: String? = null,
    val district: String? = null,
    val detail: String? = null,
    @SerializedName("is_default")
    val isDefault: Boolean? = null,
)

// ---- Conversation History (Memory Lite P3) ----

data class ConversationListResponse(
    @SerializedName("user_id")
    val userId: String = "",
    val count: Int = 0,
    val conversations: List<ConversationItem> = emptyList(),
)

data class ConversationItem(
    @SerializedName("conversation_id")
    val conversationId: String = "",
    @SerializedName("session_id")
    val sessionId: String = "",
    val title: String = "",
    val status: String = "",
    @SerializedName("last_message")
    val lastMessage: String = "",
    @SerializedName("context_snapshot")
    val contextSnapshot: Map<String, Any?>? = null,
    @SerializedName("created_at")
    val createdAt: String = "",
    @SerializedName("updated_at")
    val updatedAt: String = "",
)

data class ConversationMessagesResponse(
    @SerializedName("conversation_id")
    val conversationId: String = "",
    val count: Int = 0,
    val messages: List<ConversationMessageItem> = emptyList(),
)

data class ConversationMessageItem(
    @SerializedName("message_id")
    val messageId: String = "",
    val role: String = "",
    val content: String = "",
    @SerializedName("image_url")
    val imageUrl: String = "",
    @SerializedName("product_refs")
    val productRefs: List<String> = emptyList(),
    @SerializedName("evidence_refs")
    val evidenceRefs: List<String> = emptyList(),
    @SerializedName("created_at")
    val createdAt: String = "",
)

// ---- Preference Entries (V3 条目化) ----

data class PreferenceEntryDto(
    @SerializedName("entry_id") val entryId: String = "",
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("raw_text") val rawText: String = "",
    @SerializedName("category") val category: String = "",
    @SerializedName("sub_category") val subCategory: String = "",
    @SerializedName("brands") val brands: List<String> = emptyList(),
    @SerializedName("scenarios") val scenarios: List<String> = emptyList(),
    @SerializedName("budget_min") val budgetMin: Double? = null,
    @SerializedName("budget_max") val budgetMax: Double? = null,
    @SerializedName("avoid_tags") val avoidTags: List<String> = emptyList(),
    @SerializedName("must_tags") val mustTags: List<String> = emptyList(),
    @SerializedName("enabled") val enabled: Boolean = true,
    @SerializedName("created_at") val createdAt: String = "",
)

data class PreferenceEntriesResponse(
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("entries") val entries: List<PreferenceEntryDto> = emptyList(),
    @SerializedName("count") val count: Int = 0,
)

data class ParseRequest(
    @SerializedName("user_id") val userId: String,
    @SerializedName("raw_text") val rawText: String,
)

data class ParseResultResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("parsed") val parsed: PreferenceEntryDto? = null,
    @SerializedName("error") val error: String? = null,
)

data class PreferenceSaveRequest(
    @SerializedName("user_id") val userId: String,
    @SerializedName("raw_text") val rawText: String,
    @SerializedName("entry_id") val entryId: String = "",
)

data class PreferenceSaveResultResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("entry") val entry: PreferenceEntryDto? = null,
    @SerializedName("error") val error: String? = null,
)

// ---- Profile (长期偏好画像，旧兼容) ----

data class ProfileSaveRequest(
    @SerializedName("user_id") val userId: String,
    @SerializedName("raw_text") val rawText: String,
)

data class ProfileResponse(
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("raw_text") val rawText: String = "",
    @SerializedName("categories") val categories: List<String> = emptyList(),
    @SerializedName("sub_categories") val subCategories: List<String> = emptyList(),
    @SerializedName("brands") val brands: List<String> = emptyList(),
    @SerializedName("devices") val devices: List<String> = emptyList(),
    @SerializedName("scenarios") val scenarios: List<String> = emptyList(),
    @SerializedName("budget_min") val budgetMin: Double? = null,
    @SerializedName("budget_max") val budgetMax: Double? = null,
    @SerializedName("avoid_tags") val avoidTags: List<String> = emptyList(),
    @SerializedName("must_tags") val mustTags: List<String> = emptyList(),
    @SerializedName("enabled") val enabled: Boolean = true,
    @SerializedName("updated_at") val updatedAt: String = "",
)

data class ToggleResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("enabled") val enabled: Boolean = false,
)

// ---- Memory (P1-4, 已废弃) ----

data class MemoryListResponse(
    @SerializedName("user_id")
    val userId: String = "",
    val count: Int = 0,
    val memories: List<UserMemoryItem> = emptyList(),
)

data class UserMemoryItem(
    @SerializedName("memory_id")
    val memoryId: String = "",
    @SerializedName("user_id")
    val userId: String = "",
    @SerializedName("memory_type")
    val memoryType: String = "",
    val content: String = "",
    @SerializedName("structured_value")
    val structuredValue: Map<String, Any?>? = null,
    val source: String = "",
    val confidence: Double = 0.0,
    val status: String = "",
    @SerializedName("session_id")
    val sessionId: String = "",
    @SerializedName("conversation_id")
    val conversationId: String = "",
    @SerializedName("decay_weight")
    val decayWeight: Double = 1.0,
    @SerializedName("created_at")
    val createdAt: String = "",
)
