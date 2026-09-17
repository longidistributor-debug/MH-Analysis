from pathlib import Path
import re

# v69:
# - Audit/fix SL/TP geometry without removing any setup/video-reference logic.
# - SL uses the NEAREST valid structural invalidation, not the farther extreme.
# - Trade sizing uses a robust recent-range basis so one volatility spike cannot
#   inflate every subsequent SL/TP for many bars.
# - TP2 can use farther liquidity only when it is INSIDE the normal TP2 cap;
#   it can no longer expand beyond the intended volatility objective.
# - Show exact SL/TP reasons and R-multiples in the detailed analysis output.
# - Keep backend/provider wording private and TradingView visual-only.

# -----------------------------------------------------------------------------
# AnalysisEngine: repair SL/TP sizing and write exact reasons into Signal fields.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()

start=s.index('        val tf=tfMinutes(timeframe);val maxRiskAtr=')
end=s.index('\n        val familyName=',start)
new_levels=r'''        val tf=tfMinutes(timeframe)
        val maxRiskAtr=when{tf<=1->.80;tf<=5->.95;tf<=15->1.08;tf<=30->1.22;else->1.38}

        // Robust trade-range basis. The normal ATR is still retained for the rest
        // of the analysis engine, but one exceptional candle must not force huge
        // SL/TP distances for the next 14 bars.
        val trWindow=c.takeLast(24)
        val trSamples=mutableListOf<Double>()
        for(i in 1 until trWindow.size){
            val x=trWindow[i];val pc=trWindow[i-1].c
            trSamples+=max(x.h-x.l,max(abs(x.h-pc),abs(x.l-pc)))
        }
        val trSorted=trSamples.filter{it.isFinite()&&it>0}.sorted()
        val medianTr=if(trSorted.isNotEmpty())trSorted[trSorted.size/2] else a
        val sizingAtr=min(a,medianTr*1.35).coerceAtLeast(1e-9)
        val spikeFiltered=sizingAtr<a*.90

        // Previous code used minOf() for BUY and maxOf() for SELL, which could
        // deliberately select the FARTHER structure and widen the SL. Select the
        // closest meaningful invalidation on the correct side of entry instead.
        val invalidationCandidates=mutableListOf<Pair<String,Double>>()
        if(dir=="BUY"){
            if(localLow<entry)invalidationCandidates+="local swing low" to localLow
            support?.takeIf{it.price<entry}?.let{invalidationCandidates+="nearest support/liquidity level" to it.price}
            if(priorLow<entry&&entry-priorLow<=sizingAtr*maxRiskAtr*1.15)invalidationCandidates+="recent structure low" to priorLow
        }else{
            if(localHigh>entry)invalidationCandidates+="local swing high" to localHigh
            resistance?.takeIf{it.price>entry}?.let{invalidationCandidates+="nearest resistance/liquidity level" to it.price}
            if(priorHigh>entry&&priorHigh-entry<=sizingAtr*maxRiskAtr*1.15)invalidationCandidates+="recent structure high" to priorHigh
        }
        val invalidation=if(dir=="BUY")invalidationCandidates.maxByOrNull{it.second}else invalidationCandidates.minByOrNull{it.second}
        val buffer=sizingAtr*.08
        val structureRisk=invalidation?.let{abs(entry-it.second)+buffer}
        val minRisk=sizingAtr*.32
        val maxRisk=sizingAtr*maxRiskAtr

        // If the closest real invalidation is still materially beyond the allowed
        // risk envelope, the trade geometry is poor: do not manufacture a wide SL.
        if(structureRisk!=null&&structureRisk>maxRisk*1.15)return null
        val rawRisk=structureRisk?:sizingAtr*.55
        val risk=rawRisk.coerceIn(minRisk,maxRisk)
        val sl=if(dir=="BUY")entry-risk else entry+risk

        val tp1Atr=when{tf<=1->.72;tf<=5->.90;tf<=15->1.05;tf<=30->1.18;else->1.35}
        val tp2Atr=when{tf<=1->1.02;tf<=5->1.25;tf<=15->1.50;tf<=30->1.70;else->1.95}
        val rawTp1=if(dir=="BUY")entry+sizingAtr*tp1Atr else entry-sizingAtr*tp1Atr
        val rawTp2=if(dir=="BUY")entry+sizingAtr*tp2Atr else entry-sizingAtr*tp2Atr

        val opposingLiquidity=if(dir=="BUY")lm.resistances.filter{it.price>entry+sizingAtr*.20}.minByOrNull{it.price}?.price else lm.supports.filter{it.price<entry-sizingAtr*.20}.maxByOrNull{it.price}?.price
        val nearest=if(dir=="BUY")listOfNotNull(localHigh,priorHigh,swingHigh,opposingLiquidity).filter{it>entry+sizingAtr*.20}.minOrNull() else listOfNotNull(localLow,priorLow,swingLow,opposingLiquidity).filter{it<entry-sizingAtr*.20}.maxOrNull()
        val tp1UsesStructure=nearest!=null&&if(dir=="BUY")nearest<rawTp1 else nearest>rawTp1
        val tp1=if(tp1UsesStructure)nearest!! else rawTp1

        val fartherLiquidity=if(dir=="BUY")lm.resistances.filter{it.price>tp1+sizingAtr*.12}.minByOrNull{it.price}?.price else lm.supports.filter{it.price<tp1-sizingAtr*.12}.maxByOrNull{it.price}?.price
        // Important fix: farther liquidity may shorten TP2, but it may not extend
        // TP2 beyond the normal volatility objective.
        val fartherInsideCap=fartherLiquidity?.takeIf{if(dir=="BUY")it>tp1&&it<=rawTp2 else it<tp1&&it>=rawTp2}
        val tp2=fartherInsideCap?:rawTp2

        val reward1=abs(tp1-entry);val reward2=abs(tp2-entry)
        val rr1=reward1/risk.coerceAtLeast(1e-9);val rr2=reward2/risk.coerceAtLeast(1e-9)
        // Do not publish geometry where the available reward is clearly too small
        // relative to the structural risk.
        if(rr1<.45||rr2<.90)return null

        val volNote=if(spikeFiltered)" Recent volatility spike was filtered for sizing (${fmt(a)} raw range → ${fmt(sizingAtr)} robust range)." else ""
        val slReason=if(invalidation!=null){
            val capped=if(rawRisk>maxRisk)" Risk was capped at ${two(maxRiskAtr)}x normal range." else if(rawRisk<minRisk)" A minimum noise buffer was applied." else ""
            "Nearest valid ${invalidation.first} is ${fmt(invalidation.second)}; SL adds a ${two(buffer)} buffer beyond that structure. Risk ${fmt(risk)} (${two(risk/sizingAtr)}x normal range).$capped$volNote"
        }else{
            "No closer confirmed invalidation level was available, so a controlled ${two(risk/sizingAtr)}x normal-range fallback was used. Risk ${fmt(risk)}.$volNote"
        }
        val tp1Reason=if(tp1UsesStructure){
            "TP1 is limited by the nearest opposing structure/liquidity at ${fmt(tp1)} instead of extending to the full ${two(tp1Atr)}x range target. Reward ${fmt(reward1)} = ${two(rr1)}R."
        }else{
            "No closer opposing structure blocks the first objective, so TP1 uses the ${two(tp1Atr)}x normal-range target. Reward ${fmt(reward1)} = ${two(rr1)}R.$volNote"
        }
        val tp2Reason=if(fartherInsideCap!=null){
            "TP2 uses the next opposing liquidity objective at ${fmt(tp2)}, which is inside the ${two(tp2Atr)}x maximum target envelope. Reward ${fmt(reward2)} = ${two(rr2)}R."
        }else{
            val ignored=if(fartherLiquidity!=null)" A farther liquidity level exists at ${fmt(fartherLiquidity)}, but it was ignored because it would make TP2 excessively distant." else ""
            "TP2 is capped at the ${two(tp2Atr)}x normal-range objective. Reward ${fmt(reward2)} = ${two(rr2)}R.$ignored$volNote"
        }'''
