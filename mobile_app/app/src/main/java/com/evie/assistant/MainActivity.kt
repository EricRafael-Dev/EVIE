package com.evie.assistant

import android.Manifest
import android.content.pm.PackageManager
import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.webkit.MimeTypeMap
import android.widget.EditText
import android.widget.Toast
import android.widget.TextView
import android.widget.ImageView
import android.widget.Button
import android.widget.LinearLayout
import android.app.Activity
import android.database.ContentObserver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.ImageDecoder
import android.graphics.Matrix
import android.graphics.RectF
import android.provider.OpenableColumns
import android.speech.tts.TextToSpeech
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.evie.assistant.databinding.ActivityMainBinding
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.*


class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var config: DeviceConfig
    private lateinit var apiClient: EvieApiClient
    private lateinit var audioManager: AudioStreamManager
    private lateinit var proceduralRenderer: ProceduralUIRenderer

    private val gson = Gson()
    private val mainHandler = Handler(Looper.getMainLooper())
    private var isConnected = false
    private var isDestroyedActivity = false
    private val processedDownloads = Collections.synchronizedSet(mutableSetOf<String>())
    private var activeDownloadDialog: AlertDialog? = null

    private val activityLogs = StringBuilder()
    private var lastSentMessage = ""
    private var isEvieStreaming = false
    private var streamingStartIdx = -1

    private var tts: TextToSpeech? = null
    private var isTtsReady = false
    private var activeScreenshotDialog: AlertDialog? = null
    private var lastScreenshotTimestamp = 0L
    private var screenshotObserver: ContentObserver? = null
    private var screenCaptureCallback: Any? = null


    data class ProactiveInsight(
        val timestamp: String,
        val text: String,
        val window: String? = null
    )
    private val proactiveInsights = mutableListOf<ProactiveInsight>()
    private var currentAutonomyMode = "balanced"

    private val resetHologramRunnable = Runnable {
        if (!audioManager.isLive()) {
            binding.hologramCore.setState(HologramSphereView.CoreState.IDLE)
            binding.tvCoreStatus.text = "◉ ONLINE"
            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_cyan))
            binding.tvEyesSubtitle?.visibility = View.GONE
        }
    }

    private val clockRunnable = object : Runnable {
        override fun run() {
            val now = Date()
            val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(now)
            val dateFmt = SimpleDateFormat("EEE dd MMM yyyy", Locale.US).format(now)
            binding.tvClock.text = timeFmt
            binding.tvDate.text = dateFmt
            mainHandler.postDelayed(this, 1000L)
        }
    }

    private val recordAudioPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                toggleMic()
            } else {
                Toast.makeText(this, "Permissão de microfone necessária", Toast.LENGTH_SHORT).show()
            }
        }

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { _ ->
            try {
                EvieBackgroundService.start(this)
            } catch (_: Exception) {}
        }

    private val cameraPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                takePictureLauncher.launch(null)
            } else {
                Toast.makeText(this, "Permissão de câmera necessária", Toast.LENGTH_SHORT).show()
            }
        }

    private val takePictureLauncher =
        registerForActivityResult(ActivityResultContracts.TakePicturePreview()) { bitmap ->
            if (bitmap != null) {
                sendCapturedVision(bitmap)
            }
        }

    private val pickImageLauncher =
        registerForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
            uri?.let { handleGalleryImageSelected(it) }
        }

    private val pickDocumentLauncher =
        registerForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
            uri?.let { handleDocumentSelected(it) }
        }

    private val mediaPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                setupScreenshotDetection()
            }
        }

    private var activeConfirmDialog: AlertDialog? = null
    private var activeConfirmKey: String? = null
    private var confirmTimerRunnable: Runnable? = null
    private var isMobileAudioActive = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Wake screen and display on lock screen
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            )
        }

        // Protect against uncaught crashes on edge cases
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            android.util.Log.e("EvieApp", "Uncaught exception on thread ${thread.name}", throwable)
            defaultHandler?.uncaughtException(thread, throwable)
        }

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        config = DeviceConfig(this)
        apiClient = EvieApiClient(config)
        audioManager = AudioStreamManager(config)

        initTextToSpeech()

        setupUI()
        setupListeners()
        setupScreenshotDetection()
        startClock()

        // Request notification permission on Android 13+ cleanly
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        // Request media/storage permission for gallery and screenshot detection
        val mediaPerm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_IMAGES
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }
        if (ContextCompat.checkSelfPermission(this, mediaPerm) != PackageManager.PERMISSION_GRANTED) {
            mediaPermissionLauncher.launch(mediaPerm)
        }

        // Initial default log matching reference
        appendLog("SYS: JARVIS online - sleeping. Say 'Hey Jarvis' to wake me.")

        try {
            EvieBackgroundService.start(this)
            EvieBackgroundService.activeActivity = this
        } catch (e: Exception) {
            android.util.Log.e("EvieApp", "Could not start EvieBackgroundService", e)
        }

        refreshConnection()
        connectEventFeed()
        mainHandler.post(telemetryRunnable)

        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        EvieBackgroundService.activeActivity = this
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent == null) return
        val fileName = intent.getStringExtra("name") ?: ""
        val url = intent.getStringExtra("url") ?: ""
        val httpUrl = intent.getStringExtra("http_url") ?: ""
        val sizeStr = intent.getStringExtra("size_str") ?: ""
        if (intent.getBooleanExtra("action_analyze_screenshot", false)) {
            intent.removeExtra("action_analyze_screenshot")
            mainHandler.postDelayed({
                checkAndHandleLatestScreenshot(fromCallback = true)
            }, 500L)
        }
        if (fileName.isNotEmpty() && url.isNotEmpty()) {
            val key = "${fileName}_${url.hashCode()}"
            if (!processedDownloads.contains(key)) {
                showFileDownloadPopup(key, url, httpUrl, fileName, sizeStr)
            }
        }
    }

    private fun setupUI() {
        binding.hologramCore.setState(HologramSphereView.CoreState.MUTED)
        binding.tvCoreStatus.text = "◉ MUTED"
        binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_red))
        updateMicButtonUI(false)
        binding.contentCardLayout.visibility = View.GONE
        binding.tvCognitiveStatus?.text = "• OBSERVANDO..."
        binding.tvCognitiveStatus?.setTextColor(ContextCompat.getColor(this, R.color.hud_cyan))
        updateProactivityButtonUI(currentAutonomyMode)

        val pContainer = binding.proceduralCardsContainer
        if (pContainer != null) {
            proceduralRenderer = ProceduralUIRenderer(this, pContainer) { actionId, payload ->
                apiClient.sendUIAction(actionId, payload) { success ->
                    runOnUiThread {
                        appendLog("⚡ [SDUI AÇÃO]: $actionId")
                    }
                }
            }
        }
        binding.btnProceduralClear?.setOnClickListener {
            binding.proceduralScrollView?.visibility = View.GONE
            if (::proceduralRenderer.isInitialized) {
                proceduralRenderer.clearAll()
            }
        }

        binding.geoRadarMapView?.onMarkerSelectedListener = { marker ->
            appendLog("🎯 [RADAR TÁTICO]: Foco em ${marker.label} (${"%.4f".format(marker.lat)}, ${"%.4f".format(marker.lon)})")
            apiClient.sendUIAction(
                "geo_marker_selected",
                mapOf("label" to marker.label, "lat" to marker.lat, "lon" to marker.lon)
            ) {}
        }

        initDefaultProceduralUI()
    }

    private fun setupListeners() {
        binding.btnSend.setOnClickListener {
            val text = binding.etInput.text.toString().trim()
            if (text.isNotEmpty()) {
                sendUserMessage(text)
            }
        }

        binding.etInput.setOnEditorActionListener { _, _, _ ->
            val text = binding.etInput.text.toString().trim()
            if (text.isNotEmpty()) {
                sendUserMessage(text)
                true
            } else false
        }

        binding.btnInterrupt.setOnClickListener {
            triggerInterrupt()
        }

        binding.btnMicToggle.setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED
            ) {
                toggleMic()
            } else {
                recordAudioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            }
        }

        binding.btnSettings.setOnClickListener {
            showSettingsDialog()
        }

        binding.btnReconnect.setOnClickListener {
            Toast.makeText(this, "Reconectando...", Toast.LENGTH_SHORT).show()
            refreshConnection()
            connectEventFeed()
        }

        binding.btnAttach?.setOnClickListener {
            showAttachmentChoiceDialog()
        }

        binding.btnHandoff?.setOnClickListener {
            toggleAudioHandoff()
        }

        binding.btnProactivityMode?.setOnClickListener {
            showProactivityModeDialog()
        }

        binding.btnInsightsFeed?.setOnClickListener {
            showInsightsFeedDialog()
        }

        binding.btnContentDismiss.setOnClickListener {
            binding.contentCardLayout.visibility = View.GONE
        }

        binding.btnRemoteDesktop?.setOnClickListener {
            requestRemoteDesktopConnection()
        }

        binding.btnRemoteClose?.setOnClickListener {
            closeRemoteDesktop()
        }

        binding.btnRemoteMonitorToggle?.setOnClickListener {
            toggleRemoteMonitor()
        }

        binding.btnRemoteKeyboard?.setOnClickListener {
            toggleRemoteKeyboard()
        }

        binding.btnToggleRemoteToolbar?.setOnClickListener {
            val bar = binding.remoteControlBar ?: return@setOnClickListener
            if (bar.visibility == View.VISIBLE) {
                bar.visibility = View.GONE
                binding.btnToggleRemoteToolbar?.alpha = 0.45f
            } else {
                bar.visibility = View.VISIBLE
                binding.btnToggleRemoteToolbar?.alpha = 0.95f
            }
        }

        binding.btnRemoteTouchMode?.setOnClickListener {
            remoteInteractionMode = (remoteInteractionMode + 1) % 3
            when (remoteInteractionMode) {
                0 -> {
                    binding.btnRemoteTouchMode?.text = "📱 TOUCH"
                    Toast.makeText(this, "Modo Touch: 1 dedo rola página, 2 dedos pinça/arrasta zoom", Toast.LENGTH_SHORT).show()
                }
                1 -> {
                    binding.btnRemoteTouchMode?.text = "🖐️ PAN"
                    Toast.makeText(this, "Modo Navegar: 1 dedo arrasta tela ultrawide, toque clica", Toast.LENGTH_SHORT).show()
                }
                2 -> {
                    binding.btnRemoteTouchMode?.text = "🖱️ MOUSE"
                    Toast.makeText(this, "Modo Mouse: 1 dedo move cursor", Toast.LENGTH_SHORT).show()
                }
            }
        }

        binding.btnRemoteZoomReset?.setOnClickListener {
            if (currentZoom > 1.05f) {
                resetZoom()
            } else {
                quickZoom(2.5f)
            }
        }

        setupRemoteDesktopTouchAndKeyboard()
    }

    private fun startClock() {
        mainHandler.post(clockRunnable)
    }

    private fun formatUserEntry(deviceName: String, text: String): String {
        val dev = deviceName.ifBlank { config.deviceName.ifBlank { "Poco X7" } }
        val clean = text.removePrefix("[$dev]:").removePrefix("[$dev] (Texto):").removePrefix("[$dev] (Voz):").trim()
        return "▸ [$dev]:\n  $clean"
    }

    private fun formatEvieEntry(text: String): String {
        val clean = text.removePrefix("Evie:").removePrefix("JARVIS:").trim()
        return "◈ EVIE:\n  $clean"
    }

    private fun formatSystemEntry(text: String): String {
        val clean = text.removePrefix("SYS:").removePrefix("· SYS:").trim()
        return "· SYS: $clean"
    }

    private fun appendLog(line: String, isBlock: Boolean = false) {
        runOnUiThread {
            try {
                val trimmedLine = line.trim()
                if (trimmedLine.isEmpty()) return@runOnUiThread

                // Evita mensagens consecutivas idênticas no terminal
                val currentText = activityLogs.toString().trim()
                if (currentText.endsWith(trimmedLine)) {
                    return@runOnUiThread
                }

                if (activityLogs.isNotEmpty()) {
                    if (isBlock) {
                        activityLogs.append("\n\n")
                    } else {
                        activityLogs.append("\n")
                    }
                }
                activityLogs.append(line)

                // Keep buffer reasonable
                if (activityLogs.length > 8000) {
                    val cut = activityLogs.indexOf("\n", 2500)
                    if (cut != -1) {
                        activityLogs.delete(0, cut + 1)
                    }
                }

                binding.tvActivityLog.text = activityLogs.toString()

                // Scroll internally inside logScrollView so the main screen stays locked
                binding.logScrollView.post {
                    try {
                        binding.logScrollView.fullScroll(View.FOCUS_DOWN)
                    } catch (_: Exception) {}
                }
            } catch (e: Exception) {
                android.util.Log.e("EvieApp", "Error appending log", e)
            }
        }
    }

    private fun triggerInterrupt() {
        appendLog("· SYS: Interrupt command sent.", isBlock = false)
        binding.hologramCore.setState(HologramSphereView.CoreState.MUTED)
        binding.tvCoreStatus.text = "◉ INTERRUPTED"
        binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_red))

        apiClient.sendInterrupt { success, _ ->
            runOnUiThread {
                if (success) {
                    Toast.makeText(this, "Interrompido", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun toggleMic() {
        if (audioManager.isLive()) {
            audioManager.stopStreaming()
            updateMicButtonUI(false)
            binding.hologramCore.setState(HologramSphereView.CoreState.MUTED)
            binding.tvCoreStatus.text = "◉ MUTED"
            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_red))
            appendLog("· SYS: Microphone muted.", isBlock = false)
            Toast.makeText(this, "Microfone mudo", Toast.LENGTH_SHORT).show()
        } else {
            binding.hologramCore.setState(HologramSphereView.CoreState.LISTENING)
            binding.tvCoreStatus.text = "◉ LISTENING"
            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_cyan))
            updateMicButtonUI(true)
            appendLog("· SYS: Microphone active.", isBlock = false)

            audioManager.startStreaming { live, msg ->
                runOnUiThread {
                    if (live) {
                        Toast.makeText(this, "Evie ouvindo...", Toast.LENGTH_SHORT).show()
                    } else {
                        updateMicButtonUI(false)
                        binding.hologramCore.setState(HologramSphereView.CoreState.MUTED)
                        binding.tvCoreStatus.text = "◉ MUTED"
                        binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_red))
                        if (msg.isNotEmpty() && !msg.contains("User stopped")) {
                            appendLog(formatSystemEntry(msg), isBlock = false)
                        }
                    }
                }
            }
        }
    }

    private fun updateMicButtonUI(active: Boolean) {
        if (active) {
            binding.btnMicToggle.text = "🎙  MICROPHONE ACTIVE"
            binding.btnMicToggle.setBackgroundResource(R.drawable.bg_hud_button_mic)
            binding.btnMicToggle.setTextColor(ContextCompat.getColor(this, R.color.hud_green))
        } else {
            binding.btnMicToggle.text = "🔇  MICROPHONE MUTED"
            binding.btnMicToggle.setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            binding.btnMicToggle.setTextColor(ContextCompat.getColor(this, R.color.hud_red))
        }
    }

    private fun sendUserMessage(text: String) {
        try {
            binding.etInput.text.clear()
            val deviceLabel = config.deviceName.ifBlank { "Poco X7" }
            lastSentMessage = text.trim()
            appendLog(formatUserEntry(deviceLabel, text), isBlock = true)

            binding.hologramCore.setState(HologramSphereView.CoreState.LISTENING)
            binding.tvCoreStatus.text = "◉ PROCESSING..."
            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_cyan))

            val svc = EvieBackgroundService.instance
            if (svc != null) {
                svc.sendCommand(text) { success, resultMsg ->
                    runOnUiThread {
                        if (!success) {
                            appendLog("· SYS: Falha ao enviar: $resultMsg", isBlock = false)
                        }
                    }
                }
            } else {
                apiClient.sendCommand(text) { success, resultMsg ->
                    runOnUiThread {
                        try {
                            if (!success) {
                                appendLog("· SYS: Falha ao enviar: $resultMsg", isBlock = false)
                            }
                        } catch (e: Exception) {
                            android.util.Log.e("EvieApp", "Error in sendCommand callback", e)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            android.util.Log.e("EvieApp", "Error in sendUserMessage", e)
            Toast.makeText(this, "Erro ao enviar: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updateStreamingLog(text: String) {
        if (!isEvieStreaming) {
            isEvieStreaming = true
            if (activityLogs.isNotEmpty()) {
                activityLogs.append("\n\n")
            }
            streamingStartIdx = activityLogs.length
            activityLogs.append(text)
        } else {
            if (streamingStartIdx in 0..activityLogs.length) {
                activityLogs.delete(streamingStartIdx, activityLogs.length)
                activityLogs.append(text)
            } else {
                activityLogs.append("\n\n").append(text)
                streamingStartIdx = activityLogs.length - text.length
            }
        }
        binding.tvActivityLog.text = activityLogs.toString()
        binding.logScrollView.post {
            try {
                binding.logScrollView.fullScroll(View.FOCUS_DOWN)
            } catch (_: Exception) {}
        }
    }

    private fun finalizeStreamingLog(finalText: String) {
        if (isEvieStreaming) {
            if (streamingStartIdx in 0..activityLogs.length) {
                activityLogs.delete(streamingStartIdx, activityLogs.length)
                activityLogs.append(finalText)
            }
            isEvieStreaming = false
            streamingStartIdx = -1
            binding.tvActivityLog.text = activityLogs.toString()
            binding.logScrollView.post {
                try {
                    binding.logScrollView.fullScroll(View.FOCUS_DOWN)
                } catch (_: Exception) {}
            }
        } else {
            val trimmedFinal = finalText.trim()
            val curLogs = activityLogs.toString().trim()
            if (!curLogs.endsWith(trimmedFinal)) {
                appendLog(finalText, isBlock = true)
            }
        }
    }

    private fun refreshConnection() {
        apiClient.checkStatus { success, _, devName ->
            runOnUiThread {
                try {
                    isConnected = success
                    if (success) {
                        binding.tvConnectionStatus.text = "ONLINE"
                        binding.tvConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_green))
                        binding.statusDot.setBackgroundColor(ContextCompat.getColor(this, R.color.hud_green))
                        // Fetch initial metrics snapshot immediately
                        apiClient.fetchSysStats { stats ->
                            if (stats != null) {
                                runOnUiThread { applySysMetrics(stats) }
                            }
                        }
                    } else {
                        binding.tvConnectionStatus.text = "OFFLINE"
                        binding.tvConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_red))
                        binding.statusDot.setBackgroundColor(ContextCompat.getColor(this, R.color.hud_red))
                    }
                } catch (e: Exception) {
                    android.util.Log.e("EvieApp", "Error in refreshConnection UI update", e)
                }
            }
        }
    }

    private fun applySysMetrics(json: JsonObject) {
        try {
            val cpu = json.optFloat("cpu", 0f)
            val mem = json.optFloat("mem", 0f)
            val net = json.optString("net", "0KB/s")
            val up = json.optString("uptime", "--:--")
            val proc = json.optInt("proc", 0)
            val os = json.optString("os", "WIN")

            val gpuVal = json.optFloat("gpu", -1f)
            val gpuStrField = json.optString("gpu_str", "")
            val gpuStr = when {
                gpuStrField.isNotEmpty() -> gpuStrField
                gpuVal >= 0f -> "${gpuVal.toInt()}%"
                else -> "N/A"
            }

            binding.tvCpu.text = "${cpu.toInt()}%"
            binding.tvMem.text = "${mem.toInt()}%"
            binding.pbMem.progress = mem.toInt().coerceIn(0, 100)
            binding.tvNet.text = net
            binding.tvGpu.text = gpuStr
            binding.tvUptime.text = "UP $up"
            binding.tvProc.text = "PROC $proc"
            binding.tvOs.text = "OS $os"
        } catch (e: Exception) {
            android.util.Log.e("EvieApp", "Error applying system metrics", e)
        }
    }

    fun onServiceConnected(connected: Boolean) {
        runOnUiThread {
            isConnected = connected
            if (connected) {
                binding.tvConnectionStatus.text = "ONLINE"
                binding.tvConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_green))
                binding.statusDot.setBackgroundColor(ContextCompat.getColor(this, R.color.hud_green))
                apiClient.fetchSysStats { stats ->
                    if (stats != null) {
                        runOnUiThread { applySysMetrics(stats) }
                    }
                }
            } else {
                binding.tvConnectionStatus.text = "RECONNECTING"
                binding.tvConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.hud_yellow))
                binding.statusDot.setBackgroundColor(ContextCompat.getColor(this, R.color.hud_yellow))
            }
        }
    }

    fun handleBackgroundMessage(json: JsonObject) {
        val type = json.optString("type")

        when (type) {
            "response_stream" -> {
                val fullChunk = json.optString("full")
                runOnUiThread {
                    try {
                        binding.hologramCore.setState(HologramSphereView.CoreState.SPEAKING)
                        binding.tvCoreStatus.text = "◉ EVIE RESPONDING"
                        binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))

                        mainHandler.removeCallbacks(resetHologramRunnable)
                        mainHandler.postDelayed(resetHologramRunnable, 4500L)

                        if (fullChunk.isNotEmpty()) {
                            updateStreamingLog(formatEvieEntry(fullChunk))
                            binding.tvEyesSubtitle?.text = "\"${fullChunk.take(130)}\""
                            binding.tvEyesSubtitle?.visibility = View.VISIBLE
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("EvieApp", "Error in response_stream", e)
                    }
                }
            }

            "log" -> {
                val msg = json.optString("text")
                val speaker = json.optString("speaker")
                val device = json.optString("device")

                runOnUiThread {
                    try {
                        if (msg.isNotEmpty()) {
                            val curDev = config.deviceName.ifBlank { "Poco X7" }
                            val trimmedMsg = msg.trim()

                            if (speaker.lowercase() == "user") {
                                // Deduplicate echo of own sent user message
                                val isOwnEcho = lastSentMessage.isNotEmpty() &&
                                    (trimmedMsg == lastSentMessage ||
                                     trimmedMsg == "[$curDev]: $lastSentMessage") &&
                                    (device.isBlank() || device.equals(curDev, ignoreCase = true) || device.equals("Mobile", ignoreCase = true))

                                if (isOwnEcho) {
                                    return@runOnUiThread
                                }

                                val userBlock = formatUserEntry(device, msg)
                                if (isEvieStreaming && streamingStartIdx in 0..activityLogs.length) {
                                    val insertText = userBlock + "\n\n"
                                    activityLogs.insert(streamingStartIdx, insertText)
                                    streamingStartIdx += insertText.length
                                    binding.tvActivityLog.text = activityLogs.toString()
                                    binding.logScrollView.post {
                                        try {
                                            binding.logScrollView.fullScroll(View.FOCUS_DOWN)
                                        } catch (_: Exception) {}
                                    }
                                } else {
                                    appendLog(userBlock, isBlock = true)
                                }
                            } else if (speaker.lowercase() == "jarvis" || speaker.lowercase() == "evie" || msg.startsWith("Evie:") || msg.startsWith("JARVIS:")) {
                                finalizeStreamingLog(formatEvieEntry(msg))

                                binding.hologramCore.setState(HologramSphereView.CoreState.SPEAKING)
                                binding.tvCoreStatus.text = "◉ EVIE RESPONDING"
                                binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))

                                mainHandler.removeCallbacks(resetHologramRunnable)
                                mainHandler.postDelayed(resetHologramRunnable, 4500L)
                            } else if (speaker.lowercase() == "sys" || msg.startsWith("SYS:") || msg.startsWith("· SYS:")) {
                                appendLog(formatSystemEntry(msg), isBlock = false)
                            } else {
                                appendLog(msg, isBlock = false)
                            }
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("EvieApp", "Error rendering log message", e)
                    }
                }
            }

            "content" -> {
                val title = json.optString("title", "CONTENT")
                val contentText = json.optString("text", "")
                val ts = json.optString("ts", "")

                runOnUiThread {
                    try {
                        binding.contentCardLayout.visibility = View.VISIBLE
                        binding.tvContentTitle.text = "◈ $title"
                        binding.tvContentTs.text = ts
                        binding.tvContentBody.text = contentText
                        binding.contentScrollView.post {
                            try {
                                binding.contentScrollView.fullScroll(View.FOCUS_UP)
                            } catch (_: Exception) {}
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("EvieApp", "Error displaying content panel", e)
                    }
                }
            }

            "content_dismiss" -> {
                runOnUiThread {
                    binding.contentCardLayout.visibility = View.GONE
                }
            }

            "sys_metrics" -> {
                runOnUiThread {
                    applySysMetrics(json)
                }
            }

            "status" -> {
                val state = json.optString("state")
                runOnUiThread {
                    try {
                        if (state == "sleeping") {
                            binding.hologramCore.setState(HologramSphereView.CoreState.MUTED)
                            binding.tvCoreStatus.text = "◉ MUTED"
                            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
                        } else if (state == "active") {
                            binding.hologramCore.setState(HologramSphereView.CoreState.IDLE)
                            binding.tvCoreStatus.text = "◉ ONLINE"
                            binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("EvieApp", "Error updating status", e)
                    }
                }
            }

            "proactive_message", "evie_proactive_message" -> {
                val text = json.optString("text")
                val activeWindow = json.optString("active_window")
                val ts = json.optString("timestamp", SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date()))

                runOnUiThread {
                    if (text.isNotBlank()) {
                        val alreadyExists = proactiveInsights.any { it.text.trim() == text.trim() }
                        if (!alreadyExists) {
                            proactiveInsights.add(0, ProactiveInsight(ts, text, activeWindow))
                            binding.btnInsightsFeed?.text = "✨ IDEIAS (${proactiveInsights.size})"
                            appendLog("💡 [INICIATIVA DA EVIE]\n$text", isBlock = true)
                        }

                        binding.hologramCore.setVisualState(VisualState.CURIOUS_SPARK)
                        binding.tvEyesSubtitle?.text = "\"${text.take(130)}\""
                        binding.tvEyesSubtitle?.visibility = View.VISIBLE
                        binding.tvCoreStatus.text = "◉ EVIE PROATIVA"
                        binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))

                        mainHandler.removeCallbacks(resetHologramRunnable)
                        mainHandler.postDelayed(resetHologramRunnable, 5500L)
                    }
                }
            }

            "cognitive_state_changed" -> {
                val state = json.optString("state").lowercase()
                runOnUiThread {
                    when {
                        state.contains("observ") -> {
                            binding.tvCognitiveStatus?.text = "• OBSERVANDO..."
                            binding.tvCognitiveStatus?.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
                            binding.hologramCore.setVisualState(VisualState.IDLE_OBSERVING)
                        }
                        state.contains("think") || state.contains("pens") -> {
                            binding.tvCognitiveStatus?.text = "• PENSANDO EM ALGO..."
                            binding.tvCognitiveStatus?.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))
                            binding.hologramCore.setVisualState(VisualState.THINKING_DEEP)
                        }
                        state.contains("speak") || state.contains("faland") -> {
                            binding.tvCognitiveStatus?.text = "• FALANDO..."
                            binding.tvCognitiveStatus?.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
                            binding.hologramCore.setVisualState(VisualState.SPEAKING)
                        }
                        state.contains("paus") || state.contains("foco") -> {
                            binding.tvCognitiveStatus?.text = "• MODO FOCO ATIVO"
                            binding.tvCognitiveStatus?.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
                            binding.hologramCore.setVisualState(VisualState.FOCUSED)
                        }
                    }
                }
            }

            "proactivity_mode_changed" -> {
                val mode = json.optString("mode").lowercase()
                currentAutonomyMode = mode
                runOnUiThread {
                    updateProactivityButtonUI(mode)
                }
            }

            "file_download" -> {
                val downloadUrl = json.optString("url")
                val httpUrl = json.optString("http_url")
                val fileName = json.optString("name", "arquivo_evie")
                val sizeStr = json.optString("size_str", "")
                val timestamp = json.optDouble("timestamp", 0.0)
                val downloadKey = "${fileName}_${timestamp.toLong()}_${downloadUrl.hashCode()}"

                if (processedDownloads.contains(downloadKey)) {
                    return
                }

                runOnUiThread {
                    showFileDownloadPopup(downloadKey, downloadUrl, httpUrl, fileName, sizeStr)
                }
            }

            "confirm_request" -> {
                val key = json.optString("key")
                val title = json.optString("title", "AÇÃO CRÍTICA REQUER CONFIRMAÇÃO")
                val detail = json.optString("detail", "Deseja autorizar a execução desta ação?")
                val expiresIn = json.optInt("expires_in", 90)
                runOnUiThread {
                    showConfirmGateDialog(key, title, detail, expiresIn)
                }
            }

            "confirm_resolved" -> {
                val key = json.optString("key")
                val result = json.optBoolean("result", false)
                runOnUiThread {
                    if (activeConfirmKey == key) {
                        confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
                        activeConfirmDialog?.dismiss()
                        activeConfirmDialog = null
                        activeConfirmKey = null
                        appendLog("· SYS: Confirmação [$key] ${if (result) "AUTORIZADA" else "RECUSADA"}.", false)
                        if (key == "remote_desktop" && result) {
                            openRemoteDesktop()
                        }
                    }
                }
            }

            "remote_desktop_authorized" -> {
                runOnUiThread {
                    openRemoteDesktop()
                }
            }

            "procedural_ui" -> {
                runOnUiThread {
                    try {
                        val payload = gson.fromJson(json, ProceduralUIPayload::class.java)
                        if (payload != null) {
                            val vState = VisualState.fromString(payload.visualState)
                            binding.hologramCore.setVisualState(vState)
                            when (vState) {
                                VisualState.ALERT_URGENT -> {
                                    binding.tvCoreStatus.text = "◉ ALERTA"
                                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
                                }
                                VisualState.SPEAKING -> {
                                    binding.hologramCore.setAudioLevel(0.85f)
                                    binding.tvCoreStatus.text = "◉ EVIE FALANDO"
                                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
                                }
                                VisualState.THINKING_DEEP -> {
                                    binding.tvCoreStatus.text = "◉ PROCESSANDO"
                                    binding.tvCoreStatus.setTextColor(Color.parseColor("#C084FC"))
                                }
                                VisualState.CURIOUS_SPARK -> {
                                    binding.tvCoreStatus.text = "◉ INSIGHT"
                                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))
                                }
                                VisualState.FOCUS_CALM -> {
                                    binding.tvCoreStatus.text = "◉ MODO FOCO"
                                    binding.tvCoreStatus.setTextColor(Color.parseColor("#38BDF8"))
                                }
                                else -> {
                                    binding.tvCoreStatus.text = "◉ OBSERVANDO"
                                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
                                }
                            }

                            if (!payload.voiceText.isNullOrBlank()) {
                                val vt = payload.voiceText.trim()
                                val alreadyLogged = activityLogs.contains(vt)
                                if (!alreadyLogged) {
                                    appendLog(formatEvieEntry(payload.voiceText))
                                    if (isTtsReady) {
                                        tts?.speak(payload.voiceText, TextToSpeech.QUEUE_FLUSH, null, "sdui_voice")
                                    }
                                }
                                binding.tvEyesSubtitle?.text = "\"${payload.voiceText.take(130)}\""
                                binding.tvEyesSubtitle?.visibility = View.VISIBLE
                            }

                            if (payload.uiTree.isNotEmpty()) {
                                for (comp in payload.uiTree) {
                                    if (comp.getResolvedType() == ComponentType.GEO_MAP_CARD) {
                                        val lat = comp.latitude ?: -23.5505
                                        val lon = comp.longitude ?: -46.6333
                                        binding.geoRadarMapView?.setGeoData(
                                            lat = lat,
                                            lon = lon,
                                            location = comp.locationName,
                                            weather = comp.weatherInfo,
                                            markers = comp.markers
                                        )
                                    }
                                }
                                // Interface SDUI mantida em stand-by conforme solicitado
                                if (::proceduralRenderer.isInitialized) {
                                    proceduralRenderer.renderTree(payload.uiTree)
                                }
                                binding.proceduralScrollView?.post {
                                    try {
                                        binding.proceduralScrollView?.fullScroll(View.FOCUS_UP)
                                    } catch (_: Exception) {}
                                }
                            }
                        }
                    } catch (e: Exception) {
                        android.util.Log.e("EvieApp", "Error rendering procedural_ui", e)
                    }
                }
            }

            "audio", "audio_stream" -> {
                runOnUiThread {
                    binding.hologramCore.setState(HologramSphereView.CoreState.SPEAKING)
                    binding.hologramCore.setAudioLevel(0.85f)
                    binding.tvCoreStatus.text = "◉ EVIE SPEAKING"
                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
                    mainHandler.removeCallbacks(resetHologramRunnable)
                    mainHandler.postDelayed(resetHologramRunnable, 4500L)
                }
            }

            "audio_end" -> {
                runOnUiThread {
                    binding.hologramCore.setAudioLevel(0.0f)
                    binding.hologramCore.setState(HologramSphereView.CoreState.IDLE)
                    binding.tvCoreStatus.text = "◉ ONLINE"
                    binding.tvCoreStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
                }
            }
        }
    }

    private fun connectEventFeed() {
        val svc = EvieBackgroundService.instance
        if (svc != null) {
            svc.connectWebSocket()
        } else {
            apiClient.connectWebSocket(object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    onServiceConnected(true)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    try {
                        val json = gson.fromJson(text, JsonObject::class.java) ?: return
                        handleBackgroundMessage(json)
                    } catch (_: Exception) {}
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    onServiceConnected(false)
                    scheduleReconnect()
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    onServiceConnected(false)
                    scheduleReconnect()
                }
            })
        }
    }

    fun showFileDownloadPopup(
        fileName: String,
        downloadUrl: String,
        httpUrl: String,
        size: Long,
        sizeStr: String
    ) {
        val downloadKey = "${fileName}_${downloadUrl.hashCode()}"
        if (!processedDownloads.contains(downloadKey)) {
            runOnUiThread {
                showFileDownloadPopup(downloadKey, downloadUrl, httpUrl, fileName, sizeStr)
            }
        }
    }

    private fun showFileDownloadPopup(
        downloadKey: String,
        url: String,
        httpUrl: String,
        fileName: String,
        sizeStr: String
    ) {
        if (isDestroyedActivity) return

        if (processedDownloads.contains(downloadKey)) return
        activeDownloadDialog?.dismiss()

        val displaySize = if (sizeStr.isNotBlank()) sizeStr else "N/A"
        val downloadTargetUrl = if (httpUrl.isNotBlank() && config.isHttps) httpUrl else if (url.isNotBlank()) url else httpUrl

        val density = resources.displayMetrics.density
        fun dp(value: Int): Int = (value * density).toInt()

        val rootLayout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(dp(22), dp(20), dp(22), dp(20))
        }

        val tvHeader = android.widget.TextView(this).apply {
            text = "◈ FILE TRANSFER PROTOCOL"
            textSize = 12f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            letterSpacing = 0.08f
            setPadding(0, 0, 0, dp(12))
        }

        val divider = View(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(1)
            ).apply {
                bottomMargin = dp(14)
            }
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.surface_card_border))
        }

        val infoBox = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_panel)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }

        val tvTargetLabel = android.widget.TextView(this).apply {
            text = "PAYLOAD TARGET:"
            textSize = 9.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.NORMAL)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
        }

        val tvFileName = android.widget.TextView(this).apply {
            text = fileName
            textSize = 13.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
            setPadding(0, dp(3), 0, dp(10))
        }

        val tvMeta = android.widget.TextView(this).apply {
            text = "SIZE: $displaySize   |   ORIGIN: PC-HOST"
            textSize = 10f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.NORMAL)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.terminal_text))
            setPadding(0, 0, 0, dp(3))
        }

        val tvDest = android.widget.TextView(this).apply {
            text = "DEST: /storage/emulated/0/Download/"
            textSize = 8.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.NORMAL)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
        }

        infoBox.addView(tvTargetLabel)
        infoBox.addView(tvFileName)
        infoBox.addView(tvMeta)
        infoBox.addView(tvDest)

        val tvStatus = android.widget.TextView(this).apply {
            text = "STATUS: INCOMING PAYLOAD READY"
            textSize = 10f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
            letterSpacing = 0.05f
            setPadding(0, dp(14), 0, dp(10))
        }

        val progressBar = android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true
            visibility = View.GONE
            setPadding(0, dp(2), 0, dp(10))
            progressTintList = android.content.res.ColorStateList.valueOf(
                ContextCompat.getColor(this@MainActivity, R.color.primary_accent)
            )
            indeterminateTintList = android.content.res.ColorStateList.valueOf(
                ContextCompat.getColor(this@MainActivity, R.color.primary_accent)
            )
        }

        val buttonsRow = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            setPadding(0, dp(6), 0, 0)
        }

        val btnCancel = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1f).apply {
                marginEnd = dp(8)
            }
            setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            text = "[ CANCEL ]"
            textSize = 11f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
            insetTop = 0
            insetBottom = 0
            minHeight = 0
        }

        val btnDownload = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1.3f)
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            text = "[ DOWNLOAD ]"
            textSize = 11f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            insetTop = 0
            insetBottom = 0
            minHeight = 0
        }

        val btnOpenFolder = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1f)
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            text = "[ VER NA PASTA ]"
            textSize = 10.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            insetTop = 0
            insetBottom = 0
            minHeight = 0
            visibility = View.GONE
        }

        buttonsRow.addView(btnCancel)
        buttonsRow.addView(btnDownload)
        buttonsRow.addView(btnOpenFolder)

        val dismissRow = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            setPadding(0, dp(6), 0, 0)
            visibility = View.GONE
        }

        val btnDismiss = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(34)
            )
            setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            text = "[ DISMISS ]"
            textSize = 10.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
            insetTop = 0
            insetBottom = 0
            minHeight = 0
        }

        dismissRow.addView(btnDismiss)

        rootLayout.addView(tvHeader)
        rootLayout.addView(divider)
        rootLayout.addView(infoBox)
        rootLayout.addView(tvStatus)
        rootLayout.addView(progressBar)
        rootLayout.addView(buttonsRow)
        rootLayout.addView(dismissRow)

        val dialog = AlertDialog.Builder(this)
            .setView(rootLayout)
            .setCancelable(false)
            .create()

        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        activeDownloadDialog = dialog

        btnCancel.setOnClickListener {
            processedDownloads.add(downloadKey)
            dialog.dismiss()
            activeDownloadDialog = null
            appendLog("· SYS: Transfer cancelled by user: $fileName", isBlock = false)
        }

        btnDismiss.setOnClickListener {
            dialog.dismiss()
            activeDownloadDialog = null
        }

        btnDownload.setOnClickListener {
            processedDownloads.add(downloadKey)

            btnDownload.isEnabled = false
            btnCancel.visibility = View.GONE
            btnOpenFolder.visibility = View.GONE
            dismissRow.visibility = View.GONE
            tvStatus.text = "STATUS: STREAMING PAYLOAD..."
            tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            progressBar.visibility = View.VISIBLE

            appendLog("· SYS: Transferring payload: $fileName ($displaySize)", isBlock = false)
            Toast.makeText(this@MainActivity, "Recebendo: $fileName", Toast.LENGTH_SHORT).show()

            lifecycleScope.launch(Dispatchers.IO) {
                var downloadedUri: Uri? = null
                var downloadedFile: File? = null
                var errorMsg: String? = null

                try {
                    val urlsToTry = listOf(downloadTargetUrl, url, httpUrl).filter { it.isNotBlank() }.distinct()
                    var response: okhttp3.Response? = null

                    for (candidateUrl in urlsToTry) {
                        try {
                            val urlWithToken = if (!candidateUrl.contains("token=") && config.authToken.isNotBlank()) {
                                val sep = if (candidateUrl.contains("?")) "&" else "?"
                                "$candidateUrl${sep}token=${config.authToken}"
                            } else candidateUrl

                            val req = okhttp3.Request.Builder()
                                .url(urlWithToken)
                                .header("Authorization", "Bearer ${config.authToken}")
                                .get()
                                .build()
                            val resp = apiClient.client.newCall(req).execute()
                            if (resp.isSuccessful && resp.body != null) {
                                response = resp
                                break
                            }
                        } catch (_: Exception) {}
                    }

                    if (response == null || response.body == null) {
                        throw Exception("Host connection timeout")
                    }

                    val body = response.body!!
                    val inputStream = body.byteStream()

                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        val contentValues = ContentValues().apply {
                            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                            put(MediaStore.MediaColumns.MIME_TYPE, getMimeType(fileName))
                            put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                            put(MediaStore.MediaColumns.IS_PENDING, 1)
                        }
                        val contentUri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, contentValues)
                        if (contentUri != null) {
                            contentResolver.openOutputStream(contentUri)?.use { out ->
                                inputStream.copyTo(out)
                            }
                            contentValues.clear()
                            contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
                            contentResolver.update(contentUri, contentValues, null, null)
                            downloadedUri = contentUri
                        }
                    } else {
                        val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                        if (!dir.exists()) dir.mkdirs()
                        val target = File(dir, fileName)
                        FileOutputStream(target).use { out ->
                            inputStream.copyTo(out)
                        }
                        downloadedFile = target
                        MediaScannerConnection.scanFile(this@MainActivity, arrayOf(target.absolutePath), null, null)
                    }

                } catch (e: Exception) {
                    errorMsg = e.localizedMessage ?: "Network error"
                    android.util.Log.e("EvieApp", "Error in payload transfer", e)
                }

                withContext(Dispatchers.Main) {
                    progressBar.visibility = View.GONE
                    if (downloadedUri != null || downloadedFile != null) {
                        tvStatus.text = "STATUS: TRANSFER COMPLETE [SAVED]"
                        tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
                        appendLog("· SYS: Arquivo salvo em Downloads: $fileName", isBlock = false)
                        Toast.makeText(this@MainActivity, "Salvo: $fileName", Toast.LENGTH_SHORT).show()

                        btnDownload.isEnabled = true
                        btnDownload.visibility = View.VISIBLE
                        btnDownload.layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1f).apply {
                            marginEnd = dp(8)
                        }
                        btnDownload.setBackgroundResource(R.drawable.bg_hud_button_mic)
                        btnDownload.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
                        btnDownload.text = "[ OPEN FILE ]"
                        btnDownload.setOnClickListener {
                            openDownloadedFile(downloadedUri, downloadedFile, fileName)
                            dialog.dismiss()
                            activeDownloadDialog = null
                        }

                        btnOpenFolder.visibility = View.VISIBLE
                        btnOpenFolder.layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1f)
                        btnOpenFolder.setOnClickListener {
                            openDownloadsFolder()
                            dialog.dismiss()
                            activeDownloadDialog = null
                        }

                        btnCancel.visibility = View.GONE
                        dismissRow.visibility = View.VISIBLE
                    } else {
                        tvStatus.text = "STATUS: TRANSFER FAILED [${errorMsg ?: "ERROR"}]"
                        tvStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
                        appendLog("· SYS: Erro na transferência de $fileName: $errorMsg", isBlock = false)
                        btnDownload.isEnabled = true
                        btnDownload.text = "[ RETRY ]"
                        btnDownload.layoutParams = android.widget.LinearLayout.LayoutParams(0, dp(36), 1.3f)
                        btnCancel.visibility = View.VISIBLE
                        btnOpenFolder.visibility = View.GONE
                        dismissRow.visibility = View.GONE
                    }
                }
            }
        }

        dialog.show()
    }

    private fun openDownloadsFolder() {
        // Opção 1: Intent padrão da pasta de Downloads do Android com seletor (Chooser)
        try {
            val intent = Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            val chooser = Intent.createChooser(intent, "Escolha o explorador de arquivos").apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(chooser)
            return
        } catch (_: Exception) {}

        // Opção 2: DocumentsContract Downloads Provider com seletor
        try {
            val downloadUri = Uri.parse("content://com.android.externalstorage.documents/document/primary%3ADownload")
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(downloadUri, DocumentsContract.Document.MIME_TYPE_DIR)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            val chooser = Intent.createChooser(intent, "Escolha o explorador de arquivos").apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(chooser)
            return
        } catch (_: Exception) {}

        // Opção 3: Diretório público de Downloads ou MediaStore com seletor
        try {
            val uri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Downloads.EXTERNAL_CONTENT_URI
            } else {
                val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                Uri.fromFile(dir)
            }
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "*/*")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            val chooser = Intent.createChooser(intent, "Escolha o explorador de arquivos").apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(chooser)
            return
        } catch (_: Exception) {}

        Toast.makeText(this, "Nenhum explorador de arquivos encontrado", Toast.LENGTH_SHORT).show()
    }

    private fun openDownloadedFile(uri: Uri?, file: File?, fileName: String) {
        try {
            val targetUri = uri ?: if (file != null) Uri.fromFile(file) else null ?: return
            val mime = getMimeType(fileName)
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(targetUri, mime)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)
        } catch (_: Exception) {
            Toast.makeText(this, "Nenhum visualizador compatível encontrado", Toast.LENGTH_SHORT).show()
        }
    }

    private fun getMimeType(fileName: String): String {
        val ext = fileName.substringAfterLast('.', "").lowercase()
        return MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "*/*"
    }



    private fun scheduleReconnect() {
        if (isDestroyedActivity) return
        mainHandler.postDelayed({
            if (!isDestroyedActivity && !isConnected) {
                connectEventFeed()
            }
        }, 3000L)
    }

    private fun showSettingsDialog() {
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 20, 50, 10)
        }

        val hostLabel = android.widget.TextView(this).apply {
            text = "Endereço do Servidor / Host (Tailscale):"
            textSize = 12f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
        }
        val hostInput = EditText(this).apply {
            hint = "Host IP:Porta (ex: 100.73.5.37:8000)"
            setText(config.serverHost)
            textSize = 13f
        }

        val devLabel = android.widget.TextView(this).apply {
            text = "Nome do Dispositivo no Log:"
            textSize = 12f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            setPadding(0, 25, 0, 0)
        }
        val devInput = EditText(this).apply {
            hint = "Ex: Poco X7, Rafael Mobile"
            setText(config.deviceName)
            textSize = 13f
        }

        layout.addView(hostLabel)
        layout.addView(hostInput)
        layout.addView(devLabel)
        layout.addView(devInput)

        AlertDialog.Builder(this)
            .setTitle("Configurações do Nó")
            .setView(layout)
            .setPositiveButton("Salvar") { _, _ ->
                val newHost = hostInput.text.toString().trim()
                val newDev = devInput.text.toString().trim()
                if (newHost.isNotEmpty()) config.serverHost = newHost
                if (newDev.isNotEmpty()) config.deviceName = newDev
                refreshConnection()
                connectEventFeed()
                Toast.makeText(this, "Salvo: $newDev ($newHost)", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun checkCameraAndOpen() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            takePictureLauncher.launch(null)
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun sendCapturedVision(
        bitmap: android.graphics.Bitmap,
        prompt: String = "Análise visual do ambiente capturada pelo Poco X7."
    ) {
        val stream = java.io.ByteArrayOutputStream()
        bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 85, stream)
        val byteArray = stream.toByteArray()
        val base64 = android.util.Base64.encodeToString(byteArray, android.util.Base64.NO_WRAP)

        appendLog("· SYS: Transmitindo imagem para a Evie...", false)
        apiClient.sendVisionImage(base64, "image/jpeg", prompt) { success, msg ->
            runOnUiThread {
                if (success) {
                    Toast.makeText(this@MainActivity, "Frame de visão enviado!", Toast.LENGTH_SHORT).show()
                    appendLog("· SYS: Frame visual processado pela Evie.", false)
                } else {
                    appendLog("· SYS: Falha ao enviar frame visual: $msg", false)
                }
            }
        }
    }

    private fun initTextToSpeech() {
        try {
            tts = TextToSpeech(this) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    val result = tts?.setLanguage(Locale("pt", "BR"))
                    isTtsReady = (result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED)
                }
            }
        } catch (e: Exception) {
            android.util.Log.e("EvieApp", "Error initializing TTS", e)
        }
    }

    private fun speakEvieVoice(text: String) {
        try {
            if (isTtsReady && tts != null) {
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "evie_voice_prompt")
            }
        } catch (e: Exception) {
            android.util.Log.e("EvieApp", "Error speaking via TTS", e)
        }
    }

    private fun showAttachmentChoiceDialog() {
        if (isDestroyedActivity) return

        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(dp(22), dp(20), dp(22), dp(20))
        }

        val tvTitle = android.widget.TextView(this).apply {
            text = "◈ ANEXAR ARQUIVO AO SISTEMA"
            textSize = 12f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            letterSpacing = 0.08f
            setPadding(0, 0, 0, dp(4))
        }

        val tvSub = android.widget.TextView(this).apply {
            text = "SELECIONE O TIPO DE CARGA PARA ENVIO"
            textSize = 9.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.NORMAL)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
            setPadding(0, 0, 0, dp(12))
        }

        val divider = View(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(1)
            ).apply { bottomMargin = dp(14) }
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.surface_card_border))
        }

        root.addView(tvTitle)
        root.addView(tvSub)
        root.addView(divider)

        val btnCamera = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(40)
            ).apply { bottomMargin = dp(10) }
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            text = "Câmera"
            isAllCaps = false
            textSize = 11.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        val btnGallery = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(40)
            ).apply { bottomMargin = dp(10) }
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            text = "Fotos"
            isAllCaps = false
            textSize = 11.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        val btnDocument = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(40)
            ).apply { bottomMargin = dp(14) }
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            text = "Documentos"
            isAllCaps = false
            textSize = 11.5f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        val btnCancel = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(36)
            )
            setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            text = "[ CANCELAR ]"
            textSize = 11f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        root.addView(btnCamera)
        root.addView(btnGallery)
        root.addView(btnDocument)
        root.addView(btnCancel)

        val dialog = AlertDialog.Builder(this)
            .setView(root)
            .create()

        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)

        btnCamera.setOnClickListener {
            dialog.dismiss()
            checkCameraAndOpen()
        }

        btnGallery.setOnClickListener {
            dialog.dismiss()
            pickImageLauncher.launch("image/*")
        }

        btnDocument.setOnClickListener {
            dialog.dismiss()
            pickDocumentLauncher.launch("*/*")
        }

        btnCancel.setOnClickListener {
            dialog.dismiss()
        }

        dialog.show()
    }

    private fun handleGalleryImageSelected(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val bitmap = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    ImageDecoder.decodeBitmap(ImageDecoder.createSource(contentResolver, uri)) { decoder, _, _ ->
                        decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                    }
                } else {
                    @Suppress("DEPRECATION")
                    MediaStore.Images.Media.getBitmap(contentResolver, uri)
                }

                if (bitmap != null) {
                    withContext(Dispatchers.Main) {
                        showSendImageDialog(bitmap, "Foto da Galeria")
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Não foi possível carregar a imagem.", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Erro ao abrir imagem: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showSendImageDialog(bitmap: Bitmap, title: String) {
        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(dp(20), dp(18), dp(20), dp(18))
        }

        val tvTitle = android.widget.TextView(this).apply {
            text = "◈ ENVIAR IMAGEM: $title"
            textSize = 13f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
        }
        root.addView(tvTitle)

        val preview = android.widget.ImageView(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(160)
            ).apply { topMargin = dp(10); bottomMargin = dp(10) }
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            setImageBitmap(bitmap)
        }
        root.addView(preview)

        val etPrompt = EditText(this).apply {
            hint = "Instrução (ex: analise este gráfico, resuma...)"
            setText("Analise esta imagem em detalhes.")
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
            setHintTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
            setBackgroundResource(R.drawable.bg_hud_input)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            textSize = 12f
            setTypeface(android.graphics.Typeface.MONOSPACE)
        }
        root.addView(etPrompt)

        val btnSend = android.widget.Button(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
            ).apply { topMargin = dp(12) }
            text = "ENVIAR PARA EVIE"
            setBackgroundResource(R.drawable.bg_hud_button_mic)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            textSize = 12f
        }
        root.addView(btnSend)

        val dialog = AlertDialog.Builder(this)
            .setView(root)
            .create()

        btnSend.setOnClickListener {
            val userPrompt = etPrompt.text.toString().trim().ifBlank { "Analise esta imagem em detalhes." }
            dialog.dismiss()
            sendCapturedVision(bitmap, userPrompt)
        }

        dialog.show()
    }

    private fun handleDocumentSelected(uri: Uri) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                var fileName = "documento"
                contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    val nameIdx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (nameIdx != -1 && cursor.moveToFirst()) {
                        fileName = cursor.getString(nameIdx) ?: "documento"
                    }
                }
                val mimeType = contentResolver.getType(uri) ?: "application/octet-stream"
                val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }

                if (bytes != null && bytes.isNotEmpty()) {
                    withContext(Dispatchers.Main) {
                        appendLog("· SYS: Enviando arquivo '$fileName' (${bytes.size / 1024} KB)...", false)
                        Toast.makeText(this@MainActivity, "Enviando $fileName...", Toast.LENGTH_SHORT).show()
                    }

                    apiClient.uploadFile(bytes, fileName, mimeType) { success, msg ->
                        runOnUiThread {
                            if (success) {
                                appendLog("· SYS: Arquivo '$fileName' enviado com sucesso.", false)
                                Toast.makeText(this@MainActivity, "Arquivo '$fileName' enviado!", Toast.LENGTH_SHORT).show()
                                apiClient.sendCommand("Enviei o arquivo $fileName para seu diretório de uploads.") { _, _ -> }
                            } else {
                                appendLog("· SYS: Falha ao enviar arquivo '$fileName': $msg", false)
                                Toast.makeText(this@MainActivity, "Erro ao enviar: $msg", Toast.LENGTH_LONG).show()
                            }
                        }
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Arquivo vazio ou inacessível.", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Erro ao ler arquivo: ${e.localizedMessage}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun setupScreenshotDetection() {
        try {
            screenshotObserver?.let {
                try { contentResolver.unregisterContentObserver(it) } catch (_: Exception) {}
            }
            screenshotObserver = object : ContentObserver(mainHandler) {
                override fun onChange(selfChange: Boolean, uri: Uri?) {
                    super.onChange(selfChange, uri)
                    checkAndHandleLatestScreenshot(fromCallback = false)
                }
            }
            contentResolver.registerContentObserver(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                true,
                screenshotObserver!!
            )
        } catch (e: Exception) {
            android.util.Log.w("EvieApp", "Could not register screenshot ContentObserver", e)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            try {
                screenCaptureCallback?.let {
                    try { (it as? Activity.ScreenCaptureCallback)?.let { cb -> unregisterScreenCaptureCallback(cb) } } catch (_: Exception) {}
                }
                val callback = Activity.ScreenCaptureCallback {
                    runOnUiThread {
                        checkAndHandleLatestScreenshot(fromCallback = true)
                    }
                }
                registerScreenCaptureCallback(mainExecutor, callback)
                screenCaptureCallback = callback
            } catch (e: Exception) {
                android.util.Log.w("EvieApp", "Could not register ScreenCaptureCallback", e)
            }
        }
    }

    fun checkAndHandleLatestScreenshot(fromCallback: Boolean = false) {
        val now = System.currentTimeMillis()
        if (now - lastScreenshotTimestamp < 3000) return
        lastScreenshotTimestamp = now

        lifecycleScope.launch(Dispatchers.IO) {
            // Short delay for filesystem flush on screenshot save
            kotlinx.coroutines.delay(700)

            val projection = arrayOf(
                MediaStore.Images.Media._ID,
                MediaStore.Images.Media.DISPLAY_NAME,
                MediaStore.Images.Media.DATE_ADDED
            )
            val sortOrder = "${MediaStore.Images.Media.DATE_ADDED} DESC"

            var targetUri: Uri? = null
            var targetName = "screenshot.jpg"

            try {
                contentResolver.query(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    projection,
                    null,
                    null,
                    sortOrder
                )?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val idCol = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                        val nameCol = cursor.getColumnIndex(MediaStore.Images.Media.DISPLAY_NAME)
                        val dateCol = cursor.getColumnIndex(MediaStore.Images.Media.DATE_ADDED)

                        val id = cursor.getLong(idCol)
                        val name = if (nameCol != -1) cursor.getString(nameCol) ?: "" else ""
                        val dateAdded = if (dateCol != -1) cursor.getLong(dateCol) else 0L

                        val ageSec = (System.currentTimeMillis() / 1000) - dateAdded
                        val isScreenshotMatch = name.contains("screenshot", ignoreCase = true) ||
                                name.contains("screen", ignoreCase = true) ||
                                name.contains("captura", ignoreCase = true) ||
                                name.contains("print", ignoreCase = true)

                        if (fromCallback || (isScreenshotMatch && ageSec < 35) || ageSec < 15) {
                            targetUri = Uri.withAppendedPath(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id.toString())
                            targetName = name.ifBlank { "screenshot.jpg" }
                        }
                    }
                }
            } catch (e: Exception) {
                android.util.Log.e("EvieApp", "Error querying screenshot MediaStore", e)
            }

            if (targetUri != null) {
                val bitmap = try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                        ImageDecoder.decodeBitmap(ImageDecoder.createSource(contentResolver, targetUri!!)) { decoder, _, _ ->
                            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                        }
                    } else {
                        @Suppress("DEPRECATION")
                        MediaStore.Images.Media.getBitmap(contentResolver, targetUri!!)
                    }
                } catch (e: Exception) {
                    null
                }

                if (bitmap != null) {
                    withContext(Dispatchers.Main) {
                        showScreenshotAnalysisPopup(bitmap, targetName)
                    }
                }
            }
        }
    }

    private fun showScreenshotAnalysisPopup(bitmap: Bitmap, name: String) {
        if (isDestroyedActivity) return

        activeScreenshotDialog?.dismiss()
        activeScreenshotDialog = null

        speakEvieVoice("Detectei uma captura de tela. Gostaria que eu analisasse a imagem?")
        appendLog("· SYS: Captura de tela detectada: $name", false)

        val density = resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(dp(22), dp(20), dp(22), dp(20))
        }

        val tvHeader = android.widget.TextView(this).apply {
            text = "📸 CAPTURA DE TELA DETECTADA"
            textSize = 13f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
        }
        root.addView(tvHeader)

        val tvMsg = android.widget.TextView(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                android.widget.LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(8); bottomMargin = dp(10) }
            text = "◈ EVIE: Detectei uma nova captura de tela. Deseja que eu analise o conteúdo visual agora?"
            textSize = 12f
            setTypeface(android.graphics.Typeface.MONOSPACE)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
        }
        root.addView(tvMsg)

        val preview = android.widget.ImageView(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(160)
            ).apply { bottomMargin = dp(14) }
            scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            setImageBitmap(bitmap)
        }
        root.addView(preview)

        val btnLayout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            weightSum = 2f
        }

        val btnDismiss = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                0,
                dp(36),
                1f
            ).apply { marginEnd = dp(6) }
            text = "✕ DESCARTAR"
            setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            textSize = 11f
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        val btnAnalyze = com.google.android.material.button.MaterialButton(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                0,
                dp(36),
                1f
            ).apply { marginStart = dp(6) }
            text = "✓ ANALISAR"
            setBackgroundResource(R.drawable.bg_hud_button_mic)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            textSize = 11f
            insetTop = 0; insetBottom = 0; minHeight = 0
        }

        btnLayout.addView(btnDismiss)
        btnLayout.addView(btnAnalyze)
        root.addView(btnLayout)

        val dialog = AlertDialog.Builder(this)
            .setView(root)
            .setCancelable(true)
            .create()

        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)

        btnDismiss.setOnClickListener {
            tts?.stop()
            dialog.dismiss()
        }

        btnAnalyze.setOnClickListener {
            tts?.stop()
            dialog.dismiss()
            appendLog("· SYS: Enviando captura de tela para análise multimodal da Evie...", false)
            sendCapturedVision(bitmap, "Analise detalhadamente esta captura de tela, identifique elementos e responda com clareza.")
        }

        dialog.setOnDismissListener {
            tts?.stop()
            if (activeScreenshotDialog == dialog) {
                activeScreenshotDialog = null
            }
        }

        activeScreenshotDialog = dialog
        dialog.show()
    }

    private fun toggleAudioHandoff() {
        val target = if (isMobileAudioActive) "pc" else "mobile"
        appendLog("· SYS: Solicitando handoff de voz para: ${target.uppercase()}...", false)
        apiClient.requestSessionHandoff(target) { success, msg ->
            runOnUiThread {
                if (success) {
                    isMobileAudioActive = (target == "mobile")
                    val label = if (isMobileAudioActive) "Áudio transferido para o Celular" else "Áudio transferido para o PC"
                    Toast.makeText(this@MainActivity, label, Toast.LENGTH_SHORT).show()
                    appendLog("· SYS: $label", false)
                } else {
                    Toast.makeText(this@MainActivity, "Erro no handoff: $msg", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun updateProactivityButtonUI(mode: String) {
        val m = mode.lowercase()
        when {
            m.contains("silent") || m.contains("silêncio") -> {
                binding.btnProactivityMode?.text = "💡 AUTO: 0%"
                binding.btnProactivityMode?.setTextColor(ContextCompat.getColor(this, R.color.text_dim))
            }
            m.contains("curious") || m.contains("curiosa") -> {
                binding.btnProactivityMode?.text = "💡 AUTO: 100%"
                binding.btnProactivityMode?.setTextColor(ContextCompat.getColor(this, R.color.hud_green))
            }
            else -> {
                binding.btnProactivityMode?.text = "💡 AUTO: 50%"
                binding.btnProactivityMode?.setTextColor(ContextCompat.getColor(this, R.color.hud_yellow))
            }
        }
    }

    private fun showProactivityModeDialog() {
        val modes = arrayOf(
            "Silenciosa (0%) - Apenas responde quando chamada",
            "Equilibrada (50%) - Sugestões e perguntas oportunas",
            "Super Curiosa (100%) - Brainstorming constante e proativo"
        )
        val modeKeys = arrayOf("silent", "balanced", "curious")
        val currentIdx = when (currentAutonomyMode.lowercase()) {
            "silent" -> 0
            "curious" -> 2
            else -> 1
        }

        AlertDialog.Builder(this)
            .setTitle("MODO DE AUTONOMIA DA EVIE")
            .setSingleChoiceItems(modes, currentIdx) { dialog, which ->
                val chosenMode = modeKeys[which]
                currentAutonomyMode = chosenMode
                updateProactivityButtonUI(chosenMode)
                apiClient.setProactivityMode(chosenMode) { ok, resp ->
                    runOnUiThread {
                        if (ok) {
                            Toast.makeText(this, "Modo atualizado: ${chosenMode.uppercase()}", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(this, "Falha ao sincronizar: $resp", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                dialog.dismiss()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun showInsightsFeedDialog() {
        if (proactiveInsights.isEmpty()) {
            Toast.makeText(this, "Nenhuma iniciativa registrada hoje ainda.", Toast.LENGTH_SHORT).show()
            return
        }

        val dialogView = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(40, 36, 40, 36)
        }

        // Header do Popup com Estética Sci-Fi
        val headerLayout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, 24)
        }

        val titleTv = android.widget.TextView(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(0, android.widget.LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f)
            text = "✨ FEED DE IDEIAS DA EVIE (${proactiveInsights.size})"
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            textSize = 14.5f
            typeface = android.graphics.Typeface.MONOSPACE
            paint.isFakeBoldText = true
        }
        headerLayout.addView(titleTv)
        dialogView.addView(headerLayout)

        // Subtítulo descritivo
        val subTv = android.widget.TextView(this).apply {
            text = "Toque em uma ideia para responder ou conversar com a Evie:"
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
            textSize = 11.5f
            setPadding(0, 0, 0, 18)
        }
        dialogView.addView(subTv)

        // Lista rolável de Cards de Ideias
        val scrollView = android.widget.ScrollView(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                (resources.displayMetrics.density * 320).toInt()
            )
            isVerticalScrollBarEnabled = true
        }

        val listContainer = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
        }

        var dialogInstance: android.app.Dialog? = null

        proactiveInsights.forEachIndexed { idx, insight ->
            val card = android.widget.LinearLayout(this).apply {
                orientation = android.widget.LinearLayout.VERTICAL
                setBackgroundResource(R.drawable.bg_hud_panel)
                setPadding(26, 20, 26, 20)
                val lp = android.widget.LinearLayout.LayoutParams(
                    android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT
                )
                lp.bottomMargin = 14
                layoutParams = lp
                isClickable = true
                isFocusable = true
            }

            // Cabeçalho do Card: Horário limpo e Janela/Contexto
            val cardHeader = android.widget.LinearLayout(this).apply {
                orientation = android.widget.LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
            }

            // Limpa timestamp se vier em epoch/float (ex: [1792058430.0888019] -> 10:07)
            val cleanTime = try {
                val raw = insight.timestamp.trim().removeSurrounding("[", "]")
                val floatVal = raw.toDoubleOrNull()
                if (floatVal != null && floatVal > 1000000) {
                    SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(floatVal.toLong() * 1000L))
                } else if (raw.length >= 8 && raw.contains(":")) {
                    raw.take(8)
                } else {
                    raw
                }
            } catch (_: Exception) {
                insight.timestamp
            }

            val timeBadge = android.widget.TextView(this).apply {
                text = "🕒 $cleanTime"
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_cyan))
                textSize = 10.5f
                typeface = android.graphics.Typeface.MONOSPACE
            }
            cardHeader.addView(timeBadge)

            if (!insight.window.isNullOrBlank()) {
                val windowBadge = android.widget.TextView(this).apply {
                    layoutParams = android.widget.LinearLayout.LayoutParams(
                        android.widget.LinearLayout.LayoutParams.WRAP_CONTENT,
                        android.widget.LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply { leftMargin = 16 }
                    text = "• ${insight.window.take(24)}"
                    setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))
                    textSize = 10f
                    maxLines = 1
                    ellipsize = android.text.TextUtils.TruncateAt.END
                }
                cardHeader.addView(windowBadge)
            }
            card.addView(cardHeader)

            // Texto da iniciativa
            val textTv = android.widget.TextView(this).apply {
                text = insight.text
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
                textSize = 13f
                setLineSpacing(3f, 1.15f)
                setPadding(0, 10, 0, 4)
            }
            card.addView(textTv)

            card.setOnClickListener {
                dialogInstance?.dismiss()
                binding.etInput.setText("Sobre o que você disse: \"${insight.text}\"")
                binding.etInput.setSelection(binding.etInput.text.length)
                binding.etInput.requestFocus()
            }

            listContainer.addView(card)
        }

        scrollView.addView(listContainer)
        dialogView.addView(scrollView)

        // Botão Fechar Futurista
        val footerLayout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.END
            setPadding(0, 20, 0, 0)
        }

        val btnClose = android.widget.Button(this).apply {
            text = "FECHAR"
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.primary_accent))
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            textSize = 12f
            typeface = android.graphics.Typeface.MONOSPACE
            setPadding(30, 8, 30, 8)
            setOnClickListener {
                dialogInstance?.dismiss()
            }
        }
        footerLayout.addView(btnClose)
        dialogView.addView(footerLayout)

        dialogInstance = android.app.Dialog(this).apply {
            requestWindowFeature(android.view.Window.FEATURE_NO_TITLE)
            setContentView(dialogView)
            window?.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(android.graphics.Color.TRANSPARENT))
            show()
        }
    }

    private val telemetryRunnable = object : Runnable {
        override fun run() {
            if (!isDestroyedActivity) {
                sendMobileTelemetry()
                mainHandler.postDelayed(this, 60000L)
            }
        }
    }

    private fun sendMobileTelemetry() {
        try {
            val bm = getSystemService(Context.BATTERY_SERVICE) as? android.os.BatteryManager
            val batteryPct = bm?.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
            val isCharging = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                bm?.isCharging == true
            } else false

            val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager
            val screenOn = pm?.isInteractive == true

            apiClient.sendMobileTelemetry(
                battery = if (batteryPct >= 0) batteryPct else null,
                screenOn = screenOn,
                screenName = "MainChatHUD"
            ) { _ -> }
            syncLocationToPc()
        } catch (_: Exception) {}
    }

    private fun initDefaultProceduralUI() {
        if (!::proceduralRenderer.isInitialized) return
        val defaultMetrics = UIComponent(
            id = "sys_metrics_init",
            type = ComponentType.METRIC_CARD.raw,
            title = "TELEMETRIA DO DISPOSITIVO // POCO X7",
            metrics = listOf(
                MetricItem(label = "LINK", value = "ONLINE", color = "#00e676"),
                MetricItem(label = "RADAR", value = "60 FPS", color = "#00f0ff"),
                MetricItem(label = "SAT", value = "14 SATS", color = "#38bdf8"),
                MetricItem(label = "MODO", value = "TÁTICO", color = "#ffaa00")
            )
        )
        val defaultChecklist = UIComponent(
            id = "checklist_init",
            type = ComponentType.INTERACTIVE_CHECKLIST.raw,
            title = "DIRETRIZES ATIVAS // EVIE",
            checklistItems = listOf(
                ChecklistItem("chk_1", "Radar tático e malha espacial em 60 FPS", true),
                ChecklistItem("chk_2", "Sincronização bidirecional PC <-> Mobile", true),
                ChecklistItem("chk_3", "Monitoramento autônomo e proativo ativo", true)
            )
        )
        val defaultAction = UIComponent(
            id = "action_init",
            type = ComponentType.ACTION_DECISION_CARD.raw,
            title = "AÇÕES RÁPIDAS HUD",
            body = "Comandos táticos rápidos de telemetria e rede.",
            actions = listOf(
                ActionItem("radar_ping", "📡 Varredura Radar", "primary"),
                ActionItem("sync_location", "📍 Sincronizar GPS", "success")
            )
        )
        proceduralRenderer.renderTree(listOf(defaultMetrics, defaultChecklist, defaultAction))
    }

    private fun syncLocationToPc() {
        try {
            var lat = -23.546100
            var lon = -46.628900
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
            ) {
                val locMgr = getSystemService(Context.LOCATION_SERVICE) as? android.location.LocationManager
                val lastLoc = locMgr?.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
                    ?: locMgr?.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)
                if (lastLoc != null) {
                    lat = lastLoc.latitude
                    lon = lastLoc.longitude
                }
            }
            binding.geoRadarMapView?.updateMobileLocation(lat, lon)
            apiClient.sendGeoLocation(lat, lon, 4.2f) { ok ->
                if (ok) {
                    android.util.Log.d("EvieApp", "Geolocalização sincronizada com o PC.")
                }
            }
        } catch (_: Exception) {}
    }

    private fun showConfirmGateDialog(
        key: String,
        title: String,
        detail: String,
        expiresIn: Int
    ) {
        if (isDestroyedActivity) return

        confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
        activeConfirmDialog?.dismiss()
        activeConfirmKey = key

        val density = resources.displayMetrics.density
        fun dp(value: Int): Int = (value * density).toInt()

        val rootLayout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_dialog)
            setPadding(dp(22), dp(20), dp(22), dp(20))
        }

        val tvHeader = android.widget.TextView(this).apply {
            text = "⚠️ GATE HUMANO: AÇÃO CRÍTICA"
            textSize = 13f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))
            letterSpacing = 0.08f
            setPadding(0, 0, 0, dp(10))
        }

        val divider = View(this).apply {
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(1)
            ).apply { bottomMargin = dp(14) }
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.hud_yellow))
        }

        val tvTitle = android.widget.TextView(this).apply {
            text = title
            textSize = 12f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
            setPadding(0, 0, 0, dp(8))
        }

        val tvDetail = android.widget.TextView(this).apply {
            text = detail
            textSize = 10f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.NORMAL)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_dim))
            setPadding(0, 0, 0, dp(14))
        }

        var secondsRemaining = if (expiresIn > 0) expiresIn else 90
        val tvTimer = android.widget.TextView(this).apply {
            text = "EXPIRA EM: ${secondsRemaining}s"
            textSize = 10f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
            setPadding(0, 0, 0, dp(16))
        }

        val btnConfirm = android.widget.Button(this).apply {
            text = "AUTORIZAR  ✓"
            textSize = 11f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_green))
            setBackgroundResource(R.drawable.bg_hud_button_mic)
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
            ).apply { bottomMargin = dp(8) }
        }

        val btnReject = android.widget.Button(this).apply {
            text = "RECUSAR  ✕"
            textSize = 11f
            setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.hud_red))
            setBackgroundResource(R.drawable.bg_hud_button_interrupt)
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
            )
        }

        rootLayout.addView(tvHeader)
        rootLayout.addView(divider)
        rootLayout.addView(tvTitle)
        rootLayout.addView(tvDetail)
        rootLayout.addView(tvTimer)
        rootLayout.addView(btnConfirm)
        rootLayout.addView(btnReject)

        val dialog = AlertDialog.Builder(this)
            .setView(rootLayout)
            .setCancelable(true)
            .create()

        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)

        btnConfirm.setOnClickListener {
            confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
            dialog.dismiss()
            activeConfirmKey = null
            activeConfirmDialog = null
            appendLog("· SYS: Autorizando ação crítica [$key]...", false)
            apiClient.resolveConfirm(key, true) { success, msg ->
                runOnUiThread {
                    if (success) {
                        Toast.makeText(this@MainActivity, "Ação autorizada!", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this@MainActivity, "Erro ao autorizar: $msg", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        btnReject.setOnClickListener {
            confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
            dialog.dismiss()
            activeConfirmKey = null
            activeConfirmDialog = null
            appendLog("· SYS: Recusando ação crítica [$key]...", false)
            apiClient.resolveConfirm(key, false) { _, _ ->
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "Ação recusada", Toast.LENGTH_SHORT).show()
                }
            }
        }

        dialog.setOnDismissListener {
            confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
            if (activeConfirmKey == key) {
                activeConfirmKey = null
                activeConfirmDialog = null
                apiClient.resolveConfirm(key, false) { _, _ -> }
            }
        }

        confirmTimerRunnable = object : Runnable {
            override fun run() {
                secondsRemaining--
                if (secondsRemaining <= 0) {
                    dialog.dismiss()
                } else {
                    tvTimer.text = "EXPIRA EM: ${secondsRemaining}s"
                    mainHandler.postDelayed(this, 1000L)
                }
            }
        }
        mainHandler.postDelayed(confirmTimerRunnable!!, 1000L)

        activeConfirmDialog = dialog
        dialog.show()
    }

    override fun onDestroy() {
        super.onDestroy()
        isDestroyedActivity = true
        confirmTimerRunnable?.let { mainHandler.removeCallbacks(it) }
        activeConfirmDialog?.dismiss()
        activeConfirmDialog = null
        activeDownloadDialog?.dismiss()
        activeDownloadDialog = null
        activeScreenshotDialog?.dismiss()
        activeScreenshotDialog = null

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                (screenCaptureCallback as? Activity.ScreenCaptureCallback)?.let {
                    unregisterScreenCaptureCallback(it)
                }
            }
        } catch (_: Exception) {}

        screenshotObserver?.let {
            try {
                contentResolver.unregisterContentObserver(it)
            } catch (_: Exception) {}
        }

        tts?.stop()
        tts?.shutdown()
        tts = null

        mainHandler.removeCallbacks(clockRunnable)
        audioManager.stopStreaming()
        remoteStreamJob?.cancel()
        remoteStreamJob = null
        if (EvieBackgroundService.activeActivity == this) {
            EvieBackgroundService.activeActivity = null
        }
    }

    // ── Remote Desktop & SpaceView Engine (Matrix GPU Zoom & Pan) ────────────
    private var isRemoteDesktopActive = false
    private var activeRemoteMonitor = 0
    private var remoteMonitorsCount = 2
    private var remoteStreamJob: kotlinx.coroutines.Job? = null
    private var lastRemoteTouchNormX = 0.5f
    private var lastRemoteTouchNormY = 0.5f
    private var isTouchDragging = false

    // Hardware GPU Matrix Zoom & Pan for Ultrawide Monitors
    private val baseMatrix = Matrix()
    private val currentMatrix = Matrix()
    private var currentZoom = 1.0f
    private var currentBitmapWidth = 0f
    private var currentBitmapHeight = 0f
    private var isBaseMatrixInit = false

    // Interaction modes: 0 = TOUCH (Scroll PC), 1 = PAN (Drag zoomed screen), 2 = MOUSE (Pointer)
    private var remoteInteractionMode = 0

    private fun clampAndApplyMatrix() {
        val viewW = binding.remoteScreenView.width.toFloat()
        val viewH = binding.remoteScreenView.height.toFloat()
        if (viewW <= 0f || viewH <= 0f || currentBitmapWidth <= 0f || currentBitmapHeight <= 0f) return

        if (currentZoom <= 1.02f) {
            currentZoom = 1.0f
            currentMatrix.set(baseMatrix)
        } else {
            val rect = RectF(0f, 0f, currentBitmapWidth, currentBitmapHeight)
            currentMatrix.mapRect(rect)
            var deltaX = 0f
            var deltaY = 0f

            if (rect.width() <= viewW) {
                deltaX = (viewW - rect.width()) / 2f - rect.left
            } else {
                if (rect.left > 0f) deltaX = -rect.left
                else if (rect.right < viewW) deltaX = viewW - rect.right
            }

            if (rect.height() <= viewH) {
                deltaY = (viewH - rect.height()) / 2f - rect.top
            } else {
                if (rect.top > 0f) deltaY = -rect.top
                else if (rect.bottom < viewH) deltaY = viewH - rect.bottom
            }

            if (deltaX != 0f || deltaY != 0f) {
                currentMatrix.postTranslate(deltaX, deltaY)
            }
        }

        binding.remoteScreenView.imageMatrix = currentMatrix
        val label = if (currentZoom <= 1.05f) "🔍 1.0x" else "🔍 ${"%.1f".format(currentZoom)}x"
        binding.btnRemoteZoomReset?.text = label
    }

    private fun resetZoom() {
        currentZoom = 1.0f
        currentMatrix.set(baseMatrix)
        clampAndApplyMatrix()
    }

    private fun quickZoom(targetScale: Float, focusX: Float = -1f, focusY: Float = -1f) {
        val viewW = binding.remoteScreenView.width.toFloat()
        val viewH = binding.remoteScreenView.height.toFloat()
        if (viewW <= 0f || viewH <= 0f) return

        val fx = if (focusX >= 0f) focusX else (viewW / 2f)
        val fy = if (focusY >= 0f) focusY else (viewH / 2f)

        currentMatrix.set(baseMatrix)
        val factor = targetScale.coerceIn(1.0f, 6.0f)
        currentMatrix.postScale(factor, factor, fx, fy)
        currentZoom = factor
        clampAndApplyMatrix()
    }

    private fun updateDesktopBitmap(bitmap: Bitmap) {
        val prevW = currentBitmapWidth
        val prevH = currentBitmapHeight
        currentBitmapWidth = bitmap.width.toFloat()
        currentBitmapHeight = bitmap.height.toFloat()

        val viewW = binding.remoteScreenView.width.toFloat()
        val viewH = binding.remoteScreenView.height.toFloat()

        if (viewW > 0 && viewH > 0) {
            val dimensionsChanged = (prevW != currentBitmapWidth || prevH != currentBitmapHeight)
            if (!isBaseMatrixInit || dimensionsChanged) {
                val src = RectF(0f, 0f, currentBitmapWidth, currentBitmapHeight)
                val dst = RectF(0f, 0f, viewW, viewH)
                baseMatrix.setRectToRect(src, dst, Matrix.ScaleToFit.CENTER)
                if (!isBaseMatrixInit || currentZoom <= 1.05f) {
                    currentMatrix.set(baseMatrix)
                    currentZoom = 1.0f
                }
                isBaseMatrixInit = true
            }
        }

        binding.remoteScreenView.setImageBitmap(bitmap)
        binding.remoteScreenView.imageMatrix = currentMatrix
    }

    private fun mapTouchToRemoteCoords(touchX: Float, touchY: Float): Pair<Float, Float>? {
        if (currentBitmapWidth <= 0f || currentBitmapHeight <= 0f) return null
        val inv = Matrix()
        if (!currentMatrix.invert(inv)) return null
        val pts = floatArrayOf(touchX, touchY)
        inv.mapPoints(pts)
        val normX = (pts[0] / currentBitmapWidth).coerceIn(0f, 1f)
        val normY = (pts[1] / currentBitmapHeight).coerceIn(0f, 1f)
        return Pair(normX, normY)
    }

    private fun requestRemoteDesktopConnection() {
        if (isRemoteDesktopActive) {
            closeRemoteDesktop()
            return
        }
        val req = JsonObject().apply {
            addProperty("type", "remote_desktop_request")
            addProperty("device", config.deviceName)
        }
        val sent = apiClient.sendWebSocketJson(req)
        if (!sent) {
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val request = okhttp3.Request.Builder()
                        .url("${config.httpBaseUrl}/api/remote_desktop/request")
                        .addHeader("Authorization", "Bearer ${config.authToken}")
                        .post(okhttp3.RequestBody.create(null, ByteArray(0)))
                        .build()
                    apiClient.client.newCall(request).execute()
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Erro ao conectar: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    private fun openRemoteDesktop() {
        if (isDestroyedActivity) return
        isRemoteDesktopActive = true
        isBaseMatrixInit = false
        currentZoom = 1.0f
        binding.remoteScreenView.scaleType = ImageView.ScaleType.MATRIX
        binding.remoteScreenView.scaleX = 1.0f
        binding.remoteScreenView.scaleY = 1.0f
        binding.remoteScreenView.translationX = 0f
        binding.remoteScreenView.translationY = 0f
        binding.remoteControlBar?.visibility = View.GONE
        binding.btnToggleRemoteToolbar?.alpha = 0.45f
        binding.remoteDesktopOverlay.visibility = View.VISIBLE
        binding.pbRemoteLoading.visibility = View.VISIBLE
        updateRemoteTitle()

        // Fetch monitors count
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val req = okhttp3.Request.Builder()
                    .url("${config.httpBaseUrl}/api/remote_desktop/monitors")
                    .addHeader("Authorization", "Bearer ${config.authToken}")
                    .get()
                    .build()
                val resp = apiClient.client.newCall(req).execute()
                if (resp.isSuccessful) {
                    val body = resp.body?.string() ?: ""
                    val json = gson.fromJson(body, JsonObject::class.java)
                    val count = json.optInt("count", 2)
                    remoteMonitorsCount = if (count > 0) count else 2
                }
            } catch (_: Exception) {}
        }

        // Start stream loop (requesting crisp 1080p ultrawide 2560px width & quality 82)
        remoteStreamJob?.cancel()
        remoteStreamJob = lifecycleScope.launch(Dispatchers.IO) {
            while (isRemoteDesktopActive && !isDestroyedActivity) {
                try {
                    val frameUrl = "${config.httpBaseUrl}/api/remote_desktop/frame?monitor=$activeRemoteMonitor&quality=82&width=2560&token=${config.authToken}"
                    val req = okhttp3.Request.Builder()
                        .url(frameUrl)
                        .addHeader("Authorization", "Bearer ${config.authToken}")
                        .get()
                        .build()

                    val resp = apiClient.client.newCall(req).execute()
                    if (resp.isSuccessful) {
                        val stream = resp.body?.byteStream()
                        if (stream != null) {
                            val bitmap = BitmapFactory.decodeStream(stream)
                            if (bitmap != null) {
                                withContext(Dispatchers.Main) {
                                    if (isRemoteDesktopActive) {
                                        binding.pbRemoteLoading.visibility = View.GONE
                                        updateDesktopBitmap(bitmap)
                                    }
                                }
                            }
                        }
                    }
                } catch (_: Exception) {
                    kotlinx.coroutines.delay(120)
                }
                kotlinx.coroutines.delay(25)
            }
        }
    }

    private fun closeRemoteDesktop() {
        isRemoteDesktopActive = false
        remoteStreamJob?.cancel()
        remoteStreamJob = null
        resetZoom()
        binding.remoteControlBar?.visibility = View.GONE
        binding.remoteDesktopOverlay.visibility = View.GONE
        hideSoftKeyboard(binding.etRemoteKeySink)
    }

    private fun toggleRemoteMonitor() {
        activeRemoteMonitor = (activeRemoteMonitor + 1) % remoteMonitorsCount
        resetZoom()
        updateRemoteTitle()
        binding.pbRemoteLoading.visibility = View.VISIBLE
    }

    private fun updateRemoteTitle() {
        val label = if (activeRemoteMonitor == 0) "MONITOR 1 (PRINCIPAL)" else "MONITOR 2 (SECUNDÁRIO)"
        binding.tvRemoteTitle.text = "◈ PC: $label"
        binding.btnRemoteMonitorToggle.text = if (activeRemoteMonitor == 0) "🖥️ M1" else "🖥️ M2"
    }

    private fun toggleRemoteKeyboard() {
        binding.etRemoteKeySink.requestFocus()
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager
        imm?.showSoftInput(binding.etRemoteKeySink, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
    }

    private fun hideSoftKeyboard(view: View) {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager
        imm?.hideSoftInputFromWindow(view.windowToken, 0)
    }

    private fun sendRemoteInput(action: String, x: Float, y: Float, text: String = "", key: String = "", dy: Int = 0) {
        val payload = JsonObject().apply {
            addProperty("type", "remote_input")
            addProperty("action", action)
            addProperty("monitor", activeRemoteMonitor)
            addProperty("x", x)
            addProperty("y", y)
            if (text.isNotEmpty()) addProperty("text", text)
            if (key.isNotEmpty()) addProperty("key", key)
            if (dy != 0) addProperty("dy", dy)
        }
        val sent = apiClient.sendWebSocketJson(payload)
        if (!sent) {
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val mediaType = "application/json".toMediaType()
                    val req = okhttp3.Request.Builder()
                        .url("${config.httpBaseUrl}/api/remote_desktop/input")
                        .addHeader("Authorization", "Bearer ${config.authToken}")
                        .post(payload.toString().toRequestBody(mediaType))
                        .build()
                    apiClient.client.newCall(req).execute()
                } catch (_: Exception) {}
            }
        }
    }

    @android.annotation.SuppressLint("ClickableViewAccessibility")
    private fun setupRemoteDesktopTouchAndKeyboard() {
        var downTime = 0L
        var downTouchX = 0f
        var downTouchY = 0f
        var lastTouchX = 0f
        var lastTouchY = 0f
        var lastScrollY = 0f
        var isTwoFingerGesture = false
        var hasMovedSignificant = false
        var lastTapTime = 0L
        var lastTapX = 0f
        var lastTapY = 0f
        var prevTwoFingerMidX = 0f
        var prevTwoFingerMidY = 0f
        var isTwoFingerPanning = false

        val scaleDetector = android.view.ScaleGestureDetector(
            this,
            object : android.view.ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScale(detector: android.view.ScaleGestureDetector): Boolean {
                    val factor = detector.scaleFactor
                    val targetZoom = (currentZoom * factor).coerceIn(1.0f, 6.0f)
                    val actualFactor = targetZoom / currentZoom
                    currentZoom = targetZoom
                    currentMatrix.postScale(actualFactor, actualFactor, detector.focusX, detector.focusY)
                    clampAndApplyMatrix()
                    return true
                }
            }
        )

        binding.remoteScreenView.setOnTouchListener { _, event ->
            scaleDetector.onTouchEvent(event)

            val coords = mapTouchToRemoteCoords(event.x, event.y)
            val normX = coords?.first ?: 0.5f
            val normY = coords?.second ?: 0.5f

            when (event.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    downTime = System.currentTimeMillis()
                    downTouchX = event.x
                    downTouchY = event.y
                    lastTouchX = event.x
                    lastTouchY = event.y
                    lastScrollY = event.y
                    lastRemoteTouchNormX = normX
                    lastRemoteTouchNormY = normY
                    hasMovedSignificant = false
                    isTwoFingerGesture = false
                    isTwoFingerPanning = false
                    isTouchDragging = false

                    if (remoteInteractionMode == 2) {
                        sendRemoteInput("move", normX, normY)
                    }
                }
                android.view.MotionEvent.ACTION_POINTER_DOWN -> {
                    if (event.pointerCount >= 2) {
                        isTwoFingerGesture = true
                        prevTwoFingerMidX = (event.getX(0) + event.getX(1)) / 2f
                        prevTwoFingerMidY = (event.getY(0) + event.getY(1)) / 2f
                        isTwoFingerPanning = true
                    }
                }
                android.view.MotionEvent.ACTION_MOVE -> {
                    if (scaleDetector.isInProgress) {
                        // Pinching handled cleanly by ScaleGestureDetector
                        return@setOnTouchListener true
                    }

                    if (event.pointerCount >= 2) {
                        // Two-finger pan across the zoomed view
                        val midX = (event.getX(0) + event.getX(1)) / 2f
                        val midY = (event.getY(0) + event.getY(1)) / 2f
                        if (isTwoFingerPanning) {
                            val dx = midX - prevTwoFingerMidX
                            val dy = midY - prevTwoFingerMidY
                            if (Math.abs(dx) > 1f || Math.abs(dy) > 1f) {
                                hasMovedSignificant = true
                                currentMatrix.postTranslate(dx, dy)
                                clampAndApplyMatrix()
                            }
                        }
                        prevTwoFingerMidX = midX
                        prevTwoFingerMidY = midY
                        return@setOnTouchListener true
                    }

                    // Single finger move
                    val totalDistX = Math.abs(event.x - downTouchX)
                    val totalDistY = Math.abs(event.y - downTouchY)
                    if (totalDistX > 14f || totalDistY > 14f) {
                        hasMovedSignificant = true
                    }

                    when (remoteInteractionMode) {
                        0 -> { // TOUCH mode: 1 finger vertical drag scrolls PC
                            if (hasMovedSignificant) {
                                val deltaY = event.y - lastScrollY
                                if (Math.abs(deltaY) >= 4f) {
                                    val scrollAmount = (deltaY * 3.2f).toInt()
                                    sendRemoteInput("scroll", normX, normY, dy = scrollAmount)
                                    lastScrollY = event.y
                                    lastRemoteTouchNormX = normX
                                    lastRemoteTouchNormY = normY
                                }
                            }
                        }
                        1 -> { // PAN mode: 1 finger drag pans the ultrawide screen
                            if (hasMovedSignificant) {
                                val dx = event.x - lastTouchX
                                val dy = event.y - lastTouchY
                                currentMatrix.postTranslate(dx, dy)
                                clampAndApplyMatrix()
                                lastTouchX = event.x
                                lastTouchY = event.y
                            }
                        }
                        2 -> { // MOUSE mode: 1 finger moves mouse pointer
                            val dx = Math.abs(normX - lastRemoteTouchNormX)
                            val dy = Math.abs(normY - lastRemoteTouchNormY)
                            if (dx > 0.005f || dy > 0.005f) {
                                isTouchDragging = true
                                sendRemoteInput("move", normX, normY)
                                lastRemoteTouchNormX = normX
                                lastRemoteTouchNormY = normY
                            }
                        }
                    }
                }
                android.view.MotionEvent.ACTION_POINTER_UP -> {
                    if (event.pointerCount == 2) {
                        isTwoFingerPanning = false
                    }
                    if (isTwoFingerGesture && !hasMovedSignificant && !scaleDetector.isInProgress) {
                        val duration = System.currentTimeMillis() - downTime
                        if (duration < 450) {
                            sendRemoteInput("right_click", normX, normY)
                        }
                    }
                }
                android.view.MotionEvent.ACTION_UP -> {
                    val duration = System.currentTimeMillis() - downTime
                    val now = System.currentTimeMillis()

                    if (!hasMovedSignificant && !scaleDetector.isInProgress) {
                        // Double-tap zoom toggle
                        if (now - lastTapTime < 320 && Math.abs(event.x - lastTapX) < 40 && Math.abs(event.y - lastTapY) < 40) {
                            if (currentZoom > 1.05f) {
                                resetZoom()
                            } else {
                                quickZoom(2.5f, event.x, event.y)
                            }
                            lastTapTime = 0L
                            return@setOnTouchListener true
                        }
                        lastTapTime = now
                        lastTapX = event.x
                        lastTapY = event.y

                        if (isTwoFingerGesture) {
                            sendRemoteInput("right_click", normX, normY)
                        } else if (duration > 550) {
                            sendRemoteInput("right_click", normX, normY)
                        } else {
                            sendRemoteInput("click", normX, normY)
                        }
                    } else if (remoteInteractionMode == 2 && isTouchDragging) {
                        sendRemoteInput("up", normX, normY)
                    }
                }
            }
            true
        }

        // Virtual keyboard typing capture
        binding.etRemoteKeySink.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (count > 0 && s != null) {
                    val newText = s.subSequence(start, start + count).toString()
                    sendRemoteInput("text", lastRemoteTouchNormX, lastRemoteTouchNormY, text = newText)
                } else if (before > 0 && count == 0) {
                    sendRemoteInput("key", lastRemoteTouchNormX, lastRemoteTouchNormY, key = "backspace")
                }
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })

        binding.etRemoteKeySink.setOnEditorActionListener { _, actionId, event ->
            if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_SEND ||
                actionId == android.view.inputmethod.EditorInfo.IME_ACTION_DONE ||
                (event != null && event.keyCode == android.view.KeyEvent.KEYCODE_ENTER)
            ) {
                sendRemoteInput("key", lastRemoteTouchNormX, lastRemoteTouchNormY, key = "enter")
                true
            } else {
                false
            }
        }
    }
}



