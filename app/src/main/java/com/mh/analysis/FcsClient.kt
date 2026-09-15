package com.mh.analysis

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.ArrayDeque
import kotlin.math.max

object FcsClient {
    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)
    private data class SourceCache(val at:Long,val candles:List<Candle>,val credits:Int)
    private data class PeriodPlan(val sourcePeriod:String,val multiplier:Int,val sourceLength:Int)

    private val cache=mutableMapOf<String,Cache>()
    private val sourceCache=mutableMapOf<String,SourceCache>()
    private val requestTimes=ArrayDeque<Long>()

    private const val MAX_REQUESTS_PER_WINDOW=3
    private const val REQUEST_WINDOW_MS=61_000L
    private const val RESULT_CACHE_MS=8_000L
    private const val SOURCE_FRESH_MS=18_000L
    private const val SOURCE_STALE_OK_MS=5*60_000L

    @Synchronized
    fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase()
        val tf=period.trim().lowercase()
        val resultKey="$sym|$tf|$length"
        val now=System.currentTimeMillis()
        val existing=cache[resultKey]
        if(!force&&existing!=null&&now-existing.at<RESULT_CACHE_MS)return existing.candles to 0

        val plan=periodPlan(tf,length)
        val sourceKey="$sym|${plan.sourcePeriod.lowercase()}"
        val sourceHit=sourceCache[sourceKey]
        val enough=sourceHit!=null&&sourceHit.candles.size>=requiredSource(plan,length)

        val raw:Pair<List<Candle>,Int> = when {
            !force&&enough&&now-sourceHit!!.at<SOURCE_FRESH_MS -> sourceHit.candles to 0
            canRequestNow() -> {
                val fetched=fetchMarket(sym,accessKey,plan.sourcePeriod,plan.sourceLength)
                noteRequest()
                sourceCache[sourceKey]=SourceCache(System.currentTimeMillis(),fetched.first,fetched.second)
                fetched
            }
            enough&&now-sourceHit!!.at<SOURCE_STALE_OK_MS -> sourceHit.candles to 0
            else -> throw IllegalStateException("Market feed is synchronizing. Retry in about ${nextSlotMs()/1000L+1}s.")
        }

        val built=if(plan.multiplier==1)raw.first.takeLast(length) else aggregate(raw.first,plan.multiplier).takeLast(length)
        if(built.size<60)throw IllegalStateException("Not enough live candle history for $symbol $period (${built.size})")
        cache[resultKey]=Cache(System.currentTimeMillis(),built,raw.second)
        return built to raw.second
    }

    private fun periodPlan(period:String,length:Int):PeriodPlan=when(period){
        "1m"->PeriodPlan("1m",1,length.coerceAtLeast(300))
        "5m"->PeriodPlan("5m",1,1500)
        "15m"->PeriodPlan("5m",3,1500)
        "30m"->PeriodPlan("5m",6,1500)
        "1h"->PeriodPlan("15m",4,1000)
        else->PeriodPlan(period,1,length.coerceAtLeast(220))
    }

    private fun requiredSource(plan:PeriodPlan,length:Int):Int=
        max(60*plan.multiplier,(length*plan.multiplier).coerceAtMost(plan.sourceLength)).coerceAtMost(plan.sourceLength)

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

    private fun trimWindow(){val now=System.currentTimeMillis();while(requestTimes.isNotEmpty()&&now-requestTimes.first()>=REQUEST_WINDOW_MS)requestTimes.removeFirst()}
    private fun canRequestNow():Boolean{trimWindow();return requestTimes.size<MAX_REQUESTS_PER_WINDOW}
    private fun noteRequest(){requestTimes.addLast(System.currentTimeMillis());trimWindow()}
    private fun nextSlotMs():Long{trimWindow();if(requestTimes.size<MAX_REQUESTS_PER_WINDOW)return 0L;return (REQUEST_WINDOW_MS-(System.currentTimeMillis()-requestTimes.first())).coerceAtLeast(0L)}

    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        return when(symbol){
            "XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity")
            else->{
                try{fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")}
                catch(first:Exception){
                    if(!canRequestNow())throw first
                    val result=fetch("crypto",key,"BTCUSDT",period,length,"crypto")
                    noteRequest();result
                }
            }
        }
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
        if(root.has("status")&&!root.optBoolean("status",true)){
            val msg=root.optString("msg","Market data request failed")
            if(msg.contains("rate limit",true))throw IllegalStateException("Market data request limit reached. Cached chart remains available until the next sync slot.")
            throw IllegalStateException(msg)
        }
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
        if(candles.size<60)throw IllegalStateException("Not enough live candle data for $symbol")
        return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){"1m"->"1m";"5m"->"5m";"15m"->"15m";"30m"->"30m";"1h"->"1h";else->p}
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
