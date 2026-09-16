from pathlib import Path
import re

# v40: three additional video-derived confluence families.
# They are supporting setup families, never universal blockers, and they preserve
# the full existing structure/liquidity/MA/FVG/OB/divergence/video engine.

p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

# -----------------------------------------------------------------------------
# 1) Detect the three new chart techniques after existing v33 wick-fill logic.
# -----------------------------------------------------------------------------
anchor='''        val bullWickFill=bullWickFillSource?.let{x->val base=max(x.o,x.c);x.h-base>=a*.35&&last.c>base+a*.05&&last.c<x.h+a*.08&&last.c>last.o&&(pressureBull||momentumBull||bosBull||displacementBull)}==true\n        val bearWickFill=bearWickFillSource?.let{x->val base=min(x.o,x.c);base-x.l>=a*.35&&last.c<base-a*.05&&last.c>x.l-a*.08&&last.c<last.o&&(pressureBear||momentumBear||bosBear||displacementBear)}==true\n'''
insert=anchor+'''\n        // v40 VIDEO TECHNIQUE A — range liquidity compression -> external sweep -> reclaim.\n        // Tight ranges build stops on both edges. The middle of the box is not an entry;\n        // confirmation strengthens only after one edge is swept and price reclaims/rejects.\n        val compression=liquidityCompressionRange(c,a)\n        val bullCompressionSweep=compression?.let{box->\n            val swept=c.takeLast(min(4,c.size)).any{x->x.l<box.first-a*.05&&x.c>box.first-a*.02}\n            swept&&last.c>box.first+a*.04&&(pressureBull||momentumBull||chochBull||displacementBull||bullReaction)\n        }==true\n        val bearCompressionSweep=compression?.let{box->\n            val swept=c.takeLast(min(4,c.size)).any{x->x.h>box.second+a*.05&&x.c<box.second+a*.02}\n            swept&&last.c<box.second-a*.04&&(pressureBear||momentumBear||chochBear||displacementBear||bearReaction)\n        }==true\n\n        // v40 VIDEO TECHNIQUE B — abnormal counter-candle / fault-level retest.\n        // A distinctive opposite candle/base interrupting an impulse can become a future\n        // decision level. A later revisit plus rejection/body control is confirmation.\n        val bullFaultLevel=faultLevel(c,"BUY",a)\n        val bearFaultLevel=faultLevel(c,"SELL",a)\n        val bullFaultReaction=bullFaultLevel?.let{lv->last.l<=lv+a*.18&&last.c>=lv-a*.03&&last.c>last.o&&(pressureBull||momentumBull||bosBull||chochBull||bullReaction)}==true\n        val bearFaultReaction=bearFaultLevel?.let{lv->last.h>=lv-a*.18&&last.c<=lv+a*.03&&last.c<last.o&&(pressureBear||momentumBear||bosBear||chochBear||bearReaction)}==true\n'''
if anchor not in s: raise SystemExit('v40 detection anchor not found')
s=s.replace(anchor,insert,1)

# -----------------------------------------------------------------------------
# 2) Add scoring evidence.
# -----------------------------------------------------------------------------
anchor='''        if(bullWickFill)b(16,"Upper-wick body break opened a wick-fill continuation target")\n        if(bearWickFill)s(16,"Lower-wick body break opened a wick-fill continuation target")\n'''
insert=anchor+'''        if(bullCompressionSweep)b(18,"Range liquidity compressed, sell-side edge swept, then reclaimed with bullish confirmation")\n        if(bearCompressionSweep)s(18,"Range liquidity compressed, buy-side edge swept, then rejected with bearish confirmation")\n        if(bullFaultReaction)b(17,"Bullish revisit/rejection of an abnormal counter-candle fault level")\n        if(bearFaultReaction)s(17,"Bearish revisit/rejection of an abnormal counter-candle fault level")\n'''
if anchor not in s: raise SystemExit('v40 score anchor not found')
s=s.replace(anchor,insert,1)

# -----------------------------------------------------------------------------
# 3) Make them independent setup families so a valid video pattern can qualify
#    through the same multi-family / multi-pillar gate as every older technique.
# -----------------------------------------------------------------------------
anchor='''        val bullWickFillFamily=bullWickFill&&(momentumBull||pressureBull||bosBull||displacementBull)\n        val bearWickFillFamily=bearWickFill&&(momentumBear||pressureBear||bosBear||displacementBear)\n'''
insert=anchor+'''        val bullCompressionFamily=bullCompressionSweep&&(bullLiquidityRoute||liqSweepBull||stopHuntBull||chochBull||momentumBull||displacementBull)\n        val bearCompressionFamily=bearCompressionSweep&&(bearLiquidityRoute||liqSweepBear||stopHuntBear||chochBear||momentumBear||displacementBear)\n        val bullFaultFamily=bullFaultReaction&&(trendBull||momentumBull||chochBull||bosBull||bullParticipantFamily)\n        val bearFaultFamily=bearFaultReaction&&(trendBear||momentumBear||chochBear||bosBear||bearParticipantFamily)\n'''
if anchor not in s: raise SystemExit('v40 family-booleans anchor not found')
s=s.replace(anchor,insert,1)

