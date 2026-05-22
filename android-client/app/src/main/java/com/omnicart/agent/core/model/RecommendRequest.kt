package com.omnicart.agent.core.model

import com.google.gson.annotations.SerializedName

data class RecommendRequest(
    @SerializedName("user_query")
    val userQuery: String,
    @SerializedName("image_url")
    val imageUrl: String? = null,
    @SerializedName("demo_mode")
    val demoMode: Boolean = false,
    @SerializedName("session_id")
    val sessionId: String = "",
)
