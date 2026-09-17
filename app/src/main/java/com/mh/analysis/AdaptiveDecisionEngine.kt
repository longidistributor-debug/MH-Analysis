package com.mh.analysis

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Final same-timeframe decision layer.
 *
 * Existing engines still discover/describe setups. This layer decides whether the
 * discovered setup is strong enough NOW by comparing it with the selected
 * timeframe's own recent distribution. It deliberately avoids fixed pip targets
 * and prevents correlated indicators from being counted as independent votes.
 */
object AdaptiveDecisionEngine {
    private data class Pivot(val index:Int,val price:Double)
    private data class Structure(
        val internalHigh:Double?, val internalLow:Double?,
        val externalHigh:Double?, val externalLow:Double?,
        val breakUp:Boolean, val breakDown:Boolean,
        val sweepLow:Boolean, val sweepHigh:Boolean,
        val description:String
    )
    private data class ZoneLife(val low:Double,val high:Double,val touches:Int,val depth:Double,val state:String)
    private data class Side(
        val direction:String,
        val structure:Int,val liquidity:Int,val location:Int,val momentum:Int,
        val volatility:Int,val candle:Int,val risk:Int,val execution:Int,
        val score:Int
    )
    private data class Profile(
        val regime:String,
        val buy:Side,val sell:Side,
        val requiredScore:Int,val requiredMargin:Int,
        val bodyRank:Int,val rangeRank:Int,val atrRank:Int,val efficiencyRank:Int,
        val breakoutAcceptance:Int,val breakoutRequired:Int,
        val structure:Structure,
        val bullOb:ZoneLife?,val bearOb:ZoneLife?,
        val fvgLife:String
    )

