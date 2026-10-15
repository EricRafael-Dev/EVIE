package com.evie.eyes.behaviors

import com.evie.eyes.core.Key
import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Track
import com.evie.eyes.core.easeInQuad
import com.evie.eyes.core.easeOutCubic
import com.evie.eyes.model.EyeParams

val SINGLE_BLINK = Track(
    listOf(
        Key(0.00, 0.0),
        Key(0.07, 1.0, ::easeInQuad),
        Key(0.11, 1.0),
        Key(0.26, 0.0, ::easeOutCubic),
    ),
)
val DOUBLE_BLINK: Track = SINGLE_BLINK.then(SINGLE_BLINK, gap = 0.08)
const val CLOSED_RESIDUE = 0.04 // fração de altura que sobra com o olho "fechado" (linha fina)
const val BLINK_SQUASH = 0.12   // o olho alarga um pouco ao fechar (squash & stretch)

/** Piscar: intervalos aleatórios, piscada dupla e leve defasagem entre os olhos. */
class BlinkLayer(
    private val rng: PyRandom,
    private val interval: Pair<Double, Double> = Pair(2.0, 6.0),
    private val doubleChance: Double = 0.15,
    private val maxEyeDelay: Double = 0.02,
) : Layer {
    var enabled = true
    var rate = 1.0 // >1 pisca mais, <1 pisca menos

    private var track: Track = SINGLE_BLINK
    private var t: Double? = null
    private var delay = 0.0
    private var next = rng.uniform(interval.first, interval.second)

    val blinking: Boolean get() = t != null

    /** Quanto os dois olhos estão fechados (vale o menos fechado), 0..1. */
    val closure: Double
        get() {
            val time = t ?: return 0.0
            return minOf(track.sample(time), track.sample(time - delay))
        }

    fun cancel() {
        t = null
    }

    fun trigger(double: Boolean = false, slow: Boolean = false) {
        val base = if (double) DOUBLE_BLINK else SINGLE_BLINK
        track = if (slow) base.scaled(2.0) else base
        delay = rng.uniform(0.0, maxEyeDelay)
        t = 0.0
    }

    override fun update(dt: Double) {
        t?.let {
            val advanced = it + dt
            t = if (advanced > track.duration + delay) null else advanced
        }
        if (t == null && enabled) {
            next -= dt * maxOf(rate, 0.0)
            if (next <= 0.0) {
                trigger(double = rng.random() < doubleChance)
                next = rng.uniform(interval.first, interval.second)
            }
        }
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        val time = t ?: return
        for ((eye, eyeDelay) in listOf(left to 0.0, right to delay)) {
            val closure = track.sample(time - eyeDelay)
            eye.h *= 1.0 - (1.0 - CLOSED_RESIDUE) * closure
            eye.w *= 1.0 + BLINK_SQUASH * closure
        }
    }
}
