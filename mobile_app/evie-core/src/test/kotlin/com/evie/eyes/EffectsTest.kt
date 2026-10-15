package com.evie.eyes

import com.evie.eyes.effects.heartbeat
import com.evie.eyes.model.Presets
import com.evie.eyes.states.IdleConfig
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private const val DT = 1.0 / 60.0

private fun Face.run(seconds: Double) = repeat((seconds / DT).toInt()) { update(DT) }

private fun quietFace(expression: String = "neutral"): Face {
    val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
    face.run(0.3)
    if (expression != "neutral") face.setExpression(expression)
    face.saccade.enabled = false
    face.drift.enabled = false
    face.breathing.enabled = false
    face.blink.enabled = false
    return face
}

private fun Face.kinds() = particles.map { it.kind }

class EffectsTest {
    @Test
    fun presetsDeclareKnownEffects() {
        val presets = Presets.loadDefault()
        assertEquals(listOf("tears"), presets.getValue("sad").fx)
        assertEquals(listOf("zzz"), presets.getValue("asleep").fx)
        assertEquals(emptyList(), presets.getValue("neutral").fx)
        assertEquals(listOf("hearts"), presets.getValue("love").fx)
        assertEquals("heart", presets.getValue("love").left.glyph)
        assertEquals("star", presets.getValue("excited").right.glyph)
    }

    @Test
    fun tearsSwellInTheCornerThenFall() {
        val face = quietFace("sad")
        var tear = face.particles.firstOrNull { it.kind == "tear" }
        var guard = 0
        while (tear == null && guard++ < (4 / DT).toInt()) {
            face.update(DT)
            tear = face.particles.firstOrNull { it.kind == "tear" }
        }
        checkNotNull(tear)
        val startY = tear.y
        face.run(tear.hold * 0.8)
        assertEquals(startY, tear.y, 1e-9) // ainda inchando no canto
        face.run(0.5)
        assertTrue(tear.y > startY + 0.05) // caiu
    }

    @Test
    fun zzzRiseWhileAsleep() {
        val face = quietFace()
        face.idle.sleepNow()
        face.run(1.0)
        val z = face.particles.first { it.kind == "zzz" }
        val y0 = z.y
        face.run(0.5)
        assertTrue(z.y < y0)
    }

    @Test
    fun continuousEffectsStopWhenExpressionChanges() {
        val face = quietFace("sad")
        face.run(3.0)
        face.setExpression("neutral")
        face.run(2.5)
        assertFalse("tear" in face.kinds())
    }

    @Test
    fun angerMarkPersistsAndFadesOut() {
        val face = quietFace("angry")
        face.run(3.0)
        assertEquals(1, face.kinds().count { it == "anger" })
        face.setExpression("neutral")
        face.run(0.6)
        assertFalse("anger" in face.kinds())
    }

    @Test
    fun surpriseFiresRingsAndExclamationOnce() {
        val face = quietFace("surprised")
        assertTrue(face.kinds().count { it == "ring" } == 2 && face.kinds().count { it == "exclaim" } == 1)
        face.run(1.5)
        assertTrue("ring" !in face.kinds() && "exclaim" !in face.kinds())
    }

    @Test
    fun winkSparklesNextToClosedEye() {
        val face = quietFace("wink")
        face.run(0.6)
        val sparkles = face.particles.filter { it.kind == "sparkle" }
        assertEquals(2, sparkles.size)
        assertTrue(sparkles.all { it.x > 0.5 })
    }

    @Test
    fun happySparklesKeepComing() {
        val face = quietFace("happy")
        var seen = 0
        repeat((4 / DT).toInt()) {
            val before = face.kinds().count { it == "sparkle" }
            face.update(DT)
            seen += maxOf(0, face.kinds().count { it == "sparkle" } - before)
        }
        assertTrue(seen >= 3)
    }

    @Test
    fun angryEyesTrembleAndNeutralOnesDoNot() {
        fun xRange(face: Face): Double {
            val xs = ArrayList<Double>()
            repeat((1 / DT).toInt()) {
                face.update(DT)
                xs.add(face.eyes[0].x)
            }
            return xs.max() - xs.min()
        }
        assertTrue(xRange(quietFace()) < 1e-6)
        val angry = quietFace("angry")
        angry.run(1.0)
        assertTrue(xRange(angry) > 0.01)
    }

