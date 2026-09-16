from pathlib import Path
import re

# v45: replace the public TradingView widget with TradingView Lightweight Charts.
# The analysis engine remains unchanged. App-calculated S/R, OB and signal levels
# are real price-scale objects, so they move with zoom/pan instead of floating over
# the WebView. Historical candles come from the selected-timeframe FCS data.

# -----------------------------------------------------------------------------
# MainActivity: push exact selected-timeframe candles + levels to the chart.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

if 'import org.json.JSONArray' not in s:
    s=s.replace('import org.json.JSONObject\n','import org.json.JSONObject\nimport org.json.JSONArray\n',1)

s=s.replace('class MainActivityV29:Activity(){','class MainActivityV29:Activity(),LiveSocketHub.Listener{',1)

# Restore cached chart payload on timeframe/pair switch while retaining v44 snapshot.
s=re.sub(
    r'    private fun switchVisibleChart\(\)\{[^\n]*\}',
    '''    private fun switchVisibleChart(){
        pairLabel.text="$symbol • $period"
        if(chartReady){
            chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null)
            showCachedAnalysisGuides()
        }
        showExisting();updateSnapshot()
    }''',s,count=1
)

# v44 made showSignalCard snapshot-only. Re-enable signal price objects on the controlled chart.
start=s.index('    private fun showSignalCard(a:ActiveSignal?){')
end=s.index('\n    private fun showAnalysisGuides(data:List<Candle>){',start)
new_signal='''    private fun showSignalCard(a:ActiveSignal?){
        updateSnapshot()
        if(!chartReady)return
        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}
        val x=a.signal
        val j=JSONObject().put("direction",x.direction).put("state",a.state).put("entry",x.entry).put("sl",x.sl).put("tp1",x.tp1).put("tp2",x.tp2).put("score",x.score)
        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }
'''
s=s[:start]+new_signal+s[end:]

# Replace v44 snapshot-only guide helpers with real candle + price-line payloads.
start=s.index('    private fun showAnalysisGuides(data:List<Candle>){')
end=s.index('\n    private fun updateSnapshot(data:List<Candle>?=null){',start)
new_guides='''    private fun pushChartCandles(data:List<Candle>){
        if(!chartReady)return
        val arr=JSONArray()
        data.takeLast(220).forEach{c->
            val ts=if(c.t>10_000_000_000L)c.t/1000L else c.t
            arr.put(JSONObject().put("time",ts).put("open",c.o).put("high",c.h).put("low",c.l).put("close",c.c).put("volume",c.v))
        }
        chart.evaluateJavascript("setChartData(${JSONObject.quote(arr.toString())})",null)
    }

    private fun pushChartLevels(data:List<Candle>){
        if(!chartReady)return
        val lv=AnalysisEngine.chartLevels(period,data)
        if(lv==null){chart.evaluateJavascript("clearAnalysisLevels()",null);return}
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)}
        lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }

    private fun showAnalysisGuides(data:List<Candle>){
        pushChartCandles(data);pushChartLevels(data);updateSnapshot(data);showSignalCard(SignalStore.loadActive(this,symbol,period))
    }
    private fun showCachedAnalysisGuides(){
        val data=FcsClient.peek(symbol,period,220)
        if(data.isNullOrEmpty()){
            if(chartReady){chart.evaluateJavascript("clearChartData()",null);chart.evaluateJavascript("clearAnalysisLevels()",null)}
            updateSnapshot();showSignalCard(SignalStore.loadActive(this,symbol,period));return
        }
        showAnalysisGuides(data)
    }
'''
s=s[:start]+new_guides+s[end:]

