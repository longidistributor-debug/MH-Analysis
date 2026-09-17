package com.mh.analysis

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Same-timeframe quality layer. It never reads another timeframe.
 * It enhances/filter signals produced by the structure + video-reference engines.
 */
object AdvancedMarketEngine {
    data class MarketMap(
        val regime:String,
        val atr:Double,
        val atrRatio:Double,
        val adx:Double,
        val plusDi:Double,
        val minusDi:Double,
        val vwap:Double?,
        val vwapDistanceAtr:Double?,
        val candleQuality:Int,
        val bullObLow:Double?,
        val bullObHigh:Double?,
        val bearObLow:Double?,
        val bearObHigh:Double?,
        val equalHigh:Double?,
        val equalLow:Double?,
        val fvgType:String?,
        val fvgLow:Double?,
        val fvgHigh:Double?,
        val fvgFillPct:Int,
        val divergence:String?,
        val spreadAtr:Double?,
        val spreadWarning:Boolean,
        val severeSpread:Boolean
    )

    data class Assessment(
        val signal:Signal?,
        val map:MarketMap,
        val quality:Int,
        val grade:String,
        val decision:String,
        val reasons:List<String>,
        val warnings:List<String>
    )

    data class ReEvaluation(
        val state:String,
        val score:Int,
        val grade:String,
        val reasons:List<String>,
        val map:MarketMap,
        val replacement:Signal?=null
    )

    private data class Adx(val adx:Double,val plus:Double,val minus:Double)
    private data class Zone(val low:Double,val high:Double)
    private data class Fvg(val type:String,val low:Double,val high:Double,val fill:Int)
    private data class Div(val regularBull:Boolean,val regularBear:Boolean,val hiddenBull:Boolean,val hiddenBear:Boolean)

    fun grade(score:Int)=when{
        score>=86->"A+"
        score>=80->"A"
        score>=74->"B+"
        score>=68->"B"
        else->"C"
    }

    fun marketMap(symbol:String,timeframe:String,c:List<Candle>):MarketMap{
        if(c.size<30){
            return MarketMap("BUILDING",0.0,1.0,0.0,0.0,0.0,null,null,0,null,null,null,null,null,null,null,null,null,0,null,null,false,false)
        }
        val a=atr(c,14).coerceAtLeast(1e-9)
        val tr=trueRanges(c)
        val base=if(tr.size>28)tr.dropLast(min(14,tr.size)).takeLast(min(42,max(1,tr.size-14))).averageOr(a) else a
        val atrRatio=(a/base.coerceAtLeast(1e-9)).coerceIn(.2,4.0)
        val ad=adx(c,14)
        val vw=vwap(c.takeLast(min(160,c.size)))
        val last=c.last()
        val vdist=vw?.let{abs(last.c-it)/a}
        val quality=candleQuality(c,a)
        val bullOb=findOrderBlock(c,true,a)
        val bearOb=findOrderBlock(c,false,a)
        val eqh=equalLevel(c,true,a)
        val eql=equalLevel(c,false,a)
        val fvg=recentFvg(c)
        val div=divergence(c,a)
        val divText=when{
            div.regularBull->"Bullish divergence"
            div.regularBear->"Bearish divergence"
            div.hiddenBull->"Hidden bullish divergence"
            div.hiddenBear->"Hidden bearish divergence"
            else->null
        }
        val spreadAtr=LiveMarketState.spreadAtr(symbol,a)
        val spreadWarning=spreadAtr?.let{it>.08}==true
        val severeSpread=spreadAtr?.let{it>.18}==true
        val recent=c.takeLast(min(28,c.size)).dropLast(1)
        val recentHigh=recent.maxOfOrNull{it.h}?:last.h
        val recentLow=recent.minOfOrNull{it.l}?:last.l
        val breakoutUp=last.c>recentHigh+a*.15&&quality>=58
        val breakoutDown=last.c<recentLow-a*.15&&quality>=58
        val sweepLow=last.l<recentLow-a*.03&&last.c>recentLow
        val sweepHigh=last.h>recentHigh+a*.03&&last.c<recentHigh
        val reversal=(sweepLow&&(div.regularBull||quality>=62))||(sweepHigh&&(div.regularBear||quality>=62))
        val regime=when{
            atrRatio>=1.85->"HIGH_VOLATILITY"
            atrRatio<=.62&&ad.adx<18->"LOW_VOLATILITY"
            breakoutUp||breakoutDown->"BREAKOUT"
            reversal->"REVERSAL"
            ad.adx>=23->"TRENDING"
            else->"RANGING"
        }
        return MarketMap(
            regime,a,atrRatio,ad.adx,ad.plus,ad.minus,vw,vdist,quality,
            bullOb?.low,bullOb?.high,bearOb?.low,bearOb?.high,
            eqh,eql,fvg?.type,fvg?.low,fvg?.high,fvg?.fill,divText,
            spreadAtr,spreadWarning,severeSpread
        )
    }

