from pathlib import Path
import re

# v50 UI-only cleanup.
# - Remove provider/data diagnostics from Market Map.
# - Keep TRADE LEVELS -> SETUP -> MATCHED CONFIRMATIONS order.
# - SETUP is one concise line; confirmations are one arrow per row.
# - RE-EVALUATION appears only when explicitly requested.
# - Keep the genuine live TradingView widget unchanged.

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Remove the provider/data line from the v49 snapshot while retaining internal
# freshness checks used to suppress stale market maps.
s=re.sub(r'''\n        val ageText=age\?\.let\{if\(it<1000L\)"now" else "\$\{it/1000L\}s ago"\}\?:"unknown"\n        out\.append\("➜ DATA: \$\{FcsClient\.feedLabel\(symbol\)\} • \$ageText"\)\n        current\?\.let\{out\.append\(" • close \$\{price\(it\)\}"\)\};out\.append\("\\n"\)''','',s,count=1)

# Rebuild the manual signal report with a concise setup title and row-by-row
# matched confirmations.
start=s.index('    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{')
end=s.index('\n    private fun showRecords()',start)
new_format='''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{\n        val sig=a.signal\n        val matched=sig.reasons.map{it.trim()}.filter{it.isNotBlank()}.distinct().take(7)\n        val raw=sig.setupReason.trim()\n        val title=raw.substringBefore(". Evidence:").substringBefore(" Evidence:").trim().ifBlank{"Qualified ${sig.direction} setup on ${sig.timeframe}"}\n        val out=StringBuilder()\n        out.append("TRADE LEVELS\\n")\n        out.append("➜ ${sig.direction} • ${sig.score}/100 • ${a.state}\\n")\n        out.append("➜ ENTRY: ${price(sig.entry)}\\n")\n        out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\\n")\n        out.append("➜ SL / INVALIDATION: ${price(sig.sl)}\\n\\n")\n        out.append("SETUP\\n")\n        out.append("➜ ").append(title).append("\\n\\n")\n        out.append("MATCHED CONFIRMATIONS\\n")\n        if(matched.isEmpty())out.append("➜ Primary setup conditions matched.")\n        else matched.forEach{out.append("➜ ").append(it).append("\\n")}\n        if(forcedConclusion!=null){out.append("\\nRE-EVALUATION\\n").append(arrowLines(forcedConclusion))}\n        return out.toString().trim()\n    }\n'''
s=s[:start]+new_format+s[end:]
p.write_text(s)

# Remove the capability warning text from inside the chart; leave only the
# neutral live-chart label. This does not add fake overlays.
p=Path('app/src/main/assets/tradingview_live.html')
h=p.read_text()
h=h.replace("if(st)st.textContent='LIVE TRADINGVIEW • NATIVE MARKS '+(nativeOk?'ON':'UNAVAILABLE');",
            "if(st)st.textContent='LIVE TRADINGVIEW';")
p.write_text(h)

p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \\d+','versionCode = 50',s);s=re.sub(r'versionName = "[^"]+"','versionName = "50.0"',s);p.write_text(s)
print('v50 UI cleanup applied')
