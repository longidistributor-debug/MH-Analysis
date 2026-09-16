from pathlib import Path
import re

# v42: every supported FCS timeframe + true selected-timeframe analysis + chart structure guides.
# Keeps v39 manual ANALYZE / RE-EVALUATE flow, v40 video techniques and v41 volatility engine.

# -----------------------------------------------------------------------------
# FCS history periods
# Native FCS: 1m,5m,15m,30m,1h,2h,4h,5h,1d,1w,1M
# 10m remains a custom OHLC aggregation of native 5m candles.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
s=re.sub(r'private val periods=listOf\([^\n]+\)', 'private val periods=listOf("1m","5m","10m","15m","30m","1h","2h","4h","5h","1d","1w","1M")', s, count=1)

start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        if(current.size>=100&&!force)return current.takeLast(220) to 0
        if(!canRequestNow()){
            if(current.isNotEmpty()&&!force)return current.takeLast(220) to 0
            throw IllegalStateException("Fresh timeframe request limit reached. Wait briefly and analyze again; stale candles were not presented as fresh data.")
        }
        var credits=0
        fun fetchSeed(sourceTf:String,length:Int):List<Candle>{
            val out=try{fetchMarket(sym,accessKey,sourceTf,length)}catch(e:Exception){noteRequest();throw e}
            noteRequest();credits+=out.second
            return out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
        }
        when(tf){
            "10m"->{
                val five=fetchSeed("5m",360)
                putCache(sym,"5m",five,true)
                putCache(sym,"10m",aggregate(five,10),true)
            }
            "1m","5m","15m","30m","1h","2h","4h","5h","1d","1w","1M"->{
                val exact=fetchSeed(tf,300)
                putCache(sym,tf,exact,true)
            }
            else->throw IllegalStateException("Unsupported timeframe $tf")
        }
        val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)
        if(result.size<100)throw IllegalStateException("$sym $tf does not yet have enough selected-timeframe candles for reliable analysis")
        return result to credits
    }'''
s=s[:start]+new_seed+s[end:]

start=s.index('    private fun normalizePeriod(p:String)=')
end=s.index('\n    private fun cacheKey',start)
new_norm='''    private fun normalizePeriod(p:String):String{
        val raw=p.trim()
        if(raw=="1M"||raw.equals("month",true)||raw.equals("monthly",true))return "1M"
        return when(raw.lowercase()){
            "1","1m"->"1m";"5","5m"->"5m";"10","10m"->"10m";"15","15m"->"15m";"30","30m"->"30m"
            "60","1h"->"1h";"120","2h"->"2h";"240","4h"->"4h";"300","5h"->"5h"
            "1440","1d","d","day"->"1d";"10080","1w","w","week"->"1w";else->raw
        }
    }'''
s=s[:start]+new_norm+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Analysis engine: timeframe-specific horizons, same-candle invalidation,
# validated order blocks and public chart levels.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

if 'data class ChartLevels' not in s:
    s=s.replace('    data class SetupCheck(val valid:Boolean,val reason:String)\n',
'''    data class SetupCheck(val valid:Boolean,val reason:String)
    data class ChartLevels(
        val support:Double,val resistance:Double,
        val bullObLow:Double?=null,val bullObHigh:Double?=null,
        val bearObLow:Double?=null,val bearObHigh:Double?=null
    )
''',1)

# True timeframe minutes, preserving 1M != 1m.
start=s.index('    private fun tfMinutes(tf:String)=')
end=s.index('\n    private fun one(',start)
new_tf='''    private fun tfMinutes(tf:String):Int{
        val raw=tf.trim();if(raw=="1M")return 43200
        return when(raw.lowercase(Locale.US)){
            "1m"->1;"5m"->5;"10m"->10;"15m"->15;"30m"->30;"1h"->60;"2h"->120;"4h"->240;"5h"->300;"1d"->1440;"1w"->10080;else->60
        }
    }'''
s=s[:start]+new_tf+s[end:]

# More appropriate bar horizons per selected timeframe.
s=s.replace('''        val recentN=when{tfProfile<=1->90;tfProfile<=5->72;tfProfile<=10->66;tfProfile<=15->60;tfProfile<=30->54;else->48}
        val localN=when{tfProfile<=1->24;tfProfile<=5->22;tfProfile<=10->20;tfProfile<=15->18;tfProfile<=30->16;else->15}
        val priorN=when{tfProfile<=1->52;tfProfile<=5->48;tfProfile<=10->45;tfProfile<=15->42;tfProfile<=30->38;else->34}
        val shortN=when{tfProfile<=1->20;tfProfile<=5->18;tfProfile<=10->17;tfProfile<=15->16;tfProfile<=30->15;else->14}
