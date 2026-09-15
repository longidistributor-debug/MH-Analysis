from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

# Preserve all existing named setup families but add a multi-pillar fallback.
start=s.index('        val bullFamily=listOf(')
line_end=s.index('\n',start)+1
family_line=s[start:line_end]
end=s.index('        val win=if(dir=="BUY")',line_end)
new_gate=family_line+'''        val tfm=tfMinutes(timeframe)
        val minDirectionalScore=when{tfm<=1->48;tfm<=5->46;tfm<=15->44;tfm<=30->43;else->42}
        val minSeparation=when{tfm<=1->10;tfm<=5->9;tfm<=15->8;tfm<=30->8;else->7}
        val bullTrendPillar=listOf(e20>e50,s20>s50,last.c>e150,slopeBull).count{it}>=3
        val bearTrendPillar=listOf(e20<e50,s20<s50,last.c<e150,slopeBear).count{it}>=3
        val bullMomentumPillar=momentumBull||rsiBullDiv||displacementBull||pressureBull
        val bearMomentumPillar=momentumBear||rsiBearDiv||displacementBear||pressureBear
        val bullStructurePillar=bosBull||retestBull||chochBull||srFlipBull||bullLevelLadder||bullParticipantFamily
        val bearStructurePillar=bosBear||retestBear||chochBear||srFlipBear||bearLevelLadder||bearParticipantFamily
        val bullLiquidityPillar=stopHuntBull||fakeBull||liqSweepBull||multiTouchBull||bullLiquidityRoute
        val bearLiquidityPillar=stopHuntBear||fakeBear||liqSweepBear||multiTouchBear||bearLiquidityRoute
        val bullZonePillar=nearSupport||fvgBull||bullObMid!=null||bullPauseFamily||bullTrendlineFamily||bullWickFamily
        val bearZonePillar=nearResistance||fvgBear||bearObMid!=null||bearPauseFamily||bearTrendlineFamily||bearWickFamily
        val bullImpulsePillar=bullIR||bullWickFillFamily||pullbackBull
        val bearImpulsePillar=bearIR||bearWickFillFamily||pullbackBear
        val bullPillars=listOf(bullTrendPillar,bullMomentumPillar,bullStructurePillar,bullLiquidityPillar,bullZonePillar,bullImpulsePillar).count{it}
        val bearPillars=listOf(bearTrendPillar,bearMomentumPillar,bearStructurePillar,bearLiquidityPillar,bearZonePillar,bearImpulsePillar).count{it}
        val bullFamilyQualified=bullFamily>0&&bull>=minDirectionalScore
        val bearFamilyQualified=bearFamily>0&&bear>=minDirectionalScore
        val bullConfluenceQualified=bullPillars>=4&&bull>=minDirectionalScore
        val bearConfluenceQualified=bearPillars>=4&&bear>=minDirectionalScore
        val bullValid=(bullFamilyQualified||bullConfluenceQualified)&&(bull-bear)>=minSeparation
        val bearValid=(bearFamilyQualified||bearConfluenceQualified)&&(bear-bull)>=minSeparation
        if(!bullValid&&!bearValid)return null
        val dir=when{bullValid&&!bearValid->"BUY";bearValid&&!bullValid->"SELL";bull-bear>=minSeparation->"BUY";bear-bull>=minSeparation->"SELL";else->return null}
'''
s=s[:start]+new_gate+s[end:]

s=s.replace('else->"established trend pullback"}', 'else->"multi-factor confluence"}', 1)

old_setup='''        val setupReason="$dir $familyName. Best current setup family. Evidence: $strongest.$irText$liqText Pending entry uses $entrySource at ${fmt(entry)} outside the signal candle. Targets prefer the next opposing liquidity/structure level when available."\n'''
new_setup='''        val majorLevels=majorSupportResistance(c,a)\n        val setupReason="$dir $familyName on $timeframe. Evidence: $strongest.$irText$liqText Major support ${fmt(majorLevels.first)}, major resistance ${fmt(majorLevels.second)}. Pending entry uses $entrySource at ${fmt(entry)} outside the signal candle. Targets prefer the next opposing liquidity/structure level when available."\n'''
if old_setup not in s: raise SystemExit('v37 analysis setupReason anchor not found')
s=s.replace(old_setup,new_setup,1)