    fun assess(symbol:String,timeframe:String,c:List<Candle>,base:Signal?):Assessment{
        val map=marketMap(symbol,timeframe,c)
        if(base==null){
            val why=when(map.regime){
                "RANGING"->"No clean same-timeframe structure setup survived the range/chop filters."
                "HIGH_VOLATILITY"->"No setup passed the high-volatility execution and structure filters."
                else->"No structure setup currently has enough same-timeframe confluence."
            }
            return Assessment(null,map,0,"-",why,emptyList(),mapWarnings(map))
        }
        val buy=base.direction=="BUY"
        val last=c.last()
        val risk=abs(base.entry-base.sl).coerceAtLeast(1e-9)
        val rr1=abs(base.tp1-base.entry)/risk
        val rr2=abs(base.tp2-base.entry)/risk
        val breakoutSetup=base.reasons.any{it.contains("BOS",true)||it.contains("breakout",true)||it.contains("displacement",true)}
        val continuationSetup=base.reasons.any{it.contains("continuation",true)||it.contains("pullback",true)||it.contains("retest",true)}
        val reasons=mutableListOf<String>()
        val warnings=mapWarnings(map).toMutableList()
        var delta=0

        val dmiAligned=if(buy)map.plusDi>map.minusDi else map.minusDi>map.plusDi
        when{
            map.adx>=28&&dmiAligned->{delta+=8;reasons+="Strong ADX/DMI trend alignment (${one(map.adx)})"}
            map.adx>=21&&dmiAligned->{delta+=4;reasons+="ADX/DMI supports the direction (${one(map.adx)})"}
            map.adx<16&&breakoutSetup->{delta-=10;warnings+="Low ADX: breakout lacks trend strength"}
            map.adx<16->{delta-=4;warnings+="Low ADX: market is choppy"}
            !dmiAligned&&map.adx>=24->{delta-=7;warnings+="DMI is strong against the signal direction"}
        }

        when{
            map.atrRatio in .85..1.65->{delta+=2;reasons+="ATR volatility is usable (${two(map.atrRatio)}× baseline)"}
            map.atrRatio>=1.85->{delta-=5;warnings+="ATR expansion is extreme; execution risk is higher"}
            map.atrRatio<=.62&&breakoutSetup->{delta-=7;warnings+="Volatility contraction makes the breakout less convincing"}
        }

        map.vwap?.let{vw->
            val aligned=if(buy)last.c>=vw else last.c<=vw
            if(aligned){delta+=4;reasons+="Price is aligned with VWAP"}else{delta-=4;warnings+="Price is on the wrong side of VWAP"}
            if((map.vwapDistanceAtr?:0.0)>2.2){delta-=6;warnings+="Price is overextended more than 2.2 ATR from VWAP"}
        }

        if(map.candleQuality>=72){delta+=6;reasons+="High-quality displacement/confirmation candle (${map.candleQuality}/100)"}
        else if(map.candleQuality<32){delta-=5;warnings+="Current candle quality is weak (${map.candleQuality}/100)"}

        val fvgAligned=(buy&&map.fvgType=="BULLISH")||(!buy&&map.fvgType=="BEARISH")
        val fvgOpposite=(buy&&map.fvgType=="BEARISH")||(!buy&&map.fvgType=="BULLISH")
        if(fvgAligned&&map.fvgFillPct<100){delta+=6;reasons+="Aligned ${map.fvgType} FVG remains ${100-map.fvgFillPct}% unfilled"}
        if(fvgOpposite&&map.fvgFillPct<65){delta-=4;warnings+="Opposing FVG remains active"}

        val alignedOb=if(buy)zone(map.bullObLow,map.bullObHigh) else zone(map.bearObLow,map.bearObHigh)
        alignedOb?.let{z->
            val dist=distanceToZone(last.c,z)/map.atr.coerceAtLeast(1e-9)
            if(dist<=.55){delta+=6;reasons+="Price is reacting near the aligned order block"}
        }

        if(buy&&map.equalLow!=null&&last.l<map.equalLow&&last.c>map.equalLow){delta+=7;reasons+="Equal-low liquidity was swept and reclaimed"}
        if(!buy&&map.equalHigh!=null&&last.h>map.equalHigh&&last.c<map.equalHigh){delta+=7;reasons+="Equal-high liquidity was swept and rejected"}
        if(buy&&map.equalHigh!=null&&map.equalHigh>last.c){delta+=2;reasons+="Buy-side liquidity remains above as a usable objective"}
        if(!buy&&map.equalLow!=null&&map.equalLow<last.c){delta+=2;reasons+="Sell-side liquidity remains below as a usable objective"}

        when(map.divergence){
            "Bullish divergence"->if(buy){delta+=5;reasons+="Bullish RSI divergence supports the setup"}else{delta-=4;warnings+="Bullish divergence conflicts with SELL"}
            "Bearish divergence"->if(!buy){delta+=5;reasons+="Bearish RSI divergence supports the setup"}else{delta-=4;warnings+="Bearish divergence conflicts with BUY"}
            "Hidden bullish divergence"->if(buy&&continuationSetup){delta+=4;reasons+="Hidden bullish divergence supports continuation"}
            "Hidden bearish divergence"->if(!buy&&continuationSetup){delta+=4;reasons+="Hidden bearish divergence supports continuation"}
        }

        when(map.regime){
            "TRENDING"->if(continuationSetup&&dmiAligned){delta+=5;reasons+="TRENDING regime favors continuation"}
            "BREAKOUT"->if(breakoutSetup){delta+=5;reasons+="BREAKOUT regime matches the setup"}
            "RANGING"->if(breakoutSetup){delta-=7;warnings+="RANGING regime lowers breakout confidence"}
            "HIGH_VOLATILITY"->{delta-=2;warnings+="High-volatility regime requires wider execution tolerance"}
            "LOW_VOLATILITY"->if(breakoutSetup){delta-=5;warnings+="Low-volatility regime can produce false breaks"}
        }

        when{
            rr1>=2.0->{delta+=6;reasons+="Strong risk/reward: TP1 ${two(rr1)}R"}
            rr1>=1.5->{delta+=3;reasons+="Acceptable risk/reward: TP1 ${two(rr1)}R"}
            rr1<1.15->{delta-=12;warnings+="Risk/reward below minimum (${two(rr1)}R)"}
        }
        if(rr2>=2.2)reasons+="Extended target offers ${two(rr2)}R"

        map.spreadAtr?.let{sp->
            when{
                sp>.18->{delta-=18;warnings+="Abnormal live spread (${two(sp)} ATR) blocks a fresh entry"}
                sp>.08->{delta-=6;warnings+="Live spread is wider than normal (${two(sp)} ATR)"}
                else->{delta+=2;reasons+="Live spread is acceptable"}
            }
        }

        val quality=(base.score+delta).coerceIn(0,99)
        val weakBreakout=breakoutSetup&&map.adx<16&&map.candleQuality<55
        val rejected=map.severeSpread||rr1<1.15||quality<68||weakBreakout
        val decision=when{
            map.severeSpread->"NO TRADE: live spread is abnormally wide."
            rr1<1.15->"NO TRADE: reward does not justify the structural risk."
            weakBreakout->"NO TRADE: breakout is weak relative to ATR/ADX/candle quality."
            quality<68->"NO TRADE: confluence quality is below the minimum threshold."
            else->"${base.direction} setup accepted by same-timeframe quality filters."
        }
        if(rejected)return Assessment(null,map,quality,grade(quality),decision,reasons.distinct(),warnings.distinct())

        val top=(reasons+base.reasons).distinct().take(10)
        val concise=top.take(3).joinToString("; ")
        val slAtr=abs(base.entry-base.sl)/map.atr.coerceAtLeast(1e-9)
        val enhanced=base.copy(
            score=quality,
            reasons=top,
            setupReason="${base.direction} because $concise.",
            validityReason="Valid only while this ${base.timeframe} structure remains intact, DMI does not reverse strongly, spread stays acceptable and structural invalidation is not breached.",
            slReason="${base.slReason} Stop distance is ${two(slAtr)} ATR from entry and remains behind the setup invalidation structure.",
            tp1Reason="${base.tp1Reason} TP1 provides ${two(rr1)}R and targets the nearest usable opposing structure/liquidity.",
            tp2Reason="${base.tp2Reason} TP2 extends to ${two(rr2)}R when structure continues."
        )
        return Assessment(enhanced,map,quality,grade(quality),decision,reasons.distinct(),warnings.distinct())
    }

