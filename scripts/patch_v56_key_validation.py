from pathlib import Path
import re

# v56: make FCS authentication deterministic and stop generic HTTP 400 loops.
# - Normalize pasted keys (raw key, full URL, access_key=..., Bearer ...).
# - Validate the key first against the simplest documented Gold latest endpoint.
# - Parse FCS JSON errors even when HTTP status is 400/401 and surface auth errors clearly.
# - Only after auth passes, continue with provider-specific OANDA history/latest requests.

p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Add key normalizer helper before fetchMarket if absent.
anchor='''    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{'''
if 'private fun normalizeAccessKey(' not in s:
    helper='''    private fun normalizeAccessKey(raw:String):String{\n        var x=raw.trim().trim('\\"','\\'')\n        if(x.startsWith("Bearer ",true))x=x.substringAfter(' ').trim()\n        val marker="access_key="\n        val i=x.indexOf(marker,ignoreCase=true)\n        if(i>=0){\n            x=x.substring(i+marker.length).substringBefore('&').substringBefore('#').trim()\n            x=runCatching{java.net.URLDecoder.decode(x,"UTF-8")}.getOrDefault(x)\n        }\n        return x.trim()\n    }\n\n    private fun fcsError(body:String,http:Int):IllegalStateException{\n        val root=runCatching{JSONObject(body)}.getOrNull()\n        val apiCode=root?.optInt("code",http)?:http\n        val msg=root?.optString("msg","")?.trim().orEmpty()\n        return when(apiCode){\n            101,401->IllegalStateException("FCS ACCESS KEY REJECTED — UPDATE ANALYSIS KEY")\n            102->IllegalStateException("FCS ACCOUNT INACTIVE / EXPIRED — UPDATE OR RENEW ANALYSIS KEY")\n            403->IllegalStateException("FCS KEY HAS NO PERMISSION FOR THIS MARKET DATA")\n            429->IllegalStateException("FCS RATE LIMIT REACHED — WAIT AND ANALYZE AGAIN")\n            else->IllegalStateException("FCS MARKET DATA ERROR $apiCode${if(msg.isNotBlank())" • $msg" else ""}")\n        }\n    }\n\n    private fun validateAccessKey(rawKey:String){\n        val key=normalizeAccessKey(rawKey)\n        if(key.isBlank())throw IllegalStateException("FCS ACCESS KEY MISSING — UPDATE ANALYSIS KEY")\n        val u="https://api-v4.fcsapi.com/forex/latest?symbol=XAUUSD&type=commodity&access_key=${enc(key)}"\n        val c=URL(u).openConnection() as HttpURLConnection\n        c.connectTimeout=12000;c.readTimeout=18000;c.requestMethod="GET"\n        val code=c.responseCode\n        val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}\n        val root=runCatching{JSONObject(body)}.getOrNull()\n        if(code !in 200..299)throw fcsError(body,code)\n        if(root!=null && root.has("status") && !root.optBoolean("status",true))throw fcsError(body,root.optInt("code",code))\n    }\n\n'''
    if anchor not in s: raise SystemExit('v56 fetchMarket anchor not found')
    s=s.replace(anchor,helper+anchor,1)

# Normalize keys at seed entry and validate only for forced/manual refreshes so cached reads remain cheap.
start='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{\n        val sym=symbol.uppercase();val tf=normalizePeriod(period)'''
repl='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{\n        val cleanKey=normalizeAccessKey(accessKey)\n        if(force)validateAccessKey(cleanKey)\n        val sym=symbol.uppercase();val tf=normalizePeriod(period)'''
if start not in s: raise SystemExit('v56 seed anchor not found')
s=s.replace(start,repl,1)

# All fetches inside seed should use cleanKey, not the raw pasted string.
# Limit replacement to this function body region.
seed_start=s.index('    @Synchronized fun seedForPeriod(')
seed_end=s.index('\n\n    /** Best-effort background fill.',seed_start)
seg=s[seed_start:seed_end].replace('fetchMarket(sym,accessKey,','fetchMarket(sym,cleanKey,').replace('fetchLatestCandle(sym,accessKey,','fetchLatestCandle(sym,cleanKey,')
s=s[:seed_start]+seg+s[seed_end:]

# Make history/latest non-200 errors parse FCS JSON instead of dumping raw JSON.
s=s.replace('''if(code !in 200..299)throw IllegalStateException("Market data HTTP $code • ${body.take(180)}")''','''if(code !in 200..299)throw fcsError(body,code)''')
s=s.replace('''if(code !in 200..299)throw IllegalStateException("Latest market data HTTP $code • ${body.take(180)}")''','''if(code !in 200..299)throw fcsError(body,code)''')

# Also convert status:false responses to structured FCS errors in the two market request paths.
s=s.replace('''val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Latest market data request failed"))''','''val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw fcsError(body,root.optInt("code",code))''')
s=s.replace('''val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Market data request failed"))''','''val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw fcsError(body,root.optInt("code",code))''')

p.write_text(s)

# MainActivity: normalize common pasted formats when saving so future calls are clean.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
m=p.read_text()
old='''val x=historyInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();'''
new='''var x=historyInput.text.toString().trim().trim('\\"','\\'');if(x.startsWith("Bearer ",true))x=x.substringAfter(' ').trim();val mk="access_key=";val ki=x.indexOf(mk,ignoreCase=true);if(ki>=0)x=x.substring(ki+mk.length).substringBefore('&').substringBefore('#').trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();'''
if old not in m: raise SystemExit('v56 save key anchor not found')
m=m.replace(old,new,1)
p.write_text(m)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 56',g);g=re.sub(r'versionName = "[^"]+"','versionName = "56.0"',g);p.write_text(g)
print('v56 key normalization + validation applied')
