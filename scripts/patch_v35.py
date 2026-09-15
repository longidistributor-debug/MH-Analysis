from pathlib import Path
import re

# v35: continuous lifecycle, real alarm toggles, structured analysis UI,
# strong-only replacement, and TradingView touch/toolbar cleanup.

# ---------- SignalStore: tick crossing, dynamic structure checks, replacement gate ----------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()

# Add replacement decision model.
if 'data class ReplacementDecision' not in s:
    s=s.replace(
        '    data class ProcessEvent(val signal:Signal,val state:String,val at:Long)\n',
        '    data class ProcessEvent(val signal:Signal,val state:String,val at:Long)\n'
        '    data class ReplacementDecision(val replace:Boolean,val reason:String)\n',
        1
    )

# Replace acceptCandidate with a version that records replacement reason and seeds live crossing reference.
start=s.index('    fun acceptCandidate(c:Context,candidate:Signal):Boolean{')
end=s.index('\n\n    fun evaluate(', start)
new_accept='''    @Synchronized fun acceptCandidate(c:Context,candidate:Signal):Boolean{
        if(findDuplicate(c,candidate)!=null)return false
        loadActive(c,candidate.symbol,candidate.timeframe)?.let{old->
            expirePending(c,old,"Replaced by a materially stronger newly confirmed setup.",System.currentTimeMillis())
        }
        val now=System.currentTimeMillis()
        saveActive(c,ActiveSignal(candidate,state="PENDING"))
        val px=FcsClient.peek(candidate.symbol,candidate.timeframe,1)?.lastOrNull()?.c
        if(px!=null&&px.isFinite()){
            prefs(c).edit()
                .putLong("live_origin_${candidate.id}",java.lang.Double.doubleToRawLongBits(px))
                .putLong("live_ref_${candidate.id}",java.lang.Double.doubleToRawLongBits(px))
                .putString("live_validity_${candidate.id}","Fresh setup accepted; live structure monitoring active.")
                .apply()
        }
        AlarmStore.ensureArmed(c,candidate)
        return true
    }'''
s=s[:start]+new_accept+s[end:]

