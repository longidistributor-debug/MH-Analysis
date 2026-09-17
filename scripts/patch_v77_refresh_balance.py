from pathlib import Path
import re

# -----------------------------------------------------------------------------
# v77 goals
# 1) NEW ANALYZE must visibly re-run every press on the SAME timeframe.
#    It may attempt at most one fresh REST history request. If the local request
#    window blocks that call, a verified current live snapshot is re-analysed
#    instead of making the button look dead.
# 2) Remove the v76 double-rejection problem. AdvancedMarketEngine remains an
#    evidence/map layer, while the final AdaptiveDecisionEngine may assess the
#    raw discovered candidate when AdvancedMarketEngine soft-rejects it.
# 3) Keep hard protections: broken external structure, abnormal spread and bad RR.
# -----------------------------------------------------------------------------

# ---- Adaptive engine balancing ------------------------------------------------
adv=Path('app/src/main/java/com/mh/analysis/AdaptiveDecisionEngine.kt')
a=adv.read_text()

# refine accepts the raw candidate as a fallback so a soft Advanced rejection
# does not automatically make every timeframe NO TRADE.
a=a.replace('''        candles:List<Candle>,\n        prior:AdvancedMarketEngine.Assessment\n    ):AdvancedMarketEngine.Assessment {\n        if(candles.size<80) return prior\n        val p=profile(symbol,candles,prior)\n        val map=prior.map.copy(regime=p.regime)\n        val sig=prior.signal\n''','''        candles:List<Candle>,\n        prior:AdvancedMarketEngine.Assessment,\n        fallback:Signal?=null\n    ):AdvancedMarketEngine.Assessment {\n        if(candles.size<80) return prior\n        val sig=prior.signal?:fallback\n        val p=profile(symbol,candles,prior,sig)\n        val map=prior.map.copy(regime=p.regime)\n''',1)

# Conflict is meaningful only when the opposite side is itself strong.
a=a.replace('''        if(margin<p.requiredMargin) adaptiveWarnings += "BUY/SELL evidence is too close; directional conflict is unresolved"\n        if(chosen.score<p.requiredScore) adaptiveWarnings += "Adaptive confluence ${chosen.score}/100 is below the current market requirement ${p.requiredScore}"\n        if(isBreakout&&p.breakoutAcceptance<p.breakoutRequired) adaptiveWarnings += "Breakout has not earned enough acceptance relative to recent ${timeframe} candles"\n''','''        val meaningfulConflict=opposite.score>=p.requiredScore-6 && margin<p.requiredMargin\n        if(meaningfulConflict) adaptiveWarnings += "BUY/SELL evidence is genuinely conflicted; the opposite side is also strong"\n        if(chosen.score<p.requiredScore) adaptiveWarnings += "Adaptive confluence ${chosen.score}/100 is below the current market requirement ${p.requiredScore}"\n        val weakAcceptedBreakout=isBreakout&&alignedExternalBreak&&p.breakoutAcceptance<p.breakoutRequired\n        if(weakAcceptedBreakout) adaptiveWarnings += "The structural breakout has not earned enough acceptance relative to recent ${timeframe} candles"\n''',1)

# Hard risk is calculated from the actual candidate even if Advanced soft-rejected it.
a=a.replace('''        val rejected = adaptiveWarnings.isNotEmpty() && (\n            margin<p.requiredMargin ||\n            chosen.score<p.requiredScore ||\n            (isBreakout&&p.breakoutAcceptance<p.breakoutRequired) ||\n            oppositeExternalBreak ||\n            prior.map.severeSpread\n        )\n''','''        val risk=abs(sig.entry-sig.sl).coerceAtLeast(1e-9)\n        val rr1=abs(sig.tp1-sig.entry)/risk\n        val hardRiskReject=rr1<1.10\n        if(hardRiskReject) adaptiveWarnings += "Risk/reward is below the hard structural minimum (${String.format(java.util.Locale.US,"%.2f",rr1)}R)"\n        val rejected =\n            prior.map.severeSpread ||\n            oppositeExternalBreak ||\n            hardRiskReject ||\n            chosen.score<p.requiredScore ||\n            meaningfulConflict ||\n            weakAcceptedBreakout\n''',1)