    fun reevaluate(active:ActiveSignal,c:List<Candle>,replacement:Signal?):ReEvaluation{
        val s=active.signal
        val map=marketMap(s.symbol,s.timeframe,c)
        val reasons=mutableListOf<String>()
        val last=c.lastOrNull()
        if(last==null)return ReEvaluation("INVALID",0,"C",listOf("No fresh candle data is available."),map)

        if(active.state in setOf("STOPPED","EXPIRED","REVIEW")){
            return ReEvaluation("INVALID",s.score,grade(s.score),listOf("Stored setup state is ${active.state}."),map)
        }
        if(active.state=="TP1 HIT"){
            return ReEvaluation("TARGET REACHED",s.score,grade(s.score),listOf("TP1 has already been reached by fresh ${s.timeframe} price action."),map)
        }

        val slBroken=if(s.direction=="BUY")last.l<=s.sl else last.h>=s.sl
        if(slBroken)return ReEvaluation("INVALID",0,"C",listOf("Structural stop/invalidation level has been breached."),map)

        val setupCheck=AnalysisEngine.setupCheck(s,c)
        reasons+=setupCheck.reason
        if(!setupCheck.valid)return ReEvaluation("INVALID",max(0,s.score-20),"C",reasons,map)

        val replacementOpposite=replacement?.takeIf{it.direction!=s.direction&&it.score>=76}
        if(replacementOpposite!=null){
            reasons+="A fresh opposite ${replacementOpposite.direction} setup now has stronger confluence (${replacementOpposite.score}/100)."
            return ReEvaluation("REVERSED",replacementOpposite.score,grade(replacementOpposite.score),reasons,map,replacementOpposite)
        }

        val current=assess(s.symbol,s.timeframe,c,s)
        reasons+=current.reasons.take(4)
        reasons+=current.warnings.take(4)
        val quality=current.quality

        if(active.state=="PENDING"){
            val move=if(s.direction=="BUY")last.c-s.entry else s.entry-last.c
            if(move>map.atr*.75){
                reasons+="Price has moved too far from the planned entry; chasing would degrade entry quality."
                return ReEvaluation("WEAKENING",quality,grade(quality),reasons.distinct(),map)
            }
        }

        if(map.severeSpread){
            reasons+="Entry is temporarily blocked until live spread normalizes."
            return ReEvaluation("WEAKENING",quality,grade(quality),reasons.distinct(),map)
        }
        if(current.signal==null&&quality<58){
            reasons+="The original confluence has degraded below the continuation threshold."
            return ReEvaluation("INVALID",quality,grade(quality),reasons.distinct(),map)
        }
        if(current.signal==null||quality<72){
            reasons+="The setup is still structurally alive but quality has weakened."
            return ReEvaluation("WEAKENING",quality,grade(quality),reasons.distinct(),map)
        }
        reasons+="The original same-timeframe thesis remains intact."
        return ReEvaluation("STILL VALID",quality,grade(quality),reasons.distinct(),map)
    }

