package com.mh.analysis

import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Permanent source implementation of the seven video-reference techniques that
 * previously existed only as CI patch steps.
 *
 * 1. Projected trendline third-touch/retest rejection
 * 2. Liquidity-to-liquidity rotation
 * 3. Broken-level ladder continuation
 * 4. Dominant-wick reclaim / wick-fill rejection
 * 5. Range-liquidity compression -> external sweep -> reclaim/rejection
 * 6. Abnormal counter-candle / fault-level retest
 * 7. Asymmetric structure-based risk/reward quality
 */
object VideoTechniqueEngine {
    private data class Level(val price:Double,val touches:Int)
    private data class Evidence(val weight:Int,val text:String,val level:Double?=null)

    fun analyzeOrEnhance(symbol:String,timeframe:String,c:List<Candle>,base:Signal?):Signal?{
        if(c.size<60)return base
        val a=atr(c,14).coerceAtLeast(1e-9)
        val last=c.last();val prev=c[c.lastIndex-1]
        val closes=c.map{it.c}
        val e20=ema(closes,20).last();val e50=ema(closes,50).last();val r=rsi(closes,14)
        val macd=ema(closes,12).last()-ema(closes,26).last()
        val macdPrev=ema(closes.dropLast(1),12).last()-ema(closes.dropLast(1),26).last()
        val range=(last.h-last.l).coerceAtLeast(1e-9);val body=abs(last.c-last.o)
        val lowerWick=min(last.o,last.c)-last.l;val upperWick=last.h-max(last.o,last.c)
        val bullPressure=last.c>last.o&&body/range>=.42&&last.c>=last.h-range*.32
        val bearPressure=last.c<last.o&&body/range>=.42&&last.c<=last.l+range*.32
        val bullMomentum=(e20>=e50&&macd>=macdPrev&&r>=48)||bullPressure
        val bearMomentum=(e20<=e50&&macd<=macdPrev&&r<=52)||bearPressure

        val lows=pivotLevels(c,false,a);val highs=pivotLevels(c,true,a)
        val support=lows.filter{it.price<last.c+a*.30}.maxByOrNull{it.price}
        val resistance=highs.filter{it.price>last.c-a*.30}.minByOrNull{it.price}
        val sweepBull=support?.let{last.l<it.price-a*.03&&last.c>it.price+a*.01}==true
        val sweepBear=resistance?.let{last.h>it.price+a*.03&&last.c<it.price-a*.01}==true

        val bullTrendline=projectedTrendline(c,"BUY",a)
        val bearTrendline=projectedTrendline(c,"SELL",a)
        val bullTrendlineReaction=bullTrendline?.let{last.l<=it+a*.20&&last.c>=it-a*.04&&last.c>last.o&&(lowerWick>=body*.70||bullPressure)}==true
        val bearTrendlineReaction=bearTrendline?.let{last.h>=it-a*.20&&last.c<=it+a*.04&&last.c<last.o&&(upperWick>=body*.70||bearPressure)}==true

        val bullWickSource=dominantWickSource(c,"BUY",a)
        val bearWickSource=dominantWickSource(c,"SELL",a)
        val bullWickReclaim=bullWickSource?.let{x->val edge=min(x.o,x.c);val depth=(edge-x.l).coerceAtLeast(1e-9);last.l<=edge+a*.10&&last.l>=x.l-a*.10&&last.c>edge+min(a*.08,depth*.18)&&last.c>last.o&&bullMomentum}==true
        val bearWickReclaim=bearWickSource?.let{x->val edge=max(x.o,x.c);val depth=(x.h-edge).coerceAtLeast(1e-9);last.h>=edge-a*.10&&last.h<=x.h+a*.10&&last.c<edge-min(a*.08,depth*.18)&&last.c<last.o&&bearMomentum}==true

        val bullOpp=highs.filter{it.price>last.c+a*.30}.minByOrNull{it.price}
        val bearOpp=lows.filter{it.price<last.c-a*.30}.maxByOrNull{it.price}
        val bullRoute=(sweepBull||support?.let{it.touches>=3&&last.l<=it.price+a*.12&&last.c>it.price}==true)&&bullOpp!=null&&(bullOpp.price-last.c)>=a*.65&&bullMomentum
        val bearRoute=(sweepBear||resistance?.let{it.touches>=3&&last.h>=it.price-a*.12&&last.c<it.price}==true)&&bearOpp!=null&&(last.c-bearOpp.price)>=a*.65&&bearMomentum

        val bullLadder=nearestBrokenResistance(c,a,last.c)
        val bearLadder=nearestBrokenSupport(c,a,last.c)
        val bullLadderReaction=bullLadder!=null&&bullOpp!=null&&last.c>bullLadder&&abs(last.l-bullLadder)<=a*.30&&(bullOpp.price-last.c)>=a*.55&&bullMomentum
        val bearLadderReaction=bearLadder!=null&&bearOpp!=null&&last.c<bearLadder&&abs(last.h-bearLadder)<=a*.30&&(last.c-bearOpp.price)>=a*.55&&bearMomentum

        val compression=liquidityCompressionRange(c,a)
        val bullCompression=compression?.let{box->c.takeLast(min(4,c.size)).any{x->x.l<box.first-a*.05&&x.c>box.first-a*.02}&&last.c>box.first+a*.04&&bullMomentum}==true
        val bearCompression=compression?.let{box->c.takeLast(min(4,c.size)).any{x->x.h>box.second+a*.05&&x.c<box.second+a*.02}&&last.c<box.second-a*.04&&bearMomentum}==true

        val bullFault=faultLevel(c,"BUY",a)
        val bearFault=faultLevel(c,"SELL",a)
        val bullFaultReaction=bullFault?.let{last.l<=it+a*.18&&last.c>=it-a*.03&&last.c>last.o&&bullMomentum}==true
        val bearFaultReaction=bearFault?.let{last.h>=it-a*.18&&last.c<=it+a*.03&&last.c<last.o&&bearMomentum}==true

        val bull=mutableListOf<Evidence>();val bear=mutableListOf<Evidence>()
        if(bullTrendlineReaction)bull+=Evidence(16,"Ascending trendline third-touch / retest rejection",bullTrendline)
        if(bearTrendlineReaction)bear+=Evidence(16,"Descending trendline third-touch / retest rejection",bearTrendline)
        if(bullRoute)bull+=Evidence(if(sweepBull)19 else 14,"Liquidity-to-liquidity BUY rotation with a clear opposing pool",support?.price)
        if(bearRoute)bear+=Evidence(if(sweepBear)19 else 14,"Liquidity-to-liquidity SELL rotation with a clear opposing pool",resistance?.price)
        if(bullLadderReaction)bull+=Evidence(15,"Broken-level ladder held with room to the next resistance/liquidity objective",bullLadder)
        if(bearLadderReaction)bear+=Evidence(15,"Broken-level ladder held with room to the next support/liquidity objective",bearLadder)
        if(bullWickReclaim)bull+=Evidence(16,"Dominant lower-wick reclaim / wick-fill rejection",bullWickSource?.let{min(it.o,it.c)})
        if(bearWickReclaim)bear+=Evidence(16,"Dominant upper-wick reclaim / wick-fill rejection",bearWickSource?.let{max(it.o,it.c)})
        if(bullCompression)bull+=Evidence(18,"Range liquidity compressed, sell-side edge swept, then reclaimed",compression?.first)
        if(bearCompression)bear+=Evidence(18,"Range liquidity compressed, buy-side edge swept, then rejected",compression?.second)
        if(bullFaultReaction)bull+=Evidence(17,"Bullish revisit/rejection of an abnormal counter-candle fault level",bullFault)
        if(bearFaultReaction)bear+=Evidence(17,"Bearish revisit/rejection of an abnormal counter-candle fault level",bearFault)

        if(base!=null)return enhance(base,bull,bear)

        val bullWeight=bull.sumOf{it.weight};val bearWeight=bear.sumOf{it.weight}
        if(bullWeight<14&&bearWeight<14)return null
        val dir=when{
            bullWeight>=14&&bullWeight-bearWeight>=6&&bullMomentum->"BUY"
            bearWeight>=14&&bearWeight-bullWeight>=6&&bearMomentum->"SELL"
            else->return null
        }
        val evidence=if(dir=="BUY")bull else bear
        if(evidence.isEmpty())return null

        val levels=evidence.mapNotNull{it.level}.filter{v->
            val directional=if(dir=="BUY")v<last.c else v>last.c
            val distance=abs(last.c-v)/a
            directional&&distance in .04..2.6
        }.sortedBy{abs(last.c-it)}
        val entry=levels.firstOrNull()?:if(dir=="BUY")min(last.l-a*.03,last.c-a*.16)else max(last.h+a*.03,last.c+a*.16)

        val local=c.takeLast(min(26,c.size)).dropLast(1)
        val localLow=local.minOf{it.l};val localHigh=local.maxOf{it.h}
        val structuralRisk=if(dir=="BUY")entry-(localLow-a*.08)else(localHigh+a*.08)-entry
        val risk=max(a*.65,min(max(structuralRisk,0.0),a*1.30)).coerceAtMost(a*1.30)
        val sl=if(dir=="BUY")entry-risk else entry+risk

        val rawTp1=if(dir=="BUY")entry+a*1.20 else entry-a*1.20
        val rawTp2=if(dir=="BUY")entry+a*1.85 else entry-a*1.85
        val objective1=if(dir=="BUY")highs.filter{it.price>entry+a*.35}.minByOrNull{it.price}?.price else lows.filter{it.price<entry-a*.35}.maxByOrNull{it.price}?.price
        val tp1=objective1?.let{if(dir=="BUY")max(rawTp1,it)else min(rawTp1,it)}?:rawTp1
        val objective2=if(dir=="BUY")highs.filter{it.price>tp1+a*.25}.minByOrNull{it.price}?.price else lows.filter{it.price<tp1-a*.25}.maxByOrNull{it.price}?.price
        val tp2=objective2?:rawTp2

        val rr1=abs(tp1-entry)/risk.coerceAtLeast(1e-9);val rr2=abs(tp2-entry)/risk.coerceAtLeast(1e-9)
        val rrBonus=when{rr1>=2.50->8;rr1>=2.00->6;rr1>=1.60->3;else->0}
        val directionalWeight=if(dir=="BUY")bullWeight else bearWeight
        val opposingWeight=if(dir=="BUY")bearWeight else bullWeight
        val score=(62+(directionalWeight/4)-min(8,opposingWeight/6)+rrBonus).coerceIn(60,97)
        val reasonLines=evidence.sortedByDescending{it.weight}.map{"${it.text} (+${it.weight})"}.toMutableList()
        reasonLines+="Asymmetric structure-based R:R • TP1 ${two(rr1)}R • TP2 ${two(rr2)}R${if(rrBonus>0)" (+$rrBonus)" else ""}"

        val fvg=recentFvg(c)
        val family=evidence.maxByOrNull{it.weight}?.text?:"video-reference structure"
        val setupReason="$dir video-reference setup. Decisive pattern: $family. Entry is a pullback/retest level outside the current candle; SL is behind nearby structure and targets use opposing structure/liquidity when available."
        return Signal(
            UUID.randomUUID().toString(),symbol,timeframe,dir,entry,sl,tp1,tp2,score,
            if(dir=="BUY")bullWeight else 0,if(dir=="SELL")bearWeight else 0,0,
            System.currentTimeMillis(),last.t,"PENDING",reasonLines.take(12),e20,e50,r,macd,a,
            fvg?.first,fvg?.second?.first,fvg?.second?.second,
            "No fixed candle-count expiry. The setup remains valid only while live structure, momentum and the originating video-pattern thesis remain intact.",
            "SL is behind nearby live invalidation structure and ATR-capped risk.",
            "TP1 targets the next usable structure/liquidity objective with asymmetric reward quality.",
            "TP2 targets the next extension/liquidity objective.",setupReason
        )
    }

