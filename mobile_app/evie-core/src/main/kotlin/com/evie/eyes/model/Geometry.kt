package com.evie.eyes.model

/**
 * Proporções do rosto, em frações da tela (independentes de resolução).
 *
 * Usadas pelo renderer (pixels) e pelos efeitos (que guardam posições normalizadas 0..1).
 */
object Geometry {
    const val EYE_W = 0.22     // largura base do olho / largura da tela
    const val EYE_H = 0.36     // altura base do olho / altura da tela
    const val SPACING = 0.38   // distância entre os centros dos olhos / largura da tela
    const val TRAVEL_X = 0.12  // deslocamento máximo do olhar / largura da tela
    const val TRAVEL_Y = 0.15  // deslocamento máximo do olhar / altura da tela

    /** Centro do olho em coordenadas normalizadas (x: fração da largura, y: fração da altura). */
    fun eyeCenter(p: EyeParams, side: Int): Pair<Double, Double> =
        Pair(0.5 + side * SPACING / 2.0 + p.x * TRAVEL_X, 0.5 + p.y * TRAVEL_Y)
}