    private fun mapWarnings(m:MarketMap):List<String>{
        val out=mutableListOf<String>()
        if(m.spreadWarning)out+="Spread is wider than normal"
        if(m.regime=="HIGH_VOLATILITY")out+="High-volatility regime"
        if(m.regime=="RANGING"&&m.adx<18)out+="Choppy/ranging regime"
        if((m.vwapDistanceAtr?:0.0)>2.2)out+="Price is overextended from VWAP"
        return out
    }

    private fun trueRanges(c:List<Candle>):List<Double>{
        if(c.size<2)return emptyList()
        val out=ArrayList<Double>(c.size-1)
        for(i in 1 until c.size){
            val x=c[i];val p=c[i-1]
            out+=max(x.h-x.l,max(abs(x.h-p.c),abs(x.l-p.c)))
        }
        return out
    }

    private fun atr(c:List<Candle>,n:Int):Double{
        val tr=trueRanges(c);if(tr.isEmpty())return 0.0
        return tr.takeLast(min(n,tr.size)).average()
    }

    private fun adx(c:List<Candle>,n:Int):Adx{
        if(c.size<n+3)return Adx(0.0,0.0,0.0)
        val dx=mutableListOf<Double>();var lastPlus=0.0;var lastMinus=0.0
        for(end in n until c.size){
            var tr=0.0;var plus=0.0;var minus=0.0
            val start=max(1,end-n+1)
            for(i in start..end){
                val x=c[i];val p=c[i-1]
                tr+=max(x.h-x.l,max(abs(x.h-p.c),abs(x.l-p.c)))
                val up=x.h-p.h;val down=p.l-x.l
                if(up>down&&up>0)plus+=up
                if(down>up&&down>0)minus+=down
            }
            if(tr<=0)continue
            val pdi=100.0*plus/tr;val mdi=100.0*minus/tr
            val den=(pdi+mdi).coerceAtLeast(1e-9)
            dx+=100.0*abs(pdi-mdi)/den
            lastPlus=pdi;lastMinus=mdi
        }
        val a=if(dx.isEmpty())0.0 else dx.takeLast(min(n,dx.size)).average()
        return Adx(a,lastPlus,lastMinus)
    }

