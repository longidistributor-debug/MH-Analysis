from pathlib import Path
import re

# v64 FINAL requested architecture:
# - TradingView widget is visual live market view only.
# - No FCS/WebSocket chart connection and no WebSocket key UI.
# - XAUUSD analysis uses FCS REST/cache only.
# - Manual ANALYZE force-refreshes the selected timeframe and REPLACES its cache.
# - Never create a new signal from an old cache when a fresh manual fetch fails.
# - S/R rule: support = immediately previous CLOSED candle low;
#   resistance = highest high in the selected timeframe's recent CLOSED history.
# - BTC remains removed.

# -----------------------------------------------------------------------------
# TradingView asset: pure visual chart. App analysis values are intentionally not
# drawn into the public widget because its candles are a separate visual feed.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
p.write_text(r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>html,body{margin:0;padding:0;width:100%;height:100%;background:#131722;overflow:hidden;font-family:Arial,sans-serif}#widget{position:absolute;inset:0;background:#131722}#tag{position:absolute;left:7px;bottom:6px;z-index:4;color:#7f8999;font-size:7px;background:rgba(19,23,34,.60);padding:2px 4px;border-radius:3px;pointer-events:none}</style></head>
<body><div id="widget"></div><div id="tag">LIVE MARKET VIEW</div><script src="https://s3.tradingview.com/tv.js"></script><script>
let token=0,tvWidget=null;
function mapInterval(p){const x=String(p||'15m');const m={'1m':'1','5m':'5','10m':'10','15m':'15','30m':'30','1h':'60','2h':'120','4h':'240','5h':'300','1d':'D','1D':'D','1w':'W','1W':'W','1M':'M'};return m[x]||'15'}
function build(period,t){if(t!==token)return;if(!window.TradingView||typeof TradingView.widget!=='function'){setTimeout(()=>build(period,t),350);return}const host=document.getElementById('widget');host.innerHTML='';const id='tv_'+t+'_'+Date.now();const d=document.createElement('div');d.id=id;d.style.width='100%';d.style.height='100%';host.appendChild(d);try{tvWidget=new TradingView.widget({autosize:true,width:'100%',height:'100%',symbol:'FX:XAUUSD',interval:mapInterval(period),timezone:'Asia/Karachi',theme:'dark',style:'1',locale:'en',toolbar_bg:'#131722',enable_publishing:false,hide_top_toolbar:false,hide_side_toolbar:true,allow_symbol_change:false,save_image:false,details:false,hotlist:false,calendar:false,withdateranges:false,container_id:id})}catch(e){document.getElementById('tag').textContent='LIVE MARKET VIEW'}}
function loadTradingView(_symbol,period){token++;build(period,token)}
function switchTimeframe(period){loadTradingView('XAUUSD',period)}
// Compatibility hooks. TradingView is visual-only; FCS analysis stays outside it.
function setAnalysisLevels(_raw){}function clearAnalysisLevels(){}function setSignalCard(_raw){}function clearSignalCard(){}
function setHistoricalCandles(_tf,_candles){}function setChartData(_raw){}function clearChartData(){}function updateLivePrice(_p,_t){}
function configureFcsChart(_a,_s,tf){switchTimeframe(tf)}function setFcsApiKey(_k){}function setLiveKeyRequired(){}function setNativeConnectionState(_s){}function onNativeCandle(_tf,_c){}
</script></body></html>''')

# -----------------------------------------------------------------------------
# MainActivity: restore TradingView WebView and remove WebSocket-key card.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# v63 inline FCS chart loader -> TradingView visual-only widget.
old='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");run{
                val index=this@MainActivityV29.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@MainActivityV29.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@MainActivityV29.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@MainActivityV29.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index.replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>").replace("<script src=\\\"fcs-client-lib.js\\\"></script>","").replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
new='''run{
                val html=this@MainActivityV29.assets.open("tradingview_live.html").bufferedReader().use{it.readText()}
                loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)
            }'''
if old in s:s=s.replace(old,new,1)
else:
    # Fallback for any generated formatting variation.
    s=re.sub(r'settings\.allowFileAccess=true;settings\.allowContentAccess=true;addJavascriptInterface\(FcsChartBridge\(this@MainActivityV29\),"AndroidFcs"\);run\{.*?loadDataWithBaseURL\("https://fcsapi\.com/",html,"text/html","UTF-8",null\)\s*\}',new,s,count=1,flags=re.S)

# Remove the dedicated live/WebSocket key UI card. Analysis key card stays intact.
s=re.sub(r'\n\s*val socketCard=card\(\);socketStatus=.*?root\.addView\(socketCard,LinearLayout\.LayoutParams\(-1,-2\)\.apply\{topMargin=dp\(8\)\}\)\n','\n',s,count=1,flags=re.S)

# Final chart sync: TradingView only changes visual timeframe. Cached FCS values
# stay in the app snapshot/status and are not injected into the public widget.
if '    private fun syncFcsChart(){' in s:
    st=s.index('    private fun syncFcsChart(){');en=s.index('\n    private fun ',st+10)
    s=s[:st]+'''    private fun syncFcsChart(){
        if(!chartReady)return
        symbol="XAUUSD"
        chart.evaluateJavascript("window.loadTradingView&&window.loadTradingView('XAUUSD',${JSONObject.quote(period)})",null)
        val data=FcsClient.peek("XAUUSD",period,300)
        if(!data.isNullOrEmpty())updateSnapshot(data) else updateSnapshot()
    }
'''+s[en:]

# Never fall back to an old cache after a failed MANUAL fresh fetch. That was the
# source of old/wrong signals after network/API problems.
old_fallback='''            }catch(e:Exception){runOnUiThread{
                busy=false
                val live=FcsClient.peek("XAUUSD",reqPeriod,300).orEmpty()
                if(reqSymbol==symbol&&reqPeriod==period&&live.size>=60){
                    candles=live
                    status.text="ANALYZING LIVE $reqPeriod STRUCTURE…"
                    performAnalysis()
                }else{
                    status.text="LIVE DATA SYNCING • TRY ANALYZE AGAIN"
                }
            }}'''
new_fallback='''            }catch(e:Exception){runOnUiThread{
                busy=false
                status.text="FRESH MARKET DATA UNAVAILABLE • NO SIGNAL CREATED • TRY AGAIN"
            }}'''
if old_fallback in s:s=s.replace(old_fallback,new_fallback,1)

# One-time cleanup: remove stale active Gold setup created before the clean REST-cache build.
anchor='        setContentView(buildUi())\n'
if 'v64_rest_cache_migrated' not in s and anchor in s:
    s=s.replace(anchor,anchor+'''        if(!prefs.getBoolean("v64_rest_cache_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD")
            prefs.edit().putBoolean("v64_rest_cache_migrated",true).apply()
        }
