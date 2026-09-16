from pathlib import Path
import re

# v58: integrate the uploaded FCS XAUUSD live-chart module into the existing chart section.
# - Remove TradingView from the final APK.
# - Hard-lock the app to XAUUSD and remove BTCUSDT UI/data paths.
# - Load bundled assets/fcs_chart/index.html in the existing WebViews.
# - Reuse the user's saved FCS analysis key; no key is embedded in the APK.
# - Feed the exact same live WebSocket candles back into FcsClient through FcsChartBridge.
# - Preserve analysis, S/R, OB, signal, alarm, records and floating functions.
# - Existing chart analysis hooks setAnalysisLevels/setSignalCard continue to work on the FCS canvas.

# -----------------------------------------------------------------------------
# MainActivityV29
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
if 'import org.json.JSONArray' not in s:
    s=s.replace('import org.json.JSONObject\n','import org.json.JSONObject\nimport org.json.JSONArray\n',1)

# Gold only; do not restore an old BTC preference.
s=re.sub(r'symbol=prefs\.getString\("symbol","XAUUSD"\)\?:"XAUUSD"',
         'symbol="XAUUSD";prefs.edit().putString("symbol","XAUUSD").apply()',s,count=1)
# Remove any BTC button/line left in the market selector.
s='\n'.join(line for line in s.splitlines() if 'BTCUSDT' not in line)+'\n'

# Replace the TradingView WebView payload with the uploaded FCS chart asset + narrow bridge.
s=re.sub(
    r'val html=assets\.open\("tradingview_live\.html"\).*?loadDataWithBaseURL\([^\n]*?\)',
    'settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")',
    s,count=1
)

# Text cleanup: this build no longer embeds TradingView.
s=s.replace('TRADINGVIEW LIVE','FCS XAUUSD LIVE').replace('TradingView live','FCS XAUUSD live').replace('TradingView Live','FCS XAUUSD Live')
s=s.replace('TradingView live chart is unaffected.','FCS XAUUSD live chart remains connected.')

# Gold-only switchPair.
s=re.sub(r'    private fun switchPair\(s:String\)\{[^\n]*\}',
'''    private fun switchPair(s:String){
        symbol="XAUUSD";prefs.edit().putString("symbol","XAUUSD").apply();switchVisibleChart()
    }''',s,count=1)

# Historical injection helper. This is the same FcsClient candle set used by analysis.
anchor='    private fun switchVisibleChart(){'
if anchor not in s: raise SystemExit('v58 MainActivity switchVisibleChart anchor not found')
helper='''    private fun pushFcsHistory(data:List<Candle>){
        if(!chartReady)return
        val arr=JSONArray()
        data.takeLast(300).forEach{c->
            val ts=if(c.t>10_000_000_000L)c.t/1000L else c.t
            arr.put(JSONObject().put("time",ts).put("open",c.o).put("high",c.h).put("low",c.l).put("close",c.c).put("volume",c.v))
        }
        chart.evaluateJavascript("window.setHistoricalCandles(${JSONObject.quote(period)},${arr})",null)
    }
    private fun syncFcsChart(){
        if(!chartReady)return
        symbol="XAUUSD"
        chart.evaluateJavascript("window.switchTimeframe(${JSONObject.quote(period)})",null)
        val k=savedHistoryKey()
        if(k.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)
        val data=FcsClient.peek("XAUUSD",period,300)
        if(!data.isNullOrEmpty()){pushFcsHistory(data);pushChartLevels(data)}
        showSignalCard(SignalStore.loadActive(this,"XAUUSD",period))
    }
'''
s=s.replace(anchor,helper+anchor,1)

# Replace the whole switchVisibleChart function robustly.
start=s.index('    private fun switchVisibleChart(){')
end=s.index('\n    private fun ',start+10)
new_switch='''    private fun switchVisibleChart(){
        symbol="XAUUSD";prefs.edit().putString("symbol","XAUUSD").putString("period",period).apply()
        pairLabel.text="XAUUSD • $period"
        syncFcsChart()
        showExisting();updateSnapshot()
    }
'''
s=s[:start]+new_switch+s[end:]

# Ensure analysis history is injected whenever ANALYZE/RE-EVALUATE refreshes chart guides.
if '    private fun showAnalysisGuides(data:List<Candle>){' in s:
    st=s.index('    private fun showAnalysisGuides(data:List<Candle>){')
    en=s.index('\n    private fun ',st+10)
    seg=s[st:en]
    if 'pushFcsHistory(data)' not in seg:
        seg=seg.replace('pushChartLevels(data);','pushFcsHistory(data);pushChartLevels(data);',1)
    s=s[:st]+seg+s[en:]

