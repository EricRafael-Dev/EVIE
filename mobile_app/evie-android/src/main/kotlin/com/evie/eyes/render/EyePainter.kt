package com.evie.eyes.render

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RectF
import android.graphics.Shader
import com.evie.eyes.core.clamp
import com.evie.eyes.core.pyRound
import com.evie.eyes.effects.Particle
import com.evie.eyes.model.EyeParams
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

private const val WHITE = Color.WHITE
private const val CORE_MIN = 4              // espessura mínima (px) do miolo do chevron, antes de engordar
private const val CHEVRON_HEIGHT = 0.7      // altura do ^ em relação à altura do olho
private const val CHEVRON_STROKE = 0.2      // espessura do traço em relação à altura do olho
private const val SHADE_ROWS = 64
private const val HIGHLIGHT_OPACITY = 0.72  // opacidade máxima do reflexo (translúcido, deixa a cor do olho aparecer)
private const val HIGHLIGHT_SOFTNESS = 0.45 // quanto da borda do reflexo é esfumaçada
private const val HIGHLIGHT_PARALLAX = 0.08 // deslocamento do reflexo contra o olhar (fração do olho)
private const val HIGHLIGHT_WET_SCALE = 0.3 // reflexo cresce até 30% com o olho marejado
private const val GLYPH_MIN_H = 0.3         // abaixo dessa altura (piscando) o símbolo vira a linha fina
private const val WATERLINE_OPACITY = 0.45
private val BLUSH_COLOR = Color.rgb(255, 110, 160)
private const val BLUSH_OPACITY = 0.75

/** Manchas do reflexo: (centro x, centro y) relativos ao olho, (largura, altura) relativas ao menor lado. */
private val HIGHLIGHT_SPOTS = listOf(
    doubleArrayOf(0.30, 0.27, 0.22, 0.26),
    doubleArrayOf(0.47, 0.45, 0.09, 0.09),
)

/** Nos símbolos o reflexo precisa ficar dentro da forma (o canto do retângulo é vazio). */
private val GLYPH_HIGHLIGHT_SPOTS = mapOf(
    "heart" to listOf(doubleArrayOf(0.30, 0.31, 0.19, 0.21), doubleArrayOf(0.43, 0.43, 0.08, 0.08)),
    "star" to listOf(doubleArrayOf(0.42, 0.40, 0.15, 0.17), doubleArrayOf(0.50, 0.52, 0.07, 0.07)),
)

/** Desenho procedural dos olhos (port de `render/shapes.py`), em um Canvas de Bitmap. */
internal class EyePainter(private val sprites: SoftSprites = SoftSprites()) {
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val multiply = Paint().apply { xfermode = PorterDuffXfermode(PorterDuff.Mode.MULTIPLY) }
    private val shadeShaders = HashMap<Int, LinearGradient>()
    private val path = Path()
    private val notch = Path()
    private val cut = Path()
    private val rectF = RectF()
    private val particlePainter = ParticlePainter()

    fun drawEyes(canvas: Canvas, eyes: List<EyeParams>, layout: Layout, bg: Int, particles: List<Particle>) {
        canvas.drawColor(bg)
        particlePainter.draw(canvas, particles, layout, "back")
        // Blush fica atrás dos olhos: só a parte de baixo aparece, como uma bochecha.
        eyes.forEachIndexed { i, p -> drawBlush(canvas, p, layout, if (i == 0) -1 else 1) }
        val cy = layout.height / 2.0
        eyes.forEachIndexed { i, p ->
            val side = if (i == 0) -1 else 1
            val cx = layout.width / 2.0 + side * layout.spacing / 2.0
            drawEye(canvas, p, cx, cy, layout, side, bg)
        }
        particlePainter.draw(canvas, particles, layout, "front")
    }

