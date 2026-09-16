from pathlib import Path
import re

# v53: feed integrity first, then dynamic selected-timeframe S/R.
# 1) Discard legacy generic-XAUUSD disk history by moving to a fresh provider-specific cache namespace.
# 2) Validate FCS latest by its real `update` timestamp and OANDA provider identity.
# 3) If the app missed multiple candles, refetch exact selected-timeframe history instead of appending one candle to an old series.
# 4) Replace broad min/max S/R with closed-candle timeframe-specific pivot/cluster structure.
#    The running candle may invalidate/role-reverse a level immediately, but cannot create a confirmed pivot by itself.
# 5) No hard-coded user-spoken price levels.

# -----------------------------------------------------------------------------
# FCS client: fresh provider-specific cache + quote freshness + gap recovery.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Old builds persisted generic XAUUSD candles here. Never mix them with OANDA candles.
s=s.replace('mh_candle_cache_v22','mh_candle_cache_v53_oanda')

# Replace v48 latest-candle parser with a fail-closed freshness/provider check.
start=s.index('    private fun fetchLatestCandle(symbol:String,key:String,period:String):Pair<Candle,Int>{')
end=s.index('\n\n    private fun mergeFresh',start)
new_latest='''    private fun fetchLatestCandle(symbol:String,key:String,period:String):Pair<Candle,Int>{
        val u=latestEndpoint(symbol,key,period)
        val c=URL(u).openConnection() as HttpURLConnection;c.connectTimeout=12000;c.readTimeout=22000;c.requestMethod="GET"
        val code=c.responseCode;val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}
        if(code !in 200..299)throw IllegalStateException("Latest market data HTTP $code")
        val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Latest market data request failed"))
        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1
        val response=root.opt("response")?:root.opt("data")?:throw IllegalStateException("Latest market response missing")
        val item:JSONObject=when(response){
            is JSONArray->response.optJSONObject(0)
            is JSONObject->{
                if(response.has("active")||response.has("c"))response
                else{val it=response.keys();var found:JSONObject?=null;while(it.hasNext()&&found==null){found=response.optJSONObject(it.next())};found}
            }
            else->null
        }?:throw IllegalStateException("Latest market candle unavailable")
        val a=item.optJSONObject("active")?:item
        val close=a.optDouble("c",Double.NaN);if(close.isNaN())throw IllegalStateException("Latest market price unavailable")

        // FCS `t` is candle-open time. `update` is the actual last price-update time.
        // Validate `update`, otherwise a stale REST quote can be mistaken for a fresh active candle.
        val nowSec=System.currentTimeMillis()/1000L
        val updateRaw=item.optLong("update",a.optLong("update",0L))
        if(symbol.uppercase()=="XAUUSD"){
            if(updateRaw<=0L)throw IllegalStateException("Gold quote freshness could not be verified. No signal was created.")
            val quoteAge=(nowSec-normalizeTs(updateRaw)).coerceAtLeast(0L)
            if(quoteAge>120L)throw IllegalStateException("Gold quote is stale (${quoteAge}s old). No signal was created from delayed market data.")
            val ticker=item.optString("ticker","").uppercase()
            val exchange=item.optJSONObject("profile")?.optString("exchange","")?.uppercase().orEmpty()
            if(ticker.isNotBlank()&&!ticker.startsWith("ONA:")&&exchange.isNotBlank()&&exchange!="ONA")
                throw IllegalStateException("Gold provider mismatch detected. OANDA data was required; signal blocked.")
        }

        var t=a.optLong("t",item.optLong("t",0L));if(t<=0L){val sec=periodSeconds(period);t=(nowSec/sec)*sec}
        val o=a.optDouble("o",close);val h=a.optDouble("h",close);val l=a.optDouble("l",close);val v=a.optDouble("v",0.0)
        return Candle(normalizeTs(t),o,h,l,close,v) to credits
    }'''
s=s[:start]+new_latest+s[end:]

