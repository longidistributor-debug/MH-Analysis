from pathlib import Path
import re

# ---------- FCS current-price snapshot ----------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()
if 'data class LatestSnapshot' not in s:
    s=s.replace(
        'object FcsClient {\n    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)\n',
        'object FcsClient {\n    data class LatestSnapshot(val active:Candle,val previous:Candle?,val update:Long)\n    private data class Cache(val at:Long,val candles:List<Candle>,val credits:Int)\n',1)

anchor='''    private fun putCache(symbol:String,period:String,data:List<Candle>,persist:Boolean){\n'''
if 'fun latest(accessKey:String' not in s:
    latest='''    /** Current-price endpoint used only for pending/open lifecycle tracking.\n     * It deliberately bypasses candle cache so Entry/SL/TP state follows the\n     * newest REST market snapshot instead of a previously seeded chart candle.\n     */\n    @Synchronized fun latest(accessKey:String,symbol:String,period:String="1m"):Pair<LatestSnapshot,Int>{\n        if(!canRequestNow())throw IllegalStateException("Waiting for next live-price request slot")\n        return try{val out=fetchLatest(symbol.uppercase(),accessKey,period);noteRequest();out}catch(e:Exception){noteRequest();throw e}\n    }\n\n    private fun fetchLatest(symbol:String,key:String,period:String):Pair<LatestSnapshot,Int>{\n        val group=if(symbol=="XAUUSD")"forex" else "crypto"\n        val ticker=if(symbol=="XAUUSD")"XAUUSD" else "BINANCE:BTCUSDT"\n        val type=if(symbol=="XAUUSD")"commodity" else "crypto"\n        val p=normalizePeriod(period)\n        val u="https://api-v4.fcsapi.com/$group/latest?symbol=${enc(ticker)}&period=${enc(p)}&type=${enc(type)}&get_profile=0&access_key=${enc(key)}"\n        val c=URL(u).openConnection() as HttpURLConnection;c.connectTimeout=12000;c.readTimeout=18000;c.requestMethod="GET"\n        val code=c.responseCode;val body=(if(code in 200..299)c.inputStream else c.errorStream).bufferedReader().use{it.readText()}\n        if(code !in 200..299)throw IllegalStateException("Live price HTTP $code")\n        val root=JSONObject(body);if(root.has("status")&&!root.optBoolean("status",true))throw IllegalStateException(root.optString("msg","Live price request failed"))\n        val credits=root.optJSONObject("info")?.optInt("credit_count",1)?:1\n        val response=root.opt("response")?:root.opt("data")?:root\n        val row:JSONObject=when(response){\n            is JSONArray->response.optJSONObject(0)\n            is JSONObject->{\n                if(response.has("active"))response else{\n                    val it=response.keys();var hit:JSONObject?=null\n                    while(it.hasNext()&&hit==null){val x=response.optJSONObject(it.next());if(x?.has("active")==true)hit=x}\n                    hit\n                }\n            }\n            else->null\n        }?:throw IllegalStateException("No live market snapshot returned")\n        fun candle(o:JSONObject?):Candle?{\n            if(o==null)return null;val close=o.optDouble("c",Double.NaN);if(close.isNaN())return null\n            val t=normalizeTs(o.optLong("t",row.optLong("update",System.currentTimeMillis()/1000L)))\n            return Candle(t,o.optDouble("o",close),o.optDouble("h",close),o.optDouble("l",close),close,o.optDouble("v",0.0))\n        }\n        val active=candle(row.optJSONObject("active"))?:candle(row)?:throw IllegalStateException("Live price response has no active candle")\n        val previous=candle(row.optJSONObject("previous"))\n        val update=normalizeTs(row.optLong("update",active.t))\n        return LatestSnapshot(active,previous,update) to credits\n    }\n\n'''
    if anchor not in s: raise SystemExit('FcsClient latest anchor not found')
    s=s.replace(anchor,latest+anchor,1)
p.write_text(s)

