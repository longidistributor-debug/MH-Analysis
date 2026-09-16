from pathlib import Path
import re

# v59: one saved key silently powers both analysis and live XAUUSD chart.
# Remove all user-facing websocket/FCS error wording and allow ANALYZE to fall
# back to the live/native candle cache when a REST refresh fails.

# MainActivity
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('"socket_api_key"','"api_key"')
s=s.replace('FCS XAUUSD LIVE','XAUUSD LIVE').replace('FCS XAUUSD live','XAUUSD live')
s=s.replace('FCS XAUUSD live chart remains connected.','Live XAUUSD chart remains connected.')
s=s.replace('TradingView live chart is unaffected.','')
s=s.replace('Market data HTTP','Data HTTP')
s=s.replace('MARKET DATA CONNECTION UNAVAILABLE','LIVE DATA SYNCING')
s=s.replace('ANALYSIS DATA UNAVAILABLE','ANALYSIS SYNCING')

# Replace analyze failure UI with cache fallback.
old='''            }catch(e:Exception){runOnUiThread{busy=false;status.text="ANALYSIS DATA UNAVAILABLE\\n${e.message}\\nFCS XAUUSD live chart remains connected."}}'''
if old not in s:
    old='''            }catch(e:Exception){runOnUiThread{busy=false;status.text="ANALYSIS DATA UNAVAILABLE\\n${e.message}\\nLive XAUUSD chart remains connected."}}'''
new='''            }catch(e:Exception){runOnUiThread{
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
if old in s:
    s=s.replace(old,new,1)
else:
    # generic regex fallback for the catch block immediately after seedForPeriod
    s=re.sub(r'''\}\s*catch\(e:Exception\)\{runOnUiThread\{busy=false;status\.text="[^"]*"\}\}''',
             '}catch(e:Exception){runOnUiThread{busy=false;val live=FcsClient.peek("XAUUSD",reqPeriod,300).orEmpty();if(reqSymbol==symbol&&reqPeriod==period&&live.size>=60){candles=live;status.text="ANALYZING LIVE $reqPeriod STRUCTURE…";performAnalysis()}else status.text="LIVE DATA SYNCING • TRY ANALYZE AGAIN"}}',s,count=1)
p.write_text(s)

# Overlay: same saved key only, no socket-specific pref/text.
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text().replace('"socket_api_key"','"api_key"')
s=s.replace('FCS XAUUSD LIVE','XAUUSD LIVE').replace('FCS XAUUSD live','XAUUSD live')
s=s.replace('Analysis unavailable: ${e.message}','Live data syncing • try again')
p.write_text(s)

# Alarm/background service: never look for a second socket key.
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text().replace('"socket_api_key"','"api_key"')
p.write_text(s)

# LiveSocketHub: keep functionality, remove websocket/FCS terminology from all states.
p=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
s=p.read_text()
repls={
'LIVE WEBSOCKET KEY REQUIRED':'LIVE DATA WAITING',
'LIVE STREAM OFF':'LIVE DATA OFF',
'LIVE STREAM CONNECTING':'LIVE DATA CONNECTING',
'LIVE SOCKET OPEN • WAITING FOR FCS WELCOME':'LIVE DATA CONNECTING',
'LIVE STREAM CONNECTED • JOINING FEEDS':'LIVE DATA READY',
'LIVE STREAM CONNECTED •':'LIVE DATA READY •',
'LIVE FEED ERROR •':'LIVE DATA RETRYING •',
'LIVE CONNECTION FAILED':'LIVE DATA RETRYING',
'LIVE DISCONNECTED':'LIVE DATA RETRYING',
'FCS REJECTED LIVE KEY / SOCKET SUBSCRIPTION':'LIVE DATA AUTH RETRY REQUIRED',
'FCS WEBSOCKET ENDPOINT RETURNED HTTP 404':'LIVE DATA ENDPOINT UNAVAILABLE',
'LIVE STREAM RECONNECTING':'LIVE DATA RECONNECTING'
}
for a,b in repls.items(): s=s.replace(a,b)
p.write_text(s)

# Embedded chart JS: no key/socket/FCS wording. The app injects the saved analysis key silently.
p=Path('app/src/main/assets/fcs_chart/chart.js')
s=p.read_text()
s=s.replace('API key required','Live data waiting')
s=s.replace('FCS library failed','Live data library unavailable')
s=s.replace('LIVE • FX:XAUUSD','LIVE • XAUUSD')
s=s.replace('Socket reconnecting','Live data reconnecting')
s=s.replace('Market stream error','Live data retrying')
s=s.replace('Connection failed','Live data reconnecting')
p.write_text(s)

# Embedded chart HTML text cleanup.
p=Path('app/src/main/assets/fcs_chart/index.html')
s=p.read_text().replace('<title>FCS XAUUSD Live Chart</title>','<title>XAUUSD Live Chart</title>')
s=s.replace('Waiting for XAUUSD live/history candles…','Loading XAUUSD candles…')
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 59',g);g=re.sub(r'versionName = "[^"]+"','versionName = "59.0"',g);p.write_text(g)
print('v59 silent single-key live fallback applied')
