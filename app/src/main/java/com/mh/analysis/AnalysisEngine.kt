package com.mh.analysis

import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

object AnalysisEngine {
    data class SetupCheck(val valid:Boolean,val reason:String)
    private data class IR(val direction:String,val impulseDistance:Double,val impulseCandles:Int,val avgImpulseBody:Double,val retracementDistance:Double,val retracementCandles:Int,val retracementRatio:Double,val speedRatio:Double,val counterBodyRatio:Double,val continuationStrength:Int,val reversalRisk:Boolean,val impulseHigh:Double,val impulseLow:Double,val resumed:Boolean)

    fun analyze(symbol:String,timeframe:String,c:List<Candle>):Signal?{
        if(c.size<100||isHighVolatility(c))return null
        val close=c.map{it.c};val last=c.last();val prev=c[c.lastIndex-1];val a=atr(c,14).coerceAtLeast(1e-9)
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last();val s20=sma(close,20);val s50=sma(close,50);val r=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val recent=c.takeLast(60);val local=c.takeLast(18).dropLast(1);val prior=c.takeLast(42).dropLast(4);val shortPrior=c.takeLast(16).dropLast(2)
        val swingHigh=recent.dropLast(2).maxOf{it.h};val swingLow=recent.dropLast(2).minOf{it.l};val localHigh=local.maxOf{it.h};val localLow=local.minOf{it.l};val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l};val shortHigh=shortPrior.maxOf{it.h};val shortLow=shortPrior.minOf{it.l}

        val trendBull=e20>e50&&s20>s50&&last.c>e150;val trendBear=e20<e50&&s20<s50&&last.c<e150
        val slopeBull=e20>ema(close.dropLast(3),20).last();val slopeBear=e20<ema(close.dropLast(3),20).last()
        val bosBull=last.c>priorHigh+a*.04||last.c>shortHigh+a*.025;val bosBear=last.c<priorLow-a*.04||last.c<shortLow-a*.025
        val sweepBull=last.l<priorLow&&last.c>priorLow;val sweepBear=last.h>priorHigh&&last.c<priorHigh
        val stopHuntBull=sweepBull&&(last.c-last.l)>(last.h-last.l)*.50;val stopHuntBear=sweepBear&&(last.h-last.c)>(last.h-last.l)*.50
        val fakeBull=last.l<priorLow-a*.04&&last.c>priorLow&&last.c>last.o;val fakeBear=last.h>priorHigh+a*.04&&last.c<priorHigh&&last.c<last.o
        val retestBull=(prev.c>shortHigh||prev.c>priorHigh)&&last.l<=max(shortHigh,priorHigh)+a*.22&&last.c>max(shortHigh,priorHigh)-a*.08
        val retestBear=(prev.c<shortLow||prev.c<priorLow)&&last.h>=min(shortLow,priorLow)-a*.22&&last.c<min(shortLow,priorLow)+a*.08

        val before=c.takeLast(34).dropLast(3);val downSeq=before.takeLast(9).zipWithNext().count{it.second.c<it.first.c}>=5;val upSeq=before.takeLast(9).zipWithNext().count{it.second.c>it.first.c}>=5
        val chochBull=downSeq&&last.c>before.takeLast(10).maxOf{it.h};val chochBear=upSeq&&last.c<before.takeLast(10).minOf{it.l}
        val range=(last.h-last.l).coerceAtLeast(1e-9);val body=abs(last.c-last.o);val pressureBull=last.c>last.o&&body/range>=.45&&last.c>=last.h-range*.30;val pressureBear=last.c<last.o&&body/range>=.45&&last.c<=last.l+range*.30
        val displacementBull=last.c-last.o>a*.38&&pressureBull;val displacementBear=last.o-last.c>a*.38&&pressureBear
        val momentumBull=(macd>macdPrev&&r>=49)||(macd>0&&r>=53);val momentumBear=(macd<macdPrev&&r<=56)||(macd<0&&r<=51)
        val rsiBullDiv=bullishRsiDivergence(c);val rsiBearDiv=bearishRsiDivergence(c)
        val pullbackBull=c.takeLast(10).dropLast(1).any{it.l<=e20+a*.40&&it.c>=e50-a*.20};val pullbackBear=c.takeLast(10).dropLast(1).any{it.h>=e20-a*.40&&it.c<=e50+a*.20}
        val nearSupport=abs(last.c-localLow)<=a*1.15||abs(last.c-swingLow)<=a*1.30;val nearResistance=abs(last.c-localHigh)<=a*1.15||abs(last.c-swingHigh)<=a*1.30
        val irBull=impulseRetracement(c,"BUY",a);val irBear=impulseRetracement(c,"SELL",a)

