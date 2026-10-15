package com.evie.eyes.core

import kotlin.math.floor

/** Ruído de gradiente 1D com seed; `noise(t)` devolve valores em [-1, 1]. */
class Noise1D(seed: Long = 0L) {
    private val grad = DoubleArray(256)

    init {
        val rng = PyRandom(seed)
        for (i in grad.indices) grad[i] = rng.uniform(-1.0, 1.0)
    }

    operator fun invoke(t: Double): Double {
        val i = floor(t).toInt()
        val f = t - i
        val g0 = grad[i and 255]
        val g1 = grad[(i + 1) and 255]
        val u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
        return lerp(g0 * f, g1 * (f - 1.0), u) * 2.0
    }

    /** Soma de oitavas, normalizada para [-1, 1]. */
    fun fbm(t: Double, octaves: Int = 3): Double {
        var total = 0.0
        var amp = 1.0
        var freq = 1.0
        var norm = 0.0
        repeat(octaves) {
            total += amp * this(t * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        }
        return total / norm
    }
}
