package com.evie.eyes.behaviors

import com.evie.eyes.core.Noise1D
import com.evie.eyes.core.PyRandom
import com.evie.eyes.model.EyeParams
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

const val DEFAULT_PERIOD = 4.0
const val DEFAULT_AMPLITUDE = 0.02
const val DEFAULT_BOB = 0.01
const val GLOW_PULSE = 8.0 // o brilho pulsa GLOW_PULSE vezes mais que a escala (respiração "acesa")

/** Respiração: escala + leve vaivém vertical + brilho pulsando. */
class BreathingLayer(rng: PyRandom) : Layer {
    var enabled = true
    var period = DEFAULT_PERIOD
    var amplitude = DEFAULT_AMPLITUDE // escala do olho (+-)
    var bob = DEFAULT_BOB             // deslocamento vertical (+-)

    private var amp = amplitude
    private var bobNow = bob
    private var phase = rng.uniform(0.0, 2.0 * PI)
    private val noise = Noise1D(rng.randRange(1 shl 30).toLong())
    private var time = 0.0

    fun resetDefaults() {
        period = DEFAULT_PERIOD
        amplitude = DEFAULT_AMPLITUDE
        bob = DEFAULT_BOB
    }

    override fun update(dt: Double) {
        time += dt
        // Período varia lentamente: a respiração nunca fica perfeitamente periódica.
        val currentPeriod = period * (1.0 + 0.12 * noise(time * 0.15))
        phase += dt / maxOf(currentPeriod, 0.1) * 2.0 * PI
        val k = 1.0 - exp(-2.0 * dt) // suaviza trocas de amplitude
        amp += (amplitude - amp) * k
        bobNow += (bob - bobNow) * k
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        if (!enabled) return
        val s = sin(phase)
        for (eye in listOf(left, right)) {
            eye.h *= 1.0 + amp * s
            eye.w *= 1.0 + amp * 0.5 * s
            eye.y += bobNow * s
            eye.glow *= 1.0 + GLOW_PULSE * amp * s
        }
    }
}

/** Micro-movimento contínuo do olhar: evita olhos "mortos". */
class DriftLayer(rng: PyRandom, private val amplitude: Double = 0.025, private val speed: Double = 0.7) : Layer {
    var enabled = true

    private val nx = Noise1D(rng.randRange(1 shl 30).toLong())
    private val ny = Noise1D(rng.randRange(1 shl 30).toLong())
    private var time = rng.uniform(0.0, 100.0)

    override fun update(dt: Double) {
        time += dt
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        if (!enabled) return
        val t = time * speed
        val dx = amplitude * nx.fbm(t)
        val dy = amplitude * ny.fbm(t)
        for (eye in listOf(left, right)) {
            eye.x += dx
            eye.y += dy
        }
    }
}