old='''        val bullFamily=listOf(bullLiquidity,bullRetest,bullContinuation,bullChoch,bullBreakout,bullLevelReaction,bullTrendlineFamily,bullLiquidityRoute,bullLevelLadder,bullWickFamily,bullPauseFamily,bullParticipantFamily,bullWickFillFamily).count{it};val bearFamily=listOf(bearLiquidity,bearRetest,bearContinuation,bearChoch,bearBreakout,bearLevelReaction,bearTrendlineFamily,bearLiquidityRoute,bearLevelLadder,bearWickFamily,bearPauseFamily,bearParticipantFamily,bearWickFillFamily).count{it}\n'''
new='''        val bullFamily=listOf(bullLiquidity,bullRetest,bullContinuation,bullChoch,bullBreakout,bullLevelReaction,bullTrendlineFamily,bullLiquidityRoute,bullLevelLadder,bullWickFamily,bullPauseFamily,bullParticipantFamily,bullWickFillFamily,bullCompressionFamily,bullFaultFamily).count{it};val bearFamily=listOf(bearLiquidity,bearRetest,bearContinuation,bearChoch,bearBreakout,bearLevelReaction,bearTrendlineFamily,bearLiquidityRoute,bearLevelLadder,bearWickFamily,bearPauseFamily,bearParticipantFamily,bearWickFillFamily,bearCompressionFamily,bearFaultFamily).count{it}\n'''
if old not in s: raise SystemExit('v40 family-list anchor not found')
s=s.replace(old,new,1)

# -----------------------------------------------------------------------------
# 4) Allow the new levels to become entry candidates when they are valid.
# -----------------------------------------------------------------------------
anchor='''        if(dir=="BUY"&&bullWickFillFamily&&bullWickFillSource!=null)candidates+="upper-wick base retest" to max(bullWickFillSource.o,bullWickFillSource.c)\n        if(dir=="SELL"&&bearWickFillFamily&&bearWickFillSource!=null)candidates+="lower-wick base retest" to min(bearWickFillSource.o,bearWickFillSource.c)\n'''
insert=anchor+'''        if(dir=="BUY"&&bullCompressionFamily&&compression!=null)candidates+="swept range-low reclaim retest" to compression.first\n        if(dir=="SELL"&&bearCompressionFamily&&compression!=null)candidates+="swept range-high rejection retest" to compression.second\n        if(dir=="BUY"&&bullFaultFamily&&bullFaultLevel!=null)candidates+="bullish fault-level retest" to bullFaultLevel\n        if(dir=="SELL"&&bearFaultFamily&&bearFaultLevel!=null)candidates+="bearish fault-level retest" to bearFaultLevel\n'''
if anchor not in s: raise SystemExit('v40 candidate anchor not found')
s=s.replace(anchor,insert,1)

# -----------------------------------------------------------------------------
# 5) Name the setup when one of the new families is the decisive pattern.
# -----------------------------------------------------------------------------
needle='''        val familyName=when{'''
replacement='''        val familyName=when{dir=="BUY"&&bullCompressionFamily->"range-liquidity sweep and reclaim";dir=="SELL"&&bearCompressionFamily->"range-liquidity sweep and rejection";dir=="BUY"&&bullFaultFamily->"abnormal counter-candle fault-level reaction";dir=="SELL"&&bearFaultFamily->"abnormal counter-candle fault-level reaction";'''
if needle not in s: raise SystemExit('v40 familyName anchor not found')
s=s.replace(needle,replacement,1)

