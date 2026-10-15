package com.evie.assistant

import com.google.gson.JsonObject

// ── Null-Safe Gson Helpers ──────────────────────────────────────────────────
internal fun JsonObject.optString(key: String, default: String = ""): String {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asString } catch (_: Exception) { default }
}

internal fun JsonObject.optFloat(key: String, default: Float = 0f): Float {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asFloat } catch (_: Exception) { default }
}

internal fun JsonObject.optInt(key: String, default: Int = 0): Int {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asInt } catch (_: Exception) { default }
}

internal fun JsonObject.optLong(key: String, default: Long = 0L): Long {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asLong } catch (_: Exception) { default }
}

internal fun JsonObject.optDouble(key: String, default: Double = 0.0): Double {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asDouble } catch (_: Exception) { default }
}

internal fun JsonObject.optBoolean(key: String, default: Boolean = false): Boolean {
    val elem = get(key) ?: return default
    if (elem.isJsonNull) return default
    return try { elem.asBoolean } catch (_: Exception) { default }
}
