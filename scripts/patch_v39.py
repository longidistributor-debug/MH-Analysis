from pathlib import Path
import re

# v39: simplify the app to ANALYZE + RE-EVALUATE SIGNAL only.
# Alarm/records/background trade tracking are removed from the product flow.
# The full analysis engine remains intact; re-evaluation uses fresh candles,
# setupCheck, and a fresh full-engine analyze pass. No fixed candle expiry.

# -----------------------------------------------------------------------------
# AnalysisEngine: manual re-evaluation result driven by the existing full engine.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
if 'data class ReEvaluation' not in s:
    s=s.replace(
        '    data class SetupCheck(val valid:Boolean,val reason:String)\n',
        '    data class SetupCheck(val valid:Boolean,val reason:String)\n    data class ReEvaluation(val state:String,val reason:String,val freshSignal:Signal?=null)\n',
        1
    )

anchor='''    fun isHighVolatility'''
if 'fun reEvaluateSignal(' not in s:
    if anchor not in s: raise SystemExit('v39 AnalysisEngine insertion anchor not found')
    reevaluate='''    /** Manual re-evaluation of an already-issued signal.\n     * Time/candle count alone never invalidates a setup. We first test the\n     * original thesis, then run the complete current confluence engine again.\n     */\n    fun reEvaluateSignal(original:Signal,c:List<Candle>):ReEvaluation{\n        if(c.size<100)return ReEvaluation("WEAKENING","Not enough fresh selected-timeframe history to confirm the original setup. The signal is not auto-expired by time alone.")\n        val check=setupCheck(original,c)\n        if(!check.valid)return ReEvaluation("EXPIRED",check.reason)\n\n        val fresh=analyze(original.symbol,original.timeframe,c)\n        if(fresh==null){\n            return ReEvaluation(\n                "WEAKENING",\n                "The original thesis is not structurally broken, but the complete confluence engine no longer finds enough fresh alignment for a new confirmation. ${check.reason}"\n            )\n        }\n\n        val dominance=kotlin.math.abs(fresh.bullScore-fresh.bearScore)\n        if(fresh.direction!=original.direction){\n            val strongFlip=fresh.score>=maxOf(72,original.score-2)&&dominance>=10\n            return if(strongFlip){\n                ReEvaluation(\n                    "EXPIRED",\n                    "The original ${original.direction} setup is no longer the best market thesis. The full engine now confirms a materially stronger ${fresh.direction} setup (${fresh.score}/100, directional separation $dominance). Press ANALYZE to create the new signal.",\n                    fresh\n                )\n            }else{\n                ReEvaluation(\n                    "WEAKENING",\n                    "Opposite-direction evidence is developing, but it is not strong enough to fully invalidate the original setup yet. ${check.reason}",\n                    fresh\n                )\n            }\n        }\n\n        val same=sameSetup(original,fresh)\n        val acceptable=fresh.score>=maxOf(52,original.score-10)\n        return if(same||acceptable){\n            ReEvaluation(\n                "STILL VALID",\n                "The original ${original.direction} thesis remains aligned with the current full-engine view. Current confirmation is ${fresh.score}/100. ${check.reason}",\n                fresh\n            )\n        }else{\n            ReEvaluation(\n                "WEAKENING",\n                "Direction still agrees with the original ${original.direction} setup, but present confluence has weakened (${fresh.score}/100 versus original ${original.score}/100). ${check.reason}",\n                fresh\n            )\n        }\n    }\n\n'''
    s=s.replace(anchor,reevaluate+anchor,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# SignalStore: current signal only; no automatic alarm/record lifecycle.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()
start=s.index('    @Synchronized fun acceptCandidate(c:Context,candidate:Signal):Boolean{')
end=s.index('\n\n    fun evaluate(',start)
new_accept='''    @Synchronized fun acceptCandidate(c:Context,candidate:Signal):Boolean{\n        // ANALYZE explicitly creates/replaces the current selected-timeframe signal.\n        // There is no alarm, background trigger, win/loss record, or candle-count expiry.\n        val active=ActiveSignal(candidate,state="PENDING")\n        saveActive(c,active)\n        prefs(c).edit()\n            .putString("manual_reason_${candidate.id}","Fresh signal created from the complete selected-timeframe confluence engine. Re-evaluate manually whenever you want a fresh validity check.")\n            .remove("reason_${candidate.id}")\n            .remove("live_validity_${candidate.id}")\n            .remove("trigger_reason_${candidate.id}")\n            .apply()\n        return true\n    }\n\n    @Synchronized fun setManualState(c:Context,current:ActiveSignal,state:String,reason:String):ActiveSignal{\n        val next=current.copy(state=state)\n        saveActive(c,next);saveLast(c,next)\n        prefs(c).edit().putString("manual_reason_${current.signal.id}",reason).apply()\n        return next\n    }\n\n    fun manualReason(c:Context,signalId:String)=prefs(c).getString("manual_reason_$signalId","").orEmpty()\n\n    fun clearLegacyTracking(c:Context){\n        // Preserve current/last signal and API settings, remove only old tracking history.\n        prefs(c).edit().remove("records").remove("open_trades").apply()\n    }'''
s=s[:start]+new_accept+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivityV29: two-button workflow only.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Stop old product flow on launch/update; preserve current signal.
s=s.replace('''        showExisting()\n        maybeShowOldSetupPopup()\n        startMonitorIfNeeded()\n''','''        SignalStore.clearLegacyTracking(this)\n        AlarmStore.reset(this)\n        showExisting()\n''',1)
s=s.replace('showExisting();startMonitorIfNeeded();','showExisting();')
s=s.replace(';updateKeyUi();Toast.makeText(this,"Analysis key saved",Toast.LENGTH_SHORT).show();startMonitorIfNeeded()',';updateKeyUi();Toast.makeText(this,"Analysis key saved",Toast.LENGTH_SHORT).show()',1)

# Header/version.
s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v39 • ANALYZE + RE-EVALUATE',s,count=1)

# Replace three signal-control buttons with exactly two.
old='''        val br=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};br.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(4)});br.addView(actionButton("RECORDS",false){showRecords()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(2);rightMargin=dp(2)});br.addView(actionButton("ALARM",false){alarmAndShow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(4)});sc.addView(br,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)})\n'''
new='''        val br=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL}\n        br.addView(actionButton("ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(5)})\n        br.addView(actionButton("RE-EVALUATE SIGNAL",false){reEvaluateCurrent()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(5)})\n        sc.addView(br,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)})\n'''
if old not in s: raise SystemExit('v39 MainActivity button row anchor not found')
s=s.replace(old,new,1)
s=s.replace('NEW ANALYZE • reading current','ANALYZE • reading current',1)
s=s.replace('press NEW ANALYZE for','press ANALYZE for')

# Replace analysis acceptance policy and add manual re-evaluation.
start=s.index('    private fun performAnalysis(){')
end=s.index('\n\n    private fun currentDisplayedSignal()',start)
new_perform='''    private fun performAnalysis(){\n        if(candles.size<60){status.text="NOT ENOUGH MARKET HISTORY FOR RELIABLE ANALYSIS";return}\n        val candidate=AnalysisEngine.analyze(symbol,period,candles)\n        if(candidate==null){\n            status.text=AnalysisEngine.noSignalReason(symbol,period,candles)\n            showSignalCard(SignalStore.loadActive(this,symbol,period))\n            return\n        }\n        SignalStore.acceptCandidate(this,candidate)\n        val accepted=SignalStore.loadActive(this,symbol,period)\n        status.text=accepted?.let{formatManualSignal(it,"Fresh PENDING signal created. It will not auto-expire by candle count. Use RE-EVALUATE SIGNAL whenever you want to test its current validity.")}?:"SETUP ACCEPTED"\n        showSignalCard(accepted)\n    }\n\n    private fun reEvaluateCurrent(){\n        val current=SignalStore.loadActive(this,symbol,period)\n        if(current==null){status.text="NO CURRENT SIGNAL • press ANALYZE first";return}\n        if(current.state=="EXPIRED"){status.text=formatManualSignal(current,"This signal is already EXPIRED. Press ANALYZE when you want a fresh setup.");showSignalCard(current);return}\n        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}\n        if(busy){status.text="ANALYSIS REQUEST ALREADY RUNNING";return}\n        busy=true;val reqSymbol=symbol;val reqPeriod=period\n        status.text="RE-EVALUATING • reading fresh $reqSymbol $reqPeriod market structure…"\n        thread{\n            try{\n                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)\n                runOnUiThread{\n                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"\n                    if(reqSymbol!=symbol||reqPeriod!=period){status.text="MARKET CHANGED • re-evaluate again for $symbol $period";return@runOnUiThread}\n                    val latest=SignalStore.loadActive(this,reqSymbol,reqPeriod)\n                    if(latest==null||latest.signal.id!=current.signal.id){showExisting();return@runOnUiThread}\n                    val result=AnalysisEngine.reEvaluateSignal(latest.signal,out)\n                    val next=SignalStore.setManualState(this,latest,result.state,result.reason)\n                    status.text=formatManualSignal(next,result.reason)\n                    showSignalCard(next)\n                }\n            }catch(e:Exception){runOnUiThread{busy=false;status.text="RE-EVALUATION DATA UNAVAILABLE\\n${e.message}\\nThe saved signal was not auto-expired."}}\n        }\n    }'''
s=s[:start]+new_perform+s[end:]

# Only the active manually saved signal is displayed; old records/open trades are ignored.
s=s.replace('private fun currentDisplayedSignal()=SignalStore.displayState(this,symbol,period)','private fun currentDisplayedSignal()=SignalStore.loadActive(this,symbol,period)',1)

# Replace the old lifecycle-oriented signal text with manual validity text.
start=s.index('    private fun showExisting(){')
end=s.index('\n\n    private fun showRecords()',start)
new_show='''    private fun showExisting(){\n        if(!::status.isInitialized)return\n        val a=currentDisplayedSignal()\n        if(a==null){\n            status.text="➜ $symbol • $period\\n➜ Press ANALYZE for the best current setup.\\n➜ No alarm or background record tracking is active."\n            showSignalCard(null);return\n        }\n        status.text=formatManualSignal(a)\n        showSignalCard(a)\n    }\n\n    private fun arrowLines(text:String):String{\n        return text.replace("; ",". ").split(Regex("(?<=[.!?])\\\\s+|\\\\n+"))\n            .map{it.trim().trimEnd('.')}\n            .filter{it.isNotBlank()}\n            .joinToString("\\n"){"➜ $it"}\n    }\n\n    private fun formatManualSignal(a:ActiveSignal,forcedConclusion:String?=null):String{\n        val sig=a.signal\n        val out=StringBuilder()\n        out.append("➜ SIGNAL: ${sig.direction} • ${sig.score}/100\\n")\n        out.append("➜ STATUS: ${a.state}\\n")\n        out.append("➜ ENTRY: ${price(sig.entry)}\\n")\n        out.append("➜ SL: ${price(sig.sl)}\\n")\n        out.append("➜ TP1: ${price(sig.tp1)}\\n")\n        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")\n        out.append("WHY THIS TRADE\\n").append(arrowLines(sig.setupReason)).append("\\n\\n")\n        out.append("CONFIRMATIONS\\n")\n        sig.reasons.take(10).forEach{out.append("➜ ").append(it).append("\\n")}\n        val conclusion=forcedConclusion?:SignalStore.manualReason(this,sig.id).ifBlank{\n            when(a.state){\n                "PENDING"->"Signal is saved as PENDING. Time alone does not invalidate it; use RE-EVALUATE SIGNAL for a fresh full-market check."\n                "STILL VALID"->"Latest manual re-evaluation confirms the original setup is still valid."\n                "WEAKENING"->"Latest manual re-evaluation found weaker confluence; the setup is not fully invalid yet."\n                "EXPIRED"->"Latest manual re-evaluation invalidated the original setup. Press ANALYZE for a fresh setup when needed."\n                else->a.state\n            }\n        }\n        out.append("\\nRE-EVALUATION\\n").append(arrowLines(conclusion))\n        return out.toString()\n    }'''
s=s[:start]+new_show+s[end:]

p.write_text(s)

# -----------------------------------------------------------------------------
# Floating overlay: the same two-button manual workflow, no AlarmService.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
s=s.replace('overlay(SignalStore.displayState(this,symbol,period))','overlay(SignalStore.loadActive(this,symbol,period))',1)
s=s.replace('private fun displayed()=SignalStore.displayState(this,symbol,period)','private fun displayed()=SignalStore.loadActive(this,symbol,period)',1)

old='''        root.addView(Button(this).apply{text="NEW ANALYZE";setTextColor(Color.BLACK);setBackgroundColor(Color.WHITE);setOnClickListener{analyze()}},LinearLayout.LayoutParams(-1,dp(46)));status=tv("$symbol • $period",10.5f);root.addView(status)\n'''
new='''        val actions=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL}\n        actions.addView(Button(this).apply{text="ANALYZE";setTextColor(Color.BLACK);setBackgroundColor(Color.WHITE);setOnClickListener{analyze()}},LinearLayout.LayoutParams(0,dp(46),1f).apply{rightMargin=dp(4)})\n        actions.addView(Button(this).apply{text="RE-EVALUATE";setTextColor(Color.WHITE);setBackgroundColor(Color.rgb(35,35,35));setOnClickListener{reEvaluate()}},LinearLayout.LayoutParams(0,dp(46),1f).apply{leftMargin=dp(4)})\n        root.addView(actions,LinearLayout.LayoutParams(-1,dp(46)));status=tv("$symbol • $period",10.5f);root.addView(status)\n'''
if old not in s: raise SystemExit('v39 Overlay button anchor not found')
s=s.replace(old,new,1)

start=s.index('    private fun analyze(){')
end=s.index('    private fun showState(){',start)
new_methods='''    private fun analyze(){\n        if(busy)return\n        val key=prefs.getString("api_key","")?.trim().orEmpty();if(key.isBlank()){status?.text="Save analysis key in main app first";return}\n        busy=true;status?.text="Analyzing $symbol $period…";val s0=symbol;val p0=period\n        thread{runCatching{FcsClient.seedForPeriod(key,s0,p0,true)}.onSuccess{pair->Handler(Looper.getMainLooper()).post{\n            busy=false;if(symbol!=s0||period!=p0)return@post\n            val data=pair.first;if(data.size<60){status?.text="Not enough history";return@post}\n            val candidate=AnalysisEngine.analyze(symbol,period,data)\n            if(candidate==null){status?.text=AnalysisEngine.noSignalReason(symbol,period,data);overlay(displayed());return@post}\n            SignalStore.acceptCandidate(this,candidate);showState()\n        }}.onFailure{e->Handler(Looper.getMainLooper()).post{busy=false;status?.text="Analysis unavailable: ${e.message}"}}}\n    }\n\n    private fun reEvaluate(){\n        if(busy)return\n        val current=displayed()?:run{status?.text="No current signal • press ANALYZE first";return}\n        if(current.state=="EXPIRED"){status?.text="EXPIRED • press ANALYZE for a fresh setup";return}\n        val key=prefs.getString("api_key","")?.trim().orEmpty();if(key.isBlank()){status?.text="Save analysis key in main app first";return}\n        busy=true;status?.text="Re-evaluating $symbol $period…";val s0=symbol;val p0=period\n        thread{runCatching{FcsClient.seedForPeriod(key,s0,p0,true)}.onSuccess{pair->Handler(Looper.getMainLooper()).post{\n            busy=false;if(symbol!=s0||period!=p0)return@post\n            val latest=displayed();if(latest==null||latest.signal.id!=current.signal.id){showState();return@post}\n            val result=AnalysisEngine.reEvaluateSignal(latest.signal,pair.first)\n            SignalStore.setManualState(this,latest,result.state,result.reason);showState()\n        }}.onFailure{e->Handler(Looper.getMainLooper()).post{busy=false;status?.text="Re-evaluation unavailable: ${e.message}"}}}\n    }\n'''
s=s[:start]+new_methods+s[end:]

start=s.index('    private fun showState(){')
end=s.index('    private fun overlay(',start)
new_state='''    private fun showState(){\n        val a=displayed()\n        if(a==null){status?.text="$symbol • $period\\nPress ANALYZE for a setup";overlay(null);return}\n        val sig=a.signal;val reason=SignalStore.manualReason(this,sig.id)\n        status?.text="${sig.direction} ${sig.score}/100 • ${a.state}\\nEntry ${price(sig.entry)}  SL ${price(sig.sl)}  TP1 ${price(sig.tp1)}\\n${reason.take(220)}"\n        overlay(a)\n    }\n'''
s=s[:start]+new_state+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Manifest: remove alarm/background tracking registration and permissions.
# Keep OverlayService foreground support for the floating chart.
# -----------------------------------------------------------------------------
p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text()
for perm in [
    '    <uses-permission android:name="android.permission.VIBRATE" />\n',
    '    <uses-permission android:name="android.permission.WAKE_LOCK" />\n',
    '    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />\n'
]:
    s=s.replace(perm,'')
s=re.sub(r'\s*<receiver android:name="\.BootReceiver"[\s\S]*?</receiver>','',s,count=1)
s=s.replace('        <service android:name=".AlarmService" android:exported="false" />\n','')
p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 39',s);s=re.sub(r'versionName = "[^"]+"','versionName = "39.0"',s);p.write_text(s)

print('v39 manual analyze/re-evaluate workflow applied')
