package com.evie.eyes.states

import com.evie.eyes.Face
import com.evie.eyes.ExpressionSource
import com.evie.eyes.core.PyRandom

const val ACTIVE = "active"
const val BORED = "bored"
const val SLEEPY = "sleepy"
const val ASLEEP = "asleep"

/** Tempos (s) desde o último estímulo. */
data class IdleConfig(
    var enabled: Boolean = true,
    var boredAfter: Double = 20.0,   // passa a olhar em volta com mais frequência
    var yawnAfter: Double = 40.0,    // boceja uma vez
    var sleepyAfter: Double = 60.0,  // pálpebras caídas, pisca devagar
    var sleepAfter: Double = 80.0,   // dorme
    var jitter: Double = 0.15,       // variação aleatória (+-) nos tempos acima
) {
    companion object {
        /** Versão acelerada, boa para demonstração e testes. */
        fun fast(factor: Double = 0.2): IdleConfig {
            val base = IdleConfig()
            return base.copy(
                boredAfter = base.boredAfter * factor,
                yawnAfter = base.yawnAfter * factor,
                sleepyAfter = base.sleepyAfter * factor,
                sleepAfter = base.sleepAfter * factor,
            )
        }
    }
}

/** Estado IDLE: vida própria, tédio crescente, bocejo e sono. */
class IdleController(private val face: Face, var config: IdleConfig, private val rng: PyRandom) {
    var stage = ACTIVE
        private set
    var clock = 0.0
        private set

    private var yawned = false
    private var bored = 0.0
    private var yawn = 0.0
    private var sleepy = 0.0
    private var sleep = 0.0

    init {
        rollThresholds()
    }

    private fun rollThresholds() {
        val cfg = config
        val values = listOf(cfg.boredAfter, cfg.yawnAfter, cfg.sleepyAfter, cfg.sleepAfter)
            .map { base -> base * rng.uniform(1.0 - cfg.jitter, 1.0 + cfg.jitter) }
            .sorted()
        bored = values[0]
        yawn = values[1]
        sleepy = values[2]
        sleep = values[3]
    }

    /** Um estímulo chegou: volta ao comportamento normal. */
    fun reset() {
        if (stage == SLEEPY || stage == ASLEEP) {
            face.setExpression("neutral", source = ExpressionSource.IDLE)
        }
        restoreLayers()
        stage = ACTIVE
        clock = 0.0
        yawned = false
        rollThresholds()
    }

    /** Acorda o robô; se estava dormindo, ele se assusta antes de relaxar. */
    fun wake() {
        val wasAsleep = stage == ASLEEP
        reset()
        if (wasAsleep) {
            face.setExpression("surprised", duration = 0.9, source = ExpressionSource.IDLE)
            face.blink.trigger(double = true)
        }
    }

    fun sleepNow() = enter(ASLEEP)

    fun update(dt: Double) {
        if (!config.enabled) return
        // O relógio só corre quando a expressão é "neutral" ou foi o próprio IDLE que a definiu.
        if ((stage == ACTIVE || stage == BORED) && face.expression != "neutral") return
        clock += dt
        if (stage == ACTIVE && clock >= bored) enter(BORED)
        if (stage == BORED && !yawned && clock >= yawn) {
            yawned = true
            face.yawn.trigger()
        }
        if ((stage == ACTIVE || stage == BORED) && clock >= sleepy) enter(SLEEPY)
        if (stage == SLEEPY && clock >= sleep) enter(ASLEEP)
    }

    private fun restoreLayers() {
        face.saccade.enabled = true
        face.saccade.activity = 1.0
        face.blink.enabled = true
        face.blink.rate = 1.0
        face.breathing.resetDefaults()
    }

    private fun enter(newStage: String) {
        restoreLayers()
        stage = newStage
        when (newStage) {
            BORED -> face.saccade.activity = 1.8
            SLEEPY -> {
                face.setExpression("sleepy", source = ExpressionSource.IDLE)
                face.saccade.activity = 0.35
                face.blink.rate = 0.5
                face.breathing.period = 5.5
            }
            ASLEEP -> {
                face.setExpression("asleep", source = ExpressionSource.IDLE)
                face.saccade.enabled = false
                face.blink.enabled = false
                face.breathing.period = 6.5
                face.breathing.amplitude = 0.04
                face.breathing.bob = 0.05
            }
        }
    }
}
