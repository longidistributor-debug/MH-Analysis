from pathlib import Path
import re

# v49: current selected-timeframe map correctness + concise output order.
# - S/R can never be inverted relative to the fresh current close.
# - Broken support can role-reverse into resistance after displacement.
# - Invalidated OBs are discarded.
# - Normal ANALYZE output: TRADE LEVELS -> SETUP -> MATCHED CONFIRMATIONS.
# - RE-EVALUATION appears only after the user presses RE-EVALUATE.
# - Stale Market Map levels are hidden instead of being presented as current.
# - Keep genuine live TradingView widget; native shapes/zones only when TV exposes
#   the programmable chart API. No drifting HTML overlay fallback.

# -----------------------------------------------------------------------------
# AnalysisEngine: truly directional current S/R + active order blocks.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

start=s.index('    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{')
end=s.index('\n\n    private fun validatedOrderBlock',start)
new_chart='''    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{
        if(c.size<30)return null
        val a=atr(c,14).coerceAtLeast(1e-9);val tf=tfMinutes(timeframe);val current=c.last().c
        val look=when{tf<=1->88;tf<=5->76;tf<=10->70;tf<=15->64;tf<=30->56;tf<=60->50;tf<=120->46;tf<=300->42;tf<=1440->38;tf<=10080->34;else->30}
        val raw=c.takeLast(min(look,c.size));val confirmed=if(raw.size>8)raw.dropLast(2) else raw
        val lows=mutableListOf<Pair<Double,Int>>();val highs=mutableListOf<Pair<Double,Int>>()
        for(i in 2 until confirmed.size-2){
            val x=confirmed[i]
            if(x.l<=confirmed[i-1].l&&x.l<=confirmed[i-2].l&&x.l<=confirmed[i+1].l&&x.l<=confirmed[i+2].l)lows+=x.l to i
            if(x.h>=confirmed[i-1].h&&x.h>=confirmed[i-2].h&&x.h>=confirmed[i+1].h&&x.h>=confirmed[i+2].h)highs+=x.h to i
        }
        val tol=max(a*.16,abs(current)*0.000025);val minGap=max(a*.025,abs(current)*0.000005)
        fun clusters(src:List<Pair<Double,Int>>):List<Triple<Double,Int,Int>>{
            if(src.isEmpty())return emptyList();val groups=mutableListOf<MutableList<Pair<Double,Int>>>()
            for(pt in src.sortedBy{it.first}){val g=groups.lastOrNull();val center=g?.map{it.first}?.average();if(g!=null&&center!=null&&abs(center-pt.first)<=tol)g+=pt else groups+=mutableListOf(pt)}
            return groups.map{g->Triple(g.map{it.first}.average(),g.size,g.maxOf{it.second})}
        }
        val lc=clusters(lows);val hc=clusters(highs)
        // Role reversal matters after displacement: a broken pivot-low above price
        // can become resistance; a broken pivot-high below price can become support.
        val below=(lc+hc).filter{it.first<current-minGap}
        val above=(lc+hc).filter{it.first>current+minGap}
        fun nearestBelow(src:List<Triple<Double,Int,Int>>):Double?=src.filter{it.second>=2}.maxByOrNull{it.first}?.first?:src.maxByOrNull{it.first}?.first
        fun nearestAbove(src:List<Triple<Double,Int,Int>>):Double?=src.filter{it.second>=2}.minByOrNull{it.first}?.first?:src.minByOrNull{it.first}?.first
        var support=nearestBelow(below);var resistance=nearestAbove(above)
        // During a fresh breakout/breakdown there may be no confirmed pivot on one
        // side yet. Use only REAL recent candle extremes on the correct side.
        val recent=c.takeLast(min(10,c.size))
        if(support==null||support>=current){support=recent.map{it.l}.filter{it<current-minGap}.maxOrNull()}
        if(resistance==null||resistance<=current){resistance=recent.map{it.h}.filter{it>current+minGap}.minOrNull()}
        // Wider real-extreme fallback, still never fabricate a level or cross price.
        if(support==null){support=raw.map{it.l}.filter{it<current-minGap}.maxOrNull()}
        if(resistance==null){resistance=raw.map{it.h}.filter{it>current+minGap}.minOrNull()}
        if(support==null||resistance==null||support>=current||resistance<=current)return null
        val bo=validatedOrderBlock(c,"BUY",a);val so=validatedOrderBlock(c,"SELL",a)
        return ChartLevels(support,resistance,bo?.let{min(it.o,it.c)},bo?.let{max(it.o,it.c)},so?.let{min(it.o,it.c)},so?.let{max(it.o,it.c)})
    }'''
