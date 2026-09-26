from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

if 'private lateinit var analysisClock:TextView' not in s:
    s=s.replace('private lateinit var pairLabel:TextView\n', 'private lateinit var pairLabel:TextView\n    private lateinit var analysisClock:TextView\n    private val liveClockHandler=Handler(Looper.getMainLooper())\n    private var liveClockStarted=false\n')

s=s.replace('MH - V.05','MH - V.06')
anchor='''            addView(txt("MH - V.06",10f,true))\n'''
if 'WhatsApp Support 24/7' not in s and anchor in s:
    s=s.replace(anchor,anchor+'''            addView(txt("WhatsApp Support 24/7",11f,true,Color.rgb(37,211,102)).apply{\n                setPadding(0,dp(5),0,0)\n                setOnClickListener{ openWhatsAppSupport() }\n            })\n''',1)

s=s.replace('section("FCS MARKET CHART")','section("MARKET CHART")')
s=s.replace('FCS CHART','MARKET CHART')
s=s.replace('FCS calls:','API calls:')
s=s.replace('FCS PROVIDER COOLDOWN','DATA PROVIDER COOLDOWN')
s=s.replace('FCS PROVIDER WINDOW ACTIVE','DATA WINDOW ACTIVE')
s=s.replace('FCS REST','API')
s=s.replace('Cached/live FCS chart remains available.','Cached market chart remains available.')
s=s.replace('Fresh FCS history','Fresh market history')

root_anchor=''';sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)'''
if root_anchor in s and 'analysisClock=txt(' not in s:
    s=s.replace(root_anchor,''';sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)})\n        analysisClock=txt("",11f,true,Color.LTGRAY).apply{visibility=View.GONE;gravity=Gravity.CENTER_VERTICAL;setPadding(dp(12),dp(10),dp(12),0)}\n        sc.addView(analysisClock,LinearLayout.LayoutParams(-1,-2))\n        root.addView(sc)''',1)

s=s.replace('''                    renderFcsChart(pack.selected)\n                    performFreshAnalysis(result)''','''                    renderFcsChart(pack.selected)\n                    performFreshAnalysis(result)\n                    startLiveAnalysisClock()''',1)

old='''        val s=a.signal;val why=s.reasons.take(8).joinToString("\\n")\n        status.text="$headline • ${s.timeframe}\\n${s.direction} • ${s.score}/100 • ${a.state}\\nEntry ${price(s.entry)}   SL ${price(s.sl)}\\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\\n\\n${marketContext()}\\n\\nWHY THIS TRADE\\n${s.setupReason}\\n\\nCONFIRMATIONS\\n$why${if(note.isBlank())"" else "\\n\\n$note"}"'''
new='''        val s=a.signal\n        val why=s.reasons.take(10).mapIndexed{i,r->"➜ ${i+1}. $r"}.joinToString("\\n")\n        status.text="""$headline\n\n➜ SIGNAL\n${s.direction} • ${s.score}/100 • ${a.state} • ${s.timeframe}\n\n➜ LEVELS\nEntry  ${price(s.entry)}\nSL     ${price(s.sl)}\nTP1    ${price(s.tp1)}\nTP2    ${price(s.tp2)}\n\n➜ MARKET CONTEXT\n${marketContext()}\n\n➜ WHY THIS TRADE\n${s.setupReason}\n\n➜ CONFIRMATIONS / REASONS\n$why${if(note.isBlank())"" else "\\n\\n➜ DECISION NOTE\\n$note"}"""'''
if old not in s: raise SystemExit('showSetup anchor not found')
s=s.replace(old,new,1)
s=s.replace('''                status.text="$title\\n${result.decision}\\n\\n${marketContext()}"''','''                status.text="$title\\n\\n➜ DECISION\\n${result.decision}\\n\\n➜ MARKET CONTEXT\\n${marketContext()}"''')

method_anchor='''    private fun enableFloat(){'''
if 'private fun startLiveAnalysisClock()' not in s:
    s=s.replace(method_anchor,'''    private fun startLiveAnalysisClock(){\n        if(!::analysisClock.isInitialized)return\n        analysisClock.visibility=View.VISIBLE\n        if(liveClockStarted)return\n        liveClockStarted=true\n        val tick=object:Runnable{\n            override fun run(){\n                if(::analysisClock.isInitialized){\n                    val now=SimpleDateFormat("hh:mm:ss a",Locale.US).format(Date())\n                    analysisClock.text="● LIVE • $now"\n                    liveClockHandler.postDelayed(this,1000L)\n                }\n            }\n        }\n        liveClockHandler.post(tick)\n    }\n\n    private fun openWhatsAppSupport(){\n        val url="https://wa.me/923434824609"\n        runCatching{ startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(url))) }\n            .onFailure{ Toast.makeText(this,"WhatsApp is unavailable",Toast.LENGTH_SHORT).show() }\n    }\n\n'''+method_anchor,1)

p.write_text(s)

b=Path('app/build.gradle.kts')
x=b.read_text().replace('versionCode = 37','versionCode = 38').replace('versionName = "V.05"','versionName = "V.06"')
b.write_text(x)
print('V.06 UI/support/live-time patch applied')
