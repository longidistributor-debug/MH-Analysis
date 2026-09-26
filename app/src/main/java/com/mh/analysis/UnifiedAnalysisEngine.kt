package com.mh.analysis

import android.content.Context
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneOffset
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * V.01 manual-analysis coordinator.
 *
 * It combines the existing structure engine, all permanent video-reference
 * techniques, the advanced market map, adaptive decision layer, true provider
 * HTF confirmation, execution-quality filters and bounded local calibration.
 * It never performs network I/O itself; FcsClient supplies one three-call pack.
 */
object UnifiedAnalysisEngine {
    data class Result(
        val signal:Signal?,
        val decision:String,
        val htfSummary:String,
        val executionSummary:String,
        val calibrationSummary:String,
        val blocked:Boolean
    )

    private data class HtfView(val direction:String,val strength:Int,val summary:String)
    private data class Execution(val blocked:Boolean,val penalty:Int,val summary:String)
    private data class Calibration(val adjustment:Int,val summary:String)

    fun analyze(
        context:Context,
        symbol:String,
        timeframe:String,
        current:List<Candle>,
        higher:List<Candle>,
        higherTimeframe:String,
        quote:FcsClient.MarketQuote
    ):Result {
        if(current.size<100)return Result(null,"NO SIGNAL: selected timeframe history is insufficient.","HTF unavailable","Execution not evaluated","Calibration not evaluated",false)
        if(higher.size<60)return Result(null,"NO SIGNAL: true higher-timeframe history is insufficient.","HTF unavailable","Execution not evaluated","Calibration not evaluated",false)

        val base=AnalysisEngine.analyze(symbol,timeframe,current)
        val withVideo=VideoTechniqueEngine.analyzeOrEnhance(symbol,timeframe,current,base)
        val advanced=AdvancedMarketEngine.assess(symbol,timeframe,current,withVideo)
        val adaptive=AdaptiveDecisionEngine.refine(symbol,timeframe,current,advanced)
        val candidate=adaptive.signal

        val htf=htfView(higher,higherTimeframe)
        val execution=execution(symbol,current,quote)
        val calibration=calibration(context,symbol,timeframe,current)

        if(execution.blocked){
            return Result(
                null,
                "EXECUTION BLOCKED: ${execution.summary}",
                htf.summary,
                execution.summary,
                calibration.summary,
                true
            )
        }

        if(candidate==null){
            val detail=listOf(adaptive.decision,htf.summary,execution.summary,calibration.summary).joinToString("\n")
            return Result(null,"NO SIGNAL\n$detail",htf.summary,execution.summary,calibration.summary,false)
        }

        val aligned=htf.direction==candidate.direction
        val opposed=htf.direction!="NEUTRAL"&&!aligned
        val htfDelta=when{
            aligned&&htf.strength>=80->8
            aligned&&htf.strength>=65->5
            aligned->3
            opposed&&htf.strength>=80->-12
            opposed&&htf.strength>=65->-8
            opposed->-4
            else->0
        }
        val raw=candidate.score+htfDelta-execution.penalty+calibration.adjustment
        val finalScore=raw.coerceIn(0,99)
        val strongOpposition=opposed&&htf.strength>=82&&candidate.score<86
        val weakAfterFilters=finalScore<68

        if(strongOpposition||weakAfterFilters){
            val why=if(strongOpposition)"true $higherTimeframe structure/momentum strongly opposes ${candidate.direction}" else "combined post-filter score is only $finalScore/100"
            return Result(
                null,
                "NO SIGNAL: $why.\n${htf.summary}\n${execution.summary}\n${calibration.summary}",
                htf.summary,execution.summary,calibration.summary,false
            )
        }

        val extra=mutableListOf<String>()
        extra+=htf.summary
        extra+=execution.summary
        extra+=calibration.summary
        if(htfDelta!=0)extra+="True HTF score adjustment ${if(htfDelta>0)"+" else ""}$htfDelta"
        if(execution.penalty>0)extra+="Execution-quality score adjustment -${execution.penalty}"
        val reasons=(extra+candidate.reasons).distinct().take(12)
        val final=candidate.copy(
            score=finalScore,
            reasons=reasons,
            setupReason="${candidate.setupReason} True $higherTimeframe provider candles, execution quality and bounded calibration were included in the final decision.",
            validityReason="${candidate.validityReason} True $higherTimeframe confirmation and execution quality must also remain acceptable."
        )
        return Result(
            final,
            "${final.direction} accepted • final evidence ${final.score}/100 • true HTF ${htf.direction} ${htf.strength}/100",
            htf.summary,execution.summary,calibration.summary,false
        )
    }