# Dynamic thesis validation: no fixed candle expiry.
start=s.index('    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{')
end=s.index('\n    fun isHighVolatility',start)
new_check='''    fun setupCheck(s:Signal,c:List<Candle>):SetupCheck{
        if(c.size<60)return SetupCheck(true,"Waiting for enough fresh data to validate the live thesis.")
        if(isHighVolatility(c))return SetupCheck(false,"Pending setup invalidated by abnormal live volatility / range expansion.")
        val last=c.last();val close=c.map{it.c};val tf=tfMinutes(s.timeframe)
        val e20=ema(close,20).last();val e50=ema(close,50).last();val rr=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val a=atr(c,14).coerceAtLeast(1e-9)
        val bars=when{tf<=1->14;tf<=5->16;tf<=15->18;tf<=30->20;else->24}
        val prior=c.takeLast((bars+2).coerceAtMost(c.size)).dropLast(1)
        val hi=prior.maxOf{it.h};val lo=prior.minOf{it.l}
        val majors=majorSupportResistance(c,a);val support=majors.first;val resistance=majors.second
        var opposite=0;val why=mutableListOf<String>()
        if(s.direction=="BUY"){
            if(last.c<=s.sl)return SetupCheck(false,"BUY invalidated: live price traded through the structural SL ${fmt(s.sl)}.")
            if(e20<e50){opposite++;why+="EMA20 crossed below EMA50"}
            if(rr<43){opposite++;why+="RSI weakened to ${one(rr)}"}
            if(macd<0&&macd<macdPrev){opposite++;why+="MACD is negative and falling"}
            if(last.c<lo-a*.04){opposite+=2;why+="bearish structure break below ${fmt(lo)}"}
            if(last.c<support-a*.18){opposite+=2;why+="major support ${fmt(support)} failed"}
        }else{
            if(last.c>=s.sl)return SetupCheck(false,"SELL invalidated: live price traded through the structural SL ${fmt(s.sl)}.")
            if(e20>e50){opposite++;why+="EMA20 crossed above EMA50"}
            if(rr>57){opposite++;why+="RSI strengthened to ${one(rr)}"}
            if(macd>0&&macd>macdPrev){opposite++;why+="MACD is positive and rising"}
            if(last.c>hi+a*.04){opposite+=2;why+="bullish structure break above ${fmt(hi)}"}
            if(last.c>resistance+a*.18){opposite+=2;why+="major resistance ${fmt(resistance)} failed"}
        }
        val ir=impulseRetracement(c,s.direction,a)
        if(ir?.reversalRisk==true){opposite+=2;why+="${pct(ir.retracementRatio)} aggressive counter-retracement damaged the impulse"}
        val invalidThreshold=when{tf<=5->4;tf<=15->4;tf<=30->5;else->5}
        if(opposite>=invalidThreshold)return SetupCheck(false,"Original ${s.direction} setup is no longer valid: ${why.joinToString("; ")}.")
        val live=mutableListOf<String>()
        live+="EMA20 ${fmt(e20)} / EMA50 ${fmt(e50)}";live+="RSI ${one(rr)}"
        ir?.let{live+="retracement ${pct(it.retracementRatio)}, speed ${two(it.speedRatio)}x"}
        live+="major S/R ${fmt(support)} / ${fmt(resistance)}"
        return SetupCheck(true,"Live thesis valid • ${live.joinToString(" • ")}.")
    }'''
s=s[:start]+new_check+s[end:]

