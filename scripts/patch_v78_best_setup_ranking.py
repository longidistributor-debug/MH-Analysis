from pathlib import Path
import re

# -----------------------------------------------------------------------------
# v78: the legacy/core/video/advanced/adaptive implementations stay available,
# but none of their fixed thresholds is allowed to be the final hard gate.
# BestSetupEngine ranks the whole current same-timeframe market and selects the
# strongest live thesis. Hard NO SIGNAL is reserved for data insufficiency or
# statistical directional ambiguity measured from that timeframe itself.
# -----------------------------------------------------------------------------

# Clean two source-string escapes and remove fixed fallback noise/uncertainty floors.
best=Path('app/src/main/java/com/mh/analysis/BestSetupEngine.kt')
e=best.read_text()
e=e.replace('"A newer $${fresh.timeframe} candle/snapshot was analysed. "','"A newer ${fresh.timeframe} candle/snapshot was analysed. "')
e=e.replace('.replace("$${fresh.timeframe}", fresh.timeframe)','')
e=e.replace('"Current body rank ${(bodyStrength * 100).roundToInt()} vs its own $${c.size}-candle sample"','"Current body rank ${(bodyStrength * 100).roundToInt()} vs its own ${c.size}-candle sample"')
e=e.replace('''        ).map { it.copy(reasons = it.reasons.map { x -> x.replace("$${c.size}", c.size.toString()) }) }\n''','''        )\n''')
e=e.replace('''        val uncertainty = (pMad * 100.0 / sqrt(max(1, pressure.size).toDouble())).coerceAtLeast(.35)\n''','''        val uncertainty = (pMad * 100.0 / sqrt(max(1, pressure.size).toDouble())).coerceAtLeast(1e-6)\n''')
e=e.replace('''        val wickNoise = if (dir == "BUY") median(wickSeries(c, false)) else median(wickSeries(c, true))\n        val noise = max(wickNoise, st.trMedian - st.trMad).coerceAtLeast(st.trMedian * .15)\n''','''        val wickNoise = if (dir == "BUY") median(wickSeries(c, false)) else median(wickSeries(c, true))\n        val robustNoise = median((wickSeries(c,false)+wickSeries(c,true)+trueRanges(c)).filter{it>0.0})\n        val noise = max(wickNoise, robustNoise).coerceAtLeast(1e-9)\n''')
best.write_text(e)

# -----------------------------------------------------------------------------
# Store: NEW ANALYZE is allowed to replace the prior current analysis, even if
# it was triggered. Automatic live updates only track entry/SL/TP lifecycle;
# they no longer expire a setup through old fixed RSI/volatility thresholds.
# -----------------------------------------------------------------------------
store=Path('app/src/main/java/com/mh/analysis/LiveSetupStore.kt')
l=store.read_text()
old='''        if (state == "PENDING" || state == "TRIGGERED") {\n            val check = AnalysisEngine.setupCheck(s, candles)\n            if (!check.valid) {\n                state = "EXPIRED"\n                changed = true\n                reason = check.reason\n            } else if (reason.isBlank()) {\n                reason = check.reason\n            }\n        }\n'''
new='''        if ((state == "PENDING" || state == "TRIGGERED") && reason.isBlank()) {\n            reason = "Live price updated. Directional thesis is re-ranked only by NEW ANALYZE / RE-EVALUATE; no legacy fixed-threshold expiry was applied."\n        }\n'''
if old in l:
    l=l.replace(old,new,1)
else:
    raise SystemExit('v78 LiveSetupStore validation anchor not found')
anchor='''    fun materiallyChanged(a: Signal, b: Signal): Boolean {\n'''
helper='''    /** Manual NEW ANALYZE always replaces the previous analysis snapshot. */\n    fun replaceFresh(c: Context, candidate: Signal): ActiveSignal {\n        val fresh = ActiveSignal(candidate, state = "PENDING")\n        save(c, fresh)\n        return fresh\n    }\n\n'''+anchor
if anchor in l and 'fun replaceFresh(' not in l:
    l=l.replace(anchor,helper,1)
