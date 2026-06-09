package com.omnicart.agent.core.config

import com.omnicart.agent.BuildConfig

object AppConfig {
    val BASE_URL: String get() = BuildConfig.BASE_URL
    const val TIMEOUT_SECONDS = 30L
}
