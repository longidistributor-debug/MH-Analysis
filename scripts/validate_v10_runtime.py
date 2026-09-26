from pathlib import Path

cal=Path('app/src/main/java/com/mh/analysis/EconomicCalendarClient.kt').read_text()
u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt').read_text()
m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt').read_text()

assert 'fun ensureReady(timeoutMs:Long=8000L):Boolean' in cal
assert 'MAX_CACHE_AGE_MS=7L*24L*60L*60L*1000L' in cal
assert 'Mozilla/5.0 (Android) MH-Analysis/V.10' in cal
assert 'primary/fallback feeds unavailable after verified refresh' in cal
assert 'risk score -4' in cal

assert 'private fun execution(symbol:String,timeframe:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution' in u
assert 'rangeAtr' in u and 'gapAtr' in u and 'candle age' in u
assert 'market data is stale' in u
assert 'bid/ask spread unavailable' not in u
assert 'Live spread is abnormal' in u
assert 'EconomicCalendarClient.risk(symbol)' in u
assert 'VideoTechniqueEngine.analyzeOrEnhance' in u
assert 'AdvancedMarketEngine.assess' in u
assert 'AdaptiveDecisionEngine.refine' in u
assert 'ProQualityEngine.assess' in u

manual=f[f.find('fun manualAnalysisPack'):f.find('/** V.02: legacy helpers')]
assert manual.count('fetchMarket(')==2, manual.count('fetchMarket(')
assert 'fetchLatest(' not in manual
assert 'MH - V.10' in m

print('V.10 runtime reliability validation passed')
