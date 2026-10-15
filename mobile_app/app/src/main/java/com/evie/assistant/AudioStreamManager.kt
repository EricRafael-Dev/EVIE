package com.evie.assistant

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import okhttp3.*
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class AudioStreamManager(private val config: DeviceConfig) {

    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT

    private var audioRecord: AudioRecord? = null
    private var recordThread: Thread? = null
    private val isRecording = AtomicBoolean(false)

    private val client = EvieApiClient.createClient()

    private var audioWs: WebSocket? = null

    @SuppressLint("MissingPermission")
    fun startStreaming(onStateChanged: (Boolean, String) -> Unit) {
        if (isRecording.get()) return

        val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat).coerceAtLeast(2048)
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            sampleRate,
            channelConfig,
            audioFormat,
            bufferSize
        )

        val wsUrl = "${config.wsBaseUrl}/ws/phone-audio?token=${config.authToken}"
        val request = Request.Builder().url(wsUrl).build()

        audioWs = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isRecording.set(true)
                audioRecord?.startRecording()
                onStateChanged(true, "Gravando áudio...")

                recordThread = Thread {
                    val buffer = ByteArray(1024)
                    while (isRecording.get()) {
                        val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                        if (read > 0) {
                            webSocket.send(buffer.copyOf(read).toByteString())
                        }
                    }
                }.apply { start() }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                stopStreaming()
                onStateChanged(false, "Falha na conexão de voz: ${t.localizedMessage}")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                stopStreaming()
                onStateChanged(false, "Voz finalizada")
            }
        })
    }

    fun stopStreaming() {
        if (!isRecording.getAndSet(false)) return
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (_: Exception) {}
        audioRecord = null
        recordThread?.interrupt()
        recordThread = null

        audioWs?.close(1000, "User stopped speaking")
        audioWs = null
    }

    fun isLive(): Boolean = isRecording.get()
}
