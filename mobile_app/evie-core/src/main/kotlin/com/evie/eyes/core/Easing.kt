package com.evie.eyes.core

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.pow

/** Funções de suavização (t em 0..1 -> 0..1) e utilitários numéricos. */
typealias Easing = (Double) -> Double

fun clamp(x: Double, lo: Double = 0.0, hi: Double = 1.0): Double =
    if (x < lo) lo else if (x > hi) hi else x

fun lerp(a: Double, b: Double, t: Double): Double = a + (b - a) * t

/** `round()` do Python: arredonda metades para o inteiro par (banker's rounding). */
fun pyRound(x: Double): Int = Math.rint(x).toInt()

fun linear(t: Double): Double = clamp(t)

fun easeInQuad(t: Double): Double {
    val c = clamp(t)
    return c * c
}

fun easeOutQuad(t: Double): Double {
    val c = clamp(t)
    return 1.0 - (1.0 - c) * (1.0 - c)
}

fun easeInOutQuad(t: Double): Double {
    val c = clamp(t)
    return if (c < 0.5) 2 * c * c else 1.0 - (-2 * c + 2).pow(2) / 2
}

fun easeInCubic(t: Double): Double = clamp(t).pow(3)

fun easeOutCubic(t: Double): Double = 1.0 - (1.0 - clamp(t)).pow(3)

fun easeInOutCubic(t: Double): Double {
    val c = clamp(t)
    return if (c < 0.5) 4 * c.pow(3) else 1.0 - (-2 * c + 2).pow(3) / 2
}

fun easeInOutSine(t: Double): Double = -(cos(PI * clamp(t)) - 1.0) / 2.0

fun easeOutBack(t: Double): Double {
    val c = clamp(t)
    val c1 = 1.70158
    val c3 = c1 + 1.0
    return 1.0 + c3 * (c - 1.0).pow(3) + c1 * (c - 1.0).pow(2)
}

val EASINGS: Map<String, Easing> = linkedMapOf(
    "linear" to ::linear,
    "ease_in_quad" to ::easeInQuad,
    "ease_out_quad" to ::easeOutQuad,
    "ease_in_out_quad" to ::easeInOutQuad,
    "ease_in_cubic" to ::easeInCubic,
    "ease_out_cubic" to ::easeOutCubic,
    "ease_in_out_cubic" to ::easeInOutCubic,
    "ease_in_out_sine" to ::easeInOutSine,
    "ease_out_back" to ::easeOutBack,
)
