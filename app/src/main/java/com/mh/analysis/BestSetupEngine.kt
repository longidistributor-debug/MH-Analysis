package com.mh.analysis

import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * v78 final decision engine.
 *
 * Philosophy: analyse the selected timeframe as a whole, rank all available
 * bullish/bearish setup families, then return the best CURRENT thesis. Legacy
 * engines and the seven video techniques are evidence providers, not hard gates.
 * No fixed pip distance, fixed ATR multiple, fixed score threshold or fixed
 * candle-count pattern can by itself create/reject the final signal.
 */
object BestSetupEngine {
    data class Decision(
        val signal: Signal?,
        val map: AdvancedMarketEngine.MarketMap,
        val buyScore: Int,
        val sellScore: Int,
        val bestFamily: String,
        val runnerUpFamily: String,
        val explanation: String,
        val reasons: List<String>,
        val warnings: List<String>
    )

    data class Recheck(
        val state: String,
        val score: Int,
        val grade: String,
        val reasons: List<String>,
        val map: AdvancedMarketEngine.MarketMap,
        val replacement: Signal? = null
    )

    private data class Pivot(val index: Int, val price: Double)
    private data class Family(val direction: String, val name: String, val score: Double, val reasons: List<String>)
    private data class Stats(
        val trMedian: Double,
        val trMad: Double,
        val bodyRank: Int,
        val rangeRank: Int,
        val atrRank: Int,
        val pressureUncertainty: Double,
        val fastWindow: Int,
        val slowWindow: Int
    )

    fun analyze(symbol: String, timeframe: String, candles: List<Candle>, previous: Signal? = null): Decision {
        val w = candles.takeLast(min(300, candles.size))
        val map = AdvancedMarketEngine.marketMap(symbol, timeframe, w)
        if (w.size < 60) {
            return Decision(null, map, 0, 0, "-", "-", "Not enough same-timeframe history to compare current market behaviour reliably.", emptyList(), listOf("Need more direct $timeframe candles."))
        }

        val stats = stats(w)
        val core = runCatching { AnalysisEngine.analyze(symbol, timeframe, w) }.getOrNull()
        val videoStandalone = runCatching { VideoTechniqueEngine.analyzeOrEnhance(symbol, timeframe, w, null) }.getOrNull()
        val videoEnhanced = runCatching { VideoTechniqueEngine.analyzeOrEnhance(symbol, timeframe, w, core) }.getOrNull()

        val families = mutableListOf<Family>()
        families += trendFamilies(w, map, stats)
        families += structureFamilies(w, map, stats)
        families += liquidityFamilies(w, map, stats)
        families += breakoutFamilies(w, map, stats)
        families += reversalFamilies(w, map, stats)
        families += zoneFamilies(w, map, stats)
        families += momentumFamilies(w, map, stats)

        core?.let { families += legacyFamily(it, "Core multi-technique setup") }
        videoStandalone?.let { families += legacyFamily(it, "Video-reference setup") }
        if (videoEnhanced != null && (core == null || videoEnhanced.id != core.id)) {
            families += legacyFamily(videoEnhanced, "Combined core + video-reference setup")
        }

        val buy = aggregate(families.filter { it.direction == "BUY" })
        val sell = aggregate(families.filter { it.direction == "SELL" })
        val buyScore = buy.first.roundToInt().coerceIn(0, 99)
        val sellScore = sell.first.roundToInt().coerceIn(0, 99)
        val edge = abs(buy.first - sell.first)
        val uncertainty = stats.pressureUncertainty
        val bestDir = if (buy.first >= sell.first) "BUY" else "SELL"
        val winner = if (bestDir == "BUY") buy else sell
        val loser = if (bestDir == "BUY") sell else buy
        val bestFamily = winner.second.firstOrNull()?.name ?: "Composite market structure"
        val runner = winner.second.drop(1).firstOrNull()?.name ?: loser.second.firstOrNull()?.name ?: "-"

        val rankedReasons = winner.second.take(5).flatMap { f ->
            listOf("${f.name} ${f.score.roundToInt()}/100") + f.reasons.take(2)
        }.distinct()
        val warnings = mutableListOf<String>()
        if (map.spreadWarning) warnings += "Live spread is wider than its normal execution context; analysis remains informational."
        if (map.severeSpread) warnings += "Live spread is abnormal; price execution may differ from the analysis levels."
        if (map.fvgType != null && map.fvgFillPct >= 90) warnings += "Latest ${map.fvgType} FVG is almost fully mitigated and carries little weight."

        // Ambiguity is statistical, not a fixed score gate. The edge must only
        // exceed the uncertainty measured from this timeframe's own recent pressure.
        if (edge <= uncertainty) {
            val why = "No clear current directional edge: BUY $buyScore vs SELL $sellScore; the ${two(edge)} point difference is inside this timeframe's measured uncertainty ${two(uncertainty)}."
            return Decision(null, map, buyScore, sellScore, bestFamily, runner, why, rankedReasons.take(12), warnings)
        }

        val plan = buildSignal(symbol, timeframe, w, map, stats, bestDir, buyScore, sellScore, winner.second, previous)
        val explanation = buildString {
            append("$bestDir is the strongest CURRENT $timeframe thesis. ")
            append("BUY $buyScore vs SELL $sellScore; edge ${two(edge)} is larger than measured same-timeframe uncertainty ${two(uncertainty)}. ")
            append("Best family: $bestFamily.")
        }
        return Decision(plan, map, buyScore, sellScore, bestFamily, runner, explanation, rankedReasons.take(12), warnings)
    }

