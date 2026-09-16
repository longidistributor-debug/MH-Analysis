from pathlib import Path
import re

# v48: provider/freshness correctness.
# - Match Gold analysis to the same OANDA source shown in TradingView (ONA:XAUUSD).
# - On every forced ANALYZE/RE-EVALUATE, refresh the active candle from FCS latest
#   before calculations. If fresh verification cannot be obtained, fail closed.
# - Expose feed/freshness metadata in the snapshot.
# - Keep real TradingView visual chart and manual signal workflow unchanged.

# -----------------------------------------------------------------------------
# FcsClient
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Expose cache age / source label for UI diagnostics.
anchor='''    @Synchronized fun hasUsableHistory(symbol:String,period:String,min:Int=100)=\n        (cache[cacheKey(symbol,period)]?.candles?.size?:0)>=min\n'''
if 'fun cacheAgeMs(' not in s:
    helper='''    @Synchronized fun hasUsableHistory(symbol:String,period:String,min:Int=100)=\n        (cache[cacheKey(symbol,period)]?.candles?.size?:0)>=min\n\n    @Synchronized fun cacheAgeMs(symbol:String,period:String):Long?=\n        cache[cacheKey(symbol,period)]?.let{(System.currentTimeMillis()-it.at).coerceAtLeast(0L)}\n\n    @Synchronized fun cachedClose(symbol:String,period:String):Double?=\n        cache[cacheKey(symbol,period)]?.candles?.lastOrNull()?.c\n\n    fun feedLabel(symbol:String)=when(symbol.uppercase()){\n        "XAUUSD"->"OANDA via FCS (ONA:XAUUSD)"\n        "BTCUSDT"->"BINANCE via FCS"\n        else->"FCS selected provider"\n    }\n'''
    if anchor not in s: raise SystemExit('v48 FcsClient hasUsableHistory anchor not found')
    s=s.replace(anchor,helper,1)

# Provider-match historical Gold to OANDA instead of generic aggregated XAUUSD.
s=s.replace('''            "XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")''',
            '''            "XAUUSD"->fetch("forex",key,"ONA:XAUUSD",period,length,"commodity");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")''',1)

# Helpers for fresh active candle.
insert_before='''    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{'''
if 'private fun fetchLatestCandle(' not in s:
    helpers='''    private fun periodSeconds(period:String):Long=when(normalizePeriod(period)){\n        "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;"1h"->3600L;\n        "2h"->7200L;"4h"->14400L;"5h"->18000L;"1d"->86400L;"1w"->604800L;"1M"->2592000L;else->900L\n    }\n\n    private fun latestEndpoint(symbol:String,key:String,period:String):String{\n        val p=normalizePeriod(period)\n        return when(symbol.uppercase()){\n            "XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("ONA:XAUUSD")}&period=${enc(p)}&type=commodity&access_key=${enc(key)}"\n            else->"https://api-v4.fcsapi.com/crypto/latest?symbol=${enc("BINANCE:BTCUSDT")}&period=${enc(p)}&access_key=${enc(key)}"\n        }\n    }\n\n    private fun fetchLatestCandle(symbol:String,key:String,period:String):Pair<Candle,Int>{\n        val u=latestEndpoint(symbol,key,period)\n        val c=URL(u).openConnection() as HttpURLConnection;c.connectTimeout=12000;c.readTimeout=22000;c.requestMethod="GET"\n        val code=c.responseCode;val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}\n        if(code !in 200..299)throw IllegalStateException("Latest market data HTTP $code")\n        val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Latest market data request failed"))\n        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1\n        val response=root.opt("response")?:root.opt("data")?:throw IllegalStateException("Latest market response missing")\n        val item:JSONObject=when(response){\n            is JSONArray->response.optJSONObject(0)\n            is JSONObject->{\n                if(response.has("active")||response.has("c"))response\n                else{val it=response.keys();var found:JSONObject?=null;while(it.hasNext()&&found==null){found=response.optJSONObject(it.next())};found}\n            }\n            else->null\n        }?:throw IllegalStateException("Latest market candle unavailable")\n        val a=item.optJSONObject("active")?:item\n        val close=a.optDouble("c",Double.NaN);if(close.isNaN())throw IllegalStateException("Latest market price unavailable")\n        var t=a.optLong("t",item.optLong("t",0L));if(t<=0L){val sec=periodSeconds(period);val now=System.currentTimeMillis()/1000L;t=(now/sec)*sec}\n        val o=a.optDouble("o",close);val h=a.optDouble("h",close);val l=a.optDouble("l",close);val v=a.optDouble("v",0.0)\n        return Candle(normalizeTs(t),o,h,l,close,v) to credits\n    }\n\n    private fun mergeFresh(symbol:String,period:String,x:Candle){\n        val tf=normalizePeriod(period);val key=cacheKey(symbol,tf);val old=cache[key]?.candles?.toMutableList()?:mutableListOf()\n        val t=normalizeTs(x.t);val y=x.copy(t=t)\n        if(old.isNotEmpty()&&normalizeTs(old.last().t)==t)old[old.lastIndex]=y\n        else{old+=y;if(old.size>12000)repeat(old.size-12000){old.removeAt(0)}}\n        putCache(symbol,tf,old,true)\n    }\n\n'''
    if insert_before not in s: raise SystemExit('v48 fetchMarket anchor not found')
    s=s.replace(insert_before,helpers+insert_before,1)