        var fvgType:String?=null;var fvgLow:Double?=null;var fvgHigh:Double?=null
        val fw=c.takeLast(30);for(i in 2 until fw.size){if(fw[i].l>fw[i-2].h){fvgType="BULLISH";fvgLow=fw[i-2].h;fvgHigh=fw[i].l};if(fw[i].h<fw[i-2].l){fvgType="BEARISH";fvgLow=fw[i].h;fvgHigh=fw[i-2].l}}
        val fvgBull=fvgType=="BULLISH";val fvgBear=fvgType=="BEARISH"
        val bullOb=c.takeLast(14).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(14).dropLast(1).lastOrNull{it.c>it.o};val bullObMid=bullOb?.let{(it.o+it.c)/2};val bearObMid=bearOb?.let{(it.o+it.c)/2}

        var bull=0;var bear=0;val br=mutableListOf<Pair<Int,String>>();val sr=mutableListOf<Pair<Int,String>>()
        fun b(p:Int,x:String){bull+=p;br+=p to x};fun s(p:Int,x:String){bear+=p;sr+=p to x}
        if(e20>e50)b(9,"EMA20 above EMA50")else s(9,"EMA20 below EMA50");if(s20>s50)b(7,"SMA20 above SMA50")else s(7,"SMA20 below SMA50");if(last.c>e150)b(5,"Price above EMA150")else s(5,"Price below EMA150")
        if(slopeBull)b(6,"EMA slope rising");if(slopeBear)s(6,"EMA slope falling");if(r>=54)b(6,"RSI bullish ${one(r)}")else if(r<=46)s(6,"RSI bearish ${one(r)}")
        if(rsiBullDiv)b(15,"Bullish RSI divergence");if(rsiBearDiv)s(15,"Bearish RSI divergence");if(macd>0)b(5,"MACD above zero")else s(5,"MACD below zero");if(macd>macdPrev)b(6,"MACD pressure rising")else s(6,"MACD pressure falling")
        if(bosBull)b(16,"Bullish BOS / breakout");if(bosBear)s(16,"Bearish BOS / breakout");if(retestBull)b(18,"Bullish breakout retest held");if(retestBear)s(18,"Bearish breakout retest held")
        if(stopHuntBull)b(20,"Sell-side liquidity / SL hunt reclaimed");if(stopHuntBear)s(20,"Buy-side liquidity / SL hunt rejected");if(fakeBull)b(18,"Bearish break failed — bullish fakeout");if(fakeBear)s(18,"Bullish break failed — bearish fakeout")
        if(chochBull)b(16,"Bullish CHoCH");if(chochBear)s(16,"Bearish CHoCH");if(fvgBull)b(8,"Bullish FVG context");if(fvgBear)s(8,"Bearish FVG context");if(bullObMid!=null)b(5,"Bullish order-block context");if(bearObMid!=null)s(5,"Bearish order-block context")
        if(displacementBull)b(10,"Bullish displacement / pressure");if(displacementBear)s(10,"Bearish displacement / pressure");if(pullbackBull)b(8,"Recent EMA pullback held");if(pullbackBear)s(8,"Recent EMA rejection held");if(nearSupport)b(5,"Near structural support");if(nearResistance)s(5,"Near structural resistance")
        irBull?.let{m->if(m.continuationStrength>=20&&!m.reversalRisk)b(14,"Strong bullish impulse / weak retracement ${pct(m.retracementRatio)}") else if(m.continuationStrength>=10&&!m.reversalRisk)b(8,"Healthy bullish retracement ${pct(m.retracementRatio)}") else if(m.reversalRisk)s(10,"Bull impulse damaged by ${pct(m.retracementRatio)} aggressive retracement")}
        irBear?.let{m->if(m.continuationStrength>=20&&!m.reversalRisk)s(14,"Strong bearish impulse / weak retracement ${pct(m.retracementRatio)}") else if(m.continuationStrength>=10&&!m.reversalRisk)s(8,"Healthy bearish retracement ${pct(m.retracementRatio)}") else if(m.reversalRisk)b(10,"Bear impulse damaged by ${pct(m.retracementRatio)} aggressive retracement")}

