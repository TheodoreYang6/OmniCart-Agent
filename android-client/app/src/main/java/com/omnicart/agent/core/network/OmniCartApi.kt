package com.omnicart.agent.core.network

import com.google.gson.annotations.SerializedName
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.model.RecommendRequest
import com.omnicart.agent.core.model.RecommendResponse
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

    // ---- 上传 ----
    @Multipart
    @POST("api/upload")
    suspend fun uploadImage(@Part file: MultipartBody.Part): UploadResponse

    // ---- 购物车 ----
    @GET("api/cart")
    suspend fun getCart(
        @Query("user_id") userId: String = "demo_user_001",
    ): CartResponse

    @POST("api/cart/items")
    suspend fun addToCart(
        @Body item: AddToCartRequest,
        @Query("user_id") userId: String = "demo_user_001",
    ): CartItemResponse

    @PUT("api/cart/items/{cart_item_id}")
    suspend fun updateCartItem(
        @Path("cart_item_id") cartItemId: String,
        @Body update: UpdateCartRequest,
        @Query("user_id") userId: String = "demo_user_001",
    ): CartItemResponse

    @DELETE("api/cart/items/{cart_item_id}")
    suspend fun removeCartItem(
        @Path("cart_item_id") cartItemId: String,
        @Query("user_id") userId: String = "demo_user_001",
    ): OkResponse

    @POST("api/cart/select-all")
    suspend fun selectAllCart(
        @Query("selected") selected: Boolean = true,
        @Query("user_id") userId: String = "demo_user_001",
    ): OkResponse

    @DELETE("api/cart/clear")
    suspend fun clearCart(
        @Query("user_id") userId: String = "demo_user_001",
    ): OkResponse

    // ---- 结算 ----
    @POST("api/checkout")
    suspend fun checkout(@Body request: CheckoutRequest): CheckoutResponse

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
        @Query("user_id") userId: String = "demo_user_001",
    ): AddressListResponse

    @POST("api/addresses")
    suspend fun createAddress(
        @Body request: AddressCreateRequest,
        @Query("user_id") userId: String = "demo_user_001",
    ): AddressItem

    @PUT("api/addresses/{address_id}")
    suspend fun updateAddress(
        @Path("address_id") addressId: String,
        @Body request: AddressUpdateRequest,
        @Query("user_id") userId: String = "demo_user_001",
    ): AddressItem

    @DELETE("api/addresses/{address_id}")
    suspend fun deleteAddress(
        @Path("address_id") addressId: String,
        @Query("user_id") userId: String = "demo_user_001",
    ): OkResponse

    // ---- 偏好 ----
    @GET("api/preferences")
    suspend fun getPreferences(
        @Query("session_id") sessionId: String,
    ): Map<String, Any?>

    @PUT("api/preferences")
    suspend fun updatePreferences(
        @Query("session_id") sessionId: String,
        @Body body: Map<String, Any?>,
    ): Map<String, Any?>
}

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
    val skus: List<Map<String, Any?>>? = null,
    @SerializedName("rag_knowledge")
    val ragKnowledge: Map<String, Any?>? = null,
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
    val userId: String = "demo_user_001",
    @SerializedName("item_ids")
    val itemIds: List<String> = emptyList(),
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
    val userId: String = "demo_user_001",
    @SerializedName("session_id")
    val sessionId: String = "",
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
