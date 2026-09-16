from pathlib import Path
import re

# v51: separate MAJOR selected-timeframe structure from local entry structure.
# - Market Map shows broad major swing boundaries, not nearest micro S/R.
# - Local S/R remains internal for retest/entry logic.
# - Major S/R becomes an additional confluence pillar in signal scoring.
# - Align optional FCS WebSocket Gold subscription to OANDA provider family.
# - Keep real TradingView public widget and v50 concise UI.

p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

# Add a broad selected-timeframe major range helper if not already present.
anchor='    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{'
if 'fun majorRangeLevels(timeframe:String,c:List<Candle>)' not in s:
    idx=s.index(anchor)
    helper='''    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{\n        if(c.size<30)return null\n        val tf=tfMinutes(timeframe)\n        val look=when{\n            tf<=1->180;tf<=5->132;tf<=10->112;tf<=15->96;tf<=30->84;tf<=60->72;\n            tf<=120->64;tf<=300->56;tf<=1440->48;tf<=10080->40;else->32\n        }\n        val w=c.takeLast(min(look,c.size))\n        if(w.size<20)return null\n        val current=w.last().c\n        val a=atr(c,14).coerceAtLeast(1e-9)\n        // Major structure uses the broad selected-timeframe dealing range. Include\n        // the active candle because a violent current candle can create the new\n        // major low/high immediately (time alone does not define validity).\n        val rawLow=w.minOf{it.l};val rawHigh=w.maxOf{it.h}\n        if(rawHigh<=rawLow)return null\n        // Reject absurd isolated data spikes only when one wick is many ATR away\n        // from the rest of the selected-timeframe distribution.\n        val lows=w.map{it.l}.sorted();val highs=w.map{it.h}.sorted()\n        val secondLow=lows.getOrNull(1)?:rawLow;val secondHigh=highs.getOrNull(highs.size-2)?:rawHigh\n        val majorLow=if(secondLow-rawLow>a*5.0)secondLow else rawLow\n        val majorHigh=if(rawHigh-secondHigh>a*5.0)secondHigh else rawHigh\n        if(majorLow>=current||majorHigh<=current)return null\n        return majorLow to majorHigh\n    }\n\n'''
    s=s[:idx]+helper+s[idx:]

# Replace chartLevels with a major-map implementation while retaining active OBs.
start=s.index('    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{')
end=s.index('\n\n    private fun validatedOrderBlock',start)
new_chart='''    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{\n        if(c.size<30)return null\n        val a=atr(c,14).coerceAtLeast(1e-9)\n        val major=majorRangeLevels(timeframe,c)?:return null\n        val current=c.last().c\n        val support=major.first;val resistance=major.second\n        if(support>=current||resistance<=current)return null\n        val bo=validatedOrderBlock(c,"BUY",a);val so=validatedOrderBlock(c,"SELL",a)\n        return ChartLevels(\n            support,resistance,\n            bo?.let{min(it.o,it.c)},bo?.let{max(it.o,it.c)},\n            so?.let{min(it.o,it.c)},so?.let{max(it.o,it.c)}\n        )\n    }'''
s=s[:start]+new_chart+s[end:]

# Add major-range proximity to the main analysis context immediately after the
# existing local nearSupport/nearResistance calculation.
needle='''        val nearSupport=abs(last.c-localLow)<=a*1.15||abs(last.c-swingLow)<=a*1.30;val nearResistance=abs(last.c-localHigh)<=a*1.15||abs(last.c-swingHigh)<=a*1.30\n'''
if needle in s and 'nearMajorSupport' not in s:
    repl=needle+'''        val majorRange=majorRangeLevels(timeframe,c);val majorSupport=majorRange?.first;val majorResistance=majorRange?.second\n        val nearMajorSupport=majorSupport?.let{abs(last.c-it)<=a*1.60}==true\n        val nearMajorResistance=majorResistance?.let{abs(last.c-it)<=a*1.60}==true\n'''
    s=s.replace(needle,repl,1)

# Give major selected-timeframe reactions real weight, but do not make them the
# only reason for a trade.
score_anchor='''        if(displacementBull)b(10,"Bullish displacement / pressure");if(displacementBear)s(10,"Bearish displacement / pressure");if(pullbackBull)b(8,"Recent EMA pullback held");if(pullbackBear)s(8,"Recent EMA rejection held");if(nearSupport)b(5,"Near structural support");if(nearResistance)s(5,"Near structural resistance")\n'''
if score_anchor in s and 'Near MAJOR selected-timeframe support' not in s:
    s=s.replace(score_anchor,score_anchor+'''        if(nearMajorSupport)b(9,"Near MAJOR selected-timeframe support ${majorSupport?.let{fmt(it)}?:"-"}")\n        if(nearMajorResistance)s(9,"Near MAJOR selected-timeframe resistance ${majorResistance?.let{fmt(it)}?:"-"}")\n''',1)

# Include major range inside the zone pillar used by v37+ confluence fallback.
s=s.replace('''val bullZonePillar=nearSupport||fvgBull||bullObMid!=null||bullPauseFamily||bullTrendlineFamily||bullWickFamily''',
            '''val bullZonePillar=nearSupport||nearMajorSupport||fvgBull||bullObMid!=null||bullPauseFamily||bullTrendlineFamily||bullWickFamily''',1)
s=s.replace('''val bearZonePillar=nearResistance||fvgBear||bearObMid!=null||bearPauseFamily||bearTrendlineFamily||bearWickFamily''',
            '''val bearZonePillar=nearResistance||nearMajorResistance||fvgBear||bearObMid!=null||bearPauseFamily||bearTrendlineFamily||bearWickFamily''',1)

# Make setup/no-trade text use the same broad major range when available.
s=s.replace('''        val majorLevels=majorSupportResistance(c,a)\n''','''        val majorLevels=majorRangeLevels(timeframe,c)?:majorSupportResistance(c,a)\n''',2)

p.write_text(s)

# Optional live socket alignment: if the account has WebSocket access, subscribe
# to OANDA Gold rather than mixing a generic FX Gold stream into OANDA history.
p=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
h=p.read_text()
h=h.replace('private val symbols=listOf("FX:XAUUSD","BINANCE:BTCUSDT")','private val symbols=listOf("ONA:XAUUSD","BINANCE:BTCUSDT")')
# Expand mappings for supported native timeframes when socket access exists.
h=h.replace('private val periods=listOf("1","5","15","30","60")','private val periods=listOf("1","5","15","30","60","120","240","300","1440","10080")')
h=h.replace('''            "60","1h"->"1h"\n            else->return''','''            "60","1h"->"1h"\n            "120","2h"->"2h"\n            "240","4h"->"4h"\n            "300","5h"->"5h"\n            "1440","1d"->"1d"\n            "10080","1w"->"1w"\n            else->return''')
p.write_text(h)

# Snapshot wording: explicitly label these as MAJOR S/R so users do not confuse
# them with local entry/retest levels.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
m=p.read_text()
m=m.replace('''out.append("➜ SUPPORT: ${price(lv.support)}   RESISTANCE: ${price(lv.resistance)}\\n")''',
            '''out.append("➜ MAJOR SUPPORT: ${price(lv.support)}\\n")\n                out.append("➜ MAJOR RESISTANCE: ${price(lv.resistance)}\\n")''')
p.write_text(m)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 51',g);g=re.sub(r'versionName = "[^"]+"','versionName = "51.0"',g);p.write_text(g)
print('v51 major selected-timeframe structure correction applied')
