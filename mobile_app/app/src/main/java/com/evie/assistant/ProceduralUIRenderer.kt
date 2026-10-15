package com.evie.assistant

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class ProceduralUIRenderer(
    private val context: Context,
    private val container: ViewGroup,
    private val onActionTriggered: (actionId: String, payload: Map<String, Any>?) -> Unit
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val renderedViews = mutableMapOf<String, View>()

    fun clearAll() {
        container.removeAllViews()
        renderedViews.clear()
    }

    fun renderTree(uiTree: List<UIComponent>) {
        for (component in uiTree) {
            renderOrUpdateComponent(component)
        }
    }

    fun renderOrUpdateComponent(comp: UIComponent) {
        val existingView = renderedViews[comp.id]
        if (existingView != null) {
            val index = container.indexOfChild(existingView)
            if (index >= 0) {
                container.removeViewAt(index)
                val newView = buildComponentView(comp)
                container.addView(newView, index)
                renderedViews[comp.id] = newView
                animateEntrance(newView)
                return
            }
        }

        val newView = buildComponentView(comp)
        container.addView(newView)
        renderedViews[comp.id] = newView
        animateEntrance(newView)
    }

    private fun animateEntrance(view: View) {
        view.alpha = 0f
        view.translationY = 20f
        view.animate()
            .alpha(1f)
            .translationY(0f)
            .setDuration(300)
            .start()
    }

    private fun buildComponentView(comp: UIComponent): View {
        return when (comp.getResolvedType()) {
            ComponentType.METRIC_CARD, ComponentType.STAT_GRID -> buildMetricCard(comp)
            ComponentType.INTERACTIVE_CHECKLIST -> buildChecklistCard(comp)
            ComponentType.ACTION_DECISION_CARD -> buildActionDecisionCard(comp)
            ComponentType.CODE_SNIPPET_DIFF -> buildCodeSnippetCard(comp)
            ComponentType.TIMELINE_BLOCK -> buildTimelineCard(comp)
            ComponentType.EPHEMERAL_TOAST -> buildEphemeralToast(comp)
            ComponentType.GEO_MAP_CARD -> buildGeoMapCard(comp)
        }
    }

    // 1. MetricCard / StatGrid
    private fun buildMetricCard(comp: UIComponent): View {
        val panel = createBasePanel()
        if (!comp.title.isNullOrEmpty()) {
            panel.addView(createHeaderTitle(comp.title))
        }

        val metricsList: List<MetricItem> = comp.metrics ?: emptyList()
        val gridLayout = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(4) }
            weightSum = metricsList.size.toFloat().coerceAtLeast(1f)
        }

        for (metric in metricsList) {
            val cell = LinearLayout(context).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                    marginEnd = dp(3)
                }
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setBackgroundColor(Color.parseColor("#081220"))
                setPadding(dp(4), dp(4), dp(4), dp(4))
            }

            val labelTv = TextView(context).apply {
                text = metric.label.uppercase()
                textSize = 8f
                typeface = Typeface.MONOSPACE
                setTextColor(Color.parseColor("#64748B"))
                gravity = Gravity.CENTER
            }

            val valueTv = TextView(context).apply {
                text = metric.value
                textSize = 12f
                typeface = Typeface.MONOSPACE
                setTypeface(typeface, Typeface.BOLD)
                setTextColor(Color.parseColor("#00F0FF"))
                gravity = Gravity.CENTER
            }

            cell.addView(labelTv)
            cell.addView(valueTv)

            if (!metric.delta.isNullOrEmpty()) {
                val deltaTv = TextView(context).apply {
                    text = metric.delta
                    textSize = 8f
                    typeface = Typeface.MONOSPACE
                    val isPositive = metric.delta.startsWith("+")
                    setTextColor(if (isPositive) Color.parseColor("#00E676") else Color.parseColor("#FF4D5A"))
                    gravity = Gravity.CENTER
                }
                cell.addView(deltaTv)
            }

            gridLayout.addView(cell)
        }

        panel.addView(gridLayout)
        return panel
    }

    // 2. InteractiveChecklist
    private fun buildChecklistCard(comp: UIComponent): View {
        val panel = createBasePanel()
        if (!comp.title.isNullOrEmpty()) {
            panel.addView(createHeaderTitle(comp.title))
        }

        val itemsList: List<ChecklistItem> = comp.checklistItems ?: emptyList()
        for (item in itemsList) {
            val row = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = dp(3) }
            }

            val cb = CheckBox(context).apply {
                isChecked = item.completed
                setOnCheckedChangeListener { _, isChecked ->
                    onActionTriggered(
                        "checklist_toggle",
                        mapOf(
                            "component_id" to comp.id,
                            "item_id" to item.id,
                            "completed" to isChecked
                        )
                    )
                }
            }

            val textTv = TextView(context).apply {
                text = item.text
                textSize = 10f
                typeface = Typeface.MONOSPACE
                setTextColor(if (item.completed) Color.parseColor("#64748B") else Color.parseColor("#E2E8F0"))
            }

            row.addView(cb)
            row.addView(textTv)
            panel.addView(row)
        }

        return panel
    }

    // 3. ActionDecisionCard
    private fun buildActionDecisionCard(comp: UIComponent): View {
        val panel = createBasePanel()
        if (!comp.title.isNullOrEmpty()) {
            panel.addView(createHeaderTitle("⚡ ${comp.title}"))
        }

        if (!comp.body.isNullOrEmpty()) {
            val bodyTv = TextView(context).apply {
                text = comp.body
                textSize = 9.5f
                typeface = Typeface.MONOSPACE
                setTextColor(Color.parseColor("#CBD5E1"))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = dp(2) }
            }
            panel.addView(bodyTv)
        }

        // Action Buttons Row
        val buttonsRow = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(6) }
        }

        val actionsList: List<ActionItem> = comp.actions ?: emptyList()
        for (action in actionsList) {
            val btn = TextView(context).apply {
                text = action.label
                textSize = 9f
                typeface = Typeface.MONOSPACE
                setTypeface(typeface, Typeface.BOLD)
                gravity = Gravity.CENTER
                includeFontPadding = false
                setPadding(dp(8), dp(5), dp(8), dp(5))
                isClickable = true
                isFocusable = true

                when (action.style?.lowercase()) {
                    "danger" -> {
                        setBackgroundResource(R.drawable.bg_hud_button_interrupt)
                        setTextColor(Color.parseColor("#FF4D5A"))
                    }
                    "success" -> {
                        setBackgroundResource(R.drawable.bg_hud_button_blue)
                        setTextColor(Color.parseColor("#00E676"))
                    }
                    "accent", "warning" -> {
                        setBackgroundResource(R.drawable.bg_hud_button_gold)
                        setTextColor(Color.parseColor("#F59E0B"))
                    }
                    else -> {
                        setBackgroundResource(R.drawable.bg_hud_button_blue)
                        setTextColor(Color.parseColor("#00F0FF"))
                    }
                }

                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { marginEnd = dp(6) }

                setOnClickListener {
                    onActionTriggered(action.id, action.payload ?: emptyMap())
                }
            }
            buttonsRow.addView(btn)
        }

        panel.addView(buttonsRow)
        return panel
    }

    // 4. CodeSnippetDiff
    private fun buildCodeSnippetCard(comp: UIComponent): View {
        val panel = createBasePanel()
        val titleText = if (comp.filePath.isNullOrEmpty()) "❖ CODE INSPECTOR" else "❖ ${comp.filePath}"
        panel.addView(createHeaderTitle(titleText))

        val codeBox = TextView(context).apply {
            text = comp.codeContent ?: ""
            textSize = 9f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#7DD3FC"))
            setBackgroundColor(Color.parseColor("#040812"))
            setPadding(dp(6), dp(6), dp(6), dp(6))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(4) }
        }
        panel.addView(codeBox)

        val btnRow = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(4) }
        }

        // Copy button
        val copyBtn = TextView(context).apply {
            text = "📋 COPIAR"
            textSize = 8.5f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#00F0FF"))
            setBackgroundResource(R.drawable.bg_hud_button_blue)
            setPadding(dp(6), dp(4), dp(6), dp(4))
            includeFontPadding = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { marginEnd = dp(6) }
            setOnClickListener {
                val clip = ClipData.newPlainText("code", comp.codeContent ?: "")
                (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(clip)
                Toast.makeText(context, "Código copiado!", Toast.LENGTH_SHORT).show()
            }
        }
        btnRow.addView(copyBtn)

        val actionsList: List<ActionItem> = comp.actions ?: emptyList()
        for (act in actionsList) {
            val actBtn = TextView(context).apply {
                text = act.label
                textSize = 8.5f
                typeface = Typeface.MONOSPACE
                setTextColor(Color.parseColor("#F59E0B"))
                setBackgroundResource(R.drawable.bg_hud_button_gold)
                setPadding(dp(6), dp(4), dp(6), dp(4))
                includeFontPadding = false
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { marginEnd = dp(6) }
                setOnClickListener {
                    onActionTriggered(act.id, act.payload ?: emptyMap())
                }
            }
            btnRow.addView(actBtn)
        }

        panel.addView(btnRow)
        return panel
    }

    // 5. TimelineBlock
    private fun buildTimelineCard(comp: UIComponent): View {
        val panel = createBasePanel()
        panel.addView(createHeaderTitle(comp.title ?: "◈ TIMELINE / SCHEDULE"))

        val eventsList: List<TimelineEvent> = comp.timelineEvents ?: emptyList()
        for (evt in eventsList) {
            val row = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = dp(3) }
            }

            val timeTv = TextView(context).apply {
                text = evt.time
                textSize = 8.5f
                typeface = Typeface.MONOSPACE
                setTypeface(typeface, Typeface.BOLD)
                setTextColor(Color.parseColor("#00F0FF"))
                layoutParams = LinearLayout.LayoutParams(dp(50), LinearLayout.LayoutParams.WRAP_CONTENT)
            }

            val titleTv = TextView(context).apply {
                text = evt.title
                textSize = 9.5f
                typeface = Typeface.MONOSPACE
                setTextColor(Color.parseColor("#E2E8F0"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }

            val statusTv = TextView(context).apply {
                text = evt.status?.uppercase() ?: ""
                textSize = 8f
                typeface = Typeface.MONOSPACE
                setTextColor(
                    when (evt.status?.lowercase()) {
                        "done", "completed" -> Color.parseColor("#00E676")
                        "active", "current" -> Color.parseColor("#F59E0B")
                        else -> Color.parseColor("#64748B")
                    }
                )
            }

            row.addView(timeTv)
            row.addView(titleTv)
            row.addView(statusTv)
            panel.addView(row)
        }

        return panel
    }

    // 6. EphemeralToast
    private fun buildEphemeralToast(comp: UIComponent): View {
        val panel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundResource(R.drawable.bg_hud_panel)
            setPadding(dp(8), dp(5), dp(8), dp(5))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(3) }
        }

        val iconTv = TextView(context).apply {
            text = "⚡ "
            textSize = 10f
            setTextColor(Color.parseColor("#F59E0B"))
        }

        val bodyTv = TextView(context).apply {
            text = comp.body ?: comp.title ?: ""
            textSize = 9f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#00F0FF"))
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        panel.addView(iconTv)
        panel.addView(bodyTv)

        val duration = (comp.durationSeconds ?: 5) * 1000L
        mainHandler.postDelayed({
            panel.animate()
                .alpha(0f)
                .translationY(-15f)
                .setDuration(400)
                .setListener(object : AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: Animator) {
                        container.removeView(panel)
                        renderedViews.remove(comp.id)
                    }
                })
                .start()
        }, duration)

        return panel
    }

    private fun buildGeoMapCard(comp: UIComponent): View {
        val panel = createBasePanel()
        if (!comp.title.isNullOrEmpty()) {
            panel.addView(createHeaderTitle(comp.title))
        }

        val radarView = GeoRadarMapView(context).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(160)
            ).apply { topMargin = dp(4) }
            val lat = comp.latitude ?: -23.5505
            val lon = comp.longitude ?: -46.6333
            setGeoData(lat, lon, comp.locationName, comp.weatherInfo, comp.markers)
            onMarkerSelectedListener = { marker ->
                onActionTriggered(
                    "geo_marker_selected",
                    mapOf("label" to marker.label, "lat" to marker.lat, "lon" to marker.lon)
                )
            }
        }
        panel.addView(radarView)
        return panel
    }

    private fun createBasePanel(): LinearLayout {
        return LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_hud_panel)
            setPadding(dp(6), dp(5), dp(6), dp(5))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(4) }
        }
    }

    private fun createHeaderTitle(title: String): TextView {
        return TextView(context).apply {
            text = title
            textSize = 9.5f
            typeface = Typeface.MONOSPACE
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.parseColor("#00F0FF"))
        }
    }

    private fun dp(dpVal: Int): Int {
        return (dpVal * context.resources.displayMetrics.density).toInt()
    }
}