# Replace v34 processLivePrice implementation entirely.
start=s.index('    fun processLivePrice(')
end=s.index('\n\n    fun expireAllPendingForVolatility', start)
new_live='''    /** Tick/current-price lifecycle tracking.
     * Entry activation is based on an actual crossing/touch between consecutive
     * observed live prices, so it works for both pullback-limit and breakout
     * entries and does not depend on the candle-open timestamp.
     */
    @Synchronized fun processLivePrice(c:Context,symbol:String,price:Double,at:Long=System.currentTimeMillis()):List<ProcessEvent>{
        if(!price.isFinite())return emptyList()
        val events=mutableListOf<ProcessEvent>()
        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->
            val sig=pending.signal
            if(at<=sig.createdAt)return@forEach
            val refKey="live_ref_${sig.id}"
            val originKey="live_origin_${sig.id}"
            val rawRef=prefs(c).getLong(refKey,Long.MIN_VALUE)
            val rawOrigin=prefs(c).getLong(originKey,Long.MIN_VALUE)
            val previous=if(rawRef==Long.MIN_VALUE)price else java.lang.Double.longBitsToDouble(rawRef)
            val origin=if(rawOrigin==Long.MIN_VALUE)previous else java.lang.Double.longBitsToDouble(rawOrigin)
            prefs(c).edit()
                .putLong(refKey,java.lang.Double.doubleToRawLongBits(price))
                .putLong(originKey,java.lang.Double.doubleToRawLongBits(origin))
                .apply()

            val lo=minOf(previous,price)
            val hi=maxOf(previous,price)
            val tolerance=(sig.atr*.035).coerceAtLeast(kotlin.math.abs(sig.entry)*0.000005)
            val touched=sig.entry in (lo-tolerance)..(hi+tolerance) || kotlin.math.abs(price-sig.entry)<=tolerance

            // "Ran away" is relative to where the market was when this pending
            // setup was accepted, not hard-coded to BUY/SELL. This avoids
            // expiring valid breakout entries in the wrong direction.
            val entryAboveOrigin=sig.entry>=origin
            val ranAway=if(entryAboveOrigin) price<sig.entry-sig.atr*1.8 else price>sig.entry+sig.atr*1.8

            if(touched){
                clearActive(c,sig.symbol,sig.timeframe)
                var active=ActiveSignal(sig,at,pending.barsSeen+1,"ACTIVE")
                saveLast(c,active)
                prefs(c).edit().putString("live_validity_${sig.id}","Entry reached at live market price; trade is ACTIVE.").apply()

                val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl
                val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1
                if(hitSl||hitTp){
                    val result=if(hitSl)"LOSS" else "WIN"
                    active=active.copy(state=result)
                    addRecord(c,toRecord(active,result,at));saveLast(c,active)
                    AlarmStore.expireSignal(c,sig.id,"TRIGGERED")
                    events+=ProcessEvent(sig,result,at)
                }else{
                    addOpen(c,active)
                    AlarmStore.expireSignal(c,sig.id,"TRIGGERED")
                    events+=ProcessEvent(sig,"ACTIVE",at)
                }
            }else if(ranAway){
                val done=expirePending(c,pending,"Price moved materially away from the untouched entry before activation; the original entry is no longer actionable.",at)
                events+=ProcessEvent(sig,done.state,at)
            }
        }

        val all=openTrades(c).toMutableList()
        var changed=false
        val it=all.listIterator()
        while(it.hasNext()){
            val a=it.next();val sig=a.signal
            if(sig.symbol!=symbol||at<(a.activatedAt?:0L))continue
            val hitSl=if(sig.direction=="BUY")price<=sig.sl else price>=sig.sl
            val hitTp=if(sig.direction=="BUY")price>=sig.tp1 else price<=sig.tp1
            if(hitSl||hitTp){
                val result=if(hitSl)"LOSS" else "WIN"
                val done=a.copy(state=result)
                addRecord(c,toRecord(done,result,at));saveLast(c,done)
                prefs(c).edit().putString("live_validity_${sig.id}","Trade closed: $result.").apply()
                it.remove();changed=true;events+=ProcessEvent(sig,result,at)
            }
        }
        if(changed)saveOpen(c,all)
        return events
    }

    /** Structure/momentum validity check driven by fresh live candles, not a
     * fixed number of candles. Invalidations are persisted with the reason.
     */
    @Synchronized fun evaluateLiveStructure(c:Context,symbol:String,timeframe:String,candles:List<Candle>,at:Long=System.currentTimeMillis()):List<ProcessEvent>{
        val active=loadActive(c,symbol,timeframe)?:return emptyList()
        if(active.state!="PENDING"||candles.size<60)return emptyList()
        val check=AnalysisEngine.setupCheck(active.signal,candles)
        prefs(c).edit().putString("live_validity_${active.signal.id}",check.reason).apply()
        if(check.valid)return emptyList()
        val done=expirePending(c,active,check.reason,at)
        return listOf(ProcessEvent(done.signal,"EXPIRED",at))
    }

    fun liveValidityReason(c:Context,signalId:String)=prefs(c).getString("live_validity_$signalId","").orEmpty()

    /** A re-analysis is not allowed to churn the current setup. Same-direction
     * replacements need a real score improvement; opposite-direction flips
     * require much stronger confirmation.
     */
    fun replacementDecision(current:ActiveSignal,candidate:Signal):ReplacementDecision{
        val old=current.signal
        if(current.state!="PENDING")return ReplacementDecision(false,"Current trade is already ACTIVE; it must finish at TP1/SL before a replacement is accepted.")
        if(AnalysisEngine.sameSetup(old,candidate))return ReplacementDecision(false,"The new analysis describes the same market setup; the previous pending signal remains valid.")
        val dominance=kotlin.math.abs(candidate.bullScore-candidate.bearScore)
        val sameDirection=old.direction==candidate.direction
        val requiredScore=if(sameDirection)maxOf(72,old.score+4) else maxOf(82,old.score+8)
        val requiredDominance=if(sameDirection)12 else 18
        val stronger=candidate.score>=requiredScore&&dominance>=requiredDominance
        return if(stronger){
            ReplacementDecision(true,"New ${candidate.direction} setup is materially stronger (${candidate.score}/100 vs ${old.score}/100; directional separation $dominance).")
        }else{
            ReplacementDecision(false,"Previous ${old.direction} setup remains valid. New setup is not strong enough to replace it (${candidate.score}/100; needs at least $requiredScore with directional separation $requiredDominance).")
        }
    }'''
s=s[:start]+new_live+s[end:]

# Extend expiration cleanup and keep exact reason for records/UI.
old='''        prefs(c).edit().putString("reason_${a.signal.id}",reason).apply();return done
'''
new='''        prefs(c).edit()
            .putString("reason_${a.signal.id}",reason)
            .putString("live_validity_${a.signal.id}",reason)
            .remove("live_ref_${a.signal.id}")
            .remove("live_origin_${a.signal.id}")
            .apply()
        return done
'''
if old in s:
    s=s.replace(old,new,1)

p.write_text(s)

