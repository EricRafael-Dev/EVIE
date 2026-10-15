package com.evie.eyes.model

/** Cor RGB em ponto flutuante (0..255), como a tupla de floats do Python. */
data class Rgb(val r: Double, val g: Double, val b: Double) {
    operator fun get(index: Int): Double = when (index) {
        0 -> r
        1 -> g
        2 -> b
        else -> throw IndexOutOfBoundsException("canal $index")
    }

    companion object {
        val WHITE = Rgb(255.0, 255.0, 255.0)
    }
}

/** Parâmetros numéricos de um olho que ganham transição suave (uma mola por campo). */
enum class EyeField(val key: String) {
    W("w"),
    H("h"),
    RADIUS("radius"),
    X("x"),
    Y("y"),
    LID_TOP("lid_top"),
    LID_TILT("lid_tilt"),
    LID_BOTTOM("lid_bottom"),
    ARC("arc"),
    GLOW("glow"),
    HIGHLIGHT("highlight"),
    SHADE("shade"),
    BLUSH("blush"),
    TREMBLE("tremble"),
    WET("wet");

    companion object {
        private val byKey = values().associateBy { it.key }
        fun fromKey(key: String): EyeField? = byKey[key]
    }
}

val DEFAULT_COLOR = Rgb(76.0, 200.0, 183.0) // ciano padrão
val GLYPHS = listOf("", "heart", "star") // "" = olho normal; os outros trocam o corpo do olho por um símbolo

/** Parâmetros normalizados de um olho (mesmos campos e unidades da versão Python). */
data class EyeParams(
    var w: Double = 1.0,           // largura (1 = tamanho base do layout)
    var h: Double = 1.0,           // altura (piscar = h -> 0)
    var radius: Double = 0.55,     // 0 = cantos retos, 1 = pílula/círculo
    var x: Double = 0.0,           // olhar horizontal, -1..1
    var y: Double = 0.0,           // olhar vertical, -1..1 (positivo = baixo)
    var lidTop: Double = 0.0,      // cobertura da pálpebra superior, 0..1
    var lidTilt: Double = 0.0,     // -1 triste (canto externo cai) ... +1 bravo (canto interno cai)
    var lidBottom: Double = 0.0,   // cobertura inferior ("bochecha"), 0..1
    var arc: Double = 0.0,         // 0 = retângulo, 1 = arco feliz (^)
    var glow: Double = 0.5,        // intensidade do brilho, 0..1
    var highlight: Double = 1.0,   // reflexo especular, 0..1
    var shade: Double = 0.3,       // escurecimento da base do olho (volume), 0..1
    var blush: Double = 0.0,       // bochecha rosada abaixo do olho, 0..1
    var tremble: Double = 0.0,     // tremor + brilho pulsando como batimento (raiva), 0..1
    var wet: Double = 0.0,         // olho marejado: linha d'água e reflexo maior, 0..1
    var color: Rgb = DEFAULT_COLOR,
    var glyph: String = "",        // "", "heart" ou "star"; não é interpolado (troca escondida num piscar)
) {
    operator fun get(field: EyeField): Double = when (field) {
        EyeField.W -> w
        EyeField.H -> h
        EyeField.RADIUS -> radius
        EyeField.X -> x
        EyeField.Y -> y
        EyeField.LID_TOP -> lidTop
        EyeField.LID_TILT -> lidTilt
        EyeField.LID_BOTTOM -> lidBottom
        EyeField.ARC -> arc
        EyeField.GLOW -> glow
        EyeField.HIGHLIGHT -> highlight
        EyeField.SHADE -> shade
        EyeField.BLUSH -> blush
        EyeField.TREMBLE -> tremble
        EyeField.WET -> wet
    }

    operator fun set(field: EyeField, value: Double) {
        when (field) {
            EyeField.W -> w = value
            EyeField.H -> h = value
            EyeField.RADIUS -> radius = value
            EyeField.X -> x = value
            EyeField.Y -> y = value
            EyeField.LID_TOP -> lidTop = value
            EyeField.LID_TILT -> lidTilt = value
            EyeField.LID_BOTTOM -> lidBottom = value
            EyeField.ARC -> arc = value
            EyeField.GLOW -> glow = value
            EyeField.HIGHLIGHT -> highlight = value
            EyeField.SHADE -> shade = value
            EyeField.BLUSH -> blush = value
            EyeField.TREMBLE -> tremble = value
            EyeField.WET -> wet = value
        }
    }

    /** Campos numéricos e cor/símbolo, na mesma forma de `EyeParams.to_dict()` do Python. */
    fun toMap(): Map<String, Any> {
        val out = LinkedHashMap<String, Any>()
        for (field in EyeField.values()) out[field.key] = this[field]
        out["color"] = listOf(color.r, color.g, color.b)
        out["glyph"] = glyph
        return out
    }

    companion object {
        /** Cria a partir de um mapa (YAML), sobrescrevendo [base] (ou os padrões). */
        fun fromMap(data: Map<String, Any?>, base: EyeParams? = null): EyeParams {
            val params = base?.copy() ?: EyeParams()
            for ((key, value) in data) {
                when {
                    key == "color" -> {
                        val channels = (value as? List<*>)?.map { (it as Number).toDouble() }
                        require(channels != null && channels.size == 3) { "color precisa de 3 canais, recebeu $value" }
                        params.color = Rgb(channels[0], channels[1], channels[2])
                    }
                    key == "glyph" -> {
                        val name = (value as? String) ?: ""
                        require(name in GLYPHS) { "glyph desconhecido '$name'. Disponíveis: ${GLYPHS.drop(1)}" }
                        params.glyph = name
                    }
                    else -> {
                        val field = EyeField.fromKey(key)
                            ?: throw IllegalArgumentException("Parâmetro de olho desconhecido: '$key'")
                        params[field] = (value as Number).toDouble()
                    }
                }
            }
            return params
        }
    }
}