        val bullIR=irBull?.let{!it.reversalRisk&&it.continuationStrength>=10}==true;val bearIR=irBear?.let{!it.reversalRisk&&it.continuationStrength>=10}==true
        val bullLiquidity=(stopHuntBull||fakeBull)&&(chochBull||rsiBullDiv||pressureBull||momentumBull);val bearLiquidity=(stopHuntBear||fakeBear)&&(chochBear||rsiBearDiv||pressureBear||momentumBear)
        val bullRetest=retestBull&&(trendBull||momentumBull||fvgBull);val bearRetest=retestBear&&(trendBear||momentumBear||fvgBear)
        val bullContinuation=trendBull&&slopeBull&&(momentumBull||pressureBull||pullbackBull||bullIR)&&(pullbackBull||fvgBull||bullObMid!=null||nearSupport||bullIR)
        val bearContinuation=trendBear&&slopeBear&&(momentumBear||pressureBear||pullbackBear||bearIR)&&(pullbackBear||fvgBear||bearObMid!=null||nearResistance||bearIR)
        val bullChoch=chochBull&&(stopHuntBull||rsiBullDiv||displacementBull||pressureBull);val bearChoch=chochBear&&(stopHuntBear||rsiBearDiv||displacementBear||pressureBear)
        val bullBreakout=bosBull&&slopeBull&&(momentumBull||displacementBull||pressureBull);val bearBreakout=bosBear&&slopeBear&&(momentumBear||displacementBear||pressureBear)
        val bullFamily=listOf(bullLiquidity,bullRetest,bullContinuation,bullChoch,bullBreakout).count{it};val bearFamily=listOf(bearLiquidity,bearRetest,bearContinuation,bearChoch,bearBreakout).count{it}
        val bullValid=bullFamily>0&&bull>=40;val bearValid=bearFamily>0&&bear>=40
        if(!bullValid&&!bearValid)return null
        val dir=when{bullValid&&!bearValid->"BUY";bearValid&&!bullValid->"SELL";bull-bear>=4->"BUY";bear-bull>=4->"SELL";else->return null}
        val win=if(dir=="BUY")bull else bear;val lose=if(dir=="BUY")bear else bull;val sep=win-lose;val family=if(dir=="BUY")bullFamily else bearFamily;val selectedIr=if(dir=="BUY")irBull else irBear

