package com.omnicart.agent.core.network

import com.omnicart.agent.core.config.AppConfig
import com.omnicart.agent.feature.auth.AuthManager
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    private val okHttpClient: OkHttpClient by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        OkHttpClient.Builder()
            .addInterceptor(logging)
            .addInterceptor { chain ->
                val token = AuthManager.token
                val request = if (token.isNotBlank()) {
                    chain.request().newBuilder()
                        .header("Authorization", "Bearer $token")
                        .build()
                } else {
                    chain.request()
                }
                chain.proceed(request)
            }
            .connectTimeout(AppConfig.TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(AppConfig.TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .writeTimeout(AppConfig.TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .build()
    }

    val api: OmniCartApi by lazy {
        Retrofit.Builder()
            .baseUrl(AppConfig.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(OmniCartApi::class.java)
    }
}
