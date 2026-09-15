from pathlib import Path

# Launcher activity: one visible FCS WebSocket while foreground, native background socket only when app leaves foreground.
p=Path('app/src/main/java/com/mh/analysis/MainActivityV24.kt')
s=p.read_text()

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Missing MainActivityV24 patch target:\n'+old[:220])
    s=s.replace(old,new,1)

rep('override fun onCreate(b:Bundle?){super.onCreate(b);FcsClient.init(this);if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12);window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK;symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";setContentView(buildUi());if(savedSocketKey().isNotBlank())startStateService()}',
'''override fun onCreate(b:Bundle?){super.onCreate(b);FcsClient.init(this);if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12);window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK;symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";prefs.edit().putBoolean("visible_socket_owner",true).apply();setContentView(buildUi());if(savedSocketKey().isNotBlank())sendServiceAction("VISIBLE_SOCKET_ON")}''')

rep('override fun onResume(){super.onResume();LiveSocketHub.addListener(this);if(savedSocketKey().isNotBlank())LiveSocketHub.start(this,savedSocketKey());if(chartReady)startVisibleSocket();restoreChart();showExisting()}',
'''override fun onResume(){super.onResume();prefs.edit().putBoolean("visible_socket_owner",true).apply();if(savedSocketKey().isNotBlank())sendServiceAction("VISIBLE_SOCKET_ON");if(chartReady)startVisibleSocket();restoreChart();showExisting()}''')

rep('override fun onPause(){LiveSocketHub.removeListener(this);super.onPause()}',
'''override fun onPause(){if(chartReady)chart.evaluateJavascript("pauseLiveChart()",null);prefs.edit().putBoolean("visible_socket_owner",false).apply();if(savedSocketKey().isNotBlank())sendServiceAction("BACKGROUND_SOCKET_ON");super.onPause()}''')

rep('settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);addJavascriptInterface(JsBridge(),"AndroidLive")',
'''settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.allowFileAccess=true;settings.allowContentAccess=true;settings.allowFileAccessFromFileURLs=true;settings.allowUniversalAccessFromFileURLs=true;settings.javaScriptCanOpenWindowsAutomatically=true;setBackgroundColor(Color.BLACK);addJavascriptInterface(JsBridge(),"AndroidLive")''')

rep('private fun startVisibleSocket(){if(!chartReady)return;val k=savedSocketKey();if(k.isBlank()){socketStatus.text="● WEBSOCKET KEY REQUIRED ONCE";return};chart.evaluateJavascript("startFcsLive(${JSONObject.quote(k)})",null)}',
'''private fun startVisibleSocket(){
        if(!chartReady)return
        val access=savedHistoryKey();val socket=savedSocketKey()
        if(access.isBlank()){socketStatus.text="● ANALYSIS/HISTORY KEY REQUIRED FOR FCS CHART";return}
        if(socket.isBlank()){socketStatus.text="● WEBSOCKET KEY REQUIRED ONCE";return}
        prefs.edit().putBoolean("visible_socket_owner",true).apply();sendServiceAction("VISIBLE_SOCKET_ON")
        val js="initLiveChart(${JSONObject.quote(access)},${JSONObject.quote(socket)},${JSONObject.quote(symbol)},${JSONObject.quote(period)},'')"
        chart.evaluateJavascript(js,null)
    }''')

rep('private fun switchVisibleFeed(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("selectLive(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);restoreChart();showExisting()}',
'''private fun switchVisibleFeed(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("switchLiveChart(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);restoreChart();showExisting()}''')

rep('private fun sendLiveTickToService(s:String,c:Candle){val i=Intent(this,AlarmService::class.java).apply{action="JS_LIVE_TICK";putExtra("symbol",s);putExtra("t",c.t);putExtra("o",c.o);putExtra("h",c.h);putExtra("l",c.l);putExtra("c",c.c);putExtra("v",c.v)};if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}',
'''private fun sendLiveTickToService(s:String,c:Candle){val i=Intent(this,AlarmService::class.java).apply{action="JS_LIVE_TICK";putExtra("symbol",s);putExtra("timeframe",period);putExtra("t",c.t);putExtra("o",c.c);putExtra("h",c.c);putExtra("l",c.c);putExtra("c",c.c);putExtra("v",c.v)};if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}''')

