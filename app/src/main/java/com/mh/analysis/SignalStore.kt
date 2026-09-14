package com.mh.analysis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object SignalStore {
    private const val PREF="mh_records"
    private fun prefs(c:Context)=c.getSharedPreferences(PREF,Context.MODE_PRIVATE)
    private fun activeKey(symbol:String)="active_${symbol.uppercase()}"

    fun loadActive(c:Context,symbol:String):ActiveSignal?{
        val raw=prefs(c).getString(activeKey(symbol),null)?:return null
        return runCatching{activeFromJson(JSONObject(raw))}.getOrNull()
    }

    fun saveActive(c:Context,a:ActiveSignal){prefs(c).edit().putString(activeKey(a.signal.symbol),activeToJson(a).toString()).apply()}
    fun clearActive(c:Context,symbol:String){prefs(c).edit().remove(activeKey(symbol)).apply()}

    fun replaceWith(c:Context,signal:Signal){
        loadActive(c,signal.symbol)?.let{old->
            if(old.state!="WIN"&&old.state!="LOSS"&&old.state!="EXPIRED") addRecord(c,toRecord(old,"REPLACED",System.currentTimeMillis()))
        }
        saveActive(c,ActiveSignal(signal))
    }

    fun evaluate(c:Context,symbol:String,candles:List<Candle>):ActiveSignal?{
        var active=loadActive(c,symbol)?:return null
        val s=active.signal
        val future=candles.filter{it.t>s.createdCandleTime}.take(s.validBars)
        if(future.isEmpty())return active
        var activatedAt=active.activatedAt
        var state=active.state
        var bars=0
        for(x in future){
            bars++
            if(activatedAt==null && x.l<=s.entry && x.h>=s.entry){activatedAt=x.t;state="ACTIVE"}
            if(activatedAt!=null){
                val hitSl=if(s.direction=="BUY")x.l<=s.sl else x.h>=s.sl
                val hitTp=if(s.direction=="BUY")x.h>=s.tp1 else x.l<=s.tp1
                if(hitSl){state="LOSS";break}
                if(hitTp){state="WIN";break}
            }
        }
        if(state!="WIN"&&state!="LOSS"&&future.size>=s.validBars)state="EXPIRED"
        active=ActiveSignal(s,activatedAt,bars,state)
        if(state=="WIN"||state=="LOSS"||state=="EXPIRED"){
            addRecord(c,toRecord(active,state,future.lastOrNull()?.t?:System.currentTimeMillis()));clearActive(c,symbol);return active
        }
        saveActive(c,active);return active
    }

    fun records(c:Context):List<TradeRecord>{
        val raw=prefs(c).getString("records","[]")?:"[]";val a=runCatching{JSONArray(raw)}.getOrElse{JSONArray()};val out=mutableListOf<TradeRecord>()
        for(i in 0 until a.length())runCatching{recordFromJson(a.getJSONObject(i))}.getOrNull()?.let{out+=it}
        return out.sortedByDescending{it.startedAt}
    }

    private fun addRecord(c:Context,r:TradeRecord){
        val list=records(c).toMutableList();if(list.none{it.id==r.id})list.add(0,r)
        val a=JSONArray();list.take(200).forEach{a.put(recordToJson(it))};prefs(c).edit().putString("records",a.toString()).apply()
    }

    fun stats(c:Context):String{
        val r=records(c);val w=r.count{it.result=="WIN"};val l=r.count{it.result=="LOSS"};val e=r.count{it.result=="EXPIRED"};val rep=r.count{it.result=="REPLACED"};val resolved=w+l
        val acc=if(resolved==0)0.0 else w*100.0/resolved
        return "Signals: ${r.size}   Wins: $w   Losses: $l\nExpired: $e   Replaced: $rep\nAccuracy (resolved): ${"%.1f".format(acc)}%   •   $w/$resolved correct"
    }

    private fun toRecord(a:ActiveSignal,result:String,end:Long)=TradeRecord(a.signal.id,a.signal.symbol,a.signal.timeframe,a.signal.direction,a.signal.entry,a.signal.sl,a.signal.tp1,a.signal.score,a.signal.createdAt,a.activatedAt,end,result)

    private fun signalToJson(s:Signal)=JSONObject().apply{
        put("id",s.id);put("symbol",s.symbol);put("tf",s.timeframe);put("direction",s.direction);put("entry",s.entry);put("sl",s.sl);put("tp1",s.tp1);put("tp2",s.tp2);put("score",s.score);put("bull",s.bullScore);put("bear",s.bearScore);put("valid",s.validBars);put("createdAt",s.createdAt);put("candle",s.createdCandleTime);put("status",s.status);put("ema20",s.ema20);put("ema50",s.ema50);put("rsi",s.rsi);put("macd",s.macd);put("atr",s.atr);put("fvgType",s.fvgType);put("fvgLow",s.fvgLow);put("fvgHigh",s.fvgHigh);val a=JSONArray();s.reasons.forEach{a.put(it)};put("reasons",a)
    }
    private fun signalFromJson(j:JSONObject):Signal{val a=j.optJSONArray("reasons")?:JSONArray();val rr=mutableListOf<String>();for(i in 0 until a.length())rr+=a.optString(i);fun nd(k:String):Double?=if(j.isNull(k))null else j.optDouble(k);return Signal(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getDouble("tp2"),j.getInt("score"),j.getInt("bull"),j.getInt("bear"),j.getInt("valid"),j.getLong("createdAt"),j.getLong("candle"),j.optString("status","PENDING"),rr,j.getDouble("ema20"),j.getDouble("ema50"),j.getDouble("rsi"),j.getDouble("macd"),j.getDouble("atr"),j.optString("fvgType").ifBlank{null},nd("fvgLow"),nd("fvgHigh"))}
    private fun activeToJson(a:ActiveSignal)=JSONObject().put("signal",signalToJson(a.signal)).put("activatedAt",a.activatedAt).put("bars",a.barsSeen).put("state",a.state)
    private fun activeFromJson(j:JSONObject)=ActiveSignal(signalFromJson(j.getJSONObject("signal")),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),j.optInt("bars",0),j.optString("state","PENDING"))
    private fun recordToJson(r:TradeRecord)=JSONObject().put("id",r.id).put("symbol",r.symbol).put("tf",r.timeframe).put("direction",r.direction).put("entry",r.entry).put("sl",r.sl).put("tp1",r.tp1).put("score",r.score).put("startedAt",r.startedAt).put("activatedAt",r.activatedAt).put("endedAt",r.endedAt).put("result",r.result)
    private fun recordFromJson(j:JSONObject)=TradeRecord(j.getString("id"),j.getString("symbol"),j.getString("tf"),j.getString("direction"),j.getDouble("entry"),j.getDouble("sl"),j.getDouble("tp1"),j.getInt("score"),j.getLong("startedAt"),if(j.isNull("activatedAt"))null else j.optLong("activatedAt"),if(j.isNull("endedAt"))null else j.optLong("endedAt"),j.getString("result"))
}
