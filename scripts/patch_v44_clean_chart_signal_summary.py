from pathlib import Path
import re

# v44: clean TradingView presentation + compact external signal/market map card.
# IMPORTANT: preserve the complete v42/v43 analysis engine and all setup families.
# The public TradingView embed cannot reliably bind our external price levels to
# its internal pan/zoom transform, so v44 removes fake HTML/native-shape overlays
# and presents those calculated levels in an Android card ABOVE the chart.
# Signal detail below the chart now shows only the actually matched setup/reasons.

# -----------------------------------------------------------------------------
# MainActivity: add a compact CURRENT SIGNAL + MARKET MAP card above TradingView.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Field for the summary card.
field='''    private lateinit var status:TextView\n'''
if 'private lateinit var chartSummary:TextView' not in s:
    if field not in s: raise SystemExit('v44 chartSummary field anchor not found')
    s=s.replace(field,field+'    private lateinit var chartSummary:TextView\n',1)

# Put the summary ABOVE the chart so no candles are covered.
old='''        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{\n'''
new='''        root.addView(section("LIVE MARKET CHART"));val cc=card()\n        chartSummary=txt("",11.5f,false).apply{setPadding(dp(12),dp(10),dp(12),dp(10));background=round(Color.rgb(10,13,17),11f,Color.DKGRAY)}\n        cc.addView(chartSummary,LinearLayout.LayoutParams(-1,-2).apply{bottomMargin=dp(8)})\n        chart=WebView(this).apply{\n'''
if old not in s: raise SystemExit('v44 chart card anchor not found')
s=s.replace(old,new,1)

# Expand styled section headings to include the new compact sections.
s=s.replace('''val section=trimmed in setOf("SIGNAL","TRADE LEVELS","WHY THIS TRADE","CONFIRMATIONS","RE-EVALUATION")''',
'''val section=trimmed in setOf("CURRENT SIGNAL","MARKET MAP","SIGNAL","TRADE LEVELS","EXACT SETUP MATCH","MATCHED CONFIRMATIONS","RE-EVALUATION")''',1)

# Replace chart signal overlay behavior: update Android summary only; keep TV clean.
start=s.index('    private fun showSignalCard(a:ActiveSignal?){')
end=s.index('\n    private fun showAnalysisGuides',start)
new_show_signal='''    private fun showSignalCard(a:ActiveSignal?){
        val data=FcsClient.peek(symbol,period,220)
        val lv=if(data.isNullOrEmpty())null else AnalysisEngine.chartLevels(period,data)
        updateChartSummary(a,lv)
        if(chartReady)chart.evaluateJavascript("clearSignalCard();clearAnalysisLevels()",null)
    }

    private fun updateChartSummary(a:ActiveSignal?,lv:AnalysisEngine.ChartLevels?){
        if(!::chartSummary.isInitialized)return
        val out=StringBuilder()
        out.append("CURRENT SIGNAL\\n")
        if(a==null){
            out.append("➜ NONE • press ANALYZE for a fresh setup\\n\\n")
        }else{
            val x=a.signal
            out.append("➜ ${x.direction} • ${a.state} • ${x.score}/100\\n")
            out.append("➜ ENTRY ${price(x.entry)} • SL ${price(x.sl)}\\n")
            out.append("➜ TP1 ${price(x.tp1)} • TP2 ${price(x.tp2)}\\n\\n")
        }
        out.append("MARKET MAP\\n")
        if(lv==null){
            out.append("➜ $symbol • $period • press ANALYZE to calculate current levels")
        }else{
            out.append("➜ $symbol • $period • Support ${price(lv.support)} • Resistance ${price(lv.resistance)}\\n")
            if(lv.bullObLow!=null&&lv.bullObHigh!=null)out.append("➜ Bull OB ${price(lv.bullObLow)}–${price(lv.bullObHigh)}\\n")
            if(lv.bearObLow!=null&&lv.bearObHigh!=null)out.append("➜ Bear OB ${price(lv.bearObLow)}–${price(lv.bearObHigh)}\\n")
            if(lv.bullObLow==null&&lv.bearObLow==null)out.append("➜ No validated active order block near current structure\\n")
        }
        chartSummary.text=styledOutput(out.toString().trimEnd())
    }
'''
s=s[:start]+new_show_signal+s[end:]

# Analysis guide calls now update the top card only. Never draw approximate overlay
# levels on the embedded TradingView chart.
start=s.index('    private fun showAnalysisGuides(data:List<Candle>){')
end=s.index('\n    private fun showCachedAnalysisGuides()',start)
new_guides='''    private fun showAnalysisGuides(data:List<Candle>){
        val lv=AnalysisEngine.chartLevels(period,data)
        updateChartSummary(SignalStore.loadActive(this,symbol,period),lv)
        if(chartReady)chart.evaluateJavascript("clearAnalysisLevels();clearSignalCard()",null)
    }
'''
s=s[:start]+new_guides+s[end:]

