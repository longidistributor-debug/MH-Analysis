from pathlib import Path
import re

# v47: keep exactly one manual signal globally and make the controlled chart
# continue updating after ANALYZE. Primary visual updates use FCS websocket data;
# when the socket is silent while the Activity is visible, a rate-limited REST
# selected-timeframe refresh keeps the chart from freezing.

# -----------------------------------------------------------------------------
# SignalStore: accepting a fresh signal removes every older active manual signal.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()
old='''        val active=ActiveSignal(candidate,state="PENDING")
        saveActive(c,active)
'''
new='''        // The product now has exactly one current manual signal at a time.
        // A newly accepted setup replaces active signals from every other
        // timeframe/pair, so an older 30m signal cannot remain after a new 15m one.
        val edit=prefs(c).edit()
        prefs(c).all.keys.filter{it.startsWith("active_")}.forEach{edit.remove(it)}
        edit.apply()
        val active=ActiveSignal(candidate,state="PENDING")
        saveActive(c,active)
'''
if old not in s: raise SystemExit('v47 SignalStore accept anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Main Activity live chart watchdog.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Insert chart-live state once.
anchor='''    override fun onResume(){'''
if 'private val chartLiveHandler=Handler(Looper.getMainLooper())' not in s:
    live_state='''    private val chartLiveHandler=Handler(Looper.getMainLooper())
    @Volatile private var lastChartLiveTickAt=0L
    @Volatile private var chartRefreshBusy=false
    private val chartLiveRefresh=object:Runnable{
        override fun run(){
            if(!chartReady){chartLiveHandler.postDelayed(this,5000L);return}
            val now=System.currentTimeMillis()
            // If websocket price/candle updates are fresh, do not spend REST credits.
            if(now-lastChartLiveTickAt>14_000L&&!chartRefreshBusy){
                val key=savedHistoryKey();val reqSymbol=symbol;val reqPeriod=period
                if(key.isNotBlank()){
                    chartRefreshBusy=true
                    thread{
                        runCatching{FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)}
                            .onSuccess{pair->runOnUiThread{
                                chartRefreshBusy=false
                                if(reqSymbol==symbol&&reqPeriod==period&&chartReady){
                                    val(out,credits)=pair
                                    if(credits>0){addUsage(credits);if(::calls.isInitialized)calls.text="Analysis calls: ${usage()}/500"}
                                    pushChartCandles(out);pushChartLevels(out);updateSnapshot(out)
                                    lastChartLiveTickAt=System.currentTimeMillis()
                                }
                            }}
                            .onFailure{runOnUiThread{chartRefreshBusy=false}}
                    }
                }
            }
            chartLiveHandler.postDelayed(this,28_000L)
        }
    }

'''
    if anchor not in s: raise SystemExit('v47 onResume anchor not found')
    s=s.replace(anchor,live_state+anchor,1)

# Balanced function replacement helper.
def replace_fun(src,name,replacement):
    needle=f'    override fun {name}(){{'
    start=src.find(needle)
    if start<0: raise SystemExit(f'v47 {name} function not found')
    brace=src.find('{',start);depth=0;end=None;in_string=False;escape=False
    for i in range(brace,len(src)):
        ch=src[i]
        if in_string:
            if escape: escape=False
            elif ch=='\\': escape=True
            elif ch=='"': in_string=False
            continue
        if ch=='"': in_string=True;continue
        if ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0: end=i+1;break
    if end is None: raise SystemExit(f'v47 could not parse {name}')
    return src[:start]+replacement+src[end:]

new_resume='''    override fun onResume(){
        super.onResume()
        showExisting()
        lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh)
        lifecycleUiHandler.post(lifecycleUiRefresh)
        LiveSocketHub.addListener(this)
        val liveKey=prefs.getString("socket_api_key","")?.trim().orEmpty().ifBlank{savedHistoryKey()}
        if(liveKey.isNotBlank())LiveSocketHub.start(this,liveKey)
        if(chartReady)showCachedAnalysisGuides()
        chartLiveHandler.removeCallbacks(chartLiveRefresh)
        chartLiveHandler.postDelayed(chartLiveRefresh,28_000L)
    }'''
new_pause='''    override fun onPause(){
        chartLiveHandler.removeCallbacks(chartLiveRefresh)
        chartRefreshBusy=false
        LiveSocketHub.removeListener(this)
        lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh)
        super.onPause()
    }'''
new_destroy='''    override fun onDestroy(){
        chartLiveHandler.removeCallbacks(chartLiveRefresh)
        LiveSocketHub.removeListener(this)
        super.onDestroy()
    }'''
s=replace_fun(s,'onResume',new_resume)
s=replace_fun(s,'onPause',new_pause)
s=replace_fun(s,'onDestroy',new_destroy)

old_live='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(symbol!=this.symbol||timeframe!="1m"||!chartReady)return
        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t
        runOnUiThread{chart.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}
    }'''
new_live='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(symbol!=this.symbol||!chartReady)return
        // Native selected-timeframe feed is preferred. 1m is also accepted as a
        // universal fallback and is bucketed by the JS chart into the selected TF.
        if(timeframe!=period&&timeframe!="1m")return
        lastChartLiveTickAt=System.currentTimeMillis()
        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t
        runOnUiThread{chart.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}
    }'''
if old_live not in s: raise SystemExit('v47 MainActivity live callback anchor not found')
s=s.replace(old_live,new_live,1)

# Reset the watchdog clock when switching market/timeframe so a silent feed is
# recovered quickly, but do not immediately spend a REST request.
s=s.replace('''        pairLabel.text="$symbol • $period"
        if(chartReady){''','''        pairLabel.text="$symbol • $period"
        lastChartLiveTickAt=System.currentTimeMillis()
        if(chartReady){''',1)

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating chart: accept selected timeframe socket updates too (no REST polling).
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
old='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){if(symbol!=this.symbol||timeframe!="1m")return;val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t;Handler(Looper.getMainLooper()).post{chart?.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}}'''
new='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){if(symbol!=this.symbol||(timeframe!=period&&timeframe!="1m"))return;val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t;Handler(Looper.getMainLooper()).post{chart?.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}}'''
if old in s:s=s.replace(old,new,1)
p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 47',s);s=re.sub(r'versionName = "[^"]+"','versionName = "47.0"',s);p.write_text(s)
print('v47 single-current-signal + live chart watchdog applied')