# Replace seedForPeriod with freshness-aware implementation. Native timeframes use exact
# latest active candle; 10m refreshes native 5m then aggregates to 10m.
start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{\n        val sym=symbol.uppercase();val tf=normalizePeriod(period)\n        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()\n        var credits=0\n\n        fun fetchHistory(sourceTf:String,length:Int):List<Candle>{\n            if(!canRequestNow())throw IllegalStateException("Fresh history request limit reached. Wait briefly and analyze again.")\n            val out=try{fetchMarket(sym,accessKey,sourceTf,length)}catch(e:Exception){noteRequest();throw e}\n            noteRequest();credits+=out.second\n            return out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}\n        }\n        fun refreshLatest(sourceTf:String){\n            if(!canRequestNow())throw IllegalStateException("Fresh current-price verification is temporarily rate-limited. No signal was created from stale data.")\n            val out=try{fetchLatestCandle(sym,accessKey,sourceTf)}catch(e:Exception){noteRequest();throw e}\n            noteRequest();credits+=out.second;mergeFresh(sym,sourceTf,out.first)\n        }\n\n        // With an existing selected-timeframe cache, a forced ANALYZE does not waste\n        // another full-history call: only the active/current candle is refreshed.\n        if(current.size>=100){\n            if(!force)return current.takeLast(220) to 0\n            if(tf=="10m"){\n                if((cache[cacheKey(sym,"5m")]?.candles?.size?:0)<100){val five=fetchHistory("5m",360);putCache(sym,"5m",five,true)}\n                refreshLatest("5m");val five=cache[cacheKey(sym,"5m")]?.candles.orEmpty();putCache(sym,"10m",aggregate(five,10),true)\n            }else refreshLatest(tf)\n            val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)\n            if(result.size<100)throw IllegalStateException("$sym $tf fresh candle set is incomplete")\n            return result to credits\n        }\n\n        // First use of a timeframe: fetch exact history, then verify/replace the active\n        // candle with the Latest endpoint before any signal calculation.\n        when(tf){\n            "10m"->{\n                val five=fetchHistory("5m",360);putCache(sym,"5m",five,true);refreshLatest("5m")\n                putCache(sym,"10m",aggregate(cache[cacheKey(sym,"5m")]?.candles.orEmpty(),10),true)\n            }\n            "1m","5m","15m","30m","1h","2h","4h","5h","1d","1w","1M"->{\n                val exact=fetchHistory(tf,300);putCache(sym,tf,exact,true);refreshLatest(tf)\n            }\n            else->throw IllegalStateException("Unsupported timeframe $tf")\n        }\n        val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)\n        if(result.size<100)throw IllegalStateException("$sym $tf does not yet have enough fresh selected-timeframe candles")\n        return result to credits\n    }'''
s=s[:start]+new_seed+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity snapshot: make the source/freshness visible to the user.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Insert feed diagnostics into MARKET MAP output.
old='''        out.append("\\nMARKET MAP • $period\\n")\n        if(lv==null){'''
new='''        out.append("\\nMARKET MAP • $period\\n")\n        val age=FcsClient.cacheAgeMs(symbol,period);val apiClose=basis?.lastOrNull()?.c\n        val ageText=age?.let{if(it<1000L)"now" else "${it/1000L}s ago"}?:"unknown"\n        out.append("➜ DATA: ${FcsClient.feedLabel(symbol)} • refreshed $ageText")\n        apiClose?.let{out.append(" • close ${price(it)}")};out.append("\\n")\n        if(lv==null){'''
if old not in s: raise SystemExit('v48 MainActivity market map anchor not found')
s=s.replace(old,new,1)