    private fun enhance(base:Signal,bull:List<Evidence>,bear:List<Evidence>):Signal{
        val aligned=if(base.direction=="BUY")bull else bear
        val opposite=if(base.direction=="BUY")bear else bull
        val risk=abs(base.entry-base.sl).coerceAtLeast(1e-9)
        val rr1=abs(base.tp1-base.entry)/risk;val rr2=abs(base.tp2-base.entry)/risk
        val rrBonus=when{rr1>=2.50->8;rr1>=2.00->6;rr1>=1.60->3;else->0}
        var score=base.score+min(9,aligned.sumOf{it.weight}/10)+rrBonus-min(5,opposite.sumOf{it.weight}/14)
        val extra=aligned.sortedByDescending{it.weight}.map{"${it.text} (+${it.weight})"}
        val rr="Asymmetric structure-based R:R • TP1 ${two(rr1)}R • TP2 ${two(rr2)}R${if(rrBonus>0)" (+$rrBonus)" else ""}"
        val reasons=(extra+base.reasons+rr).distinct().take(12)
        return base.copy(score=score.coerceIn(60,97),reasons=reasons)
    }

    private fun pivotLevels(c:List<Candle>,high:Boolean,a:Double):List<Level>{
        val w=c.takeLast(min(90,c.size));if(w.size<9)return emptyList()
        val pts=mutableListOf<Double>()
        for(i in 2 until w.size-2){
            val x=w[i]
            val ok=if(high)x.h>=w[i-1].h&&x.h>=w[i-2].h&&x.h>=w[i+1].h&&x.h>=w[i+2].h else x.l<=w[i-1].l&&x.l<=w[i-2].l&&x.l<=w[i+1].l&&x.l<=w[i+2].l
            if(ok)pts+=if(high)x.h else x.l
        }
        val groups=mutableListOf<MutableList<Double>>()
        for(p in pts.sorted()){
            val g=groups.lastOrNull()
            if(g!=null&&abs(g.average()-p)<=a*.18)g+=p else groups+=mutableListOf(p)
        }
        return groups.map{Level(it.average(),it.size)}.sortedBy{it.price}
    }

