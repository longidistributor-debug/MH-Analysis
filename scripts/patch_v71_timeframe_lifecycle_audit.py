from pathlib import Path
import re

# v71:
# - Fix timeframe switching / endless-loading by removing network I/O from the
#   global FcsClient monitor and making manual requests cancellable by generation.
# - Support every app timeframe independently: 1m,5m,10m,15m,30m,1h,2h,4h,5h,1d,1w,1M.
# - No fixed candle-count expiry. Pending validity follows CURRENT selected-TF
#   structure/momentum; 1m lifecycle is only for Entry/SL/TP observation.
# - Current price can trigger Entry/SL/TP between candle closes through the
#   existing origin-aware processLivePrice lifecycle.
# - Remove random 1m volatility / ran-away auto-expiry paths.
# - ANALYZE = a new full current-market analysis; RE-EVALUATE = fresh validation
#   of the current signal and reports a materially changed/new setup if detected.
# - Preserve all existing video-reference/indicator/setup logic and TradingView visual-only.

# -----------------------------------------------------------------------------
# FcsClient: concurrency-safe but do NOT hold object monitor during HTTP.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Ensure all supported caches can be restored.
s=re.sub(r'private val periods=listOf\([^\n]+\)',
         'private val periods=listOf("1m","5m","10m","15m","30m","1h","2h","4h","5h","1d","1w","1M")',s,count=1)

# Network methods must not hold the FcsClient intrinsic lock while waiting on HTTP.
s=s.replace('@Synchronized fun history(', 'fun history(')
s=s.replace('@Synchronized fun bootstrap(', 'fun bootstrap(')
s=s.replace('@Synchronized fun refreshPreviousCompletedDay(', 'fun refreshPreviousCompletedDay(')

start=s.index('    @Synchronized fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{')
end=s.index('\n\n    /** Best-effort background fill.',start)
new_seed=r'''    fun seedForPeriod(accessKey:String,symbol:String,period:String,force:Boolean=false):Pair<List<Candle>,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())throw IllegalStateException("ANALYSIS KEY REQUIRED")
        val sym=symbol.uppercase();val tf=normalizePeriod(period)
        if(sym!="XAUUSD")throw IllegalStateException("Only XAUUSD is supported")

        fun clean(data:List<Candle>):List<Candle> = data
            .map{it.copy(t=normalizeTs(it.t))}
            .filter{it.t>0L&&it.o.isFinite()&&it.h.isFinite()&&it.l.isFinite()&&it.c.isFinite()}
            .distinctBy{it.t}.sortedBy{it.t}
        fun stepSeconds():Long=when(tf){
            "1m"->60L;"5m"->300L;"10m"->600L;"15m"->900L;"30m"->1800L;
            "1h"->3600L;"2h"->7200L;"4h"->14400L;"5h"->18000L;
            "1d"->86400L;"1w"->604800L;"1M"->2592000L;else->900L
        }
        fun recent(data:List<Candle>):Boolean{
            val x=clean(data);if(x.size<100)return false
            val age=(System.currentTimeMillis()/1000L-x.last().t).coerceAtLeast(0L)
            return age<=stepSeconds()*3L+300L
        }

        val current=synchronized(this){cache[cacheKey(sym,tf)]?.candles?.toList().orEmpty()}
        if(current.size>=100&&!force)return clean(current).takeLast(300) to 0

        // Manual Analyze/Re-evaluate gets priority. Background tracking obeys the
        // local request window and may safely reuse only a recent TF cache.
        val manual=Thread.currentThread().name.startsWith("mh-manual-")
        if(!manual&&!canRequestNow()){
            if(recent(current))return clean(current).takeLast(300) to 0
            throw IllegalStateException("MARKET HISTORY TEMPORARILY BUSY")
        }

        val requested:Pair<List<Candle>,Int>
        try{
            requested=when(tf){
                // 10m is the only synthetic TF: use enough 5m rows to retain
                // >=100 independent 10m candles after aggregation.
                "10m"->{val r=fetchMarket(sym,cleanKey,"5m",260);aggregate(clean(r.first),10) to r.second}
                // 5h is supported natively; do NOT aggregate only 180 1h bars,
                // which produced too few 5h candles in v70.
                "1m","5m","15m","30m","1h","2h","4h","5h","1d","1w","1M"->
                    fetchMarket(sym,cleanKey,tf,180).let{clean(it.first) to it.second}
                else->throw IllegalStateException("Unsupported timeframe $tf")
            }
            noteRequest()
        }catch(e:Exception){
            noteRequest()
            if(recent(current))return clean(current).takeLast(300) to 0
            throw e
        }

        val fresh=clean(requested.first)
        if(fresh.size<100){
            if(recent(current))return clean(current).takeLast(300) to 0
            throw IllegalStateException("CURRENT $tf HISTORY INCOMPLETE")
        }
        if(!recent(fresh)){
            if(recent(current))return clean(current).takeLast(300) to 0
            throw IllegalStateException("CURRENT $tf HISTORY NOT RECENT")
        }
        synchronized(this){putCache(sym,tf,fresh,true)}
        return fresh.takeLast(300) to requested.second
    }'''
