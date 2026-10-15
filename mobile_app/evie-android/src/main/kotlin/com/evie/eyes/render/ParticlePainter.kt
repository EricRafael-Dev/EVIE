package com.evie.eyes.render

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RectF
import com.evie.eyes.core.clamp
import com.evie.eyes.core.easeOutBack
import com.evie.eyes.core.easeOutCubic
import com.evie.eyes.core.pyRound
import com.evie.eyes.effects.Particle
import com.evie.eyes.effects.heartbeat
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * Desenho das partículas de emoção: lágrima, Zzz, brilho ✦, marca de raiva 💢, onda de choque, "!" e coração.
 * Cada partícula é desenhada num layer próprio com a opacidade do grupo (como o `canvas.set_alpha` do pygame).
 */
internal class ParticlePainter {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val replace = Paint(Paint.ANTI_ALIAS_FLAG).apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.SRC) }
    private val path = Path()
    private val glyphPath = Path()
    private val oval = RectF()

    /** Desenha as partículas da camada [layer] ("back" atrás dos olhos, "front" na frente). */
    fun draw(canvas: Canvas, particles: List<Particle>, layout: Layout, layer: String) {
        val unit = layout.eyeH
        for (p in particles) {
            if (p.layer != layer || p.alpha <= 0.0) continue
            val cx = p.x * layout.width
            val cy = p.y * layout.height
            when (p.kind) {
                "ring" -> ring(canvas, p, cx, cy, unit, layout)
                "tear" -> tear(canvas, p, cx, cy, unit)
                "zzz" -> zzz(canvas, p, cx, cy, unit)
                "sparkle" -> sparkle(canvas, p, cx, cy, unit)
                "anger" -> anger(canvas, p, cx, cy, unit)
                "exclaim" -> exclaim(canvas, p, cx, cy, unit)
                "heart" -> heart(canvas, p, cx, cy, unit)
            }
        }
    }

    /**
     * Desenha [block] num layer de [w] x [h] com o centro em ([cx], [cy]) e opacidade [alpha];
     * dentro do bloco as coordenadas são locais ao layer (como numa Surface do pygame).
     */
    private inline fun layer(canvas: Canvas, w: Int, h: Int, cx: Double, cy: Double, alpha: Double, block: () -> Unit) {
        val left = pyRound(cx) - w / 2
        val top = pyRound(cy) - h / 2
        val saved = canvas.saveLayerAlpha(
            left.toFloat(), top.toFloat(), (left + w).toFloat(), (top + h).toFloat(), pyRound(255.0 * clamp(alpha)),
        )
        canvas.translate(left.toFloat(), top.toFloat())
        block()
        canvas.restoreToCount(saved)
    }

    private fun rgb(p: Particle): Int = Color.rgb(
        clamp(p.color.r, 0.0, 255.0).toInt(), clamp(p.color.g, 0.0, 255.0).toInt(), clamp(p.color.b, 0.0, 255.0).toInt(),
    )

    private fun fillPaint(color: Int): Paint {
        paint.style = Paint.Style.FILL
        paint.color = color
        return paint
    }

    /** Linha grossa com juntas e pontas arredondadas. */
    private fun roundPolyline(canvas: Canvas, color: Int, points: List<Pair<Double, Double>>, width: Int) {
        path.reset()
        points.forEachIndexed { i, (x, y) -> if (i == 0) path.moveTo(x.toFloat(), y.toFloat()) else path.lineTo(x.toFloat(), y.toFloat()) }
        paint.style = Paint.Style.STROKE
        paint.color = color
        paint.strokeWidth = width.toFloat()
        paint.strokeCap = Paint.Cap.ROUND
        paint.strokeJoin = Paint.Join.ROUND
        canvas.drawPath(path, paint)
        paint.style = Paint.Style.FILL
    }

    private fun rotate(points: List<Pair<Double, Double>>, angle: Double): List<Pair<Double, Double>> {
        val c = cos(angle)
        val s = sin(angle)
        return points.map { (x, y) -> Pair(x * c - y * s, x * s + y * c) }
    }

    private fun tear(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val r = p.size * unit * (0.35 + 0.65 * p.grow)
        if (r < 1.0) return
        val pad = 2
        val w = pyRound(2 * r) + 2 * pad
        val h = pyRound(3.4 * r) + 2 * pad
        val x = r + pad
        val y = 2.4 * r + pad
        val color = rgb(p)
        // O centro do círculo da gota (0,7r abaixo do centro do layer) fica na posição da partícula.
        layer(canvas, w, h, cx, cy - 0.7 * r, p.alpha) {
            val fill = fillPaint(color)
            canvas.drawCircle(x.toFloat(), y.toFloat(), r.toFloat(), fill)
            path.reset()
            path.moveTo((x - 0.92 * r).toFloat(), (y - 0.38 * r).toFloat())
            path.lineTo(x.toFloat(), (y - 2.3 * r).toFloat())
            path.lineTo((x + 0.92 * r).toFloat(), (y - 0.38 * r).toFloat())
            path.close()
            canvas.drawPath(path, fill)
            // No pygame esse círculo substitui os pixels (alfa 190), em vez de misturar.
            replace.color = Color.argb(190, 255, 255, 255)
            canvas.drawCircle((x - 0.35 * r).toFloat(), (y - 0.15 * r).toFloat(), max(1.0, 0.3 * r).toFloat(), replace)
        }
    }

    private fun zzz(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val s = p.size * unit * (0.7 + 0.6 * p.progress)
        if (s < 2.0) return
        val width = max(2, pyRound(0.2 * s))
        val half = s * 0.8 + width
        val shape = rotate(
            listOf(Pair(-0.5 * s, -0.5 * s), Pair(0.5 * s, -0.5 * s), Pair(-0.5 * s, 0.5 * s), Pair(0.5 * s, 0.5 * s)),
            p.angle,
        )
        val size = pyRound(2 * half)
        val sway = sin(p.age * 2.5 + p.phase) * 0.25 * s
        layer(canvas, size, size, cx + sway, cy, p.alpha) {
            roundPolyline(canvas, rgb(p), shape.map { (x, y) -> Pair(x + half, y + half) }, width)
        }
    }

    private fun sparkle(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val radius = p.size * unit * sin(PI * p.progress) // cresce e some
        if (radius < 1.5) return
        val size = pyRound(2 * radius) + 4
        layer(canvas, size, size, cx, cy, p.alpha) {
            path.reset()
            for (k in 0 until 8) {
                val a = p.angle + k * PI / 4.0 - PI / 2.0
                val rad = if (k % 2 == 0) radius else 0.28 * radius
                val px = (cos(a) * rad + radius + 2).toFloat()
                val py = (sin(a) * rad + radius + 2).toFloat()
                if (k == 0) path.moveTo(px, py) else path.lineTo(px, py)
            }
            path.close()
            canvas.drawPath(path, fillPaint(rgb(p)))
            canvas.drawCircle((radius + 2).toFloat(), (radius + 2).toFloat(), max(1.0, 0.18 * radius).toFloat(), fillPaint(Color.WHITE))
        }
    }

    private fun anger(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val half = 0.5 * p.size * unit * (1.0 + 0.18 * heartbeat(p.age))
        if (half < 2.0) return
        val width = max(2, pyRound(0.36 * half))
        val size = pyRound(2 * half) + 2 * width
        val color = rgb(p)
        layer(canvas, size, size, cx, cy, p.alpha) {
            for (quarter in 0 until 4) {
                val leg = rotate(ANGER_LEG, quarter * PI / 2.0)
                roundPolyline(canvas, color, leg.map { (x, y) -> Pair(x * half + size / 2.0, y * half + size / 2.0) }, width)
            }
        }
    }

    private fun ring(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double, layout: Layout) {
        val grow = 1.0 + 0.45 * easeOutCubic(p.progress)
        val rx = (p.sizeX ?: p.size) * layout.eyeW * grow
        val ry = p.size * layout.eyeH * grow
        val width = max(1, pyRound(0.08 * unit * (1.0 - p.progress)))
        val w = pyRound(2 * rx) + 4
        val h = pyRound(2 * ry) + 4
        layer(canvas, w, h, cx, cy, p.alpha * 0.6) {
            // O pygame desenha o contorno para dentro de (2, 2, w-4, h-4); o traço fica centrado a meia espessura.
            val half = width / 2f
            oval.set(2f + half, 2f + half, (w - 2).toFloat() - half, (h - 2).toFloat() - half)
            paint.style = Paint.Style.STROKE
            paint.color = rgb(p)
            paint.strokeWidth = width.toFloat()
            canvas.drawOval(oval, paint)
            paint.style = Paint.Style.FILL
        }
    }

    private fun exclaim(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val s = p.size * unit * easeOutBack(clamp(p.age / 0.25))
        if (s < 3.0) return
        val w = pyRound(1.2 * s)
        // O pygame gira o layer w x w; aqui o layer é a caixa do quadrado girado.
        val box = ceil(w * (abs(cos(p.angle)) + abs(sin(p.angle)))).toInt() + 2
        layer(canvas, box, box, cx, cy, p.alpha) {
            canvas.translate(box / 2f, box / 2f)
            canvas.rotate(Math.toDegrees(p.angle).toFloat())
            canvas.translate(-w / 2f, -w / 2f)
            val barW = max(1, pyRound(0.26 * s))
            val barH = max(1, pyRound(0.62 * s))
            val barLeft = w / 2 - barW / 2
            val barTop = pyRound(w / 2.0 - 0.2 * s) - barH / 2
            oval.set(barLeft.toFloat(), barTop.toFloat(), (barLeft + barW).toFloat(), (barTop + barH).toFloat())
            val fill = fillPaint(rgb(p))
            canvas.drawRoundRect(oval, (barW / 2).toFloat(), (barW / 2).toFloat(), fill)
            canvas.drawCircle(w / 2f, (w / 2.0 + 0.36 * s).toFloat(), (0.14 * s).toFloat(), fill)
        }
    }

    private fun heart(canvas: Canvas, p: Particle, cx: Double, cy: Double, unit: Double) {
        val s = pyRound(p.size * unit * (0.75 + 0.25 * easeOutBack(clamp(p.age / 0.3))))
        if (s < 3) return
        val sway = sin(p.age * 3.0 + p.phase) * 0.18 * s
        layer(canvas, s + 4, s + 4, cx + sway, cy, p.alpha) {
            Glyphs.draw(canvas, IRect(2, 2, s, s), rgb(p), "heart", paint, glyphPath)
        }
    }

    private companion object {
        /** Uma "perna" da marca de raiva: curva em L com o canto virado para o centro (escala -1..1). */
        val ANGER_LEG: List<Pair<Double, Double>> = (0..10).map { i ->
            val t = i / 10.0
            val u = 1 - t
            Pair(u * u * 0.38 + 2 * u * t * 0.38 + t * t * 1.0, u * u * 1.0 + 2 * u * t * 0.38 + t * t * 0.38)
        }
    }
}