''','''        val recentN=when{tfProfile<=1->90;tfProfile<=5->72;tfProfile<=10->66;tfProfile<=15->60;tfProfile<=30->54;tfProfile<=60->48;tfProfile<=120->44;tfProfile<=240->40;tfProfile<=300->38;tfProfile<=1440->34;tfProfile<=10080->30;else->26}
        val localN=when{tfProfile<=1->24;tfProfile<=5->22;tfProfile<=10->20;tfProfile<=15->18;tfProfile<=30->16;tfProfile<=60->15;tfProfile<=120->14;tfProfile<=300->13;tfProfile<=1440->12;else->11}
        val priorN=when{tfProfile<=1->52;tfProfile<=5->48;tfProfile<=10->45;tfProfile<=15->42;tfProfile<=30->38;tfProfile<=60->34;tfProfile<=120->32;tfProfile<=300->30;tfProfile<=1440->28;tfProfile<=10080->26;else->24}
        val shortN=when{tfProfile<=1->20;tfProfile<=5->18;tfProfile<=10->17;tfProfile<=15->16;tfProfile<=30->15;tfProfile<=60->14;tfProfile<=300->13;else->12}
''',1)

s=s.replace('''        val sequenceN=when{tfProfile<=1->42;tfProfile<=5->38;tfProfile<=10->36;tfProfile<=15->34;tfProfile<=30->30;else->28}
        val sequenceLeg=when{tfProfile<=5->10;tfProfile<=15->9;else->8}
''','''        val sequenceN=when{tfProfile<=1->42;tfProfile<=5->38;tfProfile<=10->36;tfProfile<=15->34;tfProfile<=30->30;tfProfile<=60->28;tfProfile<=120->26;tfProfile<=300->24;else->22}
        val sequenceLeg=when{tfProfile<=5->10;tfProfile<=15->9;tfProfile<=60->8;else->7}
''',1)

s=s.replace('''        val minDirectionalScore=(when{tfm<=1->48;tfm<=5->46;tfm<=10->45;tfm<=15->44;tfm<=30->43;else->42})+(if(highVol)8 else 0)
        val minSeparation=(when{tfm<=1->10;tfm<=5->9;tfm<=10->9;tfm<=15->8;tfm<=30->8;else->7})+(if(highVol)4 else 0)
''','''        val minDirectionalScore=(when{tfm<=1->48;tfm<=5->46;tfm<=10->45;tfm<=15->44;tfm<=30->43;tfm<=60->42;tfm<=120->41;tfm<=300->40;tfm<=1440->39;else->38})+(if(highVol)8 else 0)
        val minSeparation=(when{tfm<=1->10;tfm<=5->9;tfm<=10->9;tfm<=15->8;tfm<=30->8;tfm<=60->7;tfm<=120->7;tfm<=300->6;tfm<=1440->6;else->5})+(if(highVol)4 else 0)