# Start the already-present FCS live stream only for live visual candle updates.
# It is not used for alarms/trade records. A failed socket leaves the historical
# analysis chart intact.
anchor='''    private fun savedHistoryKey()=prefs.getString("api_key","")?.trim().orEmpty()'''
if 'override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle)' not in s:
    live='''    override fun onResume(){
        super.onResume();LiveSocketHub.addListener(this)
        val liveKey=prefs.getString("socket_api_key","")?.trim().orEmpty().ifBlank{savedHistoryKey()}
        if(liveKey.isNotBlank())LiveSocketHub.start(this,liveKey)
        if(chartReady)showCachedAnalysisGuides()
    }
    override fun onPause(){LiveSocketHub.removeListener(this);super.onPause()}
    override fun onDestroy(){LiveSocketHub.removeListener(this);super.onDestroy()}
    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(symbol!=this.symbol||timeframe!="1m"||!chartReady)return
        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t
        runOnUiThread{chart.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}
    }

'''
    if anchor not in s: raise SystemExit('v45 live listener anchor not found')
    s=s.replace(anchor,live+anchor,1)

# Lightweight Charts CDN is the WebView base instead of the old widget host.
s=s.replace('loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)',
            'loadDataWithBaseURL("https://unpkg.com/",html,"text/html","UTF-8",null)')
p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: same controlled chart and chart-level payloads.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
if 'import org.json.JSONArray' not in s:
    s=s.replace('import org.json.JSONObject\n','import org.json.JSONObject\nimport org.json.JSONArray\n',1)
s=s.replace('class OverlayService:Service(){','class OverlayService:Service(),LiveSocketHub.Listener{',1)
s=s.replace('loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)',
            'loadDataWithBaseURL("https://unpkg.com/",html,"text/html","UTF-8",null)')

# onCreate: listen for live visual price updates only.
s=s.replace('override fun onCreate(){super.onCreate();FcsClient.init(this);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}',
'''override fun onCreate(){super.onCreate();FcsClient.init(this);LiveSocketHub.addListener(this);val liveKey=prefs.getString("socket_api_key","")?.trim().orEmpty().ifBlank{prefs.getString("api_key","")?.trim().orEmpty()};if(liveKey.isNotBlank())LiveSocketHub.start(this,liveKey);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}''',1)

# Replace guide helper with candle + price levels.
if '    private fun showOverlayGuidesFromCache(){' in s:
    start=s.index('    private fun showOverlayGuidesFromCache(){')
    end=s.index('\n    private fun displayed()',start)
    helper='''    private fun showOverlayGuidesFromCache(){
        val data=FcsClient.peek(symbol,period,220)
        if(data.isNullOrEmpty()){chart?.evaluateJavascript("clearChartData()",null);chart?.evaluateJavascript("clearAnalysisLevels()",null);return}
        val arr=JSONArray();data.takeLast(220).forEach{c->val ts=if(c.t>10_000_000_000L)c.t/1000L else c.t;arr.put(JSONObject().put("time",ts).put("open",c.o).put("high",c.h).put("low",c.l).put("close",c.c).put("volume",c.v))}
        chart?.evaluateJavascript("setChartData(${JSONObject.quote(arr.toString())})",null)
        val lv=AnalysisEngine.chartLevels(period,data)?:return
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart?.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }
'''
    s=s[:start]+helper+s[end:]
else:
    raise SystemExit('v45 overlay guide helper not found')

