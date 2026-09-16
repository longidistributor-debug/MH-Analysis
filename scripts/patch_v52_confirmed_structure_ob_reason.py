from pathlib import Path
import re

# v52: confirmed structure + transparent OB diagnostics.
# - MAJOR S/R is derived only from CLOSED selected-timeframe candles.
# - The running/current candle may test, break or reclaim a confirmed level, but
#   it does not replace that level until the candle closes.
# - Do not reject a real violent closed-candle extreme as an ATR "outlier".
# - If an OB is unavailable, explain exactly why instead of printing '-'.

p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

# Replace v51 majorRangeLevels. v51 included the active candle and could also
# discard a genuine volatility extreme via a 5 ATR outlier filter. Both are
# wrong for the user's confirmed-candle market map.
start=s.index('    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{')
end=s.index('\n\n    fun chartLevels',start)
new_major='''    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{
        if(c.size<31)return null
        val tf=tfMinutes(timeframe)
        val look=when{
            tf<=1->180;tf<=5->132;tf<=10->112;tf<=15->96;tf<=30->84;tf<=60->72;
            tf<=120->64;tf<=300->56;tf<=1440->48;tf<=10080->40;else->32
        }
        // The final candle is the fresh/running candle merged by FcsClient.
        // Confirmed major structure MUST come from completed candles only.
        val closed=c.dropLast(1)
        if(closed.size<20)return null
        val w=closed.takeLast(min(look,closed.size))
        if(w.size<20)return null
        val majorLow=w.minOf{it.l}
        val majorHigh=w.maxOf{it.h}
        if(!majorLow.isFinite()||!majorHigh.isFinite()||majorHigh<=majorLow)return null
        return majorLow to majorHigh
    }'''
s=s[:start]+new_major+s[end:]

# Replace chartLevels so a live candle temporarily trading through a confirmed
# boundary does not erase the already-confirmed major level.
start=s.index('    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{')
end=s.index('\n\n    private fun validatedOrderBlock',start)
new_chart='''    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{
        if(c.size<31)return null
        val a=atr(c,14).coerceAtLeast(1e-9)
        val major=majorRangeLevels(timeframe,c)?:return null
        val bo=validatedOrderBlock(c,"BUY",a);val so=validatedOrderBlock(c,"SELL",a)
        return ChartLevels(
            major.first,major.second,
            bo?.let{min(it.o,it.c)},bo?.let{max(it.o,it.c)},
            so?.let{min(it.o,it.c)},so?.let{max(it.o,it.c)}
        )
    }'''
s=s[:start]+new_chart+s[end:]

# Add a public diagnostic that mirrors the actual validatedOrderBlock rules.
# It is used only when no valid zone exists, so the UI tells the user why.
insert=s.index('\n\n    private fun validatedOrderBlock',s.index('    fun chartLevels'))
if 'fun orderBlockUnavailableReason(' not in s:
    helper='''

    fun orderBlockUnavailableReason(c:List<Candle>,direction:String):String{
        if(c.size<10)return "None — not enough selected-timeframe candles to validate an order block"
        val a=atr(c,14).coerceAtLeast(1e-9)
        if(validatedOrderBlock(c,direction,a)!=null)return "Available"
        val w=c.takeLast(min(64,c.size));if(w.size<10)return "None — not enough selected-timeframe candles to validate an order block"
        val current=w.last().c
        var sawBase=false;var sawDisplacement=false;var sawInvalidated=false
        for(i in w.size-5 downTo 2){
            val x=w[i];val body=abs(x.c-x.o);if(body<a*.10)continue
            val low=min(x.o,x.c);val high=max(x.o,x.c)
            val after=w.subList(i+1,min(w.size,i+5));if(after.isEmpty())continue
            val later=w.subList(i+1,w.size)
            if(direction=="BUY"){
                if(x.c>=x.o)continue
                sawBase=true
                val displacement=after.any{it.c>x.h+a*.22&&it.c-it.o>a*.28};val moved=after.maxOf{it.h}>x.h+a*.45
                if(displacement&&moved){
                    sawDisplacement=true
                    if(later.any{it.c<low-a*.08}||current<low-a*.08)sawInvalidated=true
                }
            }else{
                if(x.c<=x.o)continue
                sawBase=true
                val displacement=after.any{it.c<x.l-a*.22&&it.o-it.c>a*.28};val moved=after.minOf{it.l}<x.l-a*.45
                if(displacement&&moved){
                    sawDisplacement=true
                    if(later.any{it.c>high+a*.08}||current>high+a*.08)sawInvalidated=true
                }
            }
        }
        return if(direction=="BUY") when{
            sawInvalidated->"None — previous bullish OB was invalidated by a later close below its zone"
            sawBase&&!sawDisplacement->"None — bearish base exists, but no confirmed bullish displacement/BOS followed it"
            !sawBase->"None — no qualifying bearish base candle for a bullish OB"
            else->"None — no active bullish OB satisfies displacement and invalidation rules"
        } else when{
            sawInvalidated->"None — previous bearish OB was invalidated by a later close above its zone"
            sawBase&&!sawDisplacement->"None — bullish base exists, but no confirmed bearish displacement/BOS followed it"
            !sawBase->"None — no qualifying bullish base candle for a bearish OB"
            else->"None — no active bearish OB satisfies displacement and invalidation rules"
        }
    }'''
    s=s[:insert]+helper+s[insert:]

