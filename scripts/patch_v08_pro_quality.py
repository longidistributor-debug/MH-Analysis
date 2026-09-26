from pathlib import Path

u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt')
x=u.read_text()

anchor='''        val calibration=calibration(context,symbol,timeframe,current)\n        val news=EconomicCalendarClient.risk(symbol)\n        val executionNewsSummary="${execution.summary}\\n${news.summary}"'''
repl='''        val calibration=calibration(context,symbol,timeframe,current)\n        val news=EconomicCalendarClient.risk(symbol)\n        val quality=ProQualityEngine.assess(context,symbol,timeframe,current,candidate)\n        val executionNewsSummary="${execution.summary}\\n${news.summary}"'''
if anchor not in x: raise SystemExit('V08 quality anchor not found')
x=x.replace(anchor,repl,1)

newsblock='''        if(news.blocked){\n            return Result('''
qualityblock='''        if(quality.blocked){\n            return Result(\n                null,\n                "NO SIGNAL: ${quality.summary}",\n                htf.summary,\n                executionNewsSummary,\n                "${calibration.summary}\\n${quality.stats}",\n                true\n            )\n        }\n\n        if(news.blocked){\n            return Result('''
if newsblock not in x: raise SystemExit('V08 block anchor not found')
x=x.replace(newsblock,qualityblock,1)

raw='''        val raw=candidate.score+htfDelta-execution.penalty-news.penalty+calibration.adjustment'''
newraw='''        val raw=candidate.score+htfDelta-execution.penalty-news.penalty+calibration.adjustment+quality.adjustment'''
if raw not in x: raise SystemExit('V08 raw score anchor not found')
x=x.replace(raw,newraw,1)

extra='''        extra+=calibration.summary\n        if(htfDelta!=0)extra+="True HTF score adjustment ${if(htfDelta>0)"+" else ""}$htfDelta"'''
newextra='''        extra+=calibration.summary\n        extra+=quality.summary\n        extra+=quality.stats\n        extra+=quality.invalidation\n        extra+="Score breakdown: Base ${candidate.score} | HTF ${signed(htfDelta)} | Execution -${execution.penalty} | News -${news.penalty} | Quality ${signed(quality.adjustment)} | Calibration ${signed(calibration.adjustment)}"\n        extra+="Quality factors: ${quality.breakdown}"\n        if(htfDelta!=0)extra+="True HTF score adjustment ${if(htfDelta>0)"+" else ""}$htfDelta"'''
if extra not in x: raise SystemExit('V08 extra anchor not found')
x=x.replace(extra,newextra,1)

reason='''            setupReason="${candidate.setupReason} True $higherTimeframe provider candles, execution quality, free high-impact economic calendar risk and bounded calibration were included in the final decision.",'''
newreason='''            setupReason="${candidate.setupReason} True $higherTimeframe provider candles, execution quality, economic-calendar risk, regime/conflict/data-quality/room-to-target checks and bounded calibration were included in the final decision.",'''
if reason not in x: raise SystemExit('V08 setup reason anchor not found')
x=x.replace(reason,newreason,1)

ret='''            "${final.direction} accepted • final evidence ${final.score}/100 • true HTF ${htf.direction} ${htf.strength}/100",'''
newret='''            "${final.direction} accepted • grade ${if(final.score>=90)"A+" else if(final.score>=84)"A" else if(final.score>=76)"B+" else "B"} • final evidence ${final.score}/100 • true HTF ${htf.direction} ${htf.strength}/100",'''
if ret not in x: raise SystemExit('V08 return anchor not found')
x=x.replace(ret,newret,1)
u.write_text(x)

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=m.read_text()
s=s.replace('MH - V.07','MH - V.08')
needle='''        val s=a.signal\n        val why=s.reasons.take(10).mapIndexed{i,r->"➜ ${i+1}. $r"}.joinToString("\\n")\n        status.text="""$headline'''
repl='''        val s=a.signal\n        val why=s.reasons.take(14).mapIndexed{i,r->"➜ ${i+1}. $r"}.joinToString("\\n")\n        val analyzedAt=SimpleDateFormat("hh:mm:ss a",Locale.US).format(Date())\n        status.text="""$headline\nAnalyzed at $analyzedAt'''
if needle not in s: raise SystemExit('V08 result UI anchor not found')
s=s.replace(needle,repl,1)
m.write_text(s)

b=Path('app/build.gradle.kts')
g=b.read_text().replace('versionCode = 39','versionCode = 40').replace('versionName = "V.07"','versionName = "V.08"')
b.write_text(g)
print('V.08 professional quality layer applied')
