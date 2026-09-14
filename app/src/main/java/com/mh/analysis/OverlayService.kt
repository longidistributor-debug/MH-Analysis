package com.mh.analysis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import kotlin.concurrent.thread
import kotlin.math.abs

class OverlayService : Service() {
    private lateinit var wm: WindowManager
    private lateinit var bubbleView: TextView
    private var panel: LinearLayout? = null
    private var chart: WebView? = null
    private var status: TextView? = null
    private val prefs by lazy { getSharedPreferences("mh", MODE_PRIVATE) }

    private var symbol = "XAUUSD"
    private var period = "15m"
    private var data: List<Candle> = emptyList()
    private var loadedAt = 0L
    private var ready = false
    private var busy = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        readSelection()
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        startForegroundMode()
        createBubble()
    }

    private fun readSelection() {
        symbol = prefs.getString("symbol", "XAUUSD") ?: "XAUUSD"
        period = prefs.getString("period", "15m") ?: "15m"
    }

    private fun startForegroundMode() {
        val id = "mh_analysis"
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(NotificationChannel(id, "MH Analysis", NotificationManager.IMPORTANCE_LOW))
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, id) else Notification.Builder(this)
        val notification = builder
            .setContentTitle("MH Analysis running")
            .setContentText("Gold + BTC floating analysis")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .build()
        startForeground(210, notification)
    }

    private fun overlayType(): Int = if (Build.VERSION.SDK_INT >= 26) {
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
    } else {
        WindowManager.LayoutParams.TYPE_PHONE
    }

    private fun createBubble() {
        bubbleView = TextView(this).apply {
            text = "MH"
            textSize = 16f
            gravity = Gravity.CENTER
            setTextColor(Color.BLACK)
            setTypeface(typeface, Typeface.BOLD)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.WHITE)
                setStroke(dp(2), Color.GRAY)
            }
        }
        val params = WindowManager.LayoutParams(
            dp(60), dp(60), overlayType(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = dp(18)
            y = dp(210)
        }

        var startX = 0
        var startY = 0
        var touchX = 0f
        var touchY = 0f
        var moved = false

        bubbleView.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x
                    startY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - touchX).toInt()
                    val dy = (event.rawY - touchY).toInt()
                    if (abs(dx) > dp(4) || abs(dy) > dp(4)) moved = true
                    params.x = startX + dx
                    params.y = startY + dy
                    wm.updateViewLayout(bubbleView, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) togglePanel()
                    true
                }
                else -> false
            }
        }
        wm.addView(bubbleView, params)
    }

    private fun togglePanel() {
        if (panel == null) showPanel() else hidePanel()
    }

    private fun showPanel() {
        readSelection()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(10), dp(10), dp(10))
            background = GradientDrawable().apply {
                setColor(Color.rgb(6, 6, 6))
                cornerRadius = dp(16).toFloat()
                setStroke(dp(1), Color.GRAY)
            }
        }
        panel = root

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        header.addView(textView("MH ANALYSIS", 14f, true), LinearLayout.LayoutParams(0, dp(42), 1f))
        header.addView(Button(this).apply {
            text = "—"
            setOnClickListener { hidePanel() }
        }, LinearLayout.LayoutParams(dp(48), dp(40)))
        root.addView(header)

        val pairRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        pairRow.addView(Button(this).apply {
            text = "GOLD"
            setOnClickListener { switchPair("XAUUSD") }
        }, LinearLayout.LayoutParams(0, dp(42), 1f))
        pairRow.addView(Button(this).apply {
            text = "BTC"
            setOnClickListener { switchPair("BTCUSDT") }
        }, LinearLayout.LayoutParams(0, dp(42), 1f))
        root.addView(pairRow)

        chart = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            setBackgroundColor(Color.BLACK)
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    ready = true
                    loadData()
                }
            }
            loadUrl("file:///android_asset/chart.html")
        }
        root.addView(chart, LinearLayout.LayoutParams(-1, dp(300)))

        root.addView(Button(this).apply {
            text = "NEW ANALYZE"
            setTextColor(Color.BLACK)
            setBackgroundColor(Color.WHITE)
            setOnClickListener { analyze() }
        }, LinearLayout.LayoutParams(-1, dp(48)))

        status = textView("$symbol • $period", 11f).apply { setPadding(0, dp(8), 0, 0) }
        root.addView(status)

        val params = WindowManager.LayoutParams(
            dp(360), dp(520), overlayType(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = dp(8)
            y = dp(55)
        }
        wm.addView(root, params)
    }

    private fun switchPair(next: String) {
        if (symbol == next) return
        symbol = next
        prefs.edit().putString("symbol", symbol).apply()
        data = emptyList()
        loadedAt = 0L
        chart?.evaluateJavascript("clearChart()", null)
        status?.text = "Loading $symbol..."
        loadData()
    }

    private fun loadData() {
        if (!ready || busy) return
        val accessKey = prefs.getString("api_key", "")?.trim().orEmpty()
        if (accessKey.isBlank()) {
            status?.text = "API key missing"
            return
        }
        busy = true
        thread {
            try {
                val (candles, _) = FcsClient.history(accessKey, symbol, period, 220, false)
                data = candles
                loadedAt = System.currentTimeMillis()
                val evaluated = SignalStore.evaluate(this, symbol, candles)
                Handler(Looper.getMainLooper()).post {
                    render(candles)
                    busy = false
                    if (evaluated != null && evaluated.state in setOf("WIN", "LOSS", "EXPIRED")) {
                        status?.text = "SIGNAL ${evaluated.state} • record saved"
                    } else {
                        showActive()
                    }
                }
            } catch (e: Exception) {
                Handler(Looper.getMainLooper()).post {
                    busy = false
                    status?.text = "Load failed: ${e.message}"
                }
            }
        }
    }

    private fun render(candles: List<Candle>) {
        val arr = JSONArray()
        candles.forEach {
            arr.put(JSONObject().put("t", it.t).put("o", it.o).put("h", it.h).put("l", it.l).put("c", it.c).put("v", it.v))
        }
        chart?.evaluateJavascript(
            "renderCandles(${JSONObject.quote(arr.toString())},${JSONObject.quote(symbol)},${JSONObject.quote(period)})",
            null
        )
        showOverlay(SignalStore.loadActive(this, symbol))
    }

    private fun analyze() {
        if (busy) return
        val fresh = data.isNotEmpty() && System.currentTimeMillis() - loadedAt < 60_000L
        if (!fresh) {
            status?.text = "Refreshing data..."
            loadData()
            return
        }
        val signal = AnalysisEngine.analyze(symbol, period, data)
        if (signal == null) {
            status?.text = "NO VALID EDGE"
            return
        }
        SignalStore.replaceWith(this, signal)
        showActive()
        showOverlay(SignalStore.loadActive(this, symbol))
    }

    private fun showActive() {
        val active = SignalStore.loadActive(this, symbol)
        if (active == null) {
            status?.text = "$symbol • $period • no active signal"
            showOverlay(null)
            return
        }
        val s = active.signal
        val fvg = if (s.fvgLow != null && s.fvgHigh != null) {
            "${s.fvgType} FVG ${price(s.fvgLow)}-${price(s.fvgHigh)}"
        } else {
            "No FVG"
        }
        status?.text = "${s.direction} ${s.score}/100 • ${active.state}\n" +
            "Entry ${price(s.entry)}  SL ${price(s.sl)}  TP1 ${price(s.tp1)}\n" +
            "Bull ${s.bullScore} / Bear ${s.bearScore} • RSI ${String.format(Locale.US, "%.1f", s.rsi)}\n" +
            fvg
    }

    private fun showOverlay(active: ActiveSignal?) {
        if (active == null) {
            chart?.evaluateJavascript("setSignal(null)", null)
            return
        }
        val s = active.signal
        val j = JSONObject()
            .put("entry", s.entry).put("sl", s.sl).put("tp1", s.tp1).put("tp2", s.tp2)
            .put("state", active.state).put("validBars", s.validBars)
            .put("fvgType", s.fvgType).put("fvgLow", s.fvgLow).put("fvgHigh", s.fvgHigh)
        chart?.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})", null)
    }

    private fun price(v: Double?): String = when {
        v == null -> "-"
        abs(v) >= 100 -> String.format(Locale.US, "%.2f", v)
        else -> String.format(Locale.US, "%.5f", v)
    }

    private fun hidePanel() {
        panel?.let { runCatching { wm.removeView(it) } }
        panel = null
        chart = null
        status = null
        ready = false
    }

    private fun textView(value: String, size: Float, bold: Boolean = false) = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(Color.WHITE)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        hidePanel()
        if (::bubbleView.isInitialized) runCatching { wm.removeView(bubbleView) }
        super.onDestroy()
    }
}
