from pathlib import Path
import re

# v63 FINAL chart transport architecture:
# - REST Analysis Access Key remains in native Android FcsClient.
# - Dedicated WebSocket Key is used ONLY by FCS's official bundled FCSClient.
# - No native/custom LiveSocketHub ownership for the visible chart.
# - WebView runs with https://fcsapi.com/ base origin (not file://) to avoid null/file Origin handshakes.
# - Vendor client is bundled locally, so chart connection does not depend on a CDN script.

# -----------------------------------------------------------------------------
# Restore the uploaded canvas renderer shell. Android injects vendor lib + JS inline.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/index.html')
p.write_text(r'''<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
  <title>XAUUSD Live Chart</title>
  <link rel="stylesheet" href="chart.css" />
</head>
<body>
  <div id="app">
    <div class="topbar">
      <div><div class="symbol">XAUUSD</div><div id="price" class="price">--</div></div>
      <div id="status" class="status disconnected">Connecting…</div>
    </div>
    <div id="timeframes" class="timeframes" aria-hidden="true">
      <button data-tf="1m">1m</button><button data-tf="5m">5m</button><button data-tf="15m" class="active">15m</button><button data-tf="30m">30m</button><button data-tf="1h">1H</button><button data-tf="2h">2H</button><button data-tf="4h">4H</button><button data-tf="1D">1D</button><button data-tf="1W">1W</button>
    </div>
    <div class="chart-wrap"><canvas id="chart"></canvas><div id="emptyState" class="empty">Loading XAUUSD candles…</div></div>
    <div class="quote-row"><div><span>O</span><b id="o">--</b></div><div><span>H</span><b id="h">--</b></div><div><span>L</span><b id="l">--</b></div><div><span>C</span><b id="c">--</b></div></div>
  </div>
  <script src="fcs-client-lib.js"></script>
  <script src="chart.js"></script>
</body>
</html>
''')