''',1)

# Timeframe-specific structural risk/targets.
s=s.replace('''        val tf=tfMinutes(timeframe);val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=15->1.08;tf<=30->1.22;else->1.38};''',
'''        val tf=tfMinutes(timeframe);val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=10->1.02;tf<=15->1.08;tf<=30->1.22;tf<=60->1.38;tf<=120->1.42;tf<=300->1.50;tf<=1440->1.60;tf<=10080->1.70;else->1.80};''',1)
s=s.replace('''val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=15->1.05;tf<=30->1.18;else->1.35};val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=15->1.50;tf<=30->1.70;else->1.95};''',
'''val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=10->.98;tf<=15->1.05;tf<=30->1.18;tf<=60->1.35;tf<=120->1.45;tf<=300->1.55;tf<=1440->1.70;tf<=10080->1.85;else->2.00};val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=10->1.38;tf<=15->1.50;tf<=30->1.70;tf<=60->1.95;tf<=120->2.10;tf<=300->2.30;tf<=1440->2.50;tf<=10080->2.75;else->3.00};''',1)

# Use validated order blocks instead of simply taking the last opposite-colored candle.
s=s.replace('''        val bullOb=c.takeLast(14).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(14).dropLast(1).lastOrNull{it.c>it.o};val bullObMid=bullOb?.let{(it.o+it.c)/2};val bearObMid=bearOb?.let{(it.o+it.c)/2}
''','''        val bullOb=validatedOrderBlock(c,"BUY",a);val bearOb=validatedOrderBlock(c,"SELL",a);val bullObMid=bullOb?.let{(it.o+it.c)/2};val bearObMid=bearOb?.let{(it.o+it.c)/2}
''',1)
s=s.replace('''        val bullOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c>it.o};val obText="Bull OB ${bullOb?.let{fmt((it.o+it.c)/2)}?:"-"} • Bear OB ${bearOb?.let{fmt((it.o+it.c)/2)}?:"-"}"
''','''        val bullOb=validatedOrderBlock(c,"BUY",a);val bearOb=validatedOrderBlock(c,"SELL",a);val obText="Bull OB ${bullOb?.let{"${fmt(min(it.o,it.c))}–${fmt(max(it.o,it.c))}"}?:"-"} • Bear OB ${bearOb?.let{"${fmt(min(it.o,it.c))}–${fmt(max(it.o,it.c))}"}?:"-"}"
''',1)

# Replace setupCheck completely: no time/candle-count expiry; current candle can invalidate immediately.
start=s.index('    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{')
try:
    end=s.index('\n    /** Manual re-evaluation',start)
except ValueError:
    end=s.index('\n    fun reEvaluateSignal',start)
new_check='''    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<60)return SetupCheck(true,"Waiting for enough fresh selected-timeframe data; time alone never invalidates the signal.")
        val last=c.last();val prev=c[c.lastIndex-1];val close=c.map{it.c};val tf=tfMinutes(s.timeframe)
        val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val a=atr(c,14).coerceAtLeast(1e-9);val highVol=highVolForTimeframe(c,s.timeframe)
        val bars=when{tf<=1->22;tf<=5->20;tf<=10->19;tf<=15->18;tf<=30->17;tf<=60->16;tf<=120->15;tf<=300->14;else->13}
        val prior=c.takeLast((bars+2).coerceAtMost(c.size)).dropLast(1);val hi=prior.maxOf{it.h};val lo=prior.minOf{it.l}
        val srLook=when{tf<=1->80;tf<=5->72;tf<=10->64;tf<=15->58;tf<=30->50;tf<=60->46;tf<=120->42;tf<=300->38;tf<=1440->34;else->30}
        val majors=directionalMajorLevels(c,a,srLook);val support=majors.first;val resistance=majors.second
        val candleRange=(last.h-last.l).coerceAtLeast(1e-9);val body=abs(last.c-last.o);val oppBody=body/candleRange>=.55
        var opposite=0;val why=mutableListOf<String>()
        if(s.direction=="BUY"){
            if(last.l<=s.sl)return SetupCheck(false,"BUY expired immediately: the current ${s.timeframe} candle traded through structural SL ${fmt(s.sl)} (low ${fmt(last.l)}).")
            if(e20<e50){opposite++;why+="EMA20 fell below EMA50"};if(rr<43){opposite++;why+="RSI weakened to ${one(rr)}"};if(macd<0&&macd<macdPrev){opposite++;why+="MACD is negative and falling"}
            if(last.c<lo-a*.04){opposite+=2;why+="close broke selected-timeframe structure below ${fmt(lo)}"}
            if(last.l<support-a*.18){opposite+=2;why+="current candle swept deeply below major support ${fmt(support)} without a valid reclaim yet"}
            if(last.c<support-a*.10){opposite+=2;why+="major support ${fmt(support)} failed on current price"}
            if(last.c<last.o&&oppBody&&(last.o-last.c)>a*.65){opposite+=2;why+="strong bearish displacement formed inside the current candle"}
        }else{
            if(last.h>=s.sl)return SetupCheck(false,"SELL expired immediately: the current ${s.timeframe} candle traded through structural SL ${fmt(s.sl)} (high ${fmt(last.h)}).")
            if(e20>e50){opposite++;why+="EMA20 rose above EMA50"};if(rr>57){opposite++;why+="RSI strengthened to ${one(rr)}"};if(macd>0&&macd>macdPrev){opposite++;why+="MACD is positive and rising"}
            if(last.c>hi+a*.04){opposite+=2;why+="close broke selected-timeframe structure above ${fmt(hi)}"}
            if(last.h>resistance+a*.18){opposite+=2;why+="current candle swept deeply above major resistance ${fmt(resistance)} without a valid rejection yet"}
            if(last.c>resistance+a*.10){opposite+=2;why+="major resistance ${fmt(resistance)} failed on current price"}
            if(last.c>last.o&&oppBody&&(last.c-last.o)>a*.65){opposite+=2;why+="strong bullish displacement formed inside the current candle"}
        }
        val ir=impulseRetracement(c,s.direction,a);if(ir?.reversalRisk==true){opposite+=2;why+="${pct(ir.retracementRatio)} aggressive counter-retracement damaged the original impulse"}
        val threshold=if(highVol)6 else when{tf<=15->4;tf<=60->5;else->5}
        if(opposite>=threshold)return SetupCheck(false,"Original ${s.direction} signal is EXPIRED on fresh ${s.timeframe} data: ${why.joinToString("; ")}.")
        val regime=if(highVol)"HIGH VOLATILITY — stricter confirmation active" else "normal volatility"
        return SetupCheck(true,"Original ${s.direction} thesis remains valid on fresh ${s.timeframe} candles • $regime • current O/H/L/C ${fmt(last.o)}/${fmt(last.h)}/${fmt(last.l)}/${fmt(last.c)} • EMA20 ${fmt(e20)} / EMA50 ${fmt(e50)} • RSI ${one(rr)} • major S/R ${fmt(support)} / ${fmt(resistance)}${ir?.let{" • retracement ${pct(it.retracementRatio)}, speed ${two(it.speedRatio)}x"}.orEmpty()}.")
    }'''
s=s[:start]+new_check+s[end:]

# Re-evaluation reasons are always based on fresh selected-timeframe evidence.
start=s.index('    fun reEvaluateSignal(original:Signal,c:List<Candle>):ReEvaluation{')
end=s.index('\n    fun isHighVolatility',start)
new_re='''    fun reEvaluateSignal(original:Signal,c:List<Candle>):ReEvaluation{
        if(c.size<100)return ReEvaluation("WEAKENING","Not enough fresh ${original.timeframe} candles to verify the original setup. It is not expired by elapsed time or candle count.")
        val check=setupCheck(original,c)
        if(!check.valid)return ReEvaluation("EXPIRED",check.reason)
        val fresh=analyze(original.symbol,original.timeframe,c)
        if(fresh==null){
            return ReEvaluation("WEAKENING","The original structure has not fully failed, but the complete current ${original.timeframe} engine no longer has enough confluence to confirm a fresh entry. ${check.reason}")
        }
        val dominance=abs(fresh.bullScore-fresh.bearScore)
        if(fresh.direction!=original.direction){
            val strongFlip=fresh.score>=maxOf(72,original.score-2)&&dominance>=10
            return if(strongFlip)ReEvaluation("EXPIRED","Original ${original.direction} signal is EXPIRED: fresh ${original.timeframe} candles now confirm a materially stronger ${fresh.direction} thesis (${fresh.score}/100, directional separation $dominance). ${check.reason}",fresh)
            else ReEvaluation("WEAKENING","Opposite ${fresh.direction} evidence is developing on fresh ${original.timeframe} candles, but it is not strong enough for a full invalidation yet. ${check.reason}",fresh)
        }
        val same=sameSetup(original,fresh);val acceptable=fresh.score>=maxOf(52,original.score-10)
        return if(same||acceptable)ReEvaluation("STILL VALID","Fresh ${original.timeframe} candles still support the original ${original.direction} thesis. Current full-engine confirmation ${fresh.score}/100. ${check.reason}",fresh)
        else ReEvaluation("WEAKENING","Direction remains ${original.direction}, but fresh ${original.timeframe} confluence weakened to ${fresh.score}/100 from ${original.score}/100. ${check.reason}",fresh)
    }
