from pathlib import Path
import re

# v72 is the only build-time patch. It connects the permanently committed
# VideoTechniqueEngine to both main and floating analysis flows and updates version text.

main = Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s = main.read_text()
old = '''        val raw=AnalysisEngine.analyze(symbol,period,candles)\n        val candidate=raw?.let{applyPreviousDayContext(it)}\n'''
new = '''        val core=AnalysisEngine.analyze(symbol,period,candles)\n        val raw=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,candles,core)\n        val candidate=raw?.let{applyPreviousDayContext(it)}\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'VideoTechniqueEngine.analyzeOrEnhance(symbol,period,candles,core)' not in s:
    raise SystemExit('v72 main analysis anchor not found')
s = re.sub(r'MS • v\d+ • [^"\n]+', 'MS • v72 • FRESH MULTI-TECHNIQUE ENGINE', s, count=1)
main.write_text(s)

overlay = Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s = overlay.read_text()
old = '''                val fresh=AnalysisEngine.analyze(symbol,period,data)\n'''
new = '''                val core=AnalysisEngine.analyze(symbol,period,data)\n                val fresh=VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'VideoTechniqueEngine.analyzeOrEnhance(symbol,period,data,core)' not in s:
    raise SystemExit('v72 overlay analysis anchor not found')
overlay.write_text(s)

build = Path('app/build.gradle.kts')
s = build.read_text()
s = re.sub(r'versionCode = \d+', 'versionCode = 72', s)
s = re.sub(r'versionName = "[^"]+"', 'versionName = "72.0"', s)
build.write_text(s)

print('v72 fresh multi-technique source integration applied')
