package com.evie.assistant

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import kotlin.math.sqrt
import com.evie.eyes.render.EvieEyesView as CoreEvieEyesView
import com.evie.eyes.render.RenderQuality

/**
 * EvieEyesView - Motor Procedural Oficial de Olhos Expressivos da Evie (Mark LV).
 * Baseado no Evie-EYES-Kotlin (Choreographer 60 FPS, supersampling 2x, bloom em 2 escalas,
 * vinheta de emoção, rastros, partículas de emoção, reflexos especulares e física de molas).
 *
 * Interações táteis e gestuais integradas:
 * - Toque único:
 *   * Lado esquerdo (x < 40%): Pisca olho esquerdo (wink_left) com feedback tátil.
 *   * Lado direito (x > 60%): Pisca olho direito (wink_right) com feedback tátil.
 *   * Centro (40%..60%): Carinho amoroso (love / corações 💕) ou alegria.
 * - Toque duplo:
 *   * Dança animada / comemoração com pulinho alegre (hop kick), olhos felizes (happy ^^) e estrelas.
 * - Arraste contínuo:
 *   * Olhar interativo acompanhando a ponta dos dedos pela tela.
 * - Chacoalhar o celular (Shake detection via acelerômetro):
 *   * Olhos chacoalham, sobressalto com pulo, expressão irritada (angry 💢) e vibração háptica.
 */
open class EvieEyesView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : CoreEvieEyesView(context, attrs, defStyleAttr), SensorEventListener {

    private var currentVisualState: VisualState = VisualState.IDLE_OBSERVING
    private var audioLevel: Float = 0f

    // Gestos táteis
    private val gestureDetector: GestureDetector
    private var isDraggingTouch: Boolean = false

    // Detecção de shake (Acelerômetro)
    private var sensorManager: SensorManager? = null
    private var accelerometer: Sensor? = null
    private var lastShakeTimestamp: Long = 0L
    private var lastAccelX: Float = 0f
    private var lastAccelY: Float = 0f
    private var lastAccelZ: Float = 9.8f
    private var hasPrevAccel: Boolean = false

    // Feedback tátil (Vibração háptica)
    private var vibrator: Vibrator? = null

    init {
        // Desativamos o trackTouch básico da classe pai para gerenciar gestos completos com prioridade
        trackTouch = false
        tapToPoke = false
        adaptiveQuality = true
        quality = RenderQuality.HIGH

        // 1. Configuração do GestureDetector para toques simples e duplos
        val gestureListener = object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent): Boolean {
                return true
            }

