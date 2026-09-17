from pathlib import Path
import re

# v70:
# - Fix v69 Kotlin duplicate rr1/rr2 compile regression.
# - Keep v69 SL/TP geometry + exact reasons.
# - Make manual ANALYZE resilient to a temporary history request failure without
#   ever falling back to genuinely stale candles.
# - TradingView remains visual-only; backend/provider wording stays private.

# -----------------------------------------------------------------------------
# AnalysisEngine: v69 introduced local rr1/rr2 names that conflict with existing
# downstream setup-quality variables. Rename only inside the v69 sizing block.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
if '        val reward1=abs(tp1-entry);val reward2=abs(tp2-entry)' in s:
    st=s.index('        val reward1=abs(tp1-entry);val reward2=abs(tp2-entry)')
    en=s.index('\n        val familyName=',st)
    block=s[st:en]
    block=block.replace('val rr1=','val levelRr1=').replace('val rr2=','val levelRr2=')
    block=block.replace('rr1<.45','levelRr1<.45').replace('rr2<.90','levelRr2<.90')
    block=block.replace('${two(rr1)}R','${two(levelRr1)}R').replace('${two(rr2)}R','${two(levelRr2)}R')
    s=s[:st]+block+s[en:]
p.write_text(s)

# -----------------------------------------------------------------------------
# FcsClient: manual fresh history with one retry + strict recent-cache fallback.
# A request/network hiccup should not block analysis when the selected timeframe
# cache is still within the same fresh market window. Old cache remains forbidden.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())throw IllegalStateException("ANALYSIS KEY REQUIRED")
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        if(sym!="XAUUSD")throw IllegalStateException("Only XAUUSD is supported")
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()

        fun clean(data:List<Candle>):List<Candle> = data
            .map{it.copy(t=normalizeTs(it.t))}
            .filter{it.t>0L&&it.o.isFinite()&&it.h.isFinite()&&it.l.isFinite()&&it.c.isFinite()}
            .distinctBy{it.t}
            .sortedBy{it.t}

        fun stepSeconds():Long=when(tf){
            "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;"1h"->3600L;
            "2h"->7200L;"4h"->14400L;"5h"->18000L;"1d"->86400L;"1w"->604800L;else->900L
        }
        fun isRecent(data:List<Candle>):Boolean{
            val x=clean(data);if(x.size<100)return false
            val age=(System.currentTimeMillis()/1000L-x.last().t).coerceAtLeast(0L)
            // History may end on the active bar or the last completed bar.
            // Three bars + 5 minutes is the hard maximum for a fallback.
            return age<=stepSeconds()*3L+300L
        }

        if(current.size>=100&&!force)return current.takeLast(300) to 0
        if(!force&&!canRequestNow()){
            if(isRecent(current))return clean(current).takeLast(300) to 0
            throw IllegalStateException("MARKET HISTORY TEMPORARILY BUSY")
        }

        fun request(length:Int):Pair<List<Candle>,Int>{
            return when(tf){
                "10m"->{
                    val r=fetchMarket(sym,cleanKey,"5m",length)
                    aggregate(clean(r.first),10) to r.second
                }
                "5h"->{
                    val r=fetchMarket(sym,cleanKey,"1h",length)
                    aggregate(clean(r.first),300) to r.second
                }
                else->fetchMarket(sym,cleanKey,tf,length).let{clean(it.first) to it.second}
            }
        }

        var lastError:Exception?=null
        var fetched:Pair<List<Candle>,Int>?=null
        // First request is intentionally smaller than the old 300-bar call: 180
        // is still ample for the 100-bar analysis minimum and is less fragile.
        for((idx,len) in listOf(180,120).withIndex()){
            try{
                val r=request(len);noteRequest()
                val rows=clean(r.first)
                if(rows.size>=100&&isRecent(rows)){fetched=rows to r.second;break}
                lastError=IllegalStateException(if(rows.size<100)"CURRENT HISTORY INCOMPLETE" else "CURRENT HISTORY NOT RECENT")
            }catch(e:Exception){
                noteRequest();lastError=e
            }
            if(idx==0)try{Thread.sleep(350L)}catch(_:Exception){}
        }

        if(fetched==null){
            // Crucial safety rule: temporary request failure may reuse only a
            // recently successful selected-timeframe cache. Never analyze stale data.
            if(isRecent(current))return clean(current).takeLast(300) to 0
            throw (lastError?:IllegalStateException("CURRENT MARKET HISTORY UNAVAILABLE"))
        }

        val fresh=clean(fetched!!.first)
        putCache(sym,tf,fresh,true) // successful manual fetch replaces old series
        return fresh.takeLast(300) to fetched!!.second
    }'''
s=s[:start]+new_seed+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: keep public error wording neutral/private. The underlying error is
# intentionally not printed to end users.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN','MARKET HISTORY TEMPORARILY UNAVAILABLE • TRY AGAIN')
s=s.replace('FRESH DATA ANALYSIS UNAVAILABLE','MARKET HISTORY TEMPORARILY UNAVAILABLE')
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 70',g);g=re.sub(r'versionName = "[^"]+"','versionName = "70.0"',g);p.write_text(g)
print('v70 compile fix + strict fresh-analysis fallback applied')
