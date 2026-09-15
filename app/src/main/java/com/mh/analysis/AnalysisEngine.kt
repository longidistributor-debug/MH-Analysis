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
        val recent=c.takeLast(60);val local=c.takeLast(18).dropLast(1);val prior=c.takeLast(42).dropLast(4);val shortPrior=c.takeLast(16).dropLast(2)
        val swingHigh=recent.dropLast(2).maxOf{it.h};val swingLow=recent.dropLast(2).minOf{it.l}
        val localHigh=local.maxOf{it.h};val localLow=local.minOf{it.l};val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l}
        val shortHigh=shortPrior.maxOf{it.h};val shortLow=shortPrior.minOf{it.l}

        val trendBull=e20>e50&&s20>s50&&last.c>e150
        val trendBear=e20<e50&&s20<s50&&last.c<e150
        val trendSlopeBull=e20>ema(close.dropLast(3),20).last()&&e50>=ema(close.dropLast(4),50).last()
        val trendSlopeBear=e20<ema(close.dropLast(3),20).last()&&e50<=ema(close.dropLast(4),50).last()
        val bosBull=last.c>priorHigh+a*.05;val bosBear=last.c<priorLow-a*.05
        val shortBosBull=last.c>shortHigh+a*.03;val shortBosBear=last.c<shortLow-a*.03
        val sweepBull=last.l<priorLow&&last.c>priorLow;val sweepBear=last.h>priorHigh&&last.c<priorHigh
        val stopHuntBull=sweepBull&&(last.c-last.l)>(last.h-last.l)*.55;val stopHuntBear=sweepBear&&(last.h-last.c)>(last.h-last.l)*.55
        val fakeBreakBull=last.l<priorLow-a*.06&&last.c>priorLow&&last.c>last.o;val fakeBreakBear=last.h>priorHigh+a*.06&&last.c<priorHigh&&last.c<last.o
        val retestBull=(prev.c>shortHigh||prev.c>priorHigh)&&last.l<=max(shortHigh,priorHigh)+a*.18&&last.c>max(shortHigh,priorHigh)-a*.05
        val retestBear=(prev.c<shortLow||prev.c<priorLow)&&last.h>=min(shortLow,priorLow)-a*.18&&last.c<min(shortLow,priorLow)+a*.05

        val before=c.takeLast(34).dropLast(3);val downSeq=before.takeLast(9).zipWithNext().count{it.second.c<it.first.c}>=5;val upSeq=before.takeLast(9).zipWithNext().count{it.second.c>it.first.c}>=5
        val chochBull=downSeq&&last.c>before.takeLast(10).maxOf{it.h};val chochBear=upSeq&&last.c<before.takeLast(10).minOf{it.l}

        val range=(last.h-last.l).coerceAtLeast(1e-9);val body=abs(last.c-last.o)
        val pressureBull=last.c>last.o&&body/range>=.47&&last.c>=last.h-range*.27;val pressureBear=last.c<last.o&&body/range>=.47&&last.c<=last.l+range*.27
        val displacementBull=last.c-last.o>a*.40&&pressureBull;val displacementBear=last.o-last.c>a*.40&&pressureBear
        val momentumBull=(macd>macdPrev&&r>=50)||(macd>0&&r>=54)
        val momentumBear=(macd<macdPrev&&r<=55)||(macd<0&&r<=50)
        val nearSupport=abs(last.c-localLow)<=a*1.10||abs(last.c-swingLow)<=a*1.25;val nearResistance=abs(last.c-localHigh)<=a*1.10||abs(last.c-swingHigh)<=a*1.25
        val rsiBullDiv=bullishRsiDivergence(c);val rsiBearDiv=bearishRsiDivergence(c)
        val pullbackBull=c.takeLast(10).dropLast(1).any{it.l<=e20+a*.35&&it.c>=e50-a*.15};val pullbackBear=c.takeLast(10).dropLast(1).any{it.h>=e20-a*.35&&it.c<=e50+a*.15}

        var fvgType:String?=null;var fvgLow:Double?=null;var fvgHigh:Double?=null
        val fw=c.takeLast(30);for(i in 2 until fw.size){if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l};if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}}
        val fvgBull=fvgType=="BULLISH";val fvgBear=fvgType=="BEARISH"
        val bullOb=c.takeLast(14).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(14).dropLast(1).lastOrNull{it.c>it.o};val bullObMid=bullOb?.let{(it.o+it.c)/2};val bearObMid=bearOb?.let{(it.o+it.c)/2}

        var bull=0;var bear=0;val br=mutableListOf<Pair<Int,String>>();val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,x:String){bull+=p;br+=p to x};fun s(p:Int,x:String){bear+=p;sr+=p to x}
        if(e20>e50)b(9,"EMA20 above EMA50")else s(9,"EMA20 below EMA50")
        if(s20>s50)b(7,"SMA20 above SMA50")else s(7,"SMA20 below SMA50")
        if(last.c>e150)b(5,"Price above EMA150")else s(5,"Price below EMA150")
        if(trendSlopeBull)b(6,"EMA trend slope rising");if(trendSlopeBear)s(6,"EMA trend slope falling")
        if(r>=54)b(6,"RSI bullish ${one(r)}")else if(r<=46)s(6,"RSI bearish ${one(r)}")
        if(rsiBullDiv)b(15,"Bullish RSI divergence");if(rsiBearDiv)s(15,"Bearish RSI divergence")
        if(macd>0)b(5,"MACD above zero")else s(5,"MACD below zero")
        if(macd>macdPrev)b(6,"MACD pressure rising")else s(6,"MACD pressure falling")
        if(bosBull||shortBosBull)b(16,"Bullish BOS / breakout");if(bosBear||shortBosBear)s(16,"Bearish BOS / breakout")
        if(retestBull)b(18,"Bullish breakout retest held");if(retestBear)s(18,"Bearish breakout retest held")
        if(stopHuntBull)b(20,"Sell-side liquidity / SL hunt reclaimed");if(stopHuntBear)s(20,"Buy-side liquidity / SL hunt rejected")
        if(fakeBreakBull)b(18,"Bearish break failed — bullish fakeout");if(fakeBreakBear)s(18,"Bullish break failed — bearish fakeout")
        if(chochBull)b(16,"Bullish CHoCH");if(chochBear)s(16,"Bearish CHoCH")
        if(fvgBull)b(8,"Bullish FVG context");if(fvgBear)s(8,"Bearish FVG context")
        if(bullObMid!=null)b(5,"Bullish order-block context");if(bearObMid!=null)s(5,"Bearish order-block context")
        if(displacementBull)b(10,"Bullish displacement / pressure");if(displacementBear)s(10,"Bearish displacement / pressure")
        if(pullbackBull)b(8,"Recent EMA pullback held");if(pullbackBear)s(8,"Recent EMA rejection held")
        if(nearSupport)b(5,"Near structural support");if(nearResistance)s(5,"Near structural resistance")

        val bullLiquidityReversal=(stopHuntBull||fakeBreakBull)&&(chochBull||rsiBullDiv||pressureBull||momentumBull)
        val bearLiquidityReversal=(stopHuntBear||fakeBreakBear)&&(chochBear||rsiBearDiv||pressureBear||momentumBear)
        val bullBreakoutRetest=retestBull&&(trendBull||momentumBull||fvgBull);val bearBreakoutRetest=retestBear&&(trendBear||momentumBear||fvgBear)
        val bullContinuation=trendBull&&trendSlopeBull&&(momentumBull||pressureBull||pullbackBull||shortBosBull)&&(pullbackBull||fvgBull||bullObMid!=null||shortBosBull||nearSupport)
        val bearContinuation=trendBear&&trendSlopeBear&&(momentumBear||pressureBear||pullbackBear||shortBosBear)&&(pullbackBear||fvgBear||bearObMid!=null||shortBosBear||nearResistance)
        val bullChoch=chochBull&&(stopHuntBull||rsiBullDiv||displacementBull||pressureBull);val bearChoch=chochBear&&(stopHuntBear||rsiBearDiv||displacementBear||pressureBear)
        val bullBreakoutMomentum=(bosBull||shortBosBull)&&trendSlopeBull&&(momentumBull||displacementBull);val bearBreakoutMomentum=(bosBear||shortBosBear)&&trendSlopeBear&&(momentumBear||displacementBear)

        val bullFamily=listOf(bullLiquidityReversal,bullBreakoutRetest,bullContinuation,bullChoch,bullBreakoutMomentum).count{it};val bearFamily=listOf(bearLiquidityReversal,bearBreakoutRetest,bearContinuation,bearChoch,bearBreakoutMomentum).count{it}
        val dir=if(bull>=bear)"BUY" else "SELL";val win=max(bull,bear);val lose=min(bull,bear);val sep=win-lose;val family=if(dir=="BUY")bullFamily else bearFamily
        if(family<1||win<44||sep<6)return null

        val matchingFvg=(dir=="BUY"&&fvgBull)||(dir=="SELL"&&fvgBear);val fvgMid=if(matchingFvg&&fvgLow!=null&&fvgHigh!=null)(fvgLow!!+fvgHigh!!)/2 else null;val obMid=if(dir=="BUY")bullObMid else bearObMid
        val impulse=c.takeLast(24);val impulseHigh=impulse.maxOf{it.h};val impulseLow=impulse.minOf{it.l};val impulseRange=(impulseHigh-impulseLow).coerceAtLeast(a)
        val retrace382=if(dir=="BUY")impulseHigh-impulseRange*.382 else impulseLow+impulseRange*.382;val retrace50=if(dir=="BUY")impulseHigh-impulseRange*.50 else impulseLow+impulseRange*.50
        val candidates=mutableListOf<Pair<String,Double>>()
        if(fvgMid!=null)candidates+="FVG midpoint" to fvgMid;if(obMid!=null)candidates+="order-block midpoint" to obMid
        if(dir=="BUY"&&e20<last.c)candidates+="EMA20 pullback" to e20;if(dir=="SELL"&&e20>last.c)candidates+="EMA20 pullback" to e20
        if(dir=="BUY"&&e50<last.c)candidates+="EMA50 structure pullback" to e50;if(dir=="SELL"&&e50>last.c)candidates+="EMA50 structure pullback" to e50
        if(dir=="BUY"&&retestBull)candidates+="breakout retest" to max(shortHigh,priorHigh);if(dir=="SELL"&&retestBear)candidates+="breakout retest" to min(shortLow,priorLow)
        if((dir=="BUY"&&trendBull)||(dir=="SELL"&&trendBear)){candidates+="38.2% impulse retracement" to retrace382;candidates+="50% impulse retracement" to retrace50}
        val validEntries=candidates.filter{(_,v)->val dist=abs(last.c-v)/a;val untouched=if(dir=="BUY")v<=last.l-a*.02 else v>=last.h+a*.02;val directional=if(dir=="BUY")v<last.c else v>last.c;directional&&untouched&&dist in .08..2.35}.sortedBy{abs(last.c-it.second)}
        if(validEntries.isEmpty())return null
        val entrySource=validEntries.first().first;val entry=validEntries.first().second

        val tf=tfMinutes(timeframe);val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=15->1.08;tf<=30->1.22;else->1.38}
        val structureRisk=if(dir=="BUY")entry-(localLow-a*.08)else(localHigh+a*.08)-entry;val risk=max(a*.62,min(max(structureRisk,0.0),a*maxRiskAtr)).coerceAtMost(a*maxRiskAtr);val sl=if(dir=="BUY")entry-risk else entry+risk
        val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=15->1.05;tf<=30->1.18;else->1.35};val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=15->1.50;tf<=30->1.70;else->1.95}
        val rawTp1=if(dir=="BUY")entry+a*tp1Atr else entry-a*tp1Atr;val rawTp2=if(dir=="BUY")entry+a*tp2Atr else entry-a*tp2Atr
        val nearest=if(dir=="BUY")listOf(localHigh,priorHigh,swingHigh).filter{it>entry+a*.20}.minOrNull() else listOf(localLow,priorLow,swingLow).filter{it<entry-a*.20}.maxOrNull();val tp1=if(nearest!=null){if(dir=="BUY")min(rawTp1,nearest)else max(rawTp1,nearest)}else rawTp1;val tp2=rawTp2

        val familyName=when{dir=="BUY"&&bullLiquidityReversal->"liquidity / SL-hunt reversal";dir=="SELL"&&bearLiquidityReversal->"liquidity / SL-hunt reversal";dir=="BUY"&&bullBreakoutRetest->"breakout + retest continuation";dir=="SELL"&&bearBreakoutRetest->"breakout + retest continuation";dir=="BUY"&&bullChoch->"CHoCH reversal";dir=="SELL"&&bearChoch->"CHoCH reversal";dir=="BUY"&&bullBreakoutMomentum->"breakout momentum continuation";dir=="SELL"&&bearBreakoutMomentum->"breakout momentum continuation";else->"established trend pullback"}
        val score=(60+sep+(family*5)).coerceIn(60,96);val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(10).map{"${it.second} (+${it.first})"};val strongest=reasons.take(4).joinToString("; ")
        val validityReason="No fixed candle-count expiry. Pending remains valid only while live trend, momentum, liquidity and structure support the original thesis; abnormal volatility or structural failure expires it immediately."
        val setupReason="$dir $familyName. Best confirmed family on the current graph. Evidence: $strongest. Evidence balance $win vs $lose. Pending entry uses $entrySource at ${fmt(entry)} and is outside the signal candle."
        val slReason="SL is behind local invalidation structure and capped by ${two(maxRiskAtr)} ATR for $timeframe.";val tp1Reason="TP1 uses nearby structure and a ${two(tp1Atr)} ATR objective.";val tp2Reason="TP2 uses an extended ${two(tp2Atr)} ATR objective."
        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,0,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh,validityReason,slReason,tp1Reason,tp2Reason,setupReason)
    }

    fun sameSetup(a:Signal,b:Signal):Boolean{if(a.symbol!=b.symbol||a.timeframe!=b.timeframe||a.direction!=b.direction)return false;val at=max(a.atr,b.atr).coerceAtLeast(1e-9);return abs(a.entry-b.entry)<=at*.55&&abs(a.sl-b.sl)<=at*.80}
    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{if(c.size<60)return SetupCheck(true,"Waiting for enough fresh data.");if(isHighVolatility(c))return SetupCheck(false,"Pending setup invalidated by abnormal live volatility.");val last=c.last();val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last();val p=c.takeLast(18).dropLast(1);val hi=p.maxOf{it.h};val lo=p.minOf{it.l};var opposite=0;if(s.direction=="BUY"){if(last.c<s.sl)return SetupCheck(false,"BUY invalidated: price closed through structural SL.");if(e20<e50)opposite++;if(rr<43)opposite++;if(m<0)opposite++;if(last.c<lo)opposite+=2;if(s.fvgType=="BULLISH"&&s.fvgLow!=null&&last.c<s.fvgLow)opposite++}else{if(last.c>s.sl)return SetupCheck(false,"SELL invalidated: price closed through structural SL.");if(e20>e50)opposite++;if(rr>57)opposite++;if(m>0)opposite++;if(last.c>hi)opposite+=2;if(s.fvgType=="BEARISH"&&s.fvgHigh!=null&&last.c>s.fvgHigh)opposite++};return if(opposite>=3)SetupCheck(false,"Original setup is no longer valid: live trend/momentum/structure changed before entry.") else SetupCheck(true,"Live setup thesis remains valid.")}
    fun isHighVolatility(c:List<Candle>):Boolean{if(c.size<25)return false;val a=atr(c.dropLast(1),14).coerceAtLeast(1e-9);val last=c.last();val tr=max(last.h-last.l,max(abs(last.h-c[c.lastIndex-1].c),abs(last.l-c[c.lastIndex-1].c)));val recent=c.takeLast(20).dropLast(1).map{it.h-it.l}.sorted();val med=recent[recent.size/2].coerceAtLeast(1e-9);return tr>a*2.5||tr>med*3.1}
    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{if(c.size<100)return "$symbol $timeframe • waiting for enough live history.";if(isHighVolatility(c))return "$symbol $timeframe • abnormal volatility; waiting for structure to stabilize.";val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14);return "$symbol $timeframe • no stronger confirmed setup has cleared the quality floor yet. EMA20 ${fmt(e20)}, EMA50 ${fmt(e50)}, RSI ${one(rr)}."}

    private fun bullishRsiDivergence(c:List<Candle>):Boolean{if(c.size<35)return false;val a=c.takeLast(30);val first=a.take(15);val second=a.takeLast(15);val l1=first.minOf{it.l};val l2=second.minOf{it.l};val r1=rsi(first.map{it.c},7);val r2=rsi(second.map{it.c},7);return l2<l1&&r2>r1+3}
    private fun bearishRsiDivergence(c:List<Candle>):Boolean{if(c.size<35)return false;val a=c.takeLast(30);val first=a.take(15);val second=a.takeLast(15);val h1=first.maxOf{it.h};val h2=second.maxOf{it.h};val r1=rsi(first.map{it.c},7);val r2=rsi(second.map{it.c},7);return h2>h1&&r2<r1-3}
    private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"5m"->5;"15m"->15;"30m"->30;"1h"->60;else->15}
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v);private fun two(v:Double)=String.format(Locale.US,"%.2f",v);private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun sma(v:List<Double>,p:Int)=v.takeLast(min(p,v.size)).average();private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{if(c.size<2)return 0.0;var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun stdev(v:List<Double>):Double{if(v.isEmpty())return 0.0;val m=v.average();return sqrt(v.sumOf{(it-m)*(it-m)}/v.size)}
}