    fun reevaluate(active: ActiveSignal, candles: List<Candle>): Recheck {
        val s = active.signal
        val w = candles.takeLast(min(300, candles.size))
        val map = AdvancedMarketEngine.marketMap(s.symbol, s.timeframe, w)
        val last = w.lastOrNull() ?: return Recheck("INVALID", 0, "C", listOf("No fresh same-timeframe candle is available."), map)

        val slBroken = if (s.direction == "BUY") last.l <= s.sl else last.h >= s.sl
        if (slBroken) return Recheck("INVALID", 0, "C", listOf("Price breached the structural invalidation/SL level."), map)
        val tp1Hit = if (s.direction == "BUY") last.h >= s.tp1 else last.l <= s.tp1
        if (tp1Hit) return Recheck("TARGET REACHED", s.score, AdvancedMarketEngine.grade(s.score), listOf("Fresh ${s.timeframe} price action reached TP1."), map)

        val d = analyze(s.symbol, s.timeframe, w, s)
        val fresh = d.signal
        if (fresh == null) {
            return Recheck("WEAKENING", max(1, max(d.buyScore, d.sellScore)), AdvancedMarketEngine.grade(max(d.buyScore, d.sellScore)), listOf(
                "The original ${s.direction} setup has not hit structural invalidation, but the fresh ranking no longer has a statistically clear edge.",
                d.explanation
            ) + d.reasons.take(5), d.map)
        }
        if (fresh.direction != s.direction) {
            return Recheck("REVERSED", fresh.score, AdvancedMarketEngine.grade(fresh.score), listOf(
                "Fresh full-market ranking now prefers ${fresh.direction} instead of the original ${s.direction}.",
                d.explanation
            ) + fresh.reasons.take(5), d.map, fresh)
        }
        return Recheck("STILL VALID", fresh.score, AdvancedMarketEngine.grade(fresh.score), listOf(
            "Fresh full-market ranking still selects ${s.direction} as the best current setup.",
            d.explanation
        ) + fresh.reasons.take(5), d.map, fresh)
    }

