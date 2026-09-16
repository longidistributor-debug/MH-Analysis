from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Remove the duplicate lifecycle pair introduced by v45; keep only the live callback
# and onDestroy cleanup. The existing v34/v35 lifecycle methods are augmented below.
old='''    override fun onResume(){
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
new='''    override fun onDestroy(){LiveSocketHub.removeListener(this);super.onDestroy()}
    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(symbol!=this.symbol||timeframe!="1m"||!chartReady)return
        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t
        runOnUiThread{chart.evaluateJavascript("updateLivePrice(${candle.c},$ts)",null)}
    }

'''
if old not in s: raise SystemExit('v45 duplicate lifecycle block not found')
s=s.replace(old,new,1)

old_resume='''    override fun onResume(){super.onResume();showExisting();startMonitorIfNeeded();lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);lifecycleUiHandler.post(lifecycleUiRefresh)}'''
new_resume='''    override fun onResume(){
        super.onResume();showExisting();startMonitorIfNeeded();lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);lifecycleUiHandler.post(lifecycleUiRefresh)
        LiveSocketHub.addListener(this)
        val liveKey=prefs.getString("socket_api_key","")?.trim().orEmpty().ifBlank{savedHistoryKey()}
        if(liveKey.isNotBlank())LiveSocketHub.start(this,liveKey)
        if(chartReady)showCachedAnalysisGuides()
    }'''
if old_resume not in s: raise SystemExit('v45 existing onResume anchor not found')
s=s.replace(old_resume,new_resume,1)

old_pause='''    override fun onPause(){lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);super.onPause()}'''
new_pause='''    override fun onPause(){LiveSocketHub.removeListener(this);lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);super.onPause()}'''
if old_pause not in s: raise SystemExit('v45 existing onPause anchor not found')
s=s.replace(old_pause,new_pause,1)

p.write_text(s)
print('v45 lifecycle listener conflict fixed')
