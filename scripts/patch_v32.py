from pathlib import Path
import re

main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

# Keep the public header clean: never mention build/version/video layers there.
s=re.sub(r';addView\(txt\("MS • v\d+ • [^"]+",10f,true\)\)', '', s)

old='''    private fun showSignalCard(a:ActiveSignal?){
        if(!chartReady)return
        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}
        val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)
        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }
'''
new='''    private fun showSignalCard(a:ActiveSignal?){
        if(!chartReady)return
        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}
        val s=a.signal
        val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)
        val bars=when(period.lowercase()){ "1m"->70;"5m"->48;"15m"->32;"30m"->30;else->28 }
        val basis=FcsClient.peek(symbol,period,220).orEmpty().takeLast(bars)
        if(basis.size>=5){
            val lo=basis.minOf{it.l};val hi=basis.maxOf{it.h};val spread=(hi-lo).coerceAtLeast(kotlin.math.abs(hi)*0.0005).coerceAtLeast(0.0001)
            j.put("viewLow",lo-spread*.06).put("viewHigh",hi+spread*.06)
        }
        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }
'''
if old not in s: raise SystemExit('MainActivity showSignalCard anchor not found')
s=s.replace(old,new,1)
main.write_text(s)

overlay=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
o=overlay.read_text()
old_o='''    private fun overlay(a:ActiveSignal?){if(a==null){chart?.evaluateJavascript("clearSignalCard()",null);return};val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score);chart?.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)}
'''
new_o='''    private fun overlay(a:ActiveSignal?){
        if(a==null){chart?.evaluateJavascript("clearSignalCard()",null);return}
        val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)
        val bars=when(period.lowercase()){ "1m"->70;"5m"->48;"15m"->32;"30m"->30;else->28 }
        val basis=FcsClient.peek(symbol,period,220).orEmpty().takeLast(bars)
        if(basis.size>=5){val lo=basis.minOf{it.l};val hi=basis.maxOf{it.h};val spread=(hi-lo).coerceAtLeast(kotlin.math.abs(hi)*0.0005).coerceAtLeast(0.0001);j.put("viewLow",lo-spread*.06).put("viewHigh",hi+spread*.06)}
        chart?.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }
'''
if old_o not in o: raise SystemExit('OverlayService overlay anchor not found')
o=o.replace(old_o,new_o,1)
overlay.write_text(o)

print('v32 clean TradingView signal guides patch applied')
