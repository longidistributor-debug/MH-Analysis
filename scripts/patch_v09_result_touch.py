from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

s=s.replace('MH - V.08','MH - V.09')

chart_anchor='''            settings.javaScriptEnabled=true;settings.domStorageEnabled=true\n            setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;switchVisibleChart()}}'''
chart_repl='''            settings.javaScriptEnabled=true;settings.domStorageEnabled=true\n            setBackgroundColor(Color.rgb(19,23,34))\n            setOnTouchListener{v,e->\n                when(e.actionMasked){\n                    android.view.MotionEvent.ACTION_DOWN,\n                    android.view.MotionEvent.ACTION_MOVE,\n                    android.view.MotionEvent.ACTION_POINTER_DOWN -> v.parent?.requestDisallowInterceptTouchEvent(true)\n                    android.view.MotionEvent.ACTION_UP,\n                    android.view.MotionEvent.ACTION_CANCEL -> v.parent?.requestDisallowInterceptTouchEvent(false)\n                }\n                false\n            }\n            webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;switchVisibleChart()}}'''
if chart_anchor not in s: raise SystemExit('V09 chart touch anchor not found')
s=s.replace(chart_anchor,chart_repl,1)

old_no_signal='''                status.text="$title\\n\\n➜ DECISION\\n${result.decision}\\n\\n➜ MARKET CONTEXT\\n${marketContext()}"'''
new_no_signal='''                status.text="$title\\n\\n➜ DECISION\\n${compactDecision(result.decision)}\\n\\n${organizedContext()}"'''
if old_no_signal not in s: raise SystemExit('V09 no-signal result anchor not found')
s=s.replace(old_no_signal,new_no_signal,1)

start=s.find('    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){')
end=s.find('    private fun marketContext():String{', start)
if start == -1 or end == -1: raise SystemExit('V09 showSetup boundary not found')
new_show='''    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){
        if(a==null){status.text="$headline\\n\\n${organizedContext()}";showSignalCard(null);return}
        val s=a.signal
        val why=s.reasons.take(12).mapIndexed{i,r->"➜ ${i+1}. $r"}.joinToString("\\n")
        val analyzedAt=SimpleDateFormat("hh:mm:ss a",Locale.US).format(Date())
        val cleanNote=compactDecision(note).takeIf{it.isNotBlank()&& !it.startsWith("${s.direction} accepted")}
        status.text="""$headline
Analyzed at $analyzedAt

➜ SIGNAL
${s.direction} • ${s.score}/100 • ${a.state} • ${s.timeframe}

➜ LEVELS
Entry  ${price(s.entry)}
SL     ${price(s.sl)}
TP1    ${price(s.tp1)}
TP2    ${price(s.tp2)}

${organizedContext()}

➜ WHY THIS TRADE
${s.setupReason}

➜ CONFIRMATIONS / REASONS
$why${cleanNote?.let{"\\n\\n➜ DECISION NOTE\\n$it"}?:""}"""
        showSignalCard(a)
    }

    private fun compactDecision(raw:String):String{
        if(raw.isBlank())return "No fresh decision detail available."
        val contextPrefixes=listOf("True ","Execution quality:","Economic calendar:","HIGH IMPACT USD:","Adaptive calibration:","Professional quality:","Outcome stats:","Score breakdown:","Quality factors:")
        val kept=raw.lines().map{it.trim()}.filter{it.isNotBlank()}.filterNot{line->contextPrefixes.any{line.startsWith(it,true)}}
        return kept.distinct().take(4).joinToString("\\n").ifBlank{"No fresh directional setup passed the current quality gates."}
    }

    private fun organizedContext():String{
        val u=lastUnified?:return "➜ MARKET CONTEXT\\nWaiting for fresh manual analysis."
        return "➜ TRUE HTF\\n${u.htfSummary}\\n\\n➜ EXECUTION / NEWS\\n${u.executionSummary}\\n\\n➜ CALIBRATION\\n${u.calibrationSummary}"
    }

'''
s=s[:start]+new_show+s[end:]

p.write_text(s)

b=Path('app/build.gradle.kts')
x=b.read_text().replace('versionCode = 40','versionCode = 41').replace('versionName = "V.08"','versionName = "V.09"')
b.write_text(x)
print('V.09 organized results and chart touch isolation applied')
