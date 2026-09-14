package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object SignalStore {
    private const val PREF="mh_records"
    private const val KEEP_MS=3L*24*60*60*1000
    data class ProcessEvent(val signal:Signal,val state:String,val at:Long)
    private fun prefs(c:Context)=c.getSharedPreferences(PREF,Context.MODE_PRIVATE)
    private fun activeKey(symbol:String,timeframe:String)="active_${symbol.uppercase()}_${timeframe.lowercase()}"

    fun loadActive(c:Context,symbol:String,timeframe:String):ActiveSignal?{
        val raw=prefs(c).getString(activeKey(symbol,timeframe),null)?:return null
        return runCatching{activeFromJson(JSONObject(raw))}.getOrNull()
    }
    fun pendingSignals(c:Context):List<ActiveSignal>{
        return prefs(c).all.entries.filter{it.key.startsWith("active_")}.mapNotNull{e->
            val raw=e.value as? String ?: return@mapNotNull null
            runCatching{activeFromJson(JSONObject(raw))}.getOrNull()
        }.filter{it.state=="PENDING"}
    }
    fun saveActive(c:Context,a:ActiveSignal){prefs(c).edit().putString(activeKey(a.signal.symbol,a.signal.timeframe),activeToJson(a).toString()).apply()}
    fun clearActive(c:Context,symbol:String,timeframe:String){prefs(c).edit().remove(activeKey(symbol,timeframe)).apply()}

    fun findDuplicate(c:Context,candidate:Signal):ActiveSignal?{
        val pending=loadActive(c,candidate.symbol,candidate.timeframe)
        if(pending!=null&&AnalysisEngine.sameSetup(pending.signal,candidate))return pending
        return openTrades(c).firstOrNull{it.signal.symbol==candidate.symbol&&it.signal.timeframe==candidate.timeframe&&AnalysisEngine.sameSetup(it.signal,candidate)}
    }
    fun acceptCandidate(c:Context,candidate:Signal):Boolean{
        if(findDuplicate(c,candidate)!=null)return false
        val old=loadActive(c,candidate.symbol,candidate.timeframe)
        if(old!=null){
            addRecord(c,toRecord(old,"EXPIRED",System.currentTimeMillis()))
            AlarmStore.expireSignal(c,old.signal.id,"EXPIRED")
            clearActive(c,old.signal.symbol,old.signal.timeframe)
        }
        saveActive(c,ActiveSignal(candidate,state="PENDING"))
        return true
    }

    fun evaluate(c:Context,symbol:String,timeframe:String,candles:List<Candle>):ActiveSignal?{
        var terminal=evaluateOpenTrades(c,symbol,timeframe,candles)
        val pending=loadActive(c,symbol,timeframe)?:return terminal
        val s=pending.signal
        val future=candles.filter{toMillis(it.t)>maxOf(toMillis(s.createdCandleTime),s.createdAt)}
        if(future.isEmpty())return pending
        for(x in future){
            val events=processMinuteCandle(c,symbol,x)
            val mine=events.lastOrNull{it.signal.id==s.id}
            if(mine!=null)return when(mine.state){
                "ACTIVE"->openTrades(c).firstOrNull{it.signal.id==s.id}
                else->ActiveSignal(s,null,0,mine.state)
            }
        }
        val current=loadActive(c,symbol,timeframe)?:return terminal
        val check=AnalysisEngine.setupCheck(current.signal,candles)
        if(!check.valid){
            val expired=current.copy(state="EXPIRED")
            addRecord(c,toRecord(expired,"EXPIRED",toMillis(candles.last().t)))
            AlarmStore.expireSignal(c,current.signal.id,"EXPIRED")
            clearActive(c,current.signal.symbol,current.signal.timeframe)
            terminal=expired
        }
        return terminal?:loadActive(c,symbol,timeframe)
    }

    fun processMinuteCandle(c:Context,symbol:String,x:Candle):List<ProcessEvent>{
        val events=mutableListOf<ProcessEvent>()
        val t=toMillis(x.t)
        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->
            val s=pending.signal
            if(t<=maxOf(toMillis(s.createdCandleTime),s.createdAt))return@forEach
            val touched=x.l<=s.entry&&x.h>=s.entry
            val missed=if(s.direction=="BUY") x.l>s.entry+s.atr*1.25 else x.h<s.entry-s.atr*1.25
            if(touched){
                clearActive(c,s.symbol,s.timeframe)
                var active=ActiveSignal(s,t,pending.barsSeen+1,"ACTIVE")
                AlarmStore.expireSignal(c,s.id,"TRIGGERED")
                val hitSl=if(s.direction=="BUY")x.l<=s.sl else x.h>=s.sl
                val hitTp=if(s.direction=="BUY")x.h>=s.tp1 else x.l<=s.tp1
                if(hitSl||hitTp){
                    val result=if(hitSl)"LOSS" else "WIN"
                    active=active.copy(state=result)
                    addRecord(c,toRecord(active,result,t));events+=ProcessEvent(s,result,t)
                }else{
                    addOpen(c,active);events+=ProcessEvent(s,"ACTIVE",t)
                }
            }else if(missed){
                val expired=pending.copy(state="EXPIRED")
                addRecord(c,toRecord(expired,"EXPIRED",t));AlarmStore.expireSignal(c,s.id,"EXPIRED");clearActive(c,s.symbol,s.timeframe)
                events+=ProcessEvent(s,"EXPIRED",t)
            }
        }
        val all=openTrades(c).toMutableList();var changed=false
        val it=all.listIterator()
        while(it.hasNext()){
            val a=it.next();val s=a.signal
            if(s.symbol!=symbol||t<(a.activatedAt?:0L))continue
            val hitSl=if(s.direction=="BUY")x.l<=s.sl else x.h>=s.sl
            val hitTp=if(s.direction=="BUY")x.h>=s.tp1 else x.l<=s.tp1
            if(hitSl||hitTp){
                val result=if(hitSl)"LOSS" else "WIN";val done=a.copy(state=result)
                addRecord(c,toRecord(done,result,t));it.remove();changed=true;events+=ProcessEvent(s,result,t)
            }
        }
        if(changed)saveOpen(c,all)
        return events
    }

    private fun evaluateOpenTrades(c:Context,symbol:String,timeframe:String,candles:List<Candle>):ActiveSignal?{
        var terminal:ActiveSignal?=null
        candles.forEach{x->
            processMinuteCandle(c,symbol,x).lastOrNull{it.signal.timeframe==timeframe&&it.state in setOf("WIN","LOSS")}?.let{e->terminal=ActiveSignal(e.signal,e.at,0,e.state)}
        }
        return terminal
    }

    fun openTrades(c:Context):List<ActiveSignal>{
        val cutoff=System.currentTimeMillis()-KEEP_MS
        val raw=prefs(c).getString("open_trades","[]")?:"[]";val arr=runCatching{JSONArray(raw)}.getOrElse{JSONArray()};val out=mutableListOf<ActiveSignal>()
        for(i in 0 until arr.length())runCatching{activeFromJson(arr.getJSONObject(i))}.getOrNull()?.let{if(it.signal.createdAt>=cutoff)out+=it}
        val sorted=out.sortedByDescending{it.signal.createdAt};saveOpen(c,sorted);return sorted
    }
    private fun addOpen(c:Context,a:ActiveSignal){val l=openTrades(c).toMutableList();if(l.none{it.signal.id==a.signal.id})l.add(0,a);saveOpen(c,l)}
    private fun saveOpen(c:Context,l:List<ActiveSignal>){val a=JSONArray();l.take(100).forEach{a.put(activeToJson(it))};prefs(c).edit().putString("open_trades",a.toString()).apply()}

    fun records(c:Context):List<TradeRecord>{
        val cutoff=System.currentTimeMillis()-KEEP_MS;val raw=prefs(c).getString("records","[]")?:"[]";val arr=runCatching{JSONArray(raw)}.getOrElse{JSONArray()};val out=mutableListOf<TradeRecord>()
        for(i in 0 until arr.length())runCatching{recordFromJson(arr.getJSONObject(i))}.getOrNull()?.let{if(it.startedAt>=cutoff)out+=it}
        val sorted=out.sortedByDescending{it.startedAt};persistRecords(c,sorted);return sorted
    }
    fun recordsForDay(c:Context,day:String):List<TradeRecord>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return records(c).filter{f.format(Date(it.startedAt))==day}}
    fun openForDay(c:Context,day:String):List<ActiveSignal>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return openTrades(c).filter{f.format(Date(it.signal.createdAt))==day}}
    fun reset(c:Context){prefs(c).edit().clear().apply()}
    private fun addRecord(c:Context,r:TradeRecord){val l=records(c).toMutableList();val i=l.indexOfFirst{it.id==r.id};if(i>=0)l[i]=r else l.add(0,r);persistRecords(c,l)}
    private fun persistRecords(c:Context,l:List<TradeRecord>){val a=JSONArray();l.take(200).forEach{a.put(recordToJson(it))};prefs(c).edit().putString("records",a.toString()).apply()}
    fun stats(c:Context,day:String?=null):String{
        val r=if(day==null)records(c)else recordsForDay(c,day);val open=if(day==null)openTrades(c).size else openForDay(c,day).size
        val wins=r.count{it.result=="WIN"};val losses=r.count{it.result=="LOSS"};val expired=r.count{it.result=="EXPIRED"};val resolved=wins+losses;val total=r.size+open
        val winRate=if(resolved==0)0.0 else wins*100.0/resolved;val lossRate=if(resolved==0)0.0 else losses*100.0/resolved;val expRate=if(total==0)0.0 else expired*100.0/total
        return "Signals: $total   Open: $open   Resolved: $resolved\nWins: $wins (${one(winRate)}%)   Losses: $losses (${one(lossRate)}%)\nExpired/Missed: $expired (${one(expRate)}%)   Win ratio: ${one(winRate)}%"
    }

    fun isStale(a:ActiveSignal):Boolean{
        val tf=when(a.signal.timeframe.lowercase()){
            "3m"->180_000L;"5m"->300_000L;"10m"->600_000L;"15m"->900_000L;"30m"->1_800_000L;
            "1h"->3_600_000L;"2h"->7_200_000L;"4h"->14_400_000L;"6h"->21_600_000L;"12h"->43_200_000L;
            "1d","1day"->86_400_000L;else->900_000L
        }
        val limit=maxOf(30*60_000L,tf*3)
        return System.currentTimeMillis()-a.signal.createdAt>limit
    }

    private fun toRecord(a:ActiveSignal,result:String,end:Long):TradeRecord{val s=a.signal;return TradeRecord(s.id,s.symbol,s.timeframe,s.direction,s.entry,s.sl,s.tp1,s.score,s.createdAt,a.activatedAt,end,result)}
    private fun signalToJson(s:Signal):JSONObject{val reasons=JSONArray();s.reasons.forEach{reasons.put(it)};return JSONObject().put("id",s.id).put("symbol",s.symbol).put("tf",s.timeframe).put("direction",s.direction).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score).put("bull",s.bullScore).put("bear",s.bearScore).put("valid",s.validBars).put("createdAt",s.createdAt).put("candle",s.createdCandleTime).put("status",s.status).put("ema20",s.ema20).put("ema50",s.ema50).put("rsi",s.rsi).put("macd",s.macd).put("atr",s.atr).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh).put("validityReason",s.validityReason).put("slReason",s.slReason).put("tp1Reason",s.tp1Reason).put("tp2Reason",s.tp2Reason).put("setupReason",s.setupReason).put("reasons",reasons)}
    private fun signalFromJson(j:JSONObject):Signal{val a=j.optJSONArray("reasons")?:JSONArray();val reasons=mutableListOf<String>();for(i in 0 until a.length())reasons+=a.optString(i);val low=if(j.isNull("fvgLow"))null else j.optDouble("fvgLow");val high=if(j.isNull("fvgHigh"))null else j.optDouble("fvgHigh");val type=j.optString("fvgType").ifBlank{null};return Signal(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getDouble("tp2"),j.getInt("score"),j.getInt("bull"),j.getInt("bear"),j.optInt("valid",0),j.getLong("createdAt"),j.getLong("candle"),j.optString("status","PENDING"),reasons,j.getDouble("ema20"),j.getDouble("ema50"),j.getDouble("rsi"),j.getDouble("macd"),j.getDouble("atr"),type,low,high,j.optString("validityReason","Structure driven."),j.optString("slReason","Structure/ATR stop."),j.optString("tp1Reason","Structure/ATR target."),j.optString("tp2Reason","Extended structure target."),j.optString("setupReason","Weighted confluence."))}
    private fun activeToJson(a:ActiveSignal)=JSONObject().put("signal",signalToJson(a.signal)).put("activatedAt",a.activatedAt).put("bars",a.barsSeen).put("state",a.state)
    private fun activeFromJson(j:JSONObject)=ActiveSignal(signalFromJson(j.getJSONObject("signal")),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),j.optInt("bars",0),j.optString("state","PENDING"))
    private fun recordToJson(r:TradeRecord)=JSONObject().put("id",r.id).put("symbol",r.symbol).put("tf",r.timeframe).put("direction",r.direction).put("entry",r.entry).put("sl",r.sl).put("tp1",r.tp1).put("score",r.score).put("startedAt",r.startedAt).put("activatedAt",r.activatedAt).put("endedAt",r.endedAt).put("result",r.result)
    private fun recordFromJson(j:JSONObject)=TradeRecord(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getInt("score"),j.getLong("startedAt"),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),if(j.isNull("endedAt"))null else j.optLong("endedAt"),j.getString("result"))
    private fun toMillis(t:Long)=if(t in 1..9_999_999_999L)t*1000L else t
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v)
}
