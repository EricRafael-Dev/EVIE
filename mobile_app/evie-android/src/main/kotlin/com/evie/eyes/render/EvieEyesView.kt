package com.evie.eyes.render

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.Choreographer
import android.view.MotionEvent
import android.view.View
import com.evie.eyes.Face
import kotlin.math.max
import kotlin.math.min

/**
 * View que anima os olhos da Evie. Cuida do loop (simulação com passo fixo de 1/120 s, como no app
 * Python), do renderer e do letterbox: a face é desenhada em [renderWidth] x [renderHeight] e escalada
 * para caber na View mantendo a proporção.
 *
 * Uso básico:
 * ```
 * val eyes = EvieEyesView(context)
 * eyes.setExpression("happy", durationSeconds = 4.0)
 * eyes.lookAt(0.6, -0.2)
 * ```
 * O loop roda enquanto a View está anexada à janela e visível; use [start]/[stop] para controle manual.
 */
open class EvieEyesView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr), Choreographer.FrameCallback {

    /** A face animada. Pode ser trocada (por exemplo, para usar uma seed ou presets próprios). */
    var face: Face = Face()
        set(value) {
            field = value
            accumulator = 0.0
        }

    /** Tamanho lógico do desenho. As proporções do rosto são relativas a ele. */
    var renderWidth: Int = 800
        set(value) {
            field = value
            renderer = null
        }
    var renderHeight: Int = 480
        set(value) {
            field = value
            renderer = null
        }

    /** Nível de qualidade do render (low, medium, high). */
    var quality: RenderQuality = RenderQuality.HIGH
        set(value) {
            field = value
            renderer?.setQuality(value)
        }

    /**
     * Se verdadeiro (padrão), baixa a qualidade sozinho quando o aparelho não acompanha ~60 fps
     * (high -> medium -> low). Desligue para fixar o nível escolhido em [quality].
     */
    var adaptiveQuality: Boolean = true

    /** Se verdadeiro, o olhar segue o dedo. */
    var trackTouch: Boolean = false

    /** Se verdadeiro, um toque "cutuca" a Evie (acorda se estiver dormindo). */
    var tapToPoke: Boolean = false

    /** Cor de fundo (também usada nas faixas do letterbox). */
    var backgroundColorInt: Int = Color.rgb(4, 6, 8)
        set(value) {
            field = value
            renderer = null
        }

    /** Tempo médio (ms) de simulação + render por frame, para diagnóstico. */
    var frameMillis: Double = 0.0
        private set

    private var renderer: FaceRenderer? = null
    private var frame: Bitmap? = null
    private var running = false
    private var lastFrameNanos = 0L
    private var accumulator = 0.0
    private var slowFrames = 0
    private val paint = Paint().apply { isFilterBitmap = true }
    private val dst = RectF()

    // --- ciclo de vida ----------------------------------------------------------

    fun start() {
        if (running) return
        running = true
        lastFrameNanos = 0L
        Choreographer.getInstance().postFrameCallback(this)
    }

    fun stop() {
        running = false
        Choreographer.getInstance().removeFrameCallback(this)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (visibility == VISIBLE) start()
    }

    override fun onDetachedFromWindow() {
        stop()
        super.onDetachedFromWindow()
    }

    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        if (visibility == VISIBLE && isAttachedToWindow) start() else if (visibility != VISIBLE) stop()
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        val dt = if (lastFrameNanos == 0L) 0.0 else (frameTimeNanos - lastFrameNanos) / 1e9
        lastFrameNanos = frameTimeNanos

        val started = System.nanoTime()
        advance(dt)
        val current = renderer ?: FaceRenderer(renderWidth, renderHeight, backgroundColorInt, quality).also { renderer = it }
        frame = current.render(face.eyes, face.particles)
        recordCost((System.nanoTime() - started) / 1e6)

        invalidate()
        Choreographer.getInstance().postFrameCallback(this)
    }

    /** Avança a simulação em passos fixos (independentes do FPS do aparelho). */
    private fun advance(dt: Double) {
        accumulator += min(dt, MAX_DT)
        while (accumulator >= STEP) {
            face.update(STEP)
            accumulator -= STEP
        }
    }

    private fun recordCost(ms: Double) {
        frameMillis = if (frameMillis == 0.0) ms else frameMillis * 0.9 + ms * 0.1
        if (!adaptiveQuality) return
        slowFrames = if (frameMillis > SLOW_FRAME_MS) slowFrames + 1 else 0
        if (slowFrames > SLOW_FRAMES_BEFORE_DOWNGRADE && quality != RenderQuality.LOW) {
            quality = quality.lighter()
            slowFrames = 0
            frameMillis = 0.0
        }
    }

    // --- desenho -----------------------------------------------------------------

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(backgroundColorInt)
        val bitmap = frame ?: return
        computeLetterbox(bitmap.width, bitmap.height)
        canvas.drawBitmap(bitmap, null, dst, paint)
    }

    private fun computeLetterbox(w: Int, h: Int) {
        val scale = min(width / w.toFloat(), height / h.toFloat())
        val dw = w * scale
        val dh = h * scale
        val left = (width - dw) / 2f
        val top = (height - dh) / 2f
        dst.set(left, top, left + dw, top + dh)
    }

    // --- toque -------------------------------------------------------------------

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!trackTouch && !tapToPoke) return super.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE -> if (trackTouch) {
                computeLetterbox(renderWidth, renderHeight)
                val nx = ((event.x - dst.left) / max(dst.width(), 1f)) * 2f - 1f
                val ny = ((event.y - dst.top) / max(dst.height(), 1f)) * 2f - 1f
                face.lookAt(nx.toDouble(), ny.toDouble(), hold = 0.4)
            }
            MotionEvent.ACTION_UP -> if (tapToPoke) {
                face.poke()
                performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()

    // --- atalhos para a API da Face -----------------------------------------------

    fun setExpression(name: String, durationSeconds: Double? = null) = face.setExpression(name, durationSeconds)

    fun lookAt(x: Double, y: Double, holdSeconds: Double = 2.0) = face.lookAt(x, y, holdSeconds)

    fun blink(double: Boolean = false) = face.blinkNow(double)

    fun yawn() = face.yawn.trigger()

    fun sleep() = face.idle.sleepNow()

    fun poke() = face.poke()

    private companion object {
        const val STEP = 1.0 / 120.0        // passo fixo da simulação, independente do FPS de render
        const val MAX_DT = 0.1              // limite para não "pular" a animação depois de uma pausa
        const val SLOW_FRAME_MS = 15.0
        const val SLOW_FRAMES_BEFORE_DOWNGRADE = 90
    }
}
