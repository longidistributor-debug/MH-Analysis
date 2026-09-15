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
    private val cache=mutableMapOf<String,Cache>()
    private val requestTimes=ArrayDeque<Long>()
    private val preferred=mutableMapOf<String,String>()
    private const val MAX_REQUESTS_PER_WINDOW=3
    private const val REQUEST_WINDOW_MS=61_000L
    private val periods=listOf("1m","5m","15m","30m","1h")

    @Synchronized fun peek(symbol:String,period:String,length:Int=220):List<Candle>? {
        preferred[symbol.uppercase()]=normalizePeriod(period)
        return cache[cacheKey(symbol,period)]?.candles?.takeLast(length)
    }

    @Synchronized fun hasUsableHistory(symbol:String,period:String,min:Int=100)=
        (cache[cacheKey(symbol,period)]?.candles?.size?:0)>=min

    @Synchronized fun applyLiveCandle(symbol:String,period:String,candle:Candle):Candle {
        val key=cacheKey(symbol,period)
        val t=normalizeTs(candle.t)
        val x=candle.copy(t=t)
        val existing=cache[key]?:return x
        val old=existing.candles.toMutableList()
        if(old.isNotEmpty()&&normalizeTs(old.last().t)==t)old[old.lastIndex]=x
        else{
            old+=x
            if(old.size>12000)repeat(old.size-12000){old.removeAt(0)}
        }
        cache[key]=Cache(System.currentTimeMillis(),old,0)
        return x
    }

    @Synchronized fun applyLivePrice(symbol:String,period:String,t:Long,price:Double):Candle? {
        val key=cacheKey(symbol,period)
        val existing=cache[key]?:return null
        val old=existing.candles.toMutableList()
        if(old.isEmpty())return null
        val ts=normalizeTs(t)
        val last=old.last()
        val same=normalizeTs(last.t)==ts||ts==0L
        val x=if(same)last.copy(h=max(last.h,price),l=kotlin.math.min(last.l,price),c=price)
        else Candle(ts,price,price,price,price,0.0)
        if(same)old[old.lastIndex]=x else old+=x
        if(old.size>12000)repeat(old.size-12000){old.removeAt(0)}
        cache[key]=Cache(System.currentTimeMillis(),old,0)
        return x
    }

    /**
     * Progressive seed. The family containing the last requested UI timeframe is fetched first.
     * A failed family never discards successful history from another family.
     * Families:
     * 1m x 600 -> 1m + 5m
     * 15m x 300 -> 15m + 30m
     * 1h x 300 -> 1h
     */
    @Synchronized fun bootstrap(accessKey:String,symbol:String,force:Boolean=false):Pair<Map<String,List<Candle>>,Int>{
        val sym=symbol.uppercase()
        val enough=periods.all{hasUsableHistory(sym,it,100)}
        if(enough&&!force)return periods.associateWith{cache[cacheKey(sym,it)]?.candles?.takeLast(220)?:emptyList()} to 0

        var credits=0
        var lastError=""

        fun request(period:String,length:Int):List<Candle>?{
            if(!canRequestNow()){lastError="Historical seed is waiting for the next provider request slot.";return null}
            return try{
                val out=fetchMarket(sym,accessKey,period,length)
                noteRequest();credits+=out.second
                out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
            }catch(e:Exception){
                noteRequest();lastError=e.message?:"History request failed";null
            }
        }

        fun seedOneMinute(){
            var one=cache[cacheKey(sym,"1m")]?.candles.orEmpty()
            if(force||one.size<600){request("1m",600)?.let{one=it;cache[cacheKey(sym,"1m")]=Cache(System.currentTimeMillis(),one,0)}}
            if(one.isNotEmpty())cache[cacheKey(sym,"5m")]=Cache(System.currentTimeMillis(),aggregate(one,5),0)
        }
        fun seedFifteen(){
            var fifteen=cache[cacheKey(sym,"15m")]?.candles.orEmpty()
            if(force||fifteen.size<300){request("15m",300)?.let{fifteen=it;cache[cacheKey(sym,"15m")]=Cache(System.currentTimeMillis(),fifteen,0)}}
            if(fifteen.isNotEmpty())cache[cacheKey(sym,"30m")]=Cache(System.currentTimeMillis(),aggregate(fifteen,30),0)
        }
        fun seedHour(){
            var hour=cache[cacheKey(sym,"1h")]?.candles.orEmpty()
            if(force||hour.size<300){request("1h",300)?.let{hour=it;cache[cacheKey(sym,"1h")]=Cache(System.currentTimeMillis(),hour,0)}}
        }

        val p=preferred[sym]?:"15m"
        val order=when(p){
            "1m","5m"->listOf(0,1,2)
            "1h"->listOf(2,1,0)
            else->listOf(1,0,2)
        }
        for(f in order){
            when(f){0->seedOneMinute();1->seedFifteen();2->seedHour()}
        }

        val result=periods.associateWith{cache[cacheKey(sym,it)]?.candles?.takeLast(220)?:emptyList()}
        if(result.values.none{it.size>=60})throw IllegalStateException(if(lastError.isBlank())"No usable historical seed was returned for $sym" else lastError)
        return result to credits
    }

    @Synchronized fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        preferred[symbol.uppercase()]=normalizePeriod(period)
        val hit=cache[cacheKey(symbol,period)]?.candles?.takeLast(length)
        if(!hit.isNullOrEmpty()&&hit.size>=100&&!force)return hit to 0
        val(all,credits)=bootstrap(accessKey,symbol,force)
        val out=all[normalizePeriod(period)]?.takeLast(length)?:emptyList()
        if(out.size<60)throw IllegalStateException("$symbol $period history is still seeding. Live stream stays connected and this timeframe will appear automatically.")
        return out to credits
    }

    private fun aggregate(src:List<Candle>,targetMins:Int):List<Candle>{
        if(targetMins<=1)return src
        val sec=targetMins*60L
        val out=mutableListOf<Candle>()
        var bucket=-1L;var o=0.0;var h=0.0;var l=0.0;var c=0.0;var v=0.0
        fun flush(){if(bucket>=0)out+=Candle(bucket,o,h,l,c,v)}
        for(x0 in src){
            val x=x0.copy(t=normalizeTs(x0.t));val b=(x.t/sec)*sec
            if(b!=bucket){flush();bucket=b;o=x.o;h=x.h;l=x.l;c=x.c;v=x.v}
            else{h=max(h,x.h);l=kotlin.math.min(l,x.l);c=x.c;v+=x.v}
        }
        flush();return out
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
            else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")
        }
    }

    private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String):Pair<List<Candle>,Int>{
        val p=normalizePeriod(period)
        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0&type=${enc(type)}&access_key=${enc(key)}"
        val c=URL(u).openConnection() as HttpURLConnection
        c.connectTimeout=12000;c.readTimeout=22000;c.requestMethod="GET"
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
            candles+=Candle(normalizeTs(o.optLong("t",k.toLongOrNull()?:0L)),o.optDouble("o"),o.optDouble("h"),o.optDouble("l"),o.optDouble("c"),o.optDouble("v",0.0))
        }
        when(response){
            is JSONArray->for(i in 0 until response.length())response.optJSONObject(i)?.let{add(it)}
            is JSONObject->{val it=response.keys();while(it.hasNext()){val k=it.next();response.optJSONObject(k)?.let{add(it,k)}}}
        }
        candles.sortBy{it.t}
        if(candles.size<60)throw IllegalStateException("Not enough candle history for $symbol $period")
        return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){
        "1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->p.trim().lowercase()
    }
    private fun cacheKey(symbol:String,period:String)="${symbol.uppercase()}|${normalizePeriod(period)}"
    private fun normalizeTs(t:Long)=if(t>9_999_999_999L)t/1000L else t
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