# ---------- Signal lifecycle: wall-clock live price tracking + pending records ----------
p=Path('app/src/main/java/com/mh/analysis/SignalStore.kt')
s=p.read_text()
anchor='''    fun expireAllPendingForVolatility(c:Context,symbol:String,at:Long=System.currentTimeMillis()):List<ProcessEvent>{\n'''
if 'fun processLivePrice(' not in s:
    live='''    /** Process a current market price using wall-clock observation time.\n     * This fixes the same-minute bug where candle-open timestamp is older than\n     * signal.createdAt even though price has already reached/passed Entry.\n     */\n    fun processLivePrice(c:Context,symbol:String,price:Double,at:Long=System.currentTimeMillis()):List<ProcessEvent>{\n        if(price.isNaN()||price.isInfinite())return emptyList()\n        val events=mutableListOf<ProcessEvent>()\n        pendingSignals(c).filter{it.signal.symbol==symbol}.forEach{pending->\n            val s=pending.signal;if(at<=s.createdAt)return@forEach\n            val reached=if(s.direction=="BUY")price<=s.entry else price>=s.entry\n            val ranAway=if(s.direction=="BUY")price>s.entry+s.atr*1.8 else price<s.entry-s.atr*1.8\n            if(reached){\n                clearActive(c,s.symbol,s.timeframe)\n                var active=ActiveSignal(s,at,pending.barsSeen+1,"ACTIVE");saveLast(c,active);AlarmStore.expireSignal(c,s.id,"TRIGGERED")\n                val hitSl=if(s.direction=="BUY")price<=s.sl else price>=s.sl\n                val hitTp=if(s.direction=="BUY")price>=s.tp1 else price<=s.tp1\n                if(hitSl||hitTp){\n                    val result=if(hitSl)"LOSS" else "WIN";active=active.copy(state=result);addRecord(c,toRecord(active,result,at));saveLast(c,active);events+=ProcessEvent(s,result,at)\n                }else{addOpen(c,active);events+=ProcessEvent(s,"ACTIVE",at)}\n            }else if(ranAway){\n                val expired=expirePending(c,pending,"Market moved too far from the untouched entry; original pending setup is no longer actionable.",at);events+=ProcessEvent(s,expired.state,at)\n            }\n        }\n        val all=openTrades(c).toMutableList();var changed=false;val it=all.listIterator()\n        while(it.hasNext()){\n            val a=it.next();val s=a.signal;if(s.symbol!=symbol||at<(a.activatedAt?:0L))continue\n            val hitSl=if(s.direction=="BUY")price<=s.sl else price>=s.sl\n            val hitTp=if(s.direction=="BUY")price>=s.tp1 else price<=s.tp1\n            if(hitSl||hitTp){\n                val result=if(hitSl)"LOSS" else "WIN";val done=a.copy(state=result);addRecord(c,toRecord(done,result,at));saveLast(c,done);it.remove();changed=true;events+=ProcessEvent(s,result,at)\n            }\n        }\n        if(changed)saveOpen(c,all)\n        return events\n    }\n\n'''
    if anchor not in s: raise SystemExit('SignalStore live anchor not found')
    s=s.replace(anchor,live+anchor,1)

old='''    fun recordsForDay(c:Context,day:String):List<TradeRecord>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return records(c).filter{f.format(Date(it.startedAt))==day}}\n    fun openForDay(c:Context,day:String):List<ActiveSignal>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return openTrades(c).filter{f.format(Date(it.signal.createdAt))==day}}\n'''
new='''    fun recordsForDay(c:Context,day:String):List<TradeRecord>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return records(c).filter{f.format(Date(it.startedAt))==day}}\n    fun pendingForDay(c:Context,day:String):List<ActiveSignal>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return pendingSignals(c).filter{f.format(Date(it.signal.createdAt))==day}}\n    fun openForDay(c:Context,day:String):List<ActiveSignal>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return openTrades(c).filter{f.format(Date(it.signal.createdAt))==day}}\n'''
if 'fun pendingForDay' not in s:
    if old not in s: raise SystemExit('SignalStore day anchor not found')
    s=s.replace(old,new,1)

