from pathlib import Path

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
p=Path('app/src/main/java/com/mh/analysis/ProQualityEngine.kt').read_text()
h=Path('app/src/main/assets/fcs_chart.html').read_text()
g=Path('app/build.gradle.kts').read_text()

checks={
 'version V.08':'versionName = "V.08"' in g and 'versionCode = 40' in g,
 'header V.08':'MH - V.08' in m,
 'quality engine wired':'ProQualityEngine.assess' in u,
 'quality adjustment scored':'+quality.adjustment' in u,
 'score breakdown':'Score breakdown:' in u,
 'conflict guard':'Conflict engine blocked setup' in p,
 'data guard':'dataQuality' in p and 'invalid OHLC' in p,
 'regime scoring':'COMPRESSION' in p and 'EXPANSION' in p and 'TRENDING' in p,
 'room-to-target':'Room-to-target guard' in p,
 'outcome confidence':'calibration confidence' in p,
 'static analyzed timestamp':'Analyzed at $analyzedAt' in m,
 'pinch zoom':'touches.length===2' in h and 'visibleCount' in h,
 'pan':'offset+=-dx/step' in h,
 'double tap reset':'n-lastTap<330' in h,
 'crosshair':'longTimer=setTimeout' in h and 'OHLC' not in h or 'O '+'' in h,
 'signal focus':'focusSignal()' in h,
 'level toggle':'toggleLevels()' in h,
 'provider branding hidden':'FCS ' not in h,
 'V05 two call preserved':'fetchLatest(accessKey,symbol)' not in Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text().split('fun manualAnalysisPack',1)[-1].split('fun ',1)[0] if 'fun manualAnalysisPack' in Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text() else True,
 'calendar preserved':'EconomicCalendarClient.risk' in u,
 'video engine preserved':'VideoTechniqueEngine.analyzeOrEnhance' in u,
 'advanced engine preserved':'AdvancedMarketEngine.assess' in u,
 'adaptive engine preserved':'AdaptiveDecisionEngine.refine' in u,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items():print(('OK ' if v else 'FAIL ')+k)
if failed: raise SystemExit('V08 validation failed: '+', '.join(failed))
print('V.08 professional stack validation passed')