s=s[:start]+new_seed+s[end:]

# Request-window queue can be touched from UI and service threads now.
if 'private val requestGate=Any()' not in s:
    s=s.replace('private val requestTimes=ArrayDeque<Long>()','private val requestTimes=ArrayDeque<Long>()\n    private val requestGate=Any()',1)
s=re.sub(r'''    private fun trimWindow\(\)\{[^\n]+\}\n    private fun canRequestNow\(\):Boolean\{[^\n]+\}\n    private fun noteRequest\(\)\{[^\n]+\}''',r'''    private fun trimWindowLocked(){val now=System.currentTimeMillis();while(requestTimes.isNotEmpty()&&now-requestTimes.first()>=REQUEST_WINDOW_MS)requestTimes.removeFirst()}
    private fun canRequestNow():Boolean=synchronized(requestGate){trimWindowLocked();requestTimes.size<MAX_REQUESTS_PER_WINDOW}
    private fun noteRequest(){synchronized(requestGate){requestTimes.addLast(System.currentTimeMillis());trimWindowLocked()}}''',s,count=1)

# Bound a dead/slow request so changing TF never leaves the product apparently stuck.
s=re.sub(r'c\.connectTimeout=\d+;c\.readTimeout=\d+', 'c.connectTimeout=7000;c.readTimeout=11000', s, count=1)
p.write_text(s)

# -----------------------------------------------------------------------------
# SignalStore: selected-TF structure owns expiry; 1m owns Entry/SL/TP only.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()

# Clear old displayed last signals when a NEW manual analysis replaces the symbol.
anchor='''    fun clearActiveForSymbol(c:Context,symbol:String){
        val prefix="active_${symbol.uppercase()}_"
        val e=prefs(c).edit();prefs(c).all.keys.filter{it.startsWith(prefix)}.forEach{e.remove(it)};e.apply()
    }'''
if 'fun clearLastForSymbol' not in s:
    helper=anchor+'''\n    fun clearLastForSymbol(c:Context,symbol:String){
        val prefix="last_${symbol.uppercase()}_"
        val e=prefs(c).edit();prefs(c).all.keys.filter{it.startsWith(prefix)}.forEach{e.remove(it)};e.apply()
    }
    fun primeLiveTracking(c:Context,s:Signal,price:Double){
        if(!price.isFinite())return
        prefs(c).edit()
            .putLong("live_origin_${s.id}",java.lang.Double.doubleToRawLongBits(price))
            .putLong("live_ref_${s.id}",java.lang.Double.doubleToRawLongBits(price))
            .apply()
    }'''
    if anchor not in s: raise SystemExit('v71 SignalStore clearActiveForSymbol anchor missing')
    s=s.replace(anchor,helper,1)