s=s[:start]+new_chart+s[end:]

start=s.index('    private fun validatedOrderBlock(c:List<Candle>,direction:String,a:Double):Candle?{')
end=s.index('\n\n    private fun directionalMajorLevels',start)
new_ob='''    private fun validatedOrderBlock(c:List<Candle>,direction:String,a:Double):Candle?{
        val w=c.takeLast(min(64,c.size));if(w.size<10)return null
        val current=w.last().c
        for(i in w.size-5 downTo 2){
            val x=w[i];val body=abs(x.c-x.o);if(body<a*.10)continue
            val low=min(x.o,x.c);val high=max(x.o,x.c)
            val after=w.subList(i+1,min(w.size,i+5));if(after.isEmpty())continue
            val later=w.subList(i+1,w.size)
            if(direction=="BUY"){
                if(x.c>=x.o)continue
                val displacement=after.any{it.c>x.h+a*.22&&it.c-it.o>a*.28};val moved=after.maxOf{it.h}>x.h+a*.45
                if(!displacement||!moved)continue
                // A bullish demand block is invalid once later structure closes
                // materially below its body. Do not display stale demand above price.
                val invalid=later.any{it.c<low-a*.08}||current<low-a*.08
                if(!invalid)return x
            }else{
                if(x.c<=x.o)continue
                val displacement=after.any{it.c<x.l-a*.22&&it.o-it.c>a*.28};val moved=after.minOf{it.l}<x.l-a*.45
                if(!displacement||!moved)continue
                val invalid=later.any{it.c>high+a*.08}||current>high+a*.08
                if(!invalid)return x
            }
        }
        return null
    }'''
s=s[:start]+new_ob+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: hide stale map, reorder signal detail, re-eval only on demand.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

start=s.index('    private fun updateSnapshot(data:List<Candle>?=null){')
end=s.index('\n    private fun showExisting(){',start)
new_snapshot='''    private fun updateSnapshot(data:List<Candle>?=null){
        if(!::snapshot.isInitialized)return
        val active=SignalStore.loadActive(this,symbol,period)
        val basis=data?:FcsClient.peek(symbol,period,220)
        val age=FcsClient.cacheAgeMs(symbol,period);val ageMs=age?:Long.MAX_VALUE
        val current=basis?.lastOrNull()?.c
        val freshEnough=ageMs<=90_000L
        val lv=if(freshEnough&&!basis.isNullOrEmpty())AnalysisEngine.chartLevels(period,basis) else null
        val out=StringBuilder();out.append("CURRENT SETUP\\n")
        if(active==null)out.append("➜ SIGNAL: None for $symbol • $period\\n") else{
            val sig=active.signal;out.append("➜ SIGNAL: ${sig.direction} • ${active.state} • ${sig.score}/100\\n")
            out.append("➜ ENTRY: ${price(sig.entry)}   SL: ${price(sig.sl)}\\n");out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\\n")
        }
        out.append("\\nMARKET MAP • $period\\n")
        val ageText=age?.let{if(it<1000L)"now" else "${it/1000L}s ago"}?:"unknown"
        out.append("➜ DATA: ${FcsClient.feedLabel(symbol)} • $ageText")
        current?.let{out.append(" • close ${price(it)}")};out.append("\\n")
        if(!freshEnough){out.append("➜ MAP: STALE — press ANALYZE for fresh selected-timeframe S/R and OB.")}
        else if(lv==null){out.append("➜ MAP: No valid directional S/R pair around current price yet.")}
        else{
            // Hard safety: never print crossed levels as current S/R.
            if(current!=null&&(lv.support>=current||lv.resistance<=current))out.append("➜ MAP: INVALIDATED — press ANALYZE again; crossed levels were suppressed.")
            else{
                out.append("➜ SUPPORT: ${price(lv.support)}   RESISTANCE: ${price(lv.resistance)}\\n")
                val bull=if(lv.bullObLow!=null&&lv.bullObHigh!=null)"${price(lv.bullObLow)}–${price(lv.bullObHigh)}" else "-"
                val bear=if(lv.bearObLow!=null&&lv.bearObHigh!=null)"${price(lv.bearObLow)}–${price(lv.bearObHigh)}" else "-"
                out.append("➜ BULL OB: $bull\\n");out.append("➜ BEAR OB: $bear")
            }
        }
        snapshot.text=styledOutput(out.toString())
    }
'''
s=s[:start]+new_snapshot+s[end:]