store.write_text(l)

# -----------------------------------------------------------------------------
# Main screen: each NEW ANALYZE press performs a new ranking from the latest
# direct timeframe snapshot. Keep the live WebSocket version of the current
# candle if it is newer inside the same candle bucket than the REST response.
# -----------------------------------------------------------------------------
main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

# In v77 analyseNow, preserve latest live same-candle OHLC after the one REST refresh.
old='''                credits+=freshPair.second\n                val data=freshPair.first\n                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0}\n'''
new='''                credits+=freshPair.second\n                val data=mergeLatestLive(freshPair.first,liveFallback)\n                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0}\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'mergeLatestLive(freshPair.first,liveFallback)' not in s:
    raise SystemExit('v78 NEW ANALYZE merge anchor not found')

# Replace the complete fresh-analysis decision path.
pattern=re.compile(r'''    private fun performFreshAnalysis\(\)\{.*?\n    \}\n(?=\n    private fun )''',re.S)
replacement='''    private fun performFreshAnalysis(){\n        if(candles.size<60){\n            signalHeading.text=""\n            status.text="NOT ENOUGH FRESH $period HISTORY TO RANK THE CURRENT MARKET"\n            renderSignalMap(null,lastMarketMap,"DATA BUILDING");showSignalCard(null);return\n        }\n        val before=LiveSetupStore.load(this,symbol,period)\n        val decision=BestSetupEngine.analyze(symbol,period,candles,before?.signal)\n        lastMarketMap=decision.map\n        val candidate=decision.signal?.let{applyPreviousDayContext(it)}\n        val q=candidate?.score?:maxOf(decision.buyScore,decision.sellScore)\n        lastAssessment=AdvancedMarketEngine.Assessment(\n            candidate,decision.map,q,if(candidate==null)"-" else AdvancedMarketEngine.grade(q),\n            decision.explanation,decision.reasons,decision.warnings\n        )\n        val refreshNote=BestSetupEngine.explainRefresh(before,decision)\n        if(candidate==null){\n            LiveSetupStore.clear(this,symbol,period)\n            signalHeading.setTextColor(Color.rgb(255,193,7));signalHeading.text="NO CLEAR CURRENT EDGE • $symbol • $period"\n            val lines=(decision.reasons+decision.warnings).distinct().take(10).joinToString("\\n") { "-> $it" }\n            status.text=greenSections(\n                "NEW ANALYZE RESULT\\n${decision.explanation}\\n\\nWHY PREVIOUS SIGNAL WAS NOT REUSED\\n$refreshNote${if(lines.isBlank())"" else "\\n\\nCURRENT EVIDENCE\\n$lines"}",\n                listOf("NEW ANALYZE RESULT","WHY PREVIOUS SIGNAL WAS NOT REUSED","CURRENT EVIDENCE")\n            )\n            renderSignalMap(null,decision.map,"NO CLEAR CURRENT EDGE");showSignalCard(null);return\n        }\n        val accepted=LiveSetupStore.replaceFresh(this,candidate)\n        val headline=when{\n            before==null->"NEW FRESH BEST SIGNAL"\n            before.signal.direction!=candidate.direction->"NEW SIGNAL • DIRECTION CHANGED"\n            else->"NEW ANALYZE • BEST SETUP REFRESHED"\n        }\n        showSetup(accepted,headline,refreshNote)\n    }\n'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v78 performFreshAnalysis function not found')

