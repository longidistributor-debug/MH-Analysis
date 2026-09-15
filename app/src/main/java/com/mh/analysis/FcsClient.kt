package com.mh.analysis

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.ArrayDeque

object FcsClient {
    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)
    private val cache=mutableMapOf<String,Cache>()
    private val requestTimes=ArrayDeque<Long>()

    private const val MAX_REQUESTS_PER_WINDOW=3
    private const val REQUEST_WINDOW_MS=61_000L
    private const val FRESH_MS=18_000L

    @Synchronized
    fun peek(symbol:String,period:String,length:Int=220):List<Candle>? {
        val key="${symbol.uppercase()}|${period.trim().lowercase()}"
        return cache[key]?.candles?.takeLast(length)
    }

    @Synchronized
    fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase()
        val tf=period.trim().lowercase()
        val key="$sym|$tf"
        val now=System.currentTimeMillis()
        val hit=cache[key]

        // Always return a genuinely fetched timeframe feed immediately while it is fresh.
        if(!force&&hit!=null&&now-hit.at<FRESH_MS&&hit.candles.size>=60)return hit.candles.takeLast(length) to 0

        // If the provider quota is currently full, never freeze the UI or throw a rate-limit
        // error when we already have a real chart for this exact timeframe. Return the last
        // real feed immediately and let the next refresh slot update it.
        if(!canRequestNow()){
            if(hit!=null&&hit.candles.size>=60)return hit.candles.takeLast(length) to 0
            throw IllegalStateException("Live feed is waiting for the next provider sync slot. The chart will refresh automatically.")
        }

        val fetched=try{
            fetchMarket(sym,accessKey,tf,length.coerceAtLeast(260))
        }catch(e:Exception){
            noteRequest()
            if(hit!=null&&hit.candles.size>=60)return hit.candles.takeLast(length) to 0
            throw e
        }
        noteRequest()
        cache[key]=Cache(System.currentTimeMillis(),fetched.first,fetched.second)
        return fetched.first.takeLast(length) to fetched.second
    }

    private fun trimWindow(){
        val now=System.currentTimeMillis()
        while(requestTimes.isNotEmpty()&&now-requestTimes.first()>=REQUEST_WINDOW_MS)requestTimes.removeFirst()
    }
    private fun canRequestNow():Boolean{trimWindow();return requestTimes.size<MAX_REQUESTS_PER_WINDOW}
    private fun noteRequest(){requestTimes.addLast(System.currentTimeMillis());trimWindow()}

    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        return when(symbol){
            "XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity")
            // One canonical BTC request only. A hidden fallback request could consume a second
            // provider slot and was one cause of quota errors in earlier builds.
            else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")
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
            if(msg.contains("rate limit",true))throw IllegalStateException("Provider request limit reached; the last real chart remains active until the next sync slot.")
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
        if(candles.size<60)throw IllegalStateException("Not enough live candle data for $symbol $period")
        return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){
        "1m"->"1m";"5m"->"5m";"15m"->"15m";"30m"->"30m";"1h"->"1h";else->p
    }
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
