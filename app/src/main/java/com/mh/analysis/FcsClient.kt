package com.mh.analysis

import android.content.Context
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
    private val lastPersist=mutableMapOf<String,Long>()
    private var appContext:Context?=null
    private var restored=false
    private const val MAX_REQUESTS_PER_WINDOW=3
    private const val REQUEST_WINDOW_MS=61_000L
    private const val DISK_LIMIT=500
    private val periods=listOf("1m","5m","15m","30m","1h")
    private val symbols=listOf("XAUUSD","BTCUSDT")

    @Synchronized fun init(context:Context){
        if(appContext==null)appContext=context.applicationContext
        if(restored)return
        restored=true
        val p=appContext?.getSharedPreferences("mh_candle_cache_v22",Context.MODE_PRIVATE)?:return
        for(s in symbols)for(tf in periods){
            val k=cacheKey(s,tf)
            val raw=p.getString(k,null)?:continue
            val arr=runCatching{JSONArray(raw)}.getOrNull()?:continue
            val out=mutableListOf<Candle>()
            for(i in 0 until arr.length()){
                val o=arr.optJSONObject(i)?:continue
                val t=o.optLong("t",0L);val c=o.optDouble("c",Double.NaN)
                if(t<=0L||c.isNaN())continue
                out+=Candle(t,o.optDouble("o",c),o.optDouble("h",c),o.optDouble("l",c),c,o.optDouble("v",0.0))
            }
            if(out.isNotEmpty())cache[k]=Cache(System.currentTimeMillis(),out,0)
        }
    }

    @Synchronized fun peek(symbol:String,period:String,length:Int=220):List<Candle>? =
        cache[cacheKey(symbol,period)]?.candles?.takeLast(length)

    @Synchronized fun hasUsableHistory(symbol:String,period:String,min:Int=100)=
        (cache[cacheKey(symbol,period)]?.candles?.size?:0)>=min

    @Synchronized fun applyLiveCandle(symbol:String,period:String,candle:Candle):Candle {
        val key=cacheKey(symbol,period)
        val t=normalizeTs(candle.t)
        val x=candle.copy(t=t)
        val old=cache[key]?.candles?.toMutableList()?: mutableListOf()
        val previousTs=old.lastOrNull()?.t
        if(old.isNotEmpty()&&normalizeTs(old.last().t)==t)old[old.lastIndex]=x
        else{
            old+=x
            if(old.size>12000)repeat(old.size-12000){old.removeAt(0)}
        }
        cache[key]=Cache(System.currentTimeMillis(),old,0)
        persistMaybe(key,old,previousTs!=t)
        return x
    }

    @Synchronized fun applyLivePrice(symbol:String,period:String,t:Long,price:Double):Candle? {
        val key=cacheKey(symbol,period)
        val old=cache[key]?.candles?.toMutableList()?:return null
        if(old.isEmpty())return null
        val ts=normalizeTs(t)
        val last=old.last()
        val same=normalizeTs(last.t)==ts||ts==0L
        val x=if(same)last.copy(h=max(last.h,price),l=kotlin.math.min(last.l,price),c=price)
        else Candle(ts,price,price,price,price,0.0)
        if(same)old[old.lastIndex]=x else old+=x
        if(old.size>12000)repeat(old.size-12000){old.removeAt(0)}
        cache[key]=Cache(System.currentTimeMillis(),old,0)
        persistMaybe(key,old,!same)
        return x
    }

    /** Fetches only the history family needed by the selected timeframe.
     * 1m/5m share a 1m seed; 15m/30m share a 15m seed; 1h uses a 1h seed.
     * Once persisted locally, timeframe switching is instant and costs no REST credit.
     */
    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        if(current.size>=100&&!force)return current.takeLast(220) to 0
        if(!canRequestNow()){
            if(current.isNotEmpty())return current.takeLast(220) to 0
            throw IllegalStateException("Waiting for next history request slot. Live stream keeps running.")
        }
        var credits=0
        fun fetchSeed(sourceTf:String,length:Int):List<Candle>{
            val out=try{fetchMarket(sym,accessKey,sourceTf,length)}catch(e:Exception){noteRequest();throw e}
            noteRequest();credits+=out.second
            return out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
        }
        when(tf){
            "1m","5m"->{
                val one=fetchSeed("1m",600)
                putCache(sym,"1m",one,true)
                putCache(sym,"5m",aggregate(one,5),true)
            }
            "15m","30m"->{
                val fifteen=fetchSeed("15m",300)
                putCache(sym,"15m",fifteen,true)
                putCache(sym,"30m",aggregate(fifteen,30),true)
            }
            "1h"->{
                val hour=fetchSeed("1h",300)
                putCache(sym,"1h",hour,true)
            }
        }
        val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)
        if(result.isEmpty())throw IllegalStateException("No usable history returned for $sym $tf")
        return result to credits
    }

    /** Best-effort background fill. It never discards successful families when another family fails. */
    @Synchronized fun bootstrap(accessKey:String,symbol:String,force:Boolean=false):Pair<Map<String,List<Candle>>,Int>{
        val sym=symbol.uppercase();var credits=0
        for(tf in listOf("15m","1m","1h")){
            if(!canRequestNow())break
            runCatching{seedForPeriod(accessKey,sym,tf,force)}.onSuccess{credits+=it.second}
        }
        val result=periods.associateWith{cache[cacheKey(sym,it)]?.candles?.takeLast(220)?:emptyList()}
        if(result.values.none{it.isNotEmpty()})throw IllegalStateException("No usable historical seed was returned for $sym")
        return result to credits
    }

    @Synchronized fun history(accessKey:String,symbol:String,period:String,length:Int=220,force:Boolean=false):Pair<List<Candle>,Int>{
        val hit=cache[cacheKey(symbol,period)]?.candles?.takeLast(length)
        if(!hit.isNullOrEmpty()&&hit.size>=100&&!force)return hit to 0
        val(out,credits)=seedForPeriod(accessKey,symbol,period,force)
        if(out.size<60)throw IllegalStateException("$symbol $period history is still building; live price stays connected.")
        return out.takeLast(length) to credits
    }

    private fun putCache(symbol:String,period:String,data:List<Candle>,persist:Boolean){
        val key=cacheKey(symbol,period)
        cache[key]=Cache(System.currentTimeMillis(),data,0)
        if(persist)persistNow(key,data)
    }

    private fun persistMaybe(key:String,data:List<Candle>,newCandle:Boolean){
        val now=System.currentTimeMillis();val last=lastPersist[key]?:0L
        if(newCandle||now-last>=20_000L){lastPersist[key]=now;persistNow(key,data)}
    }

    private fun persistNow(key:String,data:List<Candle>){
        val ctx=appContext?:return
        val arr=JSONArray()
        data.takeLast(DISK_LIMIT).forEach{arr.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))}
        ctx.getSharedPreferences("mh_candle_cache_v22",Context.MODE_PRIVATE).edit().putString(key,arr.toString()).apply()
    }

    private fun aggregate(src:List<Candle>,targetMins:Int):List<Candle>{
        if(targetMins<=1)return src
        val sec=targetMins*60L
        val out=mutableListOf<Candle>();var bucket=-1L;var o=0.0;var h=0.0;var l=0.0;var c=0.0;var v=0.0
        fun flush(){if(bucket>=0)out+=Candle(bucket,o,h,l,c,v)}
        for(x0 in src){
            val x=x0.copy(t=normalizeTs(x0.t));val b=(x.t/sec)*sec
            if(b!=bucket){flush();bucket=b;o=x.o;h=x.h;l=x.l;c=x.c;v=x.v}
            else{h=max(h,x.h);l=kotlin.math.min(l,x.l);c=x.c;v+=x.v}
        }
        flush();return out
    }

    private fun trimWindow(){val now=System.currentTimeMillis();while(requestTimes.isNotEmpty()&&now-requestTimes.first()>=REQUEST_WINDOW_MS)requestTimes.removeFirst()}
    private fun canRequestNow():Boolean{trimWindow();return requestTimes.size<MAX_REQUESTS_PER_WINDOW}
    private fun noteRequest(){requestTimes.addLast(System.currentTimeMillis());trimWindow()}

    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{
        return when(symbol){"XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")}
    }

    private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String):Pair<List<Candle>,Int>{
        val p=normalizePeriod(period)
        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0&type=${enc(type)}&access_key=${enc(key)}"
        val c=URL(u).openConnection() as HttpURLConnection;c.connectTimeout=12000;c.readTimeout=22000;c.requestMethod="GET"
        val code=c.responseCode;val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}
        if(code !in 200..299)throw IllegalStateException("Market data HTTP $code")
        val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Market data request failed"))
        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1;val response=root.opt("response")?:root.opt("data")?:root;val candles=mutableListOf<Candle>()
        fun add(o:JSONObject,k:String=""){if(!o.has("o")||!o.has("c"))return;candles+=Candle(normalizeTs(o.optLong("t",k.toLongOrNull()?:0L)),o.optDouble("o"),o.optDouble("h"),o.optDouble("l"),o.optDouble("c"),o.optDouble("v",0.0))}
        when(response){is JSONArray->for(i in 0 until response.length())response.optJSONObject(i)?.let{add(it)};is JSONObject->{val it=response.keys();while(it.hasNext()){val k=it.next();response.optJSONObject(k)?.let{add(it,k)}}}}
        candles.sortBy{it.t};if(candles.size<60)throw IllegalStateException("Not enough candle history for $symbol $period");return candles to credits
    }

    private fun normalizePeriod(p:String)=when(p.trim().lowercase()){"1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->p.trim().lowercase()}
    private fun cacheKey(symbol:String,period:String)="${symbol.uppercase()}|${normalizePeriod(period)}"
    private fun normalizeTs(t:Long)=if(t>9_999_999_999L)t/1000L else t
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
}
