package com.evie.assistant

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PointF
import android.graphics.RectF
import android.graphics.SweepGradient
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.animation.LinearInterpolator
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.sin

class GeoRadarMapView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var sweepAngle = 0f
    private var pulsePhase = 0f
    private var targetLockAnim = 0f

    var userLat: Double = -23.5461
    var userLon: Double = -46.6289
    var locationName: String = "SÃO PAULO, SP // BRASIL"
    var weatherInfo: String = "24°C • CÉU LIMPO"
    var pingMs: Int = 18
    var satellites: Int = 14
    var zoomScale: Float = 1.0f

    private val markersList = mutableListOf<GeoMarker>()
    private var selectedMarker: GeoMarker? = null
    var onMarkerSelectedListener: ((GeoMarker) -> Unit)? = null

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#E6020810")
        style = Paint.Style.FILL
    }
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#0D3347")
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2600F0FF")
        style = Paint.Style.STROKE
        strokeWidth = 1.2f
    }
    private val axisPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#4D00F0FF")
        style = Paint.Style.STROKE
        strokeWidth = 1.5f
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00F0FF")
        textSize = 22f
        typeface = Typeface.MONOSPACE
    }
    private val subTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#7DD3FC")
        textSize = 18f
        typeface = Typeface.MONOSPACE
    }
    private val markerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val sweepPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private var animator: ValueAnimator? = null

    init {
        // Default tactical markers
        markersList.add(
            GeoMarker(
                lat = -23.550520,
                lon = -46.633308,
                label = "BASE PC HOST",
                statusColor = "#00F0FF",
                markerType = "base",
                pulse = true
            )
        )
        markersList.add(
            GeoMarker(
                lat = -23.546100,
                lon = -46.628900,
                label = "POCO X7 MOBILE",
                statusColor = "#00E676",
                markerType = "mobile",
                pulse = true
            )
        )
        selectedMarker = markersList[1]
        startAnimation()
    }

    private fun startAnimation() {
        animator?.cancel()
        animator = ValueAnimator.ofFloat(0f, 360f).apply {
            duration = 3000
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener {
                sweepAngle = (sweepAngle + 2.5f) % 360f
                pulsePhase = (pulsePhase + 0.06f) % (2f * Math.PI.toFloat())
                targetLockAnim = (targetLockAnim + 0.08f) % (2f * Math.PI.toFloat())
                invalidate()
            }
            start()
        }
    }

    fun setGeoData(
        lat: Double,
        lon: Double,
        location: String? = null,
        weather: String? = null,
        markers: List<GeoMarker>? = null
    ) {
        userLat = lat
        userLon = lon
        if (!location.isNullOrEmpty()) locationName = location
        if (!weather.isNullOrEmpty()) weatherInfo = weather
        if (markers != null && markers.isNotEmpty()) {
            markersList.clear()
            markersList.addAll(markers)
            selectedMarker = markersList.firstOrNull()
        }
        invalidate()
    }

    fun updateMobileLocation(lat: Double, lon: Double) {
        userLat = lat
        userLon = lon
        val mob = markersList.firstOrNull { it.markerType == "mobile" || it.label.contains("POCO", ignoreCase = true) }
        if (mob != null) {
            val idx = markersList.indexOf(mob)
            markersList[idx] = mob.copy(lat = lat, lon = lon)
        } else {
            markersList.add(GeoMarker(lat, lon, "POCO X7 MOBILE", "#00E676", "mobile", true))
        }
        invalidate()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_DOWN) {
            val bounds = getRadarBounds()
            val cx = bounds[0]
            val cy = bounds[1]
            val radius = bounds[2]
            var clicked: GeoMarker? = null
            for (m in markersList) {
                val pt = projectMarker(m, cx, cy, radius)
                val dist = hypot((event.x - pt.x).toDouble(), (event.y - pt.y).toDouble())
                if (dist <= 40.0) {
                    clicked = m
                    break
                }
            }
            if (clicked != null) {
                selectedMarker = clicked
                onMarkerSelectedListener?.invoke(clicked)
            } else if (markersList.isNotEmpty()) {
                val nextIdx = ((markersList.indexOf(selectedMarker) + 1) % markersList.size)
                selectedMarker = markersList[nextIdx]
                onMarkerSelectedListener?.invoke(selectedMarker!!)
            }
            invalidate()
            return true
        }
        return super.onTouchEvent(event)
    }

    private fun getRadarBounds(): FloatArray {
        val w = width.toFloat()
        val h = height.toFloat()
        val topOffset = 42f
        val bottomOffset = 46f
        val availH = (h - topOffset - bottomOffset).coerceAtLeast(40f)
        val availW = (w - 24f).coerceAtLeast(40f)
        val radius = (min(availW, availH) / 2f) - 6f
        val cx = w / 2f
        val cy = topOffset + (availH / 2f)
        return floatArrayOf(cx, cy, radius.coerceAtLeast(15f))
    }

    private fun projectMarker(m: GeoMarker, cx: Float, cy: Float, radius: Float): PointF {
        val dLat = (m.lat - userLat) * 111.0
        val dLon = (m.lon - userLon) * 111.0 * cos(Math.toRadians(userLat))
        val scale = radius / (50.0f / zoomScale)
        val px = cx + (dLon * scale).toFloat()
        val py = cy - (dLat * scale).toFloat()
        return PointF(px, py)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        val h = height.toFloat()

        // Cyberpunk Box Container
        val roundRect = RectF(2f, 2f, w - 2f, h - 2f)
        canvas.drawRoundRect(roundRect, 10f, 10f, bgPaint)
        canvas.drawRoundRect(roundRect, 10f, 10f, borderPaint)

        // Header OSD
        textPaint.color = Color.parseColor("#00F0FF")
        textPaint.textSize = 21f
        canvas.drawText("◈ TACTICAL RADAR // GEOSPATIAL HUD", 14f, 28f, textPaint)

        val isBlink = ((System.currentTimeMillis() / 400) % 2L) == 0L
        subTextPaint.color = if (isBlink) Color.parseColor("#00E676") else Color.parseColor("#008844")
        subTextPaint.textSize = 18f
        val actText = "[ONLINE 60FPS]"
        val actWidth = subTextPaint.measureText(actText)
        canvas.drawText(actText, w - actWidth - 14f, 28f, subTextPaint)

        val bounds = getRadarBounds()
        val cx = bounds[0]
        val cy = bounds[1]
        val radius = bounds[2]

        // Concentric Rings
        val fractions = floatArrayOf(0.25f, 0.50f, 0.75f, 1.00f)
        val labels = arrayOf("12KM", "25KM", "37KM", "50KM")
        for (i in fractions.indices) {
            val r = radius * fractions[i]
            canvas.drawCircle(cx, cy, r, gridPaint)
            subTextPaint.color = Color.parseColor("#4D00F0FF")
            subTextPaint.textSize = 15f
            canvas.drawText(labels[i], cx + 4f, cy - r + 16f, subTextPaint)
        }

        // Axes
        canvas.drawLine(cx - radius, cy, cx + radius, cy, axisPaint)
        canvas.drawLine(cx, cy - radius, cx, cy + radius, axisPaint)

        // Cardinal Points
        subTextPaint.color = Color.parseColor("#00F0FF")
        subTextPaint.textSize = 17f
        canvas.drawText("N", cx - 6f, cy - radius - 4f, subTextPaint)
        canvas.drawText("S", cx - 6f, cy + radius + 18f, subTextPaint)
        canvas.drawText("E", cx + radius + 6f, cy + 6f, subTextPaint)
        canvas.drawText("W", cx - radius - 20f, cy + 6f, subTextPaint)

        // Sweep Beam
        canvas.save()
        val sweepGrad = SweepGradient(
            cx, cy,
            intArrayOf(
                Color.parseColor("#7300F0FF"),
                Color.parseColor("#2600F0FF"),
                Color.TRANSPARENT,
                Color.TRANSPARENT
            ),
            floatArrayOf(0.0f, 0.08f, 0.18f, 1.0f)
        )
        sweepPaint.shader = sweepGrad
        canvas.rotate(sweepAngle, cx, cy)
        canvas.drawCircle(cx, cy, radius, sweepPaint)
        sweepPaint.shader = null

        // Sweep frontline
        axisPaint.color = Color.parseColor("#D900F0FF")
        axisPaint.strokeWidth = 2f
        canvas.drawLine(cx, cy, cx + radius, cy, axisPaint)
        canvas.restore()

        // Markers
        for (m in markersList) {
            val pt = projectMarker(m, cx, cy, radius)
            val isSelected = (m == selectedMarker)
            val col = try { Color.parseColor(m.statusColor) } catch (_: Exception) { Color.parseColor("#00F0FF") }

            // Pulse Ring
            if (m.pulse) {
                val pr = 10f + 8f * (1f + sin(pulsePhase))
                val pAlpha = ((1f - (pr - 10f) / 16f) * 160f).toInt().coerceIn(20, 200)
                markerPaint.color = col
                markerPaint.alpha = pAlpha
                markerPaint.style = Paint.Style.STROKE
                markerPaint.strokeWidth = 1.5f
                canvas.drawCircle(pt.x, pt.y, pr, markerPaint)
            }

            // Core
            markerPaint.color = col
            markerPaint.alpha = 255
            markerPaint.style = Paint.Style.FILL
            if (m.markerType == "base") {
                canvas.drawRect(pt.x - 5f, pt.y - 5f, pt.x + 5f, pt.y + 5f, markerPaint)
            } else {
                canvas.drawCircle(pt.x, pt.y, 6f, markerPaint)
            }

            // Label
            subTextPaint.color = col
            subTextPaint.textSize = 17f
            canvas.drawText(m.label, pt.x + 10f, pt.y + 4f, subTextPaint)

            // Target Lock Reticle
            if (isSelected) {
                canvas.save()
                canvas.translate(pt.x, pt.y)
                canvas.rotate(Math.toDegrees(targetLockAnim.toDouble()).toFloat())
                markerPaint.color = Color.parseColor("#E600F0FF")
                markerPaint.style = Paint.Style.STROKE
                markerPaint.strokeWidth = 2f
                val s = 14f
                canvas.drawLine(-s, -s, -s + 6f, -s, markerPaint)
                canvas.drawLine(-s, -s, -s, -s + 6f, markerPaint)
                canvas.drawLine(s, -s, s - 6f, -s, markerPaint)
                canvas.drawLine(s, -s, s, -s + 6f, markerPaint)
                canvas.drawLine(-s, s, -s + 6f, s, markerPaint)
                canvas.drawLine(-s, s, -s, s - 6f, markerPaint)
                canvas.drawLine(s, s, s - 6f, s, markerPaint)
                canvas.drawLine(s, s, s, s - 6f, markerPaint)
                canvas.restore()

                subTextPaint.color = Color.WHITE
                subTextPaint.textSize = 15f
                canvas.drawText("[LOCK]", pt.x + 10f, pt.y + 20f, subTextPaint)
            }
        }

        // Bottom OSD Telemetry
        subTextPaint.color = Color.parseColor("#00F0FF")
        subTextPaint.textSize = 16f
        val line1 = "LAT: ${"%.4f".format(userLat)}° LON: ${"%.4f".format(userLon)}° | SATS: $satellites | PING: ${pingMs}ms"
        val line2 = "$locationName | $weatherInfo"
        canvas.drawText(line1, 14f, h - 22f, subTextPaint)
        canvas.drawText(line2, 14f, h - 6f, subTextPaint)
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        animator?.cancel()
    }
}