''',1)

s=s.replace('FCS XAUUSD LIVE','TRADINGVIEW LIVE').replace('XAUUSD LIVE','TRADINGVIEW LIVE')
p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: TradingView visual only; no socket key / no FCS live chart.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
old='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");run{
                val index=this@OverlayService.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@OverlayService.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@OverlayService.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@OverlayService.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index.replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>").replace("<script src=\\\"fcs-client-lib.js\\\"></script>","").replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
new='''run{
                val html=this@OverlayService.assets.open("tradingview_live.html").bufferedReader().use{it.readText()}
                loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)
            }'''
if old in s:s=s.replace(old,new,1)
else:s=re.sub(r'settings\.allowFileAccess=true;settings\.allowContentAccess=true;addJavascriptInterface\(FcsChartBridge\(this@OverlayService\),"AndroidFcs"\);run\{.*?loadDataWithBaseURL\("https://fcsapi\.com/",html,"text/html","UTF-8",null\)\s*\}',new,s,count=1,flags=re.S)

if '    private fun loadChart(){' in s:
    st=s.index('    private fun loadChart(){');en=s.index('\n    private fun ',st+10)
    s=s[:st]+'''    private fun loadChart(){
        val w=chart?:return
        w.evaluateJavascript("window.loadTradingView&&window.loadTradingView('XAUUSD',${JSONObject.quote(period)})",null)
        overlay(SignalStore.displayState(this,"XAUUSD",period))
    }
