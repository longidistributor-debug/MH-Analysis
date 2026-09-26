package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.OffsetDateTime
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.math.abs

/**
 * Free economic-calendar feed used by the PC build, ported to Android V.01.
 * Calendar refreshes are separate from the FCS 3-call/manual-analysis quota.
 */
object EconomicCalendarClient {
    data class Event(
        val title:String,
        val country:String,
        val timeMs:Long,
        val impact:String,
        val forecast:String,
        val previous:String,
        val actual:String
    )

    data class Risk(
        val blocked:Boolean,
        val penalty:Int,
        val summary:String,
        val nearest:Event?=null,
        val minutesToNearest:Long?=null
    )

    private const val PREF="mh_calendar_v01"
    private const val KEY_JSON="events"
    private const val KEY_AT="cached_at"
    private const val REFRESH_MS=60L*60L*1000L
    private const val MAX_CACHE_AGE_MS=72L*60L*60L*1000L
    private val refreshing=AtomicBoolean(false)
    @Volatile private var appContext:Context?=null
    @Volatile private var cachedAt:Long=0L
    @Volatile private var events:List<Event> = emptyList()

    private val endpoints=listOf(
        "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    )
    private val nextWeekEndpoints=listOf(
        "https://cdn-nfs.faireconomy.media/ff_calendar_nextweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
    )

    @Synchronized fun init(context:Context){
        if(appContext==null)appContext=context.applicationContext
        restore()
        refreshIfStale()
    }

    fun refreshIfStale(){
        val now=System.currentTimeMillis()
        if(events.isNotEmpty()&&now-cachedAt<REFRESH_MS)return
        if(!refreshing.compareAndSet(false,true))return
        thread(name="mh-calendar-refresh"){
            try{refreshNow()}finally{refreshing.set(false)}
        }
    }

    @Synchronized private fun restore(){
        val ctx=appContext?:return
        val p=ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE)
        val raw=p.getString(KEY_JSON,null)?:return
        val at=p.getLong(KEY_AT,0L)
        if(at<=0L||System.currentTimeMillis()-at>MAX_CACHE_AGE_MS)return
        val arr=runCatching{JSONArray(raw)}.getOrNull()?:return
        events=parseStored(arr)
        cachedAt=at
    }

    private fun refreshNow(){
        val first=fetchFirst(endpoints)
        val now=java.time.ZonedDateTime.now()
        val includeNext=now.dayOfWeek.value>=5 || first.isEmpty()
        val combined=if(includeNext)first+fetchFirst(nextWeekEndpoints) else first
        val clean=combined
            .filter{it.impact.equals("high",true)||it.impact.equals("medium",true)||it.impact.equals("med",true)||it.impact.equals("low",true)}
            .distinctBy{"${it.timeMs}|${it.country}|${it.title}"}
            .sortedBy{it.timeMs}
        if(clean.isEmpty())return
        synchronized(this){
            events=clean
            cachedAt=System.currentTimeMillis()
            persist(clean,cachedAt)
        }
    }

    private fun fetchFirst(urls:List<String>):List<Event>{
        for(u in urls){
            val r=runCatching{fetch(u)}.getOrNull().orEmpty()
            if(r.isNotEmpty())return r
        }
        return emptyList()
    }

    private fun fetch(endpoint:String):List<Event>{
        val c=URL(endpoint).openConnection() as HttpURLConnection
        c.connectTimeout=4500;c.readTimeout=6500;c.requestMethod="GET"
        c.setRequestProperty("User-Agent","MH-Analysis/V.01")
        val code=c.responseCode
        if(code !in 200..299)throw IllegalStateException("Calendar HTTP $code")
        val body=c.inputStream.bufferedReader().use{it.readText()}
        val arr=JSONArray(body);val out=mutableListOf<Event>()
        for(i in 0 until arr.length()){
            val o=arr.optJSONObject(i)?:continue
            val title=o.optString("title").trim();val country=o.optString("country").trim().uppercase()
            val impact=o.optString("impact").trim();val date=o.optString("date").trim()
            if(title.isBlank()||country.isBlank()||date.isBlank())continue
            val t=runCatching{OffsetDateTime.parse(date).toInstant().toEpochMilli()}.getOrNull()
                ?:runCatching{Instant.parse(date).toEpochMilli()}.getOrNull()?:continue
            out+=Event(title,country,t,impact,o.optString("forecast").trim(),o.optString("previous").trim(),o.optString("actual").trim())
        }
        return out
    }

    @Synchronized private fun persist(data:List<Event>,at:Long){
        val ctx=appContext?:return
        val a=JSONArray();data.forEach{e->a.put(JSONObject()
            .put("title",e.title).put("country",e.country).put("time",e.timeMs).put("impact",e.impact)
            .put("forecast",e.forecast).put("previous",e.previous).put("actual",e.actual))}
        ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE).edit().putString(KEY_JSON,a.toString()).putLong(KEY_AT,at).apply()
    }

    private fun parseStored(a:JSONArray):List<Event>{
        val out=mutableListOf<Event>()
        for(i in 0 until a.length()){
            val o=a.optJSONObject(i)?:continue;val t=o.optLong("time",0L)
            if(t<=0L)continue
            out+=Event(o.optString("title"),o.optString("country"),t,o.optString("impact"),o.optString("forecast"),o.optString("previous"),o.optString("actual"))
        }
        return out.sortedBy{it.timeMs}
    }

    /**
     * High-impact USD macro risk is relevant to both XAUUSD and BTCUSDT.
     * It does not invent directional bias from event names; it adjusts execution
     * quality according to proximity and blocks the most dangerous release window.
     */
    fun risk(symbol:String,nowMs:Long=System.currentTimeMillis()):Risk{
        refreshIfStale()
        val snapshot=events
        if(snapshot.isEmpty())return Risk(false,0,"Economic calendar: waiting for first free-feed refresh")
        val relevant=snapshot.filter{it.impact.equals("high",true)&&it.country=="USD"&&it.timeMs>=nowMs-45L*60L*1000L&&it.timeMs<=nowMs+24L*60L*60L*1000L}
        if(relevant.isEmpty())return Risk(false,0,"Economic calendar: no relevant HIGH USD event in the next 24h")
        val nearest=relevant.minByOrNull{abs(it.timeMs-nowMs)}?:return Risk(false,0,"Economic calendar: no nearby HIGH event")
        val signedMinutes=(nearest.timeMs-nowMs)/60_000L
        val distance=abs(signedMinutes)
        val blocked=distance<=15L
        val penalty=when{
            blocked->99
            distance<=30L->12
            distance<=60L->7
            distance<=120L->3
            else->0
        }
        val timing=when{
            signedMinutes>0->"in ${signedMinutes}m"
            signedMinutes<0->"${abs(signedMinutes)}m ago"
            else->"now"
        }
        val values=listOfNotNull(
            nearest.forecast.takeIf{it.isNotBlank()}?.let{"F $it"},
            nearest.previous.takeIf{it.isNotBlank()}?.let{"P $it"},
            nearest.actual.takeIf{it.isNotBlank()}?.let{"A $it"}
        ).joinToString(" • ")
        val tail=if(values.isBlank())"" else " • $values"
        val action=when{
            blocked->"EXECUTION BLOCK"
            penalty>0->"score -$penalty"
            else->"monitor only"
        }
        return Risk(blocked,penalty,"HIGH IMPACT USD: ${nearest.title} • $timing • $action$tail",nearest,signedMinutes)
    }
}
