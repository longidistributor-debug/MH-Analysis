from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/AdvancedMarketEngine.kt')
s=p.read_text()
old='eqh,eql,fvg?.type,fvg?.low,fvg?.high,fvg?.fill,divText,'
new='eqh,eql,fvg?.type,fvg?.low,fvg?.high,fvg?.fill?:0,divText,'
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('V.01 AdvancedMarketEngine FVG compatibility anchor not found')
p.write_text(s)
print('V.01 compile compatibility fix applied')