start=s.index('    private fun showCachedAnalysisGuides(){')
end=s.index('\n\n    private fun showExisting(){',start)
new_cached='''    private fun showCachedAnalysisGuides(){
        val data=FcsClient.peek(symbol,period,220)
        val lv=if(data.isNullOrEmpty())null else AnalysisEngine.chartLevels(period,data)
        updateChartSummary(SignalStore.loadActive(this,symbol,period),lv)
        if(chartReady)chart.evaluateJavascript("clearAnalysisLevels();clearSignalCard()",null)
    }'''
s=s[:start]+new_cached+s[end:]

# Rebuild the signal detail so it contains only the setup that actually matched and
# reasons that actually earned confluence points. No overall indicator dump.
start=s.index('    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{')
end=s.index('\n    private fun showRecords()',start)
new_format='''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{
        val sig=a.signal
        val out=StringBuilder()
        out.append("SIGNAL\\n")
        out.append("➜ ${sig.direction} • ${a.state} • ${sig.score}/100\\n\\n")
        out.append("TRADE LEVELS\\n")
        out.append("➜ ENTRY ${price(sig.entry)} • SL ${price(sig.sl)}\\n")
        out.append("➜ TP1 ${price(sig.tp1)} • TP2 ${price(sig.tp2)}\\n\\n")
        out.append("EXACT SETUP MATCH\\n")
        out.append(arrowLines(sig.setupReason)).append("\\n\\n")
        out.append("MATCHED CONFIRMATIONS\\n")
        val matched=sig.reasons.distinct().take(7)
        if(matched.isEmpty())out.append("➜ Setup-family conditions supplied the qualifying confluence.\\n")
        else matched.forEach{out.append("➜ ").append(it).append("\\n")}
        val conclusion=forcedConclusion?:SignalStore.manualReason(this,sig.id).ifBlank{
            when(a.state){
                "PENDING"->"Signal is saved as PENDING. Time or candle count alone never expires it; use RE-EVALUATE SIGNAL for a fresh validity check."
                "STILL VALID"->"Fresh re-evaluation confirms the original setup is still valid."
                "WEAKENING"->"Fresh re-evaluation found weaker confluence; read the exact reason below."
                "EXPIRED"->"Fresh re-evaluation invalidated the original setup; read the exact market reason below."
                else->a.state
            }
        }
        out.append("\\nRE-EVALUATION\\n").append(arrowLines(conclusion))
        return out.toString()
    }

'''
s=s[:start]+new_format+s[end:]

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: the same embedded TradingView must remain clean.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
# Existing methods may still call setSignalCard/setAnalysisLevels; the v44 HTML
# functions below make them clean no-ops, so no fragile Kotlin rewrite is required.
p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView HTML: remove all app-generated overlays/shapes from the public embed.
# Native TradingView candles/zoom/pan remain untouched.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text()
# Force all overlay DOM elements hidden even if earlier patches created them.
if '#signalCard,#analysisGuideLayer,#analysisLegend,#apiState{display:none!important}' not in s:
    s=s.replace('</style>','#signalCard,#analysisGuideLayer,#analysisLegend,#apiState{display:none!important}\n</style>',1)

# Override v42/v43 bridge functions at the END of the script. Function declarations
# later in the same script win, preventing createShape and approximate DOM guides.
override='''
// v44 CLEAN PUBLIC-WIDGET MODE: app-generated signal/SR/OB overlays are shown in
// Android UI above the chart. The embedded TradingView surface stays unobstructed.
function setSignalCard(raw){
  lastSignal=null;try{removeNativeShapes()}catch(e){}
  const el=document.getElementById('signalCard');if(el){el.style.display='none';el.innerHTML=''}
}
function clearSignalCard(){
  lastSignal=null;try{removeNativeShapes()}catch(e){}
  const el=document.getElementById('signalCard');if(el){el.style.display='none';el.innerHTML=''}
}
function setAnalysisLevels(raw){
  lastAnalysis=null;try{removeNativeShapes()}catch(e){}
  const layer=document.getElementById('analysisGuideLayer');if(layer)layer.innerHTML='';
  const legend=document.getElementById('analysisLegend');if(legend){legend.style.display='none';legend.innerHTML=''}
}
function clearAnalysisLevels(){
  lastAnalysis=null;try{removeNativeShapes()}catch(e){}
  const layer=document.getElementById('analysisGuideLayer');if(layer)layer.innerHTML='';
  const legend=document.getElementById('analysisLegend');if(legend){legend.style.display='none';legend.innerHTML=''}
}
'''
if 'v44 CLEAN PUBLIC-WIDGET MODE' not in s:
    pos=s.rfind('</script>')
    if pos<0: raise SystemExit('v44 HTML script end not found')
    s=s[:pos]+override+s[pos:]
p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 44',s);s=re.sub(r'versionName = "[^"]+"','versionName = "44.0"',s);p.write_text(s)

print('v44 clean chart + external signal/market map + exact-match detail applied')
