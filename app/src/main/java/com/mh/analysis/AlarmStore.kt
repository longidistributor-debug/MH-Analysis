package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object AlarmStore {
    private const val PREF="mh_alarms"
    private const val KEEP_MS=3L*24*60*60*1000
    private fun prefs(c:Context)=c.getSharedPreferences(PREF,Context.MODE_PRIVATE)

    fun add(c:Context,s:Signal){
        val list=list(c).toMutableList();val now=System.currentTimeMillis()
        if(list.none{it.signalId==s.id}){
            list.add(0,AlarmEntry("alarm_${s.id}",s.id,s.symbol,s.timeframe,s.direction,s.entry,Long.MAX_VALUE,now,true,"ARMED",null))
            save(c,list)
        }
    }

    fun list(c:Context):List<AlarmEntry>{
        val cutoff=System.currentTimeMillis()-KEEP_MS
        val raw=prefs(c).getString("alarms","[]")?:"[]";val a=runCatching{JSONArray(raw)}.getOrElse{JSONArray()};val out=mutableListOf<AlarmEntry>()
        for(i in 0 until a.length())runCatching{fromJson(a.getJSONObject(i))}.getOrNull()?.let{if(it.createdAt>=cutoff)out+=it}
        val cleaned=out.sortedByDescending{it.createdAt};save(c,cleaned);return cleaned
    }

    fun armed(c:Context)=list(c).filter{it.enabled&&it.status=="ARMED"}
    fun update(c:Context,e:AlarmEntry){val l=list(c).toMutableList();val i=l.indexOfFirst{it.id==e.id};if(i>=0)l[i]=e else l.add(0,e);save(c,l)}
    fun expireSignal(c:Context,signalId:String,status:String="EXPIRED"){
        val l=list(c).toMutableList();var changed=false
        for(i in l.indices)if(l[i].signalId==signalId&&l[i].status=="ARMED"){l[i]=l[i].copy(enabled=false,status=status);changed=true}
        if(changed)save(c,l)
    }
    fun delete(c:Context,id:String){save(c,list(c).filterNot{it.id==id})}
    fun reset(c:Context){prefs(c).edit().clear().apply()}
    fun days(c:Context):List<String>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return list(c).map{f.format(Date(it.createdAt))}.distinct().take(3)}
    fun forDay(c:Context,day:String):List<AlarmEntry>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return list(c).filter{f.format(Date(it.createdAt))==day}}
    private fun save(c:Context,l:List<AlarmEntry>){val a=JSONArray();l.take(200).forEach{a.put(toJson(it))};prefs(c).edit().putString("alarms",a.toString()).apply()}
    private fun toJson(e:AlarmEntry)=JSONObject().put("id",e.id).put("signalId",e.signalId).put("symbol",e.symbol).put("tf",e.timeframe).put("direction",e.direction).put("entry",e.entry).put("expiresAt",e.expiresAt).put("createdAt",e.createdAt).put("enabled",e.enabled).put("status",e.status).put("triggeredAt",e.triggeredAt)
    private fun fromJson(j:JSONObject)=AlarmEntry(j.getString("id"),j.getString("signalId"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.optLong("expiresAt",Long.MAX_VALUE),j.getLong("createdAt"),j.optBoolean("enabled",true),j.optString("status","ARMED"),if(j.isNull("triggeredAt"))null else j.optLong("triggeredAt"))
}