# Live visual update in floating chart.
old_destroy='''    override fun onDestroy(){hidePanel();if(::bubble.isInitialized)runCatching{wm.removeView(bubble)};super.onDestroy()}'''
new_destroy='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){if(symbol!=this.symbol||timeframe!="1m")return;val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t;Handler(Looper.getMainLooper()).post{chart?.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}}
    override fun onDestroy(){LiveSocketHub.removeListener(this);hidePanel();if(::bubble.isInitialized)runCatching{wm.removeView(bubble)};super.onDestroy()}'''
if old_destroy in s:s=s.replace(old_destroy,new_destroy,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Controlled TradingView Lightweight Charts HTML.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
html=r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#131722;font-family:Arial,sans-serif}
#root{position:absolute;inset:0;background:#131722}
#chart{position:absolute;inset:0}
#head{position:absolute;left:10px;top:8px;z-index:5;background:rgba(19,23,34,.82);border:1px solid rgba(255,255,255,.10);border-radius:7px;padding:5px 8px;color:#fff;font-size:10px;font-weight:700;pointer-events:none}
#head small{display:block;color:#9aa4b2;font-size:8px;font-weight:500;margin-top:2px}
#empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:4;color:#8b93a1;font-size:11px;pointer-events:none;text-align:center;padding:24px}
#credit{position:absolute;left:9px;bottom:6px;z-index:5;color:#6e7686;font-size:7px;pointer-events:none}
</style>
</head>
<body>
<div id="root">
  <div id="chart"></div>
  <div id="head">XAUUSD • 15m<small>Selected-timeframe analysis chart</small></div>
  <div id="empty">Press ANALYZE to load the selected-timeframe candles.</div>
  <div id="credit">TradingView Lightweight Charts</div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
<script>
let chart=null,candles=null,volume=null,currentSymbol='XAUUSD',currentPeriod='15m',data=[],analysis=null,signal=null,lines=[];
const C={bg:'#131722',text:'#c7ccd6',grid:'rgba(197,203,211,.10)',up:'#26a69a',down:'#ef5350',support:'#42a5f5',res:'#ce93d8',bull:'#26a69a',bear:'#ef5350',entry:'#f2c94c',sl:'#ff5a67',tp1:'#3ddc84',tp2:'#56d7d1'};
function init(){
 if(!window.LightweightCharts){document.getElementById('empty').textContent='Chart library unavailable. Check internet connection.';return}
 const host=document.getElementById('chart');
 chart=LightweightCharts.createChart(host,{width:host.clientWidth,height:host.clientHeight,layout:{background:{type:'solid',color:C.bg},textColor:C.text},grid:{vertLines:{color:C.grid},horzLines:{color:C.grid}},rightPriceScale:{borderColor:'#2b313d',scaleMargins:{top:.08,bottom:.23}},timeScale:{borderColor:'#2b313d',timeVisible:true,secondsVisible:false,rightOffset:6,barSpacing:9,minBarSpacing:3},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
 candles=chart.addCandlestickSeries({upColor:C.up,downColor:C.down,borderUpColor:C.up,borderDownColor:C.down,wickUpColor:C.up,wickDownColor:C.down,priceLineVisible:true,lastValueVisible:true});
 volume=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'',lastValueVisible:false,priceLineVisible:false});
 volume.priceScale().applyOptions({scaleMargins:{top:.78,bottom:0}});
 new ResizeObserver(()=>chart.applyOptions({width:host.clientWidth,height:host.clientHeight})).observe(host);
}
function psec(p){const x=String(p||'15m');if(x==='1M')return 2592000;const m={'1m':60,'5m':300,'10m':600,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,'5h':18000,'1d':86400,'1w':604800};return m[x]||900}
function bucket(ts){const n=Math.floor(Number(ts)||Date.now()/1000),s=psec(currentPeriod);return Math.floor(n/s)*s}
function fmt(v){const n=Number(v);return Number.isFinite(n)?(Math.abs(n)>=100?n.toFixed(2):n.toFixed(5)):'-'}
function setHead(){document.getElementById('head').innerHTML=currentSymbol+' • '+currentPeriod+'<small>Selected-timeframe analysis chart</small>'}
function loadTradingView(symbol,period){currentSymbol=String(symbol||'XAUUSD').toUpperCase();currentPeriod=String(period||'15m');setHead();clearChartData();analysis=null;signal=null;redrawLevels()}
function parse(raw){if(!raw)return null;if(typeof raw==='string'){try{return JSON.parse(raw)}catch(e){return null}}return raw}
function setChartData(raw){
 const x=parse(raw);if(!Array.isArray(x)||!candles)return;
 const map=new Map();x.forEach(d=>{const t=Math.floor(Number(d.time));if(Number.isFinite(t))map.set(t,{time:t,open:Number(d.open),high:Number(d.high),low:Number(d.low),close:Number(d.close),volume:Number(d.volume)||0})});
 data=[...map.values()].sort((a,b)=>a.time-b.time);if(!data.length)return clearChartData();
 candles.setData(data.map(d=>({time:d.time,open:d.open,high:d.high,low:d.low,close:d.close})));
 volume.setData(data.map(d=>({time:d.time,value:d.volume,color:d.close>=d.open?'rgba(38,166,154,.45)':'rgba(239,83,80,.45)'})));
 document.getElementById('empty').style.display='none';chart.timeScale().fitContent();redrawLevels();
}
function clearChartData(){data=[];if(candles)candles.setData([]);if(volume)volume.setData([]);document.getElementById('empty').style.display='flex';clearPriceLines()}
function updateLivePrice(price,ts){
 const p=Number(price);if(!Number.isFinite(p)||!candles||!data.length)return;const t=bucket(ts);let d=data[data.length-1];
 if(d.time===t){d={...d,high:Math.max(d.high,p),low:Math.min(d.low,p),close:p};data[data.length-1]=d}else if(t>d.time){d={time:t,open:d.close,high:Math.max(d.close,p),low:Math.min(d.close,p),close:p,volume:0};data.push(d)}else return;
 candles.update({time:d.time,open:d.open,high:d.high,low:d.low,close:d.close});volume.update({time:d.time,value:d.volume||0,color:d.close>=d.open?'rgba(38,166,154,.45)':'rgba(239,83,80,.45)'});
}
function clearPriceLines(){if(!candles)return;lines.forEach(l=>{try{candles.removePriceLine(l)}catch(e){}});lines=[]}
function line(price,color,title,width=1,style=2){const p=Number(price);if(!candles||!Number.isFinite(p))return;try{lines.push(candles.createPriceLine({price:p,color:color,lineWidth:width,lineStyle:style,axisLabelVisible:true,title:title}))}catch(e){}}
function redrawLevels(){
 clearPriceLines();if(!candles||!data.length)return;
 if(analysis){line(analysis.support,C.support,'SUPPORT',2,LightweightCharts.LineStyle.Dashed);line(analysis.resistance,C.res,'RESISTANCE',2,LightweightCharts.LineStyle.Dashed);
   if(Number.isFinite(Number(analysis.bullObLow)))line(analysis.bullObLow,C.bull,'BULL OB LOW',1,LightweightCharts.LineStyle.Dotted);
   if(Number.isFinite(Number(analysis.bullObHigh)))line(analysis.bullObHigh,C.bull,'BULL OB HIGH',1,LightweightCharts.LineStyle.Dotted);
   if(Number.isFinite(Number(analysis.bearObLow)))line(analysis.bearObLow,C.bear,'BEAR OB LOW',1,LightweightCharts.LineStyle.Dotted);
   if(Number.isFinite(Number(analysis.bearObHigh)))line(analysis.bearObHigh,C.bear,'BEAR OB HIGH',1,LightweightCharts.LineStyle.Dotted);
 }
 if(signal){line(signal.entry,C.entry,'ENTRY '+String(signal.direction||''),2,LightweightCharts.LineStyle.Solid);line(signal.sl,C.sl,'SL',2,LightweightCharts.LineStyle.Dashed);line(signal.tp1,C.tp1,'TP1',2,LightweightCharts.LineStyle.Dashed);line(signal.tp2,C.tp2,'TP2',2,LightweightCharts.LineStyle.Dashed)}
}
function setAnalysisLevels(raw){analysis=parse(raw);redrawLevels()}
function clearAnalysisLevels(){analysis=null;redrawLevels()}
function setSignalCard(raw){signal=parse(raw);redrawLevels()}
function clearSignalCard(){signal=null;redrawLevels()}
init();setHead();
</script>
</body>
</html>'''
p.write_text(html)

# Version metadata.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 45',s);s=re.sub(r'versionName = "[^"]+"','versionName = "45.0"',s);p.write_text(s)
print('v45 Lightweight Charts + zoom-synced S/R/OB/signal levels applied')
