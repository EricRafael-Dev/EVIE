package com.evie.eyes

import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Spring
import com.evie.eyes.core.EASINGS
import com.evie.eyes.core.Noise1D
import com.evie.eyes.core.Key
import com.evie.eyes.core.Track
import com.evie.eyes.core.clamp
import com.evie.eyes.core.pyRound
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Presets
import com.evie.eyes.states.IdleConfig
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

private const val DT = 1.0 / 60.0

private fun Face.run(seconds: Double) = repeat((seconds / DT).toInt()) { update(DT) }

private fun snapshot(face: Face) = face.eyes.map { it.toMap().toString() }

/** Face sem movimentos automáticos (as camadas são desligadas depois de `setExpression`, que as religa). */
private fun quietFace(expression: String = "neutral"): Face {
    val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
    face.run(0.3)
    if (expression != "neutral") face.setExpression(expression)
    face.saccade.enabled = false
    face.drift.enabled = false
    face.breathing.enabled = false
    face.blink.enabled = false
    face.update(0.0) // recompõe os olhos já sem as camadas automáticas
    return face
}

class CoreTest {
    @Test
    fun pythonRandomKnownValues() {
        // Valores conhecidos do Python 3: random.Random(42).random() e random.Random(0).random().
        assertEquals(0.6394267984578837, PyRandom(42).random())
        assertEquals(0.8444218515250481, PyRandom(0).random())
        assertEquals(0.13436424411240122, PyRandom(1).random())
    }

    @Test
    fun easingsHitEndpointsAndClamp() {
        for ((name, fn) in EASINGS) {
            assertTrue(abs(fn(0.0)) < 1e-9, name)
            assertTrue(abs(fn(1.0) - 1.0) < 1e-9, name)
            assertEquals(fn(0.0), fn(-1.0), name)
            assertEquals(fn(1.0), fn(2.0), name)
        }
    }

    @Test
    fun springConverges() {
        val s = Spring(0.0, frequency = 4.0, damping = 0.8)
        s.target = 1.0
        repeat(240) { s.update(1.0 / 120.0) }
        assertTrue(s.settled())
    }

    @Test
    fun underdampedSpringOvershootsCriticalDoesNot() {
        fun peak(damping: Double): Double {
            val s = Spring(0.0, frequency = 4.0, damping = damping)
            s.target = 1.0
            return (0 until 300).maxOf { s.update(1.0 / 120.0) }
        }
        assertTrue(peak(0.4) > 1.05)
        assertTrue(peak(1.0) <= 1.001)
    }

    @Test
    fun springIsStableWithLargeDt() {
        val s = Spring(0.0, frequency = 8.0, damping = 0.7)
        s.target = 1.0
        repeat(60) { s.update(0.1) }
        assertTrue(abs(s.value - 1.0) < 1e-3)
    }

    @Test
    fun noiseIsDeterministicAndBounded() {
        val a = Noise1D(7)
        val b = Noise1D(7)
        for (i in -500 until 500) {
            val t = i * 0.173
            assertEquals(a(t), b(t))
            assertTrue(a(t) in -1.0..1.0)
            assertTrue(a.fbm(t) in -1.0..1.0)
        }
        assertNotEquals(Noise1D(1)(3.3), Noise1D(2)(3.3))
    }

    @Test
    fun trackSamplingThenAndScaled() {
        val track = Track(listOf(Key(0.0, 0.0), Key(1.0, 1.0), Key(2.0, 0.0)))
        assertEquals(0.0, track.sample(-1.0))
        assertEquals(0.5, track.sample(0.5), 1e-12)
        assertEquals(0.0, track.sample(5.0))
        val longer = track.then(track, gap = 0.5)
        assertEquals(4.5, longer.duration)
        assertEquals(1.0, longer.sample(3.5), 1e-12)
        assertEquals(4.0, track.scaled(2.0).duration)
        assertEquals(1.0, clamp(5.0))
    }

    @Test
    fun pyRoundIsBankersRounding() {
        assertEquals(0, pyRound(0.5))
        assertEquals(2, pyRound(1.5))
        assertEquals(2, pyRound(2.5))
        assertEquals(-2, pyRound(-2.5))
        assertEquals(3, pyRound(2.6))
    }
}