# Higher-timeframe evaluation must NOT trigger Entry from a large candle range.
# It only checks the original pending thesis against the CURRENT selected-TF data.
start=s.index('    fun evaluate(c:Context,symbol:String,timeframe:String,candles:List<Candle>):ActiveSignal?{')
end=s.index('\n\n    fun processMinuteCandle',start)
new_eval=r'''    fun evaluate(c:Context,symbol:String,timeframe:String,candles:List<Candle>):ActiveSignal?{
        val pending=loadActive(c,symbol,timeframe)?:return displayState(c,symbol,timeframe)
        if(pending.state!="PENDING")return pending
        if(candles.size<60)return pending
        val check=AnalysisEngine.setupCheck(pending.signal,candles)
        if(!check.valid)return expirePending(c,pending,check.reason,toMillis(candles.last().t))
        prefs(c).edit().putString("live_validity_${pending.signal.id}",check.reason).apply()
        return pending
    }'''
s=s[:start]+new_eval+s[end:]

# 1m range lifecycle: no arbitrary "ran away 1.8 ATR" expiry. Pending dies only
# from selected-timeframe setupCheck or real structural SL after activation.
start=s.index('    fun processMinuteCandle(c:Context,symbol:String,x:Candle):List<ProcessEvent>{')
end=s.index('\n\n    fun expireAllPendingForVolatility',start)
new_minute=r'''    fun processMinuteCandle(c:Context,symbol:String,x:Candle):List<ProcessEvent>{
        val events=mutableListOf<ProcessEvent>();val t=toMillis(x.t)
        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->
            val sig=pending.signal
            // Creation minute is handled by origin-aware live/current-price logic,
            // avoiding a false trigger from OHLC movement that happened before creation.
            if(t<=sig.createdAt)return@forEach
            val touched=x.l<=sig.entry&&x.h>=sig.entry
            if(touched){
                clearActive(c,sig.symbol,sig.timeframe)
                var active=ActiveSignal(sig,t,pending.barsSeen+1,"ACTIVE")
                saveLast(c,active)
                prefs(c).edit().putString("trigger_reason_${sig.id}","1m market range reached Entry ${fmtLifecyclePrice(sig.entry)} after signal creation.").apply()
                AlarmStore.expireSignal(c,sig.id,"TRIGGERED")
                val hitSl=if(sig.direction=="BUY")x.l<=sig.sl else x.h>=sig.sl
                val hitTp=if(sig.direction=="BUY")x.h>=sig.tp1 else x.l<=sig.tp1
                if(hitSl||hitTp){
                    val result=if(hitSl)"LOSS" else "WIN";active=active.copy(state=result)
                    addRecord(c,toRecord(active,result,t));saveLast(c,active);events+=ProcessEvent(sig,result,t)
                }else{addOpen(c,active);events+=ProcessEvent(sig,"ACTIVE",t)}
            }
        }
        val all=openTrades(c).toMutableList();var changed=false;val it=all.listIterator()
        while(it.hasNext()){
            val a=it.next();val sig=a.signal;if(sig.symbol!=symbol||t<(a.activatedAt?:0L))continue
            val hitSl=if(sig.direction=="BUY")x.l<=sig.sl else x.h>=sig.sl
            val hitTp=if(sig.direction=="BUY")x.h>=sig.tp1 else x.l<=sig.tp1
            if(hitSl||hitTp){
                val result=if(hitSl)"LOSS" else "WIN";val done=a.copy(state=result)
                addRecord(c,toRecord(done,result,t));saveLast(c,done);it.remove();changed=true;events+=ProcessEvent(sig,result,t)
            }
        }
        if(changed)saveOpen(c,all);return events
    }'''
s=s[:start]+new_minute+s[end:]

