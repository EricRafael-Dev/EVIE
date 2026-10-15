package com.evie.eyes.render

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import com.evie.eyes.Face
import com.evie.eyes.effects.Particle
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Presets
import com.evie.eyes.model.Rgb
import com.evie.eyes.states.IdleConfig
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

private val BG = intArrayOf(4, 6, 8)

/** Face sem camadas automáticas, já na pose final da expressão (para imagens determinísticas). */
private fun staticFace(expression: String): Face {
    val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
    face.setExpression(expression)
    face.snap()
    face.saccade.enabled = false
    face.drift.enabled = false
    face.breathing.enabled = false
    face.blink.enabled = false
    face.tremble.enabled = false
    face.hop.enabled = false
    face.glyph.enabled = false
    face.update(0.0)
    return face
}

private fun Bitmap.sum(x: Int, y: Int): Int {
    val c = getPixel(x, y)
    return Color.red(c) + Color.green(c) + Color.blue(c)
}

private fun Bitmap.minChannel(x: Int, y: Int): Int {
    val c = getPixel(x, y)
    return minOf(Color.red(c), Color.green(c), Color.blue(c))
}

private fun moved(eyes: List<EyeParams>, x: Double) = eyes.map { it.copy().also { e -> e.x = x } }

/** Gráficos nativos do Robolectric: o Skia real desenha os Bitmaps, como no aparelho. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class RenderTest {
    private fun renderer(quality: RenderQuality = RenderQuality.HIGH) = FaceRenderer(480, 320, quality = quality)

    private fun litRows(bitmap: Bitmap, x: Int, threshold: Int = 300) = (0 until bitmap.height).filter { bitmap.sum(x, it) > threshold }

    // --- olhos básicos --------------------------------------------------------------

    @Test
    fun neutralDrawsTwoSeparatedEyes() {
        val frame = renderer().render(staticFace("neutral").eyes)
        val cols = (0 until frame.width).filter { frame.sum(it, 160) > 300 }
        assertTrue(cols.isNotEmpty())
        val gap = cols.zipWithNext { a, b -> b - a }.max()
        assertTrue("espaço entre os olhos: $gap", gap > 40)
        assertTrue(Math.abs((cols.first() + cols.last()) / 2.0 - 240) < 3) // centralizado
    }

    @Test
    fun asleepIsThinAndHappyHasCurvedTopAndBottom() {
        val r = renderer()
        val asleep = r.render(staticFace("asleep").eyes)
        val rows = litRows(asleep, 150)
        assertTrue("linhas acesas: ${rows.size}", rows.size in 1..11)

        val happy = renderer().render(staticFace("happy").eyes)
        // Só conta pixels da cor do olho (ciano), não o blush rosa abaixo dele.
        fun isEye(x: Int, y: Int): Boolean {
            val c = happy.getPixel(x, y)
            return Color.green(c) > 150 && Color.green(c) > Color.red(c)
        }
        val center = (0 until 320).filter { isEye(150, it) }
        val side = (0 until 320).filter { isEye(102, it) }
        assertTrue(center.isNotEmpty() && side.isNotEmpty())
        assertTrue("cúpula: topo do centro ${center.min()} < lateral ${side.min()}", center.min() < side.min())
        assertTrue("base recortada: ${center.max()} < ${side.max()}", center.max() < side.max())
    }

    @Test
    fun blinkClosesEyePixels() {
        val face = staticFace("neutral")
        val r = renderer()
        val openPx = litRows(r.render(face.eyes), 150).size
        face.blink.enabled = true
        face.blink.trigger()
        face.update(0.09)
        val closedPx = litRows(renderer().render(face.eyes), 150).size
        assertTrue("$closedPx < 0.3 * $openPx", closedPx < openPx * 0.3)
    }

    // --- reflexo, volume e brilho --------------------------------------------------------------

    @Test
    fun highlightShowsOnOpenEyesOnly() {
        val neutral = renderer().render(staticFace("neutral").eyes)
        assertTrue("reflexo claro no canto superior esquerdo", neutral.minChannel(128, 133) > 170)
        for (name in listOf("happy", "asleep")) {
            val frame = renderer().render(staticFace(name).eyes)
            val white = (96 until 202 step 2).maxOf { x -> (102 until 218 step 2).maxOf { y -> frame.minChannel(x, y) } }
            assertTrue("$name: máximo de branco $white", white < 150)
        }
    }

    @Test
    fun shadeDarkensBottomOfEye() {
        val frame = renderer().render(staticFace("neutral").eyes)
        assertTrue(frame.sum(175, 110) > frame.sum(175, 210) * 1.15)
    }

    @Test
    fun glowIsPerEye() {
        val face = staticFace("neutral")
        val (left, right) = face.eyes
        left.glow = 0.0
        right.glow = 1.0
        left.highlight = 0.0
        right.highlight = 0.0
        val frame = renderer(RenderQuality.LOW).render(listOf(left, right)) // "low" não tem vinheta
        // Logo fora de cada olho (4 px da borda): o halo da direita acende, o da esquerda (glow 0) não.
        val haloLeft = frame.sum(92, 160)
        val haloRight = frame.sum(388, 160)
        assertTrue("fundo puro: $haloLeft", haloLeft <= BG.sum() + 2)
        assertTrue("$haloRight > $haloLeft + 25", haloRight > haloLeft + 25)
    }

    // --- qualidade, vinheta, bloom, rastro -------------------------------------------------------

    @Test
    fun defaultCyanIsDarkerThanTheOldOne() {
        val old = 90.0 + 235.0 + 215.0
        val ratio = (EyeParams().color.r + EyeParams().color.g + EyeParams().color.b) / old
        assertTrue(ratio > 0.8 && ratio < 0.92)
    }

    @Test
    fun everyQualityRendersTheRightSize() {
        for (q in RenderQuality.values()) {
            val frame = FaceRenderer(200, 120, quality = q).render(staticFace("love").eyes)
            assertEquals(200, frame.width)
            assertEquals(120, frame.height)
        }
        assertEquals(RenderQuality.MEDIUM, RenderQuality.LOW.next())
        assertEquals(RenderQuality.LOW, RenderQuality.HIGH.next())
        assertEquals(RenderQuality.HIGH, RenderQuality.fromName("High"))
    }

    @Test
    fun backgroundIsTintedWithTheEmotionColor() {
        val neutral = renderer().render(staticFace("neutral").eyes).getPixel(240, 160)
        val love = renderer().render(staticFace("love").eyes).getPixel(240, 160)
        assertTrue(Color.green(neutral) > Color.red(neutral) + 8) // ciano
        assertTrue(Color.red(love) > Color.green(love) + 8)       // rosa
    }

    @Test
    fun tintStaysSubtleAndFadesTowardTheCorners() {
        val frame = renderer().render(staticFace("neutral").eyes)
        assertTrue(frame.sum(3, 3) <= BG.sum() + 8)
        val near = frame.getPixel(240, 40)
        assertTrue(maxOf(Color.red(near), Color.green(near), Color.blue(near)) < 70)
    }

    @Test
    fun lowHasNoVignetteAndHighHasAWiderAura() {
        val eyes = staticFace("neutral").eyes
        val low = renderer(RenderQuality.LOW).render(eyes).sum(240, 40)
        val medium = renderer(RenderQuality.MEDIUM).render(eyes)
        val high = renderer(RenderQuality.HIGH).render(eyes)
        assertTrue("low=$low", low <= BG.sum() + 8)
        assertTrue(medium.sum(240, 40) > low + 6)
        // A camada larga do "high" alcança bem longe dos olhos; o "low" não tem esse halo.
        assertTrue(high.sum(30, 160) > renderer(RenderQuality.LOW).render(eyes).sum(30, 160) + 10)
    }

    @Test
    fun fastGazeLeavesAFadingTrail() {
        val eyes = staticFace("neutral").eyes
        val r = renderer()
        r.render(eyes)
        val trailing = r.render(moved(eyes, 0.5)).sum(105, 160)
        val clean = renderer().render(moved(eyes, 0.5)).sum(105, 160)
        assertTrue("rastro: $trailing > $clean + 60", trailing > clean + 60)
        var settled = 0
        repeat(6) { settled = r.render(moved(eyes, 0.5)).sum(105, 160) }
        assertTrue(settled <= clean + 3)
    }

    @Test
    fun noTrailWhenStillOrSlowOrJumping() {
        val eyes = staticFace("neutral").eyes
        val spot = 105 to 160
        fun at(x: Double) = renderer().render(moved(eyes, x)).sum(spot.first, spot.second)

        val still = renderer()
        still.render(moved(eyes, 0.5))
        assertEquals(at(0.5), still.render(moved(eyes, 0.5)).sum(spot.first, spot.second))

        val slow = renderer()
        slow.render(moved(eyes, 0.45))
        assertTrue(slow.render(moved(eyes, 0.5)).sum(spot.first, spot.second) <= at(0.5) + 3)

        val jump = renderer()
        jump.render(eyes)
        assertEquals(at(1.5), jump.render(moved(eyes, 1.5)).sum(spot.first, spot.second))
    }

    @Test
    fun trailOnlyInHighQuality() {
        val eyes = staticFace("neutral").eyes
        val medium = renderer(RenderQuality.MEDIUM)
        medium.render(eyes)
        val clean = renderer(RenderQuality.MEDIUM).render(moved(eyes, 0.5)).sum(105, 160)
        assertEquals(clean, medium.render(moved(eyes, 0.5)).sum(105, 160))
    }

    // --- efeitos de emoção -------------------------------------------------------------------------

    @Test
    fun happyHasPinkBlushUnderTheEyes() {
        val c = renderer().render(staticFace("happy").eyes).getPixel(138, 205)
        assertTrue(Color.red(c) > Color.green(c) + 60 && Color.red(c) > 120)
    }

    @Test
    fun sadEyesHaveAWaterline() {
        val wet = staticFace("sad")
        val dry = staticFace("sad")
        dry.eyes.forEach { it.wet = 0.0 }
        val x = 149
        val y = 208
        assertTrue(renderer().render(wet.eyes).sum(x, y) > renderer().render(dry.eyes).sum(x, y) + 30)
    }

    @Test
    fun everyParticleKindRenders() {
        for (kind in listOf("tear", "zzz", "sparkle", "anger", "ring", "exclaim", "heart")) {
            val p = Particle(kind, 0.5, 0.15, size = 0.3, life = 1.0, age = 0.5, fadeIn = 0.0, fadeOut = 0.0)
            val frame = renderer().render(staticFace("neutral").eyes, listOf(p))
            val best = (180 until 300 step 2).maxOf { x -> (0 until 110 step 2).maxOf { y -> frame.sum(x, y) } }
            assertTrue("$kind: $best", best > 300)
        }
    }

    @Test
    fun frontParticlesDrawOverAndBackParticlesHideBehindEyes() {
        val face = staticFace("neutral")
        face.eyes.forEach { it.highlight = 0.0 }
        val tear = Particle("tear", 0.5, 0.5, size = 0.1, life = 1.0, color = Rgb(150.0, 205.0, 255.0), fadeIn = 0.0)
        assertTrue(Color.blue(renderer().render(face.eyes, listOf(tear)).getPixel(240, 160)) > 200)

        val plain = renderer().render(face.eyes).getPixel(149, 160)
        val ring = Particle("ring", 0.31, 0.5, size = 0.2, life = 1.0, color = Rgb(255.0, 0.0, 0.0), layer = "back", fadeIn = 0.0)
        assertEquals(plain, renderer().render(face.eyes, listOf(ring)).getPixel(149, 160)) // atrás do olho esquerdo
    }

    // --- olhos-símbolo -----------------------------------------------------------------------------------

    @Test
    fun heartEyesArePinkHeartsWithEmptyCorners() {
        val frame = renderer().render(staticFace("love").eyes)
        val center = frame.getPixel(149, 150)
        assertTrue(Color.red(center) > 200 && Color.red(center) > Color.green(center) + 60)
        assertTrue(frame.sum(149, 106) < 200 && frame.sum(99, 214) < 150)
    }

    @Test
    fun starEyesAreYellowStarsWithEmptyCorners() {
        val frame = renderer().render(staticFace("excited").eyes)
        val c = frame.getPixel(149, 165)
        assertTrue(Color.red(c) > 200 && Color.green(c) > 180 && Color.blue(c) < Color.green(c) - 30)
        assertTrue(frame.sum(100, 110) < 150 && frame.sum(198, 214) < 150)
    }

    @Test
    fun closedGlyphEyeCollapsesToAThinLine() {
        val face = staticFace("excited")
        face.eyes.forEach { it.h = 0.05 }
        val rows = litRows(renderer().render(face.eyes), 149)
        assertTrue("linhas: ${rows.size}", rows.size in 1..13)
    }

    @Test
    fun glyphHighlightStaysInsideTheShape() {
        val plain = staticFace("love")
        plain.eyes.forEach { it.highlight = 0.0 }
        val withSpot = renderer().render(staticFace("love").eyes)
        val without = renderer().render(plain.eyes)
        for ((x, y) in listOf(99 to 105, 101 to 108, 198 to 106)) {
            assertTrue("($x,$y)", withSpot.sum(x, y) <= without.sum(x, y) + 6)
        }
    }

    // --- visual -------------------------------------------------------------------------------------------

    /** Com -Devie.outputDir=..., grava a folha de contato (mesma disposição do snapshot.py) para inspeção. */
    @Test
    fun writesContactSheetWhenAskedTo() {
        val dir = System.getProperty("evie.outputDir") ?: return
        val names = Presets.loadDefault().keys.toList()
        val w = 480
        val h = 320
        val columns = 3
        val rows = (names.size + columns - 1) / columns
        val sheet = Bitmap.createBitmap(w * columns, h * rows, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(sheet)
        val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(200, 200, 200)
            textSize = 22f
        }
        names.forEachIndexed { i, name ->
            val face = Face(seed = 7, idleConfig = IdleConfig(enabled = false))
            face.update(0.3)
            face.setExpression(name)
            repeat(180) { face.update(1.0 / 120.0) } // ~1,5 s: os efeitos já apareceram
            val frame = FaceRenderer(w, h).render(face.eyes, face.particles)
            canvas.drawBitmap(frame, ((i % columns) * w).toFloat(), ((i / columns) * h).toFloat(), null)
            canvas.drawText(name, ((i % columns) * w + 8).toFloat(), ((i / columns) * h + 24).toFloat(), label)
        }
        File(dir).mkdirs()
        File(dir, "contact-sheet.png").outputStream().use { sheet.compress(Bitmap.CompressFormat.PNG, 100, it) }
        // Um PNG por expressão, sem rótulo, para comparar pixel a pixel com parity/render_reference.py.
        names.forEach { name ->
            val face = Face(seed = 7, idleConfig = IdleConfig(enabled = false))
            face.update(0.3)
            face.setExpression(name)
            repeat(180) { face.update(1.0 / 120.0) }
            val frame = FaceRenderer(w, h).render(face.eyes, face.particles)
            File(dir, "kotlin-$name.png").outputStream().use { frame.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        assertNotEquals(0, sheet.width)
    }
}
