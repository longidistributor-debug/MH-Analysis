from pathlib import Path
p=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
s=p.read_text()
old='val req=Request.Builder().url(url).build()'
new='val req=Request.Builder().url(url).header("Origin","https://fcsapi.com").header("User-Agent","Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 Chrome/153 Mobile Safari/537.36").build()'
if old in s:
    s=s.replace(old,new,1)
elif 'header("Origin","https://fcsapi.com")' not in s:
    raise SystemExit('Missing native socket request target')
p.write_text(s)
