from pathlib import Path
import re

# v36 reliability patch: never trust a merely-connected websocket, reconcile
# missed 1m candles after restart/update, use the saved socket key when present,
# and keep REST fallback alive when no fresh tick is actually arriving.

# ---------- SignalStore: historical reconciliation must not "run-away" expire ----------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()

# Historical 1m candles are authoritative for whether Entry was touched, but
# "ran away" cannot be inferred from BUY/SELL direction because entries may be
# pullback limits or breakout stops. Dynamic setupCheck owns invalidation.
s=s.replace(
    '            val ranAway=if(s.direction=="BUY")x.l>s.entry+s.atr*1.8 else x.h<s.entry-s.atr*1.8\n',
    '',1
)
s=s.replace(
    '''            }else if(ranAway){val expired=expirePending(c,pending,"Market moved too far from the untouched entry; original pending setup is no longer actionable.",t);events+=ProcessEvent(s,expired.state,t)}\n''',
    '''            }\n''',1
)
p.write_text(s)

# ---------- AlarmService: fresh-tick watchdog + restart reconciliation ----------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()

# Track whether a real 1m market message is arriving. Socket "connected" alone
# is not enough; a joined but silent feed previously froze the lifecycle.
field='''    private val structureCheckAt=mutableMapOf<String,Long>()\n'''
if 'lastSocketTickAt' not in s:
    if field not in s: raise SystemExit('v36 AlarmService field anchor not found')
    s=s.replace(field,field+'''    private val lastSocketTickAt=mutableMapOf<String,Long>()\n''',1)

# Use dedicated live socket key saved by older/live-capable builds when it
# exists. Fall back to analysis key because some accounts use one key for both.
old='''    private fun startLiveSocket(){\n        val key=prefs.getString("api_key","")?.trim().orEmpty()\n        if(key.isNotBlank())LiveSocketHub.start(this,key)\n    }\n'''
new='''    private fun startLiveSocket(){\n        val socketKey=prefs.getString("socket_api_key","")?.trim().orEmpty()\n        val historyKey=prefs.getString("api_key","")?.trim().orEmpty()\n        val key=socketKey.ifBlank{historyKey}\n        if(key.isNotBlank())LiveSocketHub.start(this,key)\n    }\n'''
if old not in s: raise SystemExit('v36 startLiveSocket anchor not found')
s=s.replace(old,new,1)

# Replace callback so a real 1m tick timestamps feed health.
start=s.index('    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){')
end=s.index('\n\n    private val tick:Runnable',start)
new_live='''    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){\n        if(!running)return\n        val now=System.currentTimeMillis()\n        if(timeframe=="1m"){\n            lastSocketTickAt[symbol]=now\n            val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n            handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,now),armedBefore)\n        }\n        if(SignalStore.pendingSignals(this).any{it.signal.symbol==symbol&&it.signal.timeframe==timeframe}){\n            val k="$symbol|$timeframe"\n            val last=structureCheckAt[k]?:0L\n            if(now-last>=3000L){\n                structureCheckAt[k]=now\n                FcsClient.peek(symbol,timeframe,220)?.takeIf{it.size>=60}?.let{data->\n                    val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                    handleEvents(SignalStore.evaluateLiveStructure(this,symbol,timeframe,data,now),armedBefore)\n                }\n            }\n        }\n        syncMonitorNotification()\n    }'''
s=s[:start]+new_live+s[end:]

