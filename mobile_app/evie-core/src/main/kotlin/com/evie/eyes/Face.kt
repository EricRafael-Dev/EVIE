package com.evie.eyes

import com.evie.eyes.behaviors.BlinkLayer
import com.evie.eyes.behaviors.BreathingLayer
import com.evie.eyes.behaviors.DanceLayer
import com.evie.eyes.behaviors.DriftLayer
import com.evie.eyes.behaviors.GlyphPulseLayer
import com.evie.eyes.behaviors.HopLayer
import com.evie.eyes.behaviors.Layer
import com.evie.eyes.behaviors.SaccadeLayer
import com.evie.eyes.behaviors.TrembleLayer
import com.evie.eyes.behaviors.YawnLayer
import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Spring
import com.evie.eyes.effects.EmotionFx
import com.evie.eyes.effects.Particle
import com.evie.eyes.effects.validateFx
import com.evie.eyes.model.EyeField
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Preset
import com.evie.eyes.model.Presets
import com.evie.eyes.model.Rgb
import com.evie.eyes.states.IdleConfig
import com.evie.eyes.states.IdleController
import kotlin.math.abs
import kotlin.math.exp

/** Quem pediu a troca de expressão: o usuário (zera o tédio) ou o próprio estado ocioso. */
enum class ExpressionSource { USER, IDLE }

/** (frequência Hz, amortecimento) por parâmetro: valores < 1 geram overshoot suave. */
private val POSE_SPRINGS: Map<EyeField, Pair<Double, Double>> = mapOf(
    EyeField.W to Pair(4.0, 0.7),
    EyeField.H to Pair(4.5, 0.55),
    EyeField.RADIUS to Pair(4.0, 1.0),
    EyeField.X to Pair(5.0, 0.8),
    EyeField.Y to Pair(5.0, 0.8),
    EyeField.LID_TOP to Pair(5.0, 0.7),
    EyeField.LID_TILT to Pair(5.0, 0.7),
    EyeField.LID_BOTTOM to Pair(5.0, 0.7),
    EyeField.ARC to Pair(4.0, 0.75),
    EyeField.GLOW to Pair(3.0, 1.0),
    EyeField.HIGHLIGHT to Pair(4.0, 1.0),
    EyeField.SHADE to Pair(3.0, 1.0),
    EyeField.BLUSH to Pair(2.0, 1.0),
    EyeField.TREMBLE to Pair(3.0, 1.0),
    EyeField.WET to Pair(1.5, 1.0),
)
private const val COLOR_RATE = 6.0       // 1/s, suavização exponencial da cor
private const val BLINK_CUT_ARC = 0.3    // mudança de `arc` acima disso troca a forma escondida num piscar
private const val BLINK_CUT_CLOSURE = 0.9 // quão fechado o olho precisa estar para trocar a forma

