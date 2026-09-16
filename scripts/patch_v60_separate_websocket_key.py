from pathlib import Path
import re

# v60: FCS REST access key and WebSocket key are separate credentials.
# - Analysis/history keeps using api_key.
# - Live XAUUSD chart and native live background stream use socket_api_key.
# - Add a dedicated WebSocket key control to the existing main UI.
# - Keep XAUUSD-only v58/v59 architecture and all analysis/trading functions.

# -----------------------------------------------------------------------------
# MainActivityV29: separate WebSocket key UI + live chart credential.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

field_anchor='''    private lateinit var historyButton:Button\n'''
if 'private lateinit var socketInput:EditText' not in s:
    if field_anchor not in s: raise SystemExit('v60 MainActivity field anchor missing')
    s=s.replace(field_anchor,field_anchor+'''    private lateinit var socketStatus:TextView\n    private lateinit var socketInput:EditText\n    private lateinit var socketButton:Button\n''',1)

if 'private var editSocket=false' not in s:
    s=s.replace('    private var editHistory=false\n','    private var editHistory=false\n    private var editSocket=false\n',1)

# Insert a dedicated live-chart key card immediately after the analysis key card.
key_card='''        historyButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{saveHistoryKey()}};keyCard.addView(historyButton,lp46(8));updateKeyUi();root.addView(keyCard,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(12)})\n'''
if 'Enter WebSocket key for live XAUUSD chart' not in s:
    if key_card not in s: raise SystemExit('v60 key card anchor missing')
    live_card='''\n        val socketCard=card();socketStatus=txt("",12f,true,Color.LTGRAY);socketCard.addView(socketStatus)\n        socketInput=input("Enter WebSocket key for live XAUUSD chart").apply{inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD};socketCard.addView(socketInput,lp48(7))\n        socketButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{saveSocketKey()}};socketCard.addView(socketButton,lp46(8));updateSocketKeyUi();root.addView(socketCard,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(8)})\n'''
    s=s.replace(key_card,key_card+live_card,1)

# The embedded live chart must receive only the WebSocket key, never the REST access key.
s=s.replace('''        val k=savedHistoryKey()\n        if(k.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)''',
'''        val k=savedSocketKey()\n        if(k.isNotBlank())chart.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)\n        else chart.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)''')

# Add socket-key persistence controls before the existing analysis-key helpers.
helper_anchor='''    private fun savedHistoryKey()=prefs.getString("api_key","")?.trim().orEmpty()'''
if 'private fun savedSocketKey()' not in s:
    if helper_anchor not in s: raise SystemExit('v60 savedHistoryKey anchor missing')
    helpers='''    private fun savedSocketKey()=prefs.getString("socket_api_key","")?.trim().orEmpty()\n    private fun updateSocketKeyUi(){\n        val h=savedSocketKey().isNotBlank()\n        socketInput.visibility=if(h&&!editSocket)View.GONE else View.VISIBLE\n        socketStatus.text=if(h&&!editSocket)"● LIVE CHART KEY SAVED" else "LIVE XAUUSD WEBSOCKET KEY"\n        socketButton.text=if(h&&!editSocket)"UPDATE LIVE CHART KEY" else "SAVE LIVE CHART KEY"\n    }\n    private fun saveSocketKey(){\n        if(savedSocketKey().isNotBlank()&&!editSocket){editSocket=true;updateSocketKeyUi();return}\n        val x=socketInput.text.toString().trim();if(x.isBlank())return\n        prefs.edit().putString("socket_api_key",x).apply()\n        editSocket=false;socketInput.setText("");updateSocketKeyUi();syncFcsChart()\n        Toast.makeText(this,"Live chart key saved",Toast.LENGTH_SHORT).show()\n        startMonitorIfNeeded()\n    }\n\n'''
    s=s.replace(helper_anchor,helpers+helper_anchor,1)

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating chart: live chart gets socket_api_key; ANALYZE continues using api_key.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
# v58 loadChart uses api_key for chart connection. Change only that compact block.
s=s.replace('''        val k=prefs.getString("api_key","")?.trim().orEmpty()\n        if(k.isNotBlank())w.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)\n        showOverlayGuidesFromCache();overlay(SignalStore.displayState(this,"XAUUSD",period))''',
'''        val k=prefs.getString("socket_api_key","")?.trim().orEmpty()\n        if(k.isNotBlank())w.evaluateJavascript("window.setFcsApiKey(${JSONObject.quote(k)})",null)\n        else w.evaluateJavascript("window.setLiveKeyRequired&&window.setLiveKeyRequired()",null)\n        showOverlayGuidesFromCache();overlay(SignalStore.displayState(this,"XAUUSD",period))''')
p.write_text(s)

# -----------------------------------------------------------------------------
# AlarmService: native continuous live stream uses WebSocket key only.
# REST fallback/analysis still uses api_key in tick/poll functions.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
s=s.replace('''    private fun startLiveSocket(){\n        val key=prefs.getString("api_key","")?.trim().orEmpty()\n        if(key.isNotBlank())LiveSocketHub.start(this,key)\n    }''',
'''    private fun startLiveSocket(){\n        val key=prefs.getString("socket_api_key","")?.trim().orEmpty()\n        if(key.isNotBlank())LiveSocketHub.start(this,key)\n    }''')
p.write_text(s)

# -----------------------------------------------------------------------------
# Embedded FCS chart: explicit neutral state when the separate live key is absent.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/fcs_chart/chart.js')
s=p.read_text()
anchor='''  window.setFcsApiKey=function(key){if(!key||typeof key!=="string"){setStatus("Live data waiting","error");return}const k=key.trim();if(!k)return;if(apiKey===k&&client)return;apiKey=k;connect()};'''
if 'window.setLiveKeyRequired' not in s:
    if anchor not in s: raise SystemExit('v60 chart setFcsApiKey anchor missing')
    s=s.replace(anchor,anchor+'\n  window.setLiveKeyRequired=function(){disconnect();apiKey=null;setStatus("LIVE CHART KEY REQUIRED","disconnected")};',1)
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 60',g);g=re.sub(r'versionName = "[^"]+"','versionName = "60.0"',g);p.write_text(g)
print('v60 separate REST access key + WebSocket live chart key applied')
