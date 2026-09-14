package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object SignalStore {
    private const val PREF = "mh_records"

    private fun prefs(c: Context) = c.getSharedPreferences(PREF, Context.MODE_PRIVATE)
    private fun activeKey(symbol: String) = "active_${symbol.uppercase()}"

    fun loadActive(c: Context, symbol: String): ActiveSignal? {
        val raw = prefs(c).getString(activeKey(symbol), null) ?: return null
        return runCatching { activeFromJson(JSONObject(raw)) }.getOrNull()
    }

    fun saveActive(c: Context, active: ActiveSignal) {
        prefs(c).edit().putString(activeKey(active.signal.symbol), activeToJson(active).toString()).apply()
    }

    fun clearActive(c: Context, symbol: String) {
        prefs(c).edit().remove(activeKey(symbol)).apply()
    }

    fun replaceWith(c: Context, signal: Signal) {
        val old = loadActive(c, signal.symbol)
        if (old != null && old.state !in setOf("WIN", "LOSS", "EXPIRED")) {
            addRecord(c, toRecord(old, "REPLACED", System.currentTimeMillis()))
        }
        saveActive(c, ActiveSignal(signal))
    }

    fun evaluate(c: Context, symbol: String, candles: List<Candle>): ActiveSignal? {
        var active = loadActive(c, symbol) ?: return null
        val s = active.signal
        val future = candles.filter { it.t > s.createdCandleTime }.take(s.validBars)
        if (future.isEmpty()) return active

        var activatedAt = active.activatedAt
        var state = active.state
        var bars = 0

        for (x in future) {
            bars++
            if (activatedAt == null && x.l <= s.entry && x.h >= s.entry) {
                activatedAt = x.t
                state = "ACTIVE"
            }
            if (activatedAt != null) {
                val hitSl = if (s.direction == "BUY") x.l <= s.sl else x.h >= s.sl
                val hitTp = if (s.direction == "BUY") x.h >= s.tp1 else x.l <= s.tp1
                if (hitSl) {
                    state = "LOSS"
                    break
                }
                if (hitTp) {
                    state = "WIN"
                    break
                }
            }
        }

        if (state !in setOf("WIN", "LOSS") && future.size >= s.validBars) state = "EXPIRED"
        active = ActiveSignal(s, activatedAt, bars, state)

        if (state in setOf("WIN", "LOSS", "EXPIRED")) {
            addRecord(c, toRecord(active, state, future.lastOrNull()?.t ?: System.currentTimeMillis()))
            clearActive(c, symbol)
            return active
        }

        saveActive(c, active)
        return active
    }

    fun records(c: Context): List<TradeRecord> {
        val raw = prefs(c).getString("records", "[]") ?: "[]"
        val arr = runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
        val out = mutableListOf<TradeRecord>()
        for (i in 0 until arr.length()) {
            runCatching { recordFromJson(arr.getJSONObject(i)) }.getOrNull()?.let { out += it }
        }
        return out.sortedByDescending { it.startedAt }
    }

    private fun addRecord(c: Context, record: TradeRecord) {
        val list = records(c).toMutableList()
        if (list.none { it.id == record.id }) list.add(0, record)
        val arr = JSONArray()
        list.take(200).forEach { arr.put(recordToJson(it)) }
        prefs(c).edit().putString("records", arr.toString()).apply()
    }

    fun stats(c: Context): String {
        val records = records(c)
        val wins = records.count { it.result == "WIN" }
        val losses = records.count { it.result == "LOSS" }
        val expired = records.count { it.result == "EXPIRED" }
        val replaced = records.count { it.result == "REPLACED" }
        val resolved = wins + losses
        val accuracy = if (resolved == 0) 0.0 else wins * 100.0 / resolved
        return "Signals: ${records.size}   Wins: $wins   Losses: $losses\n" +
            "Expired: $expired   Replaced: $replaced\n" +
            "Accuracy (resolved): ${String.format(java.util.Locale.US, "%.1f", accuracy)}%   •   $wins/$resolved correct"
    }

    private fun toRecord(active: ActiveSignal, result: String, end: Long): TradeRecord {
        val s = active.signal
        return TradeRecord(
            s.id, s.symbol, s.timeframe, s.direction,
            s.entry, s.sl, s.tp1, s.score,
            s.createdAt, active.activatedAt, end, result
        )
    }

    private fun signalToJson(s: Signal): JSONObject {
        val reasons = JSONArray()
        s.reasons.forEach { reasons.put(it) }
        return JSONObject()
            .put("id", s.id)
            .put("symbol", s.symbol)
            .put("tf", s.timeframe)
            .put("direction", s.direction)
            .put("entry", s.entry)
            .put("sl", s.sl)
            .put("tp1", s.tp1)
            .put("tp2", s.tp2)
            .put("score", s.score)
            .put("bull", s.bullScore)
            .put("bear", s.bearScore)
            .put("valid", s.validBars)
            .put("createdAt", s.createdAt)
            .put("candle", s.createdCandleTime)
            .put("status", s.status)
            .put("ema20", s.ema20)
            .put("ema50", s.ema50)
            .put("rsi", s.rsi)
            .put("macd", s.macd)
            .put("atr", s.atr)
            .put("fvgType", s.fvgType)
            .put("fvgLow", s.fvgLow)
            .put("fvgHigh", s.fvgHigh)
            .put("reasons", reasons)
    }

    private fun signalFromJson(j: JSONObject): Signal {
        val reasonArray = j.optJSONArray("reasons") ?: JSONArray()
        val reasons = mutableListOf<String>()
        for (i in 0 until reasonArray.length()) reasons += reasonArray.optString(i)

        val fvgLow: Double? = if (j.isNull("fvgLow")) null else j.optDouble("fvgLow")
        val fvgHigh: Double? = if (j.isNull("fvgHigh")) null else j.optDouble("fvgHigh")
        val fvgType = j.optString("fvgType").ifBlank { null }

        return Signal(
            id = j.getString("id"),
            symbol = j.getString("symbol"),
            timeframe = j.getString("tf"),
            direction = j.getString("direction"),
            entry = j.getDouble("entry"),
            sl = j.getDouble("sl"),
            tp1 = j.getDouble("tp1"),
            tp2 = j.getDouble("tp2"),
            score = j.getInt("score"),
            bullScore = j.getInt("bull"),
            bearScore = j.getInt("bear"),
            validBars = j.getInt("valid"),
            createdAt = j.getLong("createdAt"),
            createdCandleTime = j.getLong("candle"),
            status = j.optString("status", "PENDING"),
            reasons = reasons,
            ema20 = j.getDouble("ema20"),
            ema50 = j.getDouble("ema50"),
            rsi = j.getDouble("rsi"),
            macd = j.getDouble("macd"),
            atr = j.getDouble("atr"),
            fvgType = fvgType,
            fvgLow = fvgLow,
            fvgHigh = fvgHigh
        )
    }

    private fun activeToJson(active: ActiveSignal): JSONObject = JSONObject()
        .put("signal", signalToJson(active.signal))
        .put("activatedAt", active.activatedAt)
        .put("bars", active.barsSeen)
        .put("state", active.state)

    private fun activeFromJson(j: JSONObject): ActiveSignal {
        val activatedAt = if (j.isNull("activatedAt")) null else j.optLong("activatedAt")
        return ActiveSignal(
            signalFromJson(j.getJSONObject("signal")),
            activatedAt,
            j.optInt("bars", 0),
            j.optString("state", "PENDING")
        )
    }

    private fun recordToJson(r: TradeRecord): JSONObject = JSONObject()
        .put("id", r.id).put("symbol", r.symbol).put("tf", r.timeframe)
        .put("direction", r.direction).put("entry", r.entry).put("sl", r.sl)
        .put("tp1", r.tp1).put("score", r.score).put("startedAt", r.startedAt)
        .put("activatedAt", r.activatedAt).put("endedAt", r.endedAt).put("result", r.result)

    private fun recordFromJson(j: JSONObject): TradeRecord {
        val activatedAt = if (j.isNull("activatedAt")) null else j.optLong("activatedAt")
        val endedAt = if (j.isNull("endedAt")) null else j.optLong("endedAt")
        return TradeRecord(
            j.getString("id"), j.getString("symbol"), j.getString("tf"), j.getString("direction"),
            j.getDouble("entry"), j.getDouble("sl"), j.getDouble("tp1"), j.getInt("score"),
            j.getLong("startedAt"), activatedAt, endedAt, j.getString("result")
        )
    }
}