# -----------------------------------------------------------------------------
# Official FCSClient connection + existing canvas renderer.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/chart.js')
p.write_text(r'''(() => {
  "use strict";
  const SYMBOL="FX:XAUUSD";
  const TIMEFRAMES=["1m","5m","15m","30m","1h","2h","4h","1D","1W"];
  const cache=Object.fromEntries(TIMEFRAMES.map(tf=>[tf,[]]));
  let client=null,currentTf="15m",socketKey="",subscribedTf=null,analysis=null,signal=null;
  let viewBars=80,panBars=0,dragStartX=null,dragStartPan=0,pinchStartDistance=0,pinchStartBars=80,watchdog=null;
  const canvas=document.getElementById("chart"),ctx=canvas.getContext("2d"),emptyState=document.getElementById("emptyState"),statusEl=document.getElementById("status"),priceEl=document.getElementById("price");
  const fields={o:document.getElementById("o"),h:document.getElementById("h"),l:document.getElementById("l"),c:document.getElementById("c")};
  function setStatus(t,c){statusEl.textContent=t;statusEl.className="status "+(c||"")}
  function norm(tf){const x=String(tf||"").trim(),m={"1":"1m","5":"5m","15":"15m","30":"30m","60":"1h","1H":"1h","120":"2h","2H":"2h","240":"4h","4H":"4h","1440":"1D","1d":"1D","10080":"1W","1w":"1W"};const y=m[x]||x;return TIMEFRAMES.includes(y)?y:"15m"}
  function serverTf(tf){return {"1m":"1","5m":"5","15m":"15","30m":"30","1h":"60","2h":"120","4h":"240","1D":"1440","1W":"10080"}[norm(tf)]||"15"}
  function fmt(v){const n=Number(v);return Number.isFinite(n)?n.toFixed(2):"--"}
  function parse(v){if(!v)return null;if(typeof v==="string"){try{return JSON.parse(v)}catch(_){return null}}return v}
  function bridge(name,args){try{if(window.AndroidFcs&&typeof window.AndroidFcs[name]==="function")window.AndroidFcs[name](...args)}catch(_){}}
  function resizeCanvas(){const r=canvas.getBoundingClientRect(),d=Math.max(1,window.devicePixelRatio||1);canvas.width=Math.max(1,Math.floor(r.width*d));canvas.height=Math.max(1,Math.floor(r.height*d));ctx.setTransform(d,0,0,d,0,0);draw()}
  function upsert(tf,p,fromSocket=true){tf=norm(tf);if(!p)return;const c={time:Number(p.t??p.time),open:Number(p.o??p.open),high:Number(p.h??p.high),low:Number(p.l??p.low),close:Number(p.c??p.close),volume:Number(p.v??p.volume??0)};if(![c.time,c.open,c.high,c.low,c.close].every(Number.isFinite))return;const a=cache[tf]||(cache[tf]=[]),last=a[a.length-1];if(last&&last.time===c.time)a[a.length-1]=c;else{a.push(c);a.sort((x,y)=>x.time-y.time);if(a.length>500)a.splice(0,a.length-500)}if(fromSocket)bridge("onCandle",[tf,c.time,c.open,c.high,c.low,c.close,c.volume]);if(tf===currentTf)draw()}
  window.setHistoricalCandles=function(tf,candles){tf=norm(tf);if(!Array.isArray(candles))return;cache[tf]=candles.map(c=>({time:Number(c.time??c.t),open:Number(c.open??c.o),high:Number(c.high??c.h),low:Number(c.low??c.l),close:Number(c.close??c.c),volume:Number(c.volume??c.v??0)})).filter(c=>[c.time,c.open,c.high,c.low,c.close].every(Number.isFinite)).sort((a,b)=>a.time-b.time).slice(-500);if(tf===currentTf){panBars=0;draw()}};
  function overlayNumbers(){const o=[],add=v=>{v=Number(v);if(Number.isFinite(v))o.push(v)};if(analysis){add(analysis.support);add(analysis.resistance);add(analysis.bullObLow);add(analysis.bullObHigh);add(analysis.bearObLow);add(analysis.bearObHigh)}if(signal){add(signal.entry);add(signal.sl);add(signal.tp1);add(signal.tp2)}return o}
  function visible(){const all=cache[currentTf]||[];if(!all.length)return[];const count=Math.max(20,Math.min(240,Math.round(viewBars))),maxPan=Math.max(0,all.length-count);panBars=Math.max(0,Math.min(maxPan,Math.round(panBars)));const end=Math.max(0,all.length-panBars),start=Math.max(0,end-count);return all.slice(start,end)}
  function draw(){const r=canvas.getBoundingClientRect(),w=r.width,h=r.height;ctx.clearRect(0,0,w,h);const candles=visible();if(!candles.length){emptyState.style.display="flex";return}emptyState.style.display="none";const pl=8,pr=64,pt=10,pb=22,cw=Math.max(1,w-pl-pr),ch=Math.max(1,h-pt-pb);let min=Math.min(...candles.map(c=>c.low)),max=Math.max(...candles.map(c=>c.high));overlayNumbers().forEach(v=>{min=Math.min(min,v);max=Math.max(max,v)});if(max===min){max+=1;min-=1}let span=max-min;max+=span*.055;min-=span*.055;span=max-min;const y=p=>pt+(max-p)/span*ch;ctx.strokeStyle="#18202a";ctx.fillStyle="#75808d";ctx.lineWidth=1;ctx.font="10px Arial";for(let i=0;i<=5;i++){const yy=pt+ch*i/5;ctx.beginPath();ctx.moveTo(pl,yy);ctx.lineTo(w-pr,yy);ctx.stroke();ctx.fillText((max-span*i/5).toFixed(2),w-pr+6,yy+3)}
    function zone(lo,hi,color){lo=Number(lo);hi=Number(hi);if(!Number.isFinite(lo)||!Number.isFinite(hi))return;const a=y(Math.max(lo,hi)),b=y(Math.min(lo,hi));ctx.save();ctx.globalAlpha=.16;ctx.fillStyle=color;ctx.fillRect(pl,Math.min(a,b),cw,Math.max(2,Math.abs(b-a)));ctx.globalAlpha=.65;ctx.strokeStyle=color;ctx.strokeRect(pl,Math.min(a,b),cw,Math.max(2,Math.abs(b-a)));ctx.restore()}
    function line(price,color,label,dash){price=Number(price);if(!Number.isFinite(price))return;const yy=y(price);ctx.save();ctx.strokeStyle=color;ctx.lineWidth=1;ctx.setLineDash(dash?[5,4]:[]);ctx.beginPath();ctx.moveTo(pl,yy);ctx.lineTo(w-pr,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font="bold 9px Arial";ctx.fillText(label+" "+price.toFixed(2),pl+4,Math.max(9,yy-3));ctx.restore()}
    if(analysis){zone(analysis.bullObLow,analysis.bullObHigh,"#3ec9d0");zone(analysis.bearObLow,analysis.bearObHigh,"#ef5350");line(analysis.support,"#42a5f5","S",true);line(analysis.resistance,"#ce93d8","R",true)}const step=cw/candles.length,bw=Math.max(2,Math.min(10,step*.62));candles.forEach((c,i)=>{const x=pl+step*i+step/2,yo=y(c.open),yh=y(c.high),yl=y(c.low),yc=y(c.close),up=c.close>=c.open;ctx.strokeStyle=up?"#36c98f":"#f35b66";ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.15;ctx.beginPath();ctx.moveTo(x,yh);ctx.lineTo(x,yl);ctx.stroke();const top=Math.min(yo,yc),bh=Math.max(1.5,Math.abs(yc-yo));ctx.fillRect(x-bw/2,top,bw,bh)});if(signal){line(signal.entry,"#f2c94c","ENTRY",false);line(signal.sl,"#ff5a67","SL",true);line(signal.tp1,"#3ddc84","TP1",true);line(signal.tp2,"#56d7d1","TP2",true)}const last=(cache[currentTf]||[]).slice(-1)[0]||candles[candles.length-1];if(last){const py=y(last.close);ctx.strokeStyle="#9aa6b2";ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(pl,py);ctx.lineTo(w-pr,py);ctx.stroke();ctx.setLineDash([]);priceEl.textContent=fmt(last.close);fields.o.textContent=fmt(last.open);fields.h.textContent=fmt(last.high);fields.l.textContent=fmt(last.low);fields.c.textContent=fmt(last.close)}}
  function handle(data){if(!data||data.type!=="price"||String(data.symbol||"").toUpperCase()!==SYMBOL)return;const tf=norm(String(data.timeframe||currentTf)),p=data.prices||{},mode=String(p.mode||"").toLowerCase();if(mode==="candle"||mode==="initial"||(p.o!=null&&p.h!=null&&p.l!=null&&p.c!=null))upsert(tf,p,true);else if(mode==="askbid"||p.c!=null){const px=Number(p.c),t=Number(p.t??p.update??Math.floor(Date.now()/1000));if(Number.isFinite(px)){priceEl.textContent=fmt(px);bridge("onPrice",[tf,t,px])}}}
  function leaveCurrent(){if(client&&subscribedTf){try{client.leave(SYMBOL,subscribedTf)}catch(_){}subscribedTf=null}}
  function subscribe(){if(!client||!client.isConnected)return;const next=serverTf(currentTf);if(subscribedTf===next)return;leaveCurrent();subscribedTf=next;try{client.join(SYMBOL,next)}catch(_){}}
  function disconnect(){if(watchdog){clearTimeout(watchdog);watchdog=null}leaveCurrent();if(client){try{client.disconnect()}catch(_){}client=null}}
  function connect(){if(!socketKey){setStatus("Key required","disconnected");return}if(typeof FCSClient==="undefined"){setStatus("Chart library unavailable","error");return}disconnect();try{client=new FCSClient(socketKey);client.focusTimeout=0;client.reconnectDelay=3000;client.reconnectlimit=20;client.onconnected=()=>{if(watchdog){clearTimeout(watchdog);watchdog=null}setStatus("LIVE • XAUUSD","connected");subscribe()};client.onreconnect=()=>{setStatus("LIVE • XAUUSD","connected");subscribe()};client.onclose=()=>setStatus("Disconnected","disconnected");client.onerror=()=>setStatus("Connecting…","reconnecting");client.onmessage=d=>handle(d);setStatus("Connecting…","reconnecting");const result=client.connect();if(result&&typeof result.catch==="function")result.catch(()=>setStatus("Connection failed","error"));watchdog=setTimeout(()=>{if(!client||!client.isConnected)setStatus("Connection failed","error")},12000)}catch(_){setStatus("Connection failed","error")}}
  window.setFcsApiKey=function(key){const k=String(key||"").trim();if(!k){window.setLiveKeyRequired();return}if(socketKey===k&&client&&client.isConnected){subscribe();return}socketKey=k;connect()};
  window.setLiveKeyRequired=function(){socketKey="";disconnect();setStatus("Key required","disconnected")};
  window.switchTimeframe=function(tf){currentTf=norm(tf);panBars=0;document.querySelectorAll("#timeframes button").forEach(b=>b.classList.toggle("active",b.dataset.tf===currentTf));subscribe();draw()};
  window.setAnalysisLevels=function(raw){analysis=parse(raw);draw()};window.clearAnalysisLevels=function(){analysis=null;draw()};window.setSignalCard=function(raw){signal=parse(raw);draw()};window.clearSignalCard=function(){signal=null;draw()};window.loadTradingView=function(_s,tf){window.switchTimeframe(tf)};window.setChartData=function(raw){const d=parse(raw);if(Array.isArray(d))window.setHistoricalCandles(currentTf,d)};window.clearChartData=function(){cache[currentTf]=[];draw()};window.updateLivePrice=function(price,ts){const p=Number(price);if(Number.isFinite(p))bridge("onPrice",[currentTf,Number(ts||Math.floor(Date.now()/1000)),p])};window.setNativeConnectionState=function(_s){};window.onNativeCandle=function(_tf,_c){};
  function dist(a,b){const dx=a.clientX-b.clientX,dy=a.clientY-b.clientY;return Math.sqrt(dx*dx+dy*dy)}canvas.addEventListener("touchstart",e=>{if(e.touches.length===2){pinchStartDistance=dist(e.touches[0],e.touches[1]);pinchStartBars=viewBars;dragStartX=null}else if(e.touches.length===1){dragStartX=e.touches[0].clientX;dragStartPan=panBars}},{passive:false});canvas.addEventListener("touchmove",e=>{e.preventDefault();if(e.touches.length===2&&pinchStartDistance>0){const d=dist(e.touches[0],e.touches[1]);if(d>0){viewBars=Math.max(20,Math.min(240,pinchStartBars*(pinchStartDistance/d)));draw()}}else if(e.touches.length===1&&dragStartX!=null){const r=canvas.getBoundingClientRect(),px=Math.max(3,(r.width-72)/Math.max(20,viewBars));panBars=Math.max(0,dragStartPan+Math.round((e.touches[0].clientX-dragStartX)/px));draw()}},{passive:false});canvas.addEventListener("touchend",()=>{dragStartX=null;pinchStartDistance=0},{passive:true});canvas.addEventListener("wheel",e=>{e.preventDefault();viewBars=Math.max(20,Math.min(240,viewBars+(e.deltaY>0?8:-8)));draw()},{passive:false});document.querySelectorAll("#timeframes button").forEach(b=>b.addEventListener("click",()=>window.switchTimeframe(b.dataset.tf)));window.addEventListener("resize",resizeCanvas);new ResizeObserver(resizeCanvas).observe(canvas.parentElement);resizeCanvas();
})();
''')