p.write_text(s)

# MainActivity Market Map: show confirmed major boundaries even if the live
# candle is testing/breaching one intrabar, and explain missing OBs.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
m=p.read_text()

# Replace the v49/v51 safety branch inside updateSnapshot.
old='''            // Hard safety: never print crossed levels as current S/R.
            if(current!=null&&(lv.support>=current||lv.resistance<=current))out.append("➜ MAP: INVALIDATED — press ANALYZE again; crossed levels were suppressed.")
            else{
                out.append("➜ MAJOR SUPPORT: ${price(lv.support)}\\n")
                out.append("➜ MAJOR RESISTANCE: ${price(lv.resistance)}\\n")
                val bull=if(lv.bullObLow!=null&&lv.bullObHigh!=null)"${price(lv.bullObLow)}–${price(lv.bullObHigh)}" else "-"
                val bear=if(lv.bearObLow!=null&&lv.bearObHigh!=null)"${price(lv.bearObLow)}–${price(lv.bearObHigh)}" else "-"
                out.append("➜ BULL OB: $bull\\n");out.append("➜ BEAR OB: $bear")
            }'''
new='''            val supportState=if(current!=null&&current<lv.support)" • LIVE BELOW — awaiting close/reclaim" else " • confirmed closed-candle level"
            val resistanceState=if(current!=null&&current>lv.resistance)" • LIVE ABOVE — awaiting close/reject" else " • confirmed closed-candle level"
            out.append("➜ MAJOR SUPPORT: ${price(lv.support)}$supportState\\n")
            out.append("➜ MAJOR RESISTANCE: ${price(lv.resistance)}$resistanceState\\n")
            val bull=if(lv.bullObLow!=null&&lv.bullObHigh!=null)"${price(lv.bullObLow)}–${price(lv.bullObHigh)}" else AnalysisEngine.orderBlockUnavailableReason(basis?:emptyList(),"BUY")
            val bear=if(lv.bearObLow!=null&&lv.bearObHigh!=null)"${price(lv.bearObLow)}–${price(lv.bearObHigh)}" else AnalysisEngine.orderBlockUnavailableReason(basis?:emptyList(),"SELL")
            out.append("➜ BULL OB: $bull\\n");out.append("➜ BEAR OB: $bear")'''
if old not in m:
    raise SystemExit('v52 MainActivity market-map block anchor not found')
m=m.replace(old,new,1)

# More accurate empty-map wording for the new confirmed-range semantics.
m=m.replace('➜ MAP: No valid directional S/R pair around current price yet.','➜ MAP: No confirmed closed-candle major range is available yet.')
p.write_text(m)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 52',g);g=re.sub(r'versionName = "[^"]+"','versionName = "52.0"',g);p.write_text(g)
print('v52 confirmed closed-candle structure + OB reasons applied')