    /** Desenha um olho. [side] = -1 (esquerdo) ou +1 (direito); o canto interno fica virado para o centro. */
    private fun drawEye(canvas: Canvas, p: EyeParams, cx0: Double, cy0: Double, layout: Layout, side: Int, bg: Int) {
        val w = max(p.w * layout.eyeW, MIN_PX)
        val h = max(p.h * layout.eyeH, MIN_PX)
        val cx = cx0 + p.x * layout.travelX
        val cy = cy0 + p.y * layout.travelY

        val rect = IRect.centered(pyRound(w), pyRound(h), pyRound(cx), pyRound(cy))
        val color = p.color.toColorInt()
        val radius = (clamp(p.radius) * min(rect.w, rect.h) / 2).toInt()
        val arc = clamp(p.arc)
        // Fechado (piscando), o símbolo vira a linha fina do olho comum.
        val glyph = if (p.glyph.isNotEmpty() && p.h > GLYPH_MIN_H) p.glyph else ""
        when {
            glyph.isNotEmpty() -> Glyphs.draw(canvas, rect, color, glyph, fill, path)
            arc > 0.01 -> drawArcEye(canvas, rect, color, arc, radius)
            else -> {
                fill.style = Paint.Style.FILL
                fill.color = color
                rectF.set(rect.left.toFloat(), rect.top.toFloat(), rect.right.toFloat(), rect.bottom.toFloat())
                canvas.drawRoundRect(rectF, radius.toFloat(), radius.toFloat(), fill)
            }
        }
        // No ^ o traço é fino: gradiente forte deixaria as pontas apagadas.
        drawShade(canvas, rect, p.shade * (1.0 - 0.7 * arc))

        val margin = rect.h
        val topCover = clamp(p.lidTop) * rect.h
        val tilt = p.lidTilt * 0.5 * rect.h
        val inner = rect.top + topCover + tilt // canto voltado para o centro
        val outer = rect.top + topCover - tilt
        // Olho esquerdo (side < 0): o canto interno é o direito.
        val yLeft = if (side < 0) outer else inner
        val yRight = if (side < 0) inner else outer
        val bottomCover = clamp(p.lidBottom) * rect.h
        val visibleBottom = rect.bottom - bottomCover
        drawWaterline(canvas, rect, p, visibleBottom)
        drawHighlight(canvas, rect, p, yLeft, yRight, visibleBottom, GLYPH_HIGHLIGHT_SPOTS[glyph] ?: HIGHLIGHT_SPOTS)

        fill.style = Paint.Style.FILL
        fill.color = bg
        if (topCover > 0.5 || abs(tilt) > 0.5) {
            path.reset()
            path.moveTo((rect.left - 1).toFloat(), (rect.top - margin).toFloat())
            path.lineTo((rect.right + 1).toFloat(), (rect.top - margin).toFloat())
            path.lineTo((rect.right + 1).toFloat(), yRight.toFloat())
            path.lineTo((rect.left - 1).toFloat(), yLeft.toFloat())
            path.close()
            canvas.drawPath(path, fill)
        }
        if (bottomCover > 0.5) {
            val y = pyRound(rect.bottom - bottomCover)
            canvas.drawRect(
                (rect.left - 1).toFloat(), y.toFloat(),
                (rect.left - 1 + rect.w + 2).toFloat(), (y + pyRound(bottomCover + margin)).toFloat(), fill,
            )
        }
    }