    private fun projectedTrendline(c:List<Candle>,direction:String,a:Double):Double?{
        val w=c.takeLast(min(56,c.size));if(w.size<12)return null
        val pts=mutableListOf<Pair<Int,Double>>()
        for(i in 2 until w.size-2){
            val x=w[i]
            if(direction=="SELL"&&x.h>=w[i-1].h&&x.h>=w[i-2].h&&x.h>=w[i+1].h&&x.h>=w[i+2].h)pts+=i to x.h
            if(direction=="BUY"&&x.l<=w[i-1].l&&x.l<=w[i-2].l&&x.l<=w[i+1].l&&x.l<=w[i+2].l)pts+=i to x.l
        }
        if(pts.size<2)return null
        for(j in pts.lastIndex downTo 1){
            val p2=pts[j];val p1=pts.subList(0,j).lastOrNull{p2.first-it.first>=4}?:continue
            val slope=(p2.second-p1.second)/(p2.first-p1.first).toDouble()
            val ordered=if(direction=="SELL")p2.second<p1.second-a*.05 else p2.second>p1.second+a*.05
            val goodSlope=if(direction=="SELL")slope< -a*.006 else slope>a*.006
            if(!ordered||!goodSlope)continue
            val projected=p2.second+slope*(w.lastIndex-p2.first)
            if(abs(projected-w.last().c)<=a*2.2)return projected
        }
        return null
    }

