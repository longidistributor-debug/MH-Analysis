from pathlib import Path

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
h=Path('app/src/main/assets/fcs_chart.html').read_text()
b=Path('app/build.gradle.kts').read_text()

checks={
    'version label':'MH - V.07' in m,
    'versionName':'versionName = "V.07"' in b,
    'versionCode':'versionCode = 39' in b,
    'no bottom live clock':'analysisClock' not in m and '● LIVE' not in m and 'startLiveAnalysisClock' not in m,
    'one-second cooldown ticker':'cooldownUiTick' in m and 'postDelayed(this,1000L)' in m,
    'top live countdown':'next analysis in ${left}s' in m,
    'status synced countdown':'Next fresh analysis available in ${left}s.' in m,
    'chart no FCS waiting':'FCS • waiting for data' not in h,
    'chart no FCS symbol prefix':"'FCS '+sym" not in h,
    'whatsapp support preserved':'WhatsApp Support 24/7' in m and '923434824609' in m,
    'two-call manual engine preserved':'manualAnalysisPack' in m,
    'unified engine preserved':'UnifiedAnalysisEngine.analyze' in m,
    'organized result preserved':'➜ SIGNAL' in m and '➜ CONFIRMATIONS / REASONS' in m,
}
failed=[k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('V.07 validation failed: '+', '.join(failed))
print('V.07 UI validation passed')
