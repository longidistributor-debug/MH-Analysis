from pathlib import Path
p=Path('app/src/main/java/com/mh/analysis/MainActivity.kt')
s=p.read_text()

def rep(old,new):
    global s
    if old not in s:
        raise SystemExit('Missing patch target:\n'+old[:180])
    s=s.replace(old,new,1)

rep('import android.webkit.WebView\nimport android.webkit.WebViewClient', 'import android.webkit.WebView\nimport android.webkit.WebViewClient\nimport android.webkit.JavascriptInterface')

rep('override fun onResume(){super.onResume();LiveSocketHub.addListener(this);if(savedSocketKey().isNotBlank())LiveSocketHub.start(this,savedSocketKey());showExisting();showStalePopupIfNeeded();if(Settings.canDrawOverlays(this)&&prefs.getBoolean("want_float",false)){prefs.edit().putBoolean("want_float",false).apply();startOverlay()}}',
    'override fun onResume(){super.onResume();showExisting();showStalePopupIfNeeded();if(Settings.canDrawOverlays(this)&&prefs.getBoolean("want_float",false)){prefs.edit().putBoolean("want_float",false).apply();startOverlay()}}')

rep('override fun onPause(){LiveSocketHub.removeListener(this);super.onPause()}', 'override fun onPause(){super.onPause()}')

rep('override fun onSocketState(state:String){runOnUiThread{if(::socketStatus.isInitialized)socketStatus.text="● $state"}}',
'''override fun onSocketState(state:String){ /* background native socket state is intentionally not shown on the visible FCS chart */ }
    inner class ChartBridge{
        @JavascriptInterface fun onSocketState(state:String){runOnUiThread{if(::socketStatus.isInitialized)socketStatus.text="● $state"}}
    }
    private fun initVisibleChart(){
        if(!chartReady)return
        val a=savedKey();val sk=savedSocketKey()
        if(a.isBlank()){socketStatus.text="● SAVE HISTORY KEY TO LOAD FCS LIVE CHART";return}
        if(sk.isBlank()){socketStatus.text="● SAVE LIVE STREAM KEY FOR LIVE CANDLES";return}
        val js="initLiveChart(${JSONObject.quote(a)},${JSONObject.quote(sk)},${JSONObject.quote(symbol)},${JSONObject.quote(period)},'')"
        chart.evaluateJavascript(js,null)
    }
    private fun switchVisibleChart(){
        if(!chartReady)return
        chart.evaluateJavascript("switchLiveChart(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null)
    }''')

rep('sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np==period)return;period=np;prefs.edit().putString("period",period).apply();cancelPendingAnalyze();showCachedOrSwitching();if(!FcsClient.hasUsableHistory(symbol,period,60))load(false)};override fun onNothingSelected(p:AdapterView<*>?){}}',
    'sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np==period)return;period=np;prefs.edit().putString("period",period).apply();cancelPendingAnalyze();val cached=FcsClient.peek(symbol,period,220);candles=cached.orEmpty();loadedSymbol=if(candles.isNotEmpty())symbol else "";loadedPeriod=if(candles.isNotEmpty())period else "";pairLabel.text="$symbol • $period";switchVisibleChart();showExisting()};override fun onNothingSelected(p:AdapterView<*>?){}}')

rep('root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;showCachedOrSwitching();if(!FcsClient.hasUsableHistory(symbol,period,60))load(false)}};loadUrl("file:///android_asset/chart.html")};cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)',
'''root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.allowFileAccess=true;settings.allowContentAccess=true;setBackgroundColor(Color.BLACK);addJavascriptInterface(ChartBridge(),"AndroidLive");webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;initVisibleChart();showExisting()}};loadUrl("file:///android_asset/chart.html")};cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)''')

rep('private fun handleKeyButton(){val saved=savedKey().isNotBlank();if(saved&&!editingKey){editingKey=true;updateKeyUi();keyInput.requestFocus();return};val entered=keyInput.text.toString().trim();if(entered.isBlank()){Toast.makeText(this,"Enter a valid history key",Toast.LENGTH_SHORT).show();return};prefs.edit().putString("api_key",entered).apply();editingKey=false;updateKeyUi();Toast.makeText(this,"History key saved",Toast.LENGTH_SHORT).show();load(true)}',
    'private fun handleKeyButton(){val saved=savedKey().isNotBlank();if(saved&&!editingKey){editingKey=true;updateKeyUi();keyInput.requestFocus();return};val entered=keyInput.text.toString().trim();if(entered.isBlank()){Toast.makeText(this,"Enter a valid history key",Toast.LENGTH_SHORT).show();return};prefs.edit().putString("api_key",entered).apply();editingKey=false;updateKeyUi();Toast.makeText(this,"History key saved",Toast.LENGTH_SHORT).show();initVisibleChart()}')

