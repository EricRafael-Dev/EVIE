package com.evie.eyes.effects

import com.evie.eyes.Face
import com.evie.eyes.core.PyRandom
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Geometry
import com.evie.eyes.model.Geometry.EYE_H
import com.evie.eyes.model.Geometry.EYE_W
import com.evie.eyes.model.Rgb
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Efeitos contínuos e o intervalo (s) entre emissões. */
val CONTINUOUS: Map<String, Pair<Double, Double>> = linkedMapOf(
    "tears" to Pair(1.6, 3.0),
    "zzz" to Pair(1.1, 1.6),
    "sparkles" to Pair(0.5, 1.2),
    "hearts" to Pair(0.45, 0.9),
)
val ONE_SHOT = setOf("hop", "wink_sparkle", "shockwave", "exclaim")
val PERSISTENT = setOf("anger") // fica na tela enquanto a expressão durar
val MODES = setOf("scan")       // mudam um comportamento em vez de criar partículas
val FX_KINDS: Set<String> = CONTINUOUS.keys + ONE_SHOT + PERSISTENT + MODES

private val TEAR_COLOR = Rgb(150.0, 205.0, 255.0)
private val HEART_COLOR = Rgb(255.0, 110.0, 160.0)
private val SPARKLE_COLOR = Rgb(255.0, 248.0, 215.0)
private val ANGER_COLOR = Rgb(255.0, 80.0, 70.0)
private val EXCLAIM_COLOR = Rgb(255.0, 225.0, 110.0)
private const val HOP_DELAY = 0.22 // espera o olho reabrir (troca de forma no piscar) antes do pulinho

fun validateFx(name: String, fx: List<String>) {
    val unknown = (fx.toSet() - FX_KINDS).sorted()
    require(unknown.isEmpty()) { "Preset '$name': efeitos desconhecidos $unknown. Disponíveis: ${FX_KINDS.sorted()}" }
}

/** Dispara as partículas e comportamentos listados em `fx:` de cada preset. */
class EmotionFx(private val face: Face, private val rng: PyRandom) {
    val particles = ParticleSystem()
    var active: List<String> = emptyList()
        private set

    private class Scheduled(var remaining: Double, val callback: () -> Unit)

    private var timers = LinkedHashMap<String, Double>()
    private val scheduled = ArrayList<Scheduled>()
    private val persistent = LinkedHashMap<String, Particle>()

    fun onExpression(fx: List<String>) {
        val wanted = fx.toSet()
        for (kind in persistent.keys.toList()) {
            if (kind !in wanted) persistent.remove(kind)!!.release()
        }
        scheduled.clear()
        timers = LinkedHashMap()
        for (kind in fx) {
            if (kind in CONTINUOUS) timers[kind] = rng.uniform(0.15, 0.5)
        }
        face.saccade.scan = "scan" in wanted

        for (kind in fx) {
            when {
                kind == "hop" -> schedule(HOP_DELAY) { face.hop.kick() }
                kind == "wink_sparkle" -> {
                    schedule(0.25) { winkSparkle(0.62, -0.42, 0.2) }
                    schedule(0.45) { winkSparkle(0.8, -0.2, 0.12) }
                }
                kind == "shockwave" -> for (side in listOf(-1, 1)) shockwave(side)
                kind == "exclaim" -> exclaim()
                kind == "anger" && kind !in persistent -> {
                    val (ax, ay) = angerAnchor()
                    persistent[kind] = particles.spawn(
                        Particle(
                            "anger", ax, ay, size = 0.3, life = Double.POSITIVE_INFINITY,
                            color = ANGER_COLOR, fadeIn = 0.25, fadeOut = 0.3,
                        ),
                    )
                }
            }
        }
        active = fx.toList()
    }

    fun update(dt: Double) {
        for (item in scheduled) item.remaining -= dt
        val due = scheduled.filter { it.remaining <= 0.0 }
        scheduled.removeAll { it.remaining <= 0.0 }
        for (item in due) item.callback()

        for ((kind, before) in timers.entries.toList()) {
            var remaining = before - dt
            if (remaining <= 0.0) {
                emit(kind)
                val range = CONTINUOUS.getValue(kind)
                remaining = rng.uniform(range.first, range.second)
            }
            timers[kind] = remaining
        }

        persistent["anger"]?.let {
            val (ax, ay) = angerAnchor()
            it.x = ax
            it.y = ay
        }
        particles.update(dt)
    }

    // --- emissores ---------------------------------------------------------

    private fun schedule(delay: Double, callback: () -> Unit) {
        scheduled.add(Scheduled(delay, callback))
    }

    private fun eye(side: Int): EyeParams = face.eyes[if (side < 0) 0 else 1]

    private fun emit(kind: String) {
        when (kind) {
            "tears" -> tear()
            "zzz" -> zzz()
            "sparkles" -> sparkle()
            "hearts" -> heart()
        }
    }