    private fun vwap(c:List<Candle>):Double?{
        val valid=c.filter{it.v>0.0&&it.v.isFinite()}
        if(valid.size<max(3,c.size/5))return null
        val vol=valid.sumOf{it.v};if(vol<=0)return null
        return valid.sumOf{((it.h+it.l+it.c)/3.0)*it.v}/vol
    }

    private fun candleQuality(c:List<Candle>,a:Double):Int{
        val x=c.last();val range=(x.h-x.l).coerceAtLeast(1e-9);val body=abs(x.c-x.o)
        val bodyPct=body/range
        val closeEdge=max(abs(x.c-x.h),abs(x.c-x.l))/range
        val expansion=(range/a.coerceAtLeast(1e-9)).coerceIn(0.0,1.8)/1.8
        val q=(bodyPct*58.0+(1.0-closeEdge.coerceIn(0.0,1.0))*22.0+expansion*20.0).toInt()
        return q.coerceIn(0,100)
    }

    private fun findOrderBlock(c:List<Candle>,bull:Boolean,a:Double):Zone?{
        val start=max(1,c.size-24)
        for(i in c.size-3 downTo start){
            val x=c[i]
            val opposite=if(bull)x.c<x.o else x.c>x.o
            if(!opposite)continue
            val after=c.subList(i+1,min(c.size,i+4))
            val displaced=if(bull)after.any{it.c>x.h+a*.25&&(it.c-it.o)>a*.25} else after.any{it.c<x.l-a*.25&&(it.o-it.c)>a*.25}
            if(displaced){
                return if(bull)Zone(x.l,max(x.o,x.c)) else Zone(min(x.o,x.c),x.h)
            }
        }
        return null
    }

    private fun recentFvg(c:List<Candle>):Fvg?{
        val start=max(2,c.size-45)
        for(i in c.lastIndex downTo start){
            if(c[i].l>c[i-2].h){
                val low=c[i-2].h;val high=c[i].l
                val after=if(i<c.lastIndex)c.subList(i+1,c.size) else emptyList()
                val minLow=after.minOfOrNull{it.l}?:high
                val fill=when{minLow<=low->100;minLow>=high->0;else->(((high-minLow)/(high-low))*100.0).toInt().coerceIn(0,100)}
                return Fvg("BULLISH",low,high,fill)
            }
            if(c[i].h<c[i-2].l){
                val low=c[i].h;val high=c[i-2].l
                val after=if(i<c.lastIndex)c.subList(i+1,c.size) else emptyList()
                val maxHigh=after.maxOfOrNull{it.h}?:low
                val fill=when{maxHigh>=high->100;maxHigh<=low->0;else->(((maxHigh-low)/(high-low))*100.0).toInt().coerceIn(0,100)}
                return Fvg("BEARISH",low,high,fill)
            }
        }
        return null
    }