'''
s=s[:start]+new_re+s[end:]

# Extend no-trade horizons / descriptions to every timeframe.
s=s.replace('''        val lookback=when{tf<=1->52;tf<=5->46;tf<=10->42;tf<=15->38;tf<=30->32;else->28}
''','''        val lookback=when{tf<=1->52;tf<=5->46;tf<=10->42;tf<=15->38;tf<=30->32;tf<=60->28;tf<=120->26;tf<=300->24;tf<=1440->22;tf<=10080->20;else->18}
''',1)
s=s.replace('''        val majors=directionalMajorLevels(c,a,when{tf<=1->80;tf<=5->72;tf<=10->64;tf<=15->58;tf<=30->50;else->42});''',
'''        val majors=directionalMajorLevels(c,a,when{tf<=1->80;tf<=5->72;tf<=10->64;tf<=15->58;tf<=30->50;tf<=60->46;tf<=120->42;tf<=300->38;tf<=1440->34;tf<=10080->30;else->26});''',1)
s=s.replace('''        val profile=when{tf<=1->"1m microstructure";tf<=5->"5m intraday";tf<=10->"10m intraday bridge";tf<=15->"15m structure";tf<=30->"30m swing structure";else->"1h higher-timeframe structure"}
''','''        val profile=when{tf<=1->"1m microstructure";tf<=5->"5m intraday";tf<=10->"10m intraday bridge";tf<=15->"15m structure";tf<=30->"30m swing structure";tf<=60->"1h higher-timeframe structure";tf<=120->"2h swing structure";tf<=240->"4h macro swing";tf<=300->"5h macro swing";tf<=1440->"1d daily structure";tf<=10080->"1w weekly structure";else->"1M monthly structure"}
''',1)
s=s.replace('''        val tfRule=when{tf<=1->"1m: use more micro candles; demand fast displacement/reclaim because noise is highest.";tf<=5->"5m: prioritize intraday BOS/CHoCH + retest/liquidity reaction.";tf<=10->"10m: confirm the 5m noise into a cleaner two-candle structure before accepting continuation/reversal.";tf<=15->"15m: require structure + momentum agreement around a clear S/R/liquidity zone.";tf<=30->"30m: favor confirmed closes and major-level reactions; avoid mid-range entries.";else->"1h: prioritize higher-timeframe swing structure, major S/R and strong displacement/retest confirmation."}
''','''        val tfRule=when{tf<=1->"1m: microstructure requires fast displacement/reclaim because noise is highest.";tf<=5->"5m: prioritize intraday BOS/CHoCH + retest/liquidity reaction.";tf<=10->"10m: aggregate two true 5m candles into cleaner 10m OHLC structure.";tf<=15->"15m: require structure + momentum agreement around clear S/R/liquidity.";tf<=30->"30m: favor confirmed closes and major-level reactions; avoid mid-range entries.";tf<=60->"1h: prioritize higher-timeframe swing structure, major S/R and displacement/retest.";tf<=120->"2h: require broader swing confirmation; micro noise has low weight.";tf<=240->"4h: prioritize macro BOS/CHoCH, validated OB/FVG and major liquidity.";tf<=300->"5h: use macro swing structure and strong level reactions rather than intraday noise.";tf<=1440->"1d: daily structure dominates; require decisive close/reclaim around major levels.";tf<=10080->"1w: weekly structure and long-horizon liquidity dominate the setup.";else->"1M: monthly macro structure only; short-term intraday evidence has minimal influence."}
''',1)

# Volatility thresholds are also timeframe-specific.
s=s.replace('''        val tf=tfMinutes(timeframe);val atrMult=when{tf<=1->2.85;tf<=5->2.70;tf<=10->2.65;tf<=15->2.60;tf<=30->2.50;else->2.40};val medMult=when{tf<=5->3.30;tf<=15->3.20;tf<=30->3.10;else->3.00}
''','''        val tf=tfMinutes(timeframe);val atrMult=when{tf<=1->2.85;tf<=5->2.70;tf<=10->2.65;tf<=15->2.60;tf<=30->2.50;tf<=60->2.40;tf<=120->2.35;tf<=300->2.30;tf<=1440->2.25;else->2.20};val medMult=when{tf<=5->3.30;tf<=15->3.20;tf<=30->3.10;tf<=120->3.00;tf<=300->2.95;else->2.90}
''',1)

# Public chart levels + validated order-block helper.
anchor='''    private fun directionalMajorLevels(c:List<Candle>,a:Double,lookback:Int):Pair<Double,Double>{'''
if 'fun chartLevels(timeframe:String,c:List<Candle>)' not in s:
    helpers='''    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{
        if(c.size<30)return null
        val a=atr(c,14).coerceAtLeast(1e-9);val tf=tfMinutes(timeframe)
        val look=when{tf<=1->80;tf<=5->72;tf<=10->64;tf<=15->58;tf<=30->50;tf<=60->46;tf<=120->42;tf<=300->38;tf<=1440->34;tf<=10080->30;else->26}
        val sr=directionalMajorLevels(c,a,look)
        val bo=validatedOrderBlock(c,"BUY",a);val so=validatedOrderBlock(c,"SELL",a)
        return ChartLevels(sr.first,sr.second,bo?.let{min(it.o,it.c)},bo?.let{max(it.o,it.c)},so?.let{min(it.o,it.c)},so?.let{max(it.o,it.c)})
    }

    private fun validatedOrderBlock(c:List<Candle>,direction:String,a:Double):Candle?{
        val w=c.takeLast(min(48,c.size));if(w.size<8)return null
        for(i in w.size-5 downTo 2){
            val x=w[i];val body=abs(x.c-x.o);if(body<a*.10)continue
            val after=w.subList(i+1,min(w.size,i+5));if(after.isEmpty())continue
            if(direction=="BUY"){
                if(x.c>=x.o)continue
                val displacement=after.any{it.c>x.h+a*.22&&it.c-it.o>a*.28}
                val moved=after.maxOf{it.h}>x.h+a*.45
                if(displacement&&moved)return x
            }else{
                if(x.c<=x.o)continue
                val displacement=after.any{it.c<x.l-a*.22&&it.o-it.c>a*.28}
                val moved=after.minOf{it.l}<x.l-a*.45
                if(displacement&&moved)return x
            }
        }
        return null
    }

'''
    if anchor not in s: raise SystemExit('v42 chart-level helper anchor not found')
    s=s.replace(anchor,helpers+anchor,1)

p.write_text(s)

# -----------------------------------------------------------------------------
# Main activity + floating UI: every timeframe and analysis guide bridge.
# -----------------------------------------------------------------------------
all_periods='arrayOf("1m","5m","10m","15m","30m","1h","2h","4h","5h","1d","1w","1M")'
for file in ['app/src/main/java/com/mh/analysis/MainActivityV29.kt','app/src/main/java/com/mh/analysis/OverlayService.kt']:
    p=Path(file);x=p.read_text();x=re.sub(r'arrayOf\("1m","5m","10m","15m","30m","1h"\)',all_periods,x);p.write_text(x)

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
# Timeframe-specific chart viewport basis.
s=s.replace('''val bars=when(period.lowercase()){ "1m"->70;"5m"->48;"15m"->32;"30m"->30;else->28 }''',
'''val bars=when(period){"1m"->90;"5m"->64;"10m"->52;"15m"->44;"30m"->38;"1h"->34;"2h"->32;"4h"->30;"5h"->28;"1d"->26;"1w"->24;"1M"->22;else->32}''')
# Selected chart always reuses cached levels when available.
s=s.replace('''    private fun switchVisibleChart(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showExisting()}
''','''    private fun switchVisibleChart(){pairLabel.text="$symbol • $period";if(chartReady){chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showCachedAnalysisGuides()};showExisting()}
''',1)
# Fresh analyze/re-evaluate immediately redraw selected-timeframe levels.
s=s.replace('''candles=out;performAnalysis()''','''candles=out;performAnalysis();showAnalysisGuides(out)''',1)
s=s.replace('''                    status.text=formatManualSignal(next,result.reason)
                    showSignalCard(next)
''','''                    status.text=formatManualSignal(next,result.reason)
                    showSignalCard(next);showAnalysisGuides(out)
''',1)

anchor='''    private fun showExisting(){'''
if 'private fun showAnalysisGuides(data:List<Candle>)' not in s:
    helper='''    private fun showAnalysisGuides(data:List<Candle>){
        if(!chartReady)return
        val lv=AnalysisEngine.chartLevels(period,data)?:run{chart.evaluateJavascript("clearAnalysisLevels()",null);return}
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)}
        lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }
    private fun showCachedAnalysisGuides(){
        val data=FcsClient.peek(symbol,period,220)
        if(data.isNullOrEmpty())chart.evaluateJavascript("clearAnalysisLevels()",null) else showAnalysisGuides(data)
    }

