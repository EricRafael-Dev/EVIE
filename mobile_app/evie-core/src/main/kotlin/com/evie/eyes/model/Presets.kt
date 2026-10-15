package com.evie.eyes.model

/**
 * Carrega expressões de `presets.yaml`.
 *
 * Formato: cada preset lista parâmetros comuns aos dois olhos; as chaves opcionais `left:` e
 * `right:` sobrescrevem um olho específico, e `fx:` lista os efeitos animados da expressão.
 */
class Preset(val name: String, val left: EyeParams, val right: EyeParams, var fx: List<String> = emptyList())

object Presets {
    private const val RESOURCE = "/com/evie/eyes/presets.yaml"

    /** Presets embutidos (cópia de `presets.yaml` do projeto Python). */
    fun loadDefault(): Map<String, Preset> {
        val stream = Presets::class.java.getResourceAsStream(RESOURCE)
            ?: throw IllegalStateException("Recurso $RESOURCE não encontrado")
        return load(stream.bufferedReader(Charsets.UTF_8).use { it.readText() })
    }

    /** Lê presets de um texto YAML (útil para presets próprios do app). */
    fun load(yaml: String): Map<String, Preset> {
        val raw = YamlLite.parse(yaml)
        val presets = LinkedHashMap<String, Preset>()
        for ((name, rawSpec) in raw) {
            @Suppress("UNCHECKED_CAST")
            val spec = LinkedHashMap((rawSpec as? Map<String, Any?>) ?: emptyMap())

            @Suppress("UNCHECKED_CAST")
            val leftOverride = spec.remove("left") as? Map<String, Any?> ?: emptyMap()

            @Suppress("UNCHECKED_CAST")
            val rightOverride = spec.remove("right") as? Map<String, Any?> ?: emptyMap()
            val fx = spec.remove("fx") ?: emptyList<String>()
            require(fx is List<*> && fx.all { it is String }) {
                "Preset '$name': `fx` precisa ser uma lista de nomes, recebeu $fx"
            }
            val common = EyeParams.fromMap(spec)
            @Suppress("UNCHECKED_CAST")
            presets[name] = Preset(
                name = name,
                left = EyeParams.fromMap(leftOverride, common),
                right = EyeParams.fromMap(rightOverride, common),
                fx = fx as List<String>,
            )
        }
        require("neutral" in presets) { "presets.yaml precisa definir o preset 'neutral'" }
        return presets
    }
}