# ---------- AlarmStore: manual OFF must stay OFF ----------
p=Path('app/src/main/java/com/mh/analysis/AlarmStore.kt')
s=p.read_text()
old='''        val next=if(i>=0){
            val old=l[i]
            if(old.status in setOf("TRIGGERED","EXPIRED")) old
            else old.copy(enabled=true,status="ARMED",armedAt=old.armedAt?:now,triggeredAt=null)
        }else AlarmEntry("alarm_${s.id}",s.id,s.symbol,s.timeframe,s.direction,s.entry,Long.MAX_VALUE,now,true,"ARMED",null,now)
'''
new='''        val next=if(i>=0){
            val old=l[i]
            when{
                old.status in setOf("TRIGGERED","EXPIRED")->old
                !old.enabled&&old.status=="SAVED"->old // user explicitly switched alarm OFF
                else->old.copy(enabled=true,status="ARMED",armedAt=old.armedAt?:now,triggeredAt=null)
            }
        }else AlarmEntry("alarm_${s.id}",s.id,s.symbol,s.timeframe,s.direction,s.entry,Long.MAX_VALUE,now,true,"ARMED",null,now)
'''
if old not in s:
    raise SystemExit('AlarmStore ensureArmed anchor not found')
s=s.replace(old,new,1)
p.write_text(s)

# ---------- AlarmService: websocket is primary, REST latest is fallback ----------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
s=s.replace('class AlarmService:Service(){','class AlarmService:Service(),LiveSocketHub.Listener{',1)

field='''    private var cursor=0
'''
if 'structureCheckAt' not in s:
    s=s.replace(field,field+'''    private val structureCheckAt=mutableMapOf<String,Long>()
''',1)

old_create='''    override fun onCreate(){super.onCreate();FcsClient.init(this);createChannels();startForeground(311,serviceNotification("Starting background signal tracking"));h.post(tick)}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};h.removeCallbacks(tick);h.post(tick);return START_STICKY}
'''
new_create='''    override fun onCreate(){
        super.onCreate();FcsClient.init(this);createChannels()
        startForeground(311,serviceNotification("Starting continuous signal tracking"))
        LiveSocketHub.addListener(this);startLiveSocket();h.post(tick)
    }
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{
        if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY}
        startLiveSocket();h.removeCallbacks(tick);h.post(tick);return START_STICKY
    }

    private fun startLiveSocket(){
        val key=prefs.getString("api_key","")?.trim().orEmpty()
        if(key.isNotBlank())LiveSocketHub.start(this,key)
    }

    override fun onSocketState(state:String){
        if(running)updateService("${SignalStore.pendingSignals(this).size} pending • ${SignalStore.openTrades(this).size} open • $state")
    }

    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(!running)return
        // Use 1m live messages as the high-frequency price stream for every
        // pending/open signal on the symbol. No app/overlay needs to be open.
        if(timeframe=="1m"){
            val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
            handleEvents(SignalStore.processLivePrice(this,symbol,candle.c,System.currentTimeMillis()),armedBefore)
        }
        // Recheck the actual setup timeframe continuously, but throttle the
        // heavier structure calculation to once every ~3 seconds per feed.
        if(SignalStore.pendingSignals(this).any{it.signal.symbol==symbol&&it.signal.timeframe==timeframe}){
            val key="$symbol|$timeframe";val now=System.currentTimeMillis()
            val last=structureCheckAt[key]?:0L
            if(now-last>=3000L){
                structureCheckAt[key]=now
                FcsClient.peek(symbol,timeframe,220)?.takeIf{it.size>=60}?.let{data->
                    val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
                    handleEvents(SignalStore.evaluateLiveStructure(this,symbol,timeframe,data,now),armedBefore)
                }
            }
        }
        syncMonitorNotification()
    }
'''
if old_create not in s:
    raise SystemExit('AlarmService create anchor not found')
s=s.replace(old_create,new_create,1)

# Replace v34 tick with socket-first behavior while keeping latest REST fallback.
start=s.index('    private val tick:Runnable=object:Runnable{')
end=s.index('\n\n    private fun scheduleNext',start)
new_tick='''    private val tick:Runnable=object:Runnable{
        override fun run(){
            if(!running||fetching)return
            val key=prefs.getString("api_key","")?.trim().orEmpty()
            val pending=SignalStore.pendingSignals(this@AlarmService)
            val open=SignalStore.openTrades(this@AlarmService)
            if(key.isBlank()){updateService("Analysis/live key missing • background tracking paused");scheduleNext(60_000L);return}
            if(pending.isEmpty()&&open.isEmpty()){updateService("No pending/open trades • background monitor idle");stopSelf();return}

            pending.forEach{AlarmStore.ensureArmed(this@AlarmService,it.signal)}
            startLiveSocket()

            // Websocket is the primary price path. REST latest remains a
            // recovery path if Android/network has not connected the socket.
            if(LiveSocketHub.isConnected()){
                updateService("LIVE SOCKET • ${pending.size} pending • ${open.size} open")
                scheduleNext(45_000L);return
            }

            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()
            val lifeTasks=symbols.map{Task("LIFE",it,"1m")}
            val structureTasks=pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.filter{it.timeframe!="1m"}.map{Task("STRUCT",it.symbol,it.timeframe)}
            if(lifeTasks.isEmpty()){scheduleNext(60_000L);return}
            val useStructure=structureTasks.isNotEmpty()&&cursor%4==3
            val task=if(useStructure)structureTasks[(cursor/4)%structureTasks.size] else lifeTasks[cursor%lifeTasks.size]
            cursor=(cursor+1)%100000
            updateService("REST FALLBACK • ${pending.size} pending • ${open.size} open • ${task.symbol} ${task.timeframe}")
            fetching=true
            thread(name="mh-rest-fallback"){
                try{if(task.kind=="LIFE")pollLifecycle(key,task.symbol) else pollStructure(key,task.symbol,task.timeframe)}catch(_:Throwable){}
                finally{fetching=false;scheduleNext(21_000L)}
            }
        }
    }'''
