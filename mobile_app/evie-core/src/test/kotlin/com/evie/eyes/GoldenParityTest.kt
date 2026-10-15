package com.evie.eyes

import com.evie.eyes.behaviors.DOUBLE_BLINK
import com.evie.eyes.behaviors.SINGLE_BLINK
import com.evie.eyes.core.EASINGS
import com.evie.eyes.core.Noise1D
import com.evie.eyes.core.PyRandom
import com.evie.eyes.core.Spring
import com.evie.eyes.effects.heartbeat
import com.evie.eyes.model.EyeField
import com.evie.eyes.model.EyeParams
import com.evie.eyes.model.Presets
import com.evie.eyes.states.IdleConfig
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.fail

/**
 * Paridade com a versão Python: compara o Kotlin com `golden.json`, gerado por `parity/generate_golden.py`.
 * O gerador aleatório precisa bater exatamente; os números de ponto flutuante aceitam 1e-9
 * (as funções trigonométricas da JVM e do C podem diferir em 1 ulp).
 */
class GoldenParityTest {
    private val golden: JsonObject by lazy {
        val stream = javaClass.getResourceAsStream("/golden.json") ?: fail("golden.json ausente em src/test/resources")
        JsonParser.parseString(stream.bufferedReader().use { it.readText() }).asJsonObject
    }

    private fun near(expected: Double, actual: Double, path: String, tolerance: Double = 1e-9) {
        val ok = Math.abs(expected - actual) <= tolerance + tolerance * Math.abs(expected)
        if (!ok) fail("$path: esperado $expected, obtido $actual")
    }

    private fun JsonElement.d() = asDouble

    // --- gerador aleatório ---------------------------------------------------

    @Test
    fun randomMatchesPython() {
        for (entry in golden["random"].asJsonArray) {
            val o = entry.asJsonObject
            val seed = o["seed"].asLong
            val rng = PyRandom(seed)
            o["mixed"].asJsonArray.forEachIndexed { i, item ->
                val pair = item.asJsonArray
                val op = pair[0].asString
                val expected = pair[1]
                val path = "seed $seed, op #$i ($op)"
                when (op) {
                    "random" -> assertEquals(expected.d(), rng.random(), path)
                    "uniform" -> assertEquals(expected.d(), rng.uniform(-2.5, 3.5), path)
                    "gauss" -> near(expected.d(), rng.gauss(0.0, 0.5), path, 1e-12)
                    "choice" -> assertEquals(expected.asInt, rng.choice(listOf(-1, 1)), path)
                    "randrange" -> assertEquals(expected.asInt, rng.randRange(1 shl 30), path)
                    else -> fail("op desconhecida $op")
                }
            }
            val long = PyRandom(seed)
            val checkpoints = o["long_run"].asJsonArray
            var next = 0
            for (i in 1..3000) {
                val value = long.random()
                if (i % 250 == 0) {
                    assertEquals(checkpoints[next++].d(), value, "seed $seed, random() #$i")
                }
            }
            val bits = o["getrandbits"].asJsonArray
            listOf(1, 7, 16, 31, 32).forEachIndexed { i, k ->
                assertEquals(bits[i].asLong, PyRandom(seed).getRandBits(k), "seed $seed, getrandbits($k)")
            }
        }
    }

    // --- núcleo numérico -----------------------------------------------------

    @Test
    fun noiseMatchesPython() {
        for (entry in golden["noise"].asJsonArray) {
            val o = entry.asJsonObject
            val noise = Noise1D(o["seed"].asLong)
            for (row in o["values"].asJsonArray) {
                val r = row.asJsonArray
                near(r[1].d(), noise(r[0].d()), "noise seed ${o["seed"]} t=${r[0]}", 1e-12)
                near(r[2].d(), noise.fbm(r[0].d()), "fbm seed ${o["seed"]} t=${r[0]}", 1e-12)
            }
        }
    }

