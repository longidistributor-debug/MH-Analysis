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
        if(c.size<100)return null
        if(isHighVolatility(c))return null
        val close=c.map{it.c};val last=c.last();val prev=c[c.lastIndex-1]
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last()
        val s20=sma(close,20);val s50=sma(close,50);val r=rsi(close,14);val a=atr(c,14).coerceAtLeast(1e-9)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val recent=c.takeLast(60);val local=c.takeLast(18).dropLast(1);val prior=c.takeLast(42).dropLast(4)
        val swingHigh=recent.dropLast(2).maxOf{it.h};val swingLow=recent.dropLast(2).minOf{it.l}
        val localHigh=local.maxOf{it.h};val localLow=local.minOf{it.l};val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l}

        val trendBull=e20>e50&&s20>s50&&last.c>e150
        val trendBear=e20<e50&&s20<s50&&last.c<e150
        val bosBull=last.c>priorHigh+a*.05;val bosBear=last.c<priorLow-a*.05
        val sweepBull=last.l<priorLow&&last.c>priorLow;val sweepBear=last.h>priorHigh&&last.c<priorHigh
        val stopHuntBull=sweepBull&&(last.c-last.l)>(last.h-last.l)*.55
        val stopHuntBear=sweepBear&&(last.h-last.c)>(last.h-last.l)*.55
        val fakeBreakBull=last.l<priorLow-a*.08&&last.c>priorLow&&last.c>last.o
        val fakeBreakBear=last.h>priorHigh+a*.08&&last.c<priorHigh&&last.c<last.o
        val retestBull=prev.c>priorHigh&&last.l<=priorHigh+a*.18&&last.c>priorHigh
        val retestBear=prev.c<priorLow&&last.h>=priorLow-a*.18&&last.c<priorLow
        val before=c.takeLast(34).dropLast(3)
        val downSeq=before.takeLast(9).zipWithNext().count{it.second.c<it.first.c}>=5
        val upSeq=before.takeLast(9).zipWithNext().count{it.second.c>it.first.c}>=5
        val chochBull=downSeq&&last.c>before.takeLast(10).maxOf{it.h}
        val chochBear=upSeq&&last.c<before.takeLast(10).minOf{it.l}
        val range=(last.h-last.l).coerceAtLeast(1e-9);val body=abs(last.c-last.o)
        val pressureBull=last.c>last.o&&body/range>=.52&&last.c>=last.h-range*.22
        val pressureBear=last.c<last.o&&body/range>=.52&&last.c<=last.l+range*.22
        val displacementBull=last.c-last.o>a*.45&&pressureBull
        val displacementBear=last.o-last.c>a*.45&&pressureBear
        val nearSupport=abs(last.c-swingLow)<=a*1.15;val nearResistance=abs(last.c-swingHigh)<=a*1.15
        val rsiBullDiv=bullishRsiDivergence(c);val rsiBearDiv=bearishRsiDivergence(c)
        val pullbackBull=c.takeLast(8).dropLast(1).any{it.l<=e20+a*.30&&it.c>=e20-a*.15}
        val pullbackBear=c.takeLast(8).dropLast(1).any{it.h>=e20-a*.30&&it.c<=e20+a*.15}

        var fvgType:String?=null;var fvgLow:Double?=null;var fvgHigh:Double?=null
        val fw=c.takeLast(28)
        for(i in 2 until fw.size){
            if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l}
            if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}
        }
        val fvgBull=fvgType=="BULLISH";val fvgBear=fvgType=="BEARISH"
        val bullOb=c.takeLast(12).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(12).dropLast(1).lastOrNull{it.c>it.o}
        val bullObMid=bullOb?.let{(it.o+it.c)/2};val bearObMid=bearOb?.let{(it.o+it.c)/2}

        var bull=0;var bear=0;val br=mutableListOf<Pair<Int,String>>();val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,x:String){bull+=p;br+=p to x};fun s(p:Int,x:String){bear+=p;sr+=p to x}
        if(e20>e50)b(9,"EMA20 > EMA50")else s(9,"EMA20 < EMA50")
        if(s20>s50)b(7,"SMA20 > SMA50")else s(7,"SMA20 < SMA50")
        if(last.c>e150)b(5,"Price above EMA150")else s(5,"Price below EMA150")
        if(r>=54)b(6,"RSI bullish ${one(r)}")else if(r<=46)s(6,"RSI bearish ${one(r)}")
        if(rsiBullDiv)b(15,"Bullish RSI divergence")
        if(rsiBearDiv)s(15,"Bearish RSI divergence")
        if(macd>0)b(5,"MACD above zero")else s(5,"MACD below zero")
        if(macd>macdPrev)b(5,"MACD pressure rising")else s(5,"MACD pressure falling")
        if(bosBull)b(16,"Bullish BOS / breakout")
        if(bosBear)s(16,"Bearish BOS / breakout")
        if(retestBull)b(18,"Bullish breakout retest held")
        if(retestBear)s(18,"Bearish breakout retest held")
        if(stopHuntBull)b(20,"Sell-side liquidity / SL hunt reclaimed")
        if(stopHuntBear)s(20,"Buy-side liquidity / SL hunt rejected")
        if(fakeBreakBull)b(18,"Bearish break failed — bullish fakeout")
        if(fakeBreakBear)s(18,"Bullish break failed — bearish fakeout")
        if(chochBull)b(16,"Bullish CHoCH")
        if(chochBear)s(16,"Bearish CHoCH")
        if(fvgBull)b(8,"Bullish FVG")
        if(fvgBear)s(8,"Bearish FVG")
        if(bullObMid!=null)b(5,"Bullish order-block context")
        if(bearObMid!=null)s(5,"Bearish order-block context")
        if(displacementBull)b(10,"Bullish displacement / pressure")
        if(displacementBear)s(10,"Bearish displacement / pressure")
        if(pullbackBull)b(7,"Recent EMA20 pullback held")
        if(pullbackBear)s(7,"Recent EMA20 rejection held")
        if(nearSupport)b(6,"Near structural support")
        if(nearResistance)s(6,"Near structural resistance")

        val bullLiquidityReversal=(stopHuntBull||fakeBreakBull)&&(chochBull||rsiBullDiv||pressureBull)
        val bearLiquidityReversal=(stopHuntBear||fakeBreakBear)&&(chochBear||rsiBearDiv||pressureBear)
        val bullBreakoutRetest=retestBull&&(trendBull||pressureBull||fvgBull)
        val bearBreakoutRetest=retestBear&&(trendBear||pressureBear||fvgBear)
        val bullContinuation=trendBull&&(bosBull||displacementBull||pressureBull||macd>macdPrev||pullbackBull)&&(fvgBull||bullObMid!=null||pullbackBull||nearSupport)
        val bearContinuation=trendBear&&(bosBear||displacementBear||pressureBear||macd<macdPrev||pullbackBear)&&(fvgBear||bearObMid!=null||pullbackBear||nearResistance)
        val bullChoch=chochBull&&(stopHuntBull||rsiBullDiv||displacementBull||pressureBull)
        val bearChoch=chochBear&&(stopHuntBear||rsiBearDiv||displacementBear||pressureBear)

        val bullFamily=listOf(bullLiquidityReversal,bullBreakoutRetest,bullContinuation,bullChoch).count{it}
        val bearFamily=listOf(bearLiquidityReversal,bearBreakoutRetest,bearContinuation,bearChoch).count{it}
        val dir=if(bull>=bear)"BUY" else "SELL";val win=max(bull,bear);val lose=min(bull,bear);val sep=win-lose
        val family=if(dir=="BUY")bullFamily else bearFamily
        if(family<1||win<44||sep<7)return null

        val matchingFvg=(dir=="BUY"&&fvgBull)||(dir=="SELL"&&fvgBear)
        val fvgMid=if(matchingFvg&&fvgLow!=null&&fvgHigh!=null)(fvgLow!!+fvgHigh!!)/2 else null
        val obMid=if(dir=="BUY")bullObMid else bearObMid
        val candidates=mutableListOf<Pair<String,Double>>()
        if(fvgMid!=null)candidates+="FVG midpoint" to fvgMid
        if(obMid!=null)candidates+="order-block midpoint" to obMid
        if(dir=="BUY"&&e20<last.c)candidates+="EMA20 pullback" to e20
        if(dir=="SELL"&&e20>last.c)candidates+="EMA20 pullback" to e20
        if(dir=="BUY"&&retestBull)candidates+="breakout retest" to priorHigh
        if(dir=="SELL"&&retestBear)candidates+="breakout retest" to priorLow
        val validEntries=candidates.filter{(_,v)->
            val dist=abs(last.c-v)/a
            val directional=if(dir=="BUY")v<last.c+a*.10 else v>last.c-a*.10
            val notAlreadyPassed=if(dir=="BUY")v>last.l-a*.25 else v<last.h+a*.25
            directional&&notAlreadyPassed&&dist<=2.0
        }.sortedBy{abs(last.c-it.second)}
        if(validEntries.isEmpty())return null
        val entrySource=validEntries.first().first;val entry=validEntries.first().second

        val tf=tfMinutes(timeframe)
        val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=15->1.08;tf<=30->1.22;else->1.45}
        val structureRisk=if(dir=="BUY")entry-(localLow-a*.08)else(localHigh+a*.08)-entry
        val risk=max(a*.62,min(max(structureRisk,0.0),a*maxRiskAtr)).coerceAtMost(a*maxRiskAtr)
        val sl=if(dir=="BUY")entry-risk else entry+risk
        val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=15->1.05;tf<=30->1.18;else->1.48}
        val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=15->1.50;tf<=30->1.70;else->2.10}
        val rawTp1=if(dir=="BUY")entry+a*tp1Atr else entry-a*tp1Atr;val rawTp2=if(dir=="BUY")entry+a*tp2Atr else entry-a*tp2Atr
        val nearest=if(dir=="BUY")listOf(localHigh,priorHigh,swingHigh).filter{it>entry+a*.20}.minOrNull() else listOf(localLow,priorLow,swingLow).filter{it<entry-a*.20}.maxOrNull()
        val tp1=if(nearest!=null){if(dir=="BUY")min(rawTp1,nearest)else max(rawTp1,nearest)}else rawTp1
        val tp2=rawTp2

        val familyName=when{
            dir=="BUY"&&bullLiquidityReversal->"liquidity / SL-hunt reversal"
            dir=="SELL"&&bearLiquidityReversal->"liquidity / SL-hunt reversal"
            dir=="BUY"&&bullBreakoutRetest->"breakout + retest continuation"
            dir=="SELL"&&bearBreakoutRetest->"breakout + retest continuation"
            dir=="BUY"&&bullChoch->"CHoCH reversal"
            dir=="SELL"&&bearChoch->"CHoCH reversal"
            else->"trend continuation / pullback"
        }
        val score=(58+sep+(family*6)).coerceIn(58,96)
        val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(10).map{"${it.second} (+${it.first})"}
        val validityReason="No candle-count expiry. The setup remains pending only while its live structure, momentum, liquidity context and volatility remain valid. It expires when that thesis breaks or abnormal volatility invalidates the pending entry."
        val setupReason="$dir $familyName selected. Evidence score $win vs $lose; entry uses $entrySource at ${fmt(entry)}. One complete setup family with supporting confluence is enough; a fresh BOS candle is not mandatory for an already-established continuation trend."
        val slReason="SL is behind local invalidation structure and capped by ${two(maxRiskAtr)} ATR for $timeframe."
        val tp1Reason="TP1 uses nearby structure and a ${two(tp1Atr)} ATR objective."
        val tp2Reason="TP2 uses an extended ${two(tp2Atr)} ATR objective."
        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,0,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh,validityReason,slReason,tp1Reason,tp2Reason,setupReason)
    }

    fun sameSetup(a:Signal,b:Signal):Boolean{
        if(a.symbol!=b.symbol||a.timeframe!=b.timeframe||a.direction!=b.direction)return false
        val at=max(a.atr,b.atr).coerceAtLeast(1e-9)
        return abs(a.entry-b.entry)<=at*.55&&abs(a.sl-b.sl)<=at*.80
    }

    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<60)return SetupCheck(true,"Waiting for enough fresh data.")
        if(isHighVolatility(c))return SetupCheck(false,"Pending setup invalidated by abnormal live volatility.")
        val last=c.last();val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last()
        val p=c.takeLast(18).dropLast(1);val hi=p.maxOf{it.h};val lo=p.minOf{it.l};var opposite=0
        if(s.direction=="BUY"){
            if(last.c<s.sl)return SetupCheck(false,"BUY invalidated: price closed through structural SL.")
            if(e20<e50)opposite++;if(rr<44)opposite++;if(m<0)opposite++;if(last.c<lo)opposite+=2
            if(s.fvgType=="BULLISH"&&s.fvgLow!=null&&last.c<s.fvgLow)opposite++
        }else{
            if(last.c>s.sl)return SetupCheck(false,"SELL invalidated: price closed through structural SL.")
            if(e20>e50)opposite++;if(rr>56)opposite++;if(m>0)opposite++;if(last.c>hi)opposite+=2
            if(s.fvgType=="BEARISH"&&s.fvgHigh!=null&&last.c>s.fvgHigh)opposite++
        }
        return if(opposite>=3)SetupCheck(false,"Original setup is no longer valid: live trend/momentum/structure confirmation changed before entry.") else SetupCheck(true,"Live setup thesis still valid.")
    }

    fun isHighVolatility(c:List<Candle>):Boolean{
        if(c.size<25)return false
        val a=atr(c.dropLast(1),14).coerceAtLeast(1e-9);val last=c.last();val tr=max(last.h-last.l,max(abs(last.h-c[c.lastIndex-1].c),abs(last.l-c[c.lastIndex-1].c)))
        val recent=c.takeLast(20).dropLast(1).map{it.h-it.l}.sorted();val med=recent[recent.size/2].coerceAtLeast(1e-9)
        return tr>a*2.4||tr>med*3.0
    }

    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{
        if(c.size<100)return "NO VALID TRADE: not enough history for $symbol $timeframe."
        if(isHighVolatility(c))return "NO VALID TRADE / WAIT\nAbnormal volatility is active. New entries are blocked until market structure stabilizes."
        val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14)
        return "NO VALID TRADE / WAIT\nNo strong setup family is complete on $symbol $timeframe yet. EMA20 ${if(e20>e50)"above" else "below"} EMA50, RSI ${one(rr)}. The engine now accepts established trend continuation/pullback setups as well as liquidity reversal, breakout/retest and CHoCH — but it still will not manufacture a trade from indicators alone."
    }

    private fun bullishRsiDivergence(c:List<Candle>):Boolean{
        if(c.size<35)return false;val a=c.takeLast(30);val first=a.take(15);val second=a.takeLast(15)
        val l1=first.minOf{it.l};val l2=second.minOf{it.l};val r1=rsi(first.map{it.c},7);val r2=rsi(second.map{it.c},7)
        return l2<l1&&r2>r1+3
    }
    private fun bearishRsiDivergence(c:List<Candle>):Boolean{
        if(c.size<35)return false;val a=c.takeLast(30);val first=a.take(15);val second=a.takeLast(15)
        val h1=first.maxOf{it.h};val h2=second.maxOf{it.h};val r1=rsi(first.map{it.c},7);val r2=rsi(second.map{it.c},7)
        return h2>h1&&r2<r1-3
    }
    private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"3m"->3;"5m"->5;"10m"->10;"15m"->15;"30m"->30;"1h"->60;"2h"->120;"4h"->240;"6h"->360;"12h"->720;"1d","1day"->1440;else->15}
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v);private fun two(v:Double)=String.format(Locale.US,"%.2f",v)
    private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun sma(v:List<Double>,p:Int)=v.takeLast(min(p,v.size)).average()
    private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{if(c.size<2)return 0.0;var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun stdev(v:List<Double>):Double{if(v.isEmpty())return 0.0;val m=v.average();return sqrt(v.sumOf{(it-m)*(it-m)}/v.size)}
}