    fun explainRefresh(previous: ActiveSignal?, decision: Decision): String {
        val fresh = decision.signal
        if (previous == null && fresh == null) return decision.explanation
        if (previous == null && fresh != null) return "Fresh analysis found ${fresh.direction} as the best current setup. ${decision.explanation}"
        val old = previous!!.signal
        if (fresh == null) return "Previous ${old.direction} is not being reused. Fresh analysis cancelled it because ${decision.explanation}"
        if (fresh.direction != old.direction) return "Market ranking changed from ${old.direction} to ${fresh.direction}. ${decision.explanation}"
        val sameCandle = normalizeTs(old.createdCandleTime) == normalizeTs(fresh.createdCandleTime)
        val scoreMove = fresh.score - old.score
        return buildString {
            append(if (sameCandle) "The same live candle was analysed again from its latest OHLC state. " else "A newer $${fresh.timeframe} candle/snapshot was analysed. ")
            append("${fresh.direction} is still the best setup. ")
            append("Quality ${old.score} -> ${fresh.score}")
            if (scoreMove != 0) append(" (${if (scoreMove > 0) "+" else ""}$scoreMove)")
            append(". ${decision.explanation}")
        }.replace("$${fresh.timeframe}", fresh.timeframe)
    }

    private fun trendFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val close = c.map { it.c }
        val fast = ema(close, st.fastWindow).last()
        val slow = ema(close, st.slowWindow).last()
        val prevFast = ema(close.dropLast(min(st.fastWindow, max(2, st.fastWindow / 3))), st.fastWindow).lastOrNull() ?: fast
        val trend = ((fast - slow) / st.trMedian).coerceIn(-4.0, 4.0)
        val slope = ((fast - prevFast) / st.trMedian).coerceIn(-4.0, 4.0)
        val dmiDen = (map.plusDi + map.minusDi).coerceAtLeast(1e-9)
        val dmi = ((map.plusDi - map.minusDi) / dmiDen).coerceIn(-1.0, 1.0)
        val bull = smooth(50.0 + trend * 9.0 + slope * 6.0 + dmi * 22.0)
        val bear = smooth(50.0 - trend * 9.0 - slope * 6.0 - dmi * 22.0)
        return listOf(
            Family("BUY", "Trend / pullback continuation", bull, listOf("Adaptive fast-vs-slow trend strength ${two(trend)}", "DMI balance ${one(dmi * 100)} toward BUY when positive")),
            Family("SELL", "Trend / pullback continuation", bear, listOf("Adaptive fast-vs-slow trend strength ${two(-trend)}", "DMI balance ${one(-dmi * 100)} toward SELL when positive"))
        )
    }

    private fun structureFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val span = adaptiveSpan(c.size)
        val highs = pivots(c, true, span)
        val lows = pivots(c, false, span)
        val h = highs.lastOrNull()?.price
        val l = lows.lastOrNull()?.price
        val last = c.last()
        val position = if (h != null && l != null && h > l) ((last.c - l) / (h - l)).coerceIn(0.0, 1.0) else .5
        val breakUp = h?.let { (last.c - it) / st.trMedian } ?: 0.0
        val breakDn = l?.let { (it - last.c) / st.trMedian } ?: 0.0
        val bull = smooth(35.0 + position * 38.0 + max(0.0, breakUp) * 18.0 - max(0.0, breakDn) * 22.0)
        val bear = smooth(35.0 + (1.0 - position) * 38.0 + max(0.0, breakDn) * 18.0 - max(0.0, breakUp) * 22.0)
        return listOf(
            Family("BUY", "Adaptive market structure", bull, listOf("Swing position ${(position * 100).roundToInt()}% inside current adaptive structure", "Structure is read only from this $span-span same-timeframe pivot map")),
            Family("SELL", "Adaptive market structure", bear, listOf("Swing position ${((1 - position) * 100).roundToInt()}% toward bearish side", "Structure is read only from this $span-span same-timeframe pivot map"))
        )
    }

    private fun liquidityFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val span = adaptiveSpan(c.size)
        val highs = pivots(c, true, span)
        val lows = pivots(c, false, span)
        val last = c.last()
        val low = lows.filter { it.price <= last.c }.maxByOrNull { it.price }?.price
        val high = highs.filter { it.price >= last.c }.minByOrNull { it.price }?.price
        val lowerWick = min(last.o, last.c) - last.l
        val upperWick = last.h - max(last.o, last.c)
        val bullSweep = low?.let { if (last.l < it && last.c > it) rank01(lowerWick, wickSeries(c, false)) else 0.0 } ?: 0.0
        val bearSweep = high?.let { if (last.h > it && last.c < it) rank01(upperWick, wickSeries(c, true)) else 0.0 } ?: 0.0
        val bullObjective = map.equalHigh?.let { if (it > last.c) 1.0 else 0.0 } ?: if (high != null) .65 else .35
        val bearObjective = map.equalLow?.let { if (it < last.c) 1.0 else 0.0 } ?: if (low != null) .65 else .35
        return listOf(
            Family("BUY", "Liquidity sweep / rotation", smooth(42.0 + bullSweep * 45.0 + bullObjective * 13.0), listOf("Sell-side reclaim strength ${(bullSweep * 100).roundToInt()}th relative rank", "Opposing liquidity objective quality ${(bullObjective * 100).roundToInt()}")),
            Family("SELL", "Liquidity sweep / rotation", smooth(42.0 + bearSweep * 45.0 + bearObjective * 13.0), listOf("Buy-side rejection strength ${(bearSweep * 100).roundToInt()}th relative rank", "Opposing liquidity objective quality ${(bearObjective * 100).roundToInt()}"))
        )
    }

    private fun breakoutFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val span = adaptiveSpan(c.size)
        val highs = pivots(c.dropLast(1), true, span)
        val lows = pivots(c.dropLast(1), false, span)
        val last = c.last()
        val h = highs.lastOrNull()?.price
        val l = lows.lastOrNull()?.price
        val body = abs(last.c - last.o)
        val bodyStrength = rank01(body, c.map { abs(it.c - it.o) })
        val rangeStrength = rank01(last.h - last.l, c.map { it.h - it.l })
        val upDistance = h?.let { max(0.0, last.c - it) / st.trMedian } ?: 0.0
        val dnDistance = l?.let { max(0.0, it - last.c) / st.trMedian } ?: 0.0
        val closeLoc = ((last.c - last.l) / (last.h - last.l).coerceAtLeast(1e-9)).coerceIn(0.0, 1.0)
        val bull = smooth(35.0 + bodyStrength * 25.0 + rangeStrength * 15.0 + closeLoc * 12.0 + upDistance * 18.0)
        val bear = smooth(35.0 + bodyStrength * 25.0 + rangeStrength * 15.0 + (1.0 - closeLoc) * 12.0 + dnDistance * 18.0)
        return listOf(
            Family("BUY", "Breakout / acceptance", bull, listOf("Current body rank ${(bodyStrength * 100).roundToInt()} vs its own $${c.size}-candle sample", "Close acceptance ${(closeLoc * 100).roundToInt()}% inside current candle")),
            Family("SELL", "Breakout / acceptance", bear, listOf("Current body rank ${(bodyStrength * 100).roundToInt()} vs its own $${c.size}-candle sample", "Close acceptance ${((1 - closeLoc) * 100).roundToInt()}% toward bearish edge"))
        ).map { it.copy(reasons = it.reasons.map { x -> x.replace("$${c.size}", c.size.toString()) }) }
    }

    private fun reversalFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val last = c.last()
        val range = (last.h - last.l).coerceAtLeast(1e-9)
        val lower = (min(last.o, last.c) - last.l) / range
        val upper = (last.h - max(last.o, last.c)) / range
        val lowerRank = rank01(lower, c.map { x -> (min(x.o, x.c) - x.l) / (x.h - x.l).coerceAtLeast(1e-9) })
        val upperRank = rank01(upper, c.map { x -> (x.h - max(x.o, x.c)) / (x.h - x.l).coerceAtLeast(1e-9) })
        val divBull = if (map.divergence?.contains("bull", true) == true) 1.0 else 0.0
        val divBear = if (map.divergence?.contains("bear", true) == true) 1.0 else 0.0
        return listOf(
            Family("BUY", "Reversal / rejection", smooth(38.0 + lowerRank * 42.0 + divBull * 20.0), listOf("Lower-wick rejection rank ${(lowerRank * 100).roundToInt()}", map.divergence ?: "No RSI divergence required")),
            Family("SELL", "Reversal / rejection", smooth(38.0 + upperRank * 42.0 + divBear * 20.0), listOf("Upper-wick rejection rank ${(upperRank * 100).roundToInt()}", map.divergence ?: "No RSI divergence required"))
        )
    }

    private fun zoneFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val p = c.last().c
        fun zoneScore(lo: Double?, hi: Double?, aligned: Boolean): Double {
            if (lo == null || hi == null) return 44.0
            val dist = distanceToZone(p, lo, hi)
            val rel = rank01(dist, c.takeLast(min(120, c.size)).map { x -> abs(x.c - p) })
            return smooth(if (aligned) 82.0 - rel * 38.0 else 50.0 - rel * 18.0)
        }
        val bullOb = zoneScore(map.bullObLow, map.bullObHigh, true)
        val bearOb = zoneScore(map.bearObLow, map.bearObHigh, true)
        val bullFvg = if (map.fvgType == "BULLISH") 45.0 + (100 - map.fvgFillPct) * .45 else 42.0
        val bearFvg = if (map.fvgType == "BEARISH") 45.0 + (100 - map.fvgFillPct) * .45 else 42.0
        return listOf(
            Family("BUY", "Order block / FVG reaction", smooth((bullOb + bullFvg) / 2.0), listOf("Bull OB proximity quality ${bullOb.roundToInt()}", "Bull FVG remaining quality ${bullFvg.roundToInt()}")),
            Family("SELL", "Order block / FVG reaction", smooth((bearOb + bearFvg) / 2.0), listOf("Bear OB proximity quality ${bearOb.roundToInt()}", "Bear FVG remaining quality ${bearFvg.roundToInt()}"))
        )
    }

    private fun momentumFamilies(c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats): List<Family> {
        val returns = c.zipWithNext().map { (a, b) -> (b.c - a.c) / max(st.trMedian, 1e-9) }
        val short = returns.takeLast(st.fastWindow.coerceAtMost(returns.size)).averageOr(0.0)
        val path = returns.takeLast(st.slowWindow.coerceAtMost(returns.size))
        val directionalRank = rankSigned(short, path)
        val last = c.last()
        val closeLoc = ((last.c - last.l) / (last.h - last.l).coerceAtLeast(1e-9)).coerceIn(0.0, 1.0)
        val bull = smooth(50.0 + directionalRank * 32.0 + (closeLoc - .5) * 26.0)
        val bear = smooth(50.0 - directionalRank * 32.0 + (.5 - closeLoc) * 26.0)
        return listOf(
            Family("BUY", "Momentum / candle pressure", bull, listOf("Relative return pressure ${one(directionalRank * 100)}", "Body percentile ${st.bodyRank}; range percentile ${st.rangeRank}")),
            Family("SELL", "Momentum / candle pressure", bear, listOf("Relative return pressure ${one(-directionalRank * 100)}", "Body percentile ${st.bodyRank}; range percentile ${st.rangeRank}"))
        )
    }

    private fun legacyFamily(s: Signal, name: String): Family {
        return Family(s.direction, name, s.score.toDouble(), s.reasons.take(4))
    }

    private fun aggregate(fs: List<Family>): Pair<Double, List<Family>> {
        if (fs.isEmpty()) return 50.0 to emptyList()
        val ranked = fs.sortedByDescending { it.score }
        val top = ranked.take(min(5, ranked.size))
        val weights = top.indices.map { (top.size - it).toDouble() }
        val score = top.zip(weights).sumOf { it.first.score * it.second } / weights.sum().coerceAtLeast(1.0)
        return score to ranked
    }

    private fun buildSignal(
        symbol: String, timeframe: String, c: List<Candle>, map: AdvancedMarketEngine.MarketMap, st: Stats,
        dir: String, buyScore: Int, sellScore: Int, ranked: List<Family>, previous: Signal?
    ): Signal {
        val last = c.last()
        val span = adaptiveSpan(c.size)
        val highs = pivots(c, true, span).map { it.price }.distinct().sorted()
        val lows = pivots(c, false, span).map { it.price }.distinct().sorted()
        val entryLevels = mutableListOf<Pair<String, Double>>()
        if (dir == "BUY") {
            zoneMid(map.bullObLow, map.bullObHigh)?.takeIf { it <= last.c }?.let { entryLevels += "bull order-block reaction" to it }
            if (map.fvgType == "BULLISH") zoneMid(map.fvgLow, map.fvgHigh)?.takeIf { it <= last.c }?.let { entryLevels += "bull FVG reaction" to it }
            lows.filter { it <= last.c }.maxOrNull()?.let { entryLevels += "nearest adaptive support/liquidity" to it }
        } else {
            zoneMid(map.bearObLow, map.bearObHigh)?.takeIf { it >= last.c }?.let { entryLevels += "bear order-block reaction" to it }
            if (map.fvgType == "BEARISH") zoneMid(map.fvgLow, map.fvgHigh)?.takeIf { it >= last.c }?.let { entryLevels += "bear FVG reaction" to it }
            highs.filter { it >= last.c }.minOrNull()?.let { entryLevels += "nearest adaptive resistance/liquidity" to it }
        }
        val chosenEntry = entryLevels.minByOrNull { abs(last.c - it.second) }
        val entry = chosenEntry?.second ?: last.c
        val entrySource = chosenEntry?.first ?: "current live price because no cleaner nearby structural retest level exists"

        val wickNoise = if (dir == "BUY") median(wickSeries(c, false)) else median(wickSeries(c, true))
        val noise = max(wickNoise, st.trMedian - st.trMad).coerceAtLeast(st.trMedian * .15)
        val invalidation = if (dir == "BUY") {
            listOfNotNull(lows.filter { it < entry }.maxOrNull(), map.bullObLow?.takeIf { it < entry }, map.fvgLow?.takeIf { map.fvgType == "BULLISH" && it < entry }).maxOrNull()
        } else {
            listOfNotNull(highs.filter { it > entry }.minOrNull(), map.bearObHigh?.takeIf { it > entry }, map.fvgHigh?.takeIf { map.fvgType == "BEARISH" && it > entry }).minOrNull()
        }
        val sl = if (dir == "BUY") (invalidation ?: (entry - st.trMedian)) - noise else (invalidation ?: (entry + st.trMedian)) + noise

        val swingDistances = mutableListOf<Double>()
        val allPivots = (highs + lows).sorted()
        for (i in 1 until allPivots.size) swingDistances += abs(allPivots[i] - allPivots[i - 1])
        val expected = median(swingDistances.filter { it > 0.0 }).takeIf { it > 0.0 } ?: st.trMedian
        val objectives = if (dir == "BUY") {
            (highs + listOfNotNull(map.equalHigh, map.bearObLow, map.bearObHigh)).filter { it > entry + noise }.distinct().sorted()
        } else {
            (lows + listOfNotNull(map.equalLow, map.bullObLow, map.bullObHigh)).filter { it < entry - noise }.distinct().sortedDescending()
        }
        val tp1 = objectives.getOrNull(0) ?: if (dir == "BUY") entry + expected else entry - expected
        val tp2 = objectives.getOrNull(1) ?: if (dir == "BUY") tp1 + expected else tp1 - expected

        val score = if (dir == "BUY") buyScore else sellScore
        val reasons = ranked.take(6).flatMap { f -> listOf("${f.name} ${f.score.roundToInt()}/100") + f.reasons.take(1) }.distinct().take(12)
        val close = c.map { it.c }
        val e20 = ema(close, min(20, max(2, close.size - 1))).last()
        val e50 = ema(close, min(50, max(2, close.size - 1))).last()
        val rsi = rsi(close, min(14, max(2, close.size - 1)))
        val macd = ema(close, min(12, max(2, close.size - 1))).last() - ema(close, min(26, max(2, close.size - 1))).last()
        val best = ranked.firstOrNull()?.name ?: "Composite market structure"
        val risk = abs(entry - sl).coerceAtLeast(1e-9)
        val rr1 = abs(tp1 - entry) / risk
        val rr2 = abs(tp2 - entry) / risk
        return Signal(
            UUID.randomUUID().toString(), symbol, timeframe, dir,
            entry, sl, tp1, tp2, score, buyScore, sellScore, 0,
            System.currentTimeMillis(), last.t, "PENDING", reasons,
            e20, e50, rsi, macd, st.trMedian,
            map.fvgType, map.fvgLow, map.fvgHigh,
            "No fixed candle-count expiry. Re-evaluate against the newest direct $timeframe candles; the thesis remains valid while $dir stays the best full-market ranking and structural invalidation is not breached.",
            "SL is placed beyond the nearest live structural invalidation using wick/range noise learned from this timeframe, not a fixed pip or fixed ATR distance.",
            "TP1 uses the nearest opposing live structure/liquidity objective; fallback distance comes from the median observed swing size of this timeframe. Current computed R:R ${two(rr1)}R.",
            "TP2 uses the next opposing structure/liquidity objective or another median observed swing extension. Current computed R:R ${two(rr2)}R.",
            "$dir • BEST CURRENT SETUP: $best. $entrySource selected the entry. All available families were ranked; no single indicator, fixed ratio, fixed candle pattern or legacy hard gate decided this signal."
        )
    }

    private fun stats(c: List<Candle>): Stats {
        val trs = trueRanges(c)
        val med = median(trs).coerceAtLeast(1e-9)
        val mad = median(trs.map { abs(it - med) }).coerceAtLeast(1e-9)
        val ranges = c.map { (it.h - it.l).coerceAtLeast(1e-9) }
        val bodies = c.map { abs(it.c - it.o) }
        val bodyRank = (rank01(bodies.last(), bodies) * 100).roundToInt()
        val rangeRank = (rank01(ranges.last(), ranges) * 100).roundToInt()
        val atrSeries = rollingMedianTr(c)
        val atrRank = (rank01(atrSeries.lastOrNull() ?: med, atrSeries.ifEmpty { listOf(med) }) * 100).roundToInt()
        val pressure = c.zipWithNext().map { (a, b) -> (b.c - a.c) / max(med, 1e-9) }
        val pMed = median(pressure)
        val pMad = median(pressure.map { abs(it - pMed) })
        val uncertainty = (pMad * 100.0 / sqrt(max(1, pressure.size).toDouble())).coerceAtLeast(.35)
        val root = sqrt(c.size.toDouble()).roundToInt()
        val fast = root.coerceIn(8, max(8, c.size / 4))
        val slow = (root * 2 + (mad / med).roundToInt()).coerceIn(fast + 2, max(fast + 2, c.size / 2))
        return Stats(med, mad, bodyRank, rangeRank, atrRank, uncertainty, fast, slow)
    }

    private fun adaptiveSpan(n: Int): Int = sqrt(max(16, n).toDouble()).div(2.0).roundToInt().coerceIn(2, 10)

    private fun pivots(c: List<Candle>, high: Boolean, span: Int): List<Pivot> {
        if (c.size < span * 2 + 3) return emptyList()
        val out = mutableListOf<Pivot>()
        for (i in span until c.size - span) {
            val p = if (high) c[i].h else c[i].l
            var ok = true
            for (j in i - span..i + span) {
                if (j == i) continue
                val q = if (high) c[j].h else c[j].l
                if (if (high) q > p else q < p) { ok = false; break }
            }
            if (ok) out += Pivot(i, p)
        }
        return out
    }

    private fun trueRanges(c: List<Candle>): List<Double> {
        if (c.isEmpty()) return emptyList()
        val out = mutableListOf<Double>()
        out += c.first().h - c.first().l
        for (i in 1 until c.size) {
            val x = c[i]; val p = c[i - 1].c
            out += max(x.h - x.l, max(abs(x.h - p), abs(x.l - p)))
        }
        return out
    }

    private fun rollingMedianTr(c: List<Candle>): List<Double> {
        val tr = trueRanges(c)
        if (tr.size < 8) return tr
        val root = sqrt(tr.size.toDouble()).roundToInt().coerceAtLeast(5)
        return (root until tr.size).map { i -> median(tr.subList(max(0, i - root + 1), i + 1)) }
    }

    private fun wickSeries(c: List<Candle>, upper: Boolean): List<Double> = c.map { x ->
        if (upper) x.h - max(x.o, x.c) else min(x.o, x.c) - x.l
    }.map { max(0.0, it) }

    private fun rank01(x: Double, values: List<Double>): Double {
        val v = values.filter { it.isFinite() }
        if (v.isEmpty()) return .5
        return (v.count { it <= x }.toDouble() / v.size).coerceIn(0.0, 1.0)
    }

    private fun rankSigned(x: Double, values: List<Double>): Double {
        val r = rank01(x, values)
        return (r * 2.0 - 1.0).coerceIn(-1.0, 1.0)
    }

    private fun median(v: List<Double>): Double {
        val s = v.filter { it.isFinite() }.sorted()
        if (s.isEmpty()) return 0.0
        val m = s.size / 2
        return if (s.size % 2 == 0) (s[m - 1] + s[m]) / 2.0 else s[m]
    }

    private fun zoneMid(lo: Double?, hi: Double?): Double? = if (lo == null || hi == null) null else (lo + hi) / 2.0
    private fun distanceToZone(p: Double, lo: Double, hi: Double) = when { p < lo -> lo - p; p > hi -> p - hi; else -> 0.0 }
    private fun smooth(x: Double) = x.coerceIn(0.0, 99.0)
    private fun normalizeTs(t: Long) = if (t > 9_999_999_999L) t / 1000L else t

    private fun ema(v: List<Double>, p: Int): List<Double> {
        if (v.isEmpty()) return emptyList()
        val period = p.coerceIn(1, v.size)
        val k = 2.0 / (period + 1.0)
        val out = MutableList(v.size) { 0.0 }; out[0] = v[0]
        for (i in 1 until v.size) out[i] = v[i] * k + out[i - 1] * (1 - k)
        return out
    }

    private fun rsi(v: List<Double>, p: Int): Double {
        if (v.size < 2) return 50.0
        val n = p.coerceIn(1, v.size - 1)
        var g = 0.0; var l = 0.0
        for (i in v.size - n until v.size) {
            val d = v[i] - v[i - 1]
            if (d > 0) g += d else l -= d
        }
        if (l <= 1e-12) return 100.0
        val rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)
    }

    private fun List<Double>.averageOr(default: Double): Double = if (isEmpty()) default else average()
    private fun one(v: Double) = String.format(Locale.US, "%.1f", v)
    private fun two(v: Double) = String.format(Locale.US, "%.2f", v)
}
