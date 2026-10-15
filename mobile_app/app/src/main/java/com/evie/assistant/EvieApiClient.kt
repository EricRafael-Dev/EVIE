package com.evie.assistant

import com.google.gson.Gson
import com.google.gson.JsonObject
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class EvieApiClient(private val config: DeviceConfig) {

    private val gson = Gson()
    val client: OkHttpClient = createClient()

    private var activeWebSocket: WebSocket? = null

    companion object {
        fun createClient(): OkHttpClient {
            return try {
                val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
                    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
                    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                })

                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, trustAllCerts, SecureRandom())

                OkHttpClient.Builder()
                    .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
                    .hostnameVerifier { _, _ -> true }
                    .connectTimeout(6, TimeUnit.SECONDS)
                    .readTimeout(10, TimeUnit.SECONDS)
                    .writeTimeout(10, TimeUnit.SECONDS)
                    .pingInterval(15, TimeUnit.SECONDS)
                    .build()
            } catch (_: Exception) {
                OkHttpClient.Builder()
                    .connectTimeout(6, TimeUnit.SECONDS)
                    .readTimeout(10, TimeUnit.SECONDS)
                    .writeTimeout(10, TimeUnit.SECONDS)
                    .pingInterval(15, TimeUnit.SECONDS)
                    .build()
            }
        }
    }

    fun checkStatus(callback: (Boolean, String, String?) -> Unit) {
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/status")
            .header("Authorization", "Bearer ${config.authToken}")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Erro de conexão", null)
            }

            override fun onResponse(call: Call, response: Response) {
                try {
                    val body = response.body?.string() ?: ""
                    if (response.isSuccessful) {
                        val json = gson.fromJson(body, JsonObject::class.java)
                        val deviceRecognized = if (json.has("device") && !json.get("device").isJsonNull) {
                            json.get("device").asString
                        } else null
                        callback(true, "Conectado", deviceRecognized)
                    } else {
                        callback(false, "Servidor retornou ${response.code}", null)
                    }
                } catch (e: Exception) {
                    callback(false, "Erro ao processar resposta", null)
                }
            }
        })
    }

    fun fetchSysStats(callback: (JsonObject?) -> Unit) {
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/sys_stats")
            .header("Authorization", "Bearer ${config.authToken}")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(null)
            }

            override fun onResponse(call: Call, response: Response) {
                try {
                    val body = response.body?.string() ?: ""
                    if (response.isSuccessful) {
                        val json = gson.fromJson(body, JsonObject::class.java)
                        callback(json)
                    } else {
                        callback(null)
                    }
                } catch (_: Exception) {
                    callback(null)
                }
            }
        })
    }

    fun sendCommand(text: String, callback: (Boolean, String) -> Unit) {
        try {
            val jsonPayload = JsonObject().apply {
                addProperty("text", text)
                addProperty("device", config.deviceName)
            }

            // Send via WebSocket if connected for zero-latency transmission
            val wsSent = try {
                val wsPayload = JsonObject().apply {
                    addProperty("type", "command")
                    addProperty("text", text)
                    addProperty("device", config.deviceName)
                }
                activeWebSocket?.send(wsPayload.toString()) ?: false
            } catch (_: Exception) {
                false
            }

            if (wsSent) {
                callback(true, "Comando enviado")
                return
            }

            // Issue HTTP post as reliable fallback if WebSocket is not connected
            val requestBody = jsonPayload.toString().toRequestBody("application/json".toMediaType())
            val targetUrl = "${config.httpBaseUrl}/api/native/command"
            val request = Request.Builder()
                .url(targetUrl)
                .header("Authorization", "Bearer ${config.authToken}")
                .post(requestBody)
                .build()

            client.newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    callback(false, e.localizedMessage ?: "Falha ao enviar comando")
                }

                override fun onResponse(call: Call, response: Response) {
                    callback(response.isSuccessful, if (response.isSuccessful) "Comando enviado" else "Erro ${response.code}")
                }
            })
        } catch (e: Exception) {
            callback(false, e.localizedMessage ?: "Erro ao despachar comando")
        }
    }

    fun sendUIAction(actionId: String, payload: Map<String, Any>?, callback: ((Boolean) -> Unit)? = null) {
        try {
            val jsonPayload = JsonObject().apply {
                addProperty("type", "ui_action")
                addProperty("action_id", actionId)
                if (payload != null) {
                    add("payload", gson.toJsonTree(payload))
                }
                addProperty("device", config.deviceName.ifBlank { "Mobile" })
            }

            val wsSent = try {
                activeWebSocket?.send(jsonPayload.toString()) ?: false
            } catch (_: Exception) {
                false
            }

            if (wsSent) {
                callback?.invoke(true)
                return
            }

            val requestBody = jsonPayload.toString().toRequestBody("application/json".toMediaType())
            val targetUrl = "${config.httpBaseUrl}/api/ui_action"
            val request = Request.Builder()
                .url(targetUrl)
                .header("Authorization", "Bearer ${config.authToken}")
                .post(requestBody)
                .build()

            client.newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    callback?.invoke(false)
                }

                override fun onResponse(call: Call, response: Response) {
                    callback?.invoke(response.isSuccessful)
                }
            })
        } catch (_: Exception) {
            callback?.invoke(false)
        }
    }

    fun sendGeoLocation(lat: Double, lon: Double, accuracy: Float = 5.0f, callback: ((Boolean) -> Unit)? = null) {
        try {
            val jsonPayload = JsonObject().apply {
                addProperty("type", "geo_location")
                addProperty("lat", lat)
                addProperty("lon", lon)
                addProperty("accuracy", accuracy)
                addProperty("device", config.deviceName.ifBlank { "POCO X7 MOBILE" })
            }
            val wsSent = try {
                activeWebSocket?.send(jsonPayload.toString()) ?: false
            } catch (_: Exception) {
                false
            }
            if (wsSent) {
                callback?.invoke(true)
                return
            }
            val requestBody = jsonPayload.toString().toRequestBody("application/json".toMediaType())
            val targetUrl = "${config.httpBaseUrl}/api/mobile/telemetry"
            val request = Request.Builder()
                .url(targetUrl)
                .header("Authorization", "Bearer ${config.authToken}")
                .post(requestBody)
                .build()
            client.newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    callback?.invoke(false)
                }
                override fun onResponse(call: Call, response: Response) {
                    callback?.invoke(response.isSuccessful)
                }
            })
        } catch (_: Exception) {
            callback?.invoke(false)
        }
    }

    fun sendInterrupt(callback: (Boolean, String) -> Unit) {
        try {
            val wsPayload = JsonObject().apply {
                addProperty("type", "interrupt")
            }
            activeWebSocket?.send(wsPayload.toString())
        } catch (_: Exception) {}

        val requestBody = "".toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/interrupt")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Falha ao interromper")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, "Interrompido")
            }
        })
    }

    fun resolveConfirm(key: String, accepted: Boolean, callback: (Boolean, String) -> Unit) {
        val payload = JsonObject().apply {
            addProperty("key", key)
            addProperty("accepted", accepted)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/confirm/resolve")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Falha ao resolver confirmação")
            }

            override fun onResponse(call: Call, response: Response) {
                val ok = response.isSuccessful
                val body = response.body?.string() ?: ""
                val msg = try {
                    gson.fromJson(body, JsonObject::class.java).optString("message", "Resolvido")
                } catch (_: Exception) {
                    if (ok) "Confirmação enviada" else "Erro ${response.code}"
                }
                callback(ok, msg)
            }
        })
    }

    fun sendVisionImage(imageBase64: String, mimeType: String = "image/jpeg", prompt: String = "", callback: (Boolean, String) -> Unit) {
        val payload = JsonObject().apply {
            addProperty("image", imageBase64)
            addProperty("mime_type", mimeType)
            addProperty("prompt", prompt)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/mobile/vision")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Falha ao enviar imagem")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, if (response.isSuccessful) "Imagem enviada para Evie" else "Erro ${response.code}")
            }
        })
    }

    fun uploadFile(
        fileBytes: ByteArray,
        fileName: String,
        mimeType: String = "application/octet-stream",
        callback: (Boolean, String) -> Unit
    ) {
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file",
                fileName,
                fileBytes.toRequestBody(mimeType.toMediaType())
            )
            .build()

        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/upload")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Falha ao enviar arquivo")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, if (response.isSuccessful) "Arquivo $fileName enviado" else "Erro ${response.code}")
            }
        })
    }

    fun syncOfflineNotes(notes: List<String>, callback: (Boolean, Int) -> Unit) {
        val array = com.google.gson.JsonArray().apply {
            notes.forEach { add(it) }
        }
        val payload = JsonObject().apply {
            add("notes", array)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/mobile/offline_sync")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, 0)
            }

            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful) {
                    val body = response.body?.string() ?: ""
                    val count = try {
                        gson.fromJson(body, JsonObject::class.java).get("synced_count").asInt
                    } catch (_: Exception) { notes.size }
                    callback(true, count)
                } else {
                    callback(false, 0)
                }
            }
        })
    }

    fun requestSessionHandoff(target: String, callback: (Boolean, String) -> Unit) {
        val payload = JsonObject().apply {
            addProperty("target", target)
            addProperty("device_id", config.deviceName)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/session/handoff")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Falha no handoff de áudio")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, if (response.isSuccessful) "Áudio transferido para $target" else "Erro ${response.code}")
            }
        })
    }

    fun setProactivityMode(mode: String, callback: (Boolean, String) -> Unit) {
        val payload = JsonObject().apply {
            addProperty("mode", mode)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/proactivity/mode")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Erro ao alterar modo")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, if (response.isSuccessful) "Modo alterado para $mode" else "Erro ${response.code}")
            }
        })
    }

    fun pauseProactivity(minutes: Int = 60, callback: (Boolean, String) -> Unit) {
        val payload = JsonObject().apply {
            addProperty("minutes", minutes)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/proactivity/pause")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback(false, e.localizedMessage ?: "Erro ao pausar")
            }

            override fun onResponse(call: Call, response: Response) {
                callback(response.isSuccessful, if (response.isSuccessful) "Pausado por ${minutes}m" else "Erro ${response.code}")
            }
        })
    }

    fun sendMobileTelemetry(battery: Int?, screenOn: Boolean, screenName: String, callback: ((Boolean) -> Unit)? = null) {
        val payload = JsonObject().apply {
            if (battery != null) addProperty("battery", battery)
            addProperty("screen_on", screenOn)
            addProperty("app_screen", screenName)
        }
        val requestBody = payload.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("${config.httpBaseUrl}/api/mobile/telemetry")
            .header("Authorization", "Bearer ${config.authToken}")
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                callback?.invoke(false)
            }

            override fun onResponse(call: Call, response: Response) {
                callback?.invoke(response.isSuccessful)
            }
        })
    }

    fun connectWebSocket(listener: WebSocketListener): WebSocket {
        activeWebSocket?.close(1000, "Reconnecting")
        val request = Request.Builder()
            .url("${config.wsBaseUrl}/ws?token=${config.authToken}")
            .build()

        val ws = client.newWebSocket(request, listener)
        activeWebSocket = ws
        return ws
    }

    fun disconnect() {
        activeWebSocket?.close(1000, "App closed")
        activeWebSocket = null
    }
}
