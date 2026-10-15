package com.evie.eyes.render

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LightingColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.Rect
import android.graphics.Shader
import com.evie.eyes.core.clamp
import com.evie.eyes.core.pyRound
import com.evie.eyes.effects.Particle
import com.evie.eyes.model.EyeParams
import kotlin.math.hypot
import kotlin.math.max

private const val GLOW_BLEND = 0.1     // largura (fração da tela) da transição entre o halo esquerdo e o direito
private const val TINT_STRENGTH = 0.16 // intensidade máxima da vinheta colorida atrás dos olhos
private const val TRAIL_START = 0.012  // velocidade (fração da largura por frame) a partir da qual o rastro aparece
private const val TRAIL_FULL = 0.05    // velocidade em que o rastro chega ao máximo
private const val TRAIL_JUMP = 0.12    // acima disso é um salto (troca de cena, redimensionar), não movimento: sem rastro
private const val TRAIL_DECAY = 0.5    // quanto de brilho o rastro mantém a cada frame, no máximo
private const val TRAIL_RELEASE = 0.55 // velocidade com que o rastro "solta" depois que o olho para

/** Bitmap com o Canvas que o desenha (criado uma vez e reaproveitado entre frames). */
private class Surface(val bitmap: Bitmap) {
    val canvas = Canvas(bitmap)

    constructor(w: Int, h: Int) : this(Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888))
}

/**
 * Renderizador: desenha os olhos em supersampling, reduz, soma brilho em duas escalas, vinheta de
 * emoção e rastro. Port fiel de `FaceRenderer` (render/pygame_backend.py), sobre Bitmaps do Android.
 *
 * O Bitmap devolvido por [render] pertence ao renderer e é reaproveitado no frame seguinte.
 * Não é thread-safe: use sempre da mesma thread.
 */
