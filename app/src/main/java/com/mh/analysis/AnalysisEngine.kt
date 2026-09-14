package com.mh.analysis

import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

object AnalysisEngine {
    data class SetupCheck(val valid:Boolean,val reason:String)

    fun analyze(symbol:String,timeframe:String,c:List<Candle>):Signal?{
        if(c.size<80)return null
        val close=c.map{it.c}
        val last=c.last()
        val prev=c[c.lastIndex-1]
        val e20=ema(close,20).last()
        val e50=ema(close,50).last()
        val e150=ema(close,min(150,c.size-1)).last()
        val r=rsi(close,14)
        val a=atr(c,14).coerceAtLeast(1e-9)
        val macd=ema(close,12).last()-ema(close,26).last()
        val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val basis=close.takeLast(20).average()
        val sd=stdev(close.takeLast(20))
        val upper=basis+2*sd
        val lower=basis-2*sd
        val recent=c.takeLast(55)
        val swingHigh=recent.dropLast(2).maxOf{it.h}
        val swingLow=recent.dropLast(2).minOf{it.l}
        val local=c.takeLast(16).dropLast(1)
        val localHigh=local.maxOf{it.h}
        val localLow=local.minOf{it.l}
        val prior=c.takeLast(38).dropLast(4)
        val priorHigh=prior.maxOf{it.h}
        val priorLow=prior.minOf{it.l}

        var bull=0
        var bear=0
        val br=mutableListOf<Pair<Int,String>>()
        val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,s:String){bull+=p;br+=p to s}
        fun s(p:Int,x:String){bear+=p;sr+=p to x}

        if(e20>e50)b(14,"EMA20 is above EMA50") else s(14,"EMA20 is below EMA50")
        if(last.c>e150)b(7,"Price is above EMA150") else s(7,"Price is below EMA150")
        if(e20>ema(close.dropLast(1),20).last())b(5,"EMA20 is rising") else s(5,"EMA20 is falling")
        when{
            r>=55->b(9,"RSI14 is bullish at ${one(r)}")
            r<=45->s(9,"RSI14 is bearish at ${one(r)}")
            else->{b(2,"RSI14 is neutral at ${one(r)}");s(2,"RSI14 is neutral at ${one(r)}")}
        }
        if(macd>0)b(8,"MACD is above zero") else s(8,"MACD is below zero")
        if(macd>macdPrev)b(5,"MACD momentum is rising") else s(5,"MACD momentum is falling")
        if(last.c>priorHigh)b(17,"Bullish BOS / breakout is confirmed")
        if(last.c<priorLow)s(17,"Bearish BOS / breakout is confirmed")
        if(last.l<priorLow&&last.c>priorLow)b(16,"Sell-side liquidity sweep is visible")
        if(last.h>priorHigh&&last.c<priorHigh)s(16,"Buy-side liquidity sweep is visible")

        val before=c.takeLast(32).dropLast(3)
        val upSeq=before.takeLast(8).zipWithNext().count{it.second.c>it.first.c}>=5
        val downSeq=before.takeLast(8).zipWithNext().count{it.second.c<it.first.c}>=5
        if(downSeq&&last.c>before.takeLast(10).maxOf{it.h})b(13,"Bullish CHoCH is confirmed")
        if(upSeq&&last.c<before.takeLast(10).minOf{it.l})s(13,"Bearish CHoCH is confirmed")

