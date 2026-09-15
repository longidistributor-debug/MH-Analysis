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

    // User plan allows 3 real requests/minute. The app now needs only two live
    // source feeds per symbol: native 1m and deep 5m. 5m/15m/30m are all built
    // from the same 5m source so timeframe switching does not create new calls.
    private const val MIN_GAP_MS=20_500L
    private const val RESULT_CACHE_MS=20_000L
    private const val ONE_MIN_TTL_MS=24_000L
    private const val FIVE_MIN_TTL_MS=55_000L

    @Synchronized
    fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val normalizedSymbol=symbol.uppercase()
        val normalizedPeriod=period.trim().lowercase()
        val resultKey="$normalizedSymbol|$normalizedPeriod|$length"
        val now=System.currentTimeMillis()
        val existing=cache[resultKey]
        if(!force&&existing!=null&&now-existing.at<RESULT_CACHE_MS)return existing.candles to 0

        val plan=periodPlan(normalizedPeriod,length)
        val sourceKey="$normalizedSymbol|${plan.sourcePeriod.lowercase()}"
        val ttl=if(plan.sourcePeriod.equals("1m",true))ONE_MIN_TTL_MS else FIVE_MIN_TTL_MS
        val sourceHit=sourceCache[sourceKey]
        val enough=sourceHit!=null&&sourceHit.candles.size>=requiredSource(plan,length)

        val raw:Pair<List<Candle>,Int>
        if(!force&&enough&&now-sourceHit!!.at<ttl){
            raw=sourceHit.candles to 0
        }else{
            // If a valid cached source exists but another module just consumed the
            // request slot, use that source immediately instead of freezing the UI.
            // Background refresh will update it on the next allowed request.
            val since=System.currentTimeMillis()-lastNetworkAt
            if(!force&&enough&&since<MIN_GAP_MS){
                raw=sourceHit!!.candles to 0
            }else{
                val wait=max(0L,MIN_GAP_MS-since)
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
        }

        val built=if(plan.multiplier==1)raw.first.takeLast(length)
        else aggregate(raw.first,plan.multiplier).takeLast(length)
        if(built.size<60)throw IllegalStateException("Not enough candle data for $symbol $period (${built.size})")
        cache[resultKey]=Cache(System.currentTimeMillis(),built,raw.second)
        return built to raw.second
    }

    private fun periodPlan(period:String,length:Int):PeriodPlan=when(period){
        "1m"->PeriodPlan("1m",1,length.coerceAtLeast(240))
        "5m"->PeriodPlan("5m",1,1500)
        "15m"->PeriodPlan("5m",3,1500)
        "30m"->PeriodPlan("5m",6,1500)
        else->PeriodPlan("5m",1,1500)
    }

    private fun requiredSource(plan:PeriodPlan,length:Int):Int{
        return (length*plan.multiplier).coerceAtMost(plan.sourceLength).coerceAtLeast(60*plan.multiplier)
    }

    private fun aggregate(src:List<Candle>,multiplier:Int):List<Candle>{
        if(multiplier<=1||src.isEmpty())return src
        val out=mutableListOf<Candle>()
        var i=src.size%multiplier
        while(i+multiplier<=src.size){
            val g=src.subList(i,i+multiplier)
            out+=Candle(g.first().t,g.first().o,g.maxOf{it.h},g.minOf{it.l},g.last().c,g.sumOf{it.v})
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
        if(code !in 200..299)throw IllegalStateException("Market data HTTP $code")
        val root=JSONObject(body)
        if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Market data request failed"))
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

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){"1m"->"1m";"5m"->"5m";else->p}
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
