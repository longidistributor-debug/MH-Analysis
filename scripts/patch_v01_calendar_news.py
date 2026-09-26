from pathlib import Path

main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()
s=s.replace('super.onCreate(b);FcsClient.init(this)','super.onCreate(b);FcsClient.init(this);EconomicCalendarClient.init(this)',1)
s=s.replace('''        super.onResume()\n        LiveSocketHub.addListener(this)''','''        super.onResume()\n        EconomicCalendarClient.refreshIfStale()\n        LiveSocketHub.addListener(this)''',1)
s=s.replace('MS • V.01 • 3-CALL TRUE HTF ENGINE','MS • V.01 • 3-CALL + HIGH-IMPACT CALENDAR',1)
s=s.replace('TRADINGVIEW LIVE • MANUAL ANALYSIS USES 3 FCS CALLS','TRADINGVIEW LIVE • 3 FCS CALLS + FREE HIGH-IMPACT CALENDAR',1)
main.write_text(s)

u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt')
x=u.read_text()
old='''        val htf=htfView(higher,higherTimeframe)\n        val execution=execution(symbol,current,quote)\n        val calibration=calibration(context,symbol,timeframe,current)\n\n        if(execution.blocked){'''
new='''        val htf=htfView(higher,higherTimeframe)\n        val execution=execution(symbol,current,quote)\n        val calibration=calibration(context,symbol,timeframe,current)\n        val news=EconomicCalendarClient.risk(symbol)\n        val executionNewsSummary="${execution.summary}\\n${news.summary}"\n\n        if(news.blocked){\n            return Result(\n                null,\n                "EXECUTION BLOCKED: ${news.summary}",\n                htf.summary,\n                executionNewsSummary,\n                calibration.summary,\n                true\n            )\n        }\n\n        if(execution.blocked){'''
if old not in x: raise SystemExit('calendar anchor 1 not found')
x=x.replace(old,new,1)
x=x.replace('''                execution.summary,\n                calibration.summary,''','''                executionNewsSummary,\n                calibration.summary,''',1)
x=x.replace('''            val detail=listOf(adaptive.decision,htf.summary,execution.summary,calibration.summary).joinToString("\\n")\n            return Result(null,"NO SIGNAL\\n$detail",htf.summary,execution.summary,calibration.summary,false)''','''            val detail=listOf(adaptive.decision,htf.summary,executionNewsSummary,calibration.summary).joinToString("\\n")\n            return Result(null,"NO SIGNAL\\n$detail",htf.summary,executionNewsSummary,calibration.summary,false)''',1)
x=x.replace('''        val raw=candidate.score+htfDelta-execution.penalty+calibration.adjustment''','''        val raw=candidate.score+htfDelta-execution.penalty-news.penalty+calibration.adjustment''',1)
x=x.replace('''                "NO SIGNAL: $why.\\n${htf.summary}\\n${execution.summary}\\n${calibration.summary}",\n                htf.summary,execution.summary,calibration.summary,false''','''                "NO SIGNAL: $why.\\n${htf.summary}\\n${executionNewsSummary}\\n${calibration.summary}",\n                htf.summary,executionNewsSummary,calibration.summary,false''',1)
x=x.replace('''        extra+=execution.summary\n        extra+=calibration.summary''','''        extra+=execution.summary\n        extra+=news.summary\n        extra+=calibration.summary''',1)
x=x.replace('''        if(execution.penalty>0)extra+="Execution-quality score adjustment -${execution.penalty}"''','''        if(execution.penalty>0)extra+="Execution-quality score adjustment -${execution.penalty}"\n        if(news.penalty>0)extra+="High-impact calendar score adjustment -${news.penalty}"''',1)
x=x.replace('''            setupReason="${candidate.setupReason} True $higherTimeframe provider candles, execution quality and bounded calibration were included in the final decision.",\n            validityReason="${candidate.validityReason} True $higherTimeframe confirmation and execution quality must also remain acceptable."''','''            setupReason="${candidate.setupReason} True $higherTimeframe provider candles, execution quality, free high-impact economic calendar risk and bounded calibration were included in the final decision.",\n            validityReason="${candidate.validityReason} True $higherTimeframe confirmation, execution quality and high-impact calendar risk must also remain acceptable."''',1)
x=x.replace('''            htf.summary,execution.summary,calibration.summary,false''','''            htf.summary,executionNewsSummary,calibration.summary,false''',1)
u.write_text(x)

print('V.01 high-impact calendar/news scoring wired')
