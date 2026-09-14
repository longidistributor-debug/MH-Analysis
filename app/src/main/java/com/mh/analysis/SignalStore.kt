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
    private fun prefs(c:Context)=c.getSharedPreferences(PREF,Context.MODE_PRIVATE)
    private fun activeKey(symbol:String,timeframe:String)="active_${symbol.uppercase()}_${timeframe.lowercase()}"

    fun loadActive(c:Context,symbol:String,timeframe:String):ActiveSignal?{
        val raw=prefs(c).getString(activeKey(symbol,timeframe),null)?:return null
        return runCatching{activeFromJson(JSONObject(raw))}.getOrNull()
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
        val future=candles.filter{it.t>s.createdCandleTime}
        if(future.isEmpty())return pending

        var bars=0
        for((idx,x) in future.withIndex()){
            bars++
            if(x.l<=s.entry&&x.h>=s.entry){
                var triggered=ActiveSignal(s,x.t,bars,"ACTIVE")
                clearActive(c,s.symbol,s.timeframe)
                var result:String?=null
                var end:Long?=null
                for(y in future.drop(idx)){
                    val hitSl=if(s.direction=="BUY")y.l<=s.sl else y.h>=s.sl
                    val hitTp=if(s.direction=="BUY")y.h>=s.tp1 else y.l<=s.tp1
                    if(hitSl){result="LOSS";end=y.t;break}
                    if(hitTp){result="WIN";end=y.t;break}
                }
                if(result!=null){
                    triggered=triggered.copy(state=result)
                    addRecord(c,toRecord(triggered,result,end?:x.t))
                    removeOpen(c,s.id)
                }else addOpen(c,triggered)
                return triggered
            }
        }

        val check=AnalysisEngine.setupCheck(s,candles)
        if(!check.valid){
            val expired=pending.copy(barsSeen=bars,state="EXPIRED")
            addRecord(c,toRecord(expired,"EXPIRED",candles.last().t))
            AlarmStore.expireSignal(c,s.id,"EXPIRED")
            clearActive(c,s.symbol,s.timeframe)
            terminal=expired
            return terminal
        }
        val kept=pending.copy(barsSeen=bars,state="PENDING")
        saveActive(c,kept)
        return kept
    }

    private fun evaluateOpenTrades(c:Context,symbol:String,timeframe:String,candles:List<Candle>):ActiveSignal?{
        val all=openTrades(c).toMutableList()
        var terminal:ActiveSignal?=null
        var changed=false
        val it=all.listIterator()
        while(it.hasNext()){
            val a=it.next();val s=a.signal
            if(s.symbol!=symbol||s.timeframe!=timeframe)continue
            val start=a.activatedAt?:s.createdCandleTime
            val future=candles.filter{it.t>=start}
            var result:String?=null;var end:Long?=null
            for(x in future){
                val hitSl=if(s.direction=="BUY")x.l<=s.sl else x.h>=s.sl
                val hitTp=if(s.direction=="BUY")x.h>=s.tp1 else x.l<=s.tp1
                if(hitSl){result="LOSS";end=x.t;break}
                if(hitTp){result="WIN";end=x.t;break}
            }
            if(result!=null){
                val done=a.copy(state=result)
                addRecord(c,toRecord(done,result,end?:System.currentTimeMillis()))
                it.remove();changed=true;terminal=done
            }
        }
        if(changed)saveOpen(c,all)
        return terminal
    }

    fun openTrades(c:Context):List<ActiveSignal>{
        val cutoff=System.currentTimeMillis()-KEEP_MS
        val raw=prefs(c).getString("open_trades","[]")?:"[]"
        val arr=runCatching{JSONArray(raw)}.getOrElse{JSONArray()}
        val out=mutableListOf<ActiveSignal>()
        for(i in 0 until arr.length())runCatching{activeFromJson(arr.getJSONObject(i))}.getOrNull()?.let{if(it.signal.createdAt>=cutoff)out+=it}
        val sorted=out.sortedByDescending{it.signal.createdAt};saveOpen(c,sorted);return sorted
    }

    private fun addOpen(c:Context,a:ActiveSignal){val l=openTrades(c).toMutableList();if(l.none{it.signal.id==a.signal.id})l.add(0,a);saveOpen(c,l)}
    private fun removeOpen(c:Context,id:String){saveOpen(c,openTrades(c).filterNot{it.signal.id==id})}
    private fun saveOpen(c:Context,l:List<ActiveSignal>){val a=JSONArray();l.take(100).forEach{a.put(activeToJson(it))};prefs(c).edit().putString("open_trades",a.toString()).apply()}

    fun records(c:Context):List<TradeRecord>{
        val cutoff=System.currentTimeMillis()-KEEP_MS
        val raw=prefs(c).getString("records","[]")?:"[]"
        val arr=runCatching{JSONArray(raw)}.getOrElse{JSONArray()}
        val out=mutableListOf<TradeRecord>()
        for(i in 0 until arr.length())runCatching{recordFromJson(arr.getJSONObject(i))}.getOrNull()?.let{if(it.startedAt>=cutoff)out+=it}
        val sorted=out.sortedByDescending{it.startedAt};persistRecords(c,sorted);return sorted
    }

    fun days(c:Context):List<String>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return records(c).map{f.format(Date(it.startedAt))}.distinct().take(3)}
    fun recordsForDay(c:Context,day:String):List<TradeRecord>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return records(c).filter{f.format(Date(it.startedAt))==day}}
    fun openForDay(c:Context,day:String):List<ActiveSignal>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return openTrades(c).filter{f.format(Date(it.signal.createdAt))==day}}
    fun reset(c:Context){prefs(c).edit().clear().apply()}

    private fun addRecord(c:Context,r:TradeRecord){val l=records(c).toMutableList();val i=l.indexOfFirst{it.id==r.id};if(i>=0)l[i]=r else l.add(0,r);persistRecords(c,l)}
    private fun persistRecords(c:Context,l:List<TradeRecord>){val a=JSONArray();l.take(200).forEach{a.put(recordToJson(it))};prefs(c).edit().putString("records",a.toString()).apply()}

    fun stats(c:Context,day:String?=null):String{
        val r=if(day==null)records(c)else recordsForDay(c,day)
        val open=if(day==null)openTrades(c).size else openForDay(c,day).size
        val wins=r.count{it.result=="WIN"};val losses=r.count{it.result=="LOSS"};val expired=r.count{it.result=="EXPIRED"};val resolved=wins+losses
        val acc=if(resolved==0)0.0 else wins*100.0/resolved
        return "Resolved trades: $resolved   Open: $open\nWins: $wins   Losses: $losses   Expired pending: $expired\nWin ratio: ${String.format(Locale.US,"%.1f",acc)}%   •   $wins/$resolved wins"
    }

    private fun toRecord(a:ActiveSignal,result:String,end:Long):TradeRecord{val s=a.signal;return TradeRecord(s.id,s.symbol,s.timeframe,s.direction,s.entry,s.sl,s.tp1,s.score,s.createdAt,a.activatedAt,end,result)}

    private fun signalToJson(s:Signal):JSONObject{
        val reasons=JSONArray();s.reasons.forEach{reasons.put(it)}
        return JSONObject().put("id",s.id).put("symbol",s.symbol).put("tf",s.timeframe).put("direction",s.direction)
            .put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score).put("bull",s.bullScore).put("bear",s.bearScore).put("valid",s.validBars)
            .put("createdAt",s.createdAt).put("candle",s.createdCandleTime).put("status",s.status).put("ema20",s.ema20).put("ema50",s.ema50).put("rsi",s.rsi).put("macd",s.macd).put("atr",s.atr)
            .put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh).put("validityReason",s.validityReason).put("slReason",s.slReason).put("tp1Reason",s.tp1Reason).put("tp2Reason",s.tp2Reason).put("setupReason",s.setupReason).put("reasons",reasons)
    }

    private fun signalFromJson(j:JSONObject):Signal{
        val a=j.optJSONArray("reasons")?:JSONArray();val reasons=mutableListOf<String>();for(i in 0 until a.length())reasons+=a.optString(i)
        val low=if(j.isNull("fvgLow"))null else j.optDouble("fvgLow");val high=if(j.isNull("fvgHigh"))null else j.optDouble("fvgHigh");val type=j.optString("fvgType").ifBlank{null}
        return Signal(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getDouble("tp2"),j.getInt("score"),j.getInt("bull"),j.getInt("bear"),j.optInt("valid",0),j.getLong("createdAt"),j.getLong("candle"),j.optString("status","PENDING"),reasons,j.getDouble("ema20"),j.getDouble("ema50"),j.getDouble("rsi"),j.getDouble("macd"),j.getDouble("atr"),type,low,high,j.optString("validityReason","No fixed time expiry; valid until structure/confirmation changes."),j.optString("slReason","SL uses volatility and structure."),j.optString("tp1Reason","TP1 uses volatility and structure."),j.optString("tp2Reason","TP2 uses volatility and structure."),j.optString("setupReason","Weighted confluence setup."))
    }

    private fun activeToJson(a:ActiveSignal)=JSONObject().put("signal",signalToJson(a.signal)).put("activatedAt",a.activatedAt).put("bars",a.barsSeen).put("state",a.state)
    private fun activeFromJson(j:JSONObject)=ActiveSignal(signalFromJson(j.getJSONObject("signal")),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),j.optInt("bars",0),j.optString("state","PENDING"))
    private fun recordToJson(r:TradeRecord)=JSONObject().put("id",r.id).put("symbol",r.symbol).put("tf",r.timeframe).put("direction",r.direction).put("entry",r.entry).put("sl",r.sl).put("tp1",r.tp1).put("score",r.score).put("startedAt",r.startedAt).put("activatedAt",r.activatedAt).put("endedAt",r.endedAt).put("result",r.result)
    private fun recordFromJson(j:JSONObject)=TradeRecord(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getInt("score"),j.getLong("startedAt"),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),if(j.isNull("endedAt"))null else j.optLong("endedAt"),j.getString("result"))
}
