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
        val last=c.last();val prev=c[c.lastIndex-1]
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last()
        val r=rsi(close,14);val a=atr(c,14).coerceAtLeast(1e-9)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val basis=close.takeLast(20).average();val sd=stdev(close.takeLast(20));val upper=basis+2*sd;val lower=basis-2*sd
        val recent=c.takeLast(55);val swingHigh=recent.dropLast(2).maxOf{it.h};val swingLow=recent.dropLast(2).minOf{it.l}
        val local=c.takeLast(16).dropLast(1);val localHigh=local.maxOf{it.h};val localLow=local.minOf{it.l}
        val prior=c.takeLast(38).dropLast(4);val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l}

        val trendBull=e20>e50&&last.c>e150
        val trendBear=e20<e50&&last.c<e150
        val bosBull=last.c>priorHigh;val bosBear=last.c<priorLow
        val sweepBull=last.l<priorLow&&last.c>priorLow;val sweepBear=last.h>priorHigh&&last.c<priorHigh
        val before=c.takeLast(32).dropLast(3)
        val upSeq=before.takeLast(8).zipWithNext().count{it.second.c>it.first.c}>=5
        val downSeq=before.takeLast(8).zipWithNext().count{it.second.c<it.first.c}>=5
        val chochBull=downSeq&&last.c>before.takeLast(10).maxOf{it.h}
        val chochBear=upSeq&&last.c<before.takeLast(10).minOf{it.l}
        val displacementBull=last.c-last.o>a*.45&&c.takeLast(7).dropLast(1).any{it.c<it.o}
        val displacementBear=last.o-last.c>a*.45&&c.takeLast(7).dropLast(1).any{it.c>it.o}
        val nearSupport=abs(last.c-swingLow)<=a*1.2
        val nearResistance=abs(last.c-swingHigh)<=a*1.2

        var fvgType:String?=null;var fvgLow:Double?=null;var fvgHigh:Double?=null
        val fw=c.takeLast(24)
        for(i in 2 until fw.size){
            if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l}
            if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}
        }

        var bull=0;var bear=0
        val br=mutableListOf<Pair<Int,String>>();val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,s:String){bull+=p;br+=p to s};fun s(p:Int,x:String){bear+=p;sr+=p to x}
        if(e20>e50)b(14,"EMA20 is above EMA50") else s(14,"EMA20 is below EMA50")
        if(last.c>e150)b(7,"Price is above EMA150") else s(7,"Price is below EMA150")
        if(e20>ema(close.dropLast(1),20).last())b(5,"EMA20 is rising") else s(5,"EMA20 is falling")
        when{r>=56->b(9,"RSI14 supports bullish momentum at ${one(r)}");r<=44->s(9,"RSI14 supports bearish momentum at ${one(r)}");else->{b(1,"RSI14 is neutral at ${one(r)}");s(1,"RSI14 is neutral at ${one(r)}")}}
        if(macd>0)b(8,"MACD is above zero") else s(8,"MACD is below zero")
        if(macd>macdPrev)b(5,"MACD momentum is rising") else s(5,"MACD momentum is falling")
        if(bosBull)b(17,"Bullish BOS / breakout is confirmed");if(bosBear)s(17,"Bearish BOS / breakout is confirmed")
        if(sweepBull)b(16,"Sell-side liquidity sweep is visible");if(sweepBear)s(16,"Buy-side liquidity sweep is visible")
        if(chochBull)b(14,"Bullish CHoCH is confirmed");if(chochBear)s(14,"Bearish CHoCH is confirmed")
        if(fvgType=="BULLISH")b(9,"Bullish FVG exists at ${fmt(fvgLow)} - ${fmt(fvgHigh)}")
        if(fvgType=="BEARISH")s(9,"Bearish FVG exists at ${fmt(fvgLow)} - ${fmt(fvgHigh)}")
        if(displacementBull)b(9,"Bullish displacement / order-block context")
        if(displacementBear)s(9,"Bearish displacement / order-block context")
        if(nearSupport)b(7,"Price is near structural support");if(nearResistance)s(7,"Price is near structural resistance")
        if(last.c<=lower)b(5,"Price is near the lower Bollinger band");if(last.c>=upper)s(5,"Price is near the upper Bollinger band")
        val mom=c.takeLast(4).last().c-c.takeLast(4).first().c
        if(mom>a*.35)b(6,"Short-term momentum is bullish") else if(mom< -a*.35)s(6,"Short-term momentum is bearish")

        val dir=if(bull>=bear)"BUY" else "SELL";val win=max(bull,bear);val lose=min(bull,bear);val sep=win-lose
        if(win<52||sep<12)return null

        val matchingFvg=(dir=="BUY"&&fvgType=="BULLISH")||(dir=="SELL"&&fvgType=="BEARISH")
        val structuralCount=if(dir=="BUY") listOf(bosBull,sweepBull,chochBull,displacementBull,matchingFvg,nearSupport).count{it}
            else listOf(bosBear,sweepBear,chochBear,displacementBear,matchingFvg,nearResistance).count{it}
        val hardTrigger=if(dir=="BUY")bosBull||sweepBull||chochBull||displacementBull else bosBear||sweepBear||chochBear||displacementBear
        val trendAligned=if(dir=="BUY")trendBull else trendBear
        val reversalConfirmed=if(dir=="BUY")chochBull&&(sweepBull||displacementBull) else chochBear&&(sweepBear||displacementBear)
        if(structuralCount<2||!hardTrigger||(!trendAligned&&!reversalConfirmed))return null

        val fvgMid=if(matchingFvg&&fvgLow!=null&&fvgHigh!=null)(fvgLow!!+fvgHigh!!)/2.0 else null
        val opposite=if(dir=="BUY")c.takeLast(10).dropLast(1).lastOrNull{it.c<it.o} else c.takeLast(10).dropLast(1).lastOrNull{it.c>it.o}
        val obMid=opposite?.let{(it.o+it.c)/2.0}
        val candidates=mutableListOf<Pair<String,Double>>()
        if(fvgMid!=null)candidates+="FVG midpoint" to fvgMid
        if(dir=="BUY"&&e20<last.c)candidates+="EMA20 pullback" to e20
        if(dir=="SELL"&&e20>last.c)candidates+="EMA20 pullback" to e20
        if(obMid!=null)candidates+="Order-block candle midpoint" to obMid

        val validEntries=candidates.filter{(_,v)->
            val dist=abs(last.c-v)/a
            val untouched=if(dir=="BUY")v<last.l-a*.03 else v>last.h+a*.03
            val directional=if(dir=="BUY")v<last.c else v>last.c
            directional&&untouched&&dist in 0.12..1.60
        }.sortedBy{abs(last.c-it.second)}
        if(validEntries.isEmpty())return null
        val entrySource=validEntries.first().first;val entry=validEntries.first().second

        val tf=tfMinutes(timeframe)
        val slAtr=when{tf<=3->0.60;tf<=5->0.65;tf<=10->0.72;tf<=15->0.78;tf<=30->0.88;tf<=60->1.0;tf<=120->1.08;tf<=240->1.15;tf<=360->1.22;tf<=720->1.28;else->1.30}
        val maxRiskAtr=when{tf<=5->0.90;tf<=10->0.98;tf<=15->1.05;tf<=30->1.20;tf<=60->1.35;tf<=120->1.45;tf<=240->1.55;else->1.70}
        val structureRisk=if(dir=="BUY")entry-(localLow-a*.08) else (localHigh+a*.08)-entry
        val baseRisk=max(a*slAtr,abs(last.c-prev.c)*1.15)
        val risk=max(baseRisk,min(max(structureRisk,0.0),a*maxRiskAtr)).coerceAtMost(a*maxRiskAtr)
        val sl=if(dir=="BUY")entry-risk else entry+risk

        val tp1Atr=when{tf<=3->0.75;tf<=5->0.85;tf<=10->0.93;tf<=15->1.00;tf<=30->1.15;tf<=60->1.35;tf<=120->1.48;tf<=240->1.60;tf<=360->1.72;tf<=720->1.82;else->1.90}
        val tp2Atr=when{tf<=3->1.10;tf<=5->1.20;tf<=10->1.33;tf<=15->1.45;tf<=30->1.65;tf<=60->1.95;tf<=120->2.12;tf<=240->2.30;tf<=360->2.45;tf<=720->2.60;else->2.70}
        val rawTp1=if(dir=="BUY")entry+a*tp1Atr else entry-a*tp1Atr;val rawTp2=if(dir=="BUY")entry+a*tp2Atr else entry-a*tp2Atr
        val nearestStructure=if(dir=="BUY")listOf(localHigh,priorHigh,swingHigh).filter{it>entry+a*.25}.minOrNull() else listOf(localLow,priorLow,swingLow).filter{it<entry-a*.25}.maxOrNull()
        val tp1=if(nearestStructure!=null){if(dir=="BUY")min(rawTp1,nearestStructure)else max(rawTp1,nearestStructure)}else rawTp1
        val tp2Structure=if(dir=="BUY")listOf(priorHigh,swingHigh).filter{it>tp1+a*.20}.minOrNull() else listOf(priorLow,priorLow,swingLow).filter{it<tp1-a*.20}.maxOrNull()
        val tp2=if(tp2Structure!=null){if(dir=="BUY")min(rawTp2,tp2Structure)else max(rawTp2,tp2Structure)}else rawTp2

        val score=(58+sep*2+(win-52)/2+structuralCount*2).coerceIn(58,96)
        val validityReason="No fixed candle or clock expiry is used. The pending setup remains valid only while its original trend/structure/liquidity confirmations remain intact. Entry is not allowed on the candle that created this signal; the setup must be reached later."
        val slReason="SL is ${two(risk/a)} ATR from entry and is constrained by recent local structure plus the $timeframe volatility cap."
        val tp1Reason=if(nearestStructure!=null)"TP1 is capped by the nearest directional structure/liquidity level and the $timeframe volatility target (${two(tp1Atr)} ATR)." else "TP1 uses the $timeframe volatility target (${two(tp1Atr)} ATR) because no closer structure target was found."
        val tp2Reason=if(tp2Structure!=null)"TP2 is capped by the next structure/liquidity level and the extended $timeframe target (${two(tp2Atr)} ATR)." else "TP2 uses the extended $timeframe volatility target (${two(tp2Atr)} ATR)."
        val trendText=if(trendAligned)"aligned with the established trend" else "a confirmed reversal setup"
        val setupReason="$dir is actionable because directional evidence is $win vs $lose (difference $sep), $structuralCount structural confirmations are present, and the setup is $trendText. Entry uses the untouched $entrySource at ${fmt(entry)}, not the current market price."
        val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(9).map{"${it.second} (+${it.first})"}

        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,0,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh,validityReason,slReason,tp1Reason,tp2Reason,setupReason)
    }

    fun sameSetup(a:Signal,b:Signal):Boolean{
        if(a.symbol!=b.symbol||a.timeframe!=b.timeframe||a.direction!=b.direction)return false
        val atr=max(a.atr,b.atr).coerceAtLeast(1e-9)
        val entryClose=abs(a.entry-b.entry)<=atr*.50;val slClose=abs(a.sl-b.sl)<=atr*.75
        val fvgMatch=when{
            a.fvgType==null&&b.fvgType==null->true
            a.fvgType!=b.fvgType->false
            a.fvgLow!=null&&a.fvgHigh!=null&&b.fvgLow!=null&&b.fvgHigh!=null->max(a.fvgLow,b.fvgLow)<=min(a.fvgHigh,b.fvgHigh)+atr*.12
            else->true
        }
        val ar=a.reasons.map{it.substringBefore(" (+")}.toSet();val br=b.reasons.map{it.substringBefore(" (+")}.toSet();val overlap=ar.intersect(br).size
        return entryClose&&slClose&&fvgMatch&&overlap>=2
    }

    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<40)return SetupCheck(true,"Not enough fresh history to invalidate the setup.")
        val last=c.last();if(s.direction=="BUY"&&last.c<s.sl)return SetupCheck(false,"BUY setup invalidated: price closed below structural invalidation.")
        if(s.direction=="SELL"&&last.c>s.sl)return SetupCheck(false,"SELL setup invalidated: price closed above structural invalidation.")
        val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val r=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last()
        val prior=c.takeLast(14).dropLast(1);val priorLow=prior.minOf{it.l};val priorHigh=prior.maxOf{it.h};var opposite=0
        if(s.direction=="BUY"){
            if(e20<e50)opposite++;if(r<47)opposite++;if(m<0)opposite++;if(last.c<priorLow)opposite+=2;if(s.fvgType=="BULLISH"&&s.fvgLow!=null&&last.c<s.fvgLow)opposite++
        }else{
            if(e20>e50)opposite++;if(r>53)opposite++;if(m>0)opposite++;if(last.c>priorHigh)opposite+=2;if(s.fvgType=="BEARISH"&&s.fvgHigh!=null&&last.c>s.fvgHigh)opposite++
        }
        return if(opposite>=3)SetupCheck(false,"Setup expired because core trend/momentum/structure confirmation changed before entry.") else SetupCheck(true,"Original ${s.direction} structure is still valid; no fixed time expiry is used.")
    }

    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{
        if(c.size<80)return "NO VALID TRADE: not enough candle history is available for $symbol $timeframe."
        val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last();val r=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last()
        val trend=when{e20>e50&&close.last()>e150->"BULLISH";e20<e50&&close.last()<e150->"BEARISH";else->"MIXED"}
        return "NO VALID TRADE / WAIT\nThe engine did not find a fresh untouched entry zone with enough structure confirmation on $symbol $timeframe. Current trend: $trend. EMA20 ${if(e20>e50)"above" else "below"} EMA50, RSI14 ${one(r)}, MACD ${fmt(m)}. Indicator bias alone is not enough to create a trade."
    }

    private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){
        "3m"->3;"5m"->5;"10m"->10;"15m"->15;"30m"->30;"1h"->60;"2h"->120;"4h"->240;"6h"->360;"12h"->720;"1d"->1440;else->15
    }
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v);private fun two(v:Double)=String.format(Locale.US,"%.2f",v)
    private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun stdev(v:List<Double>):Double{if(v.isEmpty())return 0.0;val m=v.average();return sqrt(v.sumOf{(it-m)*(it-m)}/v.size)}
}
