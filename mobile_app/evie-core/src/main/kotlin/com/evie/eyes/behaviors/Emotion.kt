package com.evie.eyes.behaviors

import com.evie.eyes.core.Noise1D
import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Spring
import com.evie.eyes.effects.heartbeat
import com.evie.eyes.model.EyeParams
import kotlin.math.PI
import kotlin.math.sin

const val TREMBLE_AMP = 0.035   // deslocamento máximo do tremor (unidades de olhar)
const val TREMBLE_SPEED = 18.0  // rapidez do ruído do tremor
const val BEAT_GLOW = 0.6       // quanto o brilho cresce no pico do batimento
const val HOP_VELOCITY = 9.0    // impulso inicial do pulinho (unidades de olhar/s)
const val HEART_PULSE = 0.13    // quanto o coração incha no "tum" do batimento
const val HEART_PERIOD = 1.0    // segundos por batimento duplo
const val STAR_PULSE = 0.07     // amplitude do brilhar da estrela
const val STAR_PERIOD = 1.3

/** Olhos de coração batem como um coração; olhos de estrela cintilam. */
class GlyphPulseLayer : Layer {
    var enabled = true
    private var time = 0.0

    override fun update(dt: Double) {
        time += dt
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        if (!enabled) return
        val beat = heartbeat(time, HEART_PERIOD)
        val twinkle = sin(2.0 * PI * time / STAR_PERIOD)
        for (eye in listOf(left, right)) {
            val scale: Double
            when (eye.glyph) {
                "heart" -> {
                    scale = 1.0 + HEART_PULSE * beat
                    eye.glow *= 1.0 + 0.25 * beat
                }
                "star" -> {
                    scale = 1.0 + STAR_PULSE * twinkle
                    eye.glow *= 1.0 + 0.2 * (0.5 + 0.5 * twinkle)
                }
                else -> continue
            }
            eye.w *= scale
            eye.h *= scale
        }
    }
}

/** Lê `tremble` de cada olho: treme e faz o brilho pulsar como um coração acelerado. */
class TrembleLayer(rng: PyRandom) : Layer {
    var enabled = true
    private val nx = Noise1D(rng.randRange(1 shl 30).toLong())
    private val ny = Noise1D(rng.randRange(1 shl 30).toLong())
    private var time = 0.0

    override fun update(dt: Double) {
        time += dt
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        if (!enabled) return
        val t = time
        val beat = heartbeat(t)
        for (eye in listOf(left, right)) {
            val k = eye.tremble
            if (k <= 0.01) continue
            eye.x += k * TREMBLE_AMP * nx(t * TREMBLE_SPEED)
            eye.y += k * TREMBLE_AMP * ny(t * TREMBLE_SPEED)
            eye.glow *= 1.0 + k * BEAT_GLOW * beat
        }
    }
}

/** Pulinho elástico: [kick] lança os olhos para cima e uma mola traz de volta quicando. */
class HopLayer : Layer {
    var enabled = true
    private val spring = Spring(0.0, frequency = 3.2, damping = 0.35)

    val offset: Double get() = spring.value

    fun kick(strength: Double = 1.0) {
        if (enabled) spring.velocity -= HOP_VELOCITY * strength
    }

    override fun update(dt: Double) {
        spring.update(dt)
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        for (eye in listOf(left, right)) eye.y += spring.value
    }
}