'''+s[en:]
s=s.replace('FCS XAUUSD LIVE','TRADINGVIEW LIVE').replace('XAUUSD LIVE','TRADINGVIEW LIVE')
p.write_text(s)

# -----------------------------------------------------------------------------
# Alarm/background: no custom WebSocket ownership. REST lifecycle remains.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
if '    private fun startLiveSocket(){' in s:
    st=s.index('    private fun startLiveSocket(){');en=s.index('\n    private fun ',st+10)
    s=s[:st]+'    private fun startLiveSocket(){}\n'+s[en:]
s=re.sub(r'LiveSocketHub\.start\([^\n]+\)','',s)
p.write_text(s)

# -----------------------------------------------------------------------------
# FcsClient: fresh, provider-specific REST cache. Manual force refresh replaces
# selected-timeframe history; no old-cache fallback is allowed on force.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
for old_ns in ['mh_candle_cache_v61_exact_fx','mh_candle_cache_v57_fx','mh_candle_cache_v55_oanda_exchange','mh_candle_cache_v53_oanda','mh_candle_cache_v22']:
    s=s.replace(old_ns,'mh_candle_cache_v64_rest_fx_clean')

start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())throw IllegalStateException("ANALYSIS ACCESS KEY REQUIRED")
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        if(sym!="XAUUSD")throw IllegalStateException("Only XAUUSD is supported")
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        if(current.size>=100&&!force)return current.takeLast(300) to 0
        if(!canRequestNow()){
            if(!force&&current.size>=60)return current.takeLast(300) to 0
            throw IllegalStateException("FRESH MARKET DATA TEMPORARILY BUSY")
        }
        val out=try{fetchMarket(sym,cleanKey,tf,360)}catch(e:Exception){noteRequest();throw e}
        noteRequest()
        val fresh=out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
        if(fresh.size<60)throw IllegalStateException("FRESH $tf HISTORY INCOMPLETE")
        val step=when(tf){
            "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;"1h"->3600L;
            "2h"->7200L;"4h"->14400L;"5h"->18000L;"1d"->86400L;"1w"->604800L;else->900L
        }
        val now=System.currentTimeMillis()/1000L
        val newest=normalizeTs(fresh.last().t)
        // A history set more than two selected-timeframe bars behind is stale.
        if(now-newest>step*2L+180L)throw IllegalStateException("FRESH $tf HISTORY IS STALE")
        // Critical: REPLACE old timeframe cache. Never append old provider/history rows.
        putCache(sym,tf,fresh,true)
        return fresh.takeLast(300) to out.second
    }'''
s=s[:start]+new_seed+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# AnalysisEngine: deterministic selected-timeframe S/R from CLOSED FCS candles.
# Running candle is excluded only when its timestamp belongs to the active bucket.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
start=s.index('    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{')
end=s.index('\n\n    fun chartLevels',start)
new_levels='''    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{
        if(c.size<3)return null
        val tf=tfMinutes(timeframe).coerceAtLeast(1)
        val step=tf*60L
        val sorted=c.sortedBy{it.t}
        val now=System.currentTimeMillis()/1000L
        val last=sorted.last()
        val lastTs=if(last.t>9_999_999_999L)last.t/1000L else last.t
        // Exclude last row only when it is actually the currently-running candle.
        val closed=if(lastTs>0L && now<lastTs+step)sorted.dropLast(1) else sorted
        if(closed.size<2)return null
        val previousClosed=closed.last()
        val support=previousClosed.l
        // Same number of bars on every selected timeframe -> timeframe-specific resistance.
        val resistance=closed.takeLast(120).maxOf{it.h}
        if(!support.isFinite()||!resistance.isFinite())return null
        return support to resistance
    }'''
s=s[:start]+new_levels+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 64',g);g=re.sub(r'versionName = "[^"]+"','versionName = "64.0"',g);p.write_text(g)
print('v64 TradingView visual + clean FCS REST cache analysis applied')
