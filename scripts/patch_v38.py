from pathlib import Path
import re

# v38: fix the actual lifecycle bug. Entry triggering must depend on where the
# generated entry sits relative to the market price at signal creation, not on
# BUY/SELL direction. BUY can be a breakout stop above price or a pullback limit
# below price; SELL can likewise be either side.

# -----------------------------------------------------------------------------
# Model: remember the market price at the instant the signal was generated.
# Existing stored signals remain compatible because the new field is nullable.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/Models.kt')
s=p.read_text()
old='''    val validityReason:String,val slReason:String,val tp1Reason:String,val tp2Reason:String,val setupReason:String\n)'''
new='''    val validityReason:String,val slReason:String,val tp1Reason:String,val tp2Reason:String,val setupReason:String,\n    val originPrice:Double?=null\n)'''
if old not in s: raise SystemExit('v38 Models Signal anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# AnalysisEngine: persist last selected-timeframe close as the signal origin.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
needle=',setupReason)\n    }\n\n    fun sameSetup'
if needle not in s: raise SystemExit('v38 AnalysisEngine Signal return anchor not found')
s=s.replace(needle,',setupReason,last.c)\n    }\n\n    fun sameSetup',1)
p.write_text(s)

# -----------------------------------------------------------------------------
# SignalStore: origin-aware entry crossing, immediate alarm arming, serialization,
# and a structure-expiry precheck so an observed Entry can never be expired first.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()

# Accepted signals get an alarm row immediately. Do not wait for a background
# service iteration; a fast market can cross Entry seconds after analysis.
old='''        saveActive(c,ActiveSignal(candidate,state="PENDING"));return true\n'''
new='''        saveActive(c,ActiveSignal(candidate,state="PENDING"))\n        AlarmStore.ensureArmed(c,candidate)\n        candidate.originPrice?.let{prefs(c).edit().putString("last_price_${candidate.id}",it.toString()).apply()}\n        return true\n'''
if old not in s: raise SystemExit('v38 acceptCandidate anchor not found')
s=s.replace(old,new,1)

# Persist originPrice in records/preferences while remaining backward compatible.
s=s.replace('.put("setupReason",s.setupReason).put("reasons",reasons)', '.put("setupReason",s.setupReason).put("originPrice",s.originPrice).put("reasons",reasons)',1)
old_from='''j.optString("setupReason","Weighted confluence."))}'''
new_from='''j.optString("setupReason","Weighted confluence."),if(j.isNull("originPrice"))null else j.optDouble("originPrice"))}'''
if old_from not in s: raise SystemExit('v38 signalFromJson anchor not found')
s=s.replace(old_from,new_from,1)

# Replace live-price lifecycle with origin/crossing logic. The old code assumed
# BUY means price must fall to Entry and SELL means price must rise to Entry,
# which is exactly why breakout entries stayed PENDING after being crossed.
start=s.index('    fun processLivePrice(c:Context,symbol:String,price:Double,at:Long=System.currentTimeMillis())')
end=s.index('\n    fun expireAllPendingForVolatility',start)
new_live='''    private fun entryCrossed(s:Signal,price:Double,previous:Double?=null):Boolean{\n        val origin=s.originPrice\n        return when{\n            origin!=null&&origin.isFinite()&&origin<s.entry -> price>=s.entry\n            origin!=null&&origin.isFinite()&&origin>s.entry -> price<=s.entry\n            origin!=null&&origin.isFinite() -> true\n            previous!=null&&previous.isFinite() -> (previous<=s.entry&&price>=s.entry)||(previous>=s.entry&&price<=s.entry)\n            else -> false\n        }\n    }\n\n    /** Process the newest observed market price. Entry is triggered by the\n     * side of Entry relative to the market when the signal was CREATED, not by\n     * BUY/SELL direction. This supports both stop/breakout and limit/pullback entries.\n     */\n    fun processLivePrice(c:Context,symbol:String,price:Double,at:Long=System.currentTimeMillis(),source:String="LIVE"):List<ProcessEvent>{\n        if(price.isNaN()||price.isInfinite())return emptyList()\n        val events=mutableListOf<ProcessEvent>()\n        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->\n            val sig=pending.signal\n            if(at<=sig.createdAt)return@forEach\n            val key="last_price_${sig.id}"\n            val previous=prefs(c).getString(key,null)?.toDoubleOrNull()\n            val reached=entryCrossed(sig,price,previous)\n            prefs(c).edit().putString(key,price.toString()).apply()\n            if(reached){\n                clearActive(c,sig.symbol,sig.timeframe)\n                var active=ActiveSignal(sig,at,pending.barsSeen+1,"ACTIVE")\n                saveLast(c,active)\n                prefs(c).edit().putString("trigger_reason_${sig.id}","$source price ${fmtPrice(price)} crossed Entry ${fmtPrice(sig.entry)}").apply()\n                AlarmStore.expireSignal(c,sig.id,"TRIGGERED")\n                val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl\n                val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1\n                if(hitSl||hitTp){\n                    val result=if(hitSl)"LOSS" else "WIN"\n                    active=active.copy(state=result)\n                    addRecord(c,toRecord(active,result,at));saveLast(c,active);events+=ProcessEvent(sig,result,at)\n                }else{\n                    addOpen(c,active);events+=ProcessEvent(sig,"ACTIVE",at)\n                }\n            }\n        }\n        val all=openTrades(c).toMutableList();var changed=false;val it=all.listIterator()\n        while(it.hasNext()){\n            val a=it.next();val sig=a.signal\n            if(sig.symbol!=symbol||at<(a.activatedAt?:0L))continue\n            val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl\n            val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1\n            if(hitSl||hitTp){\n                val result=if(hitSl)"LOSS" else "WIN"\n                val done=a.copy(state=result);addRecord(c,toRecord(done,result,at));saveLast(c,done);it.remove();changed=true;events+=ProcessEvent(sig,result,at)\n            }\n        }\n        if(changed)saveOpen(c,all)\n        return events\n    }\n\n    fun triggerReason(c:Context,signalId:String)=prefs(c).getString("trigger_reason_$signalId","").orEmpty()\n    private fun fmtPrice(v:Double)=if(kotlin.math.abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)\n'''
s=s[:start]+new_live+s[end:]

# Before dynamic structure invalidation can EXPIRE a pending signal, honor the
# newest observed price. This prevents "Entry already crossed but structure task
# expired it first" races when REST recovery and structure checks interleave.
old='''        if(active.state!="PENDING"||candles.size<60)return emptyList()\n        val check=AnalysisEngine.setupCheck(active.signal,candles)\n'''
new='''        if(active.state!="PENDING"||candles.size<60)return emptyList()\n        val observed=prefs(c).getString("last_price_${active.signal.id}",null)?.toDoubleOrNull()\n        if(observed!=null&&entryCrossed(active.signal,observed,null)){\n            val recovered=processLivePrice(c,symbol,observed,at,"STRUCTURE_PRECHECK")\n            if(recovered.isNotEmpty())return recovered\n        }\n        val check=AnalysisEngine.setupCheck(active.signal,candles)\n'''
if old not in s: raise SystemExit('v38 evaluateLiveStructure precheck anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# AlarmService: source-tagged live observations, same-minute recovery, preserve
# manual Alarm OFF, and never run structure expiry ahead of a stale price feed.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()

s=s.replace('handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,now),armedBefore)', 'markTracker(symbol,candle.c,"WEBSOCKET");handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,now,"WEBSOCKET"),armedBefore)',1)

# Manual OFF must remain OFF. Only create/arm when the signal has no alarm row.
s=s.replace('            pending.forEach{AlarmStore.ensureArmed(this@AlarmService,it.signal)}\n', '            pending.forEach{if(AlarmStore.forSignal(this@AlarmService,it.signal.id)==null)AlarmStore.ensureArmed(this@AlarmService,it.signal)}\n',1)

# Replace startup reconciliation. Include a signal-created minute via its CLOSE
# observation, while using full OHLC only for candles that started after creation.
start=s.index('    private fun reconcileRecentHistory(){')
end=s.index('\n\n    private fun pollLifecycle',start)
new_reconcile='''    private fun reconcileRecentHistory(){\n        val key=prefs.getString("api_key","")?.trim().orEmpty()\n        if(key.isBlank())return\n        val symbols=(SignalStore.pendingSignals(this).map{it.signal.symbol}+SignalStore.openTrades(this).map{it.signal.symbol}).distinct()\n        symbols.forEach{symbol->\n            runCatching{\n                val(out,credits)=FcsClient.history(key,symbol,"1m",220,true);addUsage(credits)\n                if(out.isEmpty())return@runCatching\n                val pending=SignalStore.pendingSignals(this).filter{it.signal.symbol==symbol}\n                val open=SignalStore.openTrades(this).filter{it.signal.symbol==symbol}\n                val floor=(pending.map{it.signal.createdAt}+open.map{it.activatedAt?:it.signal.createdAt}).minOrNull()?:System.currentTimeMillis()\n                out.filter{toMillis(it.t)+60_000L>floor}.sortedBy{toMillis(it.t)}.forEach{candle->\n                    val startAt=toMillis(candle.t);val endAt=startAt+60_000L\n                    var armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                    if(startAt>floor)handleEvents(SignalStore.processMinuteCandle(this,symbol,candle),armedBefore)\n                    armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                    markTracker(symbol,candle.c,"HISTORY_CLOSE")\n                    handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,endAt,"HISTORY_CLOSE"),armedBefore)\n                }\n                val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                markTracker(symbol,out.last().c,"HISTORY_LAST")\n                handleEvents(SignalStore.processLivePrice(this,symbol,out.last().c,System.currentTimeMillis(),"HISTORY_LAST"),armedBefore)\n            }\n        }\n        syncMonitorNotification()\n    }'''
s=s[:start]+new_reconcile+s[end:]

# Tag REST lifecycle observations and expose tracker freshness for UI/debugging.
s=s.replace('handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt),armedBefore)', 'markTracker(symbol,prev.c,"REST_PREVIOUS");handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt,"REST_PREVIOUS"),armedBefore)',1)
s=s.replace('handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis()),armedBefore)', 'markTracker(symbol,snapshot.active.c,"REST_ACTIVE");handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis(),"REST_ACTIVE"),armedBefore)',1)

anchor='''    private fun syncMonitorNotification(){\n'''
if 'private fun markTracker(' not in s:
    helper='''    private fun markTracker(symbol:String,price:Double,source:String){\n        prefs.edit().putString("tracker_price_${symbol.uppercase()}",price.toString())\n            .putLong("tracker_at_${symbol.uppercase()}",System.currentTimeMillis())\n            .putString("tracker_source_${symbol.uppercase()}",source).apply()\n    }\n\n'''
    if anchor not in s: raise SystemExit('v38 AlarmService helper anchor not found')
    s=s.replace(anchor,helper+anchor,1)

# Do not let a structure-only REST task expire a setup if lifecycle price data is stale.
old='''    private fun pollStructure(key:String,symbol:String,timeframe:String){\n        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)\n        if(out.size<60)return\n'''
new='''    private fun pollStructure(key:String,symbol:String,timeframe:String){\n        val priceAge=System.currentTimeMillis()-prefs.getLong("tracker_at_${symbol.uppercase()}",0L)\n        if(priceAge>35_000L)return\n        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)\n        if(out.size<60)return\n'''
if old not in s: raise SystemExit('v38 pollStructure anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Main UI: show the actual lifecycle tracker source/price with pending/active
# signals. This makes it obvious whether the background tracker is fresh.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
old='''        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")\n'''
new='''        out.append("➜ TP2: ${price(sig.tp2)}\\n")\n        val trackerPrefs=getSharedPreferences("mh",MODE_PRIVATE)\n        val tracker=trackerPrefs.getString("tracker_price_${sig.symbol.uppercase()}",null)?.toDoubleOrNull()\n        val trackerAt=trackerPrefs.getLong("tracker_at_${sig.symbol.uppercase()}",0L)\n        val trackerSource=trackerPrefs.getString("tracker_source_${sig.symbol.uppercase()}","").orEmpty()\n        if(tracker!=null&&trackerAt>0L){val age=((System.currentTimeMillis()-trackerAt).coerceAtLeast(0L))/1000L;out.append("➜ TRACKER: ${price(tracker)} • $trackerSource • ${age}s ago\\n")}\n        SignalStore.triggerReason(this,sig.id).takeIf{it.isNotBlank()}?.let{out.append("➜ TRIGGER: $it\\n")}\n        out.append("\\n")\n'''
if old not in s: raise SystemExit('v38 MainActivity formatSignal anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Version metadata.
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 38',s);s=re.sub(r'versionName = "[^"]+"','versionName = "38.0"',s);p.write_text(s)

print('v38 origin-aware entry-cross lifecycle patch applied')
