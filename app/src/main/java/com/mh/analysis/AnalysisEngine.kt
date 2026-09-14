package com.mh.analysis

import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

object AnalysisEngine {
    fun analyze(symbol:String,timeframe:String,c:List<Candle>):Signal?{
        if(c.size<80)return null
        val close=c.map{it.c};val last=c.last();val prev=c[c.lastIndex-1]
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last()
        val r=rsi(close,14);val a=atr(c,14).coerceAtLeast(1e-9)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val basis=close.takeLast(20).average();val sd=stdev(close.takeLast(20));val upper=basis+2*sd;val lower=basis-2*sd
        val recent=c.takeLast(55);val swingHigh=recent.dropLast(2).maxOf{it.h};val swingLow=recent.dropLast(2).minOf{it.l}
        val prior=c.takeLast(38).dropLast(4);val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l}
        var bull=0;var bear=0
        val br=mutableListOf<Pair<Int,String>>();val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,s:String){bull+=p;br+=p to s};fun s(p:Int,x:String){bear+=p;sr+=p to x}

        if(e20>e50)b(14,"EMA20 > EMA50") else s(14,"EMA20 < EMA50")
        if(last.c>e150)b(7,"Price above EMA150") else s(7,"Price below EMA150")
        if(e20>ema(close.dropLast(1),20).last())b(5,"EMA20 rising") else s(5,"EMA20 falling")
        when{r>=55->b(9,"RSI bullish ${"%.1f".format(r)}");r<=45->s(9,"RSI bearish ${"%.1f".format(r)}");else->{b(2,"RSI neutral ${"%.1f".format(r)}");s(2,"RSI neutral ${"%.1f".format(r)}")}}
        if(macd>0)b(8,"MACD above zero") else s(8,"MACD below zero")
        if(macd>macdPrev)b(5,"MACD momentum rising") else s(5,"MACD momentum falling")
        if(last.c>priorHigh)b(17,"Bullish BOS / breakout")
        if(last.c<priorLow)s(17,"Bearish BOS / breakout")
        if(last.l<priorLow&&last.c>priorLow)b(16,"Sell-side liquidity sweep")
        if(last.h>priorHigh&&last.c<priorHigh)s(16,"Buy-side liquidity sweep")
        val before=c.takeLast(32).dropLast(3);val upSeq=before.takeLast(8).zipWithNext().count{it.second.c>it.first.c}>=5;val downSeq=before.takeLast(8).zipWithNext().count{it.second.c<it.first.c}>=5
        if(downSeq&&last.c>before.takeLast(10).maxOf{it.h})b(13,"Bullish CHoCH")
        if(upSeq&&last.c<before.takeLast(10).minOf{it.l})s(13,"Bearish CHoCH")

        var fvgType:String?=null;var fvgLow:Double?=null;var fvgHigh:Double?=null
        val fw=c.takeLast(24)
        for(i in 2 until fw.size){
            if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l}
            if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}
        }
        if(fvgType=="BULLISH")b(9,"Bullish FVG ${fmt(fvgLow)}-${fmt(fvgHigh)}")
        if(fvgType=="BEARISH")s(9,"Bearish FVG ${fmt(fvgLow)}-${fmt(fvgHigh)}")
        if(last.c-last.o>a*.45&&c.takeLast(7).dropLast(1).any{it.c<it.o})b(8,"Bullish displacement / OB context")
        if(last.o-last.c>a*.45&&c.takeLast(7).dropLast(1).any{it.c>it.o})s(8,"Bearish displacement / OB context")
        if(abs(last.c-swingLow)<=a*1.2)b(7,"Near structural support")
        if(abs(last.c-swingHigh)<=a*1.2)s(7,"Near structural resistance")
        if(last.c<=lower)b(6,"Near lower Bollinger band")
        if(last.c>=upper)s(6,"Near upper Bollinger band")
        val mom=c.takeLast(4).last().c-c.takeLast(4).first().c
        if(mom>a*.35)b(6,"Short momentum bullish") else if(mom< -a*.35)s(6,"Short momentum bearish")

        val dir=if(bull>=bear)"BUY" else "SELL";val win=max(bull,bear);val lose=min(bull,bear);val sep=win-lose
        if(win<40||sep<6)return null
        val score=(52+sep*2+(win-40)/2).coerceIn(52,96)
        val risk=max(a*1.18,abs(last.c-prev.c)*1.6)
        val entry=last.c;val sl=if(dir=="BUY")entry-risk else entry+risk;val tp1=if(dir=="BUY")entry+risk*1.4 else entry-risk*1.4;val tp2=if(dir=="BUY")entry+risk*2.25 else entry-risk*2.25
        val valid=when{score>=85->6;score>=75->5;score>=65->4;else->3}
        val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(8).map{"${it.second} (+${it.first})"}
        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,valid,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh)
    }

    private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)"%.2f".format(v) else "%.5f".format(v)
    private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun stdev(v:List<Double>):Double{if(v.isEmpty())return 0.0;val m=v.average();return sqrt(v.sumOf{(it-m)*(it-m)}/v.size)}
}