s=s[:start]+new_tick+s[end:]

# Replace poll lifecycle to also feed the cache and dynamic structure.
start=s.index('    private fun pollLifecycle(key:String,symbol:String){')
end=s.index('\n\n    private fun handleEvents(',start)
new_poll='''    private fun pollLifecycle(key:String,symbol:String){
        val(snapshot,credits)=FcsClient.latest(key,symbol,"1m");addUsage(credits)
        FcsClient.applyLiveCandle(symbol,"1m",snapshot.active)
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        snapshot.previous?.let{prev->
            val cursorKey="life_latest_closed_$symbol"
            val endAt=toMillis(prev.t)+60_000L
            val lastDone=prefs.getLong(cursorKey,0L)
            if(endAt>lastDone){
                handleEvents(SignalStore.processMinuteCandle(this,symbol,prev),armedBefore)
                handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt),armedBefore)
                prefs.edit().putLong(cursorKey,endAt).apply()
            }
        }
        handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis()),armedBefore)
        SignalStore.pendingSignals(this).filter{it.signal.symbol==symbol&&it.signal.timeframe=="1m"}.forEach{
            FcsClient.peek(symbol,"1m",220)?.takeIf{x->x.size>=60}?.let{x->handleEvents(SignalStore.evaluateLiveStructure(this,symbol,"1m",x),armedBefore)}
        }
        syncMonitorNotification()
    }'''
s=s[:start]+new_poll+s[end:]

# Respect manual OFF. Do not fabricate/re-arm an alarm at trigger time.
s=s.replace(
    '''                "ACTIVE"->{val a=armedBefore[e.signal.id]?:AlarmStore.forSignal(this,e.signal.id)?:AlarmStore.ensureArmed(this,e.signal);triggerEntryAlarmOnce(a,e.signal)}
''',
    '''                "ACTIVE"->{armedBefore[e.signal.id]?.let{triggerEntryAlarmOnce(it,e.signal)}}
''',1)
s=s.replace(
    '''                    val a=armedBefore[e.signal.id]?:AlarmStore.forSignal(this,e.signal.id)?:AlarmStore.ensureArmed(this,e.signal);triggerEntryAlarmOnce(a,e.signal)
                    notifyTrade(e.signal,e.state)
''',
    '''                    armedBefore[e.signal.id]?.let{triggerEntryAlarmOnce(it,e.signal)}
                    notifyTrade(e.signal,e.state)
''',1)

# Dynamic structure evaluator instead of generic historical re-processing.
start=s.index('    private fun pollStructure(key:String,symbol:String,timeframe:String){')
end=s.index('\n\n    private fun fireThreeCycles',start)
new_structure='''    private fun pollStructure(key:String,symbol:String,timeframe:String){
        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)
        if(out.size<60)return
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        handleEvents(SignalStore.evaluateLiveStructure(this,symbol,timeframe,out,System.currentTimeMillis()),armedBefore)
    }

    private fun triggerEntryAlarmOnce(a:AlarmEntry,s:Signal){
        if(!a.enabled||a.status!="ARMED")return
        val firedKey="entry_alarm_fired_${s.id}"
        synchronized(this){
            if(prefs.getBoolean(firedKey,false))return
            prefs.edit().putBoolean(firedKey,true).commit()
        }
        val hit=a.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null)
        AlarmStore.update(this,hit)
        thread(name="mh-entry-alarm"){fireThreeCycles(hit)}
    }'''
