package com.evie.eyes.effects

import com.evie.eyes.core.clamp
import com.evie.eyes.model.Rgb
import kotlin.math.exp

const val MAX_PARTICLES = 64

/**
 * Uma partícula. Posição/velocidade em frações da tela; tamanhos em alturas de olho base.
 *
 * [hold]: segundos parada no lugar enquanto "nasce" (ex.: lágrima inchando no canto do olho).
 * [layer]: "back" desenha atrás dos olhos, "front" na frente.
 */
class Particle(
    val kind: String,
    var x: Double,
    var y: Double,
    var size: Double,
    var life: Double,
    var color: Rgb = Rgb.WHITE,
    var vx: Double = 0.0,
    var vy: Double = 0.0,
    var ay: Double = 0.0,
    var sizeX: Double? = null, // tamanho horizontal em larguras de olho (anéis); null = proporcional
    var angle: Double = 0.0,
    var spin: Double = 0.0,
    var hold: Double = 0.0,
    var fadeIn: Double = 0.1,
    var fadeOut: Double = 0.3,
    var phase: Double = 0.0,
    var layer: String = "front",
    var age: Double = 0.0,
) {
    val alive: Boolean get() = age < life

    val progress: Double get() = if (life > 0) clamp(age / life) else 1.0

    /** 0 -> 1 durante o [hold] (nascimento). */
    val grow: Double get() = if (hold > 0) clamp(age / hold) else 1.0

    val alpha: Double
        get() {
            val fin = if (fadeIn > 0) clamp(age / fadeIn) else 1.0
            val fout = if (fadeOut > 0) clamp((life - age) / fadeOut) else 1.0
            return minOf(fin, fout)
        }

    /** Termina em breve com fade, em vez de sumir de uma vez. */
    fun release(fade: Double = 0.35) {
        fadeOut = fade
        life = minOf(life, age + fade)
    }

    fun update(dt: Double) {
        age += dt
        angle += spin * dt
        if (age <= hold) return
        vy += ay * dt
        x += vx * dt
        y += vy * dt
    }
}

class ParticleSystem(private val limit: Int = MAX_PARTICLES) {
    val items: MutableList<Particle> = ArrayList()

    fun spawn(particle: Particle): Particle {
        if (items.size >= limit) items.removeAt(0)
        items.add(particle)
        return particle
    }

    fun update(dt: Double) {
        for (particle in items) particle.update(dt)
        items.removeAll { !(it.alive && it.y > -0.5 && it.y < 1.5) }
    }

    fun count(kind: String): Int = items.count { it.kind == kind }

    fun clear() = items.clear()
}

/** Pulso duplo "tum-tum" em 0..1, repetindo a cada [period] segundos. */
fun heartbeat(t: Double, period: Double = 0.85): Double {
    var u = t % period
    if (u < 0) u += period // `%` do Python tem o sinal do divisor
    val a = u / 0.05
    val b = (u - 0.2) / 0.05
    return exp(-(a * a)) + 0.6 * exp(-(b * b))
}