# Replace re-evaluation functions with the same final ranking engine.
pattern=re.compile(r'''    private fun reevaluateNow\(\)\{.*?\n    \}\n\n    private fun showReEvaluation\(.*?\n    \}\n\n(?=    private fun applyPreviousDayContext)''',re.S)
replacement='''    private fun reevaluateNow(){\n        val active=LiveSetupStore.load(this,symbol,period)\n        if(active==null){\n            signalHeading.setTextColor(Color.rgb(255,193,7));signalHeading.text="RE-EVALUATE • NO ACTIVE SIGNAL"\n            status.text="-> No active $symbol $period signal exists.\\n-> Press NEW ANALYZE first."\n            renderSignalMap(null,lastMarketMap,"NO ACTIVE SIGNAL");return\n        }\n        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}\n        if(busy){status.text="MARKET REFRESH IS ALREADY RUNNING FOR $symbol • $period";return}\n        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"\n        busy=true;signalHeading.setTextColor(Color.rgb(61,220,132));signalHeading.text="RE-EVALUATING • $reqSymbol • $reqPeriod"\n        status.text="-> Re-reading the latest direct $reqPeriod market snapshot.\\n-> No previous signal is assumed valid."\n        thread{\n            try{\n                var credits=0\n                val liveFallback=FcsClient.freshSnapshot(reqSymbol,reqPeriod,60,2200)\n                val freshPair=runCatching{FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)}.getOrElse{e->\n                    if(liveFallback!=null&&e.message?.contains("rate-limited",true)==true) liveFallback to 0 else throw e\n                }\n                credits+=freshPair.second\n                val data=mergeLatestLive(freshPair.first,liveFallback)\n                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0};credits+=pdPair.second\n                runOnUiThread{\n                    if(token!=analyzeGeneration||reqSymbol!=symbol||reqPeriod!=period)return@runOnUiThread\n                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"\n                    candles=data;previousDay=pdPair.first;analysisContext=reqContext\n                    val current=LiveSetupStore.load(this,symbol,period)?:active\n                    val r=BestSetupEngine.reevaluate(current,data)\n                    lastMarketMap=r.map\n                    showBestReEvaluation(current,r)\n                }\n            }catch(e:Exception){\n                runOnUiThread{if(token==analyzeGeneration){\n                    busy=false;signalHeading.setTextColor(Color.rgb(255,82,82));signalHeading.text="RE-EVALUATION UNAVAILABLE"\n                    status.text="-> ${e.message}\\n-> Existing signal was not blindly marked valid."\n                }}\n            }\n        }\n    }\n\n    private fun showBestReEvaluation(active:ActiveSignal,r:BestSetupEngine.Recheck){\n        val color=when(r.state){\n            "STILL VALID","TARGET REACHED"->Color.rgb(61,220,132)\n            "WEAKENING"->Color.rgb(255,193,7)\n            else->Color.rgb(255,82,82)\n        }\n        signalHeading.setTextColor(color);signalHeading.text="RE-EVALUATE • ${r.state} • ${r.score}/100 • ${r.grade}"\n        val lines=r.reasons.distinct().take(10).joinToString("\\n") { "-> $it" }\n        status.text=greenSections("RE-EVALUATION RESULT\\n${r.state} • ${r.score}/100 • Grade ${r.grade}\\n\\nREASONS\\n$lines",listOf("RE-EVALUATION RESULT","REASONS"))\n        when{\n            r.state=="REVERSED"&&r.replacement!=null->{\n                val repl=LiveSetupStore.replaceFresh(this,applyPreviousDayContext(r.replacement))\n                renderSignalMap(repl,r.map,"REVERSED");showSignalCard(repl)\n            }\n            r.state=="INVALID"->{LiveSetupStore.clear(this,symbol,period);renderSignalMap(null,r.map,"INVALID");showSignalCard(null)}\n            else->{renderSignalMap(active,r.map,r.state);showSignalCard(active)}\n        }\n    }\n\n'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v78 re-evaluate function block not found')

# Previous-day context is retained as evidence, but no fixed +/- score is applied.
pattern=re.compile(r'''    private fun applyPreviousDayContext\(s:Signal\):Signal\{.*?\n    \}\n''',re.S)
replacement='''    private fun applyPreviousDayContext(s:Signal):Signal{\n        val pd=previousDay?:return s\n        val last=candles.lastOrNull()?:return s\n        val reasons=s.reasons.toMutableList()\n        val bullSweep=last.l<pd.low&&last.c>pd.low\n        val bearSweep=last.h>pd.high&&last.c<pd.high\n        when{\n            bullSweep&&s.direction=="BUY"->reasons.add(0,"Previous-day low liquidity was swept and reclaimed")\n            bearSweep&&s.direction=="SELL"->reasons.add(0,"Previous-day high liquidity was swept and rejected")\n            bullSweep&&s.direction=="SELL"->reasons.add(0,"Counter evidence: previous-day low was reclaimed")\n            bearSweep&&s.direction=="BUY"->reasons.add(0,"Counter evidence: previous-day high was rejected")\n            last.c>pd.high&&s.direction=="BUY"->reasons.add(0,"Price is holding above previous-day high")\n            last.c<pd.low&&s.direction=="SELL"->reasons.add(0,"Price is holding below previous-day low")\n        }\n        return s.copy(reasons=reasons.distinct().take(12))\n    }\n'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v78 previous-day function not found')

