from pathlib import Path
import re

# -----------------------------------------------------------------------------
# Fix compile issue in AdvancedMarketEngine and wire best-signal quality layer.
# -----------------------------------------------------------------------------
adv=Path('app/src/main/java/com/mh/analysis/AdvancedMarketEngine.kt')
a=adv.read_text()
a=a.replace('eqh,eql,fvg?.type,fvg?.low,fvg?.high,fvg?.fill,divText,','eqh,eql,fvg?.type,fvg?.low,fvg?.high,(fvg?.fill?:0),divText,',1)
adv.write_text(a)

# -----------------------------------------------------------------------------
# Feed live bid/ask into execution-quality state when socket supplies them.
# -----------------------------------------------------------------------------
sock=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
s=sock.read_text()
anchor='''        val p=j.optJSONObject("prices")?:return\n        val mode=p.optString("mode").lowercase()\n'''
insert='''        val p=j.optJSONObject("prices")?:return\n        val bid=when{\n            p.has("bid")->p.optDouble("bid",Double.NaN)\n            p.has("b")->p.optDouble("b",Double.NaN)\n            j.has("bid")->j.optDouble("bid",Double.NaN)\n            j.has("b")->j.optDouble("b",Double.NaN)\n            else->Double.NaN\n        }\n        val ask=when{\n            p.has("ask")->p.optDouble("ask",Double.NaN)\n            p.has("a")->p.optDouble("a",Double.NaN)\n            j.has("ask")->j.optDouble("ask",Double.NaN)\n            j.has("a")->j.optDouble("a",Double.NaN)\n            else->Double.NaN\n        }\n        if(bid.isFinite()&&ask.isFinite())LiveMarketState.update(internal,bid,ask)\n        val mode=p.optString("mode").lowercase()\n'''
if anchor in s and 'LiveMarketState.update(internal,bid,ask)' not in s:
    s=s.replace(anchor,insert,1)
sock.write_text(s)

# -----------------------------------------------------------------------------
# Main screen: signal/market-map above chart, RE-EVALUATE, independent advanced
# quality filter, clean output formatting, and WebView touch handling so the
# TradingView right price scale receives vertical drag gestures inside ScrollView.
# -----------------------------------------------------------------------------
main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

if 'private lateinit var signalMapCard:TextView' not in s:
    s=s.replace('    private lateinit var signalHeading:TextView\n','    private lateinit var signalHeading:TextView\n    private lateinit var signalMapCard:TextView\n',1)
if 'private var lastAssessment:AdvancedMarketEngine.Assessment?=null' not in s:
    s=s.replace('    private var analysisContext:String?=null\n','    private var analysisContext:String?=null\n    private var lastAssessment:AdvancedMarketEngine.Assessment?=null\n    private var lastMarketMap:AdvancedMarketEngine.MarketMap?=null\n',1)

# Move visible signal summary out of TradingView and place it immediately above chart.
old='''        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{\n            settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.mediaPlaybackRequiresUserGesture=false\n'''
new='''        root.addView(section("LIVE MARKET CHART"))\n        signalMapCard=txt("NO ACTIVE SIGNAL • PRESS NEW ANALYZE",11.5f,false).apply{\n            setPadding(dp(12),dp(11),dp(12),dp(11));background=round(Color.rgb(8,15,11),12f,Color.rgb(47,118,77))\n        }\n        root.addView(signalMapCard,LinearLayout.LayoutParams(-1,-2).apply{bottomMargin=dp(8)})\n        val cc=card();chart=WebView(this).apply{\n            settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.mediaPlaybackRequiresUserGesture=false\n            setOnTouchListener{v,e->\n                when(e.actionMasked){\n                    android.view.MotionEvent.ACTION_DOWN,android.view.MotionEvent.ACTION_MOVE->v.parent?.requestDisallowInterceptTouchEvent(true)\n                    android.view.MotionEvent.ACTION_UP,android.view.MotionEvent.ACTION_CANCEL->v.parent?.requestDisallowInterceptTouchEvent(false)\n                }\n                false\n            }\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'signalMapCard=txt(' not in s:
    raise SystemExit('v74 live chart anchor not found')

# Two actions: fresh analysis and explicit re-evaluation.
old='''        sc.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})\n        signalHeading=txt("",16f,true,Color.rgb(61,220,132)).apply{setPadding(dp(4),dp(12),dp(4),0)};sc.addView(signalHeading,LinearLayout.LayoutParams(-1,-2))\n'''
new='''        val actionRow=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL}\n        actionRow.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(5)})\n        actionRow.addView(actionButton("RE-EVALUATE",false){reevaluateNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(5)})\n        sc.addView(actionRow,LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})\n        signalHeading=txt("",16f,true,Color.rgb(61,220,132)).apply{setPadding(dp(4),dp(12),dp(4),0)};sc.addView(signalHeading,LinearLayout.LayoutParams(-1,-2))\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'RE-EVALUATE' not in s:
    raise SystemExit('v74 signal control anchor not found')