start=s.index('    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{')
end=s.index('\n    private fun showRecords()',start)
new_format='''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{
        val sig=a.signal;val matched=sig.reasons.map{it.trim()}.filter{it.isNotBlank()}.distinct().take(5);val out=StringBuilder()
        out.append("TRADE LEVELS\\n")
        out.append("➜ ${sig.direction} • ${sig.score}/100 • ${a.state}\\n")
        out.append("➜ ENTRY: ${price(sig.entry)}\\n")
        out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\\n")
        out.append("➜ SL / INVALIDATION: ${price(sig.sl)}\\n\\n")
        out.append("SETUP\\n");out.append("➜ ${sig.setupReason.trim()}\\n\\n")
        out.append("MATCHED CONFIRMATIONS\\n")
        if(matched.isEmpty())out.append("➜ Primary setup conditions matched.") else matched.forEach{out.append("➜ ").append(it).append("\\n")}
        // Never show re-evaluation in normal ANALYZE/display output. It appears only
        // when RE-EVALUATE explicitly supplies a fresh conclusion.
        if(forcedConclusion!=null){out.append("\\nRE-EVALUATION\\n").append(arrowLines(forcedConclusion))}
        return out.toString().trim()
    }
'''
s=s[:start]+new_format+s[end:]

# One-time migration: discard old active setups generated before directional-map
# correction. User gets a clean fresh analysis under v49 rules.
oncreate='''        setContentView(buildUi())\n        showExisting()'''
if oncreate in s and 'v49_map_migrated' not in s:
    s=s.replace(oncreate,'''        setContentView(buildUi())
        if(!prefs.getBoolean("v49_map_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD");SignalStore.clearActiveForSymbol(this,"BTCUSDT")
            prefs.edit().putBoolean("v49_map_migrated",true).apply()
        }
        showExisting()''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView: no fake overlay. OB native rectangles have color only/no labels.
# Make native-drawing capability explicit in tiny status text.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
h=p.read_text()
# Replace obZone if v48 added it.
if 'function obZone(' in h:
    h=re.sub(r"function obZone\(low,high,color,label\)\{.*?\}\nfunction redraw\(\)",
'''function obZone(low,high,color,label){if(!chartApi||typeof chartApi.createMultipointShape!=='function'||!Number.isFinite(Number(low))||!Number.isFinite(Number(high)))return;try{const vr=typeof chartApi.getVisibleRange==='function'?chartApi.getVisibleRange():null;if(!vr||vr.from==null||vr.to==null)return;remember(chartApi.createMultipointShape([{time:vr.from,price:Number(low)},{time:vr.to,price:Number(high)}],{shape:'rectangle',lock:true,disableSelection:true,disableSave:true,disableUndo:true,overrides:{linecolor:color,backgroundColor:color,transparency:88,linewidth:1,showLabel:false}}))}catch(e){}}\nfunction redraw()''',h,count=1,flags=re.S)
# Strengthen ready/status reporting without adding a drifting fallback.
h=h.replace("function ready(t){if(t!==token)return;chartApi=getApi();redraw()}","function ready(t){if(t!==token)return;chartApi=getApi();const st=document.getElementById('state');const nativeOk=!!(chartApi&&typeof chartApi.createShape==='function');if(st)st.textContent='LIVE TRADINGVIEW • NATIVE MARKS '+(nativeOk?'ON':'UNAVAILABLE');redraw()}")
p.write_text(h)

# Version
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \\d+','versionCode = 49',s);s=re.sub(r'versionName = "[^"]+"','versionName = "49.0"',s);p.write_text(s)
print('v49 current directional market map + active OB + output cleanup applied')
