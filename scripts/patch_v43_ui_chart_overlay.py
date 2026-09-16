from pathlib import Path
import re

# v43: presentation clarity + fail-safe TradingView overlay.
# Preserve the full v42 analysis engine. This patch only changes output hierarchy
# and chart visualization; no indicator/setup family is removed.

# -----------------------------------------------------------------------------
# Main activity: concise NO TRADE output and green headings for readable blocks.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Imports for styled status output.
if 'import android.text.SpannableString' not in s:
    s=s.replace('import android.text.InputType\n', 'import android.text.InputType\nimport android.text.SpannableString\nimport android.text.Spanned\nimport android.text.style.ForegroundColorSpan\nimport android.text.style.StyleSpan\n',1)

# No-trade should be concise. Keep the full engine running, only summarize the UI.
s=s.replace('''            status.text=AnalysisEngine.noSignalReason(symbol,period,candles)\n            showSignalCard(SignalStore.loadActive(this,symbol,period))\n''', '''            val full=AnalysisEngine.noSignalReason(symbol,period,candles)\n            status.text=styledOutput(compactNoTrade(full))\n            showSignalCard(SignalStore.loadActive(this,symbol,period))\n''',1)

# Re-evaluation result should also use visual hierarchy.
s=s.replace('''                    status.text=formatManualSignal(next,result.reason)\n                    showSignalCard(next);showAnalysisGuides(out)\n''','''                    status.text=styledOutput(formatManualSignal(next,result.reason))\n                    showSignalCard(next);showAnalysisGuides(out)\n''',1)

# Existing/manual signal render should be styled.
s=s.replace('''        status.text=formatManualSignal(a)\n        showSignalCard(a)\n''','''        status.text=styledOutput(formatManualSignal(a))\n        showSignalCard(a)\n''',1)

# Other formatManualSignal assignments used by re-evaluate early exits.
s=s.replace('''status.text=formatManualSignal(current,"This signal is already EXPIRED. Press ANALYZE when you want a fresh setup.")''','''status.text=styledOutput(formatManualSignal(current,"This signal is already EXPIRED. Press ANALYZE when you want a fresh setup."))''')

# Give the signal result clearer block titles without changing any underlying values.
s=s.replace('''        out.append("➜ SIGNAL: ${sig.direction} • ${sig.score}/100\\n")\n        out.append("➜ STATUS: ${a.state}\\n")\n        out.append("➜ ENTRY: ${price(sig.entry)}\\n")\n        out.append("➜ SL: ${price(sig.sl)}\\n")\n        out.append("➜ TP1: ${price(sig.tp1)}\\n")\n        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")\n        out.append("WHY THIS TRADE\\n").append(arrowLines(sig.setupReason)).append("\\n\\n")\n        out.append("CONFIRMATIONS\\n")\n''','''        out.append("SIGNAL\\n")\n        out.append("➜ DIRECTION: ${sig.direction}\\n")\n        out.append("➜ CONFIDENCE: ${sig.score}/100\\n")\n        out.append("➜ STATUS: ${a.state}\\n\\n")\n        out.append("TRADE LEVELS\\n")\n        out.append("➜ ENTRY: ${price(sig.entry)}\\n")\n        out.append("➜ SL: ${price(sig.sl)}\\n")\n        out.append("➜ TP1: ${price(sig.tp1)}\\n")\n        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")\n        out.append("WHY THIS TRADE\\n").append(arrowLines(sig.setupReason)).append("\\n\\n")\n        out.append("CONFIRMATIONS\\n")\n''',1)

# Add compact + styling helpers before formatManualSignal.
anchor='''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{'''
if 'private fun compactNoTrade(' not in s:
    helpers='''    private fun compactNoTrade(full:String):String{\n        val lines=full.lines().map{it.trim()}.filter{it.isNotBlank()}\n        val first=lines.firstOrNull{it.contains("NO TRADE")}?:"➜ NO TRADE • $symbol • $period"\n        val regime=lines.firstOrNull{it.contains("REGIME:")}?.substringAfter("REGIME:")?.trim()\n        val bias=lines.firstOrNull{it.contains("BIAS:")}?.substringAfter("BIAS:")?.substringBefore("• EMA20")?.trim()\n        val waiting=lines.firstOrNull{it.contains("WAITING FOR:")}?.substringAfter("WAITING FOR:")?.trim()\n            ?:"The full confluence engine does not have enough confirmed alignment yet."\n        return buildString{\n            append(first).append("\\n")\n            append("➜ MARKET: ").append(listOfNotNull(bias,regime).joinToString(" • ")).append("\\n")\n            append("➜ WHY NO TRADE: ").append(waiting)\n        }\n    }\n\n    private fun styledOutput(raw:String):CharSequence{\n        val out=SpannableString(raw);val green=Color.rgb(63,220,132)\n        var offset=0\n        raw.split("\\n").forEach{line->\n            val start=offset;val end=start+line.length\n            val trimmed=line.trim()\n            val section=trimmed in setOf("SIGNAL","TRADE LEVELS","WHY THIS TRADE","CONFIRMATIONS","RE-EVALUATION")\n            if(section&&end>start){\n                out.setSpan(ForegroundColorSpan(green),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n                out.setSpan(StyleSpan(Typeface.BOLD),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n            }else{\n                val colon=line.indexOf(':')\n                if(colon>0){\n                    var hs=start\n                    while(hs<end&&(raw[hs]=='➜'||raw[hs]==' '))hs++\n                    val he=(start+colon+1).coerceAtMost(end)\n                    if(he>hs){\n                        out.setSpan(ForegroundColorSpan(green),hs,he,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n                        out.setSpan(StyleSpan(Typeface.BOLD),hs,he,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n                    }\n                }else if(trimmed.contains("NO TRADE")&&end>start){\n                    out.setSpan(ForegroundColorSpan(green),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n                    out.setSpan(StyleSpan(Typeface.BOLD),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)\n                }\n            }\n            offset=end+1\n        }\n        return out\n    }\n\n'''
    if anchor not in s: raise SystemExit('v43 formatManualSignal anchor not found')
    s=s.replace(anchor,helpers+anchor,1)

