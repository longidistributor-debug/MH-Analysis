from pathlib import Path
import re

# v66: keep the locked architecture exactly as requested:
# - TradingView = visual live market view only.
# - FCS REST/cache = analysis/SR/OB/signals only.
# - No WebSocket dependency for ANALYZE.
# Fix the v65 ANALYZE failure by removing automatic history prefetch pressure,
# giving manual ANALYZE priority over the app's local request throttle, using a
# plan-safe 300-candle request, and preserving all existing indicator/video logic.

# -----------------------------------------------------------------------------
# MainActivity: TradingView must not trigger FCS history requests just to render.
# Also remove the old v59 stale-cache fallback UI that survived later patches.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# v61 injected ensureChartHistory() into the visible chart switch. With TradingView
# restored in v64 this call is unnecessary and can consume REST slots before ANALYZE.
s=re.sub(r'^\s*ensureChartHistory\(\)\s*$', '', s, flags=re.M)

# Keep the helper harmless in case another generated path still references it.
if '    private fun ensureChartHistory(){' in s:
    st=s.index('    private fun ensureChartHistory(){')
    en=s.index('\n    private fun ',st+10)
    s=s[:st]+'    private fun ensureChartHistory(){}\n'+s[en:]

# Robustly remove any old catch-path that analyzes a stale cache after a failed
# fresh manual request. Manual ANALYZE must either use the new REST response or
# create no new signal.
pattern=r'''\}\s*catch\(e:Exception\)\{runOnUiThread\{\s*busy=false\s*val live=FcsClient\.peek\("XAUUSD",reqPeriod,300\)\.orEmpty\(\)\s*if\(reqSymbol==symbol&&reqPeriod==period&&live\.size>=60\)\{.*?performAnalysis\(\)\s*\}\s*else\s*\{?\s*status\.text="LIVE DATA SYNCING • TRY ANALYZE AGAIN"\s*\}?\s*\}\}'''
replacement='''}catch(e:Exception){runOnUiThread{\n                busy=false\n                status.text="FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN"\n            }}'''
s,n=re.subn(pattern,replacement,s,count=1,flags=re.S)

# Fallback for compact/generated variants of the old message.
if 'LIVE DATA SYNCING • TRY ANALYZE AGAIN' in s:
    s=s.replace('LIVE DATA SYNCING • TRY ANALYZE AGAIN','FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN')

p.write_text(s)

# -----------------------------------------------------------------------------
# FcsClient: manual fresh history has priority and uses a plan-safe request size.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# New namespace so v66 never reads a partially-built/failed v64-v65 set.
for old in ['mh_candle_cache_v64_rest_fx_clean','mh_candle_cache_v61_exact_fx','mh_candle_cache_v57_fx']:
    s=s.replace(old,'mh_candle_cache_v66_rest_fx_clean')

# Make the Gold REST fetch robust: prefer the exact FX ticker, then fall back to
# the documented commodity + exchange filter. Both remain FCS REST; never OANDA.
start=s.index('    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{')
end=s.index('\n\n    private fun fetch(',start)
new_fetch='''    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        if(symbol.uppercase()!="XAUUSD")throw IllegalArgumentException("Only XAUUSD is supported")
        val safeLength=length.coerceIn(60,300)
        return try{
            fetch("forex",key,"FX:XAUUSD",period,safeLength,"","")
        }catch(primary:Exception){
            // Official FCS commodity form; useful when the account/plan does not
            // expose the exchange-qualified ticker on History.
            fetch("forex",key,"XAUUSD",period,safeLength,"commodity","FX")
        }
    }'''
s=s[:start]+new_fetch+s[end:]

# Replace v64 seedForPeriod with a manual-priority implementation.
start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())throw IllegalStateException("ANALYSIS ACCESS KEY REQUIRED")
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        if(sym!="XAUUSD")throw IllegalStateException("Only XAUUSD is supported")
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        if(current.size>=100&&!force)return current.takeLast(300) to 0

        // Local throttle protects background refreshes only. A user pressing
        // ANALYZE must not be blocked because an automatic preload used the slots.
        if(!force&&!canRequestNow()){
            if(current.size>=60)return current.takeLast(300) to 0
            throw IllegalStateException("ANALYSIS HISTORY TEMPORARILY BUSY")
        }

        fun clean(data:List<Candle>):List<Candle> = data
            .map{it.copy(t=normalizeTs(it.t))}
            .filter{it.t>0L&&it.o.isFinite()&&it.h.isFinite()&&it.l.isFinite()&&it.c.isFinite()}
            .distinctBy{it.t}
            .sortedBy{it.t}

        val fetched:Pair<List<Candle>,Int>
        try{
            fetched=when(tf){
                // FCS does not consistently expose every synthetic timeframe on
                // every plan. Preserve app support by aggregating from native bars.
                "10m"->{
                    val r=fetchMarket(sym,cleanKey,"5m",300)
                    aggregate(clean(r.first),10) to r.second
                }
                "5h"->{
                    val r=fetchMarket(sym,cleanKey,"1h",300)
                    aggregate(clean(r.first),300) to r.second
                }
                else->fetchMarket(sym,cleanKey,tf,300).let{clean(it.first) to it.second}
            }
            noteRequest()
        }catch(e:Exception){
            noteRequest();throw e
        }

        val fresh=clean(fetched.first)
        if(fresh.size<60)throw IllegalStateException("FRESH $tf HISTORY INCOMPLETE")

        val step=when(tf){
            "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;"1h"->3600L;
            "2h"->7200L;"4h"->14400L;"5h"->18000L;"1d"->86400L;"1w"->604800L;else->900L
        }
        val now=System.currentTimeMillis()/1000L
        val newest=fresh.last().t
        // History endpoints may return the running bar or the last closed bar.
        // Allow up to three selected-timeframe bars plus five minutes, then fail
        // closed rather than creating a signal from genuinely stale history.
        if(now-newest>step*3L+300L)throw IllegalStateException("FRESH $tf HISTORY IS STALE")

        // Critical: a successful manual fetch REPLACES the selected timeframe
        // cache. No append/merge with old provider data.
        putCache(sym,tf,fresh,true)
        return fresh.takeLast(300) to fetched.second
    }'''
s=s[:start]+new_seed+s[end:]

p.write_text(s)

# -----------------------------------------------------------------------------
# Do NOT modify AnalysisEngine.analyze or the video/indicator setup logic here.
# v64 S/R rule and every existing confirmation/setup remain intact.
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 66',g);g=re.sub(r'versionName = "[^"]+"','versionName = "66.0"',g);p.write_text(g)
print('v66 manual REST priority + TradingView visual-only fix applied')
