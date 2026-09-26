package com.mh.analysis

import android.content.Context
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** V.08 bounded quality layer. No network I/O. */
object ProQualityEngine {
    data class Assessment(
        val blocked:Boolean,
        val adjustment:Int,
        val grade:String,
        val regime:String,
        val summary:String,
        val breakdown:String,
        val stats:String,
        val invalidation:String
    )

    fun assess(context:Context,symbol:String,timeframe:String,c:List<Candle>,s:Signal?):Assessment {
        val dq=dataQuality(c,timeframe)
        if(dq.first) return Assessment(true,-99,"D","UNKNOWN",dq.second,"Data quality BLOCK",outcomeStats(context,symbol,timeframe),"Setup invalid because source data quality failed")
        if(s==null) return Assessment(false,0,"N/A",regime(c),dq.second,"No candidate score breakdown",outcomeStats(context,symbol,timeframe),"No active setup")

        val a=atr(c,14).coerceAtLeast(1e-9)
        val closes=c.map{it.c}
        val e20=ema(closes,20)
        val e50=ema(closes,50)
        val r=rsi(closes,14)
        val rg=regime(c)
        var adj=0
        val parts=mutableListOf<String>()

        val trendAligned=(s.direction=="BUY"&&e20>e50)||(s.direction=="SELL"&&e20<e50)
        val momentumAligned=(s.direction=="BUY"&&r>=50)||(s.direction=="SELL"&&r<=50)
        val hardConflict=(s.direction=="BUY"&&e20<e50&&r<43)||(s.direction=="SELL"&&e20>e50&&r>57)
        if(hardConflict&&s.score<84) return Assessment(true,-99,"D",rg,"Conflict engine blocked setup: EMA trend and RSI momentum strongly oppose ${s.direction}.","Conflict BLOCK",outcomeStats(context,symbol,timeframe),"Invalid while trend/momentum conflict remains")
        if(trendAligned){adj+=3;parts+="Trend +3"} else {adj-=3;parts+="Trend -3"}
        if(momentumAligned){adj+=2;parts+="Momentum +2"} else {adj-=2;parts+="Momentum -2"}

        val breakoutLike=s.reasons.any{it.contains("break",true)||it.contains("BOS",true)||it.contains("displacement",true)||it.contains("retest",true)}
        val regimeAdj=when(rg){
            "TRENDING"->if(trendAligned)3 else -4
            "COMPRESSION"->if(breakoutLike)2 else -3
            "EXPANSION"->if(breakoutLike)2 else -2
            else->if(s.reasons.any{it.contains("sweep",true)||it.contains("reclaim",true)||it.contains("rejection",true)})2 else 0
        }
        adj+=regimeAdj;parts+="Regime ${signed(regimeAdj)}"

        val risk=abs(s.entry-s.sl).coerceAtLeast(1e-9)
        val rr=abs(s.tp1-s.entry)/risk
        val rrAdj=when{rr>=1.5->3;rr>=1.1->1;rr<0.75->-7;rr<1.0->-3;else->0}
        adj+=rrAdj;parts+="RR ${signed(rrAdj)}"

        val recent=c.takeLast(min(70,c.size)).dropLast(1)
        val room=if(s.direction=="BUY"){
            val opp=recent.filter{it.h>s.entry}.minOfOrNull{it.h}
            if(opp==null)Double.POSITIVE_INFINITY else opp-s.entry
        }else{
            val opp=recent.filter{it.l<s.entry}.maxOfOrNull{it.l}
            if(opp==null)Double.POSITIVE_INFINITY else s.entry-opp
        }
        val roomR=room/risk
        if(roomR.isFinite()&&roomR<0.35) return Assessment(true,-99,"D",rg,"Room-to-target guard blocked setup: opposing structure is only ${one(roomR)}R away.","Room BLOCK",outcomeStats(context,symbol,timeframe),"Invalid until price has sufficient room beyond nearby opposing structure")
        val roomAdj=when{!roomR.isFinite()->2;roomR>=1.5->2;roomR<0.7->-5;roomR<1.0->-2;else->0}
        adj+=roomAdj;parts+="Room ${signed(roomAdj)}"

        val bodyQuality=c.takeLast(20).map{abs(it.c-it.o)/(it.h-it.l).coerceAtLeast(1e-9)}.average()
        val candleAdj=when{bodyQuality>=.55->2;bodyQuality<.28->-2;else->0}
        adj+=candleAdj;parts+="Candle quality ${signed(candleAdj)}"

        val bounded=adj.coerceIn(-12,10)
        val projected=(s.score+bounded).coerceIn(0,99)
        val grade=when{projected>=90&&rr>=1.2->"A+";projected>=84->"A";projected>=76->"B+";projected>=68->"B";else->"C"}
        val stats=outcomeStats(context,symbol,timeframe)
        val invalidation="Invalidation: ${s.validityReason} • structural SL ${price(s.sl)}"
        val summary="Quality grade $grade • $rg regime • RR ${one(rr)}R • room ${if(roomR.isFinite())one(roomR)+"R" else "clear"} • data ${dq.second}"
        return Assessment(false,bounded,grade,rg,summary,parts.joinToString(" | "),stats,invalidation)
    }