# -----------------------------------------------------------------------------
# 6) Video technique C — asymmetric risk/reward quality. This is evaluated only
#    after the existing engine has selected structure-based Entry/SL/TP. It adds
#    confidence; it never overrides poor structure or creates a trade by itself.
# -----------------------------------------------------------------------------
old='''        val score=(60+sep+(family*5)+((selectedIr?.continuationStrength?:0).coerceIn(-8,16)/2)).coerceIn(60,97);val reasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(12).map{"${it.second} (+${it.first})"};val strongest=reasons.take(6).joinToString("; ");val irText=selectedIr?.let{" Impulse/retracement ${pct(it.retracementRatio)} depth, ${two(it.speedRatio)}x speed, ${two(it.counterBodyRatio)}x counter-body, ${it.impulseCandles}/${it.retracementCandles} candles."}.orEmpty()\n'''
new='''        val riskDistance=abs(entry-sl).coerceAtLeast(1e-9)\n        val rr1=abs(tp1-entry)/riskDistance\n        val rr2=abs(tp2-entry)/riskDistance\n        val rrBonus=when{rr1>=2.50->8;rr1>=2.00->6;rr1>=1.60->3;else->0}\n        val score=(60+sep+(family*5)+((selectedIr?.continuationStrength?:0).coerceIn(-8,16)/2)+rrBonus).coerceIn(60,97)\n        val baseReasons=(if(dir=="BUY")br else sr).sortedByDescending{it.first}.take(11).map{"${it.second} (+${it.first})"}\n        val rrReason="Asymmetric structure-based R:R • TP1 ${two(rr1)}R • TP2 ${two(rr2)}R${if(rrBonus>0)" (+$rrBonus)" else ""}"\n        val reasons=(baseReasons+rrReason).take(12)\n        val strongest=reasons.take(6).joinToString("; ");val irText=selectedIr?.let{" Impulse/retracement ${pct(it.retracementRatio)} depth, ${two(it.speedRatio)}x speed, ${two(it.counterBodyRatio)}x counter-body, ${it.impulseCandles}/${it.retracementCandles} candles."}.orEmpty()\n'''
if old not in s: raise SystemExit('v40 RR score anchor not found')
s=s.replace(old,new,1)

# Add RR visibility to the setup explanation.
s=s.replace('''Targets prefer the next opposing liquidity/structure level when available."''','''Projected structure-based reward is ${two(rr1)}R to TP1 and ${two(rr2)}R to TP2. Targets prefer the next opposing liquidity/structure level when available."''',1)

# -----------------------------------------------------------------------------
# 7) Helpers.
# -----------------------------------------------------------------------------
anchor='''    private fun impulsePauseLevel(c:List<Candle>,direction:String,a:Double):Double?{'''
helpers='''    private fun liquidityCompressionRange(c:List<Candle>,a:Double):Pair<Double,Double>?{\n        if(c.size<18)return null\n        val w=c.takeLast(min(22,c.size)).dropLast(1)\n        if(w.size<12)return null\n        // Look for a recent compact box rather than using the entire window.\n        for(len in 8..min(16,w.size)){\n            val box=w.takeLast(len)\n            val hi=box.maxOf{it.h};val lo=box.minOf{it.l};val span=hi-lo\n            if(span<a*.70||span>a*3.20)continue\n            val highTouches=box.count{hi-it.h<=a*.18}\n            val lowTouches=box.count{it.l-lo<=a*.18}\n            val mid=(hi+lo)/2\n            val centered=box.count{abs(it.c-mid)<=span*.42}>=len/2\n            if(highTouches>=2&&lowTouches>=2&&centered)return lo to hi\n        }\n        return null\n    }\n\n    private fun faultLevel(c:List<Candle>,direction:String,a:Double):Double?{\n        if(c.size<20)return null\n        val w=c.takeLast(min(42,c.size));if(w.size<12)return null\n        // Exclude the current candle; search for one counter candle/base interrupting\n        // an otherwise directional impulse, then require price to have moved away.\n        for(i in w.size-4 downTo 3){\n            val x=w[i];val body=abs(x.c-x.o)\n            if(body<a*.14)continue\n            val before=w.subList(max(0,i-3),i);val after=w.subList(i+1,min(w.size,i+4))\n            if(before.isEmpty()||after.isEmpty())continue\n            if(direction=="BUY"){\n                if(x.c>=x.o)continue\n                val directional=before.count{it.c>it.o}>=2||after.count{it.c>it.o}>=2\n                val movedAway=after.maxOf{it.h}>x.h+a*.30\n                if(directional&&movedAway)return max(x.o,x.c)\n            }else{\n                if(x.c<=x.o)continue\n                val directional=before.count{it.c<it.o}>=2||after.count{it.c<it.o}>=2\n                val movedAway=after.minOf{it.l}<x.l-a*.30\n                if(directional&&movedAway)return min(x.o,x.c)\n            }\n        }\n        return null\n    }\n\n'''
if anchor not in s: raise SystemExit('v40 helper anchor not found')
s=s.replace(anchor,helpers+anchor,1)

p.write_text(s)

# Version metadata only; v39 manual Analyze/Re-evaluate product flow is preserved.
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 40',s);s=re.sub(r'versionName = "[^"]+"','versionName = "40.0"',s);p.write_text(s)

# Visible header version.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text().replace('MS • v39 • ANALYZE + RE-EVALUATE','MS • v40 • ANALYZE + RE-EVALUATE')
p.write_text(s)

print('v40 three-video confluence techniques applied')
