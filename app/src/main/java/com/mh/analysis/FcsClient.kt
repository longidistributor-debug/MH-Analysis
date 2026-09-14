package com.mh.analysis

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.max

object FcsClient {
    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)
    private data class PeriodPlan(val sourcePeriod:String,val multiplier:Int)
    private val cache=mutableMapOf<String,Cache>()
    private var lastNetworkAt=0L
    private const val CACHE_MS=60_000L
    private const val MIN_GAP_MS=21_000L

    @Synchronized
    fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val key="${symbol.uppercase()}|${period.lowercase()}"
        val now=System.currentTimeMillis()
        val hit=cache[key]
        if(!force && hit!=null && now-hit.at<CACHE_MS) return hit.candles to 0

        val plan=periodPlan(period)
        val sourceLength=(length*plan.multiplier+plan.multiplier*4).coerceAtMost(1500)
        val wait=max(0L,MIN_GAP_MS-(now-lastNetworkAt))
        if(wait>0) Thread.sleep(wait)

        val raw=when(symbol.uppercase()){
            "XAUUSD" -> fetch("forex",accessKey,"XAUUSD",plan.sourcePeriod,sourceLength,"commodity")
            else -> try{fetch("crypto",accessKey,"BINANCE:BTCUSDT",plan.sourcePeriod,sourceLength,"crypto")}catch(_:Exception){fetch("crypto",accessKey,"BTCUSDT",plan.sourcePeriod,sourceLength,"crypto")}
        }
        lastNetworkAt=System.currentTimeMillis()

        val candles=if(plan.multiplier==1)raw.first.takeLast(length) else aggregate(raw.first,plan.multiplier).takeLast(length)
        if(candles.size<60) throw IllegalStateException("Not enough candle data for $symbol $period (${candles.size})")
        val result=candles to raw.second
        cache[key]=Cache(lastNetworkAt,result.first,result.second)
        return result
    }

    private fun periodPlan(period:String):PeriodPlan=when(period.trim().lowercase()){
        "3m"->PeriodPlan("1m",3)
        "5m"->PeriodPlan("5m",1)
        "10m"->PeriodPlan("5m",2)
        "15m"->PeriodPlan("15m",1)
        "30m"->PeriodPlan("30m",1)
        "1h"->PeriodPlan("1h",1)
        "2h"->PeriodPlan("1h",2)
        "4h"->PeriodPlan("4h",1)
        "6h"->PeriodPlan("1h",6)
        "12h"->PeriodPlan("1h",12)
        "1d"->PeriodPlan("1D",1)
        else->PeriodPlan(period,1)
    }

    private fun aggregate(src:List<Candle>,multiplier:Int):List<Candle>{
        if(multiplier<=1||src.isEmpty())return src
        val out=mutableListOf<Candle>()
        var i=0
        while(i+multiplier<=src.size){
            val g=src.subList(i,i+multiplier)
            out+=Candle(
                t=g.first().t,
                o=g.first().o,
                h=g.maxOf{it.h},
                l=g.minOf{it.l},
                c=g.last().c,
                v=g.sumOf{it.v}
            )
            i+=multiplier
        }
        return out
    }

    private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String):Pair<List<Candle>,Int>{
        val p=normalizePeriod(period)
        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0&type=${enc(type)}&access_key=${enc(key)}"
        val c=URL(u).openConnection() as HttpURLConnection
        c.connectTimeout=15000;c.readTimeout=20000;c.requestMethod="GET"
        val code=c.responseCode
        val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}
        if(code !in 200..299) throw IllegalStateException("FCS HTTP $code: ${body.take(150)}")
        val root=JSONObject(body)
        if(root.has("status")&&!root.optBoolean("status",true)) throw IllegalStateException(root.optString("msg","FCS request failed"))
        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1
        val response=root.opt("response")?:root.opt("data")?:root
        val candles=mutableListOf<Candle>()
        fun add(o:JSONObject,k:String=""){
            if(!o.has("o")||!o.has("c"))return
            candles+=Candle(o.optLong("t",k.toLongOrNull()?:0L),o.optDouble("o"),o.optDouble("h"),o.optDouble("l"),o.optDouble("c"),o.optDouble("v",0.0))
        }
        when(response){
            is JSONArray -> for(i in 0 until response.length()) response.optJSONObject(i)?.let{add(it)}
            is JSONObject -> {val it=response.keys();while(it.hasNext()){val k=it.next();response.optJSONObject(k)?.let{add(it,k)}}}
        }
        candles.sortBy{it.t}
        if(candles.size<60) throw IllegalStateException("Not enough candle data for $symbol (${candles.size})")
        return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){
        "1m"->"1m";"5m"->"5m";"15m"->"15m";"30m"->"30m";"1h"->"1h";"4h"->"4h";"1d"->"1D";else->p
    }
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