    /**
     * Olho feliz (^): dois traços retos que se encontram no topo, com as pontas arredondadas.
     *
     * Com arc = 0 é o retângulo arredondado normal; com arc = 1, um chevron de espessura uniforme.
     * Monta o miolo (região "encolhida" em r) e o engorda de volta com um traço redondo de largura 2r.
     * Coordenadas de pixel (como no pygame) ganham +0,5 para virar coordenadas contínuas do Canvas.
     */
    private fun drawArcEye(canvas: Canvas, rect: IRect, color: Int, arc: Double, radius: Int) {
        val thickness = CHEVRON_STROKE * rect.h
        val r = (1.0 - arc) * radius + arc * max(0.0, (thickness - CORE_MIN) / 2.0)
        val coreT = max(CORE_MIN.toDouble(), thickness - 2.0 * r)
        val margin = pyRound(r)
        val inset = IRect(margin, margin, max(2, rect.w - 2 * margin), max(2, rect.h - 2 * margin))

        // Coordenadas simétricas em torno do centro dos pixels, para as duas pontas ficarem iguais.
        val mid = inset.left + (inset.w - 1) / 2.0
        val halfW = (inset.w - 1) / 2.0
        val top = inset.top
        val spanH = inset.h - 1
        val bottom = inset.bottom - 1

        // O chevron ocupa só parte da altura e fica centralizado no retângulo do olho.
        val squash = arc * (1.0 - CHEVRON_HEIGHT) * spanH / 2.0
        val apexY = top + squash
        val footY = bottom - squash
        val rise = max(1.0, footY - apexY)
        val edgeY = pyRound(apexY + arc * rise)

        // Deslocamentos da borda interna para uma espessura perpendicular `coreT`.
        val slant = hypot(halfW, rise)
        val offsetX = coreT * slant / rise
        val offsetY = coreT * slant / max(1.0, halfW)
        val holeHw = max(1.0, halfW * 1.05 - arc * (halfW * 0.05 + offsetX))
        val holeApex = footY - arc * max(0.0, rise - offsetY)

        path.reset()
        path.addRect(inset.left.toFloat(), inset.top.toFloat(), inset.right.toFloat(), inset.bottom.toFloat(), Path.Direction.CW)

        // Telhado: tudo acima das duas diagonais que sobem até o ápice.
        notch.reset()
        polygon(
            notch,
            (inset.left - 1).toDouble(), -1.0,
            (inset.right + 1).toDouble(), -1.0,
            (inset.right + 1).toDouble(), edgeY.toDouble(),
            pyRound(mid).toDouble(), pyRound(apexY).toDouble(),
            (inset.left - 1).toDouble(), edgeY.toDouble(),
        )
        path.op(notch, Path.Op.DIFFERENCE)

        // Tudo abaixo dos pés do chevron.
        cut.reset()
        cut.addRect(0f, (pyRound(footY) + 1).toFloat(), rect.w.toFloat(), (pyRound(footY) + 1 + rect.h).toFloat(), Path.Direction.CW)
        path.op(cut, Path.Op.DIFFERENCE)

        // Triângulo interno que deixa só o traço.
        notch.reset()
        polygon(
            notch,
            pyRound(mid - holeHw).toDouble(), (pyRound(footY) + 1).toDouble(),
            pyRound(mid).toDouble(), pyRound(holeApex).toDouble(),
            pyRound(mid + holeHw).toDouble(), (pyRound(footY) + 1).toDouble(),
        )
        path.op(notch, Path.Op.DIFFERENCE)

        if (path.isEmpty) return
        val brush = pyRound(r)
        fill.color = color
        fill.style = if (brush >= 1) Paint.Style.FILL_AND_STROKE else Paint.Style.FILL
        fill.strokeWidth = 2f * brush
        fill.strokeJoin = Paint.Join.ROUND
        fill.strokeCap = Paint.Cap.ROUND
        canvas.save()
        canvas.translate(rect.left.toFloat(), rect.top.toFloat())
        canvas.clipRect(0f, 0f, rect.w.toFloat(), rect.h.toFloat())
        canvas.drawPath(path, fill)
        canvas.restore()
        fill.style = Paint.Style.FILL
    }

    /** Polígono com vértices dados em índices de pixel (+0,5 = centro do pixel). */
    private fun polygon(target: Path, vararg xy: Double) {
        var i = 0
        while (i < xy.size) {
            val x = (xy[i] + 0.5).toFloat()
            val y = (xy[i + 1] + 0.5).toFloat()
            if (i == 0) target.moveTo(x, y) else target.lineTo(x, y)
            i += 2
        }
        target.close()
    }

    private fun shadeShader(key: Int): LinearGradient = shadeShaders.getOrPut(key) {
        val colors = IntArray(SHADE_ROWS)
        val positions = FloatArray(SHADE_ROWS)
        for (row in 0 until SHADE_ROWS) {
            val t = row.toDouble() / (SHADE_ROWS - 1)
            val level = pyRound(255.0 * (1.0 - key / 100.0 * t.pow(1.6)))
            colors[row] = Color.rgb(level, level, level)
            positions[row] = (row + 0.5f) / SHADE_ROWS
        }
        LinearGradient(0f, 0f, 0f, 1f, colors, positions, Shader.TileMode.CLAMP)
    }

