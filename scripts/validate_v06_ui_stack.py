from pathlib import Path

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text()
u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
v=Path('app/src/main/java/com/mh/analysis/VideoTechniqueEngine.kt').read_text()
b=Path('app/build.gradle.kts').read_text()

assert 'versionCode = 38' in b and 'versionName = "V.06"' in b
assert 'MH - V.06' in m
assert 'WhatsApp Support 24/7' in m and 'https://wa.me/923434824609' in m
assert 'startLiveAnalysisClock()' in m and '● LIVE • $now' in m
for heading in ['➜ SIGNAL','➜ LEVELS','➜ MARKET CONTEXT','➜ WHY THIS TRADE','➜ CONFIRMATIONS / REASONS']:
    assert heading in m, f'missing organized result heading: {heading}'

# No user-facing FCS branding in main-screen literals.
for text in ['FCS MARKET CHART','FCS CHART','FCS calls:','FCS PROVIDER COOLDOWN','FCS PROVIDER WINDOW ACTIVE']:
    assert text not in m, f'provider branding still visible: {text}'

# V.05 reliability invariant remains: exactly two provider history calls, no latest third call.
start=f.index('@Synchronized fun manualAnalysisPack')
end=f.index('/** V.02: legacy helpers',start)
body=f[start:end]
assert body.count('fetchMarket(')==2
assert 'fetchLatest(' not in body

# Preserve complete analysis pipeline requested previously.
for token in ['AnalysisEngine.analyze','VideoTechniqueEngine.analyzeOrEnhance','AdvancedMarketEngine.assess','AdaptiveDecisionEngine.refine','htfView','execution','calibration']:
    assert token in u, f'missing analysis stack: {token}'
for token in ['trend','wick','compression']:
    assert token.lower() in v.lower(), f'missing video-reference family: {token}'
assert 'Calendar' in ''.join(x.name for x in Path('app/src/main/java/com/mh/analysis').glob('*.kt')) or Path('scripts/patch_v01_calendar_news.py').exists()
assert 'setSignalCard' in m and 'renderFcsChart' in m
print('V.06 invariants OK: UI clean, live clock/support present, two-call pack and full analysis stack preserved')