class FaceBehaviorTest {
    @Test
    fun presetsLoadAndAreAsymmetricWhereExpected() {
        val presets = Presets.loadDefault()
        val expected = setOf("neutral", "happy", "sad", "angry", "sleepy", "asleep", "surprised", "suspicious", "wink", "love", "excited")
        assertTrue(presets.keys.containsAll(expected))
        assertNotEquals(presets.getValue("suspicious").left.lidTop, presets.getValue("suspicious").right.lidTop)
        assertEquals(0.0, presets.getValue("wink").left.arc)
        assertEquals(1.0, presets.getValue("wink").right.arc)
    }

    @Test
    fun unknownEyeParamRejected() {
        assertFailsWith<IllegalArgumentException> { EyeParams.fromMap(mapOf("bogus" to 1.0)) }
    }

    @Test
    fun invalidYamlAndFxAreRejected() {
        assertFailsWith<IllegalArgumentException> { Presets.load("neutral: {}\nsad:\n  fx: tears\n") }
        assertFailsWith<IllegalArgumentException> { Presets.load("neutral: {}\nweird:\n  glyph: banana\n") }
        assertFailsWith<IllegalArgumentException> { Presets.load("neutral: {}\n\tbad: 1\n") }
        assertFailsWith<IllegalArgumentException> { Presets.load("happy:\n  arc: 1.0\n") } // sem neutral
        val presets = Presets.loadDefault().toMutableMap()
        presets.getValue("sad").fx = listOf("rainbow")
        assertFailsWith<IllegalArgumentException> { Face(presets = presets) }
    }

    @Test
    fun sameSeedSameAnimationDifferentSeedDiffers() {
        val a = Face(seed = 3)
        val b = Face(seed = 3)
        val c = Face(seed = 4)
        for (face in listOf(a, b, c)) face.run(20.0)
        assertEquals(snapshot(a), snapshot(b))
        assertNotEquals(snapshot(a), snapshot(c))
    }

    @Test
    fun blinksHappenAndEyesReopen() {
        val face = Face(seed = 1, idleConfig = IdleConfig(enabled = false))
        face.saccade.enabled = false
        var blinks = 0
        var wasBlinking = false
        var minHeight = Double.MAX_VALUE
        repeat((30.0 / DT).toInt()) {
            face.update(DT)
            minHeight = minOf(minHeight, face.eyes[0].h)
            if (face.blink.blinking && !wasBlinking) blinks++
            wasBlinking = face.blink.blinking
        }
        assertTrue(blinks in 4..20) // intervalo 2-6 s
        assertTrue(minHeight < 0.2)
        assertTrue(face.eyes[0].h > 0.5 || face.blink.blinking)
    }

    @Test
    fun saccadesMoveGazeWithinBounds() {
        val face = Face(seed = 2, idleConfig = IdleConfig(enabled = false))
        val xs = ArrayList<Double>()
        repeat((30.0 / DT).toInt()) {
            face.update(DT)
            xs.add(face.eyes[0].x)
        }
        assertTrue(xs.max() - xs.min() > 0.2)
        assertTrue(xs.all { abs(it) < 1.2 })
    }

    @Test
    fun lookAtAndEyeAsymmetry() {
        val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
        face.lookAt(0.8, -0.4, hold = 100.0)
        face.run(0.15)
        assertNotEquals(face.eyes[0].x, face.eyes[1].x) // o olho direito atrasa um pouco
        face.run(3.0)
        assertEquals(0.8, face.eyes[0].x, 0.1)
        assertEquals(-0.4, face.eyes[0].y, 0.1)
    }

    @Test
    fun timedExpressionRevertsAndUnknownIsRejected() {
        val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
        face.setExpression("happy", duration = 1.0)
        face.run(0.5)
        assertEquals("happy", face.expression)
        face.run(3.0)
        assertEquals("neutral", face.expression)
        assertFailsWith<IllegalArgumentException> { face.setExpression("nope") }
    }

    @Test
    fun colorBlendsTowardPreset() {
        val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
        face.setExpression("angry")
        face.run(3.0)
        assertTrue(face.eyes[0].color.r > 240 && face.eyes[0].color.b < 90)
    }

