package com.evie.eyes.behaviors

import com.evie.eyes.model.EyeParams
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Camada de dança rítmica com olhos felizes (^ ^), trajetória em arco parabólico
 * a 120 BPM e balanço lateral sincronizado.
 *
 * Port fiel do DanceLayer do Python (Mark LV / Astro Bot):
 * - Balanço lateral em onda senoidal (sway)
 * - Trajetória de arco parabólico (arc_curve)
 * - Movimento diferencial em arco para o par de olhos (diff_y e tilt angular)
 * - Squash & stretch sutil e glow reforçado
 */
class DanceLayer(val bpm: Double = 120.0) : Layer {
    var enabled: Boolean = false
    private var time: Double = 0.0
    private var duration: Double = 0.0
    var onFinish: (() -> Unit)? = null

    val isDancing: Boolean get() = enabled && duration > 0.0

    fun trigger(durationSec: Double = 4.5) {
        enabled = true
        time = 0.0
        duration = durationSec
    }

    fun stop() {
        if (enabled) {
            enabled = false
            duration = 0.0
            onFinish?.invoke()
        }
    }

    override fun update(dt: Double) {
        if (!enabled) return
        time += dt
        duration -= dt
        if (duration <= 0.0) {
            stop()
        }
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        if (!enabled) return

        // A 120 BPM temos 2 batidas por segundo (1 batida = 0.5s para cada arco lateral)
        val cycleFreq = (bpm / 120.0) * 1.0  // 1.0 Hz a 120 BPM
        val cyclePhase = time * cycleFreq * 2.0 * PI

        // 1. Balanço lateral do centro do rosto (de um lado para o outro)
        val normX = sin(cyclePhase)
        val sway = normX * 0.36

        // 2. Curva base do arco parabólico
        val arcCurve = 1.0 - normX * normX  // 1.0 no topo central, 0.0 nas pontas
        val centerY = -arcCurve * 0.16 + 0.04

        // 3. Trajetória de ARCO ÚNICO para o par de olhos:
        // Quando vai para a direita (normX > 0):
        // - O olho direito desce pela curvatura do arco (+diff_y)
        // - O olho esquerdo sobe (-diff_y)
        // - Ambos inclinam para o lado que está indo (tilt)
        val diffY = normX * 0.13
        val tilt = -normX * 0.22

        // 4. Deformação squash & stretch sutil no ritmo do arco
        val squash = (arcCurve - 0.45) * 0.07

        // Olho esquerdo
        left.x += sway
        left.y += centerY - diffY   // sobe quando vai para a direita
        left.lidTilt += tilt
        left.lidTop = 0.0
        left.lidBottom = 0.0
        left.w *= 1.0 - squash * 0.6
        left.h *= 1.0 + squash
        left.arc = max(left.arc, 0.95)
        left.glow *= 1.25
        left.blush = min(1.0, left.blush + 0.40)

        // Olho direito
        right.x += sway
        right.y += centerY + diffY  // desce quando vai para a direita
        right.lidTilt += tilt
        right.lidTop = 0.0
        right.lidBottom = 0.0
        right.w *= 1.0 - squash * 0.6
        right.h *= 1.0 + squash
        right.arc = max(right.arc, 0.95)
        right.glow *= 1.25
        right.blush = min(1.0, right.blush + 0.40)
    }
}
