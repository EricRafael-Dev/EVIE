package com.evie.assistant

import android.content.Context
import android.util.AttributeSet

/**
 * HologramSphereView - Substituído pelo novo motor gráfico de Dois Olhos Expressivos
 * (EvieEyesView) a 60 FPS com renderização vetorial, saccades e expressões emocionais.
 */
class HologramSphereView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : EvieEyesView(context, attrs, defStyleAttr) {

    enum class CoreState {
        MUTED,       // Deep sci-fi red / Sleepy
        IDLE,        // Cool cyan / teal neon
        LISTENING,   // High-energy glowing cyan
        SPEAKING     // Electric cyan / emerald dynamic
    }
}
