from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Remove the duplicate lifecycle pair introduced by v45; keep its onDestroy and
# live-candle callback. Earlier patches already create the Activity lifecycle
# methods, but their exact one-line body can vary between generated versions.
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

# Replace an existing Kotlin function by finding its balanced braces. This avoids
# depending on whichever exact body v34/v35/v39 produced earlier in the patch stack.
def replace_fun(src,name,replacement):
    needle=f'    override fun {name}(){{'
    start=src.find(needle)
    if start<0: raise SystemExit(f'v45 existing {name} function not found')
    brace=src.find('{',start)
    depth=0
    end=None
    in_string=False
    escape=False
    for i in range(brace,len(src)):
        ch=src[i]
        if in_string:
            if escape: escape=False
            elif ch=='\\': escape=True
            elif ch=='"': in_string=False
            continue
        if ch=='"':
            in_string=True;continue
        if ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:
                end=i+1;break
    if end is None: raise SystemExit(f'v45 could not find end of {name}')
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
    }'''
new_pause='''    override fun onPause(){
        LiveSocketHub.removeListener(this)
        lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh)
        super.onPause()
    }'''

s=replace_fun(s,'onResume',new_resume)
s=replace_fun(s,'onPause',new_pause)

# Sanity-check that only one lifecycle method remains after generation.
if s.count('override fun onResume()')!=1: raise SystemExit('v45 onResume duplicate remains')
if s.count('override fun onPause()')!=1: raise SystemExit('v45 onPause duplicate remains')

p.write_text(s)
print('v45 lifecycle listener conflict fixed robustly')
