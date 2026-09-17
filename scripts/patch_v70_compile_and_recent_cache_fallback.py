from pathlib import Path
import re

# v70:
# - Fix v69 Kotlin compile conflict caused by duplicate rr1/rr2 declarations.
# - Keep v69 SL/TP geometry + exact reasons intact.
# - If a manual fresh request fails, allow analysis only from a genuinely recent
#   selected-timeframe cache; never analyze stale history.
# - Keep TradingView visual-only and all existing indicator/video/signal logic.

# -----------------------------------------------------------------------------
# AnalysisEngine compile fix: rename the v69 diagnostic R variables so they do
# not collide with the pre-existing rr1/rr2 declarations later in analyze().
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
old='''        val reward1=abs(tp1-entry);val reward2=abs(tp2-entry)\n        val rr1=reward1/risk.coerceAtLeast(1e-9);val rr2=reward2/risk.coerceAtLeast(1e-9)\n        // Do not publish geometry where the available reward is clearly too small\n        // relative to the structural risk.\n        if(rr1<.45||rr2<.90)return null'''
new='''        val reward1=abs(tp1-entry);val reward2=abs(tp2-entry)\n        val levelRr1=reward1/risk.coerceAtLeast(1e-9);val levelRr2=reward2/risk.coerceAtLeast(1e-9)\n        // Do not publish geometry where the available reward is clearly too small\n        // relative to the structural risk.\n        if(levelRr1<.45||levelRr2<.90)return null'''
if old not in s:
    raise SystemExit('v70 rr compile-fix anchor missing')
s=s.replace(old,new,1)
# Only the v69 explanatory strings before familyName use these diagnostics.
family_idx=s.index('        val familyName=', s.index('val levelRr1='))
head=s[:family_idx]
tail=s[family_idx:]
head=head.replace('${two(rr1)}R','${two(levelRr1)}R').replace('${two(rr2)}R','${two(levelRr2)}R')
s=head+tail
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: recent-cache fallback after manual fresh-request failure.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Replace the v66 fail-closed catch with a bounded selected-timeframe cache fallback.
old='''            }catch(e:Exception){runOnUiThread{\n                busy=false\n                status.text="FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN"\n            }}'''
new='''            }catch(e:Exception){runOnUiThread{\n                busy=false\n                if(reqSymbol!=symbol||reqPeriod!=period){status.text="MARKET CHANGED • press ANALYZE for $symbol $period";return@runOnUiThread}\n                val cached=FcsClient.peek(reqSymbol,reqPeriod,300).orEmpty()\n                val stepSec=when(reqPeriod.lowercase(java.util.Locale.US)){\n                    "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;\n                    "1h"->3600L;"2h"->7200L;"4h"->14400L;"5h"->18000L;\n                    "1d"->86400L;"1w"->604800L;else->900L\n                }\n                val newest=cached.lastOrNull()?.t?.let{if(it>9_999_999_999L)it/1000L else it}?:0L\n                val nowSec=System.currentTimeMillis()/1000L\n                val candleFresh=newest>0L && nowSec-newest<=stepSec*2L+300L\n                val cacheAge=FcsClient.cacheAgeMs(reqSymbol,reqPeriod)?:Long.MAX_VALUE\n                val cacheFresh=cacheAge<=stepSec*2000L+300_000L\n                if(cached.size>=60&&candleFresh&&cacheFresh){\n                    candles=cached.takeLast(300)\n                    status.text="RECENT MARKET DATA USED • FRESH REFRESH TEMPORARILY UNAVAILABLE"\n                    performAnalysis()\n                }else{\n                    status.text="FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN"\n                }\n            }}'''
if old not in s:
    # Be tolerant of later wording-neutralization variants.
    m=re.search(r'''\}\s*catch\(e:Exception\)\{runOnUiThread\{\s*busy=false\s*status\.text="FRESH ANALYSIS DATA UNAVAILABLE • TRY AGAIN"\s*\}\}''',s,re.S)
    if not m: raise SystemExit('v70 analyze catch anchor missing')
    s=s[:m.start()]+new+s[m.end():]
else:
    s=s.replace(old,new,1)

p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 70',g);g=re.sub(r'versionName = "[^"]+"','versionName = "70.0"',g);p.write_text(g)
print('v70 compile fix + bounded recent-cache fallback applied')