# Profile can use fallback candidate RR; relax dynamic thresholds without forcing signals.
a=a.replace('''        val p=profile(active.signal.symbol,candles,currentAssessment)\n''','''        val p=profile(active.signal.symbol,candles,currentAssessment,active.signal)\n''',1)
a=a.replace('''    private fun profile(symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment):Profile{\n''','''    private fun profile(symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment,candidate:Signal?=prior.signal):Profile{\n''',1)
a=a.replace('''        val breakoutRequired=(52 + (100-efficiencyRank)*0.10 + abs(atrRank-62)*0.07).roundToInt().coerceIn(52,72)\n''','''        val breakoutRequired=(48 + (100-efficiencyRank)*0.075 + abs(atrRank-62)*0.05).roundToInt().coerceIn(48,66)\n''',1)
a=a.replace('''        val buy=side("BUY",symbol,w,prior,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)\n        val sell=side("SELL",symbol,w,prior,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)\n\n        val noise=(100-efficiencyRank).coerceIn(0,100)\n        val volatilityUncertainty=abs(atrRank-58)\n        val regimePenalty=when(regime){"RANGING"->6;"HIGH_VOLATILITY"->5;"LOW_VOLATILITY"->3;else->0}\n        val spreadPenalty=if(prior.map.spreadWarning)4 else 0\n        val requiredScore=(58 + noise*.08 + volatilityUncertainty*.05 + regimePenalty + spreadPenalty).roundToInt().coerceIn(60,79)\n        val requiredMargin=(7 + noise*.07 + volatilityUncertainty*.035 + if(regime=="RANGING")4 else 0).roundToInt().coerceIn(8,22)\n''','''        val buy=side("BUY",symbol,w,prior,candidate,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)\n        val sell=side("SELL",symbol,w,prior,candidate,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)\n\n        val noise=(100-efficiencyRank).coerceIn(0,100)\n        val volatilityUncertainty=abs(atrRank-58)\n        val regimePenalty=when(regime){"RANGING"->3;"HIGH_VOLATILITY"->3;"LOW_VOLATILITY"->2;else->0}\n        val spreadPenalty=if(prior.map.spreadWarning)3 else 0\n        val requiredScore=(54 + noise*.05 + volatilityUncertainty*.03 + regimePenalty + spreadPenalty).roundToInt().coerceIn(55,72)\n        val requiredMargin=(4 + noise*.035 + volatilityUncertainty*.02 + if(regime=="RANGING")2 else 0).roundToInt().coerceIn(4,14)\n''',1)
a=a.replace('''        direction:String,symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment,regime:String,\n''','''        direction:String,symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment,candidate:Signal?,regime:String,\n''',1)
a=a.replace('''        val sig=prior.signal\n        val risk=if(sig!=null){\n''','''        val sig=candidate\n        val risk=if(sig!=null){\n''',1)

# Re-evaluation should degrade progressively instead of invalidating on a small margin wobble.
a=a.replace('''        if(chosen.score < p.requiredScore-8 || margin < max(2,p.requiredMargin/2)){\n            return base.copy(state="INVALID",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Original confluence has degraded below the adaptive continuation boundary.").distinct())\n        }\n        if(chosen.score < p.requiredScore || margin < p.requiredMargin){\n            return base.copy(state="WEAKENING",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Signal is still structurally alive, but directional dominance has weakened.").distinct())\n        }\n''','''        val strongOpposite=opposite.score>=p.requiredScore\n        if(chosen.score < p.requiredScore-12 || (strongOpposite&&margin<=-4)){\n            return base.copy(state="INVALID",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Original confluence has materially degraded or the opposite thesis is now dominant.").distinct())\n        }\n        if(chosen.score < p.requiredScore-3 || (strongOpposite&&margin<max(2,p.requiredMargin/2))){\n            return base.copy(state="WEAKENING",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Signal remains structurally alive, but evidence has weakened enough to require caution.").distinct())\n        }\n''',1)

adv.write_text(a)

# ---- Main app integration ------------------------------------------------------
main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

# Raw enriched candidate is available to final adaptive engine if Advanced soft-rejects.
s=s.replace('''        val assessment=AdaptiveDecisionEngine.refine(symbol,period,candles,baseAssessment)\n''','''        val assessment=AdaptiveDecisionEngine.refine(symbol,period,candles,baseAssessment,enriched)\n''',1)
s=s.replace('''                    val assessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment)\n''','''                    val assessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment,enriched)\n''',1)

# Every NEW ANALYZE press attempts one fresh history request. If the local request
# window blocks it, analyse the verified current live snapshot rather than doing nothing.
pattern=re.compile(r'''                var credits=0\n                val data=FcsClient\.freshSnapshot\(reqSymbol,reqPeriod,100,2200\) \?: run\{\n                    val pair=FcsClient\.seedForPeriod\(key,reqSymbol,reqPeriod,true\);credits\+=pair\.second;pair\.first\n                \}\n                val pdPair=runCatching\{FcsClient\.previousDayRange\(key,reqSymbol\)\}\.getOrElse\{null to 0\}\n                credits\+=pdPair\.second''')
replacement='''                var credits=0\n                val liveFallback=FcsClient.freshSnapshot(reqSymbol,reqPeriod,100,2200)\n                val freshPair=runCatching{FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)}.getOrElse{e->\n                    if(liveFallback!=null && (e.message?.contains("rate-limited",true)==true)) liveFallback to 0 else throw e\n                }\n                credits+=freshPair.second\n                val data=freshPair.first\n                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0}\n                credits+=pdPair.second'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v77 NEW ANALYZE refresh anchor not found')

# Make a repeated same-timeframe run visibly confirm it really ran.
s=s.replace('''                showSetup(after,"RE-EVALUATED • NO NEW REPLACEMENT",AnalysisEngine.noSignalReason(symbol,period,candles))\n''','''                showSetup(after,"NEW ANALYZE REFRESHED • NO NEW REPLACEMENT",AnalysisEngine.noSignalReason(symbol,period,candles))\n''',1)
s=s.replace('''            else->"RE-EVALUATED • SETUP UNCHANGED"\n''','''            else->"NEW ANALYZE REFRESHED • SETUP UNCHANGED"\n''',1)
s=s.replace('''            else "Current candle and structure still support the same setup."\n''','''            else "Fresh $period analysis was run again; current candle and structure still support the same setup."\n''',1)

s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v77 • ADAPTIVE LIVE ANALYSIS',s,count=1)
main.write_text(s)

# ---- Floating analyzer gets same balanced fallback logic -----------------------
overlay=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
o=overlay.read_text()
o=o.replace('''                val adaptiveAssessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment)\n''','''                val adaptiveAssessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment,referenced)\n''',1)
overlay.write_text(o)

# Version metadata.
build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 77',b);b=re.sub(r'versionName = "[^"]+"','versionName = "77.0"',b);build.write_text(b)

print('v77 repeat refresh + balanced adaptive gating applied')
