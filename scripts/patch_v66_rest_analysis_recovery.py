from pathlib import Path
import re

# v66: stabilize the locked architecture:
# TradingView = visual live market only.
# FCS REST/cache = analysis, S/R, OB, Entry/SL/TP, signals.
# No websocket dependency for ANALYZE.
# Manual ANALYZE prefers a fresh REST replacement, but may use ONLY a recent
# selected-timeframe cache when REST is temporarily rate-limited/unavailable.

# -----------------------------------------------------------------------------
# FcsClient: restore the proven XAUUSD commodity + FX exchange REST contract and
# make force-refresh resilient without ever accepting stale cache.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
for old in ['mh_candle_cache_v64_rest_fx_clean','mh_candle_cache_v61_exact_fx','mh_candle_cache_v57_fx','mh_candle_cache_v55_oanda_exchange','mh_candle_cache_v53_oanda','mh_candle_cache_v22']:
    s=s.replace(old,'mh_candle_cache_v66_rest_fx_clean')

# Final history source: plain Gold ticker + commodity + FX provider filter.
start=s.index('    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{')
end=s.index('\n\n    private fun fetch(',start)
s=s[:start]+'''    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        if(symbol.uppercase()!="XAUUSD")throw IllegalArgumentException("Only XAUUSD is supported")
        return fetch("forex",key,"XAUUSD",period,length,"commodity","FX")
    }'''+s[end:]

# Replace selected-timeframe seed logic. A successful manual refresh REPLACES the
# cache. If REST is temporarily unavailable, only a RECENT cache may be analyzed.
start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())throw IllegalStateException("ANALYSIS ACCESS KEY REQUIRED")
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        if(sym!="XAUUSD")throw IllegalStateException("Only XAUUSD is supported")
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()

        fun stepSeconds():Long=when(tf){
            "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;"1h"->3600L;
            "2h"->7200L;"4h"->14400L;"5h"->18000L;"1d"->86400L;"1w"->604800L;else->900L
        }
        fun recent(data:List<Candle>):Boolean{
            if(data.size<60)return false
            val newest=normalizeTs(data.last().t)
            if(newest<=0L)return false
            val age=System.currentTimeMillis()/1000L-newest
            return age<=stepSeconds()*3L+300L
        }

        if(!force&&current.size>=100&&recent(current))return current.takeLast(300) to 0

        if(!canRequestNow()){
            if(recent(current))return current.takeLast(300) to 0
            throw IllegalStateException("MARKET DATA REFRESH BUSY")
        }

        return try{
            val out=fetchMarket(sym,cleanKey,tf,360)
            noteRequest()
            val fresh=out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
            if(fresh.size<60)throw IllegalStateException("FRESH $tf HISTORY INCOMPLETE")
            // Critical: selected timeframe is replaced, never merged with legacy rows.
            putCache(sym,tf,fresh,true)
            fresh.takeLast(300) to out.second
        }catch(e:Exception){
            noteRequest()
            // Cached FCS analysis is allowed only when that cache is still recent.
            if(recent(current)) current.takeLast(300) to 0 else throw e
        }
    }'''
s=s[:start]+new_seed+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Main UI: remove the old misleading syncing text. Keep every analysis/trading
# function intact; only failure copy changes when neither fresh nor recent cache
# is usable.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('LIVE DATA SYNCING • TRY ANALYZE AGAIN','MARKET DATA REFRESH FAILED • TRY ANALYZE AGAIN')
s=s.replace('FRESH MARKET DATA UNAVAILABLE • NO SIGNAL CREATED • TRY AGAIN','MARKET DATA REFRESH FAILED • NO SIGNAL CREATED • TRY AGAIN')
# One-time signal cleanup for this cache contract; does not touch history/settings.
anchor='        setContentView(buildUi())\n'
if 'v66_rest_analysis_migrated' not in s and anchor in s:
    s=s.replace(anchor,anchor+'''        if(!prefs.getBoolean("v66_rest_analysis_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD")
            prefs.edit().putBoolean("v66_rest_analysis_migrated",true).apply()
        }
''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Lock TradingView visual symbol to FX:XAUUSD. No analysis candles are injected.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
h=p.read_text()
h=h.replace("symbol:'OANDA:XAUUSD'","symbol:'FX:XAUUSD'")
h=h.replace('OANDA:XAUUSD','FX:XAUUSD')
p.write_text(h)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 66',g);g=re.sub(r'versionName = "[^"]+"','versionName = "66.0"',g);p.write_text(g)
print('v66 REST analysis recovery + recent-cache fallback applied')