start='''    private fun analyzeNow(){
        val current=FcsClient.peek(symbol,period,220).orEmpty();if(current.size>=60){candles=current;loadedSymbol=symbol;loadedPeriod=period;performAnalysis();return}
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE HISTORY ACCESS KEY ONCE • LIVE WEBSOCKET CHART CONTINUES";return};if(busy)return;busy=true;status.text="NEW ANALYZE • loading historical depth for $symbol $period…"
        thread{try{val(out,credits)=FcsClient.seedForPeriod(key,symbol,period,false);runOnUiThread{busy=false;if(credits>0)addUsage(credits);calls.text="Analysis history calls: ${usage()}/500";candles=out;loadedSymbol=symbol;loadedPeriod=period;renderHistory(out);performAnalysis()}}catch(e:Exception){runOnUiThread{busy=false;status.text="ANALYSIS HISTORY ERROR\\n${e.message}\\nLive WebSocket chart remains active."}}}
    }'''
new='''    private fun analyzeNow(){
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS/HISTORY KEY ONCE • LIVE FCS CHART CONTINUES";return}
        if(busy){status.text="ANALYSIS REQUEST ALREADY RUNNING • LIVE CHART CONTINUES";return}
        busy=true;val reqSymbol=symbol;val reqPeriod=period;status.text="NEW ANALYZE • fresh $reqSymbol $reqPeriod structure request…"
        thread{try{val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true);runOnUiThread{busy=false;if(credits>0)addUsage(credits);calls.text="Analysis history calls: ${usage()}/500";if(reqSymbol!=symbol||reqPeriod!=period){status.text="MARKET CHANGED • press NEW ANALYZE for $symbol $period";return@runOnUiThread};candles=out;loadedSymbol=reqSymbol;loadedPeriod=reqPeriod;performAnalysis()}}catch(e:Exception){runOnUiThread{busy=false;val fallback=FcsClient.peek(reqSymbol,reqPeriod,220).orEmpty();if(reqSymbol==symbol&&reqPeriod==period&&fallback.size>=60){candles=fallback;loadedSymbol=reqSymbol;loadedPeriod=reqPeriod;status.text="PROVIDER REFRESH UNAVAILABLE • analyzing latest saved market depth";performAnalysis()}else status.text="ANALYSIS DATA ERROR\\n${e.message}\\nLive FCS WebSocket chart remains active."}}}
    }'''
rep(start,new)

rep('private fun saveHistoryKey(){if(savedHistoryKey().isNotBlank()&&!editHistory){editHistory=true;updateKeyUi();return};val x=historyInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();editHistory=false;historyInput.setText("");updateKeyUi();Toast.makeText(this,"Analysis/history key saved",Toast.LENGTH_SHORT).show()}',
'''private fun saveHistoryKey(){if(savedHistoryKey().isNotBlank()&&!editHistory){editHistory=true;updateKeyUi();return};val x=historyInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();editHistory=false;historyInput.setText("");updateKeyUi();if(savedSocketKey().isNotBlank())startVisibleSocket();Toast.makeText(this,"Analysis/history key saved",Toast.LENGTH_SHORT).show()}''')

rep('private fun saveSocketKey(){if(savedSocketKey().isNotBlank()&&!editSocket){editSocket=true;updateKeyUi();return};val x=socketInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("socket_api_key",x).apply();editSocket=false;socketInput.setText("");updateKeyUi();startVisibleSocket();LiveSocketHub.start(this,x);startStateService();Toast.makeText(this,"WebSocket key saved • live chart starting",Toast.LENGTH_LONG).show()}',
'''private fun saveSocketKey(){if(savedSocketKey().isNotBlank()&&!editSocket){editSocket=true;updateKeyUi();return};val x=socketInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("socket_api_key",x).putBoolean("visible_socket_owner",true).apply();editSocket=false;socketInput.setText("");updateKeyUi();sendServiceAction("VISIBLE_SOCKET_ON");startVisibleSocket();Toast.makeText(this,"WebSocket key saved • official FCS live chart starting",Toast.LENGTH_LONG).show()}''')

rep('private fun startStateService(){if(savedSocketKey().isBlank())return;val i=Intent(this,AlarmService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}',
'''private fun startStateService(){if(savedSocketKey().isBlank())return;sendServiceAction(if(prefs.getBoolean("visible_socket_owner",false))"VISIBLE_SOCKET_ON" else "BACKGROUND_SOCKET_ON")}
    private fun sendServiceAction(actionName:String){val i=Intent(this,AlarmService::class.java).apply{action=actionName};if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}''')

s=s.replace('MS • v24 • WEBSOCKET-FIRST LIVE CHART','MS • v25 • SINGLE LIVE SOCKET ENGINE')
p.write_text(s)

# Background service: never compete with the foreground chart for the socket key.
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()

def rep2(old,new):
    global s
    if old not in s:
        raise SystemExit('Missing AlarmService patch target:\n'+old[:220])
    s=s.replace(old,new,1)

