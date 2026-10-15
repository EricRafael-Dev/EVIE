package com.evie.eyes.behaviors

import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Spring
import com.evie.eyes.core.clamp
import com.evie.eyes.model.EyeParams
import kotlin.math.abs
import kotlin.math.hypot

const val STRETCH_PER_SPEED = 0.008 // deformação por unidade de velocidade do olhar (1/s)
const val STRETCH_MAX = 0.12
const val SCAN_SPEED = 0.32         // no modo varredura as molas do olhar ficam ~3x mais lentas
val SCAN_HOLD = Pair(1.2, 2.0)      // segundos olhando para cada lado na varredura

/** Sacadas: olhadas rápidas para pontos aleatórios, com pequena assimetria entre os olhos. */
class SaccadeLayer(
    private val rng: PyRandom,
    private val hold: Pair<Double, Double> = Pair(0.5, 3.0),
    private val rangeX: Double = 0.8,
    private val rangeY: Double = 0.5,
    private val centerBias: Double = 0.35,
    var onShift: ((Double) -> Unit)? = null,
) : Layer {
    var enabled = true
    var activity = 1.0 // >1 muda o olhar com mais frequência

    private var timer = rng.uniform(hold.first, hold.second)
    private var tx = 0.0
    private var ty = 0.0

    // O olho direito é um pouco mais lento: vira um "atraso" orgânico.
    private val left = Pair(Spring(frequency = 7.0, damping = 0.75), Spring(frequency = 7.0, damping = 0.75))
    private val right = Pair(Spring(frequency = 6.4, damping = 0.78), Spring(frequency = 6.4, damping = 0.78))
    private var scanning = false

    /** Modo desconfiado: o olhar varre devagar de um lado para o outro. */
    var scan: Boolean
        get() = scanning
        set(value) {
            if (value == scanning) return
            scanning = value
            val slow = if (value) SCAN_SPEED else 1.0
            for ((springs, freq) in listOf(left to 7.0, right to 6.4)) {
                springs.first.frequency = freq * slow
                springs.second.frequency = freq * slow
            }
            if (value) timer = minOf(timer, 0.3)
        }

    /** Frequência atual da mola horizontal do olho esquerdo (para testes de paridade). */
    val leftFrequency: Double get() = left.first.frequency

    fun lookAt(x: Double, y: Double, hold: Double = 2.0) {
        setTarget(clamp(x, -1.0, 1.0), clamp(y, -1.0, 1.0))
        timer = hold
    }

    private fun setTarget(x: Double, y: Double) {
        val dist = hypot(x - tx, y - ty)
        tx = x
        ty = y
        onShift?.invoke(dist)
    }

    private fun pick() {
        if (scanning) {
            val side = if (tx > 0.0) -1.0 else if (tx < 0.0) 1.0 else rng.choice(listOf(-1.0, 1.0))
            setTarget(side * rng.uniform(0.45, 0.7), rng.uniform(-0.05, 0.1))
            timer = rng.uniform(SCAN_HOLD.first, SCAN_HOLD.second)
            return
        }
        val x: Double
        val y: Double
        if (rng.random() < centerBias) {
            x = rng.gauss(0.0, 0.08)
            y = rng.gauss(0.0, 0.06)
        } else {
            x = clamp(rng.gauss(0.0, 0.5), -rangeX, rangeX)
            y = clamp(rng.gauss(0.0, 0.3), -rangeY, rangeY)
        }
        setTarget(x, y)
        timer = rng.uniform(hold.first, hold.second) / maxOf(activity, 0.1)
    }

    override fun update(dt: Double) {
        val targetX: Double
        val targetY: Double
        if (enabled) {
            timer -= dt
            if (timer <= 0.0) pick()
            targetX = tx
            targetY = ty
        } else {
            targetX = 0.0
            targetY = 0.0
        }
        for ((sx, sy) in listOf(left, right)) {
            sx.target = targetX
            sy.target = targetY
            sx.update(dt)
            sy.update(dt)
        }
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        for ((eye, springs) in listOf(left to this.left, right to this.right)) {
            val (sx, sy) = springs
            eye.x += sx.value
            eye.y += sy.value
            // Stretch na direção do movimento, preservando o "volume" no outro eixo.
            val stretchX = minOf(abs(sx.velocity) * STRETCH_PER_SPEED, STRETCH_MAX)
            val stretchY = minOf(abs(sy.velocity) * STRETCH_PER_SPEED, STRETCH_MAX)
            eye.w *= 1.0 + stretchX - 0.5 * stretchY
            eye.h *= 1.0 + stretchY - 0.5 * stretchX
        }
    }
}
