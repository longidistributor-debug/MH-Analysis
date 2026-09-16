from pathlib import Path
import re

# v41: true selected-timeframe analysis + volatility-aware confluence.
# Preserve the entire existing indicator/video engine. Fixes:
# - exact candle history per supported TF (10m derived from 5m)
# - timeframe-aware structure windows
# - no universal high-volatility short-circuit
# - directional major S/R (support <= market <= resistance)
# - detailed candle/regime diagnostics proving each TF uses different OHLC

# -----------------------------------------------------------------------------
# FCS data: fetch each selected timeframe as its own candle history.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
s=s.replace('private const val MAX_REQUESTS_PER_WINDOW=3','private const val MAX_REQUESTS_PER_WINDOW=6',1)
s=s.replace('private val periods=listOf("1m","5m","15m","30m","1h")','private val periods=listOf("1m","5m","10m","15m","30m","1h")',1)

start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed='''    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        val current=cache[cacheKey(sym,tf)]?.candles.orEmpty()
        if(current.size>=100&&!force)return current.takeLast(220) to 0
        if(!canRequestNow()){
            if(current.isNotEmpty()&&!force)return current.takeLast(220) to 0
            throw IllegalStateException("Fresh timeframe request limit reached. Wait briefly, then analyze again; stale candles were not presented as fresh data.")
        }
        var credits=0
        fun fetchSeed(sourceTf:String,length:Int):List<Candle>{
            val out=try{fetchMarket(sym,accessKey,sourceTf,length)}catch(e:Exception){noteRequest();throw e}
            noteRequest();credits+=out.second
            return out.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}
        }
        when(tf){
            "10m"->{
                // FCS 5m candles are aggregated into true 10-minute OHLC buckets.
                val five=fetchSeed("5m",300)
                putCache(sym,"5m",five,true)
                putCache(sym,"10m",aggregate(five,10),true)
            }
            "1m","5m","15m","30m","1h"->{
                // Analyze the provider's exact selected-timeframe candles.
                val exact=fetchSeed(tf,300)
                putCache(sym,tf,exact,true)
            }
            else->throw IllegalStateException("Unsupported timeframe $tf")
        }
        val result=cache[cacheKey(sym,tf)]?.candles.orEmpty().takeLast(220)
        if(result.size<100)throw IllegalStateException("$sym $tf does not yet have enough independent timeframe candles for reliable analysis")
        return result to credits
    }'''
s=s[:start]+new_seed+s[end:]

