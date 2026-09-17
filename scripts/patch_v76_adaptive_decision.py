from pathlib import Path
import re

main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

# Final adaptive gate after all existing structure/video/advanced analysis.
old='''        val assessment=AdvancedMarketEngine.assess(symbol,period,candles,enriched)\n        lastAssessment=assessment;lastMarketMap=assessment.map\n        val candidate=assessment.signal\n'''
new='''        val baseAssessment=AdvancedMarketEngine.assess(symbol,period,candles,enriched)\n        val assessment=AdaptiveDecisionEngine.refine(symbol,period,candles,baseAssessment)\n        lastAssessment=assessment;lastMarketMap=assessment.map\n        val candidate=assessment.signal\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'AdaptiveDecisionEngine.refine(symbol,period,candles,baseAssessment)' not in s:
    raise SystemExit('v76 main adaptive analysis anchor not found')

# Re-evaluation also passes through the adaptive dominance/structure check.
old='''                    val assessment=AdvancedMarketEngine.assess(symbol,period,data,enriched)\n                    lastAssessment=assessment;lastMarketMap=assessment.map\n                    val r=AdvancedMarketEngine.reevaluate(life,data,assessment.signal)\n                    showReEvaluation(life,r)\n'''
new='''                    val baseAssessment=AdvancedMarketEngine.assess(symbol,period,data,enriched)\n                    val assessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment)\n                    lastAssessment=assessment;lastMarketMap=assessment.map\n                    val r0=AdvancedMarketEngine.reevaluate(life,data,assessment.signal)\n                    val r=AdaptiveDecisionEngine.refineReEvaluation(life,data,r0,assessment)\n                    showReEvaluation(life,r)\n'''
if old in s:
    s=s.replace(old,new,1)
elif 'AdaptiveDecisionEngine.refineReEvaluation(life,data,r0,assessment)' not in s:
    raise SystemExit('v76 adaptive re-evaluation anchor not found')

# Surface opposing evidence in the market-map signal card.
old='''                append("\\n-> SL : ${price(x.sl)}")\n'''
new='''                append("\\n-> SL : ${price(x.sl)}")\n                append("\\n-> Adaptive evidence BUY ${x.bullScore} | SELL ${x.bearScore}")\n'''
if old in s:
    s=s.replace(old,new,1)

s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v76 • ADAPTIVE DECISION ENGINE',s,count=1)
main.write_text(s)

# Floating analyzer uses the same final decision logic; no separate/lower-quality signal path.
overlay=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
o=overlay.read_text()
old='''                val core=AnalysisEngine.analyze(symbol,period,data)\n                val fresh=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)\n'''
new='''                val core=AnalysisEngine.analyze(symbol,period,data)\n                val referenced=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)\n                val baseAssessment=AdvancedMarketEngine.assess(symbol,period,data,referenced)\n                val adaptiveAssessment=AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment)\n                val fresh=adaptiveAssessment.signal\n'''
if old in o:
    o=o.replace(old,new,1)
elif 'AdaptiveDecisionEngine.refine(symbol,period,data,baseAssessment)' not in o:
    raise SystemExit('v76 overlay adaptive anchor not found')
overlay.write_text(o)

build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 76',b);b=re.sub(r'versionName = "[^"]+"','versionName = "76.0"',b);build.write_text(b)
print('v76 adaptive percentile/conflict/structure decision layer applied')