rep('private fun handleSocketButton(){val saved=savedSocketKey().isNotBlank();if(saved&&!editingSocket){editingSocket=true;updateSocketUi();socketInput.requestFocus();return};val entered=socketInput.text.toString().trim();if(entered.isBlank()){Toast.makeText(this,"Enter a valid live stream key",Toast.LENGTH_SHORT).show();return};prefs.edit().putString("socket_api_key",entered).apply();editingSocket=false;updateSocketUi();LiveSocketHub.start(this,entered);startStateService();Toast.makeText(this,"Live stream key saved • continuous market feed starting",Toast.LENGTH_LONG).show()}',
    'private fun handleSocketButton(){val saved=savedSocketKey().isNotBlank();if(saved&&!editingSocket){editingSocket=true;updateSocketUi();socketInput.requestFocus();return};val entered=socketInput.text.toString().trim();if(entered.isBlank()){Toast.makeText(this,"Enter a valid live stream key",Toast.LENGTH_SHORT).show();return};prefs.edit().putString("socket_api_key",entered).apply();editingSocket=false;updateSocketUi();initVisibleChart();startStateService();Toast.makeText(this,"Live stream key saved • FCS live chart starting",Toast.LENGTH_LONG).show()}')

rep('private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();cancelPendingAnalyze();showCachedOrSwitching();if(!FcsClient.hasUsableHistory(symbol,period,60))load(false)}',
    'private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();cancelPendingAnalyze();val cached=FcsClient.peek(symbol,period,220);candles=cached.orEmpty();loadedSymbol=if(candles.isNotEmpty())symbol else "";loadedPeriod=if(candles.isNotEmpty())period else "";pairLabel.text="$symbol • $period";switchVisibleChart();showExisting()}')

start='''    private fun requestAnalyze(){
        val token=++analyzeGeneration;pendingAnalyzeToken=token;val have=candles.size>=60&&loadedSymbol==symbol&&loadedPeriod==period
        if(have){pendingAnalyzeToken=null;performAnalysis();return}
        if(savedKey().isBlank()){status.text="FULL ANALYSIS NEEDS HISTORICAL CANDLES • LIVE CHART CONTINUES";return}
        status.text="BUILDING ENOUGH $symbol • $period HISTORY FOR ANALYSIS…";load(false)
    }'''
new='''    private fun requestAnalyze(){
        val token=++analyzeGeneration;pendingAnalyzeToken=token
        if(savedKey().isBlank()){status.text="SAVE HISTORY KEY FOR ANALYSIS • LIVE CHART CONTINUES";return}
        status.text="ANALYZING FRESH $symbol • $period MARKET STRUCTURE…"
        load(true)
    }'''
rep(start,new)

rep('private fun render(data:List<Candle>,renderSymbol:String=symbol,renderPeriod:String=period){if(renderSymbol!=symbol||renderPeriod!=period)return;val a=JSONArray();data.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(renderSymbol)},${JSONObject.quote(renderPeriod)})",null);showSignalOverlay(currentDisplayedSignal())}',
    'private fun render(data:List<Candle>,renderSymbol:String=symbol,renderPeriod:String=period){if(renderSymbol!=symbol||renderPeriod!=period)return;showSignalOverlay(currentDisplayedSignal())}')

rep('if(a==null){status.text=if(candles.size>=60)"$symbol • $period\\nREADY FOR ANALYSIS • LIVE CANDLES RUNNING" else "$symbol • $period\\nLIVE CANDLE RUNNING • HISTORY BUILDING";if(::chart.isInitialized&&chartReady)chart.evaluateJavascript("setSignal(null)",null);return}',
    'if(a==null){status.text="$symbol • $period\\nLIVE CHART RUNNING • PRESS NEW ANALYZE FOR FRESH SETUP";if(::chart.isInitialized&&chartReady)chart.evaluateJavascript("setSignal(null)",null);return}')

# update visible branding
s=s.replace('MS • v22 • PERSISTENT LIVE CHART','MS • v24 • FCS LIVE CHART ENGINE')
p.write_text(s)