    private fun dominantWickSource(c:List<Candle>,direction:String,a:Double):Candle?{
        val w=c.takeLast(min(14,c.size)).dropLast(1)
        return w.asReversed().firstOrNull{x->
            val body=abs(x.c-x.o).coerceAtLeast(a*.04);val range=(x.h-x.l).coerceAtLeast(1e-9)
            if(direction=="BUY"){val wick=min(x.o,x.c)-x.l;wick>=body*1.80&&wick>=a*.50&&wick/range>=.52}
            else{val wick=x.h-max(x.o,x.c);wick>=body*1.80&&wick>=a*.50&&wick/range>=.52}
        }
    }

    private fun nearestBrokenResistance(c:List<Candle>,a:Double,price:Double):Double?{
        return pivotLevels(c,true,a).filter{it.price<price&&c.takeLast(8).any{x->x.c>it.price+a*.05}}.maxByOrNull{it.price}?.price
    }

    private fun nearestBrokenSupport(c:List<Candle>,a:Double,price:Double):Double?{
        return pivotLevels(c,false,a).filter{it.price>price&&c.takeLast(8).any{x->x.c<it.price-a*.05}}.minByOrNull{it.price}?.price
    }

    private fun liquidityCompressionRange(c:List<Candle>,a:Double):Pair<Double,Double>?{
        if(c.size<18)return null
        val w=c.takeLast(min(22,c.size)).dropLast(1);if(w.size<12)return null
        for(len in 8..min(16,w.size)){
            val box=w.takeLast(len);val hi=box.maxOf{it.h};val lo=box.minOf{it.l};val span=hi-lo
            if(span<a*.70||span>a*3.20)continue
            val ht=box.count{hi-it.h<=a*.18};val lt=box.count{it.l-lo<=a*.18};val mid=(hi+lo)/2
            if(ht>=2&&lt>=2&&box.count{abs(it.c-mid)<=span*.42}>=len/2)return lo to hi
        }
        return null
    }

