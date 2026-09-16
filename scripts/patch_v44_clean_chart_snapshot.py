from pathlib import Path
import re

# v44: clean TradingView + separate live snapshot + exact-match signal summary.
# Analysis engine is unchanged. This patch only changes presentation and where
# signal/market-map information is shown.

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Dedicated snapshot text view above the chart.
s=s.replace('''    private lateinit var pairLabel:TextView\n''','''    private lateinit var pairLabel:TextView\n    private lateinit var snapshot:TextView\n''',1)

chart_anchor='''        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{'''
if chart_anchor not in s:
    raise SystemExit('v44 chart section anchor not found')
snapshot_ui='''        root.addView(section("LIVE ANALYSIS SNAPSHOT"))
        val snapCard=card()
        snapshot=txt("NO ACTIVE SIGNAL\\nMarket map appears after ANALYZE for the selected timeframe.",11.5f,false).apply{
            setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)
        }
        snapCard.addView(snapshot,LinearLayout.LayoutParams(-1,-2));root.addView(snapCard)

        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{'''
s=s.replace(chart_anchor,snapshot_ui,1)

# Switching market/timeframe updates the separate snapshot; TradingView stays visual-only.
s=s.replace('''    private fun switchVisibleChart(){pairLabel.text="$symbol • $period";if(chartReady){chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showCachedAnalysisGuides()};showExisting()}''',
'''    private fun switchVisibleChart(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showExisting();updateSnapshot()}''',1)

# Signal card no longer draws over TradingView. It only refreshes the separate snapshot.
start=s.index('    private fun showSignalCard(a:ActiveSignal?){')
next_guides='\n    private fun showAnalysisGuides(data:List<Candle>){'
end=s.index(next_guides,start) if next_guides in s[start:] else s.index('\n    private fun showExisting(){',start)
new_signal_card='''    private fun showSignalCard(a:ActiveSignal?){
        updateSnapshot()
    }
'''
s=s[:start]+new_signal_card+s[end:]

# Analysis guide functions become snapshot refreshers. No custom S/R/OB overlay on chart.
if '    private fun showAnalysisGuides(data:List<Candle>){' in s:
    start=s.index('    private fun showAnalysisGuides(data:List<Candle>){')
    end=s.index('\n    private fun showExisting(){',start)
    new_guides='''    private fun showAnalysisGuides(data:List<Candle>){
        updateSnapshot(data)
    }
    private fun showCachedAnalysisGuides(){updateSnapshot()}

    private fun updateSnapshot(data:List<Candle>?=null){
        if(!::snapshot.isInitialized)return
        val active=SignalStore.loadActive(this,symbol,period)
        val basis=data?:FcsClient.peek(symbol,period,220)
        val lv=if(!basis.isNullOrEmpty())AnalysisEngine.chartLevels(period,basis) else null
        val out=StringBuilder()
        out.append("CURRENT SETUP\\n")
        if(active==null){
            out.append("➜ SIGNAL: None for $symbol • $period\\n")
        }else{
            val sig=active.signal
            out.append("➜ SIGNAL: ${sig.direction} • ${active.state} • ${sig.score}/100\\n")
            out.append("➜ ENTRY: ${price(sig.entry)}   SL: ${price(sig.sl)}\\n")
            out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\\n")
        }
        out.append("\\nMARKET MAP • $period\\n")
        if(lv==null){
            out.append("➜ Press ANALYZE to calculate selected-timeframe levels.")
        }else{
            out.append("➜ SUPPORT: ${price(lv.support)}   RESISTANCE: ${price(lv.resistance)}\\n")
            val bull=if(lv.bullObLow!=null&&lv.bullObHigh!=null)"${price(lv.bullObLow)}–${price(lv.bullObHigh)}" else "-"
            val bear=if(lv.bearObLow!=null&&lv.bearObHigh!=null)"${price(lv.bearObLow)}–${price(lv.bearObHigh)}" else "-"
            out.append("➜ BULL OB: $bull\\n")
            out.append("➜ BEAR OB: $bear")
        }
        snapshot.text=styledOutput(out.toString())
    }

'''
    s=s[:start]+new_guides+s[end:]
