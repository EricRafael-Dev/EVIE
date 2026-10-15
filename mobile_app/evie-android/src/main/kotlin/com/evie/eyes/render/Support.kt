package com.evie.eyes.render

import android.graphics.Color
import com.evie.eyes.core.clamp
import com.evie.eyes.model.Geometry
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Rgb

/**
 * Retângulo de inteiros com a mesma semântica do `pygame.Rect` (divisão inteira em `center`),
 * para os arredondamentos de pixel baterem com a versão Python.
 */
internal class IRect(var left: Int, var top: Int, var w: Int, var h: Int) {
    val right: Int get() = left + w
    val bottom: Int get() = top + h
    val centerX: Int get() = left + w / 2
    val centerY: Int get() = top + h / 2

    companion object {
        /** Equivale a criar `Rect(0, 0, w, h)` e atribuir `rect.center = (cx, cy)`. */
        fun centered(w: Int, h: Int, cx: Int, cy: Int) = IRect(cx - w / 2, cy - h / 2, w, h)
    }
}

/** Geometria base em pixels; os parâmetros dos olhos são relativos a ela. */
internal class Layout(val width: Int, val height: Int) {
    val eyeW: Double get() = width * Geometry.EYE_W
    val eyeH: Double get() = height * Geometry.EYE_H

    /** Distância entre os centros dos olhos. */
    val spacing: Double get() = width * Geometry.SPACING
    val travelX: Double get() = width * Geometry.TRAVEL_X
    val travelY: Double get() = height * Geometry.TRAVEL_Y

    fun eyeCenter(p: EyeParams, side: Int): Pair<Double, Double> {
        val (nx, ny) = Geometry.eyeCenter(p, side)
        return Pair(nx * width, ny * height)
    }

    fun scaled(factor: Int) = Layout(width * factor, height * factor)
}

/** Cor do olho como inteiro ARGB opaco (cada canal truncado para 0..255, como `int(clamp(c, 0, 255))`). */
internal fun Rgb.toColorInt(): Int = Color.rgb(
    clamp(r, 0.0, 255.0).toInt(),
    clamp(g, 0.0, 255.0).toInt(),
    clamp(b, 0.0, 255.0).toInt(),
)