    private fun faultLevel(c:List<Candle>,direction:String,a:Double):Double?{
        if(c.size<20)return null
        val w=c.takeLast(min(42,c.size));if(w.size<12)return null
        for(i in w.size-4 downTo 3){
            val x=w[i];if(abs(x.c-x.o)<a*.14)continue
            val before=w.subList(max(0,i-3),i);val after=w.subList(i+1,min(w.size,i+4));if(before.isEmpty()||after.isEmpty())continue
            if(direction=="BUY"){
                if(x.c>=x.o)continue
                if((before.count{it.c>it.o}>=2||after.count{it.c>it.o}>=2)&&after.maxOf{it.h}>x.h+a*.30)return max(x.o,x.c)
            }else{
                if(x.c<=x.o)continue
                if((before.count{it.c<it.o}>=2||after.count{it.c<it.o}>=2)&&after.minOf{it.l}<x.l-a*.30)return min(x.o,x.c)
            }
        }
        return null
    }

    private fun recentFvg(c:List<Candle>):Pair<String,Pair<Double,Double>>?{
        val w=c.takeLast(min(30,c.size));var out:Pair<String,Pair<Double,Double>>?=null
        for(i in 2 until w.size){
            if(w[i].l>w[i-2].h)out="BULLISH" to (w[i-2].h to w[i].l)
            if(w[i].h<w[i-2].l)out="BEARISH" to (w[i].h to w[i-2].l)
        }
        return out
    }

    private fun ema(v:List<Double>,p:Int):List<Double>{if(v.isEmpty())return emptyList();val k=2.0/(p.coerceAtMost(v.size)+1);val out=MutableList(v.size){0.0};out[0]=v[0];for(i in 1 until v.size)out[i]=v[i]*k+out[i-1]*(1-k);return out}
    private fun rsi(v:List<Double>,p:Int):Double{if(v.size<=p)return 50.0;var g=0.0;var l=0.0;for(i in v.size-p until v.size){val d=v[i]-v[i-1];if(d>0)g+=d else l-=d};if(l==0.0)return 100.0;val rs=g/l;return 100.0-100.0/(1+rs)}
    private fun atr(c:List<Candle>,p:Int):Double{if(c.size<2)return 0.0;var sum=0.0;var n=0;for(i in max(1,c.size-p) until c.size){sum+=max(c[i].h-c[i].l,max(abs(c[i].h-c[i-1].c),abs(c[i].l-c[i-1].c)));n++};return if(n==0)0.0 else sum/n}
    private fun two(v:Double)=String.format(Locale.US,"%.2f",v)
}