old_stats='''    fun stats(c:Context,day:String?=null):String{\n        val r=if(day==null)records(c)else recordsForDay(c,day);val open=if(day==null)openTrades(c).size else openForDay(c,day).size;val wins=r.count{it.result=="WIN"};val losses=r.count{it.result=="LOSS"};val expired=r.count{it.result=="EXPIRED"};val resolved=wins+losses;val total=r.size+open\n        val wr=if(resolved==0)0.0 else wins*100.0/resolved;val lr=if(resolved==0)0.0 else losses*100.0/resolved;val er=if(total==0)0.0 else expired*100.0/total\n        return "Signals: $total   Open: $open   Resolved: $resolved\\nWins: $wins (${one(wr)}%)   Losses: $losses (${one(lr)}%)\\nExpired/Invalid: $expired (${one(er)}%)   Win ratio: ${one(wr)}%"\n    }\n'''
new_stats='''    fun stats(c:Context,day:String?=null):String{\n        val r=if(day==null)records(c)else recordsForDay(c,day)\n        val pending=if(day==null)pendingSignals(c).size else pendingForDay(c,day).size\n        val open=if(day==null)openTrades(c).size else openForDay(c,day).size\n        val wins=r.count{it.result=="WIN"};val losses=r.count{it.result=="LOSS"};val expired=r.count{it.result=="EXPIRED"};val resolved=wins+losses;val total=r.size+open+pending\n        val wr=if(resolved==0)0.0 else wins*100.0/resolved;val lr=if(resolved==0)0.0 else losses*100.0/resolved;val er=if(total==0)0.0 else expired*100.0/total\n        return "Signals: $total   Pending: $pending   Open: $open\\nResolved: $resolved   Wins: $wins (${one(wr)}%)   Losses: $losses (${one(lr)}%)\\nExpired/Invalid: $expired (${one(er)}%)   Win ratio: ${one(wr)}%"\n    }\n'''
if old_stats not in s: raise SystemExit('SignalStore stats anchor not found')
s=s.replace(old_stats,new_stats,1)
p.write_text(s)

# ---------- Background monitor: latest endpoint first, immediate state sync ----------
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
old_tasks='''            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()\n            val tasks=mutableListOf<Task>()\n            symbols.forEach{tasks+=Task("LIFE",it,"1m")}\n            pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.forEach{if(it.timeframe!="1m")tasks+=Task("STRUCT",it.symbol,it.timeframe)}\n            if(tasks.isEmpty()){scheduleNext(60_000L);return}\n            val task=tasks[cursor%tasks.size];cursor=(cursor+1)%100000\n'''
new_tasks='''            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()\n            val lifeTasks=symbols.map{Task("LIFE",it,"1m")}\n            val structureTasks=pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.filter{it.timeframe!="1m"}.map{Task("STRUCT",it.symbol,it.timeframe)}\n            if(lifeTasks.isEmpty()){scheduleNext(60_000L);return}\n            val useStructure=structureTasks.isNotEmpty()&&cursor%4==3\n            val task=if(useStructure)structureTasks[(cursor/4)%structureTasks.size] else lifeTasks[cursor%lifeTasks.size]\n            cursor=(cursor+1)%100000\n'''
if old_tasks not in s: raise SystemExit('AlarmService tasks anchor not found')
s=s.replace(old_tasks,new_tasks,1)
s=s.replace('finally{fetching=false;scheduleNext(22_000L)}','finally{fetching=false;scheduleNext(21_000L)}',1)