# Detailed selected-timeframe diagnostic instead of a generic repeated sentence.
start=s.index('    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{')
end=s.index('\n\n    private fun liquidityMap',start)
new_no_signal='''    fun noSignalReason(symbol:String,timeframe:String,c:List<Candle>):String{
        if(c.size<100)return "➜ NO TRADE • $symbol • $timeframe\\n➜ DATA: waiting for enough selected-timeframe candle history."
        if(isHighVolatility(c))return "➜ NO TRADE • $symbol • $timeframe\\n➜ VOLATILITY: abnormal range expansion detected.\\n➜ ACTION: wait for structure to stabilize before accepting a new setup."
        val tf=tfMinutes(timeframe);val last=c.last();val close=c.map{it.c};val a=atr(c,14).coerceAtLeast(1e-9)
        val e20=ema(close,20).last();val e50=ema(close,50).last();val e150=ema(close,min(150,c.size-1)).last();val s20=sma(close,20);val s50=sma(close,50);val rr=rsi(close,14)
        val macd=ema(close,12).last()-ema(close,26).last();val macdPrev=ema(close.dropLast(1),12).last()-ema(close.dropLast(1),26).last()
        val lookback=when{tf<=1->18;tf<=5->22;tf<=15->28;tf<=30->34;else->42}
        val prior=c.takeLast((lookback+2).coerceAtMost(c.size)).dropLast(1);val priorHigh=prior.maxOf{it.h};val priorLow=prior.minOf{it.l}
        val bosBull=last.c>priorHigh+a*.03;val bosBear=last.c<priorLow-a*.03
        val majors=majorSupportResistance(c,a);val support=majors.first;val resistance=majors.second
        val lm=liquidityMap(c,a);val sweepBull=last.l<support-a*.03&&last.c>support;val sweepBear=last.h>resistance+a*.03&&last.c<resistance
        val divBull=bullishRsiDivergence(c);val divBear=bearishRsiDivergence(c)
        val bestIr=listOfNotNull(impulseRetracement(c,"BUY",a),impulseRetracement(c,"SELL",a)).maxByOrNull{it.continuationStrength}
        val trend=when{e20>e50&&s20>s50&&last.c>e150->"BULLISH";e20<e50&&s20<s50&&last.c<e150->"BEARISH";else->"MIXED / TRANSITION"}
        val structure=when{bosBull->"Bullish BOS confirmed above ${fmt(priorHigh)}";bosBear->"Bearish BOS confirmed below ${fmt(priorLow)}";sweepBull->"Sell-side liquidity swept at ${fmt(support)} and reclaimed";sweepBear->"Buy-side liquidity swept at ${fmt(resistance)} and rejected";last.c>(priorHigh+priorLow)/2->"Price is in upper half of ${fmt(priorLow)}–${fmt(priorHigh)} range; no clean BOS yet";else->"Price is in lower half of ${fmt(priorLow)}–${fmt(priorHigh)} range; no clean BOS yet"}
        val momentum=when{rr>=55&&macd>macdPrev->"Bullish pressure • RSI ${one(rr)} • MACD rising";rr<=45&&macd<macdPrev->"Bearish pressure • RSI ${one(rr)} • MACD falling";else->"Neutral/conflicted • RSI ${one(rr)} • MACD ${if(macd>macdPrev)"rising" else "falling"}"}
        val divergence=when{divBull->"Bullish RSI divergence detected";divBear->"Bearish RSI divergence detected";else->"No confirmed RSI divergence"}
        var fvgText="No active recent FVG near current price";val fw=c.takeLast(min(30,c.size))
        for(i in 2 until fw.size){if(fw[i].l>fw[i-2].h){val lo=fw[i-2].h;val hi=fw[i].l;if(abs(last.c-(lo+hi)/2)<=a*2.5)fvgText="Bullish FVG ${fmt(lo)}–${fmt(hi)}"};if(fw[i].h<fw[i-2].l){val lo=fw[i].h;val hi=fw[i-2].l;if(abs(last.c-(lo+hi)/2)<=a*2.5)fvgText="Bearish FVG ${fmt(lo)}–${fmt(hi)}"}}
        val bullOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c<it.o};val bearOb=c.takeLast(min(16,c.size)).dropLast(1).lastOrNull{it.c>it.o}
        val obText="Bull OB ${bullOb?.let{fmt((it.o+it.c)/2)}?:"-"} • Bear OB ${bearOb?.let{fmt((it.o+it.c)/2)}?:"-"}"
        val liqText=when{sweepBull->"Sell-side pool at ${fmt(support)} was swept/reclaimed";sweepBear->"Buy-side pool at ${fmt(resistance)} was swept/rejected";else->"${lm.supports.size} support liquidity pool(s), ${lm.resistances.size} resistance pool(s) • nearest major S/R ${fmt(support)} / ${fmt(resistance)}"}
        val impulseText=bestIr?.let{"${it.direction} impulse • retracement ${pct(it.retracementRatio)} • speed ${two(it.speedRatio)}x • counter-body ${two(it.counterBodyRatio)}x${if(it.reversalRisk)" • reversal risk HIGH" else ""}"}?:"No clean impulse/retracement sequence yet"
        val profile=when{tf<=1->"1m microstructure";tf<=5->"5m intraday";tf<=15->"15m structure";tf<=30->"30m structure";else->"1h higher-timeframe structure"}
        val waiting=when{trend=="BULLISH"&&!bosBull->"Need bullish BOS/CHoCH above ${fmt(priorHigh)} plus a defended retest, liquidity reclaim, or displacement confirmation.";trend=="BEARISH"&&!bosBear->"Need bearish BOS/CHoCH below ${fmt(priorLow)} plus a rejected retest, liquidity sweep, or displacement confirmation.";trend.startsWith("MIXED")->"Need directional separation: a confirmed BOS/CHoCH away from the range, then retest/liquidity confirmation. Current evidence conflicts.";bosBull&&rr<50->"Bullish break exists, but momentum has not confirmed it yet; wait for RSI/MACD recovery or a clean retest hold.";bosBear&&rr>50->"Bearish break exists, but momentum has not confirmed it yet; wait for RSI/MACD weakness or a clean retest rejection.";else->"The structure is developing, but independent trend + structure + liquidity/zone + momentum pillars have not aligned strongly enough yet."}
        val tfRule=when{tf<=1->"For 1m, require fast displacement plus immediate reclaim/retest because noise is high.";tf<=5->"For 5m, prioritize BOS/CHoCH + retest and liquidity reaction over a single indicator.";tf<=15->"For 15m, require structure and momentum agreement with a clear S/R or liquidity level.";tf<=30->"For 30m, favor confirmed structure closes and major-level reactions; avoid mid-range entries.";else->"For 1h, require higher-timeframe structure confirmation around major S/R; one intrabar move is not enough."}
        return buildString{append("➜ NO TRADE • $symbol • $timeframe • $profile\\n");append("➜ BIAS: $trend • EMA20 ${fmt(e20)} • EMA50 ${fmt(e50)} • SMA20 ${fmt(s20)} • SMA50 ${fmt(s50)}\\n");append("➜ STRUCTURE: $structure\\n");append("➜ MAJOR S/R: support ${fmt(support)} • resistance ${fmt(resistance)}\\n");append("➜ MOMENTUM: $momentum\\n");append("➜ DIVERGENCE: $divergence\\n");append("➜ LIQUIDITY: $liqText\\n");append("➜ FVG: $fvgText\\n");append("➜ ORDER BLOCK: $obText\\n");append("➜ IMPULSE/RETRACE: $impulseText\\n");append("➜ WAITING FOR: $waiting\\n");append("➜ TIMEFRAME RULE: $tfRule")}
    }'''