    private fun htfView(c:List<Candle>,tf:String):HtfView{
        val closes=c.map{it.c};val last=c.last();val e20=ema(closes,20);val e50=ema(closes,50);val r=rsi(closes,14)
        val recent=c.takeLast(min(32,c.size)).dropLast(2)
        val hi=recent.maxOfOrNull{it.h}?:last.h;val lo=recent.minOfOrNull{it.l}?:last.l
        val bullBreak=last.c>hi;val bearBreak=last.c<lo
        val bullTrend=e20>e50&&last.c>e20;val bearTrend=e20<e50&&last.c<e20
        var bull=0;var bear=0
        if(bullTrend)bull+=42;if(bearTrend)bear+=42
        if(r>=55)bull+=22 else if(r<=45)bear+=22
        if(bullBreak)bull+=28;if(bearBreak)bear+=28
        val lastRange=(last.h-last.l).coerceAtLeast(1e-9);val closeLoc=(last.c-last.l)/lastRange
        if(closeLoc>=.68)bull+=10 else if(closeLoc<=.32)bear+=10
        val direction=when{bull-bear>=12->"BUY";bear-bull>=12->"SELL";else->"NEUTRAL"}
        val strength=max(bull,bear).coerceIn(0,100)
        val structure=when{bullBreak->"bullish external break";bearBreak->"bearish external break";else->"no external break"}
        return HtfView(direction,strength,"True $tf confirmation: $direction $strength/100 • RSI ${one(r)} • $structure")
    }