    private fun tear() {
        val side = rng.choice(listOf(-1, 1))
        val p = eye(side)
        val (cx, cy) = Geometry.eyeCenter(p, side)
        particles.spawn(
            Particle(
                "tear",
                cx + side * 0.36 * EYE_W * p.w, // canto externo, onde a lágrima se acumula
                cy + 0.42 * EYE_H * p.h,
                size = 0.09, life = 1.9, color = TEAR_COLOR,
                vx = side * 0.01, vy = 0.02, ay = 1.6, hold = 0.7, fadeIn = 0.05, fadeOut = 0.3,
            ),
        )
    }

    private fun zzz() {
        val p = eye(1)
        val (cx, cy) = Geometry.eyeCenter(p, 1)
        val light = Rgb(
            p.color.r + (255.0 - p.color.r) * 0.3,
            p.color.g + (255.0 - p.color.g) * 0.3,
            p.color.b + (255.0 - p.color.b) * 0.3,
        )
        particles.spawn(
            Particle(
                "zzz", cx + 0.45 * EYE_W, cy - 0.12 * EYE_H,
                size = 0.16, life = 2.6, color = light,
                vx = 0.035, vy = -0.075, angle = -0.2, phase = rng.uniform(0.0, 2.0 * PI),
                fadeIn = 0.4, fadeOut = 0.9,
            ),
        )
    }

    private fun heart() {
        val side = rng.choice(listOf(-1, 1))
        val (cx, cy) = Geometry.eyeCenter(eye(side), side)
        // A ordem dos sorteios é a mesma da versão Python (argumentos avaliados da esquerda p/ direita).
        val px = cx + rng.uniform(-0.4, 0.4) * EYE_W
        val size = rng.uniform(0.12, 0.2)
        val life = rng.uniform(1.8, 2.4)
        val vx = rng.uniform(-0.01, 0.01)
        val vy = -rng.uniform(0.07, 0.11)
        val phase = rng.uniform(0.0, 2.0 * PI)
        particles.spawn(
            Particle(
                "heart", px, cy - 0.5 * EYE_H,
                size = size, life = life, color = HEART_COLOR,
                vx = vx, vy = vy, phase = phase, fadeIn = 0.25, fadeOut = 0.8,
            ),
        )
    }

    private fun sparkle() {
        val side = rng.choice(listOf(-1, 1))
        val (cx, cy) = Geometry.eyeCenter(eye(side), side)
        val a = rng.uniform(Math.toRadians(200.0), Math.toRadians(340.0)) // metade de cima, fora do olho
        val size = rng.uniform(0.09, 0.15)
        val life = rng.uniform(0.6, 0.9)
        val spin = rng.uniform(-1.5, 1.5)
        particles.spawn(
            Particle(
                "sparkle", cx + cos(a) * 0.75 * EYE_W, cy + sin(a) * 0.55 * EYE_H,
                size = size, life = life, color = SPARKLE_COLOR,
                spin = spin, fadeIn = 0.0, fadeOut = 0.0,
            ),
        )
    }

    private fun winkSparkle(fx: Double, fy: Double, size: Double) {
        val (cx, cy) = Geometry.eyeCenter(eye(1), 1)
        particles.spawn(
            Particle(
                "sparkle", cx + fx * EYE_W, cy + fy * EYE_H, size = size, life = 0.9,
                color = SPARKLE_COLOR, spin = 1.2, fadeIn = 0.0, fadeOut = 0.0,
            ),
        )
    }

    private fun shockwave(side: Int) {
        val p = eye(side)
        val (cx, cy) = Geometry.eyeCenter(p, side)
        particles.spawn(
            Particle(
                "ring", cx, cy, size = 0.55 * maxOf(p.h, 1.0), sizeX = 0.55 * maxOf(p.w, 1.0), life = 0.6,
                color = p.color, layer = "back", fadeIn = 0.0, fadeOut = 0.6,
            ),
        )
    }

    private fun exclaim() {
        val (cx, cy) = Geometry.eyeCenter(eye(1), 1)
        particles.spawn(
            Particle(
                "exclaim", cx + 0.64 * EYE_W, cy - 0.62 * EYE_H, size = 0.42, life = 1.1,
                color = EXCLAIM_COLOR, angle = 0.18, fadeIn = 0.0, fadeOut = 0.3,
            ),
        )
    }

    private fun angerAnchor(): Pair<Double, Double> {
        val (cx, cy) = Geometry.eyeCenter(eye(1), 1)
        return Pair(cx + 0.6 * EYE_W, cy - 0.55 * EYE_H)
    }

    /** Dispara uma rajada de partículas sob demanda (estrelas/brilhos ou corações). */
    fun burst(kind: String = "star", count: Int = 8) {
        for (i in 0 until count) {
            when (kind) {
                "star", "sparkle" -> sparkle()
                "heart" -> heart()
                else -> sparkle()
            }
        }
    }
}
