package com.omnicart.agent.feature.chat

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

/** 语音录制工具 — M4A 格式 (AAC 编码，16kHz) */
class VoiceRecorder(private val context: Context) {

    private var recorder: MediaRecorder? = null
    private var _outputFile: File? = null

    val isRecording: Boolean get() = recorder != null
    val outputFile: File? get() = _outputFile

    fun start(): File {
        stop()

        _outputFile = File(context.cacheDir, "voice_${System.currentTimeMillis()}.m4a")
        _outputFile?.parentFile?.mkdirs()

        recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }

        recorder?.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setOutputFile(_outputFile!!.absolutePath)
            setAudioSamplingRate(16000)
            setAudioEncodingBitRate(64000)
            prepare()
            start()
        }

        return _outputFile!!
    }

    fun stop(): File? {
        try {
            recorder?.apply {
                stop()
                reset()
                release()
            }
        } catch (_: Exception) { }

        recorder = null
        return _outputFile
    }

    fun cancel() {
        try {
            recorder?.apply {
                stop()
                reset()
                release()
            }
        } catch (_: Exception) { }
        recorder = null
        _outputFile?.delete()
        _outputFile = null
    }
}
