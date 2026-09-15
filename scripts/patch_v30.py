from pathlib import Path
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
s=s.replace('MS • v29 • TRADINGVIEW LIVE','MS • v30 • TRADINGVIEW SIGNAL OVERLAY')
p.write_text(s)
