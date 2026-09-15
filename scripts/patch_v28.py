from pathlib import Path
p=Path('app/src/main/java/com/mh/analysis/MainActivityV24.kt')
s=p.read_text()
s=s.replace('MS • v27 • NATIVE WEBSOCKET LIVE ENGINE','MS • v28 • EXACT FCS WEBSOCKET TRANSPORT')
p.write_text(s)