'''
    if anchor not in s: raise SystemExit('v42 MainActivity guide anchor not found')
    s=s.replace(anchor,helper+anchor,1)
p.write_text(s)

p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('''val bars=when(period.lowercase()){ "1m"->70;"5m"->48;"15m"->32;"30m"->30;else->28 }''',
'''val bars=when(period){"1m"->90;"5m"->64;"10m"->52;"15m"->44;"30m"->38;"1h"->34;"2h"->32;"4h"->30;"5h"->28;"1d"->26;"1w"->24;"1M"->22;else->32}''')
s=s.replace('''    private fun loadChart(){chart?.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);overlay(SignalStore.loadActive(this,symbol,period))}
''','''    private fun loadChart(){chart?.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);overlay(SignalStore.loadActive(this,symbol,period));showOverlayGuidesFromCache()}
''',1)
if 'private fun showOverlayGuidesFromCache()' not in s:
    anchor='''    private fun displayed()=SignalStore.loadActive(this,symbol,period)'''
    helper='''    private fun showOverlayGuidesFromCache(){
        val data=FcsClient.peek(symbol,period,220)?:return chart?.evaluateJavascript("clearAnalysisLevels()",null).let{}
        val lv=AnalysisEngine.chartLevels(period,data)?:return
        val j=JSONObject().put("support",lv.support).put("resistance",lv.resistance)
        lv.bullObLow?.let{j.put("bullObLow",it)};lv.bullObHigh?.let{j.put("bullObHigh",it)};lv.bearObLow?.let{j.put("bearObLow",it)};lv.bearObHigh?.let{j.put("bearObHigh",it)}
        chart?.evaluateJavascript("setAnalysisLevels(${JSONObject.quote(j.toString())})",null)
    }