# This slice includes old triggerEntryAlarmOnce as it appears before pollStructure? Check actual order:
# v34 order is handleEvents, sync, triggerEntryAlarmOnce, pollStructure, fire. So we need replace separately if needed.
# Undo strategy below if index ordering shows trigger is before structure.
if '    private fun triggerEntryAlarmOnce' in s and s.index('    private fun triggerEntryAlarmOnce') < start:
    # replace only pollStructure first
    end_poll=s.index('\n\n    private fun fireThreeCycles',start)
    old_block=s[start:end_poll]
    # old_block is pollStructure only because trigger is before it.
    new_only='''    private fun pollStructure(key:String,symbol:String,timeframe:String){
        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)
        if(out.size<60)return
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        handleEvents(SignalStore.evaluateLiveStructure(this,symbol,timeframe,out,System.currentTimeMillis()),armedBefore)
    }'''
    s=s[:start]+new_only+s[end_poll:]
    # replace trigger body separately
    tstart=s.index('    private fun triggerEntryAlarmOnce(a:AlarmEntry,s:Signal){')
    tend=s.index('\n\n    private fun pollStructure',tstart)
    new_trigger='''    private fun triggerEntryAlarmOnce(a:AlarmEntry,s:Signal){
        if(!a.enabled||a.status!="ARMED")return
        val firedKey="entry_alarm_fired_${s.id}"
        synchronized(this){
            if(prefs.getBoolean(firedKey,false))return
            prefs.edit().putBoolean(firedKey,true).commit()
        }
        val hit=a.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null)
        AlarmStore.update(this,hit)
        thread(name="mh-entry-alarm"){fireThreeCycles(hit)}
    }'''
    s=s[:tstart]+new_trigger+s[tend:]
else:
    s=s[:start]+new_structure+s[end:]

# Stop websocket listener when monitor truly stops.
old_destroy='''    override fun onDestroy(){running=false;h.removeCallbacks(tick);super.onDestroy()}
'''
new_destroy='''    override fun onDestroy(){
        running=false;h.removeCallbacks(tick);LiveSocketHub.removeListener(this);LiveSocketHub.stop();super.onDestroy()
    }
'''
if old_destroy not in s:
    raise SystemExit('AlarmService destroy anchor not found')
s=s.replace(old_destroy,new_destroy,1)
p.write_text(s)

# ---------- MainActivityV29: chart gestures, strong-only re-analysis, arrow UI, records, alarms ----------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
if 'import android.view.MotionEvent' not in s:
    s=s.replace('import android.view.Gravity\n','import android.view.Gravity\nimport android.view.MotionEvent\n',1)

# Make TradingView own touch gestures while finger is inside chart, so dragging
# the right price scale vertically is not intercepted by the parent ScrollView.
needle='''            CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true)
            setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){'''
repl='''            CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true)
            setBackgroundColor(Color.rgb(19,23,34))
            setOnTouchListener{v,e->
                when(e.actionMasked){
                    MotionEvent.ACTION_DOWN,MotionEvent.ACTION_MOVE->v.parent?.requestDisallowInterceptTouchEvent(true)
                    MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL->v.parent?.requestDisallowInterceptTouchEvent(false)
                }
                false
            }
            webViewClient=object:WebViewClient(){'''
if needle not in s:
    raise SystemExit('MainActivity chart touch anchor not found')
s=s.replace(needle,repl,1)

# v34 added onResume/onPause; make resume immediately sync UI/monitor.
s=s.replace(
    'override fun onResume(){super.onResume();lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);lifecycleUiHandler.post(lifecycleUiRefresh)}',
    'override fun onResume(){super.onResume();showExisting();startMonitorIfNeeded();lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);lifecycleUiHandler.post(lifecycleUiRefresh)}',
    1
)

# Replace performAnalysis.
start=s.index('    private fun performAnalysis(){')
end=s.index('\n\n    private fun currentDisplayedSignal()',start)
new_perform='''    private fun performAnalysis(){
        if(candles.size<60){status.text="NOT ENOUGH MARKET HISTORY FOR RELIABLE ANALYSIS";return}
        SignalStore.evaluate(this,symbol,period,candles)
        val existing=SignalStore.loadActive(this,symbol,period)?:currentDisplayedSignal()
        val candidate=AnalysisEngine.analyze(symbol,period,candles)

        if(candidate==null){
            if(existing!=null&&existing.state in setOf("PENDING","ACTIVE")){
                status.text=formatSignal(existing,"Previous signal is still the best valid setup. No stronger confirmed replacement exists right now.")
                showSignalCard(existing)
            }else{
                status.text="➜ NO NEW SETUP\\n➜ ${AnalysisEngine.noSignalReason(symbol,period,candles)}"
                showSignalCard(existing)
            }
            return
        }

        val duplicate=SignalStore.findDuplicate(this,candidate)
        if(duplicate!=null){
            status.text=formatSignal(duplicate,"Previous signal is still valid. Re-analysis found the same setup, so no duplicate was created.")
            showSignalCard(duplicate);return
        }

        if(existing!=null&&existing.state=="ACTIVE"){
            status.text=formatSignal(existing,"Trade is already ACTIVE. A second overlapping signal will not replace it before TP1/SL resolves.")
            showSignalCard(existing);return
        }

        if(existing!=null&&existing.state=="PENDING"){
            val decision=SignalStore.replacementDecision(existing,candidate)
            if(!decision.replace){
                status.text=formatSignal(existing,decision.reason)
                showSignalCard(existing);return
            }
        }

        if(SignalStore.acceptCandidate(this,candidate)){
            startMonitorIfNeeded()
            val accepted=SignalStore.loadActive(this,symbol,period)
            status.text=accepted?.let{formatSignal(it,"Fresh confirmed setup accepted; continuous live lifecycle tracking is active.")}?:"➜ SETUP ACCEPTED"
            showSignalCard(accepted)
        }else{
            showExisting()
        }
    }'''
