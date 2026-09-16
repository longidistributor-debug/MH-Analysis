from pathlib import Path
import re

# v47: restore the real live TradingView widget for visual market movement and
# make the manual-analysis product keep only one current signal per symbol.
# Analysis remains FCS/API-driven only when ANALYZE or RE-EVALUATE is pressed.

# -----------------------------------------------------------------------------
# SignalStore: only one active manual signal per symbol across all timeframes.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()
anchor='''    fun clearActive(c:Context,symbol:String,timeframe:String){prefs(c).edit().remove(activeKey(symbol,timeframe)).apply()}'''
if 'fun clearActiveForSymbol' not in s:
    helper='''    fun clearActive(c:Context,symbol:String,timeframe:String){prefs(c).edit().remove(activeKey(symbol,timeframe)).apply()}
    fun clearActiveForSymbol(c:Context,symbol:String){
        val prefix="active_${symbol.uppercase()}_"
        val e=prefs(c).edit();prefs(c).all.keys.filter{it.startsWith(prefix)}.forEach{e.remove(it)};e.apply()
    }'''
    if anchor not in s: raise SystemExit('v47 clearActive anchor not found')
    s=s.replace(anchor,helper,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: latest successful ANALYZE owns the one active signal for symbol;
# stop chart-side FCS socket/candle pushing; real TradingView handles live motion.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Remove LiveSocketHub listener from Activity declaration.
s=s.replace('class MainActivityV29:Activity(),LiveSocketHub.Listener{','class MainActivityV29:Activity(){',1)

# Remove v45 live listener callback if present.
s=re.sub(r'''\n    override fun onLiveCandle\(symbol:String,timeframe:String,candle:Candle\)\{.*?\n    \}\n''','\n',s,count=1,flags=re.S)
# Remove listener/socket start snippets injected into existing lifecycle methods.
s=s.replace('LiveSocketHub.addListener(this);','')
s=s.replace('LiveSocketHub.removeListener(this);','')
s=re.sub(r'''\n?\s*val liveKey=prefs\.getString\("socket_api_key",""\)\?\.trim\(\)\.orEmpty\(\)\.ifBlank\{savedHistoryKey\(\)\}\n\s*if\(liveKey\.isNotBlank\(\)\)LiveSocketHub\.start\(this,liveKey\)''','',s)

# Restore TradingView widget base URL instead of the Lightweight Charts CDN base.
s=s.replace('loadDataWithBaseURL("https://unpkg.com/",html,"text/html","UTF-8",null)',
            'loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)')

# Replace candle-pushing guide block: live candles belong to TradingView; app only
# sends optional analysis levels/signal state. No chart data API calls here.
start=s.index('    private fun pushChartCandles(data:List<Candle>){')
end=s.index('\n    private fun updateSnapshot(data:List<Candle>?=null){',start)
new_guides='''    private fun pushChartLevels(data:List<Candle>){
        if(!chartReady)return
        val lv=AnalysisEngine.chartLevels(period,data)
        if(lv==null){chart.evaluateJavascript("clearAnalysisLevels()",null);return}
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)}
        lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }
    private fun showAnalysisGuides(data:List<Candle>){
        pushChartLevels(data);updateSnapshot(data);showSignalCard(SignalStore.loadActive(this,symbol,period))
    }
    private fun showCachedAnalysisGuides(){
        val data=FcsClient.peek(symbol,period,220)
        if(data.isNullOrEmpty()){
            if(chartReady)chart.evaluateJavascript("clearAnalysisLevels()",null)
            updateSnapshot();showSignalCard(SignalStore.loadActive(this,symbol,period));return
        }
        showAnalysisGuides(data)
    }
'''
s=s[:start]+new_guides+s[end:]

# On every completed fresh analysis, retire every prior active signal for this
# symbol before deciding whether this timeframe has a new valid setup.
needle='''    private fun performAnalysis(){
        if(candles.size<60){status.text="NOT ENOUGH MARKET HISTORY FOR RELIABLE ANALYSIS";return}
        val candidate=AnalysisEngine.analyze(symbol,period,candles)'''
replacement='''    private fun performAnalysis(){
        if(candles.size<60){status.text="NOT ENOUGH MARKET HISTORY FOR RELIABLE ANALYSIS";return}
        SignalStore.clearActiveForSymbol(this,symbol)
        val candidate=AnalysisEngine.analyze(symbol,period,candles)'''
if needle not in s: raise SystemExit('v47 performAnalysis anchor not found')
s=s.replace(needle,replacement,1)

# If current analysis produces no setup, explicitly clear chart signal state.
s=s.replace('''            status.text=AnalysisEngine.noSignalReason(symbol,period,candles)
            showSignalCard(SignalStore.loadActive(this,symbol,period))
            return''','''            status.text=AnalysisEngine.noSignalReason(symbol,period,candles)
            showSignalCard(null)
            return''',1)

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: same real TradingView chart, no FCS live socket ownership.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('class OverlayService:Service(),LiveSocketHub.Listener{','class OverlayService:Service(){',1)
s=s.replace('loadDataWithBaseURL("https://unpkg.com/",html,"text/html","UTF-8",null)',
            'loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)')
# Strip LiveSocketHub startup from onCreate while preserving the rest.
s=re.sub(r'override fun onCreate\(\)\{super\.onCreate\(\);FcsClient\.init\(this\);LiveSocketHub\.addListener\(this\);.*?;wm=getSystemService',
         'override fun onCreate(){super.onCreate();FcsClient.init(this);wm=getSystemService',s,count=1)
# Remove live callback and listener cleanup.
s=re.sub(r'''\n    override fun onLiveCandle\(symbol:String,timeframe:String,candle:Candle\)\{.*?\}\n''','\n',s,count=1,flags=re.S)
s=s.replace('LiveSocketHub.removeListener(this);','')

# Replace cached guide helper so it never pushes FCS candles into the visual chart.
if '    private fun showOverlayGuidesFromCache(){' in s:
    start=s.index('    private fun showOverlayGuidesFromCache(){')
    end=s.index('\n    private fun displayed()',start)
    helper='''    private fun showOverlayGuidesFromCache(){
        val data=FcsClient.peek(symbol,period,220)
        if(data.isNullOrEmpty()){chart?.evaluateJavascript("clearAnalysisLevels()",null);return}
        val lv=AnalysisEngine.chartLevels(period,data)?:return
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart?.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }
'''
    s=s[:start]+helper+s[end:]

# Latest analysis owns the one active signal for the symbol in floating mode too.
needle='''            val data=pair.first;if(data.size<60){status?.text="Not enough market history";return@post}
            val candidate=AnalysisEngine.analyze(symbol,period,data)'''
if needle in s:
    s=s.replace(needle,'''            val data=pair.first;if(data.size<60){status?.text="Not enough market history";return@post}
            SignalStore.clearActiveForSymbol(this,symbol)
            val candidate=AnalysisEngine.analyze(symbol,period,data)''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Real TradingView widget HTML. It is live independently of ANALYZE/API calls.
# Analysis levels are attempted only through TradingView's own chart API; there
# is deliberately no fixed HTML overlay that can drift during zoom/pan.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
html=r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
html,body{margin:0;padding:0;width:100%;height:100%;background:#131722;overflow:hidden;font-family:Arial,sans-serif}
#tvroot{position:absolute;inset:0;background:#131722}#widget{position:absolute;inset:0;z-index:1}
#state{position:absolute;left:7px;bottom:6px;z-index:4;color:#7f8999;font-size:7px;background:rgba(19,23,34,.60);padding:2px 4px;border-radius:3px;pointer-events:none}
</style>
</head>
<body>
<div id="tvroot"><div id="widget"></div><div id="state">LIVE TRADINGVIEW</div></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
let tvWidget=null,chartApi=null,currentSymbol='OANDA:XAUUSD',currentInterval='15',token=0;
let signal=null,analysis=null,shapeIds=[];
function mapSymbol(s){s=String(s||'').toUpperCase();return s==='BTCUSDT'?'BINANCE:BTCUSDT':'OANDA:XAUUSD'}
function mapInterval(p){const x=String(p||'15m');const m={'1m':'1','5m':'5','10m':'10','15m':'15','30m':'30','1h':'60','2h':'120','4h':'240','5h':'300','1d':'D','1w':'W','1M':'M'};return m[x]||'15'}
function parse(raw){if(!raw)return null;if(typeof raw==='string'){try{return JSON.parse(raw)}catch(e){return null}}return raw}
function removeShapes(){if(!chartApi){shapeIds=[];return}shapeIds.splice(0).forEach(id=>{try{if(typeof chartApi.removeEntity==='function')chartApi.removeEntity(id);else if(typeof chartApi.removeShape==='function')chartApi.removeShape(id)}catch(e){}})}
function remember(v){if(v&&typeof v.then==='function')v.then(id=>{if(id!=null)shapeIds.push(id)}).catch(()=>{});else if(v!=null)shapeIds.push(v)}
function hline(price,color,label,dashed){if(!chartApi||typeof chartApi.createShape!=='function'||!Number.isFinite(Number(price)))return;try{remember(chartApi.createShape({price:Number(price)},{shape:'horizontal_line',text:label,lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:color,linestyle:dashed?2:0,linewidth:1,showPrice:true,textcolor:color,fontsize:9}}))}catch(e){}}
function redraw(){removeShapes();if(!chartApi)return;if(analysis){hline(analysis.support,'#42a5f5','S',true);hline(analysis.resistance,'#ce93d8','R',true)}if(signal){hline(signal.entry,'#f2c94c','ENTRY',false);hline(signal.sl,'#ff5a67','SL',true);hline(signal.tp1,'#3ddc84','TP1',true);hline(signal.tp2,'#56d7d1','TP2',true)}}
function api(){try{if(tvWidget&&typeof tvWidget.activeChart==='function')return tvWidget.activeChart();if(tvWidget&&typeof tvWidget.chart==='function')return tvWidget.chart()}catch(e){}return null}
function ready(t){if(t!==token)return;chartApi=api();redraw()}
function build(symbol,period,t){if(t!==token)return;if(!window.TradingView||typeof TradingView.widget!=='function'){setTimeout(()=>build(symbol,period,t),400);return}const host=document.getElementById('widget');host.innerHTML='';const id='tv_'+t+'_'+Date.now();const d=document.createElement('div');d.id=id;d.style.width='100%';d.style.height='100%';host.appendChild(d);try{tvWidget=new TradingView.widget({autosize:true,width:'100%',height:'100%',symbol:mapSymbol(symbol),interval:mapInterval(period),timezone:'Asia/Karachi',theme:'dark',style:'1',locale:'en',toolbar_bg:'#131722',enable_publishing:false,hide_top_toolbar:false,hide_side_toolbar:true,allow_symbol_change:false,save_image:false,details:false,hotlist:false,calendar:false,withdateranges:false,container_id:id});if(tvWidget&&typeof tvWidget.onChartReady==='function')tvWidget.onChartReady(()=>ready(t));else setTimeout(()=>ready(t),2200)}catch(e){document.getElementById('state').textContent='TradingView unavailable'}}
function loadTradingView(symbol,period){currentSymbol=mapSymbol(symbol);currentInterval=mapInterval(period);token++;chartApi=null;shapeIds=[];build(symbol,period,token)}
function setAnalysisLevels(raw){analysis=parse(raw);redraw()}function clearAnalysisLevels(){analysis=null;redraw()}
function setSignalCard(raw){signal=parse(raw);redraw()}function clearSignalCard(){signal=null;redraw()}
// Compatibility no-ops: visual candles are owned by TradingView itself.
function setChartData(raw){}function clearChartData(){}function updateLivePrice(price,ts){}
</script>
</body>
</html>'''
p.write_text(html)

# Version
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 47',s);s=re.sub(r'versionName = "[^"]+"','versionName = "47.0"',s);p.write_text(s)
print('v47 live TradingView + one-current-signal patch applied')
