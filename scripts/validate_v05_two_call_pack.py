from pathlib import Path

f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text()
m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
o=Path('app/src/main/java/com/mh/analysis/OverlayService.kt').read_text()
b=Path('app/build.gradle.kts').read_text()

start=f.index('@Synchronized fun manualAnalysisPack')
end=f.index('/** V.02: legacy helpers', start)
body=f[start:end]

assert body.count('fetchMarket(') == 2, f'expected exactly 2 fetchMarket calls, got {body.count("fetchMarket(")}'
assert 'fetchLatest(' not in body, 'third latest REST call must not exist in manualAnalysisPack'
assert 'MarketQuote(latest.c,null,null' in body, 'latest execution price must derive from selected-TF candle'

# Reject the concrete auto-start paths that caused provider-window interference.
assert 'savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start' not in m, 'main resume must not auto-start FCS socket'
assert 'updateKeyUi();LiveSocketHub.start(this,x)' not in m, 'saving the key must not start the FCS socket'
assert 'takeIf{it.isNotBlank()}?.let{LiveSocketHub.start' not in o, 'overlay must not auto-start FCS socket'
assert 'LiveSocketHub.stop()' in m, 'main activity must explicitly isolate provider window'
assert '1/2 selected timeframe • 2/2 true HTF' in m, 'UI must describe the two-call pack'
assert 'MH - V.05' in m, 'V.05 header missing'
assert 'versionCode = 37' in b and 'versionName = "V.05"' in b, 'V.05 version metadata missing'

# Existing analysis stack must still be intact.
u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
for token in ['AnalysisEngine.analyze','VideoTechniqueEngine.analyzeOrEnhance','AdvancedMarketEngine.assess','AdaptiveDecisionEngine.refine','htfView','execution','calibration']:
    assert token in u, f'missing preserved analysis component: {token}'

print('V.05 invariants OK: exactly 2 FCS REST calls, no third latest call, auto-socket paths disabled, full analysis chain preserved')