else:
    raise SystemExit('v44 analysis guide function not found')

# Replace the long signal report with exact-match evidence only.
start=s.index('    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{')
end=s.index('\n    private fun showRecords()',start)
new_format='''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{
        val sig=a.signal
        val matched=sig.reasons.map{it.trim()}.filter{it.isNotBlank()}.distinct().take(5)
        val out=StringBuilder()
        out.append("SETUP\\n")
        out.append("➜ ${sig.direction} • ${sig.score}/100 • ${a.state}\\n")
        out.append("➜ ${sig.setupReason.trim()}\\n\\n")
        out.append("MATCHED CONFIRMATIONS\\n")
        if(matched.isEmpty())out.append("➜ Primary setup conditions matched.") else matched.forEach{out.append("➜ ").append(it).append("\\n")}
        out.append("\\nTRADE LEVELS\\n")
        out.append("➜ ENTRY: ${price(sig.entry)}\\n")
        out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\\n")
        out.append("➜ SL / INVALIDATION: ${price(sig.sl)}")
        val conclusion=forcedConclusion?:SignalStore.manualReason(this,sig.id).takeIf{it.isNotBlank()}
        if(conclusion!=null||a.state!="PENDING"){
            val text=conclusion?:when(a.state){
                "STILL VALID"->"Fresh re-evaluation confirms the original setup is still valid."
                "WEAKENING"->"Fresh re-evaluation found weaker confirmation; setup has not fully invalidated yet."
                "EXPIRED"->"Fresh market evidence invalidated the original setup."
                else->a.state
            }
            out.append("\\n\\nRE-EVALUATION\\n").append(arrowLines(text))
        }
        return out.toString().trim()
    }
'''
s=s[:start]+new_format+s[end:]

# Ensure styledOutput recognizes v44 section names.
s=s.replace('''val section=trimmed in setOf("SIGNAL","TRADE LEVELS","WHY THIS TRADE","CONFIRMATIONS","RE-EVALUATION")''',
'''val section=trimmed in setOf("CURRENT SETUP","SETUP","MATCHED CONFIRMATIONS","TRADE LEVELS","RE-EVALUATION")''',1)
s=s.replace('''            if(section&&end>start){''','''            if((section||trimmed.startsWith("MARKET MAP"))&&end>start){''',1)

p.write_text(s)

# TradingView is visual-only. Hide app-added overlays and disable native app shapes.
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text()
if '/* v44 clean chart */' not in s:
    s=s.replace('</style>','''/* v44 clean chart */\n#analysisGuideLayer,#analysisLegend,#signalCard,#apiState{display:none!important;visibility:hidden!important}\n</style>''',1)
    override='''\n// v44: TradingView is visual-only. All app analysis is shown outside the chart.\nfunction redrawAll(){try{removeNativeShapes()}catch(e){}}\nfunction drawSignal(s){lastSignal=s;try{removeNativeShapes()}catch(e){}}\nfunction setAnalysisLevels(raw){try{lastAnalysis=(typeof raw==='string'?JSON.parse(raw):raw)}catch(e){lastAnalysis=null}try{removeNativeShapes()}catch(e){}}\nfunction clearAnalysisLevels(){lastAnalysis=null;try{removeNativeShapes()}catch(e){}}\nfunction renderSignalCard(s){const el=document.getElementById('signalCard');if(el){el.style.display='none';el.innerHTML=''}}\nfunction renderAnalysisDom(x){const a=document.getElementById('analysisGuideLayer'),b=document.getElementById('analysisLegend');if(a)a.innerHTML='';if(b){b.innerHTML='';b.style.display='none'}}\n'''
    s=s.replace('</script>',override+'\n</script>',1)
p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 44',s);s=re.sub(r'versionName = "[^"]+"','versionName = "44.0"',s);p.write_text(s)

print('v44 clean chart + separate snapshot + exact-match output applied')