        val matchingFvg=(dir=="BUY"&&fvgBull)||(dir=="SELL"&&fvgBear);val fvgMid=if(matchingFvg&&fvgLow!=null&&fvgHigh!=null)(fvgLow!!+fvgHigh!!)/2 else null;val obMid=if(dir=="BUY")bullObMid else bearObMid
        val fallback=c.takeLast(24);val impulseHigh=selectedIr?.impulseHigh?:fallback.maxOf{it.h};val impulseLow=selectedIr?.impulseLow?:fallback.minOf{it.l};val impulseRange=(selectedIr?.impulseDistance?:((impulseHigh-impulseLow))).coerceAtLeast(a)
        val candidates=mutableListOf<Pair<String,Double>>();if(fvgMid!=null)candidates+="FVG midpoint" to fvgMid;if(obMid!=null)candidates+="order-block midpoint" to obMid
        if(dir=="BUY"&&e20<last.c)candidates+="EMA20 pullback" to e20;if(dir=="SELL"&&e20>last.c)candidates+="EMA20 pullback" to e20;if(dir=="BUY"&&e50<last.c)candidates+="EMA50 pullback" to e50;if(dir=="SELL"&&e50>last.c)candidates+="EMA50 pullback" to e50
        if(dir=="BUY"&&retestBull)candidates+="breakout retest" to max(shortHigh,priorHigh);if(dir=="SELL"&&retestBear)candidates+="breakout retest" to min(shortLow,priorLow)
        if(selectedIr!=null&&!selectedIr.reversalRisk){candidates+=if(dir=="BUY")"25% impulse retracement" to (impulseHigh-impulseRange*.25) else "25% impulse retracement" to (impulseLow+impulseRange*.25);candidates+=if(dir=="BUY")"35% impulse retracement" to (impulseHigh-impulseRange*.35) else "35% impulse retracement" to (impulseLow+impulseRange*.35)}
        val valid=candidates.filter{(_,v)->val dist=abs(last.c-v)/a;val directional=if(dir=="BUY")v<last.c else v>last.c;val untouched=if(dir=="BUY")v<=last.l-a*.01 else v>=last.h+a*.01;directional&&untouched&&dist in .05..2.60}.sortedBy{abs(last.c-it.second)}
        val chosen=valid.firstOrNull()?:run{val v=if(dir=="BUY")min(last.l-a*.03,last.c-a*.16) else max(last.h+a*.03,last.c+a*.16);"micro structure retest" to v}
        val entrySource=chosen.first;val entry=chosen.second