    private fun execution(symbol:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution{
        val a=atr(c,14).coerceAtLeast(1e-9)
        val live=LiveMarketState.quote(symbol)
        val spread=quote.spread?:live?.spread
        val spreadAtr=spread?.div(a)
        val utc=Instant.now().atZone(ZoneOffset.UTC)
        val weekend=utc.dayOfWeek==DayOfWeek.SATURDAY||utc.dayOfWeek==DayOfWeek.SUNDAY
        val fridayClose=utc.dayOfWeek==DayOfWeek.FRIDAY&&utc.hour>=21
        val rollover=utc.hour==21&&utc.minute>=50 || utc.hour==22&&utc.minute<=15
        val gold=symbol.equals("XAUUSD",true)

        if(gold&&weekend)return Execution(true,99,"Gold weekend quality filter blocked execution")
        if(gold&&fridayClose)return Execution(true,99,"Gold Friday-close quality filter blocked execution")
        if(gold&&rollover)return Execution(true,99,"Gold rollover-quality window blocked execution")
        if(spreadAtr!=null&&spreadAtr>.18)return Execution(true,99,"Live spread is abnormal (${two(spreadAtr)} ATR)")

        val penalty=when{
            spreadAtr==null->2
            spreadAtr>.08->6
            else->0
        }
        val session=when(utc.hour){
            in 7..11->"London"
            in 12..16->"London/New York overlap"
            in 17..20->"New York"
            else->"off-peak"
        }
        val spreadText=spreadAtr?.let{"spread ${two(it)} ATR"}?:"bid/ask spread unavailable; live socket fallback not present"
        return Execution(false,penalty,"Execution quality: $session UTC • $spreadText${if(penalty>0)" • caution" else " • acceptable"}")
    }

    /**
     * Controlled calibration only from data the app actually owns:
     * - a small walk-forward check on recent candle history
     * - resolved app lifecycle records (WIN/LOSS)
     * External MT5 outcomes can be added only after a real MT5 result feed exists.
     */
    private fun calibration(context:Context,symbol:String,timeframe:String,c:List<Candle>):Calibration{
        val walk=walkForward(c)
        val records=SignalStore.records(context).filter{it.symbol==symbol&&it.timeframe==timeframe&&it.result in setOf("WIN","LOSS")}.take(40)
        val resolved=records.size
        val wins=records.count{it.result=="WIN"}
        val outcomeAdj=if(resolved>=12){
            val wr=wins.toDouble()/resolved
            when{wr>=.66->2;wr>=.58->1;wr<=.34->-2;wr<=.42->-1;else->0}
        }else 0
        val total=(walk.first+outcomeAdj).coerceIn(-4,4)
        val resultText=if(resolved>=12)"$wins/$resolved local resolved setups won" else "$resolved resolved setups; minimum 12 needed for outcome weighting"
        return Calibration(total,"Adaptive calibration: walk-forward ${signed(walk.first)} (${walk.second}) • outcome ${signed(outcomeAdj)} • $resultText • bounded total ${signed(total)}")
    }

    private fun walkForward(c:List<Candle>):Pair<Int,String>{
        if(c.size<180)return 0 to "history sample too small"
        var wins=0;var losses=0
        val points=listOf(c.size-70,c.size-50,c.size-30).filter{it>=105&&it+12<c.size}
        for(end in points){
            val history=c.take(end)
            val s=AnalysisEngine.analyze("CAL","WF",history)?:continue
            val future=c.subList(end,min(c.size,end+12))
            var entered=false;var resolved=false
            for(x in future){
                if(!entered&&x.l<=s.entry&&x.h>=s.entry)entered=true
                if(!entered)continue
                val sl=if(s.direction=="BUY")x.l<=s.sl else x.h>=s.sl
                val tp=if(s.direction=="BUY")x.h>=s.tp1 else x.l<=s.tp1
                if(sl||tp){if(tp&&!sl)wins++ else losses++;resolved=true;break}
            }
            if(!resolved&&entered){
                val last=future.last().c
                val favorable=if(s.direction=="BUY")last>s.entry else last<s.entry
                if(favorable)wins++ else losses++
            }
        }
        val n=wins+losses
        if(n<2)return 0 to "$n resolved checkpoint(s)"
        val rate=wins.toDouble()/n
        val adj=when{rate>=.75->2;rate>=.60->1;rate<=.25->-2;rate<=.40->-1;else->0}
        return adj to "$wins/$n recent checkpoints favorable"
    }

    private fun ema(v:List<Double>,n:Int):Double{
        if(v.isEmpty())return 0.0;val k=2.0/(n+1.0);var e=v.first();for(i in 1 until v.size)e=v[i]*k+e*(1-k);return e
    }
    private fun rsi(v:List<Double>,n:Int):Double{
        if(v.size<n+1)return 50.0;var gain=0.0;var loss=0.0
        val start=max(1,v.size-n)
        for(i in start until v.size){val d=v[i]-v[i-1];if(d>0)gain+=d else loss-=d}
        if(loss<=1e-12)return 100.0;val rs=gain/loss;return 100.0-(100.0/(1.0+rs))
    }
    private fun atr(c:List<Candle>,n:Int):Double{
        if(c.size<2)return 0.0;val tr=mutableListOf<Double>()
        for(i in 1 until c.size){val p=c[i-1].c;val x=c[i];tr+=max(x.h-x.l,max(abs(x.h-p),abs(x.l-p)))}
        return tr.takeLast(min(n,tr.size)).average()
    }
    private fun one(v:Double)=String.format(java.util.Locale.US,"%.1f",v)
    private fun two(v:Double)=String.format(java.util.Locale.US,"%.2f",v)
    private fun signed(v:Int)=if(v>0)"+$v" else "$v"
}