    fun refine(
        symbol:String,
        timeframe:String,
        candles:List<Candle>,
        prior:AdvancedMarketEngine.Assessment
    ):AdvancedMarketEngine.Assessment {
        if(candles.size<80) return prior
        val p=profile(symbol,candles,prior)
        val map=prior.map.copy(regime=p.regime)
        val sig=prior.signal

        if(sig==null){
            val extra=listOf(
                "Adaptive regime ${p.regime}",
                "BUY evidence ${p.buy.score}/100 vs SELL ${p.sell.score}/100",
                "Current body strength is ${p.bodyRank}th percentile of this timeframe",
                "Current ATR is ${p.atrRank}th percentile of this timeframe"
            )
            return prior.copy(
                map=map,
                reasons=(extra+prior.reasons).distinct().take(10),
                decision=prior.decision+" Adaptive engine found no sufficiently dominant directional thesis."
            )
        }

        val chosen=if(sig.direction=="BUY")p.buy else p.sell
        val opposite=if(sig.direction=="BUY")p.sell else p.buy
        val margin=chosen.score-opposite.score
        val isBreakout=sig.reasons.any{
            it.contains("breakout",true)||it.contains("BOS",true)||it.contains("displacement",true)
        }
        val alignedOb=if(sig.direction=="BUY")p.bullOb else p.bearOb
        val oppositeExternalBreak=if(sig.direction=="BUY")p.structure.breakDown else p.structure.breakUp
        val alignedExternalBreak=if(sig.direction=="BUY")p.structure.breakUp else p.structure.breakDown

        val adaptiveReasons=mutableListOf<String>()
        val adaptiveWarnings=mutableListOf<String>()
        adaptiveReasons += "Adaptive ${timeframe} evidence ${sig.direction} ${chosen.score}/100 vs opposite ${opposite.score}/100"
        adaptiveReasons += "Independent-family scores: structure ${chosen.structure}, liquidity ${chosen.liquidity}, location ${chosen.location}, momentum ${chosen.momentum}, candle ${chosen.candle}, volatility ${chosen.volatility}, risk ${chosen.risk}"
        adaptiveReasons += "Directional margin $margin points; current market requires ${p.requiredMargin}"
        adaptiveReasons += "${p.structure.description}"
        adaptiveReasons += "Candle body ${p.bodyRank}th percentile • range ${p.rangeRank}th percentile • ATR ${p.atrRank}th percentile"
        alignedOb?.let{adaptiveReasons += "Aligned order block lifecycle: ${it.state} • ${it.touches} interaction(s)"}
        if(prior.map.fvgType!=null) adaptiveReasons += "${prior.map.fvgType} FVG lifecycle: ${p.fvgLife}"
        if(isBreakout) adaptiveReasons += "Breakout acceptance ${p.breakoutAcceptance}/100; adaptive requirement ${p.breakoutRequired}"

        if(margin<p.requiredMargin) adaptiveWarnings += "BUY/SELL evidence is too close; directional conflict is unresolved"
        if(chosen.score<p.requiredScore) adaptiveWarnings += "Adaptive confluence ${chosen.score}/100 is below the current market requirement ${p.requiredScore}"
        if(isBreakout&&p.breakoutAcceptance<p.breakoutRequired) adaptiveWarnings += "Breakout has not earned enough acceptance relative to recent ${timeframe} candles"
        if(oppositeExternalBreak) adaptiveWarnings += "External structure has broken against the proposed ${sig.direction} thesis"
        if(alignedOb?.state=="INVALIDATED"&&sig.reasons.any{it.contains("order",true)||it.contains("OB",true)}) adaptiveWarnings += "The order-block context used by the setup is already invalidated"
        if(prior.map.severeSpread) adaptiveWarnings += "Live spread is abnormally wide"

        val rejected = adaptiveWarnings.isNotEmpty() && (
            margin<p.requiredMargin ||
            chosen.score<p.requiredScore ||
            (isBreakout&&p.breakoutAcceptance<p.breakoutRequired) ||
            oppositeExternalBreak ||
            prior.map.severeSpread
        )

        if(rejected){
            return AdvancedMarketEngine.Assessment(
                signal=null,
                map=map,
                quality=chosen.score,
                grade=AdvancedMarketEngine.grade(chosen.score),
                decision="NO TRADE: adaptive same-timeframe evidence is not dominant enough for a clean ${sig.direction} signal.",
                reasons=adaptiveReasons.distinct().take(10),
                warnings=(adaptiveWarnings+prior.warnings).distinct().take(10)
            )
        }

        val topReasons=(adaptiveReasons+prior.reasons+sig.reasons).distinct().take(12)
        val setupSummary=topReasons.take(4).joinToString("; ")
        val enhanced=sig.copy(
            score=chosen.score.coerceIn(0,99),
            bullScore=p.buy.score,
            bearScore=p.sell.score,
            reasons=topReasons,
            setupReason="${sig.direction} accepted because $setupSummary.",
            validityReason="Valid while ${timeframe} adaptive evidence remains dominant, external structure is not broken against the thesis, and the directional margin stays above the live conflict requirement."
        )
        val decision=buildString{
            append("${sig.direction} accepted by adaptive same-timeframe decision engine")
            append(" • evidence ${chosen.score}/100")
            append(" • opposite ${opposite.score}/100")
            append(" • margin $margin/${p.requiredMargin}")
            if(alignedExternalBreak) append(" • external structure aligned")
        }
        return AdvancedMarketEngine.Assessment(
            signal=enhanced,
            map=map,
            quality=enhanced.score,
            grade=AdvancedMarketEngine.grade(enhanced.score),
            decision=decision,
            reasons=adaptiveReasons.distinct().take(10),
            warnings=(adaptiveWarnings+prior.warnings).distinct().take(10)
        )
    }

