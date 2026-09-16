from pathlib import Path
import re

# v62: remove our custom WebSocket implementation from the user-visible chart.
# Use FCS's official Advanced Chart library exactly as documented:
#   accessKey + socketApiKey + symbol FX:XAUUSD + enableSocket true.
# Android analysis remains independent and continues using FcsClient REST data.
# Existing signal/alarm/analysis UI is preserved.

# -----------------------------------------------------------------------------
# Official FCS chart wrapper (renderer + FCS-owned REST/socket lifecycle)
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/index.html')
p.write_text(r'''<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>XAUUSD Live Chart</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/fcsapi/chart-js/src/fcsapi-chart.css">
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b0f14}
#fcs_chartparent{position:absolute;inset:0;width:100%;height:100%;background:#0b0f14}
#fcs_chart{width:100%;height:100%}
#boot{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#8b95a5;font:15px Arial;z-index:1;pointer-events:none;background:#0b0f14}
</style>
</head>
<body>
<div id="fcs_chartparent"><div id="fcs_chart"></div><div id="boot">Loading XAUUSD chart…</div></div>
<script src="https://cdn.jsdelivr.net/gh/fcsapi/chart-js/src/fcsapi-chart.js"></script>
<script src="chart.js"></script>
</body>
</html>
''')

p=Path('app/src/main/assets/fcs_chart/chart.js')
p.write_text(r'''(() => {
  "use strict";
  let chart=null, accessKey="", socketKey="", currentTf="15m", analysis=null, signal=null;
  const boot=document.getElementById('boot');
  function parse(v){if(!v)return null;if(typeof v==='string'){try{return JSON.parse(v)}catch(_){return null}}return v}
  function mapTf(tf){const x=String(tf||'15m');const m={'1m':'1m','5m':'5m','10m':'10m','15m':'15m','30m':'30m','1h':'1H','2h':'2H','4h':'4H','5h':'4H','1D':'1D','1d':'1D','1W':'1W','1w':'1W','1M':'1M'};return m[x]||'15m'}
  function showBoot(t){if(boot){boot.textContent=t;boot.style.display='flex'}}
  function hideBoot(){if(boot)boot.style.display='none'}
  function destroy(){if(chart){try{chart.destroy()}catch(_){}chart=null}}
  async function redrawLines(){
    if(!chart||typeof chart.clearHorizontalLines!=='function')return;
    try{chart.clearHorizontalLines()}catch(_){}
    const add=(price,color,label,style='dashed')=>{const n=Number(price);if(!Number.isFinite(n)||typeof chart.addHorizontalLine!=='function')return;try{chart.addHorizontalLine({price:n,color,label,style,lineWidth:1,textPosition:'above-left',textColor:color,textSize:10,id:'mh_'+label.toLowerCase().replace(/[^a-z0-9]+/g,'_')})}catch(_){}};
    if(analysis){
      add(analysis.support,'#42a5f5','SUPPORT'); add(analysis.resistance,'#ce93d8','RESISTANCE');
      add(analysis.bullObLow,'#26c6da','BULL OB L'); add(analysis.bullObHigh,'#26c6da','BULL OB H');
      add(analysis.bearObLow,'#ef5350','BEAR OB L'); add(analysis.bearObHigh,'#ef5350','BEAR OB H');
    }
    if(signal){add(signal.entry,'#f2c94c','ENTRY','solid');add(signal.sl,'#ff5a67','SL');add(signal.tp1,'#3ddc84','TP1');add(signal.tp2,'#56d7d1','TP2')}
  }
  function build(){
    if(!accessKey){showBoot('Analysis key required');return}
    if(!socketKey){showBoot('Live chart key required');return}
    if(typeof FCSAPIChart==='undefined'){showBoot('Chart library loading…');setTimeout(build,600);return}
    destroy();showBoot('Loading XAUUSD chart…');
    try{
      chart=new FCSAPIChart({
        container:document.getElementById('fcs_chart'), parentid:'fcs_chartparent',
        accessKey:accessKey, socketApiKey:socketKey,
        symbol:'FX:XAUUSD', period:mapTf(currentTf), length:600,
        enableSocket:true, enableCache:false, changeURL:false,
        displayMode:'chartonly', theme:'dark', defaultChartType:'candlestick', timezone:'+05:00',
        enableGrid:true, enableCrosshair:true, enableCrosshairLabels:true,
        enablePriceLine:true, enableAskBidLines:true, enableHighLowLabels:true,
        enableDrawingTools:false, enableContextMenu:false
      });
      window.__fcsChart=chart;
      setTimeout(()=>{hideBoot();redrawLines()},1800);
    }catch(e){console.error(e);showBoot('Chart connection unavailable')}
  }
  window.configureFcsChart=function(a,s,tf){
    const na=String(a||'').trim(), ns=String(s||'').trim(), nt=String(tf||currentTf);
    const changed=na!==accessKey||ns!==socketKey; accessKey=na;socketKey=ns;currentTf=nt;
    if(changed||!chart)build();else window.switchTimeframe(nt);
  };
  window.switchTimeframe=function(tf){currentTf=String(tf||'15m');if(chart&&typeof chart.setPeriod==='function'){try{chart.setPeriod(mapTf(currentTf));setTimeout(redrawLines,500)}catch(_){}}};
  window.setAnalysisLevels=function(raw){analysis=parse(raw);redrawLines()};
  window.clearAnalysisLevels=function(){analysis=null;redrawLines()};
  window.setSignalCard=function(raw){signal=parse(raw);redrawLines()};
  window.clearSignalCard=function(){signal=null;redrawLines()};
  // Compatibility hooks used by older Android code. Official FCS chart owns candles.
  window.setHistoricalCandles=function(_tf,_candles){};
  window.setChartData=function(_raw){}; window.clearChartData=function(){};
  window.updateLivePrice=function(_p,_t){}; window.onNativeCandle=function(_tf,_c){};
  window.setNativeConnectionState=function(_s){}; window.setFcsApiKey=function(_k){};
  window.loadTradingView=function(_symbol,tf){window.switchTimeframe(tf)};
  window.addEventListener('beforeunload',destroy);
})();
''')