        val tf=tfMinutes(timeframe);val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=15->1.08;tf<=30->1.22;else->1.38};val structureRisk=if(dir=="BUY")entry-(localLow-a*.08)else(localHigh+a*.08)-entry;val risk=max(a*.62,min(max(structureRisk,0.0),a*maxRiskAtr)).coerceAtMost(a*maxRiskAtr);val sl=if(dir=="BUY")entry-risk else entry+risk
        val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=15->1.05;tf<=30->1.18;else->1.35};val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=15->1.50;tf<=30->1.70;else->1.95};val rawTp1=if(dir=="BUY")entry+a*tp1Atr else entry-a*tp1Atr;val tp2=if(dir=="BUY")entry+a*tp2Atr else entry-a*tp2Atr
        val nearest=if(dir=="BUY")listOf(localHigh,priorHigh,swingHigh).filter{it>entry+a*.20}.minOrNull() else listOf(localLow,priorLow,swingLow).filter{it<entry-a*.20}.maxOrNull();val tp1=if(nearest!=null){if(dir=="BUY")min(rawTp1,nearest)else max(rawTp1,nearest)}else rawTp1
        val familyName=when{dir=="BUY"&&bullLiquidity->"liquidity / SL-hunt reversal";dir=="SELL"&&bearLiquidity->"liquidity / SL-hunt reversal";dir=="BUY"&&bullRetest->"breakout + retest continuation";dir=="SELL"&&bearRetest->"breakout + retest continuation";dir=="BUY"&&bullChoch->"CHoCH reversal";dir=="SELL"&&bearChoch->"CHoCH reversal";dir=="BUY"&&bullBreakout->"breakout momentum continuation";dir=="SELL"&&bearBreakout->"breakout momentum continuation";else->"established trend pullback"}
        val score=(60+sep+(family*5)+((selectedIr?.continuationStrength?:0).coerceIn(-8,16)/2)).coerceIn(60,97);val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(10).map{"${it.second} (+${it.first})"};val strongest=reasons.take(5).joinToString("; ");val irText=selectedIr?.let{" Impulse/retracement ${pct(it.retracementRatio)} depth, ${two(it.speedRatio)}x speed, ${two(it.counterBodyRatio)}x counter-body, ${it.impulseCandles}/${it.retracementCandles} candles."}.orEmpty()
        val validity="No fixed candle-count expiry. Pending remains valid only while live trend, momentum, liquidity, impulse/retracement quality and structure support the setup; abnormal volatility or structural failure expires it."
        val setupReason="$dir $familyName. Best current setup family. Evidence: $strongest.$irText Pending entry uses $entrySource at ${fmt(entry)} outside the signal candle."
        return Signal(UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,bull,bear,0,System.currentTimeMillis(),last.t,"PENDING",reasons,e20,e50,r,macd,a,fvgType,fvgLow,fvgHigh,validity,"SL is behind live invalidation structure and capped by ${two(maxRiskAtr)} ATR.","TP1 uses nearby structure and ${two(tp1Atr)} ATR.","TP2 uses extended ${two(tp2Atr)} ATR.",setupReason)
    }

    fun sameSetup(a:Signal,b:Signal):Boolean{if(a.symbol!=b.symbol||a.timeframe!=b.timeframe||a.direction!=b.direction)return false;val at=max(a.atr,b.atr).coerceAtLeast(1e-9);return abs(a.entry-b.entry)<=at*.55&&abs(a.sl-b.sl)<=at*.80}
    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{if(c.size<60)return SetupCheck(true,"Waiting for enough fresh data.");if(isHighVolatility(c))return SetupCheck(false,"Pending setup invalidated by abnormal live volatility.");val last=c.last();val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14);val m=ema(close,12).last()-ema(close,26).last();val a=atr(c,14).coerceAtLeast(1e-9);val p=c.takeLast(18).dropLast(1);val hi=p.maxOf{it.h};val lo=p.minOf{it.l};var opposite=0;if(s.direction=="BUY"){if(last.c<s.sl)return SetupCheck(false,"BUY invalidated: price closed through structural SL.");if(e20<e50)opposite++;if(rr<43)opposite++;if(m<0)opposite++;if(last.c<lo)opposite+=2}else{if(last.c>s.sl)return SetupCheck(false,"SELL invalidated: price closed through structural SL.");if(e20>e50)opposite++;if(rr>57)opposite++;if(m>0)opposite++;if(last.c>hi)opposite+=2};val ir=impulseRetracement(c,s.direction,a);if(ir?.reversalRisk==true)return SetupCheck(false,"Setup expired: retracement reached ${pct(ir.retracementRatio)} with aggressive counter-pressure.");return if(opposite>=3)SetupCheck(false,"Original setup is no longer valid: live trend/momentum/structure changed before entry.") else SetupCheck(true,ir?.let{"Live thesis valid • retracement ${pct(it.retracementRatio)}, speed ${two(it.speedRatio)}x."}?:"Live setup thesis remains valid.")}
    fun isHighVolatility(c:List<Candle>):Boolean{if(c.size<25)return false;val a=atr(c.dropLast(1),14).coerceAtLeast(1e-9);val last=c.last();val tr=max(last.h-last.l,max(abs(last.h-c[c.lastIndex-1].c),abs(last.l-c[c.lastIndex-1].c)));val recent=c.takeLast(20).dropLast(1).map{it.h-it.l}.sorted();val med=recent[recent.size/2].coerceAtLeast(1e-9);return tr>a*2.5||tr>med*3.1}
    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{if(c.size<100)return "$symbol $timeframe • waiting for enough live history.";if(isHighVolatility(c))return "$symbol $timeframe • abnormal volatility; waiting for structure to stabilize.";val close=c.map{it.c};val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14);val a=atr(c,14).coerceAtLeast(1e-9);val best=listOfNotNull(impulseRetracement(c,"BUY",a),impulseRetracement(c,"SELL",a)).maxByOrNull{it.continuationStrength};val ir=best?.let{" Latest ${it.direction.lowercase()} impulse: ${pct(it.retracementRatio)} retracement, ${two(it.speedRatio)}x speed."}.orEmpty();return "$symbol $timeframe • no setup family has enough confirmation yet. EMA20 ${fmt(e20)}, EMA50 ${fmt(e50)}, RSI ${one(rr)}.$ir"}

    private fun impulseRetracement(c:List<Candle>,direction:String,a:Double):IR?{if(c.size<20)return null;val w=c.takeLast(min(48,c.size));var bs=-1;var be=-1;var score=Double.NEGATIVE_INFINITY;for(len in 3..9)for(end in (len-1) until w.lastIndex){val start=end-len+1;val g=w.subList(start,end+1);val net=if(direction=="BUY")g.last().c-g.first().o else g.first().o-g.last().c;if(net<=a*.55)continue;val same=g.count{if(direction=="BUY")it.c>it.o else it.c<it.o}.toDouble()/len;val sc=net/a+same*1.4-(w.lastIndex-end)*.055;if(sc>score){score=sc;bs=start;be=end}};if(bs<0||be<0||be>=w.lastIndex)return null;val impulse=w.subList(bs,be+1);val retr=w.subList(be+1,w.size);if(retr.isEmpty()||retr.size>14)return null;val hi=impulse.maxOf{it.h};val lo=impulse.minOf{it.l};val dist=(hi-lo).coerceAtLeast(a*.35);val avgBody=impulse.map{abs(it.c-it.o)}.average().coerceAtLeast(1e-9);val rd=if(direction=="BUY")max(0.0,hi-retr.minOf{it.l}) else max(0.0,retr.maxOf{it.h}-lo);val ratio=rd/dist;val speed=(rd/retr.size.coerceAtLeast(1))/(dist/impulse.size.coerceAtLeast(1));val counter=retr.filter{if(direction=="BUY")it.c<it.o else it.c>it.o};val cr=(if(counter.isEmpty())0.0 else counter.map{abs(it.c-it.o)}.average())/avgBody;val resumed=if(direction=="BUY")retr.takeLast(min(2,retr.size)).any{it.c>it.o} else retr.takeLast(min(2,retr.size)).any{it.c<it.o};var st=when{ratio<=.25->18;ratio<=.40->14;ratio<=.50->8;ratio<=.60->2;ratio<=.65->-4;else->-14};st+=when{speed<.45->10;speed<.70->7;speed<1.0->3;speed<1.25->-4;else->-9};st+=when{cr<.45->10;cr<.70->7;cr<1.0->2;cr<1.20->-4;else->-9};if(resumed)st+=5;val broken=if(direction=="BUY")retr.any{it.c<lo-a*.05}else retr.any{it.c>hi+a*.05};val risk=broken||(ratio>.65&&(speed>.85||cr>.95))||(ratio>.58&&speed>1.15&&cr>1.05);return IR(direction,dist,impulse.size,avgBody,rd,retr.size,ratio,speed,cr,st,risk,hi,lo,resumed)}
    private fun bullishRsiDivergence(c:List<Candle>):Boolean{if(c.size<35)return false;val x=c.takeLast(30);val a=x.take(15);val b=x.takeLast(15);return b.minOf{it.l}<a.minOf{it.l}&&rsi(b.map{it.c},7)>rsi(a.map{it.c},7)+3}
    private fun bearishRsiDivergence(c:List<Candle>):Boolean{if(c.size<35)return false;val x=c.takeLast(30);val a=x.take(15);val b=x.takeLast(15);return b.maxOf{it.h}>a.maxOf{it.h}&&rsi(b.map{it.c},7)<rsi(a.map{it.c},7)-3}
    private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"5m"->5;"15m"->15;"30m"->30;"1h"->60;else->15}
    private fun one(v:Double)=String.format(Locale.US,"%.1f",v);private fun two(v:Double)=String.format(Locale.US,"%.2f",v);private fun pct(v:Double)=String.format(Locale.US,"%.0f%%",v*100);private fun fmt(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun sma(v:List<Double>,p:Int)=v.takeLast(min(p,v.size)).average();private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{if(c.size<2)return 0.0;var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
}
