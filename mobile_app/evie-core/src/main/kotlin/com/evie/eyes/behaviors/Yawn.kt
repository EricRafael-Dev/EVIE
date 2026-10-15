package com.evie.eyes.behaviors

import com.evie.eyes.core.Key
import com.evie.eyes.core.Track
import com.evie.eyes.core.easeInOutSine
import com.evie.eyes.model.EyeParams

val YAWN = Track(
    listOf(
        Key(0.0, 0.0),
        Key(0.8, 1.0, ::easeInOutSine),
        Key(1.8, 1.0),
        Key(2.8, 0.0, ::easeInOutSine),
    ),
)

/** Bocejo: pálpebras descem, olhos se espremem e voltam devagar. */
class YawnLayer(var onFinish: (() -> Unit)? = null) : Layer {
    private var t: Double? = null

    val active: Boolean get() = t != null

    fun trigger() {
        if (t == null) t = 0.0
    }

    override fun update(dt: Double) {
        val current = t ?: return
        val advanced = current + dt
        if (advanced >= YAWN.duration) {
            t = null
            onFinish?.invoke()
        } else {
            t = advanced
        }
    }

    override fun apply(left: EyeParams, right: EyeParams) {
        val time = t ?: return
        val w = YAWN.sample(time)
        for (eye in listOf(left, right)) {
            eye.lidTop += 0.4 * w
            eye.h *= 1.0 - 0.15 * w
            eye.y += 0.06 * w
        }
    }
}
