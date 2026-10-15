package com.evie.eyes.core

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.ceil

/**
 * Mola amortecida: basta mudar [target] e o valor se move de forma orgânica.
 *
 * @param frequency frequência natural em Hz (quanto maior, mais rápido).
 * @param damping razão de amortecimento (1 = crítico, < 1 = com overshoot).
 */
class Spring(value: Double = 0.0, var frequency: Double = 4.0, var damping: Double = 0.8) {
    var value: Double = value
    var target: Double = value
    var velocity: Double = 0.0

    fun update(dt: Double): Double {
        if (dt <= 0.0) return value
        val steps = maxOf(1, ceil(dt / MAX_STEP).toInt())
        val h = dt / steps
        val omega = 2.0 * PI * frequency
        val k = omega * omega
        val c = 2.0 * damping * omega
        repeat(steps) {
            velocity += (k * (target - value) - c * velocity) * h
            value += velocity * h
        }
        return value
    }

    /** Teleporta para [newValue] (ou para o alvo atual) sem movimento. */
    fun snap(newValue: Double? = null) {
        if (newValue != null) target = newValue
        value = target
        velocity = 0.0
    }

    fun settled(eps: Double = 1e-3): Boolean = abs(target - value) < eps && abs(velocity) < eps

    private companion object {
        const val MAX_STEP = 1.0 / 240.0 // sub-passos mantêm a integração estável com dt grande
    }
}