rep2('private val statusTick=object:Runnable{override fun run(){if(running){updateService("${if(LiveSocketHub.isConnected())"BACKGROUND LIVE" else "BACKGROUND RECONNECTING"} • Pending ${SignalStore.pendingSignals(this@AlarmService).size} • Open ${SignalStore.openTrades(this@AlarmService).size} • Armed ${AlarmStore.armed(this@AlarmService).size}");h.postDelayed(this,10_000)}}}',
'''private val statusTick=object:Runnable{override fun run(){if(running){val visible=prefs.getBoolean("visible_socket_owner",false);val feed=if(visible)"VISIBLE FCS CHART FEED" else if(LiveSocketHub.isConnected())"BACKGROUND LIVE" else "BACKGROUND RECONNECTING";updateService("$feed • Pending ${SignalStore.pendingSignals(this@AlarmService).size} • Open ${SignalStore.openTrades(this@AlarmService).size} • Armed ${AlarmStore.armed(this@AlarmService).size}");h.postDelayed(this,10_000)}}}''')

rep2('override fun onCreate(){super.onCreate();FcsClient.init(this);createChannels();startForeground(311,serviceNotification("Starting continuous live market engine"));LiveSocketHub.addListener(this);val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k) else updateService("Live stream key required");h.post(statusTick)}',
'''override fun onCreate(){super.onCreate();FcsClient.init(this);createChannels();startForeground(311,serviceNotification("Starting continuous live market engine"));LiveSocketHub.addListener(this);val visible=prefs.getBoolean("visible_socket_owner",false);val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(!visible&&k.isNotBlank())LiveSocketHub.start(this,k) else if(visible)updateService("VISIBLE FCS CHART OWNS LIVE CONNECTION") else updateService("Live stream key required");h.post(statusTick)}''')

old='''    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{
        if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY}
        if(intent?.action=="JS_LIVE_TICK"){
            val s=intent.getStringExtra("symbol")?:return START_STICKY
            val c=Candle(intent.getLongExtra("t",0L),intent.getDoubleExtra("o",0.0),intent.getDoubleExtra("h",0.0),intent.getDoubleExtra("l",0.0),intent.getDoubleExtra("c",0.0),intent.getDoubleExtra("v",0.0))
            if(c.c>0)thread(name="mh-js-live-tick"){processLifecycleTick(s,c)}
            return START_STICKY
        }
        val k=prefs.getString("socket_api_key","")?.trim().orEmpty()
        if(k.isNotBlank())LiveSocketHub.start(this,k)
        return START_STICKY
    }'''
new='''    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{
        when(intent?.action){
            "STOP"->{stopSelf();return START_NOT_STICKY}
            "VISIBLE_SOCKET_ON"->{prefs.edit().putBoolean("visible_socket_owner",true).apply();LiveSocketHub.stop();updateService("VISIBLE FCS CHART OWNS LIVE CONNECTION");return START_STICKY}
            "BACKGROUND_SOCKET_ON"->{prefs.edit().putBoolean("visible_socket_owner",false).apply();val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k);return START_STICKY}
            "JS_LIVE_TICK"->{
                val s=intent.getStringExtra("symbol")?:return START_STICKY
                val tf=intent.getStringExtra("timeframe")?:"1m"
                val price=intent.getDoubleExtra("c",0.0);if(price<=0)return START_STICKY
                val c=Candle(intent.getLongExtra("t",0L),price,price,price,price,intent.getDoubleExtra("v",0.0))
                thread(name="mh-visible-live-tick"){processLifecycleTick(s,c);val key="$s|$tf";val now=System.currentTimeMillis();val prior=lastEval[key]?:0L;if(now-prior>=5_000L){lastEval[key]=now;validatePendingOnTimeframe(s,tf)}}
                return START_STICKY
            }
        }
        if(!prefs.getBoolean("visible_socket_owner",false)){val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k)}
        return START_STICKY
    }'''
rep2(old,new)
p.write_text(s)

# Native background WebSocket should look like the browser client when the app hands off to background.
p=Path('app/src/main/java/com/mh/analysis/LiveSocketHub.kt')
s=p.read_text()
old='val req=Request.Builder().url("$SOCKET_URL?access_key=${apiKey}").build()'
new='val req=Request.Builder().url("$SOCKET_URL?access_key=${apiKey}").header("Origin","https://fcsapi.com").header("User-Agent","Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 Chrome/153 Mobile Safari/537.36").build()'
if old not in s: raise SystemExit('Missing LiveSocketHub request target')
s=s.replace(old,new,1)
p.write_text(s)