# Replace scheduler. Connected-but-silent websocket now falls through to REST.
start=s.index('    private val tick:Runnable=object:Runnable{')
end=s.index('\n\n    private fun scheduleNext',start)
new_tick='''    private val tick:Runnable=object:Runnable{\n        override fun run(){\n            if(!running)return\n            if(fetching){scheduleNext(3000L);return}\n            val key=prefs.getString("api_key","")?.trim().orEmpty()\n            val pending=SignalStore.pendingSignals(this@AlarmService)\n            val open=SignalStore.openTrades(this@AlarmService)\n            if(key.isBlank()){updateService("Analysis key missing • background tracking paused");scheduleNext(60_000L);return}\n            if(pending.isEmpty()&&open.isEmpty()){updateService("No pending/open trades • background monitor idle");stopSelf();return}\n\n            pending.forEach{AlarmStore.ensureArmed(this@AlarmService,it.signal)}\n            startLiveSocket()\n\n            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()\n            val now=System.currentTimeMillis()\n            val stale=symbols.filter{now-(lastSocketTickAt[it]?:0L)>8_000L}\n            if(stale.isEmpty()&&LiveSocketHub.isConnected()){\n                val age=symbols.maxOfOrNull{now-(lastSocketTickAt[it]?:now)}?:0L\n                updateService("LIVE TICKS • ${pending.size} pending • ${open.size} open • age ${age/1000}s")\n                scheduleNext(15_000L);return\n            }\n\n            // At most three REST calls per ~63 seconds: two price-recovery calls\n            // plus one structure call. This stays inside the client's rate gate.\n            val lifeTasks=(if(stale.isNotEmpty())stale else symbols).map{Task("LIFE",it,"1m")}\n            val structureTasks=pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.map{Task("STRUCT",it.symbol,it.timeframe)}\n            if(lifeTasks.isEmpty()){scheduleNext(30_000L);return}\n            val useStructure=structureTasks.isNotEmpty()&&cursor%3==2\n            val task=if(useStructure)structureTasks[(cursor/3)%structureTasks.size] else lifeTasks[cursor%lifeTasks.size]\n            cursor=(cursor+1)%100000\n            updateService("REST RECOVERY • ${pending.size} pending • ${open.size} open • ${task.symbol} ${task.timeframe}")\n            fetching=true\n            thread(name="mh-rest-recovery"){\n                try{if(task.kind=="LIFE")pollLifecycle(key,task.symbol) else pollStructure(key,task.symbol,task.timeframe)}catch(_:Throwable){}\n                finally{fetching=false;scheduleNext(21_000L)}\n            }\n        }\n    }'''
s=s[:start]+new_tick+s[end:]

# Reconcile the last 220 one-minute candles after monitor start. This repairs a
# pending signal even when its entry was crossed while the previous build had a
# silent websocket or Android had suspended the process.
anchor='''    private fun pollLifecycle(key:String,symbol:String){\n'''
if 'private fun reconcileRecentHistory()' not in s:
    reconcile='''    private fun reconcileRecentHistory(){\n        val key=prefs.getString("api_key","")?.trim().orEmpty()\n        if(key.isBlank())return\n        val symbols=(SignalStore.pendingSignals(this).map{it.signal.symbol}+SignalStore.openTrades(this).map{it.signal.symbol}).distinct()\n        symbols.forEach{symbol->\n            runCatching{\n                val(out,credits)=FcsClient.history(key,symbol,"1m",220,true);addUsage(credits)\n                if(out.isEmpty())return@runCatching\n                val pending=SignalStore.pendingSignals(this).filter{it.signal.symbol==symbol}\n                val open=SignalStore.openTrades(this).filter{it.signal.symbol==symbol}\n                val floor=(pending.map{it.signal.createdAt}+open.map{it.activatedAt?:it.signal.createdAt}).minOrNull()?:System.currentTimeMillis()\n                var armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                out.filter{toMillis(it.t)>floor}.sortedBy{toMillis(it.t)}.forEach{candle->\n                    handleEvents(SignalStore.processMinuteCandle(this,symbol,candle),armedBefore)\n                    armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                }\n                // Seed the consecutive-price crossing reference with the newest\n                // observed close after historical reconciliation.\n                armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                handleEvents(SignalStore.processLivePrice(this,symbol,out.last().c,System.currentTimeMillis()),armedBefore)\n            }\n        }\n        syncMonitorNotification()\n    }\n\n'''
    if anchor not in s: raise SystemExit('v36 reconcile anchor not found')
    s=s.replace(anchor,reconcile+anchor,1)

# Kick reconciliation from service creation; tick self-reschedules while it runs.
old='''        startForeground(311,serviceNotification("Starting continuous signal tracking"))\n        LiveSocketHub.addListener(this);startLiveSocket();h.post(tick)\n'''
new='''        startForeground(311,serviceNotification("Starting continuous signal tracking"))\n        LiveSocketHub.addListener(this);startLiveSocket()\n        fetching=true\n        thread(name="mh-startup-reconcile"){try{reconcileRecentHistory()}finally{fetching=false;h.post(tick)}}\n'''
if old not in s: raise SystemExit('v36 onCreate reconcile anchor not found')
s=s.replace(old,new,1)

p.write_text(s)

# ---------- MainActivity: make tracking state less misleading ----------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
# The v35 conclusion said "continuous" even if the feed was connected but silent.
# Keep the wording factual; actual lifecycle status is supplied by monitor/records.
s=s.replace(
    '"Fresh confirmed setup accepted; continuous live lifecycle tracking is active."',
    '"Fresh confirmed setup accepted. Entry, validity and outcome tracking have been started in the background."',
    1
)
p.write_text(s)

# ---------- Version metadata ----------
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \\d+','versionCode = 36',s);s=re.sub(r'versionName = "[^"]+"','versionName = "36.0"',s);p.write_text(s)
print('v36 lifecycle watchdog + reconciliation patch applied')
