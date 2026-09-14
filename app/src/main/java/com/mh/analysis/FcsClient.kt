package com.mh.analysis

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.max

object FcsClient {
    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)
    private data class SourceCache(val at:Long,val candles:List<Candle>,val credits:Int)
    private data class PeriodPlan(val sourcePeriod:String,val multiplier:Int,val sourceLength:Int)

    private val cache=mutableMapOf<String,Cache>()
    private val sourceCache=mutableMapOf<String,SourceCache>()
    private var lastNetworkAt=0L

    // The connected FCS plan allows 3 requests/minute. Keep every real HTTP call
    // safely outside the rolling 20 second window. Derived/cached timeframes do not
    // consume another request.
    private const val MIN_GAP_MS=20_500L
    private const val RESULT_CACHE_MS=45_000L
    private const val FAST_SOURCE_CACHE_MS=30_000L
    private const val SLOW_SOURCE_CACHE_MS=90_000L

    @Synchronized
    fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val normalizedSymbol=symbol.uppercase()
        val normalizedPeriod=period.trim().lowercase()
        val resultKey="$normalizedSymbol|$normalizedPeriod|$length"
        val now=System.currentTimeMillis()

        val existing=cache[resultKey]
        if(!force&&existing!=null&&now-existing.at<RESULT_CACHE_MS)return existing.candles to 0

        val plan=periodPlan(normalizedPeriod,length)
        // IMPORTANT: source cache is keyed only by symbol + real FCS source period.
        // 1h, 2h, 4h, 6h and 12h therefore share ONE 1h network dataset.
        val sourceKey="$normalizedSymbol|${plan.sourcePeriod.lowercase()}"
        val sourceTtl=if(plan.sourcePeriod.equals("1m",true))FAST_SOURCE_CACHE_MS else SLOW_SOURCE_CACHE_MS
        val sourceHit=sourceCache[sourceKey]
        val enoughCached=sourceHit!=null&&sourceHit.candles.size>=minRequiredSource(plan,length)

        val raw:Pair<List<Candle>,Int>
        if(!force&&enoughCached&&now-sourceHit!!.at<sourceTtl){
            raw=sourceHit.candles to 0
        }else{
            val wait=max(0L,MIN_GAP_MS-(System.currentTimeMillis()-lastNetworkAt))
            if(wait>0)Thread.sleep(wait)

            val fetched=when(normalizedSymbol){
                "XAUUSD"->fetch("forex",accessKey,"XAUUSD",plan.sourcePeriod,plan.sourceLength,"commodity")
                else->try{fetch("crypto",accessKey,"BINANCE:BTCUSDT",plan.sourcePeriod,plan.sourceLength,"crypto")}
                catch(_:Exception){fetch("crypto",accessKey,"BTCUSDT",plan.sourcePeriod,plan.sourceLength,"crypto")}
            }
            lastNetworkAt=System.currentTimeMillis()
            sourceCache[sourceKey]=SourceCache(lastNetworkAt,fetched.first,fetched.second)
            raw=fetched
        }

        val built=if(plan.multiplier==1)raw.first.takeLast(length)
        else aggregate(raw.first,plan.multiplier).takeLast(length)

        if(built.size<60)throw IllegalStateException("Not enough candle data for $symbol $period (${built.size})")
        cache[resultKey]=Cache(System.currentTimeMillis(),built,raw.second)
        return built to raw.second
    }

    private fun periodPlan(period:String,length:Int):PeriodPlan=when(period){
        "3m"->PeriodPlan("1m",3,(length*3+18).coerceAtMost(1500))
        "5m"->PeriodPlan("5m",1,length.coerceAtLeast(220))
        "10m"->PeriodPlan("5m",2,(length*2+12).coerceAtMost(1500))
        "15m"->PeriodPlan("15m",1,length.coerceAtLeast(220))
        "30m"->PeriodPlan("30m",1,length.coerceAtLeast(220))

        // All intraday higher timeframes use one deep 1h source request. This is
        // what prevents 2h/4h/6h/12h switching from exhausting the 3 req/min plan.
        "1h"->PeriodPlan("1h",1,1500)
        "2h"->PeriodPlan("1h",2,1500)
        "4h"->PeriodPlan("1h",4,1500)
        "6h"->PeriodPlan("1h",6,1500)
        "12h"->PeriodPlan("1h",12,1500)

        // Daily stays native so the analysis engine still receives enough history.
        "1d","1day"->PeriodPlan("1D",1,length.coerceAtLeast(220))
        else->PeriodPlan(period,1,length.coerceAtLeast(220))
    }

    private fun minRequiredSource(plan:PeriodPlan,length:Int):Int{
        val wanted=(length*plan.multiplier).coerceAtMost(plan.sourceLength)
        // For large derived timeframes 60 aggregated candles are enough to render.
        // Prefer the full requested set when available.
        return max(60*plan.multiplier,wanted.coerceAtMost(plan.sourceLength)).coerceAtMost(plan.sourceLength)
    }

    private fun aggregate(src:List<Candle>,multiplier:Int):List<Candle>{
        if(multiplier<=1||src.isEmpty())return src
        val out=mutableListOf<Candle>()
        var i=src.size%multiplier
        while(i+multiplier<=src.size){
            val g=src.subList(i,i+multiplier)
            out+=Candle(
                g.first().t,
                g.first().o,
                g.maxOf{it.h},
                g.minOf{it.l},
                g.last().c,
                g.sumOf{it.v}
            )
            i+=multiplier
        }
        return out
    }

    private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String):Pair<List<Candle>,Int>{
        val p=normalizePeriod(period)
        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0&type=${enc(type)}&access_key=${enc(key)}"
        val c=URL(u).openConnection() as HttpURLConnection
        c.connectTimeout=12000;c.readTimeout=18000;c.requestMethod="GET"
        val code=c.responseCode
        val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}
        if(code !in 200..299)throw IllegalStateException("FCS HTTP $code: ${body.take(150)}")
        val root=JSONObject(body)
        if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","FCS request failed"))
        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1
        val response=root.opt("response")?:root.opt("data")?:root
        val candles=mutableListOf<Candle>()
        fun add(o:JSONObject,k:String=""){
            if(!o.has("o")||!o.has("c"))return
            candles+=Candle(o.optLong("t",k.toLongOrNull()?:0L),o.optDouble("o"),o.optDouble("h"),o.optDouble("l"),o.optDouble("c"),o.optDouble("v",0.0))
        }
        when(response){
            is JSONArray->for(i in 0 until response.length())response.optJSONObject(i)?.let{add(it)}
            is JSONObject->{val it=response.keys();while(it.hasNext()){val k=it.next();response.optJSONObject(k)?.let{add(it,k)}}}
        }
        candles.sortBy{it.t}
        if(candles.size<60)throw IllegalStateException("Not enough candle data for $symbol (${candles.size})")
        return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){
        "1m"->"1m";"5m"->"5m";"15m"->"15m";"30m"->"30m";"1h"->"1h";"4h"->"4h";"1d","1day"->"1D";else->p
    }
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