    @Test
    fun idleEscalatesToSleepAndWakes() {
        val cfg = IdleConfig(boredAfter = 2.0, yawnAfter = 4.0, sleepyAfter = 6.0, sleepAfter = 8.0, jitter = 0.0)
        val face = Face(seed = 0, idleConfig = cfg)
        val stages = HashSet<String>()
        var yawned = false
        repeat((12.0 / DT).toInt()) {
            face.update(DT)
            stages.add(face.idle.stage)
            yawned = yawned || face.yawn.active
        }
        assertTrue(stages.containsAll(listOf("active", "bored", "sleepy", "asleep")))
        assertTrue(yawned)
        assertEquals("asleep", face.expression)
        assertTrue(face.eyes[0].h < 0.25 && !face.blink.enabled)

        face.poke()
        assertTrue(face.idle.stage == "active" && face.expression == "surprised")
        face.run(3.0)
        assertEquals("neutral", face.expression)
        assertTrue(face.blink.enabled && face.saccade.enabled)
    }

    @Test
    fun manualExpressionStopsBoredomClock() {
        val cfg = IdleConfig(boredAfter = 1.0, yawnAfter = 2.0, sleepyAfter = 3.0, sleepAfter = 4.0, jitter = 0.0)
        val face = Face(seed = 0, idleConfig = cfg)
        face.setExpression("happy")
        face.run(10.0)
        assertTrue(face.idle.stage == "active" && face.expression == "happy")
    }

    @Test
    fun lookAtIgnoredWhileAsleep() {
        val face = Face(seed = 0, idleConfig = IdleConfig(enabled = false))
        face.idle.sleepNow()
        face.lookAt(1.0, 1.0)
        assertEquals("asleep", face.idle.stage)
    }

    @Test
    fun shapeChangeIsHiddenInsideABlink() {
        val face = quietFace()
        face.setExpression("happy")
        assertTrue(face.expression == "happy" && face.blink.blinking)
        var swapped = false
        repeat((1.0 / DT).toInt()) {
            val before = face.eyes.map { it.arc }
            face.update(DT)
            face.eyes.forEachIndexed { i, eye ->
                if (before[i] < 0.5 && eye.arc >= 0.5) {
                    swapped = true
                    assertTrue(eye.h < 0.15) // os dois olhos estavam fechados na troca
                }
            }
        }
        assertTrue(swapped)
        assertTrue(face.eyes.all { abs(it.arc - 1.0) < 1e-6 } && !face.blink.blinking)
    }

    @Test
    fun smallShapeChangesMorphWithoutBlink() {
        val face = quietFace()
        face.setExpression("angry")
        assertFalse(face.blink.blinking)
    }

    @Test
    fun snapAppliesPendingShapeImmediately() {
        val face = quietFace()
        face.setExpression("happy")
        face.snap()
        face.update(0.0)
        assertFalse(face.blink.blinking)
        assertTrue(face.eyes.all { abs(it.arc - 1.0) < 1e-6 && abs(it.h - 0.8) < 1e-6 })
    }

    @Test
    fun blinkSquashesEyeWider() {
        val face = quietFace()
        val openWidth = face.eyes[0].w
        face.blinkNow()
        val widths = ArrayList<Double>()
        repeat((0.3 / DT).toInt()) {
            face.update(DT)
            widths.add(face.eyes[0].w)
        }
        assertTrue(widths.max() > openWidth * 1.08)
        face.run(0.3)
        assertEquals(openWidth, face.eyes[0].w, 1e-9)
    }

    @Test
    fun fastGazeStretchesThenRelaxes() {
        val face = quietFace()
        face.saccade.enabled = true
        face.lookAt(0.0, 0.0, hold = 100.0)
        face.run(1.0)
        face.lookAt(0.9, 0.0, hold = 100.0)
        val samples = ArrayList<Pair<Double, Double>>()
        repeat((0.3 / DT).toInt()) {
            face.update(DT)
            samples.add(face.eyes[0].w to face.eyes[0].h)
        }
        assertTrue(samples.maxOf { it.first } > 1.05)
        assertTrue(samples.minOf { it.second } < 0.98)
        face.run(2.0)
        assertEquals(1.0, face.eyes[0].w, 0.01)
    }

    @Test
    fun breathingPulsesGlow() {
        val face = quietFace()
        face.breathing.enabled = true
        val glows = ArrayList<Double>()
        repeat((5.0 / DT).toInt()) {
            face.update(DT)
            glows.add(face.eyes[0].glow)
        }
        assertTrue(glows.max() - glows.min() > 0.1)
    }
}
