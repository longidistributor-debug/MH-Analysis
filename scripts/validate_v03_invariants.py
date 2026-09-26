from pathlib import Path

f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text()
m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
b=Path('app/build.gradle.kts').read_text()

assert 'private const val MANUAL_PREFS="mh_manual_pack_v03"' in f
assert 'mh_manual_pack_v02' in f and '.edit()?.clear()?.apply()' in f
assert 'reserveManualPack()' not in f
assert 'beginProviderWindowAfterFirstSuccess()' in f

start=f.index('@Synchronized fun manualAnalysisPack')
end=f.index('@Synchronized fun seedForPeriod', start)
manual=f[start:end]
assert manual.count('fetchMarket(')==2, manual.count('fetchMarket(')
assert manual.count('fetchLatest(')==1, manual.count('fetchLatest(')
first=manual.index('val selectedResult=fetchMarket')
window=manual.index('beginProviderWindowAfterFirstSuccess()')
second=manual.index('val htfResult=fetchMarket')
latest=manual.index('val quoteResult=fetchLatest')
assert first < window < second < latest
assert 'lastFailedAttemptCredits=credits' in manual

seed_start=f.index('@Synchronized fun seedForPeriod')
seed_end=f.index('@Synchronized fun previousDayRange', seed_start)
assert 'fetchMarket(' not in f[seed_start:seed_end]
history_start=f.index('@Synchronized fun history')
history_end=f.index('private fun putCache', history_start)
assert 'fetchMarket(' not in f[history_start:history_end]

assert 'MH - V.03' in m
assert 'assets.open("fcs_chart.html")' in m
assert 'tradingview_live.html' not in m
assert 'consumeFailedAttemptCredits()' in m
assert 'renderFcsChart(pack.selected)' in m
assert 'setSignalCard' in m

assert 'EconomicCalendarClient.risk(symbol)' in u
assert 'VideoTechniqueEngine.analyzeOrEnhance' in u
assert 'AdvancedMarketEngine.assess' in u
assert 'AdaptiveDecisionEngine.refine' in u
assert 'versionCode = 35' in b
assert 'versionName = "V.03"' in b

print('V.03 invariants OK: exact 3-call pack, transactional cooldown, FCS chart, analysis chain preserved')
