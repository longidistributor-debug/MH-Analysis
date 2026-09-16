from pathlib import Path
import re

# v61: make Android own the live WebSocket connection and use exact FX:XAUUSD
# for both live stream and REST history/latest. The WebView is renderer-only.

# -----------------------------------------------------------------------------
# MainActivityV29: native socket owner + chart history preload.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('class MainActivityV29:Activity(){','class MainActivityV29:Activity(),LiveSocketHub.Listener{',1)
if 'private var chartHistoryLoading=false' not in s:
    s=s.replace('    private var busy=false\n','    private var busy=false\n    private var chartHistoryLoading=false\n',1)

# Start the native live stream once the UI exists. It may connect before WebView is ready;
# FcsClient still receives candles and the chart catches up after page load.
anchor='        setContentView(buildUi())\n'
if 'LiveSocketHub.addListener(this)' not in s:
    if anchor not in s: raise SystemExit('v61 setContentView anchor missing')
    s=s.replace(anchor,anchor+'''        LiveSocketHub.addListener(this)\n        startNativeLive()\n''',1)

# Renderer sync: no JS-owned connection/key. Native socket owns connection state.
old='''        val k=savedSocketKey()\n        if(k.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)\n        else chart.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)'''
new='''        chart.evaluateJavascript("window.setNativeConnectionState&&window.setNativeConnectionState(${JSONObject.quote(if(LiveSocketHub.isConnected()) "Connected" else "Connecting")})",null)'''
if old in s:s=s.replace(old,new,1)

# Add native socket callbacks + automatic history preload before socket-key helpers.
helper_anchor='    private fun savedSocketKey()=prefs.getString("socket_api_key","")?.trim().orEmpty()'
if 'private fun startNativeLive()' not in s:
    if helper_anchor not in s: raise SystemExit('v61 socket helper anchor missing')
    helpers='''    private fun startNativeLive(){\n        val k=prefs.getString("socket_api_key","")?.trim().orEmpty()\n        if(k.isNotBlank())LiveSocketHub.start(this,k)\n        else if(chartReady)chart.evaluateJavascript("window.setNativeConnectionState&&window.setNativeConnectionState('Disconnected')",null)\n    }\n\n    override fun onSocketState(state:String){\n        if(!::chart.isInitialized||!chartReady)return\n        val label=when{\n            LiveSocketHub.isConnected()->"Connected"\n            state.contains("CONNECT",true)||state.contains("RECONNECT",true)||state.contains("RETRY",true)->"Connecting"\n            else->"Disconnected"\n        }\n        runOnUiThread{chart.evaluateJavascript("window.setNativeConnectionState&&window.setNativeConnectionState(${JSONObject.quote(label)})",null)}\n    }\n\n    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){\n        if(symbol!="XAUUSD"||!::chart.isInitialized||!chartReady)return\n        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t\n        val j=JSONObject().put("time",ts).put("open",candle.o).put("high",candle.h).put("low",candle.l).put("close",candle.c).put("volume",candle.v)\n        runOnUiThread{chart.evaluateJavascript("window.onNativeCandle&&window.onNativeCandle(${JSONObject.quote(timeframe)},${j})",null)}\n    }\n\n    private fun ensureChartHistory(){\n        if(!chartReady||chartHistoryLoading)return\n        val tf=period\n        val cached=FcsClient.peek("XAUUSD",tf,300).orEmpty()\n        if(cached.size>=60){pushFcsHistory(cached);pushChartLevels(cached);return}\n        val key=savedHistoryKey();if(key.isBlank())return\n        chartHistoryLoading=true\n        thread(name="mh-chart-history"){\n            val data=runCatching{FcsClient.seedForPeriod(key,"XAUUSD",tf,false).first}.getOrNull()\n            runOnUiThread{\n                chartHistoryLoading=false\n                if(tf==period&&!data.isNullOrEmpty()){pushFcsHistory(data);pushChartLevels(data);updateSnapshot(data)}\n            }\n        }\n    }\n\n'''
    s=s.replace(helper_anchor,helpers+helper_anchor,1)

# Every visible chart/timeframe switch should preload exact timeframe history.
if '    private fun switchVisibleChart(){' in s:
    st=s.index('    private fun switchVisibleChart(){')
    en=s.index('\n    private fun ',st+10)
    seg=s[st:en]
    if 'ensureChartHistory()' not in seg:
        seg=seg.replace('        syncFcsChart()','        syncFcsChart()\n        ensureChartHistory()',1)
    s=s[:st]+seg+s[en:]

# Saving/updating socket key must immediately restart native connection.
if '    private fun saveSocketKey(){' in s:
    st=s.index('    private fun saveSocketKey(){')
    en=s.index('\n\n',st)
    seg=s[st:en]
    if 'startNativeLive()' not in seg:
        seg=seg.replace('editSocket=false;socketInput.setText("");updateSocketKeyUi();syncFcsChart()',
                        'editSocket=false;socketInput.setText("");updateSocketKeyUi();startNativeLive();syncFcsChart()')
    s=s[:st]+seg+s[en:]