# -----------------------------------------------------------------------------
# MainActivity WebView: inline bundled assets under HTTPS base origin.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
old='settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")'
new='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@MainActivityV29),"AndroidFcs");run{
                val index=this@MainActivityV29.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@MainActivityV29.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@MainActivityV29.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@MainActivityV29.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index.replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>").replace("<script src=\\\"fcs-client-lib.js\\\"></script>","").replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
if old not in s: raise SystemExit('v63 MainActivity WebView anchor missing')
s=s.replace(old,new,1)

# v62 advanced-chart sync is replaced with our uploaded-module sync.
start=s.index('    private fun syncFcsChart(){');end=s.index('\n    private fun ',start+10)
new_sync='''    private fun syncFcsChart(){
        if(!chartReady)return
        symbol="XAUUSD"
        chart.evaluateJavascript("window.switchTimeframe(${JSONObject.quote(period)})",null)
        val live=savedSocketKey()
        if(live.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(live)})",null)
        else chart.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)
        val data=FcsClient.peek("XAUUSD",period,300)
        if(!data.isNullOrEmpty()){pushFcsHistory(data);pushChartLevels(data)}
        showSignalCard(SignalStore.loadActive(this,"XAUUSD",period))
    }
'''
s=s[:start]+new_sync+s[end:]

