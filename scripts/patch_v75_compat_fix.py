from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
anchor='''    private fun greenSections(text:String,headings:List<String>):CharSequence{\n'''
if 'private fun escapeHtml(x:String)=x' not in s:
    if anchor not in s:
        raise SystemExit('v75 compatibility anchor not found')
    s=s.replace(anchor,'    private fun escapeHtml(x:String)=x\n\n'+anchor,1)
p.write_text(s)
print('v75 compatibility helper applied')