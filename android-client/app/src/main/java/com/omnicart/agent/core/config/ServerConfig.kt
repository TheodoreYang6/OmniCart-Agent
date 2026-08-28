package com.omnicart.agent.core.config

import android.content.Context
import com.omnicart.agent.BuildConfig

/**
 * 服务器地址运行时配置。
 *
 * Debug 包的默认地址是设备回环地址，配合 adb reverse 访问开发机。旧版本曾把
 * 局域网 IP 无条件写进 SharedPreferences，网络切换后它会永久覆盖这个默认值，
 * 造成“后端明明启动了，手机却连不上”的假象。这里把旧值作为一次性迁移处理；
 * 用户在设置页重新保存过的自定义地址仍会被保留。
 */
object ServerConfig {
    private const val PREFS = "omnicart_settings"
    private const val KEY = "server_url"
    private const val KEY_EXPLICIT_OVERRIDE = "server_url_explicit_override"

    fun load(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val url = prefs.getString(KEY, null)
        val explicitOverride = prefs.getBoolean(KEY_EXPLICIT_OVERRIDE, false)
        if (BuildConfig.DEBUG && !url.isNullOrBlank() && !explicitOverride) {
            // A value written by the legacy build is not an intentional override.
            // Start from the stable adb-reverse default instead of a stale Wi-Fi IP.
            prefs.edit().remove(KEY).apply()
            AppConfig.updateBaseUrl("")
            return
        }
        if (!url.isNullOrBlank()) {
            AppConfig.updateBaseUrl(url)
        }
    }

    fun save(context: Context, url: String) {
        AppConfig.updateBaseUrl(url)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, AppConfig.BASE_URL)
            .putBoolean(KEY_EXPLICIT_OVERRIDE, true)
            .apply()
    }

    fun current(): String = AppConfig.BASE_URL
}
