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

# Make LEVELS a real visible ON/OFF control and make long-press crosshair tolerant
# of normal finger jitter while keeping pan/zoom local to the chart.
h=Path('app/src/main/assets/fcs_chart.html')
z=h.read_text()
z=z.replace('.tool{font-size:9px;font-weight:700;color:#d9dde5;background:rgba(8,11,17,.82);border:1px solid rgba(255,255,255,.14);padding:6px 8px;border-radius:6px}', '.tool{font-size:9px;font-weight:700;color:#d9dde5;background:rgba(8,11,17,.82);border:1px solid rgba(255,255,255,.14);padding:6px 8px;border-radius:6px}.tool.active{color:#111;background:#f2c94c;border-color:#f2c94c}')
z=z.replace('<div class="tool" onclick="toggleLevels()">LEVELS</div>', '<div id="levelsBtn" class="tool active" onclick="toggleLevels()">LEVELS ON</div>')
z=z.replace("function clearSignalCard(){signal=null;renderCard();draw()}function toggleLevels(){showLevels=!showLevels;draw()}", "function clearSignalCard(){signal=null;renderCard();draw()}function syncLevelsButton(){const b=document.getElementById('levelsBtn');if(!b)return;b.textContent=showLevels?'LEVELS ON':'LEVELS OFF';b.classList.toggle('active',showLevels)}function toggleLevels(){showLevels=!showLevels;syncLevelsButton();renderCard();draw()}")
z=z.replace("e.innerHTML='<b>'+String(signal.direction||'SETUP')+' • '+String(signal.state||'')+' • '+String(signal.score||'-')+'/100</b><div class=\"row\"><span class=\"dot entry\"></span>ENTRY '+fmt(signal.entry)+'</div><div class=\"row\"><span class=\"dot sl\"></span>SL '+fmt(signal.sl)+'</div><div class=\"row\"><span class=\"dot tp1\"></span>TP1 '+fmt(signal.tp1)+'</div><div class=\"row\"><span class=\"dot tp2\"></span>TP2 '+fmt(signal.tp2)+'</div>';e.style.display='block'", "if(!showLevels){e.style.display='none';e.innerHTML='';return}e.innerHTML='<b>'+String(signal.direction||'SETUP')+' • '+String(signal.state||'')+' • '+String(signal.score||'-')+'/100</b><div class=\"row\"><span class=\"dot entry\"></span>ENTRY '+fmt(signal.entry)+'</div><div class=\"row\"><span class=\"dot sl\"></span>SL '+fmt(signal.sl)+'</div><div class=\"row\"><span class=\"dot tp1\"></span>TP1 '+fmt(signal.tp1)+'</div><div class=\"row\"><span class=\"dot tp2\"></span>TP2 '+fmt(signal.tp2)+'</div>';e.style.display='block'")
z=z.replace("let drag=false,lastX=0,pinchDist=0,longTimer=null,moved=false;", "let drag=false,lastX=0,pinchDist=0,longTimer=null,moved=false,startX=0,startY=0;")
old_touch="""cv.addEventListener('touchstart',e=>{e.preventDefault();moved=false;if(e.touches.length===2){pinchDist=dist(e.touches[0],e.touches[1]);clearTimeout(longTimer);return}drag=true;lastX=e.touches[0].clientX;const x=e.touches[0].clientX,y=e.touches[0].clientY;longTimer=setTimeout(()=>{cross={x,y};drag=false;draw()},520)},{passive:false});
cv.addEventListener('touchmove',e=>{e.preventDefault();moved=true;clearTimeout(longTimer);if(e.touches.length===2){const d=dist(e.touches[0],e.touches[1]);if(pinchDist>0){const factor=pinchDist/d;visibleCount=Math.max(20,Math.min(candles.length||180,visibleCount*factor));pinchDist=d;draw()}return}if(drag&&e.touches.length===1){const x=e.touches[0].clientX,dx=x-lastX;lastX=x;const data=viewData(),pw=Math.max(1,cv.clientWidth-58),step=pw/Math.max(1,data.length);offset+=-dx/step;draw()}if(cross&&e.touches.length===1){cross={x:e.touches[0].clientX,y:e.touches[0].clientY};draw()}},{passive:false});
cv.addEventListener('touchend',e=>{clearTimeout(longTimer);drag=false;pinchDist=0},{passive:false});"""
new_touch="""cv.addEventListener('touchstart',e=>{e.preventDefault();moved=false;if(e.touches.length===2){pinchDist=dist(e.touches[0],e.touches[1]);clearTimeout(longTimer);return}drag=true;lastX=e.touches[0].clientX;startX=lastX;startY=e.touches[0].clientY;const x=startX,y=startY;longTimer=setTimeout(()=>{cross={x,y};drag=false;draw()},480)},{passive:false});
cv.addEventListener('touchmove',e=>{e.preventDefault();if(e.touches.length===2){moved=true;clearTimeout(longTimer);const d=dist(e.touches[0],e.touches[1]);if(pinchDist>0){const factor=pinchDist/d;visibleCount=Math.max(20,Math.min(candles.length||180,visibleCount*factor));pinchDist=d;draw()}return}if(e.touches.length!==1)return;const x=e.touches[0].clientX,y=e.touches[0].clientY;if(cross){cross={x,y};draw();return}const travel=Math.hypot(x-startX,y-startY);if(travel>8){moved=true;clearTimeout(longTimer)}if(drag&&travel>4){const dx=x-lastX;lastX=x;const data=viewData(),pw=Math.max(1,cv.clientWidth-58),step=pw/Math.max(1,data.length);offset+=-dx/step;draw()}},{passive:false});
cv.addEventListener('touchend',e=>{clearTimeout(longTimer);drag=false;pinchDist=0},{passive:false});cv.addEventListener('touchcancel',e=>{clearTimeout(longTimer);drag=false;pinchDist=0},{passive:false});"""
if old_touch not in z: raise SystemExit('V09 chart gesture anchor not found')
z=z.replace(old_touch,new_touch,1)
z=z.replace("window.addEventListener('resize',resize);setTimeout(resize,0);", "window.addEventListener('resize',resize);syncLevelsButton();setTimeout(resize,0);")
h.write_text(z)

b=Path('app/build.gradle.kts')
x=b.read_text().replace('versionCode = 40','versionCode = 41').replace('versionName = "V.08"','versionName = "V.09"')
b.write_text(x)
print('V.09 organized results, levels toggle and chart touch isolation applied')
