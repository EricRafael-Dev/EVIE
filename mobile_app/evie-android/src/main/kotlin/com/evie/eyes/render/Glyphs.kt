package com.evie.eyes.render

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/** Formas de olho em símbolo (coração, estrela), com pontas e curvas arredondadas. */
internal object Glyphs {
    private fun normalize(points: List<Pair<Double, Double>>): List<Pair<Double, Double>> {
        val xs = points.map { it.first }
        val ys = points.map { it.second }
        val cx = (xs.min() + xs.max()) / 2
        val cy = (ys.min() + ys.max()) / 2
        val hx = (xs.max() - xs.min()) / 2
        val hy = (ys.max() - ys.min()) / 2
        return points.map { (x, y) -> Pair((x - cx) / hx, (y - cy) / hy) }
    }

    private fun heart(samples: Int = 48): List<Pair<Double, Double>> = normalize(
        (0 until samples).map { i ->
            val t = 2.0 * PI * i / samples
            val x = 16.0 * sin(t).let { it * it * it }
            val y = -(13.0 * cos(t) - 5.0 * cos(2 * t) - 2.0 * cos(3 * t) - cos(4 * t))
            Pair(x, y)
        },
    )

    private fun star(inner: Double = 0.5): List<Pair<Double, Double>> = normalize(
        (0 until 10).map { k ->
            val a = -PI / 2 + k * PI / 5
            val r = if (k % 2 == 0) 1.0 else inner
            Pair(cos(a) * r, sin(a) * r)
        },
    )

    /** Contornos normalizados para caber em [-1, 1] x [-1, 1] (y para baixo). */
    val UNIT_SHAPES: Map<String, List<Pair<Double, Double>>> = mapOf("heart" to heart(), "star" to star())

    /** Raio de arredondamento (fração do menor lado). */
    private val ROUNDING = mapOf("heart" to 0.05, "star" to 0.08)

    /**
     * Desenha [glyph] preenchendo [rect]. O arredondamento vem de engordar um miolo menor: preenchimento
     * mais um traço de largura 2r com juntas redondas equivale a somar um círculo de raio r ao contorno.
     */
    fun draw(canvas: Canvas, rect: IRect, color: Int, glyph: String, paint: Paint, path: Path) {
        val unit = UNIT_SHAPES.getValue(glyph)
        val r = ROUNDING.getValue(glyph) * min(rect.w, rect.h)
        val hw = max(1.0, rect.w / 2.0 - r)
        val hh = max(1.0, rect.h / 2.0 - r)
        val cx = rect.centerX
        val cy = rect.centerY
        path.reset()
        unit.forEachIndexed { i, (x, y) ->
            val px = (cx + x * hw).toFloat()
            val py = (cy + y * hh).toFloat()
            if (i == 0) path.moveTo(px, py) else path.lineTo(px, py)
        }
        path.close()
        paint.color = color
        paint.style = if (r >= 1.0) Paint.Style.FILL_AND_STROKE else Paint.Style.FILL
        paint.strokeWidth = (2.0 * r).toFloat()
        paint.strokeJoin = Paint.Join.ROUND
        paint.strokeCap = Paint.Cap.ROUND
        canvas.drawPath(path, paint)
        paint.style = Paint.Style.FILL
    }
}