# -----------------------------------------------------------------------------
# MainActivity: feed BOTH saved keys to the official chart. Do not start our
# custom native socket anymore. Analysis remains REST-driven.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
# v61 start becomes harmless; this prevents the custom handshake entirely.
s=re.sub(r'    private fun startNativeLive\(\)\{.*?\n    \}', '    private fun startNativeLive(){}', s, count=1, flags=re.S)

# Replace syncFcsChart completely so it initializes the official chart with both keys.
start=s.index('    private fun syncFcsChart(){')
end=s.index('\n    private fun ',start+10)
new_sync='''    private fun syncFcsChart(){
        if(!chartReady)return
        symbol="XAUUSD"
        val access=savedHistoryKey()
        val socket=savedSocketKey()
        chart.evaluateJavascript("window.configureFcsChart&&window.configureFcsChart(${JSONObject.quote(access)},${JSONObject.quote(socket)},${JSONObject.quote(period)})",null)
        val data=FcsClient.peek("XAUUSD",period,300)
        if(!data.isNullOrEmpty())pushChartLevels(data)
        showSignalCard(SignalStore.loadActive(this,"XAUUSD",period))
    }
'''
s=s[:start]+new_sync+s[end:]

# Saving either key immediately rebuilds/syncs official chart.
if 'private fun saveSocketKey()' in s:
    st=s.index('    private fun saveSocketKey(){');en=s.index('\n\n',st);seg=s[st:en]
    seg=seg.replace('startNativeLive();syncFcsChart()','syncFcsChart()').replace('startNativeLive();','')
    s=s[:st]+seg+s[en:]

# Remove any visible native connection-state injection left by v61.
s=re.sub(r'\n\s*chart\.evaluateJavascript\("window\.setNativeConnectionState[^\n]+','',s)

p.write_text(s)

# -----------------------------------------------------------------------------
# Overlay: official chart owns live socket. No native socket start.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('LiveSocketHub.addListener(this);val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k);','')
# Replace loadChart with official dual-key configuration.
if '    private fun loadChart(){' in s:
    st=s.index('    private fun loadChart(){');en=s.index('\n    private fun ',st+10)
    load='''    private fun loadChart(){
        val w=chart?:return
        val access=prefs.getString("api_key","")?.trim().orEmpty()
        val socket=prefs.getString("socket_api_key","")?.trim().orEmpty()
        w.evaluateJavascript("window.configureFcsChart&&window.configureFcsChart(${JSONObject.quote(access)},${JSONObject.quote(socket)},${JSONObject.quote(period)})",null)
        showOverlayGuidesFromCache();overlay(SignalStore.displayState(this,"XAUUSD",period))
    }
'''
    s=s[:st]+load+s[en:]
p.write_text(s)

# -----------------------------------------------------------------------------
# AlarmService: disable the broken custom socket path. Existing REST fallback
# remains active for lifecycle/background monitoring.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
s=re.sub(r'    private fun startLiveSocket\(\)\{.*?\n    \}', '    private fun startLiveSocket(){}', s, count=1, flags=re.S)
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 62',g);g=re.sub(r'versionName = "[^"]+"','versionName = "62.0"',g);p.write_text(g)
print('v62 official FCS Advanced Chart + official socket lifecycle applied')