s=s[:start]+new_perform+s[end:]

# Replace showExisting with structured arrows and helpers.
start=s.index('    private fun showExisting(){')
end=s.index('\n\n    private fun showRecords()',start)
new_show='''    private fun showExisting(){
        if(!::status.isInitialized)return
        val a=currentDisplayedSignal()
        if(a==null){
            status.text="➜ $symbol • $period\\n➜ TRADINGVIEW LIVE\\n➜ Press NEW ANALYZE for a fresh setup."
            showSignalCard(null);return
        }
        status.text=formatSignal(a)
        showSignalCard(a)
    }

    private fun arrowLines(text:String):String{
        return text.replace("; ",". ").split(Regex("(?<=[.!?])\\\\s+|\\\\n+"))
            .map{it.trim().trimEnd('.')}
            .filter{it.isNotBlank()}
            .joinToString("\\n"){"➜ $it"}
    }

    private fun formatSignal(a:ActiveSignal,forcedConclusion:String?=null):String{
        val sig=a.signal
        val out=StringBuilder()
        out.append("➜ SIGNAL: ${sig.direction} • ${sig.score}/100\\n")
        out.append("➜ STATE: ${a.state}\\n")
        out.append("➜ ENTRY: ${price(sig.entry)}\\n")
        out.append("➜ SL: ${price(sig.sl)}\\n")
        out.append("➜ TP1: ${price(sig.tp1)}\\n")
        out.append("➜ TP2: ${price(sig.tp2)}\\n\\n")
        out.append("WHY THIS TRADE\\n").append(arrowLines(sig.setupReason)).append("\\n\\n")
        out.append("CONFIRMATIONS\\n")
        sig.reasons.take(8).forEach{out.append("➜ ").append(it).append("\\n")}
        val life=SignalStore.lifecycleReason(this,sig.id)
        val live=SignalStore.liveValidityReason(this,sig.id)
        val conclusion=forcedConclusion?:when(a.state){
            "PENDING"->live.ifBlank{"Pending setup is still valid; live price and structure are being monitored continuously."}
            "ACTIVE"->"Entry was reached. Trade is ACTIVE and TP1/SL are being tracked continuously."
            "WIN"->"TP1 was reached. Record closed as WIN."
            "LOSS"->"SL was reached. Record closed as LOSS."
            "EXPIRED"->life.ifBlank{live.ifBlank{"Setup became invalid before entry."}}
            else->life.ifBlank{live.ifBlank{a.state}}
        }
        out.append("\\nCONCLUSION\\n").append(arrowLines(conclusion))
        if(a.state=="EXPIRED"&&life.isNotBlank()&&life!=conclusion)out.append("\\n").append(arrowLines(life))
        return out.toString()
    }'''
s=s[:start]+new_show+s[end:]

