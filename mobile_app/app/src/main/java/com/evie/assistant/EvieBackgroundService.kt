package com.evie.assistant

import android.annotation.SuppressLint
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.google.gson.Gson
import com.google.gson.JsonObject
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class EvieBackgroundService : Service() {

    private lateinit var config: DeviceConfig
    private lateinit var apiClient: EvieApiClient
    private val audioPlayer = AudioTrackPlayer()
    private val gson = Gson()
    private val mainHandler = Handler(Looper.getMainLooper())

    private var activeWebSocket: WebSocket? = null
    private var isDestroyedService = false
    private var isConnected = false
    private var serviceScreenshotObserver: android.database.ContentObserver? = null
    private var serviceTts: android.speech.tts.TextToSpeech? = null
    private var lastServiceScreenshotTs = 0L

    companion object {
        const val CHANNEL_ID_SERVICE = "evie_foreground_service_channel"
        const val CHANNEL_ID_ALERTS  = "evie_alerts_channel"
        const val CHANNEL_ID_PROACTIVE = "evie_proactive_channel"
        const val NOTIFICATION_ID_SERVICE = 1001
        const val NOTIFICATION_ID_DOWNLOAD = 1002
        const val NOTIFICATION_ID_PROACTIVE = 1003

        const val KEY_TEXT_REPLY = "key_proactive_reply"
        const val ACTION_FILE_DOWNLOAD = "com.evie.assistant.ACTION_FILE_DOWNLOAD"
        const val ACTION_PROACTIVE_REPLY = "com.evie.assistant.ACTION_PROACTIVE_REPLY"
        const val ACTION_PROACTIVE_PAUSE = "com.evie.assistant.ACTION_PROACTIVE_PAUSE"

        var instance: EvieBackgroundService? = null
        var activeActivity: MainActivity? = null

        fun start(context: Context) {
            try {
                val intent = Intent(context, EvieBackgroundService::class.java)
                context.startService(intent)
            } catch (e: Exception) {
                android.util.Log.e("EvieService", "Error starting service", e)
            }
        }

        fun stop(context: Context) {
            try {
                val intent = Intent(context, EvieBackgroundService::class.java)
                context.stopService(intent)
            } catch (_: Exception) {}
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        try {
            config = DeviceConfig(this)
            apiClient = EvieApiClient(config)

            createNotificationChannels()
            startForegroundServiceNotification()
            connectWebSocket()
            initBackgroundScreenshotDetector()
        } catch (e: Exception) {
            android.util.Log.e("EvieService", "Failed to initialize EvieBackgroundService", e)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startForegroundServiceNotification()
            if (intent != null) {
                when (intent.action) {
                    ACTION_PROACTIVE_REPLY -> {
                        val replyBundle = androidx.core.app.RemoteInput.getResultsFromIntent(intent)
                        val replyText = replyBundle?.getCharSequence(KEY_TEXT_REPLY)?.toString()
                        if (!replyText.isNullOrBlank()) {
                            sendCommand(replyText) { ok, resp ->
                                val notificationManager = getSystemService(NotificationManager::class.java)
                                val updatedNotification = NotificationCompat.Builder(this, CHANNEL_ID_PROACTIVE)
                                    .setContentTitle("💡 EVIE")
                                    .setContentText("Resposta enviada: $replyText")
                                    .setSmallIcon(android.R.drawable.ic_menu_send)
                                    .setTimeoutAfter(3500)
                                    .build()
                                notificationManager.notify(NOTIFICATION_ID_PROACTIVE, updatedNotification)
                            }
                        }
                    }
                    ACTION_PROACTIVE_PAUSE -> {
                        apiClient.pauseProactivity(60) { ok, _ ->
                            val notificationManager = getSystemService(NotificationManager::class.java)
                            notificationManager.cancel(NOTIFICATION_ID_PROACTIVE)
                        }
                    }
                }
            }
        } catch (_: Exception) {}
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(NotificationManager::class.java)

            // Canal 1: Serviço em segundo plano contínuo (Silencioso)
            val serviceChannel = NotificationChannel(
                CHANNEL_ID_SERVICE,
                "Evie Background Node",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Mantém a Evie ativa em segundo plano para comandos e sincronização"
                setShowBadge(false)
            }
            notificationManager.createNotificationChannel(serviceChannel)

            // Canal 2: Alertas de Download e Ações Imediatas (Alta prioridade / Heads-up)
            val alertChannel = NotificationChannel(
                CHANNEL_ID_ALERTS,
                "Evie Alertas e Transferências",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificações urgentes para recebimento de arquivos e comandos"
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                enableVibration(true)
                setShowBadge(true)
            }
            notificationManager.createNotificationChannel(alertChannel)

            // Canal 3: Proatividade e Ideias Espontâneas (Direct Reply interativo)
            val proactiveChannel = NotificationChannel(
                CHANNEL_ID_PROACTIVE,
                "Evie Insights Proativos",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Mensagens e perguntas espontâneas iniciadas pela Evie com resposta rápida"
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                enableVibration(true)
                setShowBadge(true)
            }
            notificationManager.createNotificationChannel(proactiveChannel)
        }
    }

    private fun startForegroundServiceNotification() {
        try {
            val openAppIntent = Intent(this, MainActivity::class.java).apply {
                this.flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                this,
                0,
                openAppIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(this, CHANNEL_ID_SERVICE)
                .setContentTitle("◈ EVIE ASSISTANT")
                .setContentText("Nó de controle ativo em segundo plano")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                try {
                    startForeground(
                        NOTIFICATION_ID_SERVICE,
                        notification,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
                    )
                } catch (fgsEx: Exception) {
                    android.util.Log.w("EvieService", "Failed type-specific startForeground: ${fgsEx.message}")
                    try {
                        startForeground(NOTIFICATION_ID_SERVICE, notification)
                    } catch (fallbackEx: Exception) {
                        android.util.Log.e("EvieService", "Fallback startForeground also failed", fallbackEx)
                    }
                }
            } else {
                startForeground(NOTIFICATION_ID_SERVICE, notification)
            }
        } catch (e: Exception) {
            android.util.Log.e("EvieService", "Failed to start foreground notification", e)
        }
    }

    fun connectWebSocket() {
        if (isDestroyedService) return

        try {
            activeWebSocket?.close(1000, "Reconnecting service")
            activeWebSocket = apiClient.connectWebSocket(object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    isConnected = true
                    android.util.Log.i("EvieService", "Background WebSocket connected")
                    mainHandler.post {
                        activeActivity?.onServiceConnected(true)
                    }
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    handleWebSocketMessage(text)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    isConnected = false
                    android.util.Log.w("EvieService", "Background WebSocket failure: ${t.localizedMessage}")
                    mainHandler.post {
                        activeActivity?.onServiceConnected(false)
                    }
                    scheduleReconnect()
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    isConnected = false
                    scheduleReconnect()
                }
            })
        } catch (e: Exception) {
            android.util.Log.e("EvieService", "Error connecting websocket in service", e)
            scheduleReconnect()
        }
    }

    private fun scheduleReconnect() {
        if (isDestroyedService) return
        mainHandler.postDelayed({
            if (!isDestroyedService && !isConnected) {
                connectWebSocket()
            }
        }, 3000L)
    }

    private fun handleWebSocketMessage(rawText: String) {
        try {
            val json = gson.fromJson(rawText, JsonObject::class.java) ?: return
            val type = if (json.has("type") && !json.get("type").isJsonNull) json.get("type").asString else ""

            when (type) {
                "audio", "audio_stream" -> {
                    val base64Data = if (json.has("data") && !json.get("data").isJsonNull) json.get("data").asString else ""
                    if (base64Data.isNotEmpty()) {
                        audioPlayer.playBase64(base64Data)
                    }
                    // Notify active activity to reflect speaking state
                    mainHandler.post {
                        activeActivity?.handleBackgroundMessage(json)
                    }
                }

                "audio_end" -> {
                    audioPlayer.stop()
                    mainHandler.post {
                        activeActivity?.handleBackgroundMessage(json)
                    }
                }

                "file_download" -> {
                    val fileName = json.optString("name")
                    val fileUrl = json.optString("url")
                    val httpUrl = json.optString("http_url")
                    val fileSize = json.optLong("size", 0L)
                    val sizeStr = json.optString("size_str")

                    notifyIncomingFileDownload(fileName, fileUrl, httpUrl, fileSize, sizeStr)
                }

                "confirm_request" -> {
                    // Forward to active activity for prompt dialog
                    mainHandler.post {
                        activeActivity?.handleBackgroundMessage(json)
                    }
                }

                "proactive_message", "evie_proactive_message" -> {
                    val text = json.optString("text")
                    val activeWindow = json.optString("active_window")
                    val activeProcess = json.optString("active_process")
                    if (text.isNotBlank()) {
                        notifyProactiveMessage(text, activeWindow, activeProcess)
                    }
                    mainHandler.post {
                        activeActivity?.handleBackgroundMessage(json)
                    }
                }

                else -> {
                    // Forward logs, telemetry and status to active activity if open
                    mainHandler.post {
                        activeActivity?.handleBackgroundMessage(json)
                    }
                }
            }
        } catch (e: Exception) {
            android.util.Log.e("EvieService", "Error handling background ws message", e)
        }
    }

    @SuppressLint("WakelockTimeout")
    private fun notifyIncomingFileDownload(
        fileName: String,
        fileUrl: String,
        httpUrl: String,
        fileSize: Long,
        sizeStr: String
    ) {
        // 1. Acorda o dispositivo se estiver com a tela desligada
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            @Suppress("DEPRECATION")
            val wakeLock = pm.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "Evie:DownloadWakeLock"
            )
            wakeLock.acquire(10000L)
        } catch (e: Exception) {
            android.util.Log.w("EvieService", "Failed to acquire wake lock: ${e.message}")
        }

        // 2. Prepara Intent para lançar / trazer MainActivity para o primeiro plano
        val intent = Intent(this, MainActivity::class.java).apply {
            action = ACTION_FILE_DOWNLOAD
            putExtra("name", fileName)
            putExtra("url", fileUrl)
            putExtra("http_url", httpUrl)
            putExtra("size", fileSize)
            putExtra("size_str", sizeStr)
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or
                Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
        }

        val pendingIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID_DOWNLOAD,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // 3. Monta Notificação de Alta Prioridade com Full-Screen Intent (aparece na tela de bloqueio)
        val notification = NotificationCompat.Builder(this, CHANNEL_ID_ALERTS)
            .setContentTitle("◈ EVIE: RECEBIMENTO DE ARQUIVO")
            .setContentText("Arquivo pronto: $fileName ($sizeStr)")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setFullScreenIntent(pendingIntent, true)
            .addAction(
                android.R.drawable.stat_sys_download_done,
                "[ BAIXAR NO CELULAR ]",
                pendingIntent
            )
            .build()

        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(NOTIFICATION_ID_DOWNLOAD, notification)

        // 4. Se a atividade já estiver visível ou pronta, dispara diretamente na UI
        mainHandler.post {
            val act = activeActivity
            if (act != null) {
                act.showFileDownloadPopup(fileName, fileUrl, httpUrl, fileSize, sizeStr)
            } else {
                try {
                    startActivity(intent)
                } catch (_: Exception) {}
            }
        }
    }

    @SuppressLint("WakelockTimeout")
    fun notifyProactiveMessage(
        text: String,
        activeWindow: String?,
        activeProcess: String?
    ) {
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            @Suppress("DEPRECATION")
            val wakeLock = pm.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "Evie:ProactiveWakeLock"
            )
            wakeLock.acquire(8000L)
        } catch (_: Exception) {}

        // 1. Direct Reply RemoteInput
        val remoteInput = androidx.core.app.RemoteInput.Builder(KEY_TEXT_REPLY)
            .setLabel("Responder à Evie...")
            .build()

        val replyIntent = Intent(this, EvieBackgroundService::class.java).apply {
            action = ACTION_PROACTIVE_REPLY
        }
        val replyPendingIntent = PendingIntent.getService(
            this,
            1004,
            replyIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )

        val replyAction = NotificationCompat.Action.Builder(
            android.R.drawable.ic_menu_send,
            "Responder",
            replyPendingIntent
        ).addRemoteInput(remoteInput).build()

        // 2. Pause 1h action
        val pauseIntent = Intent(this, EvieBackgroundService::class.java).apply {
            action = ACTION_PROACTIVE_PAUSE
        }
        val pausePendingIntent = PendingIntent.getService(
            this,
            1005,
            pauseIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val pauseAction = NotificationCompat.Action.Builder(
            android.R.drawable.ic_media_pause,
            "Pausar 1h",
            pausePendingIntent
        ).build()

        // 3. Open App Content Intent
        val openIntent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val contentPendingIntent = PendingIntent.getActivity(
            this,
            1006,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val headerCtx = if (!activeWindow.isNullOrBlank()) "💡 EVIE [$activeWindow]" else "💡 EVIE • INICIATIVA"

        val notification = NotificationCompat.Builder(this, CHANNEL_ID_PROACTIVE)
            .setContentTitle(headerCtx)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setContentIntent(contentPendingIntent)
            .addAction(replyAction)
            .addAction(pauseAction)
            .build()

        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(NOTIFICATION_ID_PROACTIVE, notification)
    }

    fun sendCommand(text: String, callback: (Boolean, String) -> Unit) {
        val wsPayload = JsonObject().apply {
            addProperty("type", "command")
            addProperty("text", text)
            addProperty("device", config.deviceName)
        }
        val sent = activeWebSocket?.send(wsPayload.toString()) ?: false
        if (sent) {
            callback(true, "Comando enviado via WebSocket")
        } else {
            apiClient.sendCommand(text, callback)
        }
    }

    fun stopAudioPlayback() {
        audioPlayer.stop()
    }

    private fun initBackgroundScreenshotDetector() {
        try {
            serviceTts = android.speech.tts.TextToSpeech(applicationContext) { status ->
                if (status == android.speech.tts.TextToSpeech.SUCCESS) {
                    serviceTts?.setLanguage(java.util.Locale("pt", "BR"))
                }
            }
        } catch (_: Exception) {}

        try {
            serviceScreenshotObserver = object : android.database.ContentObserver(mainHandler) {
                override fun onChange(selfChange: Boolean, uri: android.net.Uri?) {
                    super.onChange(selfChange, uri)
                    onScreenshotObserved()
                }
            }
            contentResolver.registerContentObserver(
                android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                true,
                serviceScreenshotObserver!!
            )
        } catch (e: Exception) {
            android.util.Log.w("EvieService", "Could not register background screenshot observer", e)
        }
    }

    private fun onScreenshotObserved() {
        val now = System.currentTimeMillis()
        if (now - lastServiceScreenshotTs < 3000) return
        lastServiceScreenshotTs = now

        if (activeActivity != null) {
            activeActivity?.checkAndHandleLatestScreenshot(fromCallback = false)
            return
        }

        try {
            serviceTts?.speak("Detectei uma captura de tela. Gostaria que eu analisasse a imagem?", android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "service_screenshot")
        } catch (_: Exception) {}

        showScreenshotAlertNotification()
    }

    private fun showScreenshotAlertNotification() {
        try {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("action_analyze_screenshot", true)
            }
            val pi = PendingIntent.getActivity(
                this,
                99,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(this, CHANNEL_ID_ALERTS)
                .setContentTitle("📸 CAPTURA DE TELA DETECTADA")
                .setContentText("Evie detectou um print. Toque para analisar com IA.")
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .addAction(android.R.drawable.ic_menu_view, "ANALISAR", pi)
                .build()

            val manager = getSystemService(NotificationManager::class.java)
            manager.notify(1005, notification)
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        super.onDestroy()
        isDestroyedService = true
        activeWebSocket?.close(1000, "Service destroyed")
        audioPlayer.release()
        serviceScreenshotObserver?.let {
            try { contentResolver.unregisterContentObserver(it) } catch (_: Exception) {}
        }
        serviceTts?.stop()
        serviceTts?.shutdown()
        serviceTts = null
        instance = null
    }
}
