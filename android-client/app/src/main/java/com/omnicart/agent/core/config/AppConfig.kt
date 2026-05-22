package com.omnicart.agent.core.config

object AppConfig {
    // Android 模拟器中 10.0.2.2 指向宿主机的 localhost
    // 真机调试时请替换为电脑的局域网 IP 地址
    const val BASE_URL = "http://127.0.0.1:8006/"

    const val TIMEOUT_SECONDS = 30L
}
