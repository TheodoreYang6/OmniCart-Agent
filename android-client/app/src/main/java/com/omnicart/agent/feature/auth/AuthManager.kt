package com.omnicart.agent.feature.auth

import android.content.Context
import android.content.SharedPreferences

/** 简单的 Token + 用户信息持久化管理。 */
object AuthManager {
    private const val PREFS_NAME = "omnicart_auth"
    private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    private fun prefs(): SharedPreferences? = prefs

    val isLoggedIn: Boolean
        get() = token.isNotBlank()

    var token: String
        get() = prefs()?.getString("token", "") ?: ""
        set(value) { prefs()?.edit()?.putString("token", value)?.apply() }

    var userId: String
        get() = prefs()?.getString("user_id", "") ?: ""
        set(value) { prefs()?.edit()?.putString("user_id", value)?.apply() }

    /** 设备级匿名用户ID (UUID)，未登录时使用，确保不同设备数据隔离。首次访问时自动生成并持久化。 */
    val deviceUserId: String
        get() {
            val existing = prefs()?.getString("device_user_id", "") ?: ""
            if (existing.isNotBlank()) return existing
            val newId = "device_${java.util.UUID.randomUUID().toString().take(8)}"
            prefs()?.edit()?.putString("device_user_id", newId)?.apply()
            return newId
        }

    /** 获取当前有效用户ID：已登录返回真实ID，未登录返回设备匿名ID。 */
    val effectiveUserId: String
        get() = userId.ifBlank { deviceUserId }

    var username: String
        get() = prefs()?.getString("username", "") ?: ""
        set(value) { prefs()?.edit()?.putString("username", value)?.apply() }

    fun saveLogin(userId: String, username: String, token: String, email: String, phone: String) {
        prefs()?.edit()
            ?.putString("user_id", userId)
            ?.putString("username", username)
            ?.putString("token", token)
            ?.putString("email", email)
            ?.putString("phone", phone)
            ?.apply()
    }

    fun logout() {
        prefs()?.edit()?.clear()?.apply()
    }
}