# Ensure listener cleanup without removing any existing logic.
if 'override fun onDestroy(){LiveSocketHub.removeListener(this);' not in s:
    # Replace a simple existing onDestroy if present, otherwise insert near utility helpers.
    if re.search(r'    override fun onDestroy\(\)\{[^\n]*\}',s):
        s=re.sub(r'    override fun onDestroy\(\)\{([^\n]*)\}',r'    override fun onDestroy(){LiveSocketHub.removeListener(this);\1}',s,count=1)
    else:
        ins='    private fun savedSocketKey()'
        idx=s.find(ins)
        if idx>0:s=s[:idx]+'    override fun onDestroy(){LiveSocketHub.removeListener(this);super.onDestroy()}\n\n'+s[idx:]

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: renderer-only WebView; native LiveSocketHub supplies candles.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('class OverlayService:Service(){','class OverlayService:Service(),LiveSocketHub.Listener{',1)
# start listener/native stream during service creation
old='override fun onCreate(){super.onCreate();FcsClient.init(this);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}'
new='override fun onCreate(){super.onCreate();FcsClient.init(this);LiveSocketHub.addListener(this);val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}'
if old in s:s=s.replace(old,new,1)

# no key injection into JS
s=re.sub(r'''\n\s*val k=prefs\.getString\("socket_api_key",""\)\?\.trim\(\)\.orEmpty\(\)\n\s*if\(k\.isNotBlank\(\)\)w\.evaluateJavascript\("window\.setFcsApiKey\([^\n]+\n\s*else w\.evaluateJavascript\("window\.setLiveKeyRequired[^\n]+''','',s,count=1)

# add listener callbacks before hidePanel
anchor='    private fun hidePanel()'
if 'override fun onSocketState(state:String)' not in s:
    callbacks='''    override fun onSocketState(state:String){\n        val w=chart?:return\n        val label=if(LiveSocketHub.isConnected())"Connected" else if(state.contains("CONNECT",true)||state.contains("RECONNECT",true)||state.contains("RETRY",true))"Connecting" else "Disconnected"\n        Handler(Looper.getMainLooper()).post{w.evaluateJavascript("window.setNativeConnectionState&&window.setNativeConnectionState(${JSONObject.quote(label)})",null)}\n    }\n    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){\n        val w=chart?:return;if(symbol!="XAUUSD")return\n        val ts=if(candle.t>10_000_000_000L)candle.t/1000L else candle.t\n        val j=JSONObject().put("time",ts).put("open",candle.o).put("high",candle.h).put("low",candle.l).put("close",candle.c).put("volume",candle.v)\n        Handler(Looper.getMainLooper()).post{w.evaluateJavascript("window.onNativeCandle&&window.onNativeCandle(${JSONObject.quote(timeframe)},${j})",null)}\n    }\n'''
    if anchor not in s: raise SystemExit('v61 Overlay hidePanel anchor missing')
    s=s.replace(anchor,callbacks+anchor,1)

# listener cleanup
s=s.replace('override fun onDestroy(){hidePanel();', 'override fun onDestroy(){LiveSocketHub.removeListener(this);hidePanel();',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# FcsClient: exact exchange-qualified FX:XAUUSD on both History and Latest.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
s=s.replace('mh_candle_cache_v57_fx','mh_candle_cache_v61_exact_fx')
# v58 final fetchMarket
s=s.replace('return fetch("forex",key,"XAUUSD",period,length,"commodity","FX")',
            'return fetch("forex",key,"FX:XAUUSD",period,length,"","")')
# exact latest ticker; remove type/exchange filters
s=re.sub(r'"XAUUSD"->"https://api-v4\.fcsapi\.com/forex/latest\?symbol=\$\{enc\("XAUUSD"\)\}&period=\$\{enc\(p\)\}&type=commodity&exchange=FX&get_profile=1&access_key=\$\{enc\(key\)\}"',
         '"XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("FX:XAUUSD")}&period=${enc(p)}&get_profile=1&access_key=${enc(key)}"',s,count=1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Embedded chart: renderer only. Android native socket supplies connection state/candles.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/index.html')
h=p.read_text()
h=h.replace('  <script src="https://fcsapi.com/demo/socket/v4/fcs-client-lib.js"></script>\n','')
h=h.replace('<div id="status" class="status disconnected">Connecting…</div>','<div id="status" class="status disconnected">Connecting…</div>')
p.write_text(h)

p=Path('app/src/main/assets/fcs_chart/chart.js')
s=p.read_text()
# Prevent WebView from owning/closing a second connection. Keep compatibility names as no-ops.
s=re.sub(r'  window\.setFcsApiKey=function\(key\)\{.*?\};\n  window\.setLiveKeyRequired=function\(\)\{.*?\};',
'''  window.setFcsApiKey=function(_key){};\n  window.setLiveKeyRequired=function(){setStatus("Disconnected","disconnected")};\n  window.setNativeConnectionState=function(state){\n    const x=String(state||"Disconnected");\n    if(x==="Connected")setStatus("LIVE • XAUUSD","connected");\n    else if(x==="Connecting")setStatus("Connecting…","reconnecting");\n    else setStatus("Disconnected","disconnected");\n  };\n  window.onNativeCandle=function(tf,raw){\n    const c=parse(raw)||raw;if(!c)return;\n    upsertCandle(normalizeTf(tf),{t:c.time??c.t,o:c.open??c.o,h:c.high??c.h,l:c.low??c.l,c:c.close??c.c,v:c.volume??c.v},false);\n    if(normalizeTf(tf)===currentTf)draw();\n  };''',s,count=1,flags=re.S)
# The old connect code becomes dead because setFcsApiKey no longer invokes it.
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 61',g);g=re.sub(r'versionName = "[^"]+"','versionName = "61.0"',g);p.write_text(g)
print('v61 native live socket + exact FX:XAUUSD REST/chart alignment applied')