s=s[:start]+new_no_signal+s[end:]

anchor='''    private fun liquidityMap(c:List<Candle>,a:Double):LiquidityMap{'''
helper='''    private fun majorSupportResistance(c:List<Candle>,a:Double):Pair<Double,Double>{
        val raw=c.takeLast(min(96,c.size));val w=if(raw.size>2)raw.dropLast(1)else raw
        if(w.isEmpty()){val p=c.lastOrNull()?.c?:0.0;return p to p}
        val last=c.last().c;val lows=mutableListOf<Double>();val highs=mutableListOf<Double>()
        for(i in 2 until w.size-2){val x=w[i];if(x.l<=w[i-1].l&&x.l<=w[i-2].l&&x.l<=w[i+1].l&&x.l<=w[i+2].l)lows+=x.l;if(x.h>=w[i-1].h&&x.h>=w[i-2].h&&x.h>=w[i+1].h&&x.h>=w[i+2].h)highs+=x.h}
        val support=lows.filter{it<=last+a*.15}.maxOrNull()?:w.minOf{it.l};val resistance=highs.filter{it>=last-a*.15}.minOrNull()?:w.maxOf{it.h}
        return support to resistance
    }

'''
if anchor not in s: raise SystemExit('v37 analysis liquidityMap anchor not found')
s=s.replace(anchor,helper+anchor,1)
p.write_text(s)
print('v37 analysis engine patch applied')
