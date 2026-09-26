from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

s=s.replace('MH - V.06','MH - V.07')

# Remove V.06 bottom wall-clock UI completely.
s=s.replace('''    private lateinit var analysisClock:TextView\n    private val liveClockHandler=Handler(Looper.getMainLooper())\n    private var liveClockStarted=false\n''','')
s=s.replace('''        analysisClock=txt("",11f,true,Color.LTGRAY).apply{visibility=View.GONE;gravity=Gravity.CENTER_VERTICAL;setPadding(dp(12),dp(10),dp(12),0)}\n        sc.addView(analysisClock,LinearLayout.LayoutParams(-1,-2))\n''','')
s=s.replace('''                    performFreshAnalysis(result)\n                    startLiveAnalysisClock()''','''                    performFreshAnalysis(result)''')
clock_start=s.find('    private fun startLiveAnalysisClock(){')
wa_start=s.find('    private fun openWhatsAppSupport(){')
if clock_start != -1 and wa_start != -1 and wa_start > clock_start:
    s=s[:clock_start]+s[wa_start:]

# Single shared 1-second UI ticker.
if 'private val cooldownUiHandler=' not in s:
    anchor='    private lateinit var pairLabel:TextView\n'
    if anchor not in s: raise SystemExit('pairLabel field not found')
    s=s.replace(anchor,anchor+'''    private val cooldownUiHandler=Handler(Looper.getMainLooper())\n    private val cooldownUiTick=object:Runnable{\n        override fun run(){\n            updateCallLabel()\n            cooldownUiHandler.postDelayed(this,1000L)\n        }\n    }\n''',1)

# Patch lifecycle by ranges so previous socket-isolation edits do not break this patch.
resume_start=s.find('    override fun onResume(){')
pause_start=s.find('    override fun onPause(){')
socket_start=s.find('    override fun onSocketState', pause_start)
if resume_start == -1 or pause_start == -1 or socket_start == -1:
    raise SystemExit('lifecycle functions not found')
resume=s[resume_start:pause_start]
if 'cooldownUiHandler.post(cooldownUiTick)' not in resume:
    if 'updateCallLabel()' in resume:
        resume=resume.replace('updateCallLabel()','updateCallLabel()\n        cooldownUiHandler.removeCallbacks(cooldownUiTick)\n        cooldownUiHandler.post(cooldownUiTick)',1)
    else:
        resume=resume.rsplit('    }',1)[0]+'        cooldownUiHandler.removeCallbacks(cooldownUiTick)\n        cooldownUiHandler.post(cooldownUiTick)\n    }\n\n'
pause=s[pause_start:socket_start]
if 'cooldownUiHandler.removeCallbacks(cooldownUiTick)' not in pause:
    pause=pause.replace('    override fun onPause(){\n','    override fun onPause(){\n        cooldownUiHandler.removeCallbacks(cooldownUiTick)\n',1)
s=s[:resume_start]+resume+pause+s[socket_start:]

# Replace the whole label function. Both visible countdowns use the same value in the same tick.
u_start=s.find('    private fun updateCallLabel(){')
a_start=s.find('    private fun analyzeNow(){',u_start)
if u_start == -1 or a_start == -1:
    raise SystemExit('updateCallLabel/analyzeNow boundary not found')
new_update='''    private fun updateCallLabel(){\n        if(!::calls.isInitialized)return\n        val left=FcsClient.manualCooldownSeconds()\n        calls.text=if(left>0)"API calls: ${usage()}/500 • next analysis in ${left}s" else "API calls: ${usage()}/500 • READY"\n        if(::status.isInitialized && status.text.toString().startsWith("MANUAL ANALYSIS COOLDOWN")){\n            status.text=if(left>0)\n                "MANUAL ANALYSIS COOLDOWN\\nNext fresh analysis available in ${left}s.\\nNo extra API call was sent."\n            else\n                "ANALYSIS READY\\nYou can press NEW ANALYZE / RE-EVALUATE now."\n        }\n    }\n\n'''
s=s[:u_start]+new_update+s[a_start:]

p.write_text(s)

b=Path('app/build.gradle.kts')
x=b.read_text().replace('versionCode = 38','versionCode = 39').replace('versionName = "V.06"','versionName = "V.07"')
b.write_text(x)
print('V.07 synchronized cooldown UI patch applied')
