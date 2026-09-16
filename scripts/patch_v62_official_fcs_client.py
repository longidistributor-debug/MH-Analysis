from pathlib import Path
import re

# v62: stop using the hand-written Android socket for the visible chart.
# Use FCS's official browser client bundled inside the APK, but run the WebView
# under an HTTPS base origin so Android WebView does not present a file:// origin
# during the WebSocket handshake.  REST analysis remains separate and unchanged.

# -----------------------------------------------------------------------------
# MainActivity: renderer/browser client owns visible live chart connection.
# Keep v61 automatic REST history preload, remove native foreground socket owner.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('class MainActivityV29:Activity(),LiveSocketHub.Listener{','class MainActivityV29:Activity(){',1)
s=s.replace('        LiveSocketHub.addListener(this)\n        startNativeLive()\n','',1)

# Replace local file load with a self-contained HTML document served with HTTPS base
# origin. The vendor library, chart CSS and chart JS are bundled in the APK.
old='settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")'
new='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");run{
                val index=this@MainActivityV29.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@MainActivityV29.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@MainActivityV29.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@MainActivityV29.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index
                    .replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>")
                    .replace("<script src=\\\"fcs-client-lib.js\\\"></script>","")
                    .replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
if old not in s: raise SystemExit('v62 MainActivity chart load anchor missing')
s=s.replace(old,new,1)

# syncFcsChart: restore the separate socket key injection into the official client.
if '    private fun syncFcsChart(){' in s:
    st=s.index('    private fun syncFcsChart(){');en=s.index('\n    private fun ',st+10);seg=s[st:en]
    seg=re.sub(r'\s*chart\.evaluateJavascript\("window\.setNativeConnectionState[^\n]+\n',
'''        val k=savedSocketKey()
        if(k.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)
        else chart.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)
''',seg,count=1)
    s=s[:st]+seg+s[en:]

# Remove v61 native foreground socket callbacks, but KEEP ensureChartHistory().
s=re.sub(r'    private fun startNativeLive\(\)\{.*?\n    \}\n\n','',s,count=1,flags=re.S)
s=re.sub(r'    override fun onSocketState\(state:String\)\{.*?\n    \}\n\n','',s,count=1,flags=re.S)
s=re.sub(r'    override fun onLiveCandle\(symbol:String,timeframe:String,candle:Candle\)\{.*?\n    \}\n\n','',s,count=1,flags=re.S)
s=s.replace('updateSocketKeyUi();startNativeLive();syncFcsChart()','updateSocketKeyUi();syncFcsChart()')
s=s.replace('override fun onDestroy(){LiveSocketHub.removeListener(this);super.onDestroy()}','override fun onDestroy(){super.onDestroy()}')
p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: same official bundled FCS client / HTTPS base-origin approach.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('class OverlayService:Service(),LiveSocketHub.Listener{','class OverlayService:Service(){',1)
s=s.replace('override fun onCreate(){super.onCreate();FcsClient.init(this);LiveSocketHub.addListener(this);val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}',
            'override fun onCreate(){super.onCreate();FcsClient.init(this);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}',1)
old='settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")'
new='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");run{
                val index=this@OverlayService.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@OverlayService.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@OverlayService.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@OverlayService.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index
                    .replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>")
                    .replace("<script src=\\\"fcs-client-lib.js\\\"></script>","")
                    .replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
if old not in s: raise SystemExit('v62 Overlay chart load anchor missing')
s=s.replace(old,new,1)

# Put the saved WebSocket key back into floating chart's official client.
if '    private fun loadChart(){' in s:
    st=s.index('    private fun loadChart(){');en=s.index('\n    private fun ',st+10);seg=s[st:en]
    if 'socket_api_key' not in seg:
        needle='        w.evaluateJavascript("window.switchTimeframe(${JSONObject.quote(period)})",null)\n'
        if needle not in seg: raise SystemExit('v62 Overlay loadChart switch anchor missing')
        seg=seg.replace(needle,needle+'''        val k=prefs.getString("socket_api_key","")?.trim().orEmpty()
        if(k.isNotBlank())w.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)
        else w.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)
''',1)
    s=s[:st]+seg+s[en:]