# When sending analysis guides, also send an analysis-derived visible range so the
# HTML overlay can place the guides even if TradingView's private drawing API is absent.
old='''        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance)\n        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)}\n        lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}\n        chart.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)\n'''
new='''        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)\n        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)}\n        lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}\n        val visibleBars=when(period){"1m"->80;"5m"->60;"10m"->52;"15m"->46;"30m"->40;"1h"->36;"2h"->34;"4h"->32;"5h"->30;"1d"->28;"1w"->26;"1M"->24;else->40}\n        val w=data.takeLast(visibleBars.coerceAtMost(data.size));if(w.isNotEmpty()){val lo=w.minOf{it.l};val hi=w.maxOf{it.h};val span=(hi-lo).coerceAtLeast(kotlin.math.abs(hi)*0.0004).coerceAtLeast(0.0001);j.put("viewLow",lo-span*.08).put("viewHigh",hi+span*.08)}\n        chart.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)\n'''
if old not in s: raise SystemExit('v43 main analysis-guide JSON anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: send the same view range so chart levels render consistently.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
old='''        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance)\n        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}\n        chart?.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)\n'''
new='''        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)\n        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}\n        val visibleBars=when(period){"1m"->80;"5m"->60;"10m"->52;"15m"->46;"30m"->40;"1h"->36;"2h"->34;"4h"->32;"5h"->30;"1d"->28;"1w"->26;"1M"->24;else->40}\n        val w=data.takeLast(visibleBars.coerceAtMost(data.size));if(w.isNotEmpty()){val lo=w.minOf{it.l};val hi=w.maxOf{it.h};val span=(hi-lo).coerceAtLeast(kotlin.math.abs(hi)*0.0004).coerceAtLeast(0.0001);j.put("viewLow",lo-span*.08).put("viewHigh",hi+span*.08)}\n        chart?.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)\n'''
if old not in s: raise SystemExit('v43 overlay guide JSON anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView HTML: always-visible DOM guides + native shapes when supported.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text()

# CSS overlay that does not depend on private TradingView drawing functions.
if '#analysisGuideLayer' not in s:
    s=s.replace('''#apiState{position:absolute;left:8px;bottom:7px;z-index:65;display:none;background:rgba(9,12,18,.72);border:1px solid rgba(255,255,255,.10);border-radius:6px;padding:3px 6px;color:#b9c0cb;font-size:8px;pointer-events:none}\n''','''#apiState{position:absolute;left:8px;bottom:7px;z-index:65;display:none;background:rgba(9,12,18,.72);border:1px solid rgba(255,255,255,.10);border-radius:6px;padding:3px 6px;color:#b9c0cb;font-size:8px;pointer-events:none}\n#analysisGuideLayer{position:absolute;inset:0;z-index:50;pointer-events:none;overflow:hidden}\n.agLine{position:absolute;left:3%;right:4%;height:0;border-top:1px dashed rgba(255,255,255,.75)}\n.agLabel{position:absolute;left:4px;top:-10px;padding:2px 5px;border-radius:4px;background:rgba(8,11,16,.84);font-size:9px;font-weight:700;white-space:nowrap}\n.agSupport{border-color:#42a5f5}.agSupport .agLabel{color:#75baff}.agResistance{border-color:#ce93d8}.agResistance .agLabel{color:#e1bee7}\n.agBullOb{position:absolute;left:3%;right:4%;background:rgba(38,166,154,.10);border-top:1px dashed rgba(38,166,154,.9);border-bottom:1px dashed rgba(38,166,154,.9)}\n.agBearOb{position:absolute;left:3%;right:4%;background:rgba(239,83,80,.09);border-top:1px dashed rgba(239,83,80,.9);border-bottom:1px dashed rgba(239,83,80,.9)}\n.agZoneLabel{position:absolute;left:4px;top:2px;padding:2px 5px;border-radius:4px;background:rgba(8,11,16,.84);font-size:9px;font-weight:700;white-space:nowrap}.agBullOb .agZoneLabel{color:#62d8ca}.agBearOb .agZoneLabel{color:#ff7d79}\n#analysisLegend{position:absolute;left:8px;top:52px;z-index:55;display:none;background:rgba(8,11,16,.82);border:1px solid rgba(255,255,255,.12);border-radius:7px;padding:5px 7px;color:#fff;font-size:8px;line-height:1.45;pointer-events:none}.lgHead{color:#3fdc84;font-weight:800;margin-bottom:2px}\n''',1)
    s=s.replace('''  <div id="signalCard"></div>\n  <div id="apiState"></div>\n''','''  <div id="analysisGuideLayer"></div>\n  <div id="analysisLegend"></div>\n  <div id="signalCard"></div>\n  <div id="apiState"></div>\n''',1)

# Add fail-safe DOM rendering before redrawAll.
anchor='''function redrawAll(){'''
if 'function renderAnalysisDom' not in s:
    js='''function guidePct(price,x){\n  const lo=Number(x&&x.viewLow),hi=Number(x&&x.viewHigh),p=Number(price);\n  if(!Number.isFinite(lo)||!Number.isFinite(hi)||!Number.isFinite(p)||hi<=lo)return null;\n  const r=(hi-p)/(hi-lo);return Math.max(8,Math.min(93,8+r*85));\n}\nfunction addGuideLine(layer,price,x,cls,label){\n  const y=guidePct(price,x);if(y===null)return;const d=document.createElement('div');d.className='agLine '+cls;d.style.top=y+'%';d.innerHTML='<span class="agLabel">'+label+' '+fmt(price)+'</span>';layer.appendChild(d);\n}\nfunction addObZone(layer,low,high,x,cls,label){\n  const a=guidePct(high,x),b=guidePct(low,x);if(a===null||b===null)return;const top=Math.min(a,b),bottom=Math.max(a,b);const d=document.createElement('div');d.className=cls;d.style.top=top+'%';d.style.height=Math.max(1.2,bottom-top)+'%';d.innerHTML='<span class="agZoneLabel">'+label+' '+fmt(low)+'–'+fmt(high)+'</span>';layer.appendChild(d);\n}\nfunction renderAnalysisDom(x){\n  const layer=document.getElementById('analysisGuideLayer'),legend=document.getElementById('analysisLegend');if(!layer||!legend)return;layer.innerHTML='';\n  if(!x){legend.style.display='none';legend.innerHTML='';return}\n  addGuideLine(layer,x.support,x,'agSupport','SUPPORT');addGuideLine(layer,x.resistance,x,'agResistance','RESISTANCE');\n  if(Number.isFinite(Number(x.bullObLow))&&Number.isFinite(Number(x.bullObHigh)))addObZone(layer,Number(x.bullObLow),Number(x.bullObHigh),x,'agBullOb','BULL OB');\n  if(Number.isFinite(Number(x.bearObLow))&&Number.isFinite(Number(x.bearObHigh)))addObZone(layer,Number(x.bearObLow),Number(x.bearObHigh),x,'agBearOb','BEAR OB');\n  let h='<div class="lgHead">MARKET MAP • '+String(x.timeframe||'')+'</div><div>SUP '+fmt(x.support)+' • RES '+fmt(x.resistance)+'</div>';\n  if(Number.isFinite(Number(x.bullObLow)))h+='<div style="color:#62d8ca">Bull OB '+fmt(x.bullObLow)+'–'+fmt(x.bullObHigh)+'</div>';\n  if(Number.isFinite(Number(x.bearObLow)))h+='<div style="color:#ff7d79">Bear OB '+fmt(x.bearObLow)+'–'+fmt(x.bearObHigh)+'</div>';legend.innerHTML=h;legend.style.display='block';\n}\n'''
    if anchor not in s: raise SystemExit('v43 redrawAll anchor not found')
    s=s.replace(anchor,js+anchor,1)

# DOM guides render regardless of exactApi; native shapes remain an optional enhancement.
s=s.replace('''function redrawAll(){\n  removeNativeShapes();\n  if(!exactApi||!chartApi)return;\n''','''function redrawAll(){\n  renderAnalysisDom(lastAnalysis);\n  removeNativeShapes();\n  if(!exactApi||!chartApi)return;\n''',1)

p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 43',s);s=re.sub(r'versionName = "[^"]+"','versionName = "43.0"',s);p.write_text(s)
print('v43 concise UI + styled headings + reliable chart overlay applied')
