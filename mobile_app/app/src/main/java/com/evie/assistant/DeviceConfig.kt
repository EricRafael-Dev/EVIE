package com.evie.assistant

import android.content.Context
import android.content.SharedPreferences

class DeviceConfig(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("evie_mobile_config", Context.MODE_PRIVATE)

    var serverHost: String
        get() = prefs.getString("server_host", "https://100.73.5.37:8000") ?: "https://100.73.5.37:8000"
        set(value) = prefs.edit().putString("server_host", value.trim()).apply()

    var deviceName: String
        get() = prefs.getString("device_name", "poco-x7") ?: "poco-x7"
        set(value) = prefs.edit().putString("device_name", value.trim()).apply()

    var authToken: String
        get() = prefs.getString("auth_token", "Ybawdj5FSmkArsbxxWwtSTNhc1FCo_SOHyB8xGWBsVg") ?: "Ybawdj5FSmkArsbxxWwtSTNhc1FCo_SOHyB8xGWBsVg"
        set(value) = prefs.edit().putString("auth_token", value.trim()).apply()

    val isHttps: Boolean
        get() {
            val h = serverHost.trim().lowercase()
            return h.startsWith("https://") || (!h.startsWith("http://") && (h.contains(":8000") || h.contains(":8001")))
        }

    val cleanHost: String
        get() {
            val raw = serverHost.trim().trimEnd('/')
            return raw.removePrefix("http://")
                .removePrefix("https://")
                .removePrefix("ws://")
                .removePrefix("wss://")
                .trim()
        }

    val httpBaseUrl: String
        get() = if (isHttps) "https://$cleanHost" else "http://$cleanHost"

    val wsBaseUrl: String
        get() = if (isHttps) "wss://$cleanHost" else "ws://$cleanHost"
}
