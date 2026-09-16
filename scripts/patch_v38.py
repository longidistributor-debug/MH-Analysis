from pathlib import Path
import re

# v38: fix the real pending/trigger race in the current v35-v37 lifecycle.
# The engine already stores live_origin/live_ref when a signal is accepted.
# The bug is that activation required two observed prices to straddle Entry,
# so a fast cross between REST polls could remain PENDING. We now use the
# origin side: if Entry was above the market at creation, any later price at/
# above Entry triggers it; if Entry was below, any later price at/below triggers.

# -----------------------------------------------------------------------------
# SignalStore
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()

start=s.index('    @Synchronized fun processLivePrice(')
end=s.index('\n\n    /** Structure/momentum validity check',start)
new_live='''    private fun storedLivePrice(c:Context,key:String):Double?{\n        val raw=prefs(c).getLong(key,Long.MIN_VALUE)\n        return if(raw==Long.MIN_VALUE)null else java.lang.Double.longBitsToDouble(raw).takeIf{it.isFinite()}\n    }\n\n    private fun entryReachedFromOrigin(c:Context,sig:Signal,price:Double):Boolean{\n        val origin=storedLivePrice(c,"live_origin_${sig.id}")\n        val previous=storedLivePrice(c,"live_ref_${sig.id}")\n        val tolerance=(sig.atr*.035).coerceAtLeast(kotlin.math.abs(sig.entry)*0.000005)\n        return when{\n            origin!=null&&sig.entry>origin+tolerance -> price>=sig.entry-tolerance\n            origin!=null&&sig.entry<origin-tolerance -> price<=sig.entry+tolerance\n            origin!=null -> kotlin.math.abs(price-sig.entry)<=tolerance\n            previous!=null -> sig.entry in (minOf(previous,price)-tolerance)..(maxOf(previous,price)+tolerance)\n            else -> kotlin.math.abs(price-sig.entry)<=tolerance\n        }\n    }\n\n    /** Tick/current-price lifecycle tracking.\n     * Activation is origin-aware, so both breakout/stop and pullback/limit\n     * entries work even when the exact crossing happened between two polls.\n     */\n    @Synchronized fun processLivePrice(c:Context,symbol:String,price:Double,at:Long=System.currentTimeMillis(),source:String="LIVE"):List<ProcessEvent>{\n        if(!price.isFinite())return emptyList()\n        val events=mutableListOf<ProcessEvent>()\n        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->\n            val sig=pending.signal\n            if(at<=sig.createdAt)return@forEach\n            val originKey="live_origin_${sig.id}"\n            val refKey="live_ref_${sig.id}"\n            val existingOrigin=storedLivePrice(c,originKey)\n            val existingRef=storedLivePrice(c,refKey)\n            val origin=existingOrigin?:existingRef?:price\n            val reached=entryReachedFromOrigin(c,sig,price)\n            prefs(c).edit()\n                .putLong(originKey,java.lang.Double.doubleToRawLongBits(origin))\n                .putLong(refKey,java.lang.Double.doubleToRawLongBits(price))\n                .apply()\n\n            if(reached){\n                clearActive(c,sig.symbol,sig.timeframe)\n                var active=ActiveSignal(sig,at,pending.barsSeen+1,"ACTIVE")\n                saveLast(c,active)\n                prefs(c).edit()\n                    .putString("live_validity_${sig.id}","Entry reached; trade is ACTIVE.")\n                    .putString("trigger_reason_${sig.id}","$source price ${fmtLifecyclePrice(price)} reached Entry ${fmtLifecyclePrice(sig.entry)}.")\n                    .apply()\n\n                val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl\n                val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1\n                if(hitSl||hitTp){\n                    val result=if(hitSl)"LOSS" else "WIN"\n                    active=active.copy(state=result)\n                    addRecord(c,toRecord(active,result,at));saveLast(c,active)\n                    AlarmStore.expireSignal(c,sig.id,"TRIGGERED")\n                    events+=ProcessEvent(sig,result,at)\n                }else{\n                    addOpen(c,active)\n                    AlarmStore.expireSignal(c,sig.id,"TRIGGERED")\n                    events+=ProcessEvent(sig,"ACTIVE",at)\n                }\n            }\n        }\n\n        val all=openTrades(c).toMutableList();var changed=false;val it=all.listIterator()\n        while(it.hasNext()){\n            val a=it.next();val sig=a.signal\n            if(sig.symbol!=symbol||at<(a.activatedAt?:0L))continue\n            val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl\n            val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1\n            if(hitSl||hitTp){\n                val result=if(hitSl)"LOSS" else "WIN"\n                val done=a.copy(state=result)\n                addRecord(c,toRecord(done,result,at));saveLast(c,done)\n                prefs(c).edit().putString("live_validity_${sig.id}","Trade closed: $result.").apply()\n                it.remove();changed=true;events+=ProcessEvent(sig,result,at)\n            }\n        }\n        if(changed)saveOpen(c,all)\n        return events\n    }\n\n    fun triggerReason(c:Context,signalId:String)=prefs(c).getString("trigger_reason_$signalId","").orEmpty()\n    private fun fmtLifecyclePrice(v:Double)=if(kotlin.math.abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)\n'''
s=s[:start]+new_live+s[end:]