start=s.index('    private fun pollLifecycle(key:String,symbol:String){')
end=s.index('    private fun handleEvents(',start)
new_poll='''    private fun pollLifecycle(key:String,symbol:String){\n        val(snapshot,credits)=FcsClient.latest(key,symbol,"1m");addUsage(credits)\n        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}\n\n        // Previous closed candle is processed once for full OHLC path coverage.\n        snapshot.previous?.let{prev->\n            val cursorKey="life_latest_closed_$symbol"\n            val endAt=toMillis(prev.t)+60_000L\n            val lastDone=prefs.getLong(cursorKey,0L)\n            if(endAt>lastDone){\n                handleEvents(SignalStore.processMinuteCandle(this,symbol,prev),armedBefore)\n                // If the setup was created during that minute, candle-open timestamp\n                // alone cannot prove the crossing. Its close at candle-end can.\n                handleEvents(SignalStore.processLivePrice(this,symbol,prev.c,endAt),armedBefore)\n                prefs.edit().putLong(cursorKey,endAt).apply()\n            }\n        }\n\n        // Current active price is evaluated with observation time, not candle-open time.\n        handleEvents(SignalStore.processLivePrice(this,symbol,snapshot.active.c,System.currentTimeMillis()),armedBefore)\n        syncMonitorNotification()\n    }\n\n'''
s=s[:start]+new_poll+s[end:]

# Alarm fallback: an accepted setup must ring even if its AlarmStore row was repaired during the same tick.
s=s.replace('''                "ACTIVE"->{armedBefore[e.signal.id]?.let{triggerEntryAlarmOnce(it,e.signal)}}\n''','''                "ACTIVE"->{val a=armedBefore[e.signal.id]?:AlarmStore.forSignal(this,e.signal.id)?:AlarmStore.ensureArmed(this,e.signal);triggerEntryAlarmOnce(a,e.signal)}\n''',1)
s=s.replace('''                    armedBefore[e.signal.id]?.let{triggerEntryAlarmOnce(it,e.signal)}\n                    notifyTrade(e.signal,e.state)\n''','''                    val a=armedBefore[e.signal.id]?:AlarmStore.forSignal(this,e.signal.id)?:AlarmStore.ensureArmed(this,e.signal);triggerEntryAlarmOnce(a,e.signal)\n                    notifyTrade(e.signal,e.state)\n''',1)

# Keep service notification synchronized with actual stored lifecycle state.
anchor='''    private fun triggerEntryAlarmOnce(a:AlarmEntry,s:Signal){\n'''
if 'private fun syncMonitorNotification()' not in s:
    sync='''    private fun syncMonitorNotification(){\n        val p=SignalStore.pendingSignals(this);val o=SignalStore.openTrades(this)\n        val text=when{\n            o.isNotEmpty()->{val a=o.first();"ACTIVE • ${a.signal.symbol} ${a.signal.timeframe} • ${p.size} pending • ${o.size} open"}\n            p.isNotEmpty()->{val a=p.first();"PENDING • ${a.signal.symbol} ${a.signal.timeframe} • ${p.size} pending • 0 open"}\n            else->"No pending/open trades • lifecycle complete"\n        }\n        updateService(text)\n    }\n\n'''
    if anchor not in s: raise SystemExit('AlarmService sync anchor not found')
    s=s.replace(anchor,sync+anchor,1)

# Exact requested alarm pattern: 6s ring, 10s silent, repeated three times.
s=s.replace('vibrate(10_000L)\n                sleep(10_000L)','vibrate(6_000L)\n                sleep(6_000L)',1)

# Fresh Android notification channels so old silent/misconfigured channel settings do not persist.
s=s.replace('mh_alert_v31','mh_alert_v34').replace('mh_monitor_v31','mh_monitor_v34')
p.write_text(s)

# ---------- Main app live state refresh + pending/open/closed records ----------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()
field='''    private var candles:List<Candle> = emptyList()\n'''
if 'private val lifecycleUiHandler' not in s:
    add='''    private var candles:List<Candle> = emptyList()\n    private val lifecycleUiHandler=Handler(Looper.getMainLooper())\n    private var lastLifecycleUiKey=""\n    private val lifecycleUiRefresh:Runnable=object:Runnable{\n        override fun run(){\n            if(!busy&&::status.isInitialized){\n                val a=currentDisplayedSignal();val key=a?.let{"${it.signal.id}|${it.state}|${it.activatedAt}"}?:"none"\n                if(key!=lastLifecycleUiKey){lastLifecycleUiKey=key;showExisting()}\n            }\n            lifecycleUiHandler.postDelayed(this,1500L)\n        }\n    }\n'''
    if field not in s: raise SystemExit('MainActivity field anchor not found')
    s=s.replace(field,add,1)

