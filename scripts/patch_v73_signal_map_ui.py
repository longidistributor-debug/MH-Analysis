from pathlib import Path
import re

main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

# Green signal heading field.
if 'private lateinit var signalHeading:TextView' not in s:
    s=s.replace('    private lateinit var status:TextView\n', '    private lateinit var status:TextView\n    private lateinit var signalHeading:TextView\n', 1)

# Insert the dedicated signal heading above the detailed analysis text.
old='''        sc.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})\n        status=txt("$symbol • $period\\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH SETUP",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)\n'''
new='''        sc.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})\n        signalHeading=txt("",16f,true,Color.rgb(61,220,132)).apply{setPadding(dp(4),dp(12),dp(4),0)};sc.addView(signalHeading,LinearLayout.LayoutParams(-1,-2))\n        status=txt("$symbol • $period\\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH SETUP",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(8)});root.addView(sc)\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'signalHeading=txt(' not in s:
    raise SystemExit('v73 signal heading UI anchor not found')

# Always clear a previous timeframe's heading immediately.
s=s.replace('''        if(::status.isInitialized)status.text="$symbol • $period\\nTIMEFRAME CHANGED • PRESS NEW ANALYZE FOR FRESH DATA"\n        if(chartReady)chart.evaluateJavascript("clearSignalCard()",null)\n''','''        if(::signalHeading.isInitialized)signalHeading.text=""\n        if(::status.isInitialized)status.text="$symbol • $period\\nTIMEFRAME CHANGED • PRESS NEW ANALYZE FOR FRESH DATA"\n        if(chartReady)chart.evaluateJavascript("clearSignalCard()",null)\n''',1)

s=s.replace('''        if(analysisContext!=contextKey()&&::status.isInitialized){\n            status.text="$symbol • $period\\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH $period SETUP"\n        }\n''','''        if(analysisContext!=contextKey()&&::status.isInitialized){\n            if(::signalHeading.isInitialized)signalHeading.text=""\n            status.text="$symbol • $period\\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH $period SETUP"\n        }\n''',1)

# Clear heading during new request / failures / no setup so old signals can never appear current.
s=s.replace('''        busy=true;status.text="NEW ANALYZE • refreshing current $reqSymbol $reqPeriod candle and structure…"\n''','''        busy=true;if(::signalHeading.isInitialized)signalHeading.text="";status.text="NEW ANALYZE • refreshing current $reqSymbol $reqPeriod candle and structure…"\n''',1)
s=s.replace('''                    status.text="FRESH ANALYSIS UNAVAILABLE\\n${e.message}\\nNo stale signal was generated. TradingView remains live."\n                    showSignalCard(null)\n''','''                    signalHeading.text=""\n                    status.text="FRESH ANALYSIS UNAVAILABLE\\n${e.message}\\nNo stale signal was generated. TradingView remains live."\n                    showSignalCard(null)\n''',1)
s=s.replace('''                else{\n                    status.text="NO CURRENT SETUP\\n${marketContext()}\\n\\n${AnalysisEngine.noSignalReason(symbol,period,candles)}"\n                    showSignalCard(null)\n                }\n''','''                else{\n                    signalHeading.text=""\n                    status.text="NO CURRENT SETUP\\n${marketContext()}\\n\\n${AnalysisEngine.noSignalReason(symbol,period,candles)}"\n                    showSignalCard(null)\n                }\n''',1)

# Replace the compact setup output with the requested structured signal plan.
pattern=re.compile(r'''    private fun showSetup\(a:ActiveSignal\?,headline:String,note:String=""\)\{.*?\n    \}\n\n    private fun marketContext''',re.S)
replacement='''    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){\n        if(a==null){signalHeading.text="";status.text="$headline\\n${marketContext()}";showSignalCard(null);return}\n        val s=a.signal\n        val arrow=if(s.direction=="BUY")"↗" else "↘"\n        signalHeading.setTextColor(Color.rgb(61,220,132))\n        signalHeading.text="$arrow ${s.direction} SIGNAL • ${s.timeframe} • ${a.state}"\n        val confirmations=s.reasons.take(6).joinToString("\\n") { "• $it" }\n        val path="${price(s.entry)}  →  ${price(s.tp1)}  →  ${price(s.tp2)}"\n        val conclusion=buildString{\n            append("${s.direction} was selected because the current ${s.timeframe} formation produced the strongest valid confluence. ")\n            append(s.setupReason)\n            append(" The setup remains actionable only while its own ${s.timeframe} structure remains valid.")\n        }\n        status.text="""TRADE PLAN\nEntry  → ${price(s.entry)}\nTP1    → ${price(s.tp1)}\nTP2    → ${price(s.tp2)}\nSL     → ${price(s.sl)}\nPath   → $path\n\nWHY THIS TRADE\n${s.setupReason}\n\nWHY STOP LOSS\n${s.slReason}\n\nWHY TP1\n${s.tp1Reason}\n\nWHY TP2\n${s.tp2Reason}\n\nTRADE CONCLUSION\n$conclusion\n\nMARKET MAP\n${marketContext()}\nDATA BASIS • ${s.timeframe} candles only • no cross-timeframe dependency\n\nCONFIRMATIONS\n$confirmations${if(note.isBlank())"" else "\\n\\nUPDATE\\n$note"}""".trimIndent()\n        showSignalCard(a)\n    }\n\n    private fun marketContext'''
if pattern.search(s):
    # Lambda avoids re.sub interpreting Kotlin backslash escapes in replacement text.
    s=pattern.sub(lambda m: replacement,s,count=1)
else:
    raise SystemExit('v73 showSetup function not found')

# Send trade path + previous-day levels to the chart overlay.
pattern=re.compile(r'''    private fun showSignalCard\(a:ActiveSignal\?\)\{.*?\n    \}\n\n    private fun contextKey''',re.S)
replacement='''    private fun showSignalCard(a:ActiveSignal?){\n        if(!chartReady)return\n        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}\n        val s=a.signal\n        val j=JSONObject()\n            .put("direction",s.direction).put("state",a.state).put("timeframe",s.timeframe)\n            .put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)\n            .put("createdCandleTime",s.createdCandleTime)\n        previousDay?.let{j.put("pdHigh",it.high).put("pdLow",it.low)}\n        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)\n    }\n\n    private fun contextKey'''
if pattern.search(s):
    s=pattern.sub(lambda m: replacement,s,count=1)
else:
    raise SystemExit('v73 showSignalCard function not found')

# Visible version text. patch_v72 runs first, so this catches both committed and transformed labels.
s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v73 • SIGNAL MAP ENGINE',s,count=1)
main.write_text(s)

# -----------------------------------------------------------------------------
# TradingView widget is kept as-is; only a signal/map overlay layer is enhanced.
# -----------------------------------------------------------------------------
html=Path('app/src/main/assets/tradingview_live.html')
h=html.read_text()

h=h.replace('#signalCard{position:absolute;right:10px;top:10px;z-index:70;display:none;width:166px;', '#signalCard{position:absolute;right:10px;top:10px;z-index:70;display:none;width:205px;',1)
h=h.replace('#signalCard .head{font-size:11px;font-weight:800;margin-bottom:4px}', '#signalCard .head{font-size:11px;font-weight:800;margin-bottom:5px;color:#3ddc84}.route{margin:5px 0;padding:5px 6px;border-radius:6px;background:rgba(61,220,132,.10);font-weight:700}.pd{margin-top:4px;color:#c8ced9;font-size:8.5px}',1)

old='''  el.innerHTML='<div class="head">'+dir+' • '+String(s.state||'')+' • '+String(s.score||'-')+'/100</div>'+\n    '<div class="level"><span class="sw entry"></span>ENTRY '+fmt(s.entry)+'</div>'+\n    '<div class="level"><span class="sw sl"></span>SL '+fmt(s.sl)+'</div>'+\n    '<div class="level"><span class="sw tp1"></span>TP1 '+fmt(s.tp1)+'</div>'+\n    '<div class="level"><span class="sw tp2"></span>TP2 '+fmt(s.tp2)+'</div>';\n'''
new='''  const arrow=dir==='BUY'?'↗':'↘';\n  const pdh=Number.isFinite(Number(s.pdHigh))?fmt(s.pdHigh):'-';\n  const pdl=Number.isFinite(Number(s.pdLow))?fmt(s.pdLow):'-';\n  el.innerHTML='<div class="head">'+arrow+' '+dir+' SIGNAL • '+String(s.timeframe||'')+' • '+String(s.state||'')+'</div>'+\n    '<div class="route">TRADE '+fmt(s.entry)+' → '+fmt(s.tp1)+' → '+fmt(s.tp2)+'</div>'+\n    '<div class="level"><span class="sw entry"></span>ENTRY '+fmt(s.entry)+'</div>'+\n    '<div class="level"><span class="sw sl"></span>SL '+fmt(s.sl)+'</div>'+\n    '<div class="level"><span class="sw tp1"></span>TP1 '+fmt(s.tp1)+'</div>'+\n    '<div class="level"><span class="sw tp2"></span>TP2 '+fmt(s.tp2)+'</div>'+\n    '<div class="pd">PREV DAY HIGH '+pdh+'<br>PREV DAY LOW '+pdl+'</div>';\n'''
if old in h:
    h=h.replace(old,new,1)
else:
    raise SystemExit('v73 TradingView signal card anchor not found')

# Helper for exact arrow drawing when TradingView exposes its chart API.
anchor='''function drawSignal(s){\n'''
helper='''function tfSeconds(tf){tf=String(tf||'15m').toLowerCase();if(tf==='1m')return 60;if(tf==='5m')return 300;if(tf==='15m')return 900;if(tf==='30m')return 1800;return 3600}\nfunction drawTradeArrow(s){\n  if(!exactApi||!chartApi||typeof chartApi.createMultipointShape!=='function')return false;\n  const e=Number(s.entry),t=Number(s.tp1);if(!Number.isFinite(e)||!Number.isFinite(t))return false;\n  let ts=Number(s.createdCandleTime);if(ts>9999999999)ts=Math.floor(ts/1000);if(!Number.isFinite(ts)||ts<=0)ts=Math.floor(Date.now()/1000);\n  try{\n    const r=chartApi.createMultipointShape([{time:ts,price:e},{time:ts+tfSeconds(s.timeframe)*4,price:t}],{shape:'arrow',lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:'#3ddc84',linewidth:3,textcolor:'#3ddc84'}});\n    rememberShape(r);return true;\n  }catch(e){return false}\n}\n'''+anchor
if anchor in h and 'function drawTradeArrow' not in h:
    h=h.replace(anchor,helper,1)

old='''    const ok=[\n      drawNativeLine(s.entry,'#f2c94c',false,'ENTRY '+dir+' '+fmt(s.entry)),\n      drawNativeLine(s.sl,'#ff5a67',true,'SL '+fmt(s.sl)),\n      drawNativeLine(s.tp1,'#3ddc84',true,'TP1 '+fmt(s.tp1)),\n      drawNativeLine(s.tp2,'#56d7d1',true,'TP2 '+fmt(s.tp2))\n    ].every(Boolean);\n'''
new='''    const guides=[\n      drawNativeLine(s.entry,'#f2c94c',false,'ENTRY '+dir+' '+fmt(s.entry)),\n      drawNativeLine(s.sl,'#ff5a67',true,'SL '+fmt(s.sl)),\n      drawNativeLine(s.tp1,'#3ddc84',true,'TP1 '+fmt(s.tp1)),\n      drawNativeLine(s.tp2,'#56d7d1',true,'TP2 '+fmt(s.tp2))\n    ];\n    if(Number.isFinite(Number(s.pdHigh)))guides.push(drawNativeLine(s.pdHigh,'#8ab4f8',true,'PREV DAY HIGH '+fmt(s.pdHigh)));\n    if(Number.isFinite(Number(s.pdLow)))guides.push(drawNativeLine(s.pdLow,'#c58af9',true,'PREV DAY LOW '+fmt(s.pdLow)));\n    drawTradeArrow(s);\n    const ok=guides.every(Boolean);\n'''
if old in h:
    h=h.replace(old,new,1)
else:
    raise SystemExit('v73 TradingView guide anchor not found')

html.write_text(h)

# Version metadata.
build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 73',b);b=re.sub(r'versionName = "[^"]+"','versionName = "73.0"',b);build.write_text(b)

print('v73 signal heading, TP/SL reasoning and TradingView trade-map overlay applied')