# Historical candle activation should also leave an auditable trigger reason.
old='''                clearActive(c,s.symbol,s.timeframe);var active=ActiveSignal(s,t,pending.barsSeen+1,"ACTIVE");saveLast(c,active);AlarmStore.expireSignal(c,s.id,"TRIGGERED")\n'''
new='''                clearActive(c,s.symbol,s.timeframe);var active=ActiveSignal(s,t,pending.barsSeen+1,"ACTIVE");saveLast(c,active);prefs(c).edit().putString("trigger_reason_${s.id}","1m candle range touched Entry ${fmtLifecyclePrice(s.entry)}.").apply();AlarmStore.expireSignal(c,s.id,"TRIGGERED")\n'''
if old not in s: raise SystemExit('v38 minute-candle trigger anchor not found')
s=s.replace(old,new,1)

# Structure invalidation must never beat an already-observed Entry cross.
old='''        if(active.state!="PENDING"||candles.size<60)return emptyList()\n        val check=AnalysisEngine.setupCheck(active.signal,candles)\n'''
new='''        if(active.state!="PENDING"||candles.size<60)return emptyList()\n        val observed=storedLivePrice(c,"live_ref_${active.signal.id}")\n        if(observed!=null&&entryReachedFromOrigin(c,active.signal,observed)){\n            val recovered=processLivePrice(c,symbol,observed,at,"STRUCTURE_PRECHECK")\n            if(recovered.isNotEmpty())return recovered\n        }\n        val check=AnalysisEngine.setupCheck(active.signal,candles)\n'''
if old not in s: raise SystemExit('v38 structure precheck anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# AlarmService
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()

# Manual alarm OFF must stay OFF; only repair a missing alarm row.
s=s.replace('            pending.forEach{AlarmStore.ensureArmed(this@AlarmService,it.signal)}\n', '            pending.forEach{if(AlarmStore.forSignal(this@AlarmService,it.signal.id)==null)AlarmStore.ensureArmed(this@AlarmService,it.signal)}\n',1)

# Websocket price observations get a source tag and visible tracker heartbeat.
old='''            handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,now),armedBefore)\n'''
new='''            markTracker(symbol,candle.c,"WEBSOCKET")\n            handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,now,"WEBSOCKET"),armedBefore)\n'''
if old not in s: raise SystemExit('v38 websocket lifecycle anchor not found')
s=s.replace(old,new,1)

# Startup/restart reconciliation: the signal-created 1m candle is reconciled by
# its closing observation; later candles also use their full OHLC range.
start=s.index('    private fun reconcileRecentHistory(){')
end=s.index('\n\n    private fun pollLifecycle',start)
new_reconcile='''    private fun reconcileRecentHistory(){\n        val key=prefs.getString("api_key","")?.trim().orEmpty()\n        if(key.isBlank())return\n        val symbols=(SignalStore.pendingSignals(this).map{it.signal.symbol}+SignalStore.openTrades(this).map{it.signal.symbol}).distinct()\n        symbols.forEach{symbol->\n            runCatching{\n                val(out,credits)=FcsClient.history(key,symbol,"1m",220,true);addUsage(credits)\n                if(out.isEmpty())return@runCatching\n                val pending=SignalStore.pendingSignals(this).filter{it.signal.symbol==symbol}\n                val open=SignalStore.openTrades(this).filter{it.signal.symbol==symbol}\n                val floor=(pending.map{it.signal.createdAt}+open.map{it.activatedAt?:it.signal.createdAt}).minOrNull()?:System.currentTimeMillis()\n                out.filter{toMillis(it.t)+60_000L>floor}.sortedBy{toMillis(it.t)}.forEach{candle->\n                    val startAt=toMillis(candle.t);val endAt=startAt+60_000L\n                    var armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                    if(startAt>floor)handleEvents(SignalStore.processMinuteCandle(this,symbol,candle),armedBefore)\n                    armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                    markTracker(symbol,candle.c,"HISTORY_CLOSE")\n                    handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,endAt,"HISTORY_CLOSE"),armedBefore)\n                }\n                val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n                markTracker(symbol,out.last().c,"HISTORY_LAST")\n                handleEvents(SignalStore.processLivePrice(this,symbol,out.last().c,System.currentTimeMillis(),"HISTORY_LAST"),armedBefore)\n            }\n        }\n        syncMonitorNotification()\n    }'''
s=s[:start]+new_reconcile+s[end:]

# REST lifecycle snapshots are also source-tagged.
old='''                handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt),armedBefore)\n'''
new='''                markTracker(symbol,prev.c,"REST_PREVIOUS")\n                handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt,"REST_PREVIOUS"),armedBefore)\n'''
if old not in s: raise SystemExit('v38 REST previous anchor not found')
s=s.replace(old,new,1)
old='''        handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis()),armedBefore)\n'''
new='''        markTracker(symbol,snapshot.active.c,"REST_ACTIVE")\n        handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis(),"REST_ACTIVE"),armedBefore)\n'''
if old not in s: raise SystemExit('v38 REST active anchor not found')
s=s.replace(old,new,1)

# Structure checks are not allowed to expire a setup when the lifecycle price
# tracker itself is stale. First recover a fresh price, then judge structure.
old='''    private fun pollStructure(key:String,symbol:String,timeframe:String){\n        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)\n        if(out.size<60)return\n'''
new='''    private fun pollStructure(key:String,symbol:String,timeframe:String){\n        val priceAge=System.currentTimeMillis()-prefs.getLong("tracker_at_${symbol.uppercase()}",0L)\n        if(priceAge>35_000L)return\n        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)\n        if(out.size<60)return\n'''
if old not in s: raise SystemExit('v38 pollStructure anchor not found')
s=s.replace(old,new,1)

anchor='''    private fun syncMonitorNotification(){\n'''
helper='''    private fun markTracker(symbol:String,price:Double,source:String){\n        prefs.edit()\n            .putString("tracker_price_${symbol.uppercase()}",price.toString())\n            .putLong("tracker_at_${symbol.uppercase()}",System.currentTimeMillis())\n            .putString("tracker_source_${symbol.uppercase()}",source)\n            .apply()\n    }\n\n'''
if anchor not in s: raise SystemExit('v38 tracker helper anchor not found')
s=s.replace(anchor,helper+anchor,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Main UI: expose the background tracker price/source/age and trigger reason.
# This makes it immediately visible whether lifecycle tracking is alive.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
old='''        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")\n'''
new='''        out.append("➜ TP2: ${price(sig.tp2)}\\n")\n        val trackerPrefs=getSharedPreferences("mh",MODE_PRIVATE)\n        val tracker=trackerPrefs.getString("tracker_price_${sig.symbol.uppercase()}",null)?.toDoubleOrNull()\n        val trackerAt=trackerPrefs.getLong("tracker_at_${sig.symbol.uppercase()}",0L)\n        val trackerSource=trackerPrefs.getString("tracker_source_${sig.symbol.uppercase()}","").orEmpty()\n        if(tracker!=null&&trackerAt>0L){\n            val age=((System.currentTimeMillis()-trackerAt).coerceAtLeast(0L))/1000L\n            out.append("➜ TRACKER: ${price(tracker)} • $trackerSource • ${age}s ago\\n")\n        }\n        SignalStore.triggerReason(this,sig.id).takeIf{it.isNotBlank()}?.let{out.append("➜ TRIGGER: $it\\n")}\n        out.append("\\n")\n'''
if old not in s: raise SystemExit('v38 UI tracker anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 38',s);s=re.sub(r'versionName = "[^"]+"','versionName = "38.0"',s);p.write_text(s)

print('v38 reliable entry-cross lifecycle patch applied')