anchor='''    private fun buildUi():View{\n'''
if 'override fun onResume()' not in s:
    hooks='''    override fun onResume(){super.onResume();lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);lifecycleUiHandler.post(lifecycleUiRefresh)}\n    override fun onPause(){lifecycleUiHandler.removeCallbacks(lifecycleUiRefresh);super.onPause()}\n\n'''
    if anchor not in s: raise SystemExit('MainActivity lifecycle anchor not found')
    s=s.replace(anchor,hooks+anchor,1)

needle='''SignalStore.openForDay(this,day).forEach{b.append("OPEN ${it.signal.symbol} ${it.signal.timeframe} ${it.signal.direction} Entry ${price(it.signal.entry)}\\n")};SignalStore.recordsForDay(this,day).forEach{b.append("${it.result} ${it.symbol} ${it.timeframe} ${it.direction} ${it.score}/100\\n")}'''
replacement='''SignalStore.pendingForDay(this,day).forEach{b.append("PENDING ${it.signal.symbol} ${it.signal.timeframe} ${it.signal.direction} Entry ${price(it.signal.entry)}\\n")};SignalStore.openForDay(this,day).forEach{b.append("ACTIVE ${it.signal.symbol} ${it.signal.timeframe} ${it.signal.direction} Entry ${price(it.signal.entry)}\\n")};SignalStore.recordsForDay(this,day).forEach{b.append("${it.result} ${it.symbol} ${it.timeframe} ${it.direction} ${it.score}/100 • Entry ${price(it.entry)} • TP1 ${price(it.tp1)} • SL ${price(it.sl)}\\n")}'''
if needle not in s: raise SystemExit('MainActivity records anchor not found')
s=s.replace(needle,replacement,1)
p.write_text(s)

# ---------- Floating screen automatically follows lifecycle changes ----------
p=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
s=p.read_text()
field='''    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)};private var symbol="XAUUSD";private var period="15m";private var busy=false\n'''
if 'private val panelUiHandler' not in s:
    repl='''    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)};private var symbol="XAUUSD";private var period="15m";private var busy=false\n    private val panelUiHandler=Handler(Looper.getMainLooper())\n    private val panelUiRefresh:Runnable=object:Runnable{override fun run(){if(panel!=null&&!busy)showState();if(panel!=null)panelUiHandler.postDelayed(this,1500L)}}\n'''
    if field not in s: raise SystemExit('Overlay field anchor not found')
    s=s.replace(field,repl,1)

needle='''        wm.addView(root,WindowManager.LayoutParams(dp(390),dp(720),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.END;x=dp(6);y=dp(35)})}\n'''
repl='''        wm.addView(root,WindowManager.LayoutParams(dp(390),dp(720),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.END;x=dp(6);y=dp(35)});panelUiHandler.removeCallbacks(panelUiRefresh);panelUiHandler.post(panelUiRefresh)}\n'''
if needle not in s: raise SystemExit('Overlay showPanel anchor not found')
s=s.replace(needle,repl,1)
s=s.replace('''    private fun hidePanel(){panel?.let{runCatching{wm.removeView(it)}};panel=null;chart=null;status=null;busy=false}\n''','''    private fun hidePanel(){panelUiHandler.removeCallbacks(panelUiRefresh);panel?.let{runCatching{wm.removeView(it)}};panel=null;chart=null;status=null;busy=false}\n''',1)
p.write_text(s)

# ---------- TradingView: chart only on left, no drawing toolbar ----------
p=Path('app/src/main/assets/tradingview_live.html')
s=p.read_text().replace('hide_side_toolbar:false','hide_side_toolbar:true')
p.write_text(s)

# ---------- Version ----------
p=Path('app/build.gradle.kts')
s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 34',s);s=re.sub(r'versionName = "[^"]+"','versionName = "34.0"',s);p.write_text(s)
print('v34 lifecycle/alarms/records/TradingView cleanup patch applied')