s=s.replace('''private fun normalizePeriod(p:String)=when(p.trim().lowercase()){\"1\",\"1m\"->\"1m\";\"5\",\"5m\"->\"5m\";\"15\",\"15m\"->\"15m\";\"30\",\"30m\"->\"30m\";\"60\",\"1h\"->\"1h\";else->p.trim().lowercase()}''',
'''private fun normalizePeriod(p:String)=when(p.trim().lowercase()){\"1\",\"1m\"->\"1m\";\"5\",\"5m\"->\"5m\";\"10\",\"10m\"->\"10m\";\"15\",\"15m\"->\"15m\";\"30\",\"30m\"->\"30m\";\"60\",\"1h\"->\"1h\";else->p.trim().lowercase()}''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Analysis engine.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

# Do not stop the full engine just because volatility is high.
s=s.replace('if(c.size<100||isHighVolatility(c))return null','if(c.size<100)return null',1)

# Define a timeframe-aware volatility regime alongside ATR.
old='''        val close=c.map{it.c};val last=c.last();val prev=c[c.lastIndex-1];val a=atr(c,14).coerceAtLeast(1e-9)\n'''
new='''        val close=c.map{it.c};val last=c.last();val prev=c[c.lastIndex-1];val a=atr(c,14).coerceAtLeast(1e-9);val highVol=highVolForTimeframe(c,timeframe)\n'''
if old not in s: raise SystemExit('v41 ATR anchor not found')
s=s.replace(old,new,1)

# Timeframe-aware structure windows. Micro timeframes get more bars to reduce noise;
# higher timeframes use fewer candles because each candle already covers more market time.
old='''        val recent=c.takeLast(60);val local=c.takeLast(18).dropLast(1);val prior=c.takeLast(42).dropLast(4);val shortPrior=c.takeLast(16).dropLast(2)\n'''
new='''        val tfProfile=tfMinutes(timeframe)
        val recentN=when{tfProfile<=1->90;tfProfile<=5->72;tfProfile<=10->66;tfProfile<=15->60;tfProfile<=30->54;else->48}
        val localN=when{tfProfile<=1->24;tfProfile<=5->22;tfProfile<=10->20;tfProfile<=15->18;tfProfile<=30->16;else->15}
        val priorN=when{tfProfile<=1->52;tfProfile<=5->48;tfProfile<=10->45;tfProfile<=15->42;tfProfile<=30->38;else->34}
        val shortN=when{tfProfile<=1->20;tfProfile<=5->18;tfProfile<=10->17;tfProfile<=15->16;tfProfile<=30->15;else->14}
        val recent=c.takeLast(recentN);val local=c.takeLast(localN).dropLast(1);val prior=c.takeLast(priorN).dropLast(4);val shortPrior=c.takeLast(shortN).dropLast(2)
'''
if old not in s: raise SystemExit('v41 structure windows anchor not found')
s=s.replace(old,new,1)

# CHoCH sequence context should also differ by timeframe.
old='''        val before=c.takeLast(34).dropLast(3);val downSeq=before.takeLast(9).zipWithNext().count{it.second.c<it.first.c}>=5;val upSeq=before.takeLast(9).zipWithNext().count{it.second.c>it.first.c}>=5\n'''
new='''        val sequenceN=when{tfProfile<=1->42;tfProfile<=5->38;tfProfile<=10->36;tfProfile<=15->34;tfProfile<=30->30;else->28}
        val sequenceLeg=when{tfProfile<=5->10;tfProfile<=15->9;else->8}
        val before=c.takeLast(sequenceN).dropLast(3);val downSeq=before.takeLast(sequenceLeg).zipWithNext().count{it.second.c<it.first.c}>=sequenceLeg/2+1;val upSeq=before.takeLast(sequenceLeg).zipWithNext().count{it.second.c>it.first.c}>=sequenceLeg/2+1\n'''
if old not in s: raise SystemExit('v41 CHOCH window anchor not found')
s=s.replace(old,new,1)

# Make the v37 confluence gate stricter during abnormal expansion rather than
# returning before the full engine is evaluated.
old='''        val minDirectionalScore=when{tfm<=1->48;tfm<=5->46;tfm<=15->44;tfm<=30->43;else->42}\n        val minSeparation=when{tfm<=1->10;tfm<=5->9;tfm<=15->8;tfm<=30->8;else->7}\n'''
new='''        val minDirectionalScore=(when{tfm<=1->48;tfm<=5->46;tfm<=10->45;tfm<=15->44;tfm<=30->43;else->42})+(if(highVol)8 else 0)
        val minSeparation=(when{tfm<=1->10;tfm<=5->9;tfm<=10->9;tfm<=15->8;tfm<=30->8;else->7})+(if(highVol)4 else 0)
'''
if old not in s: raise SystemExit('v41 gate threshold anchor not found')
s=s.replace(old,new,1)

old='''        val bullConfluenceQualified=bullPillars>=4&&bull>=minDirectionalScore\n        val bearConfluenceQualified=bearPillars>=4&&bear>=minDirectionalScore\n        val bullValid=(bullFamilyQualified||bullConfluenceQualified)&&(bull-bear)>=minSeparation\n        val bearValid=(bearFamilyQualified||bearConfluenceQualified)&&(bear-bull)>=minSeparation\n'''
new='''        val requiredPillars=if(highVol)5 else 4
        val bullVolStructureOk=!highVol||((bullStructurePillar||bullLiquidityPillar)&&(bullMomentumPillar||bullImpulsePillar))
        val bearVolStructureOk=!highVol||((bearStructurePillar||bearLiquidityPillar)&&(bearMomentumPillar||bearImpulsePillar))
        val bullConfluenceQualified=bullPillars>=requiredPillars&&bull>=minDirectionalScore&&bullVolStructureOk
        val bearConfluenceQualified=bearPillars>=requiredPillars&&bear>=minDirectionalScore&&bearVolStructureOk
        val bullValid=(bullFamilyQualified||bullConfluenceQualified)&&bullVolStructureOk&&(bull-bear)>=minSeparation
        val bearValid=(bearFamilyQualified||bearConfluenceQualified)&&bearVolStructureOk&&(bear-bull)>=minSeparation
'''
if old not in s: raise SystemExit('v41 pillar gate anchor not found')
s=s.replace(old,new,1)

# Fix every v37 major S/R call to use directional levels that cannot cross.
s=s.replace('majorSupportResistance(c,a)','directionalMajorLevels(c,a,72)')

# Manual setup validation: volatility alone must not automatically expire a signal.
start=s.index('    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{')
end=s.index('\n    fun isHighVolatility',start)
new_check='''    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<60)return SetupCheck(true,"Waiting for enough fresh selected-timeframe data; time alone does not invalidate the signal.")
        val last=c.last();val close=c.map{it.c};val tf=tfMinutes(s.timeframe)
        val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val a=atr(c,14).coerceAtLeast(1e-9);val highVol=highVolForTimeframe(c,s.timeframe)
        val bars=when{tf<=1->22;tf<=5->20;tf<=10->19;tf<=15->18;tf<=30->17;else->16}
        val prior=c.takeLast((bars+2).coerceAtMost(c.size)).dropLast(1)
        val hi=prior.maxOf{it.h};val lo=prior.minOf{it.l}
        val majors=directionalMajorLevels(c,a,when{tf<=5->64;tf<=15->56;tf<=30->48;else->42});val support=majors.first;val resistance=majors.second
        var opposite=0;val why=mutableListOf<String>()
        if(s.direction=="BUY"){
            if(last.c<=s.sl)return SetupCheck(false,"BUY invalidated: selected-timeframe price closed through structural SL ${fmt(s.sl)}.")
            if(e20<e50){opposite++;why+="EMA20 below EMA50"};if(rr<43){opposite++;why+="RSI ${one(rr)}"};if(macd<0&&macd<macdPrev){opposite++;why+="MACD negative/falling"}
            if(last.c<lo-a*.04){opposite+=2;why+="bearish structure break below ${fmt(lo)}"};if(last.c<support-a*.14){opposite+=2;why+="major support ${fmt(support)} failed"}
        }else{
            if(last.c>=s.sl)return SetupCheck(false,"SELL invalidated: selected-timeframe price closed through structural SL ${fmt(s.sl)}.")
            if(e20>e50){opposite++;why+="EMA20 above EMA50"};if(rr>57){opposite++;why+="RSI ${one(rr)}"};if(macd>0&&macd>macdPrev){opposite++;why+="MACD positive/rising"}
            if(last.c>hi+a*.04){opposite+=2;why+="bullish structure break above ${fmt(hi)}"};if(last.c>resistance+a*.14){opposite+=2;why+="major resistance ${fmt(resistance)} failed"}
        }
        val ir=impulseRetracement(c,s.direction,a);if(ir?.reversalRisk==true){opposite+=2;why+="aggressive ${pct(ir.retracementRatio)} counter-retracement"}
        val invalidThreshold=if(highVol)6 else when{tf<=15->4;else->5}
        if(opposite>=invalidThreshold)return SetupCheck(false,"Original ${s.direction} setup is no longer valid: ${why.joinToString("; ")}.")
        val regime=if(highVol)"HIGH-VOLATILITY regime: setup has not structurally failed, but confirmation requirements are stricter" else "normal-volatility regime"
        return SetupCheck(true,"Original thesis remains structurally valid on ${s.timeframe} • $regime • EMA20 ${fmt(e20)} / EMA50 ${fmt(e50)} • RSI ${one(rr)} • major S/R ${fmt(support)} / ${fmt(resistance)}${ir?.let{" • retracement ${pct(it.retracementRatio)}, speed ${two(it.speedRatio)}x"}.orEmpty()}.")
    }'''
s=s[:start]+new_check+s[end:]

# Full diagnostic: never collapse volatility into one generic sentence.
start=s.index('    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{')
end=s.index('\n\n    private fun liquidityMap',start)
new_no='''    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{
        if(c.size<100)return "➜ NO TRADE • $symbol • $timeframe\\n➜ DATA: waiting for at least 100 independent $timeframe candles."
        val tf=tfMinutes(timeframe);val last=c.last();val prev=c[c.lastIndex-1];val close=c.map{it.c};val a=atr(c,14).coerceAtLeast(1e-9)
        val highVol=highVolForTimeframe(c,timeframe);val tr=max(last.h-last.l,max(abs(last.h-prev.c),abs(last.l-prev.c)));val trAtr=tr/a
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last();val s20=sma(close,20);val s50=sma(close,50);val rr=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val lookback=when{tf<=1->52;tf<=5->46;tf<=10->42;tf<=15->38;tf<=30->32;else->28}
        val prior=c.takeLast((lookback+2).coerceAtMost(c.size)).dropLast(1);val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l};val mid=(priorHigh+priorLow)/2
        val bosBull=last.c>priorHigh+a*.03;val bosBear=last.c<priorLow-a*.03
        val majors=directionalMajorLevels(c,a,when{tf<=1->80;tf<=5->72;tf<=10->64;tf<=15->58;tf<=30->50;else->42});val support=majors.first;val resistance=majors.second
        val lm=liquidityMap(c,a);val sweepBull=last.l<support-a*.03&&last.c>support;val sweepBear=last.h>resistance+a*.03&&last.c<resistance
        val divBull=bullishRsiDivergence(c);val divBear=bearishRsiDivergence(c)
        val bestIr=listOfNotNull(impulseRetracement(c,"BUY",a),impulseRetracement(c,"SELL",a)).maxByOrNull{it.continuationStrength}
        val trend=when{e20>e50&&s20>s50&&last.c>e150->"BULLISH";e20<e50&&s20<s50&&last.c<e150->"BEARISH";else->"MIXED / TRANSITION"}
        val structure=when{bosBull->"Bullish BOS above ${fmt(priorHigh)}";bosBear->"Bearish BOS below ${fmt(priorLow)}";sweepBull->"Sell-side sweep/reclaim around ${fmt(support)}";sweepBear->"Buy-side sweep/rejection around ${fmt(resistance)}";last.c>=mid->"Upper half of ${fmt(priorLow)}–${fmt(priorHigh)} structure; no confirmed external BOS";else->"Lower half of ${fmt(priorLow)}–${fmt(priorHigh)} structure; no confirmed external BOS"}
        val momentum=when{rr>=55&&macd>macdPrev->"Bullish pressure • RSI ${one(rr)} • MACD rising";rr<=45&&macd<macdPrev->"Bearish pressure • RSI ${one(rr)} • MACD falling";else->"Conflicted/neutral • RSI ${one(rr)} • MACD ${if(macd>macdPrev)"rising" else "falling"}"}
        val divergence=when{divBull->"Bullish RSI divergence";divBear->"Bearish RSI divergence";else->"No confirmed RSI divergence"}
        var fvgText="No nearby active FVG";val fw=c.takeLast(min(30,c.size));for(i in 2 until fw.size){if(fw[i].l>fw[i-2].h){val lo=fw[i-2].h;val hi=fw[i].l;if(abs(last.c-(lo+hi)/2)<=a*2.5)fvgText="Bullish FVG ${fmt(lo)}–${fmt(hi)}"};if(fw[i].h<fw[i-2].l){val lo=fw[i].h;val hi=fw[i-2].l;if(abs(last.c-(lo+hi)/2)<=a*2.5)fvgText="Bearish FVG ${fmt(lo)}–${fmt(hi)}"}}
        val bullOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c>it.o};val obText="Bull OB ${bullOb?.let{fmt((it.o+it.c)/2)}?:"-"} • Bear OB ${bearOb?.let{fmt((it.o+it.c)/2)}?:"-"}"
        val liqText="${lm.supports.size} support pool(s), ${lm.resistances.size} resistance pool(s) • directional major S/R ${fmt(support)} / ${fmt(resistance)}"
        val impulseText=bestIr?.let{"${it.direction} impulse • retracement ${pct(it.retracementRatio)} • speed ${two(it.speedRatio)}x • counter-body ${two(it.counterBodyRatio)}x${if(it.reversalRisk)" • reversal risk HIGH" else ""}"}?:"No clean impulse/retracement sequence"
        val profile=when{tf<=1->"1m microstructure";tf<=5->"5m intraday";tf<=10->"10m intraday bridge";tf<=15->"15m structure";tf<=30->"30m swing structure";else->"1h higher-timeframe structure"}
        val regime=if(highVol)"HIGH VOLATILITY / EXPANSION • current true range ${two(trAtr)} ATR" else if(trAtr<.55)"COMPRESSION • current true range ${two(trAtr)} ATR" else "NORMAL • current true range ${two(trAtr)} ATR"
        val waiting=when{
            highVol&&trend=="BULLISH"->"Volatility is expanded: require a defended sweep/reclaim or BOS + retest before BUY; do not chase the spike."
            highVol&&trend=="BEARISH"->"Volatility is expanded: require a rejected sweep or BOS + retest before SELL; do not chase the spike."
            highVol->"Volatility is expanded and direction is mixed: wait for external liquidity sweep + structural confirmation away from the range."
            trend=="BULLISH"&&!bosBull->"Need bullish BOS/CHoCH above ${fmt(priorHigh)} plus defended retest, liquidity reclaim, displacement or one of the qualified video-pattern confirmations."
            trend=="BEARISH"&&!bosBear->"Need bearish BOS/CHoCH below ${fmt(priorLow)} plus rejected retest, liquidity sweep, displacement or one of the qualified video-pattern confirmations."
            trend.startsWith("MIXED")->"Need directional separation from the current $timeframe structure; mid-range evidence conflicts."
            else->"Independent trend, structure, liquidity/zone, momentum and impulse pillars have not aligned strongly enough yet."
        }
        val tfRule=when{tf<=1->"1m: use more micro candles; demand fast displacement/reclaim because noise is highest.";tf<=5->"5m: prioritize intraday BOS/CHoCH + retest/liquidity reaction.";tf<=10->"10m: confirm the 5m noise into a cleaner two-candle structure before accepting continuation/reversal.";tf<=15->"15m: require structure + momentum agreement around a clear S/R/liquidity zone.";tf<=30->"30m: favor confirmed closes and major-level reactions; avoid mid-range entries.";else->"1h: prioritize higher-timeframe swing structure, major S/R and strong displacement/retest confirmation."}
        return buildString{
            append("➜ NO TRADE • $symbol • $timeframe • $profile\\n")
            append("➜ CANDLE: O ${fmt(last.o)} • H ${fmt(last.h)} • L ${fmt(last.l)} • C ${fmt(last.c)} • ATR ${fmt(a)}\\n")
            append("➜ REGIME: $regime\\n")
            append("➜ BIAS: $trend • EMA20 ${fmt(e20)} • EMA50 ${fmt(e50)} • SMA20 ${fmt(s20)} • SMA50 ${fmt(s50)}\\n")
            append("➜ STRUCTURE [$lookback $timeframe candles]: $structure\\n")
            append("➜ MAJOR S/R: support ${fmt(support)} • resistance ${fmt(resistance)}\\n")
            append("➜ MOMENTUM: $momentum\\n")
            append("➜ DIVERGENCE: $divergence\\n")
            append("➜ LIQUIDITY: $liqText\\n")
            append("➜ FVG: $fvgText\\n")
            append("➜ ORDER BLOCK: $obText\\n")
            append("➜ IMPULSE/RETRACE: $impulseText\\n")
            append("➜ WAITING FOR: $waiting\\n")
            append("➜ TIMEFRAME RULE: $tfRule")
        }
    }'''
s=s[:start]+new_no+s[end:]

# Add helpers before liquidityMap.
anchor='''    private fun liquidityMap(c:List<Candle>,a:Double):LiquidityMap{'''
helpers='''    private fun directionalMajorLevels(c:List<Candle>,a:Double,lookback:Int):Pair<Double,Double>{
        val last=c.last();val price=last.c;val w=c.takeLast(min(lookback,c.size));val lm=liquidityMap(c,a)
        val supportCandidates=mutableListOf<Double>();val resistanceCandidates=mutableListOf<Double>()
        supportCandidates+=w.map{it.l}.filter{it<=price};resistanceCandidates+=w.map{it.h}.filter{it>=price}
        supportCandidates+=lm.supports.map{it.price}.filter{it<=price};resistanceCandidates+=lm.resistances.map{it.price}.filter{it>=price}
        val support=supportCandidates.filter{it<price-a*.015}.maxOrNull()?:min(last.l,price-a*.05)
        val resistance=resistanceCandidates.filter{it>price+a*.015}.minOrNull()?:max(last.h,price+a*.05)
        return min(support,price) to max(resistance,price)
    }

    private fun highVolForTimeframe(c:List<Candle>,timeframe:String):Boolean{
        if(c.size<25)return false
        val base=atr(c.dropLast(1),14).coerceAtLeast(1e-9);val last=c.last();val prev=c[c.lastIndex-1]
        val tr=max(last.h-last.l,max(abs(last.h-prev.c),abs(last.l-prev.c)))
        val recent=c.takeLast(20).dropLast(1).map{it.h-it.l}.sorted();val med=recent[recent.size/2].coerceAtLeast(1e-9)
        val tf=tfMinutes(timeframe);val atrMult=when{tf<=1->2.85;tf<=5->2.70;tf<=10->2.65;tf<=15->2.60;tf<=30->2.50;else->2.40};val medMult=when{tf<=5->3.30;tf<=15->3.20;tf<=30->3.10;else->3.00}
        return tr>base*atrMult||tr>med*medMult
    }

'''
if anchor not in s: raise SystemExit('v41 helper anchor not found')
s=s.replace(anchor,helpers+anchor,1)

# 10m support in all timeframe switch logic.
s=s.replace('''private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"5m"->5;"15m"->15;"30m"->30;"1h"->60;else->15}''',
'''private fun tfMinutes(tf:String)=when(tf.lowercase(Locale.US)){"1m"->1;"5m"->5;"10m"->10;"15m"->15;"30m"->30;"1h"->60;else->15}''',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Main + floating UI: add 10m. Keep exactly ANALYZE + RE-EVALUATE.
# -----------------------------------------------------------------------------
for file in ['app/src/main/java/com/mh/analysis/MainActivityV29.kt','app/src/main/java/com/mh/analysis/OverlayService.kt']:
    p=Path(file);s=p.read_text();s=s.replace('arrayOf("1m","5m","15m","30m","1h")','arrayOf("1m","5m","10m","15m","30m","1h")');p.write_text(s)

# TradingView visual timeframe mapping.
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text();s=s.replace("if(p==='5m'||p==='5')return'5';if(p==='15m'||p==='15')return'15';","if(p==='5m'||p==='5')return'5';if(p==='10m'||p==='10')return'10';if(p==='15m'||p==='15')return'15';",1);p.write_text(s)

# Version.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 41',s);s=re.sub(r'versionName = "[^"]+"','versionName = "41.0"',s);p.write_text(s)
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt');s=p.read_text().replace('MS • v40 • ANALYZE + RE-EVALUATE','MS • v41 • TRUE TIMEFRAME ENGINE');p.write_text(s)

print('v41 true timeframe / volatility engine applied')