# No fixed-age concept anywhere in the current signal UI/lifecycle.
start=s.index('    fun isStale(a:ActiveSignal):Boolean{')
end=s.index('\n\n    private fun toRecord',start)
s=s[:start]+'''    fun isStale(a:ActiveSignal):Boolean=false\n'''+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# AlarmService: current price + selected-TF structure, no random 1m volatility expiry.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
start=s.index('    private fun pollLifecycle(key:String,symbol:String){')
end=s.index('\n\n    private fun handleEvents',start)
new_poll=r'''    private fun pollLifecycle(key:String,symbol:String){
        val(out,credits)=FcsClient.history(key,symbol,"1m",220,true);addUsage(credits)
        if(out.isEmpty())return
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        val cursorKey="life_closed_cursor_$symbol"
        val lastClosed=prefs.getLong(cursorKey,0L)
        val closed=if(out.size>1)out.dropLast(1).filter{toMillis(it.t)>lastClosed}.sortedBy{toMillis(it.t)} else emptyList()
        closed.forEach{x->
            handleEvents(SignalStore.processMinuteCandle(this,symbol,x),armedBefore)
            prefs.edit().putLong(cursorKey,toMillis(x.t)).apply()
        }
        // Current/running 1m close is an actual post-creation observation and can
        // trigger Entry/SL/TP immediately through origin-aware lifecycle logic.
        val live=out.last().c
        prefs.edit().putString("tracker_price_${symbol.uppercase()}",live.toString()).putLong("tracker_at_${symbol.uppercase()}",System.currentTimeMillis()).putString("tracker_source_${symbol.uppercase()}","CURRENT MARKET").apply()
        handleEvents(SignalStore.processLivePrice(this,symbol,live,System.currentTimeMillis(),"CURRENT MARKET"),armedBefore)
    }'''
s=s[:start]+new_poll+s[end:]

# When selected-TF structure invalidates a pending setup, audit the fresh engine
# once and tell the user if a materially different current setup now exists.
start=s.index('    private fun pollStructure(key:String,symbol:String,timeframe:String){')
end=s.index('\n\n    private fun fireThreeCycles',start)
new_struct=r'''    private fun pollStructure(key:String,symbol:String,timeframe:String){
        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)
        if(out.size<60)return
        val before=SignalStore.loadActive(this,symbol,timeframe)?:return
        SignalStore.evaluate(this,symbol,timeframe,out)
        val after=SignalStore.loadActive(this,symbol,timeframe)
        if(after==null||after.signal.id!=before.signal.id){
            var reason=SignalStore.lifecycleReason(this,before.signal.id).ifBlank{"Original pending setup is no longer structurally valid."}
            val fresh=runCatching{AnalysisEngine.analyze(symbol,timeframe,out)}.getOrNull()
            if(fresh!=null&&!AnalysisEngine.sameSetup(before.signal,fresh)){
                val hint="Current full analysis now detects ${fresh.direction} ${fresh.score}/100. Press ANALYZE to create/replace with this fresh setup."
                prefs.edit().putString("replacement_hint_${before.signal.id}",hint).apply()
                reason="$reason $hint"
            }
            notifySignalExpired(before.signal,reason)
        }
    }'''
s=s[:start]+new_struct+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: cancellable per-timeframe requests + dynamic state UI.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

if 'analysisRequestSerial' not in s:
    s=s.replace('    private var busy=false','    private var busy=false\n    @Volatile private var analysisRequestSerial=0L',1)

# Guarantee every supported timeframe is selectable.
s=re.sub(r'val periods=arrayOf\([^\n]+\)',
         'val periods=arrayOf("1m","5m","10m","15m","30m","1h","2h","4h","5h","1d","1w","1M")',s,count=1)

# Changing timeframe immediately releases the old UI request. Its result is later
# ignored by serial number, so an old slow request can never block the new TF.
old='if(np==period)return;period=np;prefs.edit().putString("period",period).apply();'
new='if(np==period)return;analysisRequestSerial++;busy=false;period=np;prefs.edit().putString("period",period).apply();'
if old in s:s=s.replace(old,new,1)
else:
    s,n=re.subn(r'if\(np==period\)return;\s*period=np;\s*prefs\.edit\(\)\.putString\("period",period\)\.apply\(\);',new,s,count=1)
    if n==0:raise SystemExit('v71 timeframe selection anchor missing')

