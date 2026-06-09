package com.omnicart.agent.core.network

import com.omnicart.agent.core.config.AppConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
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
        val req = Request.Builder()
            .url("${AppConfig.BASE_URL.trimEnd('/')}/api/recommend/stream")
            .post(body)
            .header("Accept", "text/event-stream")
            .build()

        val call = client.newCall(req)
        withContext(Dispatchers.IO) {
            try {
                val resp = call.execute()
                if (!resp.isSuccessful) { close(RuntimeException("SSE ${resp.code}")); return@withContext }
                val reader = BufferedReader(InputStreamReader(resp.body?.byteStream(), Charsets.UTF_8))
                var type = ""
                reader.forEachLine { line ->
                    when {
                        line.startsWith("event: ") -> type = line.removePrefix("event: ").trim()
                        line.startsWith("data: ") -> trySend(SseEvent(type, line.removePrefix("data: ").trim()))
                    }
                }
            } catch (e: Exception) { close(e) }
            finally { close() }
        }
        awaitClose { call.cancel() }
    }
}