# When a key is saved/updated, reconnect the embedded FCS module immediately.
if '    private fun saveHistoryKey(){' in s:
    st=s.index('    private fun saveHistoryKey(){')
    en=s.index('\n    private fun ',st+10)
    seg=s[st:en]
    if 'syncFcsChart()' not in seg:
        seg=seg.replace('startMonitorIfNeeded()','syncFcsChart();startMonitorIfNeeded()',1)
    s=s[:st]+seg+s[en:]

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating OverlayService: same FCS module, same key/cache, Gold only.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
if 'import org.json.JSONArray' not in s:
    s=s.replace('import org.json.JSONObject\n','import org.json.JSONObject\nimport org.json.JSONArray\n',1)
s=s.replace('private fun read(){symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m"}',
            'private fun read(){symbol="XAUUSD";prefs.edit().putString("symbol","XAUUSD").apply();period=prefs.getString("period","15m")?:"15m"}')
s='\n'.join(line for line in s.splitlines() if 'BTCUSDT' not in line)+'\n'
s=s.replace('TRADINGVIEW LIVE','FCS XAUUSD LIVE').replace('TradingView live','FCS XAUUSD live').replace('TradingView Live','FCS XAUUSD Live')

s=re.sub(
    r'val html=assets\.open\("tradingview_live\.html"\).*?loadDataWithBaseURL\([^\n]*?\)',
    'settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")',
    s,count=1
)

s=re.sub(r'    private fun switch\(s:String,p:String\)\{[^\n]*\}',
'''    private fun switch(s:String,p:String){
        symbol="XAUUSD";period=p;prefs.edit().putString("symbol","XAUUSD").putString("period",p).apply();loadChart();showState()
    }''',s,count=1)

# Replace loadChart so the existing floating chart follows app timeframe and uses the saved key.
s=re.sub(r'    private fun loadChart\(\)\{[^\n]*\}',
'''    private fun loadChart(){
        val w=chart?:return
        w.evaluateJavascript("window.switchTimeframe(${JSONObject.quote(period)})",null)
        val k=prefs.getString("api_key","")?.trim().orEmpty()
        if(k.isNotBlank())w.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)
        showOverlayGuidesFromCache();overlay(SignalStore.displayState(this,"XAUUSD",period))
    }''',s,count=1)

# Replace/ensure guide helper pushes both history and analysis overlays.
if '    private fun showOverlayGuidesFromCache(){' in s:
    st=s.index('    private fun showOverlayGuidesFromCache(){')
    en=s.index('\n    private fun displayed()',st)
    helper='''    private fun showOverlayGuidesFromCache(){
        val w=chart?:return
        val data=FcsClient.peek("XAUUSD",period,300)
        if(data.isNullOrEmpty()){w.evaluateJavascript("clearAnalysisLevels()",null);return}
        val arr=JSONArray();data.takeLast(300).forEach{c->val ts=if(c.t>10_000_000_000L)c.t/1000L else c.t;arr.put(JSONObject().put("time",ts).put("open",c.o).put("high",c.h).put("low",c.l).put("close",c.c).put("volume",c.v))}
        w.evaluateJavascript("window.setHistoricalCandles(${JSONObject.quote(period)},${arr})",null)
        val lv=AnalysisEngine.chartLevels(period,data)?:run{w.evaluateJavascript("clearAnalysisLevels()",null);return}
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance).put("timeframe",period)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        w.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }
'''
    s=s[:st]+helper+s[en:]

p.write_text(s)

# -----------------------------------------------------------------------------
# FcsClient: XAUUSD only. Keep the v57 FX provider path.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
s=s.replace('private val symbols=listOf("XAUUSD","BTCUSDT")','private val symbols=listOf("XAUUSD")')
if '    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{' in s:
    st=s.index('    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{')
    en=s.index('\n\n    private fun fetch(',st)
    fm='''    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        if(symbol.uppercase()!="XAUUSD")throw IllegalArgumentException("Only XAUUSD is supported")
        return fetch("forex",key,"XAUUSD",period,length,"commodity","FX")
    }'''
    s=s[:st]+fm+s[en:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Native socket hub: Gold only; keep it compatible with background lifecycle.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
s=p.read_text()
s=s.replace('private val symbols=listOf("FX:XAUUSD","BINANCE:BTCUSDT")','private val symbols=listOf("FX:XAUUSD")')
s=s.replace('private val periods=listOf("1","5","15","30","60")','private val periods=listOf("1","5","15","30","60","120","240","1D","1W")')
s='\n'.join(line for line in s.splitlines() if 'endsWith("BTCUSDT"' not in line)+'\n'
s=s.replace('''            "60","1h"->"1h"
            else->return''','''            "60","1h"->"1h"
            "120","2h"->"2h"
            "240","4h"->"4h"
            "1d"->"1D"
            "1w"->"1W"
            else->return''')
p.write_text(s)

# Remove the old TradingView asset from the packaged app. Earlier patch scripts still
# get to use/modify it during CI, then this final patch deletes it before assembleDebug.
Path('app/src/main/assets/tradingview_live.html').unlink(missing_ok=True)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 58',g);g=re.sub(r'versionName = "[^"]+"','versionName = "58.0"',g);p.write_text(g)
print('v58 integrated uploaded FCS XAUUSD module, removed TradingView/BTCUSDT')