# Helper that protects the latest WebSocket version of the same open candle from
# being overwritten by a slightly older REST snapshot.
anchor='''    private fun contextKey()="$symbol|$period"\n'''
helper='''    private fun mergeLatestLive(fetched:List<Candle>,live:List<Candle>?):List<Candle>{\n        if(fetched.isEmpty()||live.isNullOrEmpty())return fetched\n        val f=fetched.last();val l=live.last()\n        fun ts(x:Long)=if(x>9_999_999_999L)x/1000L else x\n        if(ts(f.t)!=ts(l.t))return if(ts(l.t)>ts(f.t))(fetched+l).sortedBy{ts(it.t)}.distinctBy{ts(it.t)}.takeLast(300) else fetched\n        val out=fetched.toMutableList()\n        out[out.lastIndex]=f.copy(h=maxOf(f.h,l.h),l=minOf(f.l,l.l),c=l.c,v=maxOf(f.v,l.v))\n        return out.takeLast(300)\n    }\n\n'''+anchor
if anchor in s and 'private fun mergeLatestLive(' not in s:
    s=s.replace(anchor,helper,1)

s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v78 • BEST SETUP RANKING ENGINE',s,count=1)
main.write_text(s)

# -----------------------------------------------------------------------------
# Floating analyser uses the exact same ranking engine, not a separate adaptive
# threshold chain.
# -----------------------------------------------------------------------------
over=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
o=over.read_text()
old='''                val core=AnalysisEngine.analyze(symbol,period,data)\n                val referenced=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)\n                val baseAssessment=AdvancedMarketEngine.assess(symbol,period,data,referenced)\n                val adaptiveAssessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment,referenced)\n                val fresh=adaptiveAssessment.signal\n'''
new='''                val decision=BestSetupEngine.analyze(symbol,period,data,before?.signal)\n                val fresh=decision.signal\n'''
if old in o:
    o=o.replace(old,new,1)
elif 'BestSetupEngine.analyze(symbol,period,data,before?.signal)' not in o:
    raise SystemExit('v78 overlay ranking anchor not found')
o=o.replace('''                    if(before!=null&&before.state in setOf("PENDING","TRIGGERED"))showState("RE-EVALUATED • NO NEW REPLACEMENT")\n                    else{status?.text="NO CURRENT SETUP\\n${AnalysisEngine.noSignalReason(symbol,period,data)}";overlay(null)}\n''','''                    LiveSetupStore.clear(this,symbol,period)\n                    status?.text="NO CLEAR CURRENT EDGE\\n${decision.explanation}";overlay(null)\n''',1)
o=o.replace('''                val accepted=LiveSetupStore.acceptFresh(this,fresh)\n''','''                val accepted=LiveSetupStore.replaceFresh(this,fresh)\n''',1)
over.write_text(o)

# Version metadata.
build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 78',b);b=re.sub(r'versionName = "[^"]+"','versionName = "78.0"',b);build.write_text(b)

print('v78 best-current-setup ranking + fresh refresh + unified re-evaluation applied')
