package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max

/**
 * Stores only the current setup for each symbol/timeframe.
 * There is deliberately no trade-record or alarm history here.
 */
object LiveSetupStore {
    private const val PREF = "mh_live_setup_v33"

    data class Evaluation(
        val setup: ActiveSignal?,
        val changed: Boolean = false,
        val reason: String = ""
    )

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)
    private fun key(symbol: String, timeframe: String) =
        "${symbol.uppercase()}|${timeframe.lowercase()}"

    fun load(c: Context, symbol: String, timeframe: String): ActiveSignal? =
        prefs(c).getString(key(symbol, timeframe), null)?.let {
            runCatching { activeFromJson(JSONObject(it)) }.getOrNull()
        }

    fun clear(c: Context, symbol: String, timeframe: String) {
        prefs(c).edit().remove(key(symbol, timeframe)).apply()
    }

    fun clearAll(c: Context) {
        prefs(c).edit().clear().apply()
    }

    private fun save(c: Context, a: ActiveSignal) {
        prefs(c).edit().putString(key(a.signal.symbol, a.signal.timeframe), activeToJson(a).toString()).apply()
    }

    /**
     * Re-evaluates the saved setup against the newest candles only.
     * No fixed bar-count expiry is used. State changes are driven by price,
     * structure and AnalysisEngine.setupCheck().
     */
    fun evaluate(c: Context, symbol: String, timeframe: String, candles: List<Candle>): Evaluation {
        var a = load(c, symbol, timeframe) ?: return Evaluation(null)
        if (candles.size < 20) return Evaluation(a)

        val s = a.signal
        var state = a.state
        var activatedAt = a.activatedAt
        var barsSeen = a.barsSeen
        var changed = false
        var reason = ""

        val created = max(toMillis(s.createdCandleTime), s.createdAt)
        val start = activatedAt ?: created
        val future = candles.filter { toMillis(it.t) > created }

        for (x in future) {
            val t = toMillis(x.t)
            if (state == "PENDING") {
                val touched = x.l <= s.entry && x.h >= s.entry
                if (touched) {
                    state = "TRIGGERED"
                    activatedAt = t
                    barsSeen++
                    changed = true
                    reason = "Entry was reached by fresh ${s.timeframe} price action."
                }
            }

            if (state == "TRIGGERED" && t >= (activatedAt ?: start)) {
                val hitSl = if (s.direction == "BUY") x.l <= s.sl else x.h >= s.sl
                val hitTp1 = if (s.direction == "BUY") x.h >= s.tp1 else x.l <= s.tp1
                if (hitSl && hitTp1) {
                    state = "REVIEW"
                    changed = true
                    reason = "SL and TP1 were both crossed inside one candle; intrabar order cannot be inferred safely."
                    break
                }
                if (hitSl) {
                    state = "STOPPED"
                    changed = true
                    reason = "Structural stop was reached after trigger."
                    break
                }
                if (hitTp1) {
                    state = "TP1 HIT"
                    changed = true
                    reason = "First target was reached after trigger."
                    break
                }
            }
        }

        if (state == "PENDING" || state == "TRIGGERED") {
            val check = AnalysisEngine.setupCheck(s, candles)
            if (!check.valid) {
                state = "EXPIRED"
                changed = true
                reason = check.reason
            } else if (reason.isBlank()) {
                reason = check.reason
            }
        }

        val updated = a.copy(activatedAt = activatedAt, barsSeen = barsSeen, state = state)
        if (updated != a) {
            save(c, updated)
            a = updated
        }
        return Evaluation(a, changed, reason)
    }

    /**
     * Accepts the result of a NEW ANALYZE pass.
     * A pending setup is refreshed when a newer candle materially changes the thesis.
     * A triggered setup is kept until it reaches a terminal state or becomes invalid.
     */
    fun acceptFresh(c: Context, candidate: Signal): ActiveSignal {
        val old = load(c, candidate.symbol, candidate.timeframe)
        if (old != null && old.state == "TRIGGERED") return old

        if (old != null && old.state == "PENDING") {
            val sameCandle = toMillis(old.signal.createdCandleTime) == toMillis(candidate.createdCandleTime)
            val same = AnalysisEngine.sameSetup(old.signal, candidate)
            if (sameCandle && same) {
                val refreshed = old.copy(signal = candidate.copy(id = old.signal.id, createdAt = old.signal.createdAt))
                save(c, refreshed)
                return refreshed
            }
        }

        val fresh = ActiveSignal(candidate, state = "PENDING")
        save(c, fresh)
        return fresh
    }

    fun materiallyChanged(a: Signal, b: Signal): Boolean {
        if (a.direction != b.direction) return true
        val atr = max(a.atr, b.atr).coerceAtLeast(1e-9)
        return abs(a.entry - b.entry) > atr * .18 ||
            abs(a.sl - b.sl) > atr * .22 ||
            abs(a.tp1 - b.tp1) > atr * .25 ||
            abs(a.score - b.score) >= 4
    }

    private fun signalToJson(s: Signal): JSONObject {
        val reasons = JSONArray(); s.reasons.forEach { reasons.put(it) }
        return JSONObject()
            .put("id", s.id).put("symbol", s.symbol).put("tf", s.timeframe)
            .put("direction", s.direction).put("entry", s.entry).put("sl", s.sl)
            .put("tp1", s.tp1).put("tp2", s.tp2).put("score", s.score)
            .put("bull", s.bullScore).put("bear", s.bearScore).put("valid", s.validBars)
            .put("createdAt", s.createdAt).put("candle", s.createdCandleTime)
            .put("status", s.status).put("ema20", s.ema20).put("ema50", s.ema50)
            .put("rsi", s.rsi).put("macd", s.macd).put("atr", s.atr)
            .put("fvgType", s.fvgType).put("fvgLow", s.fvgLow).put("fvgHigh", s.fvgHigh)
            .put("validityReason", s.validityReason).put("slReason", s.slReason)
            .put("tp1Reason", s.tp1Reason).put("tp2Reason", s.tp2Reason)
            .put("setupReason", s.setupReason).put("reasons", reasons)
    }

    private fun signalFromJson(j: JSONObject): Signal {
        val arr = j.optJSONArray("reasons") ?: JSONArray()
        val reasons = mutableListOf<String>()
        for (i in 0 until arr.length()) reasons += arr.optString(i)
        val low = if (j.isNull("fvgLow")) null else j.optDouble("fvgLow")
        val high = if (j.isNull("fvgHigh")) null else j.optDouble("fvgHigh")
        val type = j.optString("fvgType").ifBlank { null }
        return Signal(
            j.getString("id"), j.getString("symbol"), j.getString("tf"), j.getString("direction"),
            j.getDouble("entry"), j.getDouble("sl"), j.getDouble("tp1"), j.getDouble("tp2"),
            j.getInt("score"), j.getInt("bull"), j.getInt("bear"), j.optInt("valid", 0),
            j.getLong("createdAt"), j.getLong("candle"), j.optString("status", "PENDING"), reasons,
            j.getDouble("ema20"), j.getDouble("ema50"), j.getDouble("rsi"), j.getDouble("macd"),
            j.getDouble("atr"), type, low, high,
            j.optString("validityReason", "Structure driven."),
            j.optString("slReason", "Structure/ATR stop."),
            j.optString("tp1Reason", "Structure/ATR target."),
            j.optString("tp2Reason", "Extended structure target."),
            j.optString("setupReason", "Weighted confluence.")
        )
    }

    private fun activeToJson(a: ActiveSignal) = JSONObject()
        .put("signal", signalToJson(a.signal))
        .put("activatedAt", a.activatedAt)
        .put("bars", a.barsSeen)
        .put("state", a.state)

    private fun activeFromJson(j: JSONObject) = ActiveSignal(
        signalFromJson(j.getJSONObject("signal")),
        if (j.isNull("activatedAt")) null else j.optLong("activatedAt"),
        j.optInt("bars", 0),
        j.optString("state", "PENDING")
    )

    private fun toMillis(t: Long) = if (t in 1..9_999_999_999L) t * 1000L else t
}