    private fun equalLevel(c:List<Candle>,high:Boolean,a:Double):Double?{
        val w=c.takeLast(min(90,c.size));if(w.size<8)return null
        val pts=mutableListOf<Pair<Int,Double>>()
        for(i in 2 until w.size-2){
            val x=w[i]
            val pivot=if(high)x.h>=w[i-1].h&&x.h>=w[i-2].h&&x.h>=w[i+1].h&&x.h>=w[i+2].h else x.l<=w[i-1].l&&x.l<=w[i-2].l&&x.l<=w[i+1].l&&x.l<=w[i+2].l
            if(pivot)pts+=i to if(high)x.h else x.l
        }
        var best:Pair<Int,Double>?=null
        for(i in pts.indices)for(j in i+1 until pts.size){
            if(abs(pts[i].second-pts[j].second)<=a*.14){
                val rec=max(pts[i].first,pts[j].first)
                val avg=(pts[i].second+pts[j].second)/2.0
                if(best==null||rec>best!!.first)best=rec to avg
            }
        }
        return best?.second
    }

    private fun divergence(c:List<Candle>,a:Double):Div{
        val lows=pivots(c,false).takeLast(2);val highs=pivots(c,true).takeLast(2)
        var rb=false;var rs=false;var hb=false;var hs=false
        if(lows.size==2){
            val p1=lows[0];val p2=lows[1];val r1=rsiAt(c,p1.first,14);val r2=rsiAt(c,p2.first,14)
            rb=p2.second<p1.second-a*.04&&r2>r1+3
            hb=p2.second>p1.second+a*.04&&r2<r1-3
        }
        if(highs.size==2){
            val p1=highs[0];val p2=highs[1];val r1=rsiAt(c,p1.first,14);val r2=rsiAt(c,p2.first,14)
            rs=p2.second>p1.second+a*.04&&r2<r1-3
            hs=p2.second<p1.second-a*.04&&r2>r1+3
        }
        return Div(rb,rs,hb,hs)
    }

    private fun pivots(c:List<Candle>,high:Boolean):List<Pair<Int,Double>>{
        val start=max(2,c.size-90);val out=mutableListOf<Pair<Int,Double>>()
        for(i in start until c.size-2){
            val x=c[i]
            val ok=if(high)x.h>=c[i-1].h&&x.h>=c[i-2].h&&x.h>=c[i+1].h&&x.h>=c[i+2].h else x.l<=c[i-1].l&&x.l<=c[i-2].l&&x.l<=c[i+1].l&&x.l<=c[i+2].l
            if(ok)out+=i to if(high)x.h else x.l
        }
        return out
    }

    private fun rsiAt(c:List<Candle>,index:Int,n:Int):Double{
        if(index<=0)return 50.0
        val start=max(1,index-n+1);var gain=0.0;var loss=0.0;var count=0
        for(i in start..index){
            val d=c[i].c-c[i-1].c
            if(d>0)gain+=d else loss-=d
            count++
        }
        if(count==0)return 50.0
        val ag=gain/count;val al=loss/count
        if(al<=1e-9)return 100.0
        val rs=ag/al
        return 100.0-(100.0/(1.0+rs))
    }

    private fun zone(low:Double?,high:Double?)=if(low!=null&&high!=null)Zone(low,high) else null
    private fun distanceToZone(p:Double,z:Zone)=when{p<z.low->z.low-p;p>z.high->p-z.high;else->0.0}
    private fun List<Double>.averageOr(fallback:Double)=if(isEmpty())fallback else average()
    private fun one(v:Double)=String.format(java.util.Locale.US,"%.1f",v)
    private fun two(v:Double)=String.format(java.util.Locale.US,"%.2f",v)
}