# Replace records dialog to include pending/open and expiry reason.
start=s.index('    private fun showRecords(){')
end=s.index('\n\n    private fun alarmAndShow()',start)
new_records='''    private fun showRecords(){
        val days=lastThreeDays()
        val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(12),dp(8),dp(12),dp(8))}
        val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV29,android.R.layout.simple_spinner_dropdown_item,days)}
        val tv=TextView(this).apply{setTextColor(Color.BLACK);textSize=13f;setPadding(0,dp(10),0,dp(10))}
        fun refresh(){
            val day=sp.selectedItem?.toString()?:days.first()
            val b=StringBuilder(SignalStore.stats(this,day)).append("\\n\\n")
            val pending=SignalStore.pendingForDay(this,day)
            val active=SignalStore.openForDay(this,day)
            val closed=SignalStore.recordsForDay(this,day)
            if(pending.isNotEmpty()){
                b.append("PENDING SETUPS\\n")
                pending.forEach{a->b.append("➜ ${a.signal.symbol} ${a.signal.timeframe} • ${a.signal.direction} • ${a.signal.score}/100\\n   Entry ${price(a.signal.entry)} • ${SignalStore.liveValidityReason(this,a.signal.id).ifBlank{"Still valid / tracking"}}\\n")}
                b.append("\\n")
            }
            if(active.isNotEmpty()){
                b.append("ACTIVE / TRIGGERED\\n")
                active.forEach{a->b.append("➜ ${a.signal.symbol} ${a.signal.timeframe} • ${a.signal.direction}\\n   Entry ${price(a.signal.entry)} • TP1 ${price(a.signal.tp1)} • SL ${price(a.signal.sl)}\\n")}
                b.append("\\n")
            }
            if(closed.isNotEmpty()){
                b.append("CLOSED / EXPIRED\\n")
                closed.forEach{r->
                    b.append("➜ ${r.result} • ${r.symbol} ${r.timeframe} • ${r.direction} • ${r.score}/100\\n")
                    b.append("   Entry ${price(r.entry)} • TP1 ${price(r.tp1)} • SL ${price(r.sl)}\\n")
                    if(r.result=="EXPIRED"){
                        val why=SignalStore.lifecycleReason(this,r.id)
                        if(why.isNotBlank())b.append("   Reason: $why\\n")
                    }
                }
            }
            if(pending.isEmpty()&&active.isEmpty()&&closed.isEmpty())b.append("No records for this day.")
            tv.text=b.toString()
        }
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{
            override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()}
            override fun onNothingSelected(p:AdapterView<*>?){}
        }
        box.addView(sp);box.addView(ScrollView(this).apply{addView(tv)},LinearLayout.LayoutParams(-1,dp(440)))
        AlertDialog.Builder(this).setTitle("MS Records • Last 3 Days").setView(box)
            .setNeutralButton("Reset"){_,_->SignalStore.reset(this);showExisting()}
            .setNegativeButton("Close",null).show()
    }'''
s=s[:start]+new_records+s[end:]

# Replace alarm dialog with persistent per-item ON/OFF switch behavior.
start=s.index('    private fun alarmAndShow(){')
end=s.index('\n\n    private fun maybeShowOldSetupPopup()',start)
new_alarm='''    private fun alarmAndShow(){
        SignalStore.loadActive(this,symbol,period)?.takeIf{it.state=="PENDING"}?.let{a->
            if(AlarmStore.forSignal(this,a.signal.id)==null)AlarmStore.ensureArmed(this,a.signal)
        }
        val days=lastThreeDays()
        val outer=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(12),dp(8),dp(12),dp(8))}
        val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV29,android.R.layout.simple_spinner_dropdown_item,days)}
        val listBox=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
        fun refresh(){
            listBox.removeAllViews()
            val day=sp.selectedItem?.toString()?:days.first()
            val entries=AlarmStore.forDay(this,day)
            if(entries.isEmpty())listBox.addView(TextView(this).apply{text="No alarm history for this day.";setTextColor(Color.BLACK);setPadding(0,dp(12),0,dp(12))})
            entries.forEach{a->
                val block=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(0,dp(8),0,dp(8))}
                block.addView(TextView(this).apply{
                    text="${a.symbol} ${a.timeframe} • ${a.direction}\\nEntry ${price(a.entry)} • ${a.status}"
                    setTextColor(Color.BLACK)
                })
                val terminal=a.status in setOf("TRIGGERED","EXPIRED")
                block.addView(Button(this).apply{
                    text=if(terminal)a.status else if(a.enabled&&a.status=="ARMED")"ALARM: ON" else "ALARM: OFF"
                    isEnabled=!terminal
                    setOnClickListener{
                        val turnOn=!(a.enabled&&a.status=="ARMED")
                        AlarmStore.setEnabled(this@MainActivityV29,a.id,turnOn)
                        if(turnOn)startMonitorIfNeeded()
                        Toast.makeText(this@MainActivityV29,if(turnOn)"Entry alarm ON" else "Entry alarm OFF • lifecycle tracking stays active",Toast.LENGTH_SHORT).show()
                        refresh()
                    }
                },LinearLayout.LayoutParams(-1,dp(48)))
                listBox.addView(block)
            }
        }
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{
            override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()}
            override fun onNothingSelected(p:AdapterView<*>?){}
        }
        outer.addView(sp);outer.addView(ScrollView(this).apply{addView(listBox)},LinearLayout.LayoutParams(-1,dp(420)))
        AlertDialog.Builder(this).setTitle("MS Alarm Lifecycle").setView(outer).setNegativeButton("Close",null).show()
        startMonitorIfNeeded()
    }'''
s=s[:start]+new_alarm+s[end:]

p.write_text(s)

# ---------- OverlayService: chart gestures + same strong-only signal policy ----------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()

