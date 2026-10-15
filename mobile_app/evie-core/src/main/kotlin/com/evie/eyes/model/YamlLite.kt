package com.evie.eyes.model

/**
 * Leitor mínimo de YAML, só com o subconjunto usado em `presets.yaml`:
 * mapas por indentação, listas em linha (`[a, b]`), mapa vazio (`{}`) e escalares.
 * Números viram [Double]; erros levantam [IllegalArgumentException] com o número da linha.
 */
internal object YamlLite {
    private class Line(val number: Int, val indent: Int, val text: String)

    fun parse(source: String): Map<String, Any?> {
        val lines = ArrayList<Line>()
        source.lines().forEachIndexed { i, raw ->
            val noComment = raw.substringBefore('#')
            if (noComment.isBlank()) return@forEachIndexed
            require('\t' !in noComment) { "linha ${i + 1}: tabulação não é suportada" }
            val indent = noComment.length - noComment.trimStart().length
            lines.add(Line(i + 1, indent, noComment.trim()))
        }
        if (lines.isEmpty()) return emptyMap()
        val (map, next) = parseBlock(lines, 0, lines[0].indent)
        require(next == lines.size) { "linha ${lines[next].number}: indentação inesperada" }
        return map
    }

    private fun parseBlock(lines: List<Line>, start: Int, indent: Int): Pair<Map<String, Any?>, Int> {
        val map = LinkedHashMap<String, Any?>()
        var i = start
        while (i < lines.size && lines[i].indent == indent) {
            val line = lines[i]
            val colon = line.text.indexOf(':')
            require(colon > 0) { "linha ${line.number}: esperado 'chave: valor'" }
            val key = line.text.substring(0, colon).trim()
            val rest = line.text.substring(colon + 1).trim()
            i++
            if (rest.isEmpty()) {
                if (i < lines.size && lines[i].indent > indent) {
                    val (child, next) = parseBlock(lines, i, lines[i].indent)
                    map[key] = child
                    i = next
                } else {
                    map[key] = null
                }
            } else {
                map[key] = parseValue(rest, line.number)
            }
        }
        if (i < lines.size && lines[i].indent > indent) {
            throw IllegalArgumentException("linha ${lines[i].number}: indentação inesperada")
        }
        return Pair(map, i)
    }

    private fun parseValue(text: String, number: Int): Any? = when {
        text == "{}" -> emptyMap<String, Any?>()
        text.startsWith("[") -> {
            require(text.endsWith("]")) { "linha $number: lista sem ']'" }
            val inner = text.substring(1, text.length - 1)
            if (inner.isBlank()) emptyList() else inner.split(',').map { parseScalar(it.trim()) }
        }
        text.startsWith("{") -> throw IllegalArgumentException("linha $number: mapa em linha não é suportado")
        else -> parseScalar(text)
    }

    private fun parseScalar(text: String): Any? {
        if (text == "~" || text == "null") return null
        if (text == "true") return true
        if (text == "false") return false
        text.toDoubleOrNull()?.let { return it }
        if (text.length >= 2 && (text.first() == '"' || text.first() == '\'') && text.last() == text.first()) {
            return text.substring(1, text.length - 1)
        }
        return text
    }
}
