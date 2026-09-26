from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Version label after V.06 patch.
s=s.replace('MH - V.06','MH - V.07')

# Remove the bottom live wall-clock UI introduced in V.06.
s=s.replace('''    private lateinit var analysisClock:TextView\n    private val liveClockHandler=Handler(Looper.getMainLooper())\n    private var liveClockStarted=false\n''','')
s=s.replace('''        analysisClock=txt("",11f,true,Color.LTGRAY).apply{visibility=View.GONE;gravity=Gravity.CENTER_VERTICAL;setPadding(dp(12),dp(10),dp(12),0)}\n        sc.addView(analysisClock,LinearLayout.LayoutParams(-1,-2))\n''','')
s=s.replace('''                    performFreshAnalysis(result)\n                    startLiveAnalysisClock()''','''                    performFreshAnalysis(result)''')

start=s.find('    private fun startLiveAnalysisClock(){')
end=s.find('    private fun openWhatsAppSupport(){')
if start != -1 and end != -1 and end > start:
    s=s[:start]+s[end:]

# Add one UI ticker that updates the cooldown everywhere from the same source every second.
if 'private val cooldownUiHandler=' not in s:
    s=s.replace('''    private lateinit var pairLabel:TextView\n''','''    private lateinit var pairLabel:TextView\n    private val cooldownUiHandler=Handler(Looper.getMainLooper())\n    private val cooldownUiTick=object:Runnable{\n        override fun run(){\n            updateCallLabel()\n            cooldownUiHandler.postDelayed(this,1000L)\n        }\n    }\n''',1)

old='''        updateCallLabel()\n    }\n\n    override fun onPause(){\n        LiveSocketHub.removeListener(this)\n        super.onPause()\n    }'''
new='''        updateCallLabel()\n        cooldownUiHandler.removeCallbacks(cooldownUiTick)\n        cooldownUiHandler.post(cooldownUiTick)\n    }\n\n    override fun onPause(){\n        cooldownUiHandler.removeCallbacks(cooldownUiTick)\n        LiveSocketHub.removeListener(this)\n        super.onPause()\n    }'''
if old not in s:
    raise SystemExit('V07 lifecycle timer anchor not found')
s=s.replace(old,new,1)

old='''    private fun updateCallLabel(){\n        if(!::calls.isInitialized)return\n        val left=FcsClient.manualCooldownSeconds()\n        calls.text=if(left>0)"API calls: ${usage()}/500 • next analysis in ${left}s" else "API calls: ${usage()}/500 • 2 calls per manual analysis • READY"\n    }'''
new='''    private fun updateCallLabel(){\n        if(!::calls.isInitialized)return\n        val left=FcsClient.manualCooldownSeconds()\n        calls.text=if(left>0)"API calls: ${usage()}/500 • next analysis in ${left}s" else "API calls: ${usage()}/500 • READY"\n        if(::status.isInitialized && status.text.toString().startsWith("MANUAL ANALYSIS COOLDOWN")){\n            status.text=if(left>0)\n                "MANUAL ANALYSIS COOLDOWN\\nNext fresh analysis available in ${left}s.\\nNo extra API call was sent."\n            else\n                "ANALYSIS READY\\nYou can press NEW ANALYZE / RE-EVALUATE now."\n        }\n    }'''
if old not in s:
    raise SystemExit('V07 updateCallLabel anchor not found')
s=s.replace(old,new,1)

p.write_text(s)

b=Path('app/build.gradle.kts')
x=b.read_text().replace('versionCode = 38','versionCode = 39').replace('versionName = "V.06"','versionName = "V.07"')
b.write_text(x)
print('V.07 synchronized cooldown UI patch applied')