# Live UI refresh: service-driven ACTIVE/EXPIRED/WIN/LOSS changes appear without
# requiring the user to leave/reopen the app.
if 'private val uiStateRefresh' not in s:
    insert=s.index('    private fun buildUi():View{')
    refresh=r'''    private val uiStateHandler by lazy{Handler(Looper.getMainLooper())}
    private val uiStateRefresh=object:Runnable{
        override fun run(){
            if(!busy&&::status.isInitialized)showExisting()
            uiStateHandler.postDelayed(this,5000L)
        }
    }
    override fun onResume(){super.onResume();uiStateHandler.removeCallbacks(uiStateRefresh);uiStateHandler.post(uiStateRefresh);startMonitorIfNeeded()}
    override fun onPause(){uiStateHandler.removeCallbacks(uiStateRefresh);super.onPause()}

'''
    s=s[:insert]+refresh+s[insert:]

# Replace ANALYZE with generation-aware request handling. Daily map refresh runs
# separately so it can never hold the selected-timeframe result on "loading".
start=s.index('    private fun analyzeNow(){')
end=s.index('\n\n    private fun performAnalysis(){',start)
new_analyze=r'''    private fun analyzeNow(){
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS KEY ONCE";return}
        val token=analysisRequestSerial+1L;analysisRequestSerial=token
        busy=true;val reqSymbol=symbol;val reqPeriod=period
        status.text="ANALYZING • $reqSymbol $reqPeriod CURRENT STRUCTURE…"
        thread(name="mh-manual-analyze-$token"){
            try{
                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)
                runOnUiThread{
                    if(token!=analysisRequestSerial)return@runOnUiThread
                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"
                    if(reqSymbol!=symbol||reqPeriod!=period){status.text="$symbol • $period • READY FOR ANALYZE";return@runOnUiThread}
                    candles=out;performAnalysis()
                }
                // Previous-day map refresh is independent of signal generation.
                if(reqSymbol=="XAUUSD")thread(name="mh-daily-map-refresh"){
                    runCatching{FcsClient.refreshPreviousCompletedDay(key)}.onSuccess{r->runOnUiThread{
                        if(r.second>0){addUsage(r.second);calls.text="Analysis calls: ${usage()}/500"}
                        if(token==analysisRequestSerial&&reqPeriod==period&&!busy)updateSnapshot(candles)
                    }}
                }
            }catch(e:Exception){runOnUiThread{
                if(token!=analysisRequestSerial)return@runOnUiThread
                busy=false
                status.text="CURRENT $reqPeriod MARKET HISTORY TEMPORARILY UNAVAILABLE • TRY AGAIN"
            }}
        }
    }'''
s=s[:start]+new_analyze+s[end:]

# Fresh Analyze is authoritative for the symbol. No old timeframe pending signal
# survives a completed new analysis. If there is no setup, old LAST display is
# cleared too; open/active trades remain lifecycle-tracked separately.
start=s.index('    private fun performAnalysis(){')
end=s.index('\n\n    private fun reEvaluateCurrent(){',start)
new_perform=r'''    private fun performAnalysis(){
        if(candles.size<100){status.text="NOT ENOUGH CURRENT $period HISTORY FOR RELIABLE ANALYSIS";return}
        SignalStore.clearActiveForSymbol(this,symbol)
        SignalStore.clearLastForSymbol(this,symbol)
        val candidate=AnalysisEngine.analyze(symbol,period,candles)
        if(candidate==null){
            status.text=AnalysisEngine.noSignalReason(symbol,period,candles)
            showSignalCard(null);updateSnapshot(candles);return
        }
        SignalStore.acceptCandidate(this,candidate)
        SignalStore.primeLiveTracking(this,candidate,candles.last().c)
        startMonitorIfNeeded()
        val accepted=SignalStore.loadActive(this,symbol,period)
        status.text=accepted?.let{formatManualSignal(it,"Fresh PENDING signal created from the current $period structure. Time/candle count alone will not expire it; live selected-timeframe structure controls validity.")}?:"SETUP ACCEPTED"
        showSignalCard(accepted);updateSnapshot(candles)
    }'''
s=s[:start]+new_perform+s[end:]