s=re.sub(r'    override fun onSocketState\(state:String\)\{.*?\n    \}\n','',s,count=1,flags=re.S)
s=re.sub(r'    override fun onLiveCandle\(symbol:String,timeframe:String,candle:Candle\)\{.*?\n    \}\n','',s,count=1,flags=re.S)
s=s.replace('override fun onDestroy(){LiveSocketHub.removeListener(this);hidePanel();','override fun onDestroy(){hidePanel();',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Chart JS: use the official FCSClient exactly as intended. One symbol + one visible
# timeframe subscription only, to reduce connection/subscription complexity.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/chart.js')
s=p.read_text()
if 'let subscribedTf = null;' not in s:
    s=s.replace('  let client = null;\n','  let client = null;\n  let subscribedTf = null;\n  let connectWatchdog = null;\n',1)

# Timeframe mapping and current-only subscription.
start=s.index('  function subscribeAll(){')
end=s.index('\n  function disconnect(){',start)
new_sub='''  function serverTf(tf){
    const x=normalizeTf(tf);
    const m={"1m":"1","5m":"5","15m":"15","30m":"30","1h":"60","2h":"120","4h":"240","1D":"1D","1W":"1W"};
    return m[x]||"15";
  }
  function subscribeCurrent(){
    if(!client||!client.isConnected)return;
    const next=serverTf(currentTf);
    if(subscribedTf&&subscribedTf!==next){try{client.leave(SYMBOL,subscribedTf)}catch(_){}}
    subscribedTf=next;
    try{client.join(SYMBOL,next)}catch(_){}
  }
'''
s=s[:start]+new_sub+s[end:]

# Vendor client connect lifecycle. onconnected means FCS authentication has passed.
start=s.index('  function connect(){')
end=s.index('\n\n  window.setFcsApiKey=',start)
new_connect='''  function connect(){
    if(!apiKey){setStatus("Key required","error");return}
    if(typeof FCSClient==="undefined"){setStatus("Live library unavailable","error");return}
    disconnect();subscribedTf=null;
    try{
      client=new FCSClient(apiKey,WS_URL);
      client.focusTimeout=0;
      client.reconnectDelay=3000;
      client.reconnectlimit=20;
      client.onconnected=()=>{
        if(connectWatchdog){clearTimeout(connectWatchdog);connectWatchdog=null}
        setStatus("LIVE • XAUUSD","connected");subscribeCurrent();
      };
      client.onreconnect=()=>{setStatus("LIVE • XAUUSD","connected");subscribeCurrent()};
      client.onclose=()=>setStatus("Disconnected","disconnected");
      client.onerror=()=>setStatus("Connecting…","reconnecting");
      client.onmessage=data=>{
        if(!data)return;
        if(data.type==="price"&&String(data.symbol||"").toUpperCase()===SYMBOL)handlePrice(data);
      };
      setStatus("Connecting…","reconnecting");
      const pending=client.connect();
      if(pending&&typeof pending.catch==="function")pending.catch(()=>setStatus("Connection failed","error"));
      connectWatchdog=setTimeout(()=>{if(!client||!client.isConnected)setStatus("Connection failed","error")},12000);
    }catch(_){setStatus("Connection failed","error")}
  }
'''
s=s[:start]+new_connect+s[end:]

# Replace v61 no-op/native compatibility block with real key entry point.
start=s.index('  window.setFcsApiKey=')
end=s.index('\n  window.switchTimeframe=',start)
new_api='''  window.setFcsApiKey=function(key){
    if(!key||typeof key!=="string"){setStatus("Key required","error");return}
    const k=key.trim();if(!k)return;
    if(apiKey===k&&client&&client.isConnected){subscribeCurrent();return}
    if(apiKey!==k){apiKey=k}
    connect();
  };
  window.setLiveKeyRequired=function(){disconnect();apiKey=null;setStatus("Key required","disconnected")};
  window.setNativeConnectionState=function(_state){};
  window.onNativeCandle=function(_tf,_raw){};
'''
s=s[:start]+new_api+s[end:]

# Switching timeframe changes the live subscription as well as the renderer.
old='window.switchTimeframe=function(tf){currentTf=normalizeTf(tf);panBars=0;document.querySelectorAll("#timeframes button").forEach(b=>b.classList.toggle("active",b.dataset.tf===currentTf));draw()};'
new='window.switchTimeframe=function(tf){currentTf=normalizeTf(tf);panBars=0;document.querySelectorAll("#timeframes button").forEach(b=>b.classList.toggle("active",b.dataset.tf===currentTf));subscribeCurrent();draw()};'
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Ensure the final generated HTML has no remote dependency. Vendor library is
# injected inline by Android, so keep only chart.js marker for replacement.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/index.html')
h=p.read_text()
h=h.replace('  <script src="https://fcsapi.com/demo/socket/v4/fcs-client-lib.js"></script>\n','')
h=h.replace('  <script src="fcs-client-lib.js"></script>\n','')
p.write_text(h)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 62',g);g=re.sub(r'versionName = "[^"]+"','versionName = "62.0"',g);p.write_text(g)
print('v62 official bundled FCS client + HTTPS-origin WebView applied')