/** Dois olhos, molas de pose e camadas procedurais (port fiel da classe `Face` do Python). */
class Face(
    seed: Long? = null,
    val presets: Map<String, Preset> = Presets.loadDefault(),
    idleConfig: IdleConfig? = null,
) {
    val rng = PyRandom(seed)
    var expression = "neutral"
        private set
    var time = 0.0
        private set

    private var revertIn: Double? = null
    private var pending: List<EyeParams>? = null

    private var targets: List<EyeParams> = presetTargets("neutral")
    private var pose: List<EyeParams> = targets.map { it.copy() }
    private val springs: List<Map<EyeField, Spring>> = pose.map { p ->
        EyeField.values().associateWith { field ->
            val (frequency, damping) = POSE_SPRINGS.getValue(field)
            Spring(p[field], frequency, damping)
        }
    }

    val saccade = SaccadeLayer(rng, onShift = { distance -> onSaccade(distance) })
    val drift = DriftLayer(rng)
    val breathing = BreathingLayer(rng)
    val tremble = TrembleLayer(rng)
    val hop = HopLayer()
    val dance = DanceLayer(bpm = 120.0).apply {
        onFinish = {
            blink.trigger()
        }
    }
    val glyph = GlyphPulseLayer()
    val yawn = YawnLayer(onFinish = { blink.trigger(slow = true) })
    val blink = BlinkLayer(rng)

    // O piscar vem por último porque multiplica a altura já composta.
    val layers: List<Layer> = listOf(saccade, drift, breathing, tremble, hop, dance, glyph, yawn, blink)

    val fx: EmotionFx
    val idle: IdleController

    /** Olhos já compostos (pose + camadas), prontos para o renderer: `[esquerdo, direito]`. */
    var eyes: List<EyeParams> = pose.map { it.copy() }
        private set

    init {
        for (preset in presets.values) validateFx(preset.name, preset.fx)
        fx = EmotionFx(this, rng)
        idle = IdleController(this, idleConfig ?: IdleConfig(), rng)
    }

    /** Partículas vivas (lágrimas, Zzz, brilhos...) para passar ao renderer. */
    val particles: List<Particle> get() = fx.particles.items

    // --- API pública -------------------------------------------------------

    /** Troca a expressão base. Com [duration], volta a "neutral" depois. */
    fun setExpression(name: String, duration: Double? = null, source: ExpressionSource = ExpressionSource.USER) {
        require(name in presets) { "Expressão desconhecida '$name'. Disponíveis: ${presets.keys.sorted()}" }
        if (source == ExpressionSource.USER) idle.reset()
        expression = name
        revertIn = duration
        val newTargets = presetTargets(name)

        // Prevenção de mistura de animações: limpa resquícios de estados incompatíveis
        if (newTargets.any { it.arc > 0.05 }) {
            // Olhos felizes em chevron/arco (^ ^): zera pálpebras de tédio ou sono imediatamente
            for (t in newTargets) {
                t.lidTop = 0.0
                t.lidBottom = 0.0
                t.lidTilt = 0.0
            }
            for ((eyeSprings, eyePose) in springs.zip(pose)) {
                eyePose.lidTop = 0.0
                eyePose.lidBottom = 0.0
                eyePose.lidTilt = 0.0
                eyeSprings[EyeField.LID_TOP]?.snap(0.0)
                eyeSprings[EyeField.LID_BOTTOM]?.snap(0.0)
                eyeSprings[EyeField.LID_TILT]?.snap(0.0)
            }
        } else if (newTargets.any { it.lidTop > 0.05 }) {
            // Olhos com pálpebras de sono/tristeza/tédio: zera o arco dos chevrons imediatamente
            for (t in newTargets) {
                t.arc = 0.0
            }
            for ((eyeSprings, eyePose) in springs.zip(pose)) {
                eyePose.arc = 0.0
                eyeSprings[EyeField.ARC]?.snap(0.0)
            }
        }

        // Descarta morph pendente antigo para não sobrepor transições
        pending = null

        val bigChange = newTargets.zip(pose).any { (t, p) -> abs(t.arc - p.arc) > BLINK_CUT_ARC || t.glyph != p.glyph }
        if (bigChange) {
            // Morph de forma grande (ex.: quadrado -> ^ ou -> coração): troca com o olho fechado
            pending = newTargets
            blink.trigger()
        } else {
            targets = newTargets
        }
        fx.onExpression(presets.getValue(name).fx)
    }

    /** Dispara animação de dança rítmica com trajetória em arco a 120 BPM e olhos felizes. */
    fun triggerDance(duration: Double = 4.5) {
        idle.wake()
        setExpression("happy", duration)
        dance.trigger(duration)
        fx.burst("star", 10)
    }

    /** Olha para (x, y) em -1..1 durante [hold] segundos. Ignorado se estiver dormindo. */
    fun lookAt(x: Double, y: Double, hold: Double = 2.0) {
        if (idle.stage == "asleep") return
        idle.reset()
        saccade.lookAt(x, y, hold)
    }

    fun blinkNow(double: Boolean = false) = blink.trigger(double = double)

    /** Estímulo genérico: acorda se estiver dormindo e zera o tédio. */
    fun poke() = idle.wake()

    /** Pula direto para a pose alvo (sem animação). */
    fun snap() {
        pending?.let {
            targets = it
            pending = null
            blink.cancel()
        }
        snapPose()
    }

    fun update(dt: Double) {
        time += dt
        revertIn?.let {
            val remaining = it - dt
            revertIn = remaining
            if (remaining <= 0.0) setExpression("neutral", source = ExpressionSource.IDLE)
        }

        idle.update(dt)
        updatePose(dt)
        for (layer in layers) layer.update(dt)
        pending?.let {
            if (blink.closure >= BLINK_CUT_CLOSURE || !blink.blinking) {
                targets = it
                pending = null
                snapPose()
            }
        }

        val left = pose[0].copy()
        val right = pose[1].copy()
        for (layer in layers) layer.apply(left, right)
        eyes = listOf(left, right)
        fx.update(dt)
    }

    // --- internos ----------------------------------------------------------

    private fun snapPose() {
        pose = targets.map { it.copy() }
        for ((eyeSprings, eyePose) in springs.zip(pose)) {
            for ((field, spring) in eyeSprings) spring.snap(eyePose[field])
        }
    }

    private fun presetTargets(name: String): List<EyeParams> {
        val preset = presets.getValue(name)
        return listOf(preset.left.copy(), preset.right.copy())
    }

    private fun updatePose(dt: Double) {
        val k = 1.0 - exp(-COLOR_RATE * dt)
        for (i in pose.indices) {
            val eyePose = pose[i]
            val target = targets[i]
            for ((field, spring) in springs[i]) {
                spring.target = target[field]
                eyePose[field] = spring.update(dt)
            }
            val c = eyePose.color
            val t = target.color
            eyePose.color = Rgb(c.r + (t.r - c.r) * k, c.g + (t.g - c.g) * k, c.b + (t.b - c.b) * k)
        }
    }

    private fun onSaccade(distance: Double) {
        // Olhadas grandes costumam vir acompanhadas de uma piscada.
        if (distance > 0.5 && rng.random() < 0.3 && !blink.blinking) blink.trigger()
    }
}
