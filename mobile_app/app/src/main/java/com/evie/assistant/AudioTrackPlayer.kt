package com.evie.assistant

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Base64
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

class AudioTrackPlayer {

    private val sampleRate = 24000
    private var audioTrack: AudioTrack? = null
    private val isPlaying = AtomicBoolean(false)
    private val audioQueue = LinkedBlockingQueue<ByteArray>()
    private var playbackThread: Thread? = null

    // Lazy initialization on first audio playback — never blocks app startup
    @Synchronized
    private fun ensureAudioTrack() {
        if (audioTrack != null && audioTrack?.state == AudioTrack.STATE_INITIALIZED) {
            return
        }

        try {
            val minBufferSize = AudioTrack.getMinBufferSize(
                sampleRate,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            ).coerceAtLeast(8192)

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(minBufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            startPlaybackThread()
        } catch (e: Exception) {
            android.util.Log.e("AudioTrackPlayer", "Failed to init AudioTrack", e)
        }
    }

    private fun startPlaybackThread() {
        if (playbackThread != null && playbackThread!!.isAlive) return

        isPlaying.set(true)
        playbackThread = Thread {
            try {
                audioTrack?.play()
            } catch (_: Exception) {}

            while (isPlaying.get()) {
                try {
                    val chunk = audioQueue.take()
                    if (chunk.isNotEmpty()) {
                        if (audioTrack?.playState != AudioTrack.PLAYSTATE_PLAYING) {
                            try { audioTrack?.play() } catch (_: Exception) {}
                        }
                        audioTrack?.write(chunk, 0, chunk.size)
                    }
                } catch (_: InterruptedException) {
                    break
                } catch (e: Exception) {
                    android.util.Log.e("AudioTrackPlayer", "Error writing audio chunk", e)
                }
            }
        }.apply {
            name = "EvieAudioPlaybackThread"
            priority = Thread.NORM_PRIORITY
            isDaemon = true
            start()
        }
    }

    fun playBase64(b64: String) {
        if (b64.isBlank()) return
        try {
            val raw = Base64.decode(b64, Base64.DEFAULT)
            if (raw.isNotEmpty()) {
                ensureAudioTrack()
                audioQueue.offer(raw)
            }
        } catch (e: Exception) {
            android.util.Log.e("AudioTrackPlayer", "Error decoding base64 audio", e)
        }
    }

    fun playChunk(chunk: ByteArray) {
        if (chunk.isEmpty()) return
        try {
            ensureAudioTrack()
            audioQueue.offer(chunk)
        } catch (e: Exception) {
            android.util.Log.e("AudioTrackPlayer", "Error offering chunk", e)
        }
    }

    fun stop() {
        try {
            audioQueue.clear()
            audioTrack?.pause()
            audioTrack?.flush()
        } catch (_: Exception) {}
    }

    fun release() {
        isPlaying.set(false)
        audioQueue.clear()
        playbackThread?.interrupt()
        playbackThread = null
        try {
            audioTrack?.stop()
            audioTrack?.release()
        } catch (_: Exception) {}
        audioTrack = null
    }
}