# Native visible-chart connection must remain disabled.
s=re.sub(r'    private fun startNativeLive\(\)\{.*?\n    \}', '    private fun startNativeLive(){}', s, count=1, flags=re.S)
p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: same HTTPS-base bundled official client + separate socket key.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
old='settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");loadUrl("file:///android_asset/fcs_chart/index.html")'
new='''settings.allowFileAccess=true;settings.allowContentAccess=true;addJavascriptInterface(FcsChartBridge(this@OverlayService),"AndroidFcs");run{
                val index=this@OverlayService.assets.open("fcs_chart/index.html").bufferedReader().use{it.readText()}
                val css=this@OverlayService.assets.open("fcs_chart/chart.css").bufferedReader().use{it.readText()}
                val lib=this@OverlayService.assets.open("fcs_chart/fcs-client-lib.js").bufferedReader().use{it.readText()}
                val js=this@OverlayService.assets.open("fcs_chart/chart.js").bufferedReader().use{it.readText()}
                val html=index.replace("<link rel=\\\"stylesheet\\\" href=\\\"chart.css\\\" />","<style>$css</style>").replace("<script src=\\\"fcs-client-lib.js\\\"></script>","").replace("<script src=\\\"chart.js\\\"></script>","<script>$lib</script><script>$js</script>")
                loadDataWithBaseURL("https://fcsapi.com/",html,"text/html","UTF-8",null)
            }'''
if old not in s: raise SystemExit('v63 Overlay WebView anchor missing')
s=s.replace(old,new,1)
if '    private fun loadChart(){' in s:
    st=s.index('    private fun loadChart(){');en=s.index('\n    private fun ',st+10)
    load='''    private fun loadChart(){
        val w=chart?:return
        w.evaluateJavascript("window.switchTimeframe(${JSONObject.quote(period)})",null)
        val live=prefs.getString("socket_api_key","")?.trim().orEmpty()
        if(live.isNotBlank())w.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(live)})",null)
        else w.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)
        showOverlayGuidesFromCache();overlay(SignalStore.displayState(this,"XAUUSD",period))
    }
'''
    s=s[:st]+load+s[en:]
p.write_text(s)

# Keep custom native socket disabled for chart ownership/background. REST fallback remains.
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text();s=re.sub(r'    private fun startLiveSocket\(\)\{.*?\n    \}', '    private fun startLiveSocket(){}', s, count=1, flags=re.S);p.write_text(s)

p=Path('app/build.gradle.kts');g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 63',g);g=re.sub(r'versionName = "[^"]+"','versionName = "63.0"',g);p.write_text(g)
print('v63 clean official bundled FCS websocket chart applied')
