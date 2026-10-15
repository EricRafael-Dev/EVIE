package com.evie.eyes.core

/** Valor [value] no instante [t]; [ease] suaviza o trecho que termina nesta key. */
data class Key(val t: Double, val value: Double, val ease: Easing = ::linear)

/** Keyframes escalares para animações roteirizadas (piscar, bocejo...). */
class Track(keys: Iterable<Key>) {
    val keys: List<Key> = keys.sortedBy { it.t }

    init {
        require(this.keys.isNotEmpty()) { "Track precisa de ao menos uma key" }
    }

    val duration: Double get() = keys.last().t

    fun sample(t: Double): Double {
        if (t <= keys.first().t) return keys.first().value
        if (t >= keys.last().t) return keys.last().value
        for (i in 0 until keys.size - 1) {
            val prev = keys[i]
            val next = keys[i + 1]
            if (t <= next.t) {
                val span = next.t - prev.t
                val u = if (span <= 0.0) 1.0 else (t - prev.t) / span
                return lerp(prev.value, next.value, next.ease(u))
            }
        }
        return keys.last().value
    }

    /** Mesma animação, [factor] vezes mais lenta (>1) ou mais rápida (<1). */
    fun scaled(factor: Double): Track = Track(keys.map { Key(it.t * factor, it.value, it.ease) })

    /** Concatena [other] depois desta track, com um intervalo [gap]. */
    fun then(other: Track, gap: Double = 0.0): Track {
        val offset = duration + gap
        return Track(keys + other.keys.map { Key(it.t + offset, it.value, it.ease) })
    }
}