# Make data-unavailable wording explicit: do not imply a signal was calculated.
s=s.replace('''status.text="ANALYSIS DATA UNAVAILABLE\\n${e.message}"''','''status.text="ANALYSIS BLOCKED • FRESH MARKET DATA NOT VERIFIED\\n${e.message}"''')
s=s.replace('''status.text="RE-EVALUATION DATA UNAVAILABLE\\n${e.message}\\nThe saved signal was not auto-expired."''','''status.text="RE-EVALUATION BLOCKED • FRESH MARKET DATA NOT VERIFIED\\n${e.message}\\nThe saved signal was left unchanged."''')
p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView HTML: keep the genuine widget. Add OB native rectangles only when
# the Advanced Charts drawing API is genuinely exposed. Public iframe widget may
# not expose it; there is deliberately no drifting HTML overlay fallback.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
html=p.read_text()
if 'function obZone(' not in html:
    html=html.replace('''function hline(price,color,label,dashed){if(!chartApi||typeof chartApi.createShape!==\'function\'||!Number.isFinite(Number(price)))return;try{remember(chartApi.createShape({price:Number(price)},{shape:\'horizontal_line\',text:label,lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:color,linestyle:dashed?2:0,linewidth:1,showPrice:true,textcolor:color,fontsize:9}}))}catch(e){}}''',
'''function hline(price,color,label,dashed){if(!chartApi||typeof chartApi.createShape!=='function'||!Number.isFinite(Number(price)))return;try{remember(chartApi.createShape({price:Number(price)},{shape:'horizontal_line',text:label,lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:color,linestyle:dashed?2:0,linewidth:1,showPrice:true,textcolor:color,fontsize:9}}))}catch(e){}}\nfunction obZone(low,high,color,label){if(!chartApi||typeof chartApi.createMultipointShape!=='function'||!Number.isFinite(Number(low))||!Number.isFinite(Number(high)))return;try{const vr=typeof chartApi.getVisibleRange==='function'?chartApi.getVisibleRange():null;if(!vr||!vr.from||!vr.to)return;remember(chartApi.createMultipointShape([{time:vr.from,price:Number(low)},{time:vr.to,price:Number(high)}],{shape:'rectangle',text:label,lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:color,backgroundColor:color+'22',transparency:82,linewidth:1}}))}catch(e){}}''')
    html=html.replace('''function redraw(){removeShapes();if(!chartApi)return;if(analysis){hline(analysis.support,'#42a5f5','S',true);hline(analysis.resistance,'#ce93d8','R',true)}if(signal){hline(signal.entry,'#f2c94c','ENTRY',false);hline(signal.sl,'#ff5a67','SL',true);hline(signal.tp1,'#3ddc84','TP1',true);hline(signal.tp2,'#56d7d1','TP2',true)}}''',
'''function redraw(){removeShapes();if(!chartApi)return;if(analysis){hline(analysis.support,'#42a5f5','S',true);hline(analysis.resistance,'#ce93d8','R',true);obZone(analysis.bullObLow,analysis.bullObHigh,'#26a69a','BULL OB');obZone(analysis.bearObLow,analysis.bearObHigh,'#ef5350','BEAR OB')}if(signal){hline(signal.entry,'#f2c94c','ENTRY',false);hline(signal.sl,'#ff5a67','SL',true);hline(signal.tp1,'#3ddc84','TP1',true);hline(signal.tp2,'#56d7d1','TP2',true)}}''')
p.write_text(html)

# Version
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \\d+','versionCode = 48',s);s=re.sub(r'versionName = "[^"]+"','versionName = "48.0"',s);p.write_text(s)
print('v48 OANDA/FCS provider alignment + fresh active candle verification applied')