            override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                handleSingleTap(e.x, e.y)
                return true
            }

            override fun onDoubleTap(e: MotionEvent): Boolean {
                handleDoubleTap()
                return true
            }
        }
        gestureDetector = GestureDetector(context, gestureListener)

        // 2. Sensores de movimento e vibração
        initSensors(context)
    }

    private fun initSensors(ctx: Context) {
        try {
            sensorManager = ctx.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
            accelerometer = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        } catch (_: Exception) {}

        try {
            vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            }
        } catch (_: Exception) {}
    }

    // --- Ciclo de Vida dos Sensores -------------------------------------------

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        registerShakeSensor()
    }

    override fun onDetachedFromWindow() {
        unregisterShakeSensor()
        super.onDetachedFromWindow()
    }

    private fun registerShakeSensor() {
        accelerometer?.let {
            sensorManager?.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
    }

    private fun unregisterShakeSensor() {
        sensorManager?.unregisterListener(this)
    }

    // --- Interações Táteis (Touch & Gestures) ----------------------------------

    override fun onTouchEvent(event: MotionEvent): Boolean {
        // Permite que o GestureDetector capture eventos de toque simples e duplo
        val handled = gestureDetector.onTouchEvent(event)

        when (event.actionMasked) {
            MotionEvent.ACTION_MOVE -> {
                // Acompanha a direção do toque suavemente pela tela
                val w = width.toFloat().coerceAtLeast(1f)
                val h = height.toFloat().coerceAtLeast(1f)
                val nx = ((event.x / w) * 2f - 1f).coerceIn(-1f, 1f)
                val ny = ((event.y / h) * 2f - 1f).coerceIn(-1f, 1f)
                face.lookAt(nx.toDouble(), ny.toDouble(), hold = 0.5)
                isDraggingTouch = true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (isDraggingTouch) {
                    isDraggingTouch = false
                }
            }
        }

        return handled || super.onTouchEvent(event)
    }

    /**
     * Trata o toque único inteligente (idêntico ao PC):
     * - Olho Esquerdo (x < 40%): Pisca olho esquerdo.
     * - Olho Direito (x > 60%): Pisca olho direito.
     * - Centro (40%..60%): Carinho e alegria (happy ^^) com estrelas e pulinho.
     */
    private fun handleSingleTap(x: Float, y: Float) {
        val w = width.toFloat().coerceAtLeast(1f)
        val relX = x / w

        vibrateShort(40)

        when {
            relX < 0.40f -> {
                // Toque no olho esquerdo -> Pisca olho esquerdo
                triggerWink("left")
            }
            relX > 0.60f -> {
                // Toque no olho direito -> Pisca olho direito
                triggerWink("right")
            }
            else -> {
                // Toque no meio -> Expressão alegre / feliz (^^) com pulinho
                triggerHappy(2.5f)
            }
        }
    }

    /**
     * Trata o toque duplo (idêntico ao PC):
     * - Dança rítmica com trajetória em arco parabólico a 120 BPM e olhos felizes (^^).
     */
    private fun handleDoubleTap() {
        vibrateShort(80)
        triggerDance(4.5f)
    }

    // --- Detecção de Chacoalhão (Shake Detection) -----------------------------

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null || event.sensor.type != Sensor.TYPE_ACCELEROMETER) return

        val x = event.values[0]
        val y = event.values[1]
        val z = event.values[2]

        if (!hasPrevAccel) {
            lastAccelX = x
            lastAccelY = y
            lastAccelZ = z
            hasPrevAccel = true
            return
        }

        val dx = x - lastAccelX
        val dy = y - lastAccelY
        val dz = z - lastAccelZ

        lastAccelX = x
        lastAccelY = y
        lastAccelZ = z

        val speed = sqrt(dx * dx + dy * dy + dz * dz)
        val now = System.currentTimeMillis()

        // Limiar de agitação (shake) com debounce de 1 segundo
        if (speed > 13.0f && (now - lastShakeTimestamp) > 1000L) {
            lastShakeTimestamp = now
            onDeviceShaken()
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    /**
     * Executado ao chacoalhar o celular:
     * - Olhos tremem/sobressaltam (hop kick), expressão de irritação/tontura (angry 💢) e vibração.
     */
    private fun onDeviceShaken() {
        vibratePattern(longArrayOf(0, 70, 50, 100))
        face.idle.wake()
        face.hop.kick(0.8)
        face.tremble.enabled = true
        setExpression("angry", 3.5)
    }

    // --- Feedback Háptico -----------------------------------------------------

    private fun vibrateShort(durationMs: Long) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(durationMs)
            }
        } catch (_: Exception) {}
    }

    private fun vibratePattern(pattern: LongArray) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, -1))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, -1)
            }
        } catch (_: Exception) {}
    }

    // --- Sincronização de Estados e Expressões ---------------------------------

    /** Define o estado visual procedural enviado pelo servidor ou inferido localmente. */
    fun setVisualState(state: VisualState) {
        currentVisualState = state
        when (state) {
            VisualState.HAPPY -> {
                setExpression("happy", 3.5)
            }
            VisualState.CURIOUS_SPARK -> {
                setExpression("suspicious", 3.0)
                lookAt(0.35, -0.25, 2.5)
            }
            VisualState.THINKING_DEEP -> {
                // Ao pensar, olha para cima/lado pensativa sem forçar pálpebras caídas de sono
                lookAt(0.40, -0.60, 3.5)
                setExpression("neutral")
            }
            VisualState.SPEAKING -> {
                if (face.idle.stage == "asleep" || face.idle.stage == "sleepy") {
                    face.poke()
                }
                setExpression("neutral")
            }
            VisualState.FOCUS_CALM, VisualState.FOCUSED -> {
                lookAt(0.0, 0.0, 2.0)
                setExpression("neutral")
            }
            VisualState.SLEEPY -> {
                setExpression("sleepy")
            }
            VisualState.ALERT_URGENT, VisualState.SURPRISED -> {
                setExpression("surprised", 3.5)
            }
            VisualState.IDLE_OBSERVING -> {
                setExpression("neutral")
            }
        }
    }

    fun getVisualState(): VisualState = currentVisualState

    /** Compatibilidade com controle de estado do HUD (HologramSphereView). */
    fun setState(state: HologramSphereView.CoreState) {
        when (state) {
            HologramSphereView.CoreState.SPEAKING -> setVisualState(VisualState.SPEAKING)
            HologramSphereView.CoreState.MUTED -> setExpression("sleepy")
            HologramSphereView.CoreState.LISTENING -> {
                face.poke()
                setExpression("neutral")
            }
            HologramSphereView.CoreState.IDLE -> setVisualState(VisualState.IDLE_OBSERVING)
        }
    }

    /** Reatividade dinâmica à amplitude do áudio / voz da Evie. */
    fun setAudioLevel(level: Float) {
        audioLevel = level.coerceIn(0f, 1f)
        if (audioLevel > 0.4f) {
            face.breathing.period = 1.6
        } else {
            face.breathing.period = 4.0
        }
    }

    // --- Atalhos de Expressões e Emoções ---------------------------------------

    fun triggerWink(side: String = "left") {
        val preset = if (side.equals("right", ignoreCase = true)) "wink_right" else "wink_left"
        if (face.presets.containsKey(preset)) {
            setExpression(preset, 1.8)
        } else {
            setExpression("wink", 1.8)
        }
    }

    fun triggerSad(durationSec: Float = 3.5f) {
        setExpression("sad", durationSec.toDouble())
    }

    fun triggerAngry(durationSec: Float = 3.5f) {
        setExpression("angry", durationSec.toDouble())
    }

    fun triggerSurprised(durationSec: Float = 3.0f) {
        setExpression("surprised", durationSec.toDouble())
    }

    fun triggerLove(durationSec: Float = 4.0f) {
        setExpression("love", durationSec.toDouble())
    }

    fun triggerExcited(durationSec: Float = 4.0f) {
        setExpression("excited", durationSec.toDouble())
    }

    fun triggerSuspicious(durationSec: Float = 3.5f) {
        setExpression("suspicious", durationSec.toDouble())
    }

    fun triggerHappy(durationSec: Float = 2.5f) {
        face.idle.wake()
        face.hop.kick(0.4)
        face.fx.burst("star", 6)
        setExpression("happy", durationSec.toDouble())
    }

    fun triggerDance(durationSec: Float = 4.5f) {
        face.triggerDance(durationSec.toDouble())
    }
}