s=s[:start]+new_levels+s[end:]

old='''validity,"SL is behind live invalidation/liquidity structure and capped by ${two(maxRiskAtr)} ATR.","TP1 prefers the nearest opposing liquidity/structure level, bounded by ${two(tp1Atr)} ATR.","TP2 prefers the next liquidity objective, otherwise ${two(tp2Atr)} ATR.",setupReason)'''
new='''validity,slReason,tp1Reason,tp2Reason,setupReason)'''
if old not in s:
    raise SystemExit('v69 Signal reason constructor anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity detailed trade output: display the saved exact reasons.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
start=s.index('    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{')
end=s.index('\n    private fun showRecords()',start)
new_format=r'''    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{
        val sig=a.signal
        val matched=sig.reasons.map{it.trim()}.filter{it.isNotBlank()}.distinct().take(7)
        val raw=sig.setupReason.trim()
        val title=raw.substringBefore(". Evidence:").substringBefore(" Evidence:").trim().ifBlank{"Qualified ${sig.direction} setup on ${sig.timeframe}"}
        val risk=kotlin.math.abs(sig.entry-sig.sl).coerceAtLeast(1e-9)
        val r1=kotlin.math.abs(sig.tp1-sig.entry)/risk
        val r2=kotlin.math.abs(sig.tp2-sig.entry)/risk
        val out=StringBuilder()
        out.append("TRADE LEVELS\n")
        out.append("➜ ${sig.direction} • ${sig.score}/100 • ${a.state}\n")
        out.append("➜ ENTRY: ${price(sig.entry)}\n")
        out.append("➜ SL / INVALIDATION: ${price(sig.sl)}\n")
        out.append("➜ SL REASON: ${sig.slReason}\n")
        out.append("➜ TP1: ${price(sig.tp1)}\n")
        out.append("➜ TP1 REASON: ${sig.tp1Reason}\n")
        out.append("➜ TP2: ${price(sig.tp2)}\n")
        out.append("➜ TP2 REASON: ${sig.tp2Reason}\n")
        out.append("➜ RISK/REWARD: TP1 ${String.format(java.util.Locale.US,"%.2f",r1)}R • TP2 ${String.format(java.util.Locale.US,"%.2f",r2)}R\n\n")
        out.append("SETUP\n")
        out.append("➜ ").append(title).append("\n\n")
        out.append("MATCHED CONFIRMATIONS\n")
        if(matched.isEmpty())out.append("➜ Primary setup conditions matched.")
        else matched.forEach{out.append("➜ ").append(it).append("\n")}
        if(forcedConclusion!=null){out.append("\nRE-EVALUATION\n").append(arrowLines(forcedConclusion))}
        return out.toString().trim()
    }
'''
s=s[:start]+new_format+s[end:]

# One-time migration: old pending signals contain the pre-v69 level geometry and
# generic explanations, so do not keep showing them after this risk-engine fix.
anchor='        setContentView(buildUi())\n'
if 'v69_risk_geometry_migrated' not in s and anchor in s:
    s=s.replace(anchor,anchor+'''        if(!prefs.getBoolean("v69_risk_geometry_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD")
            prefs.edit().putBoolean("v69_risk_geometry_migrated",true).apply()
        }
''',1)

p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 69',g);g=re.sub(r'versionName = "[^"]+"','versionName = "69.0"',g);p.write_text(g)
print('v69 SL/TP geometry audit + exact reasons applied')
