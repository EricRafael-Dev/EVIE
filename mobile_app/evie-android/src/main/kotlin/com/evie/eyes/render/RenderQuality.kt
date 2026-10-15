package com.evie.eyes.render

/**
 * Custo x beleza. Displays pequenos e celulares mais fracos usam níveis mais baixos.
 *
 * @property supersample fator de supersampling (o olho é desenhado em N x e reduzido).
 * @property bloom camadas de brilho: (divisor do downscale, intensidade); a última recebe a vinheta.
 */
enum class RenderQuality(
    val supersample: Int,
    internal val bloom: List<Pair<Int, Double>>,
    val trail: Boolean,
    val tint: Boolean,
) {
    LOW(supersample = 1, bloom = listOf(10 to 0.45), trail = false, tint = false),
    MEDIUM(supersample = 2, bloom = listOf(10 to 0.45), trail = false, tint = true),
    HIGH(supersample = 2, bloom = listOf(6 to 0.32, 20 to 0.30), trail = true, tint = true);

    /** Próximo nível, dando a volta (low -> medium -> high -> low). */
    fun next(): RenderQuality = values()[(ordinal + 1) % values().size]

    /** Nível imediatamente mais leve, ou ele mesmo se já for o mais leve. */
    fun lighter(): RenderQuality = if (ordinal == 0) this else values()[ordinal - 1]

    companion object {
        fun fromName(name: String): RenderQuality =
            values().firstOrNull { it.name.equals(name, ignoreCase = true) }
                ?: throw IllegalArgumentException("Qualidade desconhecida '$name'. Disponíveis: ${values().map { it.name.lowercase() }}")
    }
}