        var fvgType:String?=null
        var fvgLow:Double?=null
        var fvgHigh:Double?=null
        val fw=c.takeLast(24)
        for(i in 2 until fw.size){
            if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l}
            if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}
        }
        if(fvgType=="BULLISH")b(9,"Bullish FVG exists at ${fmt(fvgLow)} - ${fmt(fvgHigh)}")
        if(fvgType=="BEARISH")s(9,"Bearish FVG exists at ${fmt(fvgLow)} - ${fmt(fvgHigh)}")
        if(last.c-last.o>a*.45&&c.takeLast(7).dropLast(1).any{it.c<it.o})b(8,"Bullish displacement / order-block context")
        if(last.o-last.c>a*.45&&c.takeLast(7).dropLast(1).any{it.c>it.o})s(8,"Bearish displacement / order-block context")
        if(abs(last.c-swingLow)<=a*1.2)b(7,"Price is near structural support")
        if(abs(last.c-swingHigh)<=a*1.2)s(7,"Price is near structural resistance")
        if(last.c<=lower)b(6,"Price is near the lower Bollinger band")
        if(last.c>=upper)s(6,"Price is near the upper Bollinger band")
        val mom=c.takeLast(4).last().c-c.takeLast(4).first().c
        if(mom>a*.35)b(6,"Short-term momentum is bullish") else if(mom< -a*.35)s(6,"Short-term momentum is bearish")

        val dir=if(bull>=bear)"BUY" else "SELL"
        val win=max(bull,bear)
        val lose=min(bull,bear)
        val sep=win-lose
        if(win<40||sep<7)return null

        val score=(52+sep*2+(win-40)/2).coerceIn(52,96)
        val matchingFvg=(dir=="BUY"&&fvgType=="BULLISH")||(dir=="SELL"&&fvgType=="BEARISH")
        val fvgMid=if(matchingFvg&&fvgLow!=null&&fvgHigh!=null)(fvgLow!!+fvgHigh!!)/2.0 else null
        val entry=when{
            fvgMid!=null && abs(last.c-fvgMid)<=a*1.6 -> fvgMid
            dir=="BUY" && e20<last.c && last.c-e20<=a*1.1 -> e20
            dir=="SELL" && e20>last.c && e20-last.c<=a*1.1 -> e20
            else -> last.c
        }

        val tf=tfMinutes(timeframe)
        val slAtr=when{tf<=1->0.55;tf<=5->0.65;tf<=15->0.78;tf<=30->0.88;tf<=60->1.0;tf<=240->1.15;else->1.30}
        val maxRiskAtr=when{tf<=5->0.90;tf<=15->1.05;tf<=30->1.20;tf<=60->1.35;else->1.60}
        val structureRisk=if(dir=="BUY")entry-(localLow-a*.08) else (localHigh+a*.08)-entry
        val baseRisk=max(a*slAtr,abs(last.c-prev.c)*1.15)
        val risk=max(baseRisk,min(max(structureRisk,0.0),a*maxRiskAtr)).coerceAtMost(a*maxRiskAtr)
        val sl=if(dir=="BUY")entry-risk else entry+risk

        val tp1Atr=when{tf<=1->0.65;tf<=5->0.85;tf<=15->1.00;tf<=30->1.15;tf<=60->1.35;tf<=240->1.60;else->1.90}
        val tp2Atr=when{tf<=1->1.00;tf<=5->1.20;tf<=15->1.45;tf<=30->1.65;tf<=60->1.95;tf<=240->2.30;else->2.70}
        val rawTp1=if(dir=="BUY")entry+a*tp1Atr else entry-a*tp1Atr
        val rawTp2=if(dir=="BUY")entry+a*tp2Atr else entry-a*tp2Atr
        val nearestStructure=if(dir=="BUY") listOf(localHigh,priorHigh,swingHigh).filter{it>entry+a*.25}.minOrNull() else listOf(localLow,priorLow,swingLow).filter{it<entry-a*.25}.maxOrNull()
        val tp1=if(nearestStructure!=null){if(dir=="BUY")min(rawTp1,nearestStructure) else max(rawTp1,nearestStructure)} else rawTp1
        val tp2Structure=if(dir=="BUY") listOf(priorHigh,swingHigh).filter{it>tp1+a*.20}.minOrNull() else listOf(priorLow,swingLow).filter{it<tp1-a*.20}.maxOrNull()
        val tp2=if(tp2Structure!=null){if(dir=="BUY")min(rawTp2,tp2Structure) else max(rawTp2,tp2Structure)} else rawTp2

        val validityReason="No fixed candle or clock expiry is used. This setup stays pending only while its directional confirmations and structure remain valid. It becomes TRIGGERED when entry is reached, or EXPIRED if confirmation/structure changes before entry."
        val slReason="SL is ${two(risk/a)} ATR from entry. It uses recent local structure plus a timeframe volatility cap so short-timeframe stops do not become unnecessarily wide."
        val tp1Reason=if(nearestStructure!=null)"TP1 is limited by the nearest directional structure/liquidity level and the $timeframe ATR target cap (${two(tp1Atr)} ATR)." else "TP1 uses the $timeframe ATR target cap (${two(tp1Atr)} ATR) because no closer valid structure target was found."
        val tp2Reason=if(tp2Structure!=null)"TP2 is limited by the next structure/liquidity level and the $timeframe extended ATR cap (${two(tp2Atr)} ATR)." else "TP2 uses the $timeframe extended ATR cap (${two(tp2Atr)} ATR) because no closer second structure target was found."
        val setupReason="$dir exists because directional evidence is $win vs $lose (difference $sep) across the recent movement, trend, momentum, structure, liquidity and imbalance context. The engine does not force a signal when evidence is balanced."
        val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(8).map{"${it.second} (+${it.first})"}

        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,0,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh,validityReason,slReason,tp1Reason,tp2Reason,setupReason)
    }

    fun sameSetup(a:Signal,b:Signal):Boolean{
        if(a.symbol!=b.symbol||a.timeframe!=b.timeframe||a.direction!=b.direction)return false
        val atr=max(a.atr,b.atr).coerceAtLeast(1e-9)
        val entryClose=abs(a.entry-b.entry)<=atr*.45
        val slClose=abs(a.sl-b.sl)<=atr*.70
        val fvgMatch=when{
            a.fvgType==null&&b.fvgType==null->true
            a.fvgType!=b.fvgType->false
            a.fvgLow!=null&&a.fvgHigh!=null&&b.fvgLow!=null&&b.fvgHigh!=null -> max(a.fvgLow,b.fvgLow)<=min(a.fvgHigh,b.fvgHigh)+atr*.12
            else->true
        }
        val ar=a.reasons.map{it.substringBefore(" (+")}.toSet()
        val br=b.reasons.map{it.substringBefore(" (+")}.toSet()
        val overlap=ar.intersect(br).size
        return entryClose&&slClose&&fvgMatch&&overlap>=2
    }

    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<40)return SetupCheck(true,"Not enough fresh history to invalidate the setup.")
        val last=c.last()
        if(s.direction=="BUY"&&last.c<s.sl)return SetupCheck(false,"BUY setup invalidated: price closed below its structural invalidation / SL level.")
        if(s.direction=="SELL"&&last.c>s.sl)return SetupCheck(false,"SELL setup invalidated: price closed above its structural invalidation / SL level.")
        val close=c.map{it.c}
        val e20=ema(close,20).last();val e50=ema(close,50).last();val r=rsi(close,14)
        val m=ema(close,12).last()-ema(close,26).last()
        val prior=c.takeLast(14).dropLast(1)
        val priorLow=prior.minOf{it.l};val priorHigh=prior.maxOf{it.h}
        var opposite=0
        if(s.direction=="BUY"){
            if(e20<e50)opposite++
            if(r<47)opposite++
            if(m<0)opposite++
            if(last.c<priorLow)opposite+=2
            if(s.fvgType=="BULLISH"&&s.fvgLow!=null&&last.c<s.fvgLow)opposite++
        }else{
            if(e20>e50)opposite++
            if(r>53)opposite++
            if(m>0)opposite++
            if(last.c>priorHigh)opposite+=2
            if(s.fvgType=="BEARISH"&&s.fvgHigh!=null&&last.c>s.fvgHigh)opposite++
        }
        return if(opposite>=3) SetupCheck(false,"Setup expired because core confirmation changed: trend/momentum/structure no longer support the original ${s.direction} idea.")
        else SetupCheck(true,"Original ${s.direction} confirmation is still structurally valid. No fixed time expiry is applied.")
    }

    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{
        if(c.size<80)return "NO VALID SIGNAL: not enough candle history is available for $symbol $timeframe."
        val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val r=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last()
        return "NO VALID SIGNAL\nThe current $symbol $timeframe setup does not have enough directional separation. Key checks: EMA20 ${if(e20>e50)"above" else "below"} EMA50, RSI14 ${one(r)}, MACD ${fmt(m)}. The app will not create a forced trade."
    }

    private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"5m"->5;"15m"->15;"30m"->30;"1h"->60;"4h"->240;"1d"->1440;else->15}
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v)
    private fun two(v:Double)=String.format(Locale.US,"%.2f",v)
    private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v) else String.format(Locale.US,"%.5f",v)
    private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun stdev(v:List<Double>):Double{if(v.isEmpty())return 0.0;val m=v.average();return sqrt(v.sumOf{(it-m)*(it-m)}/v.size)}
}
