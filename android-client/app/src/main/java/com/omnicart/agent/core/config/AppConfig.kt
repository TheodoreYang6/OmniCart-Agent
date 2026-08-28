package com.omnicart.agent.core.config

import com.omnicart.agent.BuildConfig

object AppConfig {
    var BASE_URL: String = BuildConfig.BASE_URL

    const val HEALTH_PATH = "api/health"
    const val TIMEOUT_SECONDS = 30L

    fun updateBaseUrl(url: String) {
        var u = url.trim()
        if (u.isEmpty()) {
            BASE_URL = BuildConfig.BASE_URL
            return
        }
        if (!u.startsWith("http://") && !u.startsWith("https://")) {
            u = "http://$u"
        }
        if (!u.endsWith("/")) {
            u = "$u/"
        }
        BASE_URL = u
    }
}
