from pathlib import Path

u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text()
m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
b=Path('app/build.gradle.kts').read_text()

required_u=[
    'val expectedBucket=(nowSec/tfSec)*tfSec',
    'val lagBars=(lagSec/tfSec).toInt()',
    'val hardStaleBars=if(btc)8 else 5',
    'Gold market is closed for the weekend',
    'Execution quality: $session • $lagText',
    'recent candle sequence has multiple timestamp gaps',
    'EconomicCalendarClient.risk(symbol)',
    'VideoTechniqueEngine.analyzeOrEnhance',
    'AdvancedMarketEngine.assess',
    'AdaptiveDecisionEngine.refine',
    'calibration(context,symbol,timeframe,current)'
]
for q in required_u:
    assert q in u, f'missing V11/preserved engine marker: {q}'
assert 'selected-timeframe market data is stale' not in u, 'old raw-seconds stale blocker still present'
assert 'ageSec>tfSec*2L+120L' not in u, 'old V10 hard cutoff still present'

# Reliable manual architecture stays at two provider history calls, no latest request.
manual=f[f.index('@Synchronized fun manualAnalysisPack'):f.index('/** V.02: legacy helpers')]
assert manual.count('fetchMarket(')==2, 'manual pack must contain exactly two provider history calls'
assert 'fetchLatest(' not in manual, 'manual pack must not restore unreliable third latest call'

for q in ['LEVELS: ON','LEVELS: OFF','MH - V.11','WhatsApp Support 24/7','ProQualityEngine']:
    assert q in m, f'missing V11 UI/preserved marker: {q}'
assert 'versionCode = 43' in b and 'versionName = "V.11"' in b

# Core indicator/reference implementation files must still exist.
for p in [
    'app/src/main/java/com/mh/analysis/AnalysisEngine.kt',
    'app/src/main/java/com/mh/analysis/VideoTechniqueEngine.kt',
    'app/src/main/java/com/mh/analysis/AdvancedMarketEngine.kt',
    'app/src/main/java/com/mh/analysis/AdaptiveDecisionEngine.kt',
    'app/src/main/java/com/mh/analysis/EconomicCalendarClient.kt',
    'app/src/main/java/com/mh/analysis/ProQualityEngine.kt'
]:
    assert Path(p).exists(), f'missing preserved component {p}'

print('V.11 validation passed: symbol-aware freshness, explicit levels state, two-call architecture and full analysis stack preserved')