'''
    if anchor not in s: raise SystemExit('v42 Overlay guide anchor not found')
    s=s.replace(anchor,helper+anchor,1)
s=s.replace('''    private fun showState(){''','''    private fun showState(){showOverlayGuidesFromCache();''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView: map all periods and draw S/R + validated order-block guides.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text()
start=s.index('function mapInterval(p){')
end=s.index('\nfunction fmt(',start)
new_map='''function mapInterval(p){
  const raw=String(p||'15m').trim();
  if(raw==='1M')return'M';
  const x=raw.toLowerCase();
  if(x==='1m'||x==='1')return'1';if(x==='5m'||x==='5')return'5';if(x==='10m'||x==='10')return'10';if(x==='15m'||x==='15')return'15';if(x==='30m'||x==='30')return'30';
  if(x==='1h'||x==='60')return'60';if(x==='2h'||x==='120')return'120';if(x==='4h'||x==='240')return'240';if(x==='5h'||x==='300')return'300';
  if(x==='1d'||x==='d')return'D';if(x==='1w'||x==='w')return'W';return'60';
}'''
s=s[:start]+new_map+s[end:]

s=s.replace('let tvWidget=null, chartApi=null, lastSignal=null, exactApi=false, shapeIds=[];',
            'let tvWidget=null, chartApi=null, lastSignal=null, lastAnalysis=null, exactApi=false, shapeIds=[];',1)

# Replace signal drawing with one shared redraw layer so analysis and signal levels coexist.
start=s.index('function drawSignal(s){')
end=s.index('\nfunction getChartApi()',start)
new_draw='''function redrawAll(){
  removeNativeShapes();
  if(!exactApi||!chartApi)return;
  if(lastAnalysis){
    drawNativeLine(lastAnalysis.support,'#42a5f5',true,'SUPPORT '+fmt(lastAnalysis.support));
    drawNativeLine(lastAnalysis.resistance,'#ab47bc',true,'RESISTANCE '+fmt(lastAnalysis.resistance));
    if(Number.isFinite(Number(lastAnalysis.bullObLow)))drawNativeLine(lastAnalysis.bullObLow,'#26a69a',true,'BULL OB LOW '+fmt(lastAnalysis.bullObLow));
    if(Number.isFinite(Number(lastAnalysis.bullObHigh)))drawNativeLine(lastAnalysis.bullObHigh,'#26a69a',true,'BULL OB HIGH '+fmt(lastAnalysis.bullObHigh));
    if(Number.isFinite(Number(lastAnalysis.bearObLow)))drawNativeLine(lastAnalysis.bearObLow,'#ef5350',true,'BEAR OB LOW '+fmt(lastAnalysis.bearObLow));
    if(Number.isFinite(Number(lastAnalysis.bearObHigh)))drawNativeLine(lastAnalysis.bearObHigh,'#ef5350',true,'BEAR OB HIGH '+fmt(lastAnalysis.bearObHigh));
  }
  if(lastSignal){
    const dir=String(lastSignal.direction||'').toUpperCase();
    drawNativeLine(lastSignal.entry,'#f2c94c',false,'ENTRY '+dir+' '+fmt(lastSignal.entry));
    drawNativeLine(lastSignal.sl,'#ff5a67',true,'SL '+fmt(lastSignal.sl));
    drawNativeLine(lastSignal.tp1,'#3ddc84',true,'TP1 '+fmt(lastSignal.tp1));
    drawNativeLine(lastSignal.tp2,'#56d7d1',true,'TP2 '+fmt(lastSignal.tp2));
  }
}
function drawSignal(s){lastSignal=s;renderSignalCard(s);redrawAll()}
function setAnalysisLevels(raw){
  if(!raw){clearAnalysisLevels();return}
  let x=raw;try{if(typeof raw==='string')x=JSON.parse(raw)}catch(e){clearAnalysisLevels();return}
  lastAnalysis=x;redrawAll()
}
function clearAnalysisLevels(){lastAnalysis=null;redrawAll()}
'''
s=s[:start]+new_draw+s[end:]

# Widget ready redraws both analysis and signal guides.
s=s.replace('''  if(lastSignal)drawSignal(lastSignal);''','''  redrawAll();if(lastSignal)renderSignalCard(lastSignal);''',1)

p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 42',s);s=re.sub(r'versionName = "[^"]+"','versionName = "42.0"',s);p.write_text(s)
print('v42 all timeframes + same-candle re-evaluation + TradingView structure guides applied')