    /** Gradiente de volume: multiplica o olho por uma rampa vertical (fundo escuro quase não muda). */
    private fun drawShade(canvas: Canvas, rect: IRect, shade: Double) {
        if (shade <= 0.005 || rect.w < 2 || rect.h < 2) return
        multiply.shader = shadeShader(pyRound(clamp(shade) * 100))
        canvas.save()
        canvas.translate(rect.left.toFloat(), rect.top.toFloat())
        canvas.scale(rect.w.toFloat(), rect.h.toFloat())
        canvas.drawRect(0f, 0f, 1f, 1f, multiply)
        canvas.restore()
    }

    /**
     * Reflexo especular: luz fixa no canto superior esquerdo, com leve paralaxe contra o olhar.
     * [yLeft]/[yRight] = altura da borda da pálpebra superior nas laterais do olho; o reflexo desce
     * para ficar logo abaixo dela, em vez de aparecer cortado.
     */
    private fun drawHighlight(
        canvas: Canvas, rect: IRect, p: EyeParams, yLeft: Double, yRight: Double, visibleBottom: Double,
        spotDefs: List<DoubleArray>,
    ) {
        val openness = clamp((p.h - 0.25) / 0.35)
        var strength = clamp(p.highlight) * openness * (1.0 - clamp(p.arc * 2.0))
        if (strength < 0.02) return
        val size = min(rect.w, rect.h) * (1.0 + HIGHLIGHT_WET_SCALE * clamp(p.wet))
        val shiftX = -p.x * HIGHLIGHT_PARALLAX * rect.w
        val shiftY = -p.y * HIGHLIGHT_PARALLAX * rect.h
        val spots = spotDefs.map { (fx, fy, fw, fh) ->
            IRect.centered(
                max(1, pyRound(fw * size)), max(1, pyRound(fh * size)),
                pyRound(rect.left + fx * rect.w + shiftX), pyRound(rect.top + fy * rect.h + shiftY),
            )
        }

        fun lidY(x: Double): Double {
            val u = (x - rect.left) / max(rect.w, 1)
            return yLeft + (yRight - yLeft) * u
        }

        val main = spots[0]
        val pad = 0.05 * size
        val drop = max(0.0, max(lidY(main.left.toDouble()), lidY(main.right.toDouble())) + pad - main.top)
        val room = visibleBottom - (main.bottom + drop)
        strength *= clamp(room / (0.15 * size))
        if (strength < 0.02) return

        canvas.save()
        canvas.clipRect(rect.left.toFloat(), rect.top.toFloat(), rect.right.toFloat(), rect.bottom.toFloat())
        for (spot in spots) {
            sprites.blit(
                canvas, spot.centerX.toDouble(), spot.centerY + drop, spot.w.toDouble(), spot.h.toDouble(),
                WHITE, HIGHLIGHT_OPACITY * strength, HIGHLIGHT_SOFTNESS,
            )
        }
        canvas.restore()
    }

    /** Olho marejado: uma faixa clara e difusa logo acima da borda de baixo. */
    private fun drawWaterline(canvas: Canvas, rect: IRect, p: EyeParams, visibleBottom: Double) {
        val wet = clamp(p.wet) * clamp((p.h - 0.25) / 0.35) * (1.0 - clamp(p.arc * 2.0))
        if (wet < 0.02) return
        canvas.save()
        canvas.clipRect(rect.left.toFloat(), rect.top.toFloat(), rect.right.toFloat(), rect.bottom.toFloat())
        sprites.blit(
            canvas, rect.centerX.toDouble(), visibleBottom - 0.14 * rect.h, 0.62 * rect.w, 0.09 * rect.h,
            WHITE, WATERLINE_OPACITY * wet, 0.6,
        )
        canvas.restore()
    }

    /** Bochecha rosada logo abaixo do olho, um pouco para fora. */
    private fun drawBlush(canvas: Canvas, p: EyeParams, layout: Layout, side: Int) {
        val blush = clamp(p.blush)
        if (blush < 0.02) return
        val (cx, cy) = layout.eyeCenter(p, side)
        sprites.blit(
            canvas, cx + side * 0.1 * layout.eyeW, cy + 0.42 * layout.eyeH, 0.7 * layout.eyeW, 0.22 * layout.eyeH,
            BLUSH_COLOR, BLUSH_OPACITY * blush, 0.7,
        )
    }

    private companion object {
        const val MIN_PX = 2.0
    }
}