    private fun dataQuality(c:List<Candle>,tf:String):Pair<Boolean,String>{
        if(c.size<100)return true to "insufficient candles (${c.size})"
        val invalid=c.count{it.h<max(it.o,it.c)||it.l>min(it.o,it.c)||it.h<it.l||!it.o.isFinite()||!it.h.isFinite()||!it.l.isFinite()||!it.c.isFinite()}
        val ts=c.map{normTs(it.t)}
        val duplicates=ts.size-ts.distinct().size
        val backward=ts.zipWithNext().count{it.second<it.first}
        if(invalid>0)return true to "$invalid invalid OHLC candle(s)"
        if(duplicates>max(2,c.size/20))return true to "too many duplicate timestamps ($duplicates)"
        if(backward>max(2,c.size/20))return true to "timestamp order is unreliable ($backward reversals)"
        val mins=tfMinutes(tf)
        val last=ts.lastOrNull()?:0L
        val age=if(last>0)(System.currentTimeMillis()-last).coerceAtLeast(0L)/60000L else 0L
        val stale=last>0&&age>max(20L,mins*4L)
        return false to if(stale)"CAUTION: last candle ${age}m old" else "GOOD (${c.size} candles, timestamps clean)"
    }

    private fun regime(c:List<Candle>):String{
        if(c.size<70)return "UNKNOWN"
        val closes=c.map{it.c};val a14=atr(c,14).coerceAtLeast(1e-9);val a50=atr(c,50).coerceAtLeast(1e-9)
        val sep=abs(ema(closes,20)-ema(closes,50))/a14
        val recentRange=c.takeLast(12).maxOf{it.h}-c.takeLast(12).minOf{it.l}
        return when{
            a14/a50>=1.45->"EXPANSION"
            recentRange/a14<=3.6->"COMPRESSION"
            sep>=0.9->"TRENDING"
            else->"RANGE"
        }
    }

    private fun outcomeStats(context:Context,symbol:String,timeframe:String):String{
        val r=SignalStore.records(context).filter{it.symbol==symbol&&it.timeframe==timeframe&&it.result in setOf("WIN","LOSS")}.take(60)
        val n=r.size;val w=r.count{it.result=="WIN"}
        if(n==0)return "Outcome stats: no resolved local setups yet"
        val wr=w*100.0/n
        val confidence=when{n>=30->"HIGH";n>=12->"MEDIUM";else->"LOW"}
        return "Outcome stats: $w/$n wins (${one(wr)}%) • calibration confidence $confidence"
    }

    private fun ema(v:List<Double>,n:Int):Double{if(v.isEmpty())return 0.0;val k=2.0/(n+1.0);var e=v.first();for(i in 1 until v.size)e=v[i]*k+e*(1-k);return e}
    private fun rsi(v:List<Double>,n:Int):Double{if(v.size<n+1)return 50.0;var g=0.0;var l=0.0;for(i in max(1,v.size-n) until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l<=1e-12)return 100.0;val rs=g/l;return 100.0-100.0/(1.0+rs)}
    private fun atr(c:List<Candle>,n:Int):Double{if(c.size<2)return 0.0;val tr=mutableListOf<Double>();for(i in 1 until c.size){val p=c[i-1].c;val x=c[i];tr+=max(x.h-x.l,max(abs(x.h-p),abs(x.l-p)))};return tr.takeLast(min(n,tr.size)).average()}
    private fun normTs(t:Long)=if(t<10_000_000_000L)t*1000L else t
    private fun tfMinutes(tf:String)=when(tf){"1m"->1L;"5m"->5L;"15m"->15L;"30m"->30L;"1h"->60L;else->15L}
    private fun signed(v:Int)=if(v>0)"+$v" else "$v"
    private fun one(v:Double)=String.format(java.util.Locale.US,"%.1f",v)
    private fun price(v:Double)=String.format(java.util.Locale.US,"%.5f",v)
}
