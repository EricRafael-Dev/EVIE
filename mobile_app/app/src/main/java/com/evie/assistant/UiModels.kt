package com.evie.assistant

import com.google.gson.JsonObject
import com.google.gson.annotations.SerializedName

enum class VisualState(val raw: String) {
    @SerializedName("IDLE_OBSERVING")
    IDLE_OBSERVING("IDLE_OBSERVING"),

    @SerializedName("THINKING_DEEP")
    THINKING_DEEP("THINKING_DEEP"),

    @SerializedName("CURIOUS_SPARK")
    CURIOUS_SPARK("CURIOUS_SPARK"),

    @SerializedName("SPEAKING")
    SPEAKING("SPEAKING"),

    @SerializedName("ALERT_URGENT")
    ALERT_URGENT("ALERT_URGENT"),

    @SerializedName("FOCUS_CALM")
    FOCUS_CALM("FOCUS_CALM"),

    @SerializedName("HAPPY")
    HAPPY("HAPPY"),

    @SerializedName("FOCUSED")
    FOCUSED("FOCUSED"),

    @SerializedName("SLEEPY")
    SLEEPY("SLEEPY"),

    @SerializedName("SURPRISED")
    SURPRISED("SURPRISED");

    companion object {
        fun fromString(str: String?): VisualState {
            val s = str?.uppercase() ?: return IDLE_OBSERVING
            return entries.firstOrNull { it.raw == s } ?: IDLE_OBSERVING
        }
    }
}

enum class ComponentType(val raw: String) {
    @SerializedName("MetricCard")
    METRIC_CARD("MetricCard"),

    @SerializedName("StatGrid")
    STAT_GRID("StatGrid"),

    @SerializedName("InteractiveChecklist")
    INTERACTIVE_CHECKLIST("InteractiveChecklist"),

    @SerializedName("ActionDecisionCard")
    ACTION_DECISION_CARD("ActionDecisionCard"),

    @SerializedName("CodeSnippetDiff")
    CODE_SNIPPET_DIFF("CodeSnippetDiff"),

    @SerializedName("TimelineBlock")
    TIMELINE_BLOCK("TimelineBlock"),

    @SerializedName("EphemeralToast")
    EPHEMERAL_TOAST("EphemeralToast"),

    @SerializedName("GeoMapCard")
    GEO_MAP_CARD("GeoMapCard");

    companion object {
        fun fromString(str: String?): ComponentType {
            val s = str?.trim() ?: return EPHEMERAL_TOAST
            return entries.firstOrNull { it.raw.equals(s, ignoreCase = true) } ?: EPHEMERAL_TOAST
        }
    }
}

data class MetricItem(
    val label: String = "",
    val value: String = "",
    val delta: String? = null,
    val color: String? = null
)

data class ChecklistItem(
    val id: String = "",
    val text: String = "",
    var completed: Boolean = false
)

data class ActionItem(
    val id: String = "",
    val label: String = "",
    val style: String? = "primary",
    val payload: Map<String, Any>? = null
)

data class TimelineEvent(
    val time: String = "",
    val title: String = "",
    val status: String? = "upcoming"
)

data class GeoMarker(
    val lat: Double = 0.0,
    val lon: Double = 0.0,
    val label: String = "",
    @SerializedName("status_color")
    val statusColor: String = "#00f0ff",
    @SerializedName("marker_type")
    val markerType: String = "device",
    val pulse: Boolean = true
)

data class UIComponent(
    val id: String = "",
    val type: String = "EphemeralToast",
    val title: String? = null,
    val body: String? = null,
    val metrics: List<MetricItem>? = null,
    @SerializedName("checklist_items")
    val checklistItems: List<ChecklistItem>? = null,
    val actions: List<ActionItem>? = null,
    @SerializedName("code_content")
    val codeContent: String? = null,
    @SerializedName("file_path")
    val filePath: String? = null,
    val language: String? = null,
    @SerializedName("timeline_events")
    val timelineEvents: List<TimelineEvent>? = null,
    @SerializedName("duration_seconds")
    val durationSeconds: Int? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerializedName("location_name")
    val locationName: String? = null,
    @SerializedName("weather_info")
    val weatherInfo: String? = null,
    val markers: List<GeoMarker>? = null,
    val data: JsonObject? = null
) {
    fun getResolvedType(): ComponentType = ComponentType.fromString(type)
}

data class ProceduralUIPayload(
    val type: String = "procedural_ui",
    @SerializedName("visual_state")
    val visualState: String = "IDLE_OBSERVING",
    @SerializedName("voice_text")
    val voiceText: String? = null,
    @SerializedName("ui_tree")
    val uiTree: List<UIComponent> = emptyList(),
    val timestamp: Double = 0.0,
    @SerializedName("component_id")
    val componentId: String? = null
)

data class UIActionPayload(
    val type: String = "ui_action",
    @SerializedName("action_id")
    val actionId: String,
    @SerializedName("component_id")
    val componentId: String? = null,
    val payload: Map<String, Any>? = null,
    val device: String = "Mobile"
)