    @Test
    fun springsMatchPython() {
        for ((index, entry) in golden["spring"].asJsonArray.withIndex()) {
            val o = entry.asJsonObject
            val spring = Spring(o["value"].d(), o["frequency"].d(), o["damping"].d())
            spring.target = o["target"].d()
            spring.velocity = o["initial_velocity"].d()
            val dtInfo = o["dts"].asJsonArray
            val dt = dtInfo[0].d()
            val count = dtInfo[1].asInt
            var sample = 0
            val samples = o["samples"].asJsonArray
            for (i in 0 until count) {
                spring.update(dt)
                if (i % 10 == 9) {
                    val expected = samples[sample++].asJsonArray
                    near(expected[0].d(), spring.value, "spring #$index passo $i valor", 1e-9)
                    near(expected[1].d(), spring.velocity, "spring #$index passo $i velocidade", 1e-9)
                }
            }
        }
    }

    @Test
    fun easingsMatchPython() {
        val ts = golden["easing"].asJsonObject["ts"].asJsonArray.map { it.d() }
        val values = golden["easing"].asJsonObject["values"].asJsonObject
        assertEquals(values.keySet().toList(), EASINGS.keys.toList())
        for ((name, fn) in EASINGS) {
            val expected = values[name].asJsonArray
            ts.forEachIndexed { i, t -> near(expected[i].d(), fn(t), "easing $name($t)", 1e-12) }
        }
    }

    @Test
    fun trackMatchesPython() {
        val o = golden["track"].asJsonObject
        val times = o["times"].asJsonArray.map { it.d() }
        val scaled = SINGLE_BLINK.scaled(2.0)
        times.forEachIndexed { i, t ->
            near(o["single"].asJsonArray[i].d(), SINGLE_BLINK.sample(t), "single($t)", 1e-12)
            near(o["double"].asJsonArray[i].d(), DOUBLE_BLINK.sample(t), "double($t)", 1e-12)
            near(o["scaled"].asJsonArray[i].d(), scaled.sample(t), "scaled($t)", 1e-12)
        }
        val durations = o["durations"].asJsonArray
        near(durations[0].d(), SINGLE_BLINK.duration, "duração simples", 1e-12)
        near(durations[1].d(), DOUBLE_BLINK.duration, "duração dupla", 1e-12)
        near(durations[2].d(), scaled.duration, "duração lenta", 1e-12)
    }

    @Test
    fun heartbeatMatchesPython() {
        for (row in golden["heartbeat"].asJsonArray) {
            val r = row.asJsonArray
            near(r[1].d(), heartbeat(r[0].d()), "heartbeat(${r[0]})", 1e-12)
            near(r[2].d(), heartbeat(r[0].d(), 1.0), "heartbeat(${r[0]}, 1.0)", 1e-12)
        }
    }

    // --- presets -------------------------------------------------------------

    @Test
    fun presetsYamlIsIdenticalToThePythonCopy() {
        val bytes = javaClass.getResourceAsStream("/com/evie/eyes/presets.yaml")!!.readBytes()
        val sha = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        assertEquals(
            golden["presets"].asJsonObject["sha256"].asString, sha,
            "presets.yaml difere do projeto Python: copie o arquivo e rode parity/generate_golden.py",
        )
    }

    @Test
    fun presetsMatchPython() {
        val expected = golden["presets"].asJsonObject
        val presets = Presets.loadDefault()
        assertEquals(expected["order"].asJsonArray.map { it.asString }, presets.keys.toList())
        for ((name, preset) in presets) {
            val e = expected["presets"].asJsonObject[name].asJsonObject
            assertEquals(e["fx"].asJsonArray.map { it.asString }, preset.fx, "fx de $name")
            compareEye(e["left"].asJsonObject, preset.left, "$name.left")
            compareEye(e["right"].asJsonObject, preset.right, "$name.right")
        }
    }

    private fun compareEye(expected: JsonObject, eye: EyeParams, path: String, tolerance: Double = 1e-12) {
        for (field in EyeField.values()) near(expected[field.key].d(), eye[field], "$path.${field.key}", tolerance)
        val color = expected["color"].asJsonArray
        near(color[0].d(), eye.color.r, "$path.color.r", tolerance)
        near(color[1].d(), eye.color.g, "$path.color.g", tolerance)
        near(color[2].d(), eye.color.b, "$path.color.b", tolerance)
        assertEquals(expected["glyph"].asString, eye.glyph, "$path.glyph")
    }