# Replace v48 seedForPeriod: on force, rebuild exact history whenever the cached series
# is more than one selected-timeframe candle behind. This prevents giant holes after sleep/app close.
start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        var credits=0

        fun fetchHistory(sourceTf:String,length:Int):List<Candle>{
            if(!canRequestNow())throw IllegalStateException("Fresh history request limit reached. Wait briefly and analyze again.")
            val out=try{fetchMarket(sym,accessKey,sourceTf,length)}catch(e:Exception){noteRequest();throw e}
            noteRequest();credits+=out.second
            return out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
        }
        fun refreshLatest(sourceTf:String){
            if(!canRequestNow())throw IllegalStateException("Fresh current-price verification is temporarily rate-limited. No signal was created from stale data.")
            val out=try{fetchLatestCandle(sym,accessKey,sourceTf)}catch(e:Exception){noteRequest();throw e}
            noteRequest();credits+=out.second;mergeFresh(sym,sourceTf,out.first)
        }
        fun cacheHasGap(sourceTf:String):Boolean{
            val src=cache[cacheKey(sym,sourceTf)]?.candles.orEmpty();if(src.isEmpty())return true
            val step=periodSeconds(sourceTf);val now=System.currentTimeMillis()/1000L
            return now-normalizeTs(src.last().t)>step*2L
        }

        if(current.size>=100&&!force)return current.takeLast(220) to 0

        if(tf=="10m"){
            val source="5m"
            val needFull=(cache[cacheKey(sym,source)]?.candles?.size?:0)<100||cacheHasGap(source)
            if(needFull){val five=fetchHistory(source,420);putCache(sym,source,five,true)}
            refreshLatest(source)
            val five=cache[cacheKey(sym,source)]?.candles.orEmpty();putCache(sym,"10m",aggregate(five,10),true)
        }else if(tf in listOf("1m","5m","15m","30m","1h","2h","4h","5h","1d","1w","1M")){
            val needFull=current.size<100||cacheHasGap(tf)
            if(needFull){val exact=fetchHistory(tf,360);putCache(sym,tf,exact,true)}
            refreshLatest(tf)
        }else throw IllegalStateException("Unsupported timeframe $tf")

        val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)
        if(result.size<100)throw IllegalStateException("$sym $tf fresh candle set is incomplete")
        return result to credits
    }'''
s=s[:start]+new_seed+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Analysis engine: closed-candle confirmed pivots, but live invalidation/role reversal.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
start=s.index('    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{')
end=s.index('\n\n    fun chartLevels',start)
new_levels='''    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{
        if(c.size<31)return null
        val tf=tfMinutes(timeframe);val closed=c.dropLast(1);if(closed.size<24)return null
        val current=c.last().c;val a=atr(c,14).coerceAtLeast(1e-9)
        val look=when{
            tf<=1->110;tf<=5->92;tf<=10->82;tf<=15->72;tf<=30->62;tf<=60->54;
            tf<=120->48;tf<=300->42;tf<=1440->36;tf<=10080->30;else->26
        }
        val span=when{tf<=5->2;tf<=30->3;tf<=120->3;tf<=300->2;else->2}
        val w=closed.takeLast(min(look,closed.size));if(w.size<span*2+6)return null
        val lows=mutableListOf<Pair<Double,Int>>();val highs=mutableListOf<Pair<Double,Int>>()
        for(i in span until w.size-span){
            val x=w[i]
            var lo=true;var hi=true
            for(j in 1..span){if(x.l>w[i-j].l||x.l>w[i+j].l)lo=false;if(x.h<w[i-j].h||x.h<w[i+j].h)hi=false}
            if(lo)lows+=x.l to i;if(hi)highs+=x.h to i
        }
        // The most recently CLOSED candle can be a confirmed reaction level when it
        // makes a fresh local extreme. The running candle confirms/invalidates it; it
        // never becomes the pivot source itself.
        val last=w.last();val prev=w.dropLast(1).takeLast(max(5,span*3))
        if(prev.isNotEmpty()){
            if(last.l<=prev.minOf{it.l})lows+=last.l to w.lastIndex
            if(last.h>=prev.maxOf{it.h})highs+=last.h to w.lastIndex
        }
        val tol=max(a*.16,abs(current)*0.000025);val minGap=max(a*.035,abs(current)*0.000005)
        fun clustered(src:List<Pair<Double,Int>>):List<Triple<Double,Int,Int>>{
            if(src.isEmpty())return emptyList()
            val groups=mutableListOf<MutableList<Pair<Double,Int>>>()
            for(pt in src.sortedBy{it.first}){
                val g=groups.lastOrNull();val center=g?.map{it.first}?.average()
                if(g!=null&&center!=null&&abs(center-pt.first)<=tol)g+=pt else groups+=mutableListOf(pt)
            }
            return groups.map{g->Triple(g.map{it.first}.average(),g.size,g.maxOf{it.second})}
        }
        // Combine highs and lows for role reversal: once price materially crosses an
        // old support it can become resistance, and vice versa.
        val levels=clustered(lows+highs)
        val below=levels.filter{it.first<current-minGap}
        val above=levels.filter{it.first>current+minGap}
        fun chooseSupport():Double?{
            val strong=below.filter{it.second>=2};return (if(strong.isNotEmpty())strong else below).maxByOrNull{it.first}?.first
        }
        fun chooseResistance():Double?{
            val strong=above.filter{it.second>=2};return (if(strong.isNotEmpty())strong else above).minByOrNull{it.first}?.first
        }
        var support=chooseSupport();var resistance=chooseResistance()
        // Real closed-candle fallback only. Never invent a number and never leave a
        // level on the wrong side of the current live market.
        if(support==null)support=w.map{it.l}.filter{it<current-minGap}.maxOrNull()
        if(resistance==null)resistance=w.map{it.h}.filter{it>current+minGap}.minOrNull()
        if(support==null||resistance==null||support>=current||resistance<=current)return null
        return support to resistance
    }'''
s=s[:start]+new_levels+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 53',g);g=re.sub(r'versionName = "[^"]+"','versionName = "53.0"',g);p.write_text(g)
print('v53 feed integrity + dynamic timeframe S/R applied')
