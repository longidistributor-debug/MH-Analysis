from pathlib import Path
import re

# SignalStore: re-evaluate current pending signal continuously against the same
# analysis engine. A stronger new structure expires the old pending setup but
# does not auto-create a new trade; NEW ANALYZE remains explicit.
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()
start=s.index('    @Synchronized fun evaluateLiveStructure(')
end=s.index('\n\n    fun liveValidityReason',start)
new_eval='''    @Synchronized fun evaluateLiveStructure(c:Context,symbol:String,timeframe:String,candles:List<Candle>,at:Long=System.currentTimeMillis()):List<ProcessEvent>{
        val active=loadActive(c,symbol,timeframe)?:return emptyList()
        if(active.state!="PENDING"||candles.size<60)return emptyList()
        val check=AnalysisEngine.setupCheck(active.signal,candles)
        prefs(c).edit().putString("live_validity_${active.signal.id}",check.reason).apply()
        if(!check.valid){
            val done=expirePending(c,active,check.reason,at)
            return listOf(ProcessEvent(done.signal,"EXPIRED",at))
        }
        val candidate=AnalysisEngine.analyze(symbol,timeframe,candles)
        if(candidate!=null&&!AnalysisEngine.sameSetup(active.signal,candidate)){
            val decision=replacementDecision(active,candidate)
            if(decision.replace){
                val reason="Pending ${active.signal.direction} setup expired before entry: ${decision.reason} Current-candle structure now favors ${candidate.direction} ${candidate.score}/100. Press NEW ANALYZE to review the fresh setup."
                val done=expirePending(c,active,reason,at)
                return listOf(ProcessEvent(done.signal,"EXPIRED",at))
            }
        }
        return emptyList()
    }'''
s=s[:start]+new_eval+s[end:]
p.write_text(s)

# Main activity: rich no-trade diagnostics and ACTIVE live-thesis text.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
old='''status.text="➜ NO NEW SETUP\\n➜ ${AnalysisEngine.noSignalReason(symbol,period,candles)}"'''
if old in s:
    s=s.replace(old,'status.text=AnalysisEngine.noSignalReason(symbol,period,candles)',1)
else:
    print('v37 runtime note: main no-signal anchor already changed')
old_active='''            "ACTIVE"->"Entry was reached. Trade is ACTIVE and TP1/SL are being tracked continuously."'''
new_active='''            "ACTIVE"->SignalStore.liveValidityReason(this,sig.id).takeIf{it.isNotBlank()}?:"Entry was reached. Trade is ACTIVE and TP1/SL are being tracked continuously."'''
if old_active in s:s=s.replace(old_active,new_active,1)
p.write_text(s)

# Floating app: after NEW ANALYZE, show the same selected-timeframe diagnostic
# instead of a generic repeated sentence. Keep existing signal if one is active.
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
old='''                    if(candidate==null){status?.text=existing?.let{stateText(it,"Previous signal is still valid; no stronger confirmation yet.")}?:"➜ No confirmed setup yet.";showState();return@post}
'''
new='''                    if(candidate==null){
                        if(existing!=null){status?.text=stateText(existing,"Previous signal is still valid; no stronger confirmation yet.");overlay(existing)}
                        else{status?.text=AnalysisEngine.noSignalReason(symbol,period,data);overlay(null)}
                        return@post
                    }
'''
if old not in s:
    raise SystemExit('v37 runtime overlay candidate-null anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# Version metadata.
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 37',s);s=re.sub(r'versionName = "[^"]+"','versionName = "37.0"',s);p.write_text(s)
print('v37 runtime validity/UI patch applied')
