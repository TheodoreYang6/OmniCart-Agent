package com.omnicart.agent.core.network

import com.omnicart.agent.core.config.AppConfig
import com.omnicart.agent.feature.auth.AuthManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Call
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

/** 极简 SSE 客户端 — 只解析 event/data 行 */
object AgentStreamClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.MINUTES)
        .build()

    data class SseEvent(val type: String, val data: String)

    fun connect(requestJson: String): Flow<SseEvent> = callbackFlow {
        val body = requestJson.toRequestBody("application/json; charset=utf-8".toMediaType())
        fun request(includeToken: Boolean): Request = Request.Builder()
            .url("${AppConfig.BASE_URL.trimEnd('/')}/api/recommend/stream")
            .post(body)
            .header("Accept", "text/event-stream")
            .apply {
                if (includeToken) {
                    AuthManager.token.takeIf { it.isNotBlank() }?.let {
                        header("Authorization", "Bearer $it")
                    }
                }
            }
            .build()

        var activeCall: Call? = null
        withContext(Dispatchers.IO) {
            try {
                val hadToken = AuthManager.token.isNotBlank()
                activeCall = client.newCall(request(includeToken = hadToken))
                var resp = activeCall!!.execute()

                // An old app/database/session may leave an invalid Bearer token in
                // SharedPreferences. Public recommendation must remain usable as a
                // guest, but we must not weaken server-side invalid-token checks.
                if (resp.code == 401 && hadToken) {
                    resp.close()
                    AuthManager.logout()
                    activeCall = client.newCall(request(includeToken = false))
                    resp = activeCall!!.execute()
                }
                if (!resp.isSuccessful) {
                    close(RuntimeException("SSE ${resp.code}"))
                    return@withContext
                }
                resp.use { response ->
                    val reader = BufferedReader(InputStreamReader(response.body?.byteStream(), Charsets.UTF_8))
                    var type = ""
                    val dataLines = mutableListOf<String>()
                    fun flush() {
                        if (dataLines.isNotEmpty()) {
                            trySend(SseEvent(type, dataLines.joinToString("\n")))
                        }
                        dataLines.clear()
                    }
                    var line: String?
                    while (true) {
                        line = reader.readLine() ?: break
                        when {
                            line.isEmpty() -> { flush(); type = "" }
                            line.startsWith("event: ") -> type = line.removePrefix("event: ").trim()
                            line.startsWith("data: ") -> dataLines.add(line.removePrefix("data: ").trim())
                        }
                    }
                    flush()
                }
            } catch (e: Exception) { close(e) }
            finally { close() }
        }
        awaitClose { activeCall?.cancel() }
    }
}