# Reset every visible signal context on pair/timeframe switch.
s=s.replace('''        previousDay=null\n        if(::signalHeading.isInitialized)signalHeading.text=""\n''','''        previousDay=null\n        lastAssessment=null;lastMarketMap=null\n        if(::signalMapCard.isInitialized)signalMapCard.text="NO ACTIVE SIGNAL • $symbol • $period • PRESS NEW ANALYZE"\n        if(::signalHeading.isInitialized)signalHeading.text=""\n''',1)

# Use advanced same-timeframe quality engine after structure + video-reference engine.
old='''        val core=AnalysisEngine.analyze(symbol,period,candles)\n        val raw=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,candles,core)\n        val candidate=raw?.let{applyPreviousDayContext(it)}\n'''
new='''        val core=AnalysisEngine.analyze(symbol,period,candles)\n        val referenced=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,candles,core)\n        val enriched=referenced?.let{applyPreviousDayContext(it)}\n        val assessment=AdvancedMarketEngine.assess(symbol,period,candles,enriched)\n        lastAssessment=assessment;lastMarketMap=assessment.map\n        val candidate=assessment.signal\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'AdvancedMarketEngine.assess(symbol,period,candles,enriched)' not in s:
    raise SystemExit('v74 advanced analysis anchor not found')

# Better no-signal explanation from the quality engine.
s=s.replace('''                    signalHeading.text=""\n                    status.text="NO CURRENT SETUP\\n${marketContext()}\\n\\n${AnalysisEngine.noSignalReason(symbol,period,candles)}"\n                    showSignalCard(null)\n''','''                    signalHeading.text=""\n                    val a=lastAssessment\n                    val reasonLines=((a?.warnings.orEmpty())+(a?.reasons.orEmpty())).distinct().take(6).joinToString("\\n") { "→ $it" }\n                    status.text="NO CURRENT SETUP\\n${a?.decision?:AnalysisEngine.noSignalReason(symbol,period,candles)}${if(reasonLines.isBlank())"" else "\\n\\n$reasonLines"}"\n                    renderSignalMap(null,lastMarketMap,"NO CURRENT SIGNAL")\n                    showSignalCard(null)\n''',1)

# Replace v73 detailed output with cleaner, non-duplicative sections and arrows.
pattern=re.compile(r'''    private fun showSetup\(a:ActiveSignal\?,headline:String,note:String=""\)\{.*?\n    \}\n\n    private fun marketContext''',re.S)
replacement='''    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){\n        if(a==null){signalHeading.text="";renderSignalMap(null,lastMarketMap,headline);status.text="$headline\\n${marketContext()}";showSignalCard(null);return}\n        val s=a.signal\n        val arrow=if(s.direction=="BUY")"↗" else "↘"\n        signalHeading.setTextColor(Color.rgb(61,220,132))\n        signalHeading.text="$arrow ${s.direction} SIGNAL • ${s.timeframe} • ${a.state} • ${s.score}/100"\n        renderSignalMap(a,lastMarketMap,headline)\n\n        val why=s.reasons.take(3).joinToString("<br>") { "→ ${escapeHtml(it)}" }\n        val confirmations=s.reasons.take(8).joinToString("<br>") { "→ ${escapeHtml(it)}" }\n        val m=lastMarketMap\n        val risk=kotlin.math.abs(s.entry-s.sl).coerceAtLeast(1e-9)\n        val rr1=kotlin.math.abs(s.tp1-s.entry)/risk\n        val rr2=kotlin.math.abs(s.tp2-s.entry)/risk\n        val conclusion=buildList<String>{\n            add("Signal quality ${s.score}/100 • Grade ${AdvancedMarketEngine.grade(s.score)}")\n            m?.let{add("Market regime ${it.regime} • ADX ${String.format(Locale.US,"%.1f",it.adx)}") }\n            add("Risk/Reward TP1 ${String.format(Locale.US,"%.2f",rr1)}R • TP2 ${String.format(Locale.US,"%.2f",rr2)}R")\n            lastAssessment?.decision?.takeIf{it.isNotBlank()}?.let{add(it)}\n        }.joinToString("<br>") { "→ ${escapeHtml(it)}" }\n        val update=if(note.isBlank())"" else "<br><br><font color='#3DDC84'><b>UPDATE</b></font><br>→ ${escapeHtml(note)}"\n        val html="""\n            <font color='#3DDC84'><b>TRADE PLAN</b></font><br>\n            “ ENTRY ” : ${price(s.entry)}<br>\n            → TP1 : ${price(s.tp1)} &nbsp;&nbsp; | &nbsp;&nbsp; TP2 : ${price(s.tp2)}<br>\n            → SL : ${price(s.sl)}<br><br>\n            <font color='#3DDC84'><b>WHY THIS TRADE</b></font><br>\n            $why<br><br>\n            <font color='#3DDC84'><b>WHY STOP LOSS</b></font><br>\n            → ${escapeHtml(s.slReason)}<br><br>\n            <font color='#3DDC84'><b>WHY TP1</b></font><br>\n            → ${escapeHtml(s.tp1Reason)}<br><br>\n            <font color='#3DDC84'><b>WHY TP2</b></font><br>\n            → ${escapeHtml(s.tp2Reason)}<br><br>\n            <font color='#3DDC84'><b>TRADE CONCLUSION</b></font><br>\n            $conclusion<br><br>\n            <font color='#3DDC84'><b>CONFIRMATIONS</b></font><br>\n            $confirmations$update\n        """.trimIndent()\n        status.text=if(Build.VERSION.SDK_INT>=24)android.text.Html.fromHtml(html,android.text.Html.FROM_HTML_MODE_LEGACY) else @Suppress("DEPRECATION") android.text.Html.fromHtml(html)\n        showSignalCard(a)\n    }\n\n    private fun marketContext'''
if pattern.search(s):
    s=pattern.sub(lambda m: replacement,s,count=1)
else:
    raise SystemExit('v74 showSetup function not found')

# Insert top market-map rendering + explicit re-evaluate workflow before previous-day context function.
anchor='''    private fun applyPreviousDayContext(s:Signal):Signal{\n'''
helper='''    private fun escapeHtml(x:String)=android.text.TextUtils.htmlEncode(x)\n\n    private fun zoneText(lo:Double?,hi:Double?):String=if(lo==null||hi==null)"-" else "${price(lo)} – ${price(hi)}"\n\n    private fun renderSignalMap(a:ActiveSignal?,m:AdvancedMarketEngine.MarketMap?,label:String=""){\n        if(!::signalMapCard.isInitialized)return\n        val pd=previousDay\n        val top=if(a==null)"NO ACTIVE SIGNAL • $symbol • $period" else {\n            val x=a.signal;val ar=if(x.direction=="BUY")"↗" else "↘"\n            "$ar ${x.direction} SIGNAL • ${x.score}/100 • ${AdvancedMarketEngine.grade(x.score)} • ${a.state}"\n        }\n        val trade=if(a==null)"" else {\n            val x=a.signal\n            "<br>“ ENTRY ” : ${price(x.entry)}<br>→ TP1 : ${price(x.tp1)} &nbsp; | &nbsp; TP2 : ${price(x.tp2)}<br>→ SL : ${price(x.sl)}"\n        }\n        val mapLines=buildList<String>{\n            add("Previous Day High : ${pd?.let{price(it.high)}?:"-"}")\n            add("Previous Day Low : ${pd?.let{price(it.low)}?:"-"}")\n            m?.let{\n                add("Bull OB : ${zoneText(it.bullObLow,it.bullObHigh)}")\n                add("Bear OB : ${zoneText(it.bearObLow,it.bearObHigh)}")\n                add("Regime : ${it.regime} • ADX ${String.format(Locale.US,"%.1f",it.adx)}")\n                it.fvgType?.let{ft->add("$ft FVG : ${zoneText(it.fvgLow,it.fvgHigh)} • ${it.fvgFillPct}% filled")}\n                it.divergence?.let{d->add("Divergence : $d")}\n                if(it.spreadWarning)add("Execution : spread wider than normal")\n            }\n        }.joinToString("<br>") { "→ ${escapeHtml(it)}" }\n        val html="<font color='#3DDC84'><b>${escapeHtml(top)}</b></font>$trade<br><br><font color='#3DDC84'><b>MARKET MAP</b></font><br>$mapLines"\n        signalMapCard.text=if(Build.VERSION.SDK_INT>=24)android.text.Html.fromHtml(html,android.text.Html.FROM_HTML_MODE_LEGACY) else @Suppress("DEPRECATION") android.text.Html.fromHtml(html)\n    }\n\n    private fun reevaluateNow(){\n        val active=LiveSetupStore.load(this,symbol,period)\n        if(active==null){\n            signalHeading.setTextColor(Color.rgb(255,193,7));signalHeading.text="RE-EVALUATE • NO ACTIVE SIGNAL"\n            status.text="→ No active $symbol $period setup exists.\\n→ Press NEW ANALYZE first."\n            renderSignalMap(null,lastMarketMap,"NO ACTIVE SIGNAL")\n            return\n        }\n        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}\n        if(busy){status.text="MARKET REFRESH IS ALREADY RUNNING FOR $symbol • $period";return}\n        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"\n        busy=true;signalHeading.setTextColor(Color.rgb(61,220,132));signalHeading.text="RE-EVALUATING • $reqSymbol • $reqPeriod"\n        status.text="→ Refreshing the current $reqPeriod candle and structure.\\n→ Existing signal will not be assumed valid."\n        thread{\n            try{\n                var credits=0\n                val data=FcsClient.freshSnapshot(reqSymbol,reqPeriod,100,2200) ?: run{\n                    val pair=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true);credits+=pair.second;pair.first\n                }\n                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0};credits+=pdPair.second\n                runOnUiThread{\n                    if(token!=analyzeGeneration||reqSymbol!=symbol||reqPeriod!=period)return@runOnUiThread\n                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"\n                    candles=data;previousDay=pdPair.first;analysisContext=reqContext\n                    val life=LiveSetupStore.evaluate(this,symbol,period,data).setup?:active\n                    val core=AnalysisEngine.analyze(symbol,period,data)\n                    val referenced=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)\n                    val enriched=referenced?.let{applyPreviousDayContext(it)}\n                    val assessment=AdvancedMarketEngine.assess(symbol,period,data,enriched)\n                    lastAssessment=assessment;lastMarketMap=assessment.map\n                    val r=AdvancedMarketEngine.reevaluate(life,data,assessment.signal)\n                    showReEvaluation(life,r)\n                }\n            }catch(e:Exception){\n                runOnUiThread{if(token==analyzeGeneration){\n                    busy=false;signalHeading.setTextColor(Color.rgb(255,82,82));signalHeading.text="RE-EVALUATION UNAVAILABLE"\n                    status.text="→ ${e.message}\\n→ Existing signal was not blindly marked valid."\n                }}\n            }\n        }\n    }\n\n    private fun showReEvaluation(active:ActiveSignal,r:AdvancedMarketEngine.ReEvaluation){\n        lastMarketMap=r.map\n        val color=when(r.state){\n            "STILL VALID","TARGET REACHED"->Color.rgb(61,220,132)\n            "WEAKENING"->Color.rgb(255,193,7)\n            else->Color.rgb(255,82,82)\n        }\n        signalHeading.setTextColor(color);signalHeading.text="RE-EVALUATE • ${r.state} • ${r.score}/100 • ${r.grade}"\n        val reasons=r.reasons.distinct().take(10).joinToString("<br>") { "→ ${escapeHtml(it)}" }\n        val html="<font color='#3DDC84'><b>RE-EVALUATION RESULT</b></font><br>→ ${escapeHtml(r.state)} • ${r.score}/100 • Grade ${escapeHtml(r.grade)}<br><br><font color='#3DDC84'><b>REASONS</b></font><br>$reasons"\n        status.text=if(Build.VERSION.SDK_INT>=24)android.text.Html.fromHtml(html,android.text.Html.FROM_HTML_MODE_LEGACY) else @Suppress("DEPRECATION") android.text.Html.fromHtml(html)\n        val display=if(r.state=="REVERSED"&&r.replacement!=null){\n            val repl=LiveSetupStore.acceptFresh(this,r.replacement)\n            renderSignalMap(repl,r.map,"REVERSED");showSignalCard(repl);repl\n        }else{\n            renderSignalMap(active,r.map,r.state);showSignalCard(active);active\n        }\n    }\n\n'''+anchor
if anchor in s and 'private fun reevaluateNow()' not in s:
    s=s.replace(anchor,helper,1)

# Extend chart level payload with quality-map levels; visual signal card itself will be hidden in HTML.
pattern=re.compile(r'''    private fun showSignalCard\(a:ActiveSignal\?\)\{.*?\n    \}\n\n    private fun contextKey''',re.S)
replacement='''    private fun showSignalCard(a:ActiveSignal?){\n        if(!chartReady)return\n        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}\n        val s=a.signal\n        val j=JSONObject()\n            .put("direction",s.direction).put("state",a.state).put("timeframe",s.timeframe)\n            .put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)\n            .put("createdCandleTime",s.createdCandleTime)\n        previousDay?.let{j.put("pdHigh",it.high).put("pdLow",it.low)}\n        lastMarketMap?.let{m->\n            m.bullObLow?.let{j.put("bullObLow",it)};m.bullObHigh?.let{j.put("bullObHigh",it)}\n            m.bearObLow?.let{j.put("bearObLow",it)};m.bearObHigh?.let{j.put("bearObHigh",it)}\n            m.fvgLow?.let{j.put("fvgLow",it)};m.fvgHigh?.let{j.put("fvgHigh",it)}\n        }\n        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)\n    }\n\n    private fun contextKey'''
if pattern.search(s):
    s=pattern.sub(lambda m: replacement,s,count=1)
else:
    raise SystemExit('v74 showSignalCard anchor not found')

s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v74 • ADAPTIVE QUALITY ENGINE',s,count=1)
main.write_text(s)

# -----------------------------------------------------------------------------
# TradingView: remove the floating BUY/SELL card from inside the chart but keep
# exact price guides when the embed exposes the chart API. Add OB/FVG guides.
# -----------------------------------------------------------------------------
html=Path('app/src/main/assets/tradingview_live.html')
h=html.read_text()
pattern=re.compile(r'''function renderSignalCard\(s\)\{.*?\n\}''',re.S)
replacement="""function renderSignalCard(s){\n  const el=document.getElementById('signalCard');\n  el.style.display='none';el.innerHTML='';\n}"""
if pattern.search(h):
    h=pattern.sub(lambda m: replacement,h,count=1)
else:
    raise SystemExit('v74 renderSignalCard anchor not found')

needle="""    if(Number.isFinite(Number(s.pdLow)))guides.push(drawNativeLine(s.pdLow,'#c58af9',true,'PREV DAY LOW '+fmt(s.pdLow)));\n    drawTradeArrow(s);\n"""
extra="""    if(Number.isFinite(Number(s.pdLow)))guides.push(drawNativeLine(s.pdLow,'#c58af9',true,'PREV DAY LOW '+fmt(s.pdLow)));\n    if(Number.isFinite(Number(s.bullObLow)))guides.push(drawNativeLine(s.bullObLow,'#3ddc84',true,'BULL OB LOW '+fmt(s.bullObLow)));\n    if(Number.isFinite(Number(s.bullObHigh)))guides.push(drawNativeLine(s.bullObHigh,'#3ddc84',true,'BULL OB HIGH '+fmt(s.bullObHigh)));\n    if(Number.isFinite(Number(s.bearObLow)))guides.push(drawNativeLine(s.bearObLow,'#ff7b72',true,'BEAR OB LOW '+fmt(s.bearObLow)));\n    if(Number.isFinite(Number(s.bearObHigh)))guides.push(drawNativeLine(s.bearObHigh,'#ff7b72',true,'BEAR OB HIGH '+fmt(s.bearObHigh)));\n    if(Number.isFinite(Number(s.fvgLow)))guides.push(drawNativeLine(s.fvgLow,'#f2c94c',true,'FVG LOW '+fmt(s.fvgLow)));\n    if(Number.isFinite(Number(s.fvgHigh)))guides.push(drawNativeLine(s.fvgHigh,'#f2c94c',true,'FVG HIGH '+fmt(s.fvgHigh)));\n    drawTradeArrow(s);\n"""
if needle in h:
    h=h.replace(needle,extra,1)
html.write_text(h)

# Version metadata.
build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 74',b);b=re.sub(r'versionName = "[^"]+"','versionName = "74.0"',b);build.write_text(b)

print('v74 adaptive quality engine + re-evaluation + clean market-map UI applied')