    // --- animação completa ---------------------------------------------------

    @Test
    fun fullAnimationTracesMatchPython() {
        val scenarios: JsonArray = golden["scenarios"].asJsonArray
        assertTrue(scenarios.size() >= 5)
        for (element in scenarios) {
            runScenario(element.asJsonObject)
        }
    }

    private fun runScenario(s: JsonObject) {
        val name = s["name"].asString
        val idle = when (s["idle"].asString) {
            "fast" -> IdleConfig.fast()
            "off" -> IdleConfig(enabled = false)
            else -> IdleConfig()
        }
        val face = Face(seed = s["seed"].asLong, idleConfig = idle)
        val dt = s["dt"].d()
        val every = s["sample_every"].asInt
        val actions = s["actions"].asJsonArray.map { it.asJsonObject }
        val samples = s["samples"].asJsonArray
        var sampleIndex = 0
        for (step in 0 until s["total_steps"].asInt) {
            for (action in actions) if (action["step"].asInt == step) apply(face, action)
            face.update(dt)
            if ((step + 1) % every == 0) {
                compareSample(samples[sampleIndex++].asJsonObject, face, "$name@${step + 1}")
            }
        }
        assertEquals(samples.size(), sampleIndex, "$name: número de amostras")
        // Mesma quantidade de sorteios consumidos nas duas versões: o próximo valor tem que ser igual.
        assertEquals(s["rng_next"].d(), face.rng.random(), "$name: estado do gerador aleatório ao final")
    }

    private fun apply(face: Face, action: JsonObject) {
        when (val op = action["op"].asString) {
            "set_expression" -> face.setExpression(
                action["name"].asString,
                duration = action["duration"]?.takeUnless { it.isJsonNull }?.asDouble,
            )
            "look_at" -> face.lookAt(action["x"].d(), action["y"].d(), hold = action["hold"]?.asDouble ?: 2.0)
            "blink_now" -> face.blinkNow(double = action["double"]?.asBoolean ?: false)
            "poke" -> face.poke()
            "sleep_now" -> face.idle.sleepNow()
            "yawn" -> face.yawn.trigger()
            "snap" -> face.snap()
            "layer" -> {
                val enabled = action["enabled"].asBoolean
                when (val layer = action["name"].asString) {
                    "saccade" -> face.saccade.enabled = enabled
                    "drift" -> face.drift.enabled = enabled
                    "breathing" -> face.breathing.enabled = enabled
                    "blink" -> face.blink.enabled = enabled
                    else -> fail("camada desconhecida $layer")
                }
            }
            else -> fail("ação desconhecida $op")
        }
    }

    private fun compareSample(expected: JsonObject, face: Face, path: String) {
        assertEquals(expected["expression"].asString, face.expression, "$path: expressão")
        assertEquals(expected["stage"].asString, face.idle.stage, "$path: estágio ocioso")
        near(expected["time"].d(), face.time, "$path: tempo")
        val eyes = expected["eyes"].asJsonArray
        compareEye(eyes[0].asJsonObject, face.eyes[0], "$path.olho esquerdo", 1e-9)
        compareEye(eyes[1].asJsonObject, face.eyes[1], "$path.olho direito", 1e-9)
        val particles = expected["particles"].asJsonArray
        assertEquals(particles.size(), face.particles.size, "$path: número de partículas")
        particles.forEachIndexed { i, element ->
            val e = element.asJsonObject
            val p = face.particles[i]
            assertEquals(e["kind"].asString, p.kind, "$path.partícula[$i] tipo")
            assertEquals(e["layer"].asString, p.layer, "$path.partícula[$i] camada")
            near(e["x"].d(), p.x, "$path.partícula[$i].x")
            near(e["y"].d(), p.y, "$path.partícula[$i].y")
            near(e["size"].d(), p.size, "$path.partícula[$i].size")
            near(e["age"].d(), p.age, "$path.partícula[$i].age")
            near(e["alpha"].d(), p.alpha, "$path.partícula[$i].alpha")
            near(e["angle"].d(), p.angle, "$path.partícula[$i].angle")
        }
    }
}