# WebView inside floating panel must own chart gestures/right price scale drag.
needle='''chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true);setBackgroundColor(Color.rgb(19,23,34));webViewClient='''
repl='''chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true);setBackgroundColor(Color.rgb(19,23,34));setOnTouchListener{v,e->when(e.actionMasked){MotionEvent.ACTION_DOWN,MotionEvent.ACTION_MOVE->v.parent?.requestDisallowInterceptTouchEvent(true);MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL->v.parent?.requestDisallowInterceptTouchEvent(false)};false};webViewClient='''
if needle not in s:
    raise SystemExit('Overlay chart touch anchor not found')
s=s.replace(needle,repl,1)

# Replace analyze method.
start=s.index('    private fun analyze(){')
end=s.index('\n    private fun startMonitor()',start)
new_analyze='''    private fun analyze(){
        if(busy)return
        val key=prefs.getString("api_key","")?.trim().orEmpty()
        if(key.isBlank()){status?.text="➜ Save analysis key in main app first";return}
        busy=true;status?.text="➜ Analyzing $symbol $period…";val s0=symbol;val p0=period
        thread{
            runCatching{FcsClient.seedForPeriod(key,s0,p0,true)}.onSuccess{pair->
                Handler(Looper.getMainLooper()).post{
                    busy=false;if(symbol!=s0||period!=p0)return@post
                    val data=pair.first
                    if(data.size<60){status?.text="➜ Not enough history";return@post}
                    SignalStore.evaluate(this,symbol,period,data)
                    val existing=SignalStore.loadActive(this,symbol,period)?:displayed()
                    val candidate=AnalysisEngine.analyze(symbol,period,data)
                    if(candidate==null){status?.text=existing?.let{stateText(it,"Previous signal is still valid; no stronger confirmation yet.")}?:"➜ No confirmed setup yet.";showState();return@post}
                    val dup=SignalStore.findDuplicate(this,candidate)
                    if(dup!=null){status?.text=stateText(dup,"Same setup confirmed again; previous signal remains valid.");overlay(dup);return@post}
                    if(existing!=null&&existing.state=="ACTIVE"){status?.text=stateText(existing,"Current trade is ACTIVE; no replacement is accepted.");overlay(existing);return@post}
                    if(existing!=null&&existing.state=="PENDING"){
                        val d=SignalStore.replacementDecision(existing,candidate)
                        if(!d.replace){status?.text=stateText(existing,d.reason);overlay(existing);return@post}
                    }
                    if(SignalStore.acceptCandidate(this,candidate))startMonitor()
                    showState()
                }
            }.onFailure{e->Handler(Looper.getMainLooper()).post{busy=false;status?.text="➜ Analysis unavailable: ${e.message}"}}
        }
    }
'''
s=s[:start]+new_analyze+s[end:]

# Replace compact state with arrows and lifecycle conclusion.
start=s.index('    private fun showState(){')
end=s.index('\n    private fun overlay(',start)
new_state='''    private fun showState(){
        val a=displayed()
        if(a==null){status?.text="➜ $symbol • $period • TradingView live\\n➜ Press NEW ANALYZE for setup";overlay(null);return}
        status?.text=stateText(a);overlay(a)
    }
    private fun stateText(a:ActiveSignal,conclusion:String?=null):String{
        val sig=a.signal
        val live=SignalStore.liveValidityReason(this,sig.id)
        val life=SignalStore.lifecycleReason(this,sig.id)
        val end=conclusion?:when(a.state){
            "PENDING"->live.ifBlank{"Previous setup remains valid and is being tracked live."}
            "ACTIVE"->"Entry reached; TP1/SL tracking is active."
            "EXPIRED"->life.ifBlank{"Setup expired before entry."}
            else->life.ifBlank{a.state}
        }
        return "➜ ${sig.direction} ${sig.score}/100 • ${a.state}\\n➜ Entry ${price(sig.entry)}\\n➜ SL ${price(sig.sl)}\\n➜ TP1 ${price(sig.tp1)}\\n➜ $end"
    }'''
s=s[:start]+new_state+s[end:]

p.write_text(s)

# ---------- TradingView: hide drawing toolbar + preserve native price-scale gestures ----------
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text()
s=s.replace('hide_side_toolbar:false','hide_side_toolbar:true')
s=s.replace('#widget{position:absolute;inset:0;z-index:1}', '#widget{position:absolute;inset:0;z-index:1;touch-action:none;-webkit-user-select:none;user-select:none}')
p.write_text(s)

# ---------- Version ----------
p=Path('app/build.gradle.kts')
s=p.read_text()
s=re.sub(r'versionCode = \d+','versionCode = 35',s)
s=re.sub(r'versionName = "[^"]+"','versionName = "35.0"',s)
p.write_text(s)

print('v35 continuous websocket lifecycle + UI/alarm/records patch applied')