# RE-EVALUATE uses the same generation/cancellation rules and explicitly reports
# a different current full-engine setup without silently replacing the old one.
start=s.index('    private fun reEvaluateCurrent(){')
end=s.index('\n\n    private fun currentDisplayedSignal()',start)
new_re=r'''    private fun reEvaluateCurrent(){
        val displayed=SignalStore.displayState(this,symbol,period)
        if(displayed!=null&&displayed.state=="ACTIVE"){
            status.text=formatManualSignal(displayed,"Trade is ACTIVE. Entry has already triggered; lifecycle tracking now follows SL/TP rather than replacing the active trade.")
            return
        }
        val current=SignalStore.loadActive(this,symbol,period)
        if(current==null){status.text="NO CURRENT $period PENDING SIGNAL • press ANALYZE first";return}
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS KEY ONCE";return}
        val token=analysisRequestSerial+1L;analysisRequestSerial=token
        busy=true;val reqSymbol=symbol;val reqPeriod=period
        status.text="RE-EVALUATING • $reqSymbol $reqPeriod CURRENT STRUCTURE…"
        thread(name="mh-manual-reevaluate-$token"){
            try{
                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)
                runOnUiThread{
                    if(token!=analysisRequestSerial)return@runOnUiThread
                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"
                    if(reqSymbol!=symbol||reqPeriod!=period){status.text="$symbol • $period • READY FOR RE-EVALUATION";return@runOnUiThread}
                    val latest=SignalStore.loadActive(this,reqSymbol,reqPeriod)
                    if(latest==null||latest.signal.id!=current.signal.id){showExisting();return@runOnUiThread}
                    candles=out
                    val result=AnalysisEngine.reEvaluateSignal(latest.signal,out)
                    var conclusion=result.reason
                    result.freshSignal?.let{fresh->
                        if(!AnalysisEngine.sameSetup(latest.signal,fresh)){
                            conclusion+=" Current full analysis detects ${fresh.direction} ${fresh.score}/100 as a materially different setup. Press ANALYZE to replace the saved signal with the fresh setup."
                        }
                    }
                    val next=SignalStore.setManualState(this,latest,result.state,conclusion)
                    if(next.state=="PENDING"||next.state=="STILL VALID"||next.state=="WEAKENING")startMonitorIfNeeded()
                    status.text=formatManualSignal(next,conclusion);showSignalCard(next);updateSnapshot(out)
                }
            }catch(e:Exception){runOnUiThread{
                if(token!=analysisRequestSerial)return@runOnUiThread
                busy=false;status.text="CURRENT $reqPeriod RE-EVALUATION DATA TEMPORARILY UNAVAILABLE • SAVED SIGNAL UNCHANGED"
            }}
        }
    }'''
s=s[:start]+new_re+s[end:]

# Display service lifecycle states as well as pending manual signal.
s=s.replace('private fun currentDisplayedSignal()=SignalStore.loadActive(this,symbol,period)',
            'private fun currentDisplayedSignal()=SignalStore.displayState(this,symbol,period)',1)

# Add automatic lifecycle/new-setup reasons to the detailed output, without
# exposing backend/provider names.
needle='''        if(forcedConclusion!=null){out.append("\\nRE-EVALUATION\\n").append(arrowLines(forcedConclusion))}
        return out.toString().trim()'''
replacement='''        val autoReason=SignalStore.lifecycleReason(this,sig.id).trim()
        val replacementHint=getSharedPreferences("mh",MODE_PRIVATE).getString("replacement_hint_${sig.id}","").orEmpty().trim()
        if(forcedConclusion!=null){out.append("\\nRE-EVALUATION\\n").append(arrowLines(forcedConclusion))}
        if(autoReason.isNotBlank()||replacementHint.isNotBlank()){
            out.append("\\n\\nLIFECYCLE\\n")
            if(autoReason.isNotBlank())out.append(arrowLines(autoReason)).append("\\n")
            if(replacementHint.isNotBlank())out.append(arrowLines(replacementHint))
        }
        return out.toString().trim()'''
if needle in s:s=s.replace(needle,replacement,1)
else:raise SystemExit('v71 formatManualSignal output anchor missing')
p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 71',g);g=re.sub(r'versionName = "[^"]+"','versionName = "71.0"',g);p.write_text(g)
print('v71 timeframe responsiveness + dynamic lifecycle audit applied')
