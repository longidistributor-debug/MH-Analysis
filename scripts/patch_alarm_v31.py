from pathlib import Path

main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()
s=s.replace(
    'SignalStore.acceptCandidate(this,s);startMonitorIfNeeded();showExisting()',
    'if(SignalStore.acceptCandidate(this,s)){AlarmStore.ensureArmed(this,s)};startMonitorIfNeeded();showExisting()'
)
main.write_text(s)

overlay=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
o=overlay.read_text()
o=o.replace(
    'if(dup==null)SignalStore.acceptCandidate(this,s);startMonitor();showState()',
    'if(dup==null&&SignalStore.acceptCandidate(this,s))AlarmStore.ensureArmed(this,s);startMonitor();showState()'
)
overlay.write_text(o)

print('v31 reliable alarm auto-arm patch applied')