class FaceRenderer(
    width: Int,
    height: Int,
    val bg: Int = Color.rgb(4, 6, 8),
    quality: RenderQuality = RenderQuality.HIGH,
) {
    var size: Pair<Int, Int> = Pair(max(1, width), max(1, height))
        private set
    var quality: RenderQuality = quality
        private set

    private val painter = EyePainter()
    private lateinit var layout: Layout
    private lateinit var hires: Surface
    private lateinit var frame: Surface
    private var trail: Surface? = null
    private var trailDecay = 0.0
    private var lastPositions: List<Pair<Double, Double>>? = null

    private val buffers = HashMap<Triple<Int, Int, Int>, Surface>()
    private val vignettes = HashMap<Pair<Int, Int>, Bitmap>()
    private val lightings = arrayOfNulls<LightingColorFilter>(256)

    private val smooth = Paint().apply { isFilterBitmap = true }
    private val copy = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.SRC) }
    private val addSmooth = Paint().apply {
        isFilterBitmap = true
        xfermode = PorterDuffXfermode(PorterDuff.Mode.ADD)
    }
    private val addTinted = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.ADD) }
    private val multiply = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.MULTIPLY) }
    private val lighten = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.LIGHTEN) }

    init {
        allocate()
    }

    fun setQuality(newQuality: RenderQuality) {
        quality = newQuality
        allocate()
    }

    fun resize(width: Int, height: Int) {
        size = Pair(max(1, width), max(1, height))
        allocate()
    }

    private fun allocate() {
        val ss = quality.supersample
        layout = Layout(size.first, size.second).scaled(ss)
        frame = Surface(size.first, size.second)
        hires = if (ss > 1) Surface(layout.width, layout.height) else frame
        trail = null
        lastPositions = null
        trailDecay = 0.0
        buffers.clear()
        vignettes.values.forEach { it.recycle() }
        vignettes.clear()
    }

    /** Devolve um Bitmap (largura x altura) com os dois olhos e as partículas de emoção. */
    fun render(eyes: List<EyeParams>, particles: List<Particle> = emptyList()): Bitmap {
        painter.drawEyes(hires.canvas, eyes, layout, bg, particles)
        if (quality.supersample > 1) {
            frame.canvas.drawBitmap(hires.bitmap, null, Rect(0, 0, size.first, size.second), smooth)
        }
        if (quality.trail) applyTrail(eyes)

        val glows = eyes.map { clamp(it.glow) }
        val tint = if (quality.tint) tintColor(eyes, glows) else null
        bloom(glows, tint)?.let {
            frame.canvas.drawBitmap(it, null, Rect(0, 0, size.first, size.second), addSmooth)
        }
        return frame.bitmap
    }

    // --- brilho e vinheta ----------------------------------------------------

    /**
     * Halo em camadas: cada uma é uma versão borrada (reduzida) do quadro, escalada por olho. As reduções
     * são encadeadas (quadro -> camada fina -> camada larga) e as camadas são somadas na menor resolução
     * que as comporta, então só há uma ampliação até o tamanho final.
     */
    private fun bloom(glows: List<Double>, tint: Int?): Bitmap? {
        if (glows.isEmpty() || (glows.max() <= 0.01 && tint == null)) return null
        var source = frame.bitmap
        val layers = ArrayList<Surface>()
        val last = quality.bloom.size - 1
        quality.bloom.forEachIndexed { index, (divisor, strength) ->
            val w = max(1, size.first / divisor)
            val h = max(1, size.second / divisor)
            val raw = areaScale(source, w, h, index)
            val layer = if (index < last) copyOf(raw, 50 + index) else raw
            layer.canvas.drawRect(0f, 0f, w.toFloat(), h.toFloat(), glowLevels(glows, w, strength))
            if (tint != null && index == last) {
                addTinted.colorFilter = LightingColorFilter(tint, 0)
                layer.canvas.drawBitmap(vignette(w, h), 0f, 0f, addTinted)
            }
            layers.add(layer)
            source = raw.bitmap
        }
        var halo = layers.last()
        for (finer in layers.dropLast(1).reversed()) {
            finer.canvas.drawBitmap(halo.bitmap, null, Rect(0, 0, finer.bitmap.width, finer.bitmap.height), addSmooth)
            halo = finer
        }
        return halo.bitmap
    }

    /** Mapa de intensidade do halo: cada metade da tela segue o brilho do seu olho (gradiente horizontal). */
    private fun glowLevels(glows: List<Double>, width: Int, strength: Double): Paint {
        val left = pyRound(255.0 * glows.first() * strength)
        val right = pyRound(255.0 * glows.last() * strength)
        val a = Color.rgb(left, left, left)
        val b = Color.rgb(right, right, right)
        val half = (GLOW_BLEND / 2).toFloat()
        multiply.shader = LinearGradient(
            0f, 0f, width.toFloat(), 0f, intArrayOf(a, a, b, b),
            floatArrayOf(0f, 0.5f - half, 0.5f + half, 1f), Shader.TileMode.CLAMP,
        )
        return multiply
    }

    /** Cor da vinheta: média das cores dos olhos, mais forte quando o brilho é alto. */
    private fun tintColor(eyes: List<EyeParams>, glows: List<Double>): Int {
        val level = TINT_STRENGTH * (0.45 + 0.55 * glows.sum() / max(glows.size, 1))
        val count = max(eyes.size, 1)
        fun channel(pick: (EyeParams) -> Double): Int = pyRound(clamp(eyes.sumOf(pick) / count / 255.0) * 255 * level)
        return Color.rgb(channel { it.color.r }, channel { it.color.g }, channel { it.color.b })
    }

    /** Mancha radial (cinza) centrada nos olhos, cacheada por tamanho; é tingida na hora de desenhar. */
    private fun vignette(w: Int, h: Int): Bitmap = vignettes.getOrPut(Pair(w, h)) {
        val pixels = IntArray(w * h)
        for (y in 0 until h) {
            for (x in 0 until w) {
                val dx = ((x + 0.5) / w - 0.5) / 0.5
                val dy = ((y + 0.5) / h - 0.5) / 0.5
                val v = clamp(1.0 - (dx * dx * 0.55 + dy * dy * 1.1))
                val level = pyRound(255 * v * v)
                pixels[y * w + x] = Color.rgb(level, level, level)
            }
        }
        Bitmap.createBitmap(pixels, w, h, Bitmap.Config.ARGB_8888)
    }

    // --- rastro --------------------------------------------------------------

    /** Persistência estilo LED: só aparece quando o olhar se move rápido. */
    private fun applyTrail(eyes: List<EyeParams>) {
        val positions = eyes.mapIndexed { i, e -> layout.eyeCenter(e, if (i == 0) -1 else 1) }
        var speed = 0.0
        val previous = lastPositions
        if (previous != null && previous.size == positions.size) {
            val moved = positions.zip(previous).maxOf { (a, b) -> hypot(a.first - b.first, a.second - b.second) }
            speed = moved / quality.supersample / max(size.first, 1)
        }
        lastPositions = positions

        var target = TRAIL_DECAY * clamp((speed - TRAIL_START) / (TRAIL_FULL - TRAIL_START))
        if (speed > TRAIL_JUMP) {
            target = 0.0
            trailDecay = 0.0
        }
        trailDecay = max(target, trailDecay * TRAIL_RELEASE)

        val ghost = trail
        if (ghost != null && trailDecay > 0.02) {
            lighten.colorFilter = lightingFilter(pyRound(255.0 * trailDecay))
            frame.canvas.drawBitmap(ghost.bitmap, 0f, 0f, lighten)
        }
        val store = ghost ?: Surface(size.first, size.second).also { trail = it }
        store.canvas.drawBitmap(frame.bitmap, 0f, 0f, copy)
    }

    private fun lightingFilter(level: Int): LightingColorFilter {
        val l = level.coerceIn(0, 255)
        return lightings[l] ?: LightingColorFilter(Color.rgb(l, l, l), 0).also { lightings[l] = it }
    }

    // --- bitmaps temporários -------------------------------------------------

    private fun buffer(w: Int, h: Int, slot: Int): Surface = buffers.getOrPut(Triple(w, h, slot)) { Surface(w, h) }

    private fun copyOf(src: Surface, slot: Int): Surface {
        val dst = buffer(src.bitmap.width, src.bitmap.height, slot)
        dst.canvas.drawBitmap(src.bitmap, 0f, 0f, copy)
        return dst
    }

    /**
     * Reduz [src] para [w] x [h] por média de área: metades sucessivas (cada uma é uma média exata de
     * 2x2) e um último passo bilinear. Isso imita o `smoothscale` do pygame, que faz média em reduções.
     */
    private fun areaScale(src: Bitmap, w: Int, h: Int, slot: Int): Surface {
        var current = src
        var stage = 0
        while (current.width / 2 >= w && current.height / 2 >= h) {
            val half = buffer(current.width / 2, current.height / 2, 100 + stage++)
            half.canvas.drawBitmap(current, null, Rect(0, 0, half.bitmap.width, half.bitmap.height), smooth)
            current = half.bitmap
        }
        val dst = buffer(w, h, slot)
        dst.canvas.drawBitmap(current, null, Rect(0, 0, w, h), smooth)
        return dst
    }
}
