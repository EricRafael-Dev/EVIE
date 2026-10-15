package com.evie.eyes.render

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import com.evie.eyes.core.clamp
import com.evie.eyes.core.pyRound
import kotlin.math.ceil
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * Sprites de borda suave (reflexo, blush, linha d'água), com cache.
 *
 * Cada sprite é uma elipse cujo alfa cai suavemente na borda, guardada como máscara ALPHA_8 e
 * desenhada com a cor/opacidade desejadas. O desfoque é gaussiano (sigma = 0,94 x raio, o que o
 * `pygame.transform.gaussian_blur` usa) e roda em resolução reduzida; o upscale vem do desenho.
 */
internal class SoftSprites {
    class Sprite(val alpha: Bitmap, val width: Int, val height: Int)

    private val cache = HashMap<Long, Sprite>()
    private val paint = Paint().apply { isFilterBitmap = true }
    private val dst = RectF()

    fun softEllipse(w: Double, h: Double, softness: Double): Sprite {
        val qw = max(1, pyRound(w / QUANT))
        val qh = max(1, pyRound(h / QUANT))
        val key = (qw.toLong() shl 40) or (qh.toLong() shl 16) or pyRound(softness * 100).toLong()
        cache[key]?.let { return it }
        if (cache.size >= CACHE_LIMIT) cache.clear()

        val sw = qw * QUANT
        val sh = qh * QUANT
        val blur = pyRound(clamp(softness, 0.0, 2.0) * min(sw, sh) / 2)
        val pad = 2 * blur
        val fullW = sw + 2 * pad
        val fullH = sh + 2 * pad
        // Borda difusa não precisa de resolução cheia: borra numa versão reduzida.
        val k = max(1, pyRound(blur.toDouble() / BLUR_STEP))
        val smallW = max(1, pyRound(fullW.toDouble() / k))
        val smallH = max(1, pyRound(fullH.toDouble() / k))

        val mask = ellipseCoverage(smallW, smallH, pad.toDouble() / k, pad.toDouble() / k, sw.toDouble() / k, sh.toDouble() / k)
        if (blur >= 1) gaussianBlur(mask, smallW, smallH, max(1, pyRound(blur.toDouble() / k)))

        val pixels = IntArray(smallW * smallH) { i ->
            val a = (mask[i] * 255f + 0.5f).toInt().coerceIn(0, 255)
            Color.argb(a, 255, 255, 255)
        }
        val argb = Bitmap.createBitmap(smallW, smallH, Bitmap.Config.ARGB_8888)
        argb.setPixels(pixels, 0, smallW, 0, 0, smallW, smallH)
        val alpha = argb.extractAlpha()
        argb.recycle()
        return Sprite(alpha, fullW, fullH).also { cache[key] = it }
    }

    /** Desenha uma elipse suave de cor [color] (RGB) e opacidade [alpha] (0..1) centrada em ([cx], [cy]). */
    fun blit(canvas: Canvas, cx: Double, cy: Double, w: Double, h: Double, color: Int, alpha: Double, softness: Double = 0.35) {
        val a = pyRound(255.0 * clamp(alpha))
        if (a <= 0 || w < 1 || h < 1) return
        val sprite = softEllipse(w, h, softness)
        val left = pyRound(cx) - sprite.width / 2
        val top = pyRound(cy) - sprite.height / 2
        paint.color = Color.argb(a, Color.red(color), Color.green(color), Color.blue(color))
        dst.set(left.toFloat(), top.toFloat(), (left + sprite.width).toFloat(), (top + sprite.height).toFloat())
        canvas.drawBitmap(sprite.alpha, null, dst, paint)
    }

    fun clear() = cache.clear()

    private companion object {
        const val QUANT = 2        // px: tamanhos são arredondados para reaproveitar o cache entre frames
        const val CACHE_LIMIT = 512
        const val BLUR_STEP = 4    // raio de blur (px) a partir do qual o sprite é borrado em resolução reduzida
        const val SIGMA_PER_RADIUS = 0.94

        /** Cobertura (0..1) de uma elipse dentro de um retângulo, com 4x4 amostras por pixel. */
        fun ellipseCoverage(w: Int, h: Int, ex: Double, ey: Double, ew: Double, eh: Double): FloatArray {
            val out = FloatArray(w * h)
            val rx = ew / 2.0
            val ry = eh / 2.0
            val cx = ex + rx
            val cy = ey + ry
            val n = 4
            for (y in 0 until h) {
                for (x in 0 until w) {
                    var inside = 0
                    for (sy in 0 until n) {
                        val dy = (y + (sy + 0.5) / n - cy) / ry
                        for (sx in 0 until n) {
                            val dx = (x + (sx + 0.5) / n - cx) / rx
                            if (dx * dx + dy * dy <= 1.0) inside++
                        }
                    }
                    out[y * w + x] = inside / (n * n).toFloat()
                }
            }
            return out
        }

        /** Desfoque gaussiano separável; fora da imagem conta como transparente. */
        fun gaussianBlur(a: FloatArray, w: Int, h: Int, radius: Int) {
            val sigma = SIGMA_PER_RADIUS * radius
            val reach = ceil(3.0 * sigma).toInt().coerceAtLeast(1)
            val kernel = FloatArray(2 * reach + 1) { i ->
                val d = (i - reach).toDouble()
                exp(-(d * d) / (2.0 * sigma * sigma)).toFloat()
            }
            val total = kernel.sum()
            for (i in kernel.indices) kernel[i] /= total

            val tmp = FloatArray(a.size)
            for (y in 0 until h) {
                for (x in 0 until w) {
                    var sum = 0f
                    for (i in -reach..reach) {
                        val sx = x + i
                        if (sx in 0 until w) sum += a[y * w + sx] * kernel[i + reach]
                    }
                    tmp[y * w + x] = sum
                }
            }
            for (y in 0 until h) {
                for (x in 0 until w) {
                    var sum = 0f
                    for (i in -reach..reach) {
                        val sy = y + i
                        if (sy in 0 until h) sum += tmp[sy * w + x] * kernel[i + reach]
                    }
                    a[y * w + x] = sum
                }
            }
        }
    }
}
