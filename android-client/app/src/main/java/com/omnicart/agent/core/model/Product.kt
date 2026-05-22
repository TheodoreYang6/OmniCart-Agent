package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class Product(
    @SerializedName("product_id")
    val productId: String = "",
    @SerializedName("title")
    val title: String = "",
    @SerializedName("brand")
    val brand: String = "",
    @SerializedName("category")
    val category: String = "",
    @SerializedName("sub_category")
    val subCategory: String = "",
    @SerializedName("price")
    val price: Double = 0.0,
    @SerializedName("image_urls")
    val imageUrls: List<String> = emptyList(),
    @SerializedName("skus")
    val skus: List<Sku>? = null,
    @SerializedName("rag_knowledge")
    val ragKnowledge: RagKnowledge? = null,
    @SerializedName("description")
    val description: String = ""
)

data class Sku(
    @SerializedName("sku_id")
    val skuId: String = "",
    @SerializedName("properties")
    val properties: Map<String, String>? = null,
    @SerializedName("price")
    val price: Double = 0.0
)

data class RagKnowledge(
    @SerializedName("marketing_description")
    val marketingDescription: String = "",
    @SerializedName("official_faq")
    val officialFaq: List<FaqItem>? = null,
    @SerializedName("user_reviews")
    val userReviews: List<ReviewItem>? = null
)

data class FaqItem(
    @SerializedName("question")
    val question: String = "",
    @SerializedName("answer")
    val answer: String = ""
)

data class ReviewItem(
    @SerializedName("nickname")
    val nickname: String = "",
    @SerializedName("rating")
    val rating: Int = 0,
    @SerializedName("content")
    val content: String = ""
)
