package com.mh.analysis

import android.content.Context
import android.webkit.JavascriptInterface

/**
 * Narrow bridge from the bundled FCS chart to the app's native candle cache.
 * It intentionally exposes only market-data callbacks so chart and analysis
 * share the same FX:XAUUSD live candle stream.
 */
class FcsChartBridge(context: Context) {
    private val appContext = context.applicationContext

    init { FcsClient.init(appContext) }

    @JavascriptInterface
    fun onCandle(timeframe: String, time: Long, open: Double, high: Double, low: Double, close: Double, volume: Double) {
        if (!open.isFinite() || !high.isFinite() || !low.isFinite() || !close.isFinite()) return
        FcsClient.applyLiveCandle(
            "XAUUSD",
            normalizeTf(timeframe),
            Candle(time, open, high, low, close, volume)
        )
    }

    @JavascriptInterface
    fun onPrice(timeframe: String, time: Long, price: Double) {
        if (!price.isFinite()) return
        FcsClient.applyLivePrice("XAUUSD", normalizeTf(timeframe), time, price)
    }

    private fun normalizeTf(raw: String): String = when (raw.trim().lowercase()) {
        "1", "1m" -> "1m"
        "5", "5m" -> "5m"
        "15", "15m" -> "15m"
        "30", "30m" -> "30m"
        "60", "1h" -> "1h"
        "120", "2h" -> "2h"
        "240", "4h" -> "4h"
        "1d" -> "1D"
        "1w" -> "1W"
        else -> raw.trim()
    }
}