    fun refineReEvaluation(
        active:ActiveSignal,
        candles:List<Candle>,
        base:AdvancedMarketEngine.ReEvaluation,
        currentAssessment:AdvancedMarketEngine.Assessment
    ):AdvancedMarketEngine.ReEvaluation {
        if(candles.size<80) return base
        if(base.state in setOf("INVALID","TARGET REACHED","STOPPED","EXPIRED")) return base
        val p=profile(active.signal.symbol,candles,currentAssessment)
        val chosen=if(active.signal.direction=="BUY")p.buy else p.sell
        val opposite=if(active.signal.direction=="BUY")p.sell else p.buy
        val margin=chosen.score-opposite.score
        val oppositeBreak=if(active.signal.direction=="BUY")p.structure.breakDown else p.structure.breakUp
        val reasons=(base.reasons+listOf(
            "Adaptive re-check: ${active.signal.direction} ${chosen.score}/100 vs opposite ${opposite.score}/100",
            "Directional margin $margin; current requirement ${p.requiredMargin}",
            p.structure.description,
            "ATR ${p.atrRank}th percentile • candle body ${p.bodyRank}th percentile"
        )).distinct()

        if(oppositeBreak){
            return base.copy(state="INVALID",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"External structure broke against the original signal.").distinct())
        }
        if(chosen.score < p.requiredScore-8 || margin < max(2,p.requiredMargin/2)){
            return base.copy(state="INVALID",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Original confluence has degraded below the adaptive continuation boundary.").distinct())
        }
        if(chosen.score < p.requiredScore || margin < p.requiredMargin){
            return base.copy(state="WEAKENING",score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Signal is still structurally alive, but directional dominance has weakened.").distinct())
        }
        if(base.state=="STILL VALID"){
            return base.copy(score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=(reasons+"Adaptive same-timeframe evidence remains dominant.").distinct())
        }
        return base.copy(score=chosen.score,grade=AdvancedMarketEngine.grade(chosen.score),reasons=reasons)
    }

    private fun profile(symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment):Profile{
        val w=c.takeLast(min(220,c.size))
        val last=w.last()
        val ranges=w.map{(it.h-it.l).coerceAtLeast(1e-9)}
        val bodies=w.map{abs(it.c-it.o)}
        val bodyRatios=w.mapIndexed{i,x->bodies[i]/ranges[i]}
        val bodyRank=rank(bodyRatios,bodyRatios.last())
        val rangeRank=rank(ranges,ranges.last())

        val atrSeries=rollingAtr(w,14)
        val atrNow=(atrSeries.lastOrNull()?:prior.map.atr).coerceAtLeast(1e-9)
        val atrRank=rank(atrSeries,atrNow)

        val erLook=max(18,min(48,w.size/5))
        val erSeries=rollingEfficiency(w,erLook)
        val erNow=erSeries.lastOrNull()?:0.0
        val efficiencyRank=rank(erSeries,erNow)

        val internalSpan=max(2,min(4,w.size/90))
        val externalSpan=max(4,min(8,w.size/45))
        val structure=structure(w,internalSpan,externalSpan,atrNow)

        val closeLocation=((last.c-last.l)/ranges.last()).coerceIn(0.0,1.0)
        val breakLevelUp=structure.externalHigh?:structure.internalHigh
        val breakLevelDown=structure.externalLow?:structure.internalLow
        val breakDistUp=breakLevelUp?.let{max(0.0,last.c-it)/atrNow}?:0.0
        val breakDistDown=breakLevelDown?.let{max(0.0,it-last.c)/atrNow}?:0.0
        val breakDist=max(breakDistUp,breakDistDown)
        val distanceScore=(100.0*breakDist/(1.0+breakDist)).roundToInt()
        val directionalClose=if(structure.breakUp)(closeLocation*100).roundToInt() else if(structure.breakDown)((1.0-closeLocation)*100).roundToInt() else 50
        val breakoutAcceptance=(distanceScore*.34 + bodyRank*.30 + rangeRank*.18 + directionalClose*.18).roundToInt().coerceIn(0,100)
        val breakoutRequired=(52 + (100-efficiencyRank)*0.10 + abs(atrRank-62)*0.07).roundToInt().coerceIn(52,72)

        val reversal=(structure.sweepLow&&last.c>last.o)||(structure.sweepHigh&&last.c<last.o)
        val regime=when{
            (structure.breakUp||structure.breakDown)&&breakoutAcceptance>=breakoutRequired->"BREAKOUT"
            reversal->"REVERSAL"
            atrRank>=90->"HIGH_VOLATILITY"
            atrRank<=12->"LOW_VOLATILITY"
            efficiencyRank>=67->"TRENDING"
            else->"RANGING"
        }

        val normBodies=w.mapIndexed{i,_->bodies[i]/atrNow}
        val displacementCut=percentile(normBodies,0.70)
        val bullOb=orderBlockLife(w,true,atrNow,displacementCut)
        val bearOb=orderBlockLife(w,false,atrNow,displacementCut)
        val fvgLife=when{
            prior.map.fvgType==null->"NONE"
            prior.map.fvgFillPct>=100->"FILLED"
            prior.map.fvgFillPct>=75->"DEEP MITIGATION"
            prior.map.fvgFillPct>=35->"PARTIAL MITIGATION"
            else->"FRESH / LIGHTLY MITIGATED"
        }

        val buy=side("BUY",symbol,w,prior,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)
        val sell=side("SELL",symbol,w,prior,regime,structure,bullOb,bearOb,bodyRank,rangeRank,atrRank,efficiencyRank)

        val noise=(100-efficiencyRank).coerceIn(0,100)
        val volatilityUncertainty=abs(atrRank-58)
        val regimePenalty=when(regime){"RANGING"->6;"HIGH_VOLATILITY"->5;"LOW_VOLATILITY"->3;else->0}
        val spreadPenalty=if(prior.map.spreadWarning)4 else 0
        val requiredScore=(58 + noise*.08 + volatilityUncertainty*.05 + regimePenalty + spreadPenalty).roundToInt().coerceIn(60,79)
        val requiredMargin=(7 + noise*.07 + volatilityUncertainty*.035 + if(regime=="RANGING")4 else 0).roundToInt().coerceIn(8,22)

        return Profile(regime,buy,sell,requiredScore,requiredMargin,bodyRank,rangeRank,atrRank,efficiencyRank,breakoutAcceptance,breakoutRequired,structure,bullOb,bearOb,fvgLife)
    }

    private fun side(
        direction:String,symbol:String,c:List<Candle>,prior:AdvancedMarketEngine.Assessment,regime:String,
        st:Structure,bullOb:ZoneLife?,bearOb:ZoneLife?,bodyRank:Int,rangeRank:Int,atrRank:Int,effRank:Int
    ):Side{
        val buy=direction=="BUY"
        val last=c.last();val map=prior.map
        val range=(last.h-last.l).coerceAtLeast(1e-9)
        val closeLoc=((last.c-last.l)/range).coerceIn(0.0,1.0)

        var structure=38
        if(if(buy)st.breakUp else st.breakDown)structure=96
        else if(if(buy)(st.internalHigh?.let{last.c>it}==true) else (st.internalLow?.let{last.c<it}==true))structure=78
        else {
            val hi=st.externalHigh;val lo=st.externalLow
            if(hi!=null&&lo!=null&&hi>lo){
                val pos=((last.c-lo)/(hi-lo)).coerceIn(0.0,1.0)
                structure=(if(buy)42+pos*32 else 74-pos*32).roundToInt()
            }
        }
        if(if(buy)st.breakDown else st.breakUp)structure=min(structure,18)

        var liquidity=42
        val eq=if(buy)map.equalLow else map.equalHigh
        if(eq!=null){
            val swept=if(buy)last.l<eq&&last.c>eq else last.h>eq&&last.c<eq
            if(swept)liquidity=96
        }
        if(if(buy)st.sweepLow else st.sweepHigh)liquidity=max(liquidity,88)
        val objective=if(buy)map.equalHigh else map.equalLow
        if(objective!=null&&if(buy)objective>last.c else objective<last.c)liquidity=max(liquidity,62)

        val alignedOb=if(buy)bullOb else bearOb
        var location=50
        map.vwap?.let{vw->
            val aligned=if(buy)last.c>=vw else last.c<=vw
            val dist=(abs(last.c-vw)/map.atr.coerceAtLeast(1e-9))
            val closeness=(100.0/(1.0+dist)).roundToInt()
            location=if(aligned)max(location,55+closeness/3) else min(location,45-closeness/5)
        }
        alignedOb?.let{z->
            val d=distanceToZone(last.c,z.low,z.high)/map.atr.coerceAtLeast(1e-9)
            val near=(100.0/(1.0+d*2.0)).roundToInt()
            val life=when(z.state){"FRESH"->100;"TESTED"->82;"MITIGATED"->60;"WEAKENED"->38;else->10}
            location=max(location,(near*.55+life*.45).roundToInt())
        }
        if(regime=="RANGING"||regime=="REVERSAL"){
            val hi=st.externalHigh;val lo=st.externalLow
            if(hi!=null&&lo!=null&&hi>lo){
                val pos=((last.c-lo)/(hi-lo)).coerceIn(0.0,1.0)
                val preferred=if(buy)(1.0-pos) else pos
                location=max(location,(preferred*100).roundToInt())
            }
        }

        val den=(map.plusDi+map.minusDi).coerceAtLeast(1e-9)
        val dmi=if(buy)map.plusDi/den else map.minusDi/den
        val seq=c.takeLast(min(9,c.size)).zipWithNext().count{(a,b)->if(buy)b.c>a.c else b.c<a.c}
        val seqScore=(seq.toDouble()/max(1,min(8,c.size-1))*100).roundToInt().coerceIn(0,100)
        val momentum=(dmi*62.0+seqScore*.38).roundToInt().coerceIn(0,100)

        val targetAtr=if(regime=="BREAKOUT")78 else 56
        val volatility=(100-abs(atrRank-targetAtr)*1.20).roundToInt().coerceIn(0,100)

        val directionalBody=if(buy)last.c>=last.o else last.c<=last.o
        val wickSupport=if(buy)(min(last.o,last.c)-last.l)/range else (last.h-max(last.o,last.c))/range
        val closeScore=if(buy)(closeLoc*100).roundToInt() else ((1.0-closeLoc)*100).roundToInt()
        val candle=(if(directionalBody)bodyRank*.55+closeScore*.30+(wickSupport*100)*.15 else (100-bodyRank)*.30+closeScore*.45+(wickSupport*100)*.25).roundToInt().coerceIn(0,100)

        val sig=prior.signal
        val risk=if(sig!=null){
            val r=abs(sig.entry-sig.sl).coerceAtLeast(1e-9)
            val rr=abs(sig.tp1-sig.entry)/r
            (100.0*rr/(1.0+rr)).roundToInt().coerceIn(0,100)
        }else 50

        val execution=map.spreadAtr?.let{sp->(100.0/(1.0+sp*8.0)).roundToInt().coerceIn(0,100)}?:70

        val families=listOf(structure,liquidity,location,momentum,volatility,candle,risk,execution).sorted()
        val trimmed=if(families.size>4)families.drop(1).dropLast(1).average() else families.average()
        val median=median(families.map{it.toDouble()})
        val breadth=families.count{it>=60}.toDouble()/families.size*100.0
        val score=(trimmed*.60+median*.25+breadth*.15).roundToInt().coerceIn(0,99)
        return Side(direction,structure,liquidity,location,momentum,volatility,candle,risk,execution,score)
    }

    private fun structure(c:List<Candle>,internalSpan:Int,externalSpan:Int,atr:Double):Structure{
        val ih=pivots(c,true,internalSpan).lastOrNull()
        val il=pivots(c,false,internalSpan).lastOrNull()
        val eh=pivots(c,true,externalSpan).lastOrNull()
        val el=pivots(c,false,externalSpan).lastOrNull()
        val last=c.last()
        val breakUp=eh?.let{last.c>it.price}==true
        val breakDown=el?.let{last.c<it.price}==true
        val sweepTol=percentile(c.takeLast(min(120,c.size)).map{it.h-it.l},0.35).coerceAtLeast(atr*.05)
        val sweepLow=(el?.let{last.l<it.price-sweepTol&&last.c>it.price}==true)||(il?.let{last.l<it.price-sweepTol&&last.c>it.price}==true)
        val sweepHigh=(eh?.let{last.h>it.price+sweepTol&&last.c<it.price}==true)||(ih?.let{last.h>it.price+sweepTol&&last.c<it.price}==true)
        val desc=when{
            breakUp->"External structure accepted above the latest protected high"
            breakDown->"External structure accepted below the latest protected low"
            sweepLow->"Sell-side structure liquidity swept and reclaimed"
            sweepHigh->"Buy-side structure liquidity swept and rejected"
            ih!=null&&il!=null->"Internal structure remains between ${fmt(il.price)} and ${fmt(ih.price)}"
            else->"Structure is still building"
        }
        return Structure(ih?.price,il?.price,eh?.price,el?.price,breakUp,breakDown,sweepLow,sweepHigh,desc)
    }

    private fun pivots(c:List<Candle>,high:Boolean,span:Int):List<Pivot>{
        if(c.size<span*2+3)return emptyList()
        val out=mutableListOf<Pivot>()
        for(i in span until c.size-span){
            val p=if(high)c[i].h else c[i].l
            var ok=true
            for(j in i-span..i+span){
                if(j==i)continue
                val q=if(high)c[j].h else c[j].l
                if(if(high)q>p else q<p){ok=false;break}
            }
            if(ok)out+=Pivot(i,p)
        }
        return out
    }

    private fun orderBlockLife(c:List<Candle>,bull:Boolean,atr:Double,displacementCut:Double):ZoneLife?{
        if(c.size<12)return null
        val start=max(2,c.size-70)
        for(i in c.size-5 downTo start){
            val x=c[i]
            val opposite=if(bull)x.c<x.o else x.c>x.o
            if(!opposite)continue
            val after=c.subList(i+1,min(c.size,i+4))
            val displaced=after.any{y->
                val norm=abs(y.c-y.o)/atr.coerceAtLeast(1e-9)
                norm>=displacementCut && if(bull)y.c>x.h else y.c<x.l
            }
            if(!displaced)continue
            val low=if(bull)x.l else min(x.o,x.c)
            val high=if(bull)max(x.o,x.c) else x.h
            val width=(high-low).coerceAtLeast(1e-9)
            var touches=0;var deepest=0.0;var invalid=false
            for(j in i+2 until c.size){
                val y=c[j]
                val overlap=y.h>=low&&y.l<=high
                if(overlap){
                    touches++
                    val depth=if(bull)(high-y.l)/width else (y.h-low)/width
                    deepest=max(deepest,depth.coerceIn(0.0,1.5))
                }
                if(if(bull)y.c<low else y.c>high){invalid=true;break}
            }
            val state=when{
                invalid->"INVALIDATED"
                touches==0->"FRESH"
                deepest<.45->"TESTED"
                deepest<.85->"MITIGATED"
                else->"WEAKENED"
            }
            return ZoneLife(low,high,touches,deepest,state)
        }
        return null
    }

    private fun rollingAtr(c:List<Candle>,n:Int):List<Double>{
        if(c.size<n+2)return emptyList()
        val out=mutableListOf<Double>()
        for(end in n until c.size){
            var sum=0.0
            for(i in end-n+1..end){
                val x=c[i];val p=c[i-1]
                sum+=max(x.h-x.l,max(abs(x.h-p.c),abs(x.l-p.c)))
            }
            out+=sum/n
        }
        return out
    }

    private fun rollingEfficiency(c:List<Candle>,n:Int):List<Double>{
        if(c.size<n+2)return emptyList()
        val out=mutableListOf<Double>()
        for(end in n until c.size){
            val start=end-n
            val net=abs(c[end].c-c[start].c)
            var path=0.0
            for(i in start+1..end)path+=abs(c[i].c-c[i-1].c)
            out+=if(path<=1e-9)0.0 else net/path
        }
        return out
    }

    private fun distanceToZone(p:Double,lo:Double,hi:Double)=when{p<lo->lo-p;p>hi->p-hi;else->0.0}
    private fun rank(values:List<Double>,x:Double):Int{
        val clean=values.filter{it.isFinite()}
        if(clean.isEmpty())return 50
        return (clean.count{it<=x}.toDouble()/clean.size*100.0).roundToInt().coerceIn(0,100)
    }
    private fun percentile(values:List<Double>,p:Double):Double{
        val s=values.filter{it.isFinite()}.sorted();if(s.isEmpty())return 0.0
        val pos=(p.coerceIn(0.0,1.0)*(s.size-1));val lo=pos.toInt();val hi=min(s.lastIndex,lo+1);val f=pos-lo
        return s[lo]*(1.0-f)+s[hi]*f
    }
    private fun median(v:List<Double>)=percentile(v,.5)
    private fun fmt(v:Double)=if(abs(v)>=100)String.format(java.util.Locale.US,"%.2f",v) else String.format(java.util.Locale.US,"%.5f",v)
}