    @Test
    fun heartbeatHasTwoBeatsPerPeriod() {
        // Amostra a partir de -0.1 s para o primeiro pico (em t = 0) não cair na borda.
        val samples = (0 until 850).map { heartbeat((it - 100) / 1000.0) }
        val peaks = (1 until 849).count { samples[it - 1] < samples[it] && samples[it] >= samples[it + 1] && samples[it] > 0.3 }
        assertEquals(2, peaks)
    }

    @Test
    fun happyHopsAfterReopening() {
        val face = quietFace("happy")
        val ys = ArrayList<Double>()
        repeat((1.2 / DT).toInt()) {
            face.update(DT)
            ys.add(face.eyes[0].y)
        }
        assertTrue(ys.min() < -0.15) // pulou acima da posição do preset (-0.05)
        face.run(3.0)
        assertEquals(-0.05, face.eyes[0].y, 0.01)
    }

    @Test
    fun suspiciousScansSideToSideSlowly() {
        val face = quietFace("suspicious")
        face.saccade.enabled = true
        assertTrue(face.saccade.scan)
        val xs = ArrayList<Double>()
        repeat((8 / DT).toInt()) {
            face.update(DT)
            xs.add(face.eyes[0].x)
        }
        assertTrue(xs.min() < -0.3 && xs.max() > 0.3)
        face.setExpression("neutral")
        assertFalse(face.saccade.scan)
        assertEquals(7.0, face.saccade.leftFrequency, 1e-9)
    }

    @Test
    fun glyphSwapIsHiddenInsideABlink() {
        val face = quietFace("love")
        assertTrue(face.expression == "love" && face.blink.blinking)
        var swapped = false
        repeat((1.0 / DT).toInt()) {
            val before = face.eyes.map { it.glyph }
            face.update(DT)
            face.eyes.forEachIndexed { i, eye ->
                if (before[i] != eye.glyph) {
                    swapped = true
                    assertTrue(before[i] == "" && eye.glyph == "heart" && eye.h < 0.15)
                }
            }
        }
        assertTrue(swapped)
        assertTrue(face.eyes.all { it.glyph == "heart" })
    }

    @Test
    fun leavingAndChangingGlyphsAlsoBlinks() {
        val face = quietFace("love")
        face.run(1.0)
        face.setExpression("excited")
        assertTrue(face.blink.blinking)
        face.run(0.6)
        assertTrue(face.eyes.all { it.glyph == "star" })
        face.setExpression("neutral")
        assertTrue(face.blink.blinking)
        face.run(0.6)
        assertTrue(face.eyes.all { it.glyph == "" })
    }

    @Test
    fun heartEyesBeatAndStarEyesTwinkle() {
        val love = quietFace("love")
        love.run(1.0)
        val widths = ArrayList<Double>()
        repeat((2 / DT).toInt()) {
            love.update(DT)
            widths.add(love.eyes[0].w)
        }
        assertTrue(widths.max() / widths.min() > 1.08)

        val star = quietFace("excited")
        star.run(1.0)
        widths.clear()
        repeat((2 / DT).toInt()) {
            star.update(DT)
            widths.add(star.eyes[0].w)
        }
        assertTrue(widths.max() / widths.min() > 1.05)

        val calm = quietFace()
        calm.run(1.0)
        assertTrue(abs(calm.eyes[0].w - 1.0) < 1e-9)
    }

    @Test
    fun loveReleasesFloatingHeartsThatRise() {
        val face = quietFace("love")
        face.run(3.0)
        val hearts = face.particles.filter { it.kind == "heart" }
        assertTrue(hearts.isNotEmpty())
        val y0 = hearts[0].y
        face.run(0.3)
        assertTrue(hearts[0].y < y0)
        face.setExpression("neutral")
        face.run(4.0)
        assertFalse("heart" in face.kinds())
    }

    @Test
    fun excitedSparklesAndHops() {
        val face = quietFace("excited")
        var seen = 0
        val ys = ArrayList<Double>()
        repeat((3 / DT).toInt()) {
            val before = face.kinds().count { it == "sparkle" }
            face.update(DT)
            seen += maxOf(0, face.kinds().count { it == "sparkle" } - before)
            ys.add(face.eyes[0].y)
        }
        assertTrue(seen >= 2)
        assertTrue(ys.min() < -0.1)
    }

    @Test
    fun unknownExpressionIsRejected() {
        assertFailsWith<IllegalArgumentException> { quietFace().setExpression("banana") }
    }
}
