package com.mh.analysis

import android.Manifest
import android.app.*
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.*
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import kotlin.concurrent.thread
import kotlin.math.abs

class MainActivityV24:Activity(),LiveSocketHub.Listener{
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private lateinit var chart:WebView;private lateinit var socketStatus:TextView;private lateinit var historyStatus:TextView;private lateinit var status:TextView;private lateinit var calls:TextView;private lateinit var pairLabel:TextView
    private lateinit var historyInput:EditText;private lateinit var socketInput:EditText;private lateinit var historyButton:Button;private lateinit var socketButton:Button
    private var symbol="XAUUSD";private var period="15m";private var chartReady=false;private var candles:List<Candle> = emptyList();private var loadedSymbol="";private var loadedPeriod="";private var busy=false;private var editHistory=false;private var editSocket=false

    override fun onCreate(b:Bundle?){super.onCreate(b);FcsClient.init(this);if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12);window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK;symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";setContentView(buildUi());if(savedSocketKey().isNotBlank())startStateService()}
    override fun onResume(){super.onResume();LiveSocketHub.addListener(this);if(savedSocketKey().isNotBlank())LiveSocketHub.start(this,savedSocketKey());if(chartReady)startVisibleSocket();restoreChart();showExisting()}
    override fun onPause(){LiveSocketHub.removeListener(this);super.onPause()}
    override fun onSocketState(state:String){runOnUiThread{if(::socketStatus.isInitialized&&state.startsWith("BACKGROUND"))socketStatus.text="● Visible WebSocket uses official FCS client • $state"}}

    private inner class JsBridge{
        @JavascriptInterface fun onSocketState(s:String){runOnUiThread{socketStatus.text="● $s"}}
        @JavascriptInterface fun onSocketMessage(raw:String){runCatching{JSONObject(raw)}.getOrNull()?.let{handleJsLive(it)}}
    }

    private fun handleJsLive(j:JSONObject){
        if(j.optString("type")!="price")return
        val rawSym=j.optString("symbol");val s=when{rawSym.endsWith("XAUUSD",true)->"XAUUSD";rawSym.endsWith("BTCUSDT",true)->"BTCUSDT";else->return}
        val tf=when(j.optString("timeframe").lowercase()){ "1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->return }
        val p=j.optJSONObject("prices")?:return;val mode=p.optString("mode").lowercase();if(mode=="profile")return
        val applied:Candle?=if(mode=="initial"||mode=="candle"||(p.has("o")&&p.has("h")&&p.has("l")&&p.has("c"))){val close=p.optDouble("c");FcsClient.applyLiveCandle(s,tf,Candle(p.optLong("t",0L),p.optDouble("o",close),p.optDouble("h",close),p.optDouble("l",close),close,p.optDouble("v",0.0)))}else if(mode=="askbid"&&p.has("c")){FcsClient.applyLivePrice(s,tf,p.optLong("t",p.optLong("update",0L)),p.optDouble("c"))}else null
        if(applied!=null&&tf=="1m")sendLiveTickToService(s,applied)
        if(applied!=null&&s==symbol&&tf==period){runOnUiThread{FcsClient.peek(symbol,period,220)?.let{candles=it;loadedSymbol=symbol;loadedPeriod=period};showExisting();showSignalOverlay(currentDisplayedSignal())}}
    }

    private fun sendLiveTickToService(s:String,c:Candle){val i=Intent(this,AlarmService::class.java).apply{action="JS_LIVE_TICK";putExtra("symbol",s);putExtra("t",c.t);putExtra("o",c.o);putExtra("h",c.h);putExtra("l",c.l);putExtra("c",c.c);putExtra("v",c.v)};if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}

    private fun buildUi():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(14),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        root.addView(txt("بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",21f,true).apply{gravity=Gravity.CENTER;textAlignment=View.TEXT_ALIGNMENT_CENTER;setPadding(0,dp(3),0,dp(14))},LinearLayout.LayoutParams(-1,-2))
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};header.addView(TextView(this).apply{text="MS";gravity=Gravity.CENTER;textSize=22f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=round(Color.BLACK,18f,Color.WHITE)},LinearLayout.LayoutParams(dp(64),dp(64)));header.addView(LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0);addView(txt("MH ANALYSIS",26f,true));addView(txt("Live Market Structure Engine",11f,false,Color.LTGRAY));addView(txt("MS • v24 • WEBSOCKET-FIRST LIVE CHART",10f,true));addView(txt("◉ WhatsApp  +92 343 4824609",11f,false,Color.LTGRAY))},LinearLayout.LayoutParams(0,-2,1f));root.addView(header)

        val keyCard=card();historyStatus=txt("",12f,true,Color.LTGRAY);keyCard.addView(historyStatus);historyInput=input("Enter analysis/history access key").apply{inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD};keyCard.addView(historyInput,lp48(7));historyButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{saveHistoryKey()}};keyCard.addView(historyButton,lp46(8));socketStatus=txt("",12f,true,Color.LTGRAY).apply{setPadding(0,dp(12),0,0)};keyCard.addView(socketStatus);socketInput=input("Enter WebSocket key").apply{inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD};keyCard.addView(socketInput,lp48(7));socketButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{saveSocketKey()}};keyCard.addView(socketButton,lp46(8));updateKeyUi();root.addView(keyCard,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(12)})

        root.addView(section("MARKET"));val mc=card();val pairs=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};pairs.addView(pairButton("GOLD\nXAUUSD"){switchPair("XAUUSD")},LinearLayout.LayoutParams(0,dp(58),1f).apply{rightMargin=dp(6)});pairs.addView(pairButton("BTC\nBTCUSDT"){switchPair("BTCUSDT")},LinearLayout.LayoutParams(0,dp(58),1f).apply{leftMargin=dp(6)});mc.addView(pairs);val row=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};pairLabel=txt("$symbol • $period",13f,true);row.addView(pairLabel,LinearLayout.LayoutParams(0,dp(48),1f));val periods=arrayOf("1m","5m","15m","30m","1h");if(period !in periods)period="15m";val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV24,android.R.layout.simple_spinner_dropdown_item,periods);setSelection(periods.indexOf(period))};row.addView(sp,LinearLayout.LayoutParams(dp(135),dp(48)));mc.addView(row);root.addView(mc);sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np==period)return;period=np;prefs.edit().putString("period",period).apply();switchVisibleFeed()};override fun onNothingSelected(p:AdapterView<*>?){}}

        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);addJavascriptInterface(JsBridge(),"AndroidLive");webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;startVisibleSocket();switchVisibleFeed();restoreChart()}};loadUrl("file:///android_asset/chart.html")};cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)

        root.addView(section("SIGNAL CONTROL"));val sc=card();calls=txt("Analysis history calls: ${usage()}/500",11f,true,Color.LTGRAY);sc.addView(calls);val br=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};br.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(4)});br.addView(actionButton("RECORDS",false){showRecords()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(2);rightMargin=dp(2)});br.addView(actionButton("ALARM",false){alarmAndShow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(4)});sc.addView(br,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});status=txt("READY",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)

        root.addView(section("FLOATING / BACKGROUND"));val fc=card();fc.addView(Button(this).apply{text="ENABLE MS LIVE FLOAT";setTextColor(Color.WHITE);background=round(Color.rgb(25,25,25),12f,Color.GRAY);setOnClickListener{enableFloat()}},LinearLayout.LayoutParams(-1,dp(52)));root.addView(fc)
        return ScrollView(this).apply{isFillViewport=true;setBackgroundColor(Color.BLACK);addView(root)}
    }

    private fun startVisibleSocket(){if(!chartReady)return;val k=savedSocketKey();if(k.isBlank()){socketStatus.text="● WEBSOCKET KEY REQUIRED ONCE";return};chart.evaluateJavascript("startFcsLive(${JSONObject.quote(k)})",null)}
    private fun switchVisibleFeed(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("selectLive(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);restoreChart();showExisting()}
    private fun restoreChart(){val cached=FcsClient.peek(symbol,period,220);if(!cached.isNullOrEmpty()){candles=cached;loadedSymbol=symbol;loadedPeriod=period;renderHistory(cached)}else{candles=emptyList();loadedSymbol="";loadedPeriod=""}}
    private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();switchVisibleFeed()}

    private fun analyzeNow(){
        val current=FcsClient.peek(symbol,period,220).orEmpty();if(current.size>=60){candles=current;loadedSymbol=symbol;loadedPeriod=period;performAnalysis();return}
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE HISTORY ACCESS KEY ONCE • LIVE WEBSOCKET CHART CONTINUES";return};if(busy)return;busy=true;status.text="NEW ANALYZE • loading historical depth for $symbol $period…"
        thread{try{val(out,credits)=FcsClient.seedForPeriod(key,symbol,period,false);runOnUiThread{busy=false;if(credits>0)addUsage(credits);calls.text="Analysis history calls: ${usage()}/500";candles=out;loadedSymbol=symbol;loadedPeriod=period;renderHistory(out);performAnalysis()}}catch(e:Exception){runOnUiThread{busy=false;status.text="ANALYSIS HISTORY ERROR\n${e.message}\nLive WebSocket chart remains active."}}}
    }

    private fun performAnalysis(){if(candles.size<60){status.text="NOT ENOUGH HISTORY FOR RELIABLE ANALYSIS YET";return};SignalStore.evaluate(this,symbol,period,candles);val existing=currentDisplayedSignal();val s=AnalysisEngine.analyze(symbol,period,candles);if(s==null){if(existing!=null&&existing.state in setOf("PENDING","ACTIVE")){val x=existing.signal;status.text="EXISTING SETUP • ${x.timeframe} • ${existing.state}\n${x.direction} ${x.score}/100\nEntry ${price(x.entry)}   SL ${price(x.sl)}\nTP1 ${price(x.tp1)}   TP2 ${price(x.tp2)}\n\nSame market setup remains valid; no stronger replacement yet.";showSignalOverlay(existing)}else status.text="NO NEW SETUP\n${AnalysisEngine.noSignalReason(symbol,period,candles)}";return};val d=SignalStore.findDuplicate(this,s);if(d!=null){val x=d.signal;status.text="EXISTING SETUP • ${d.state}\n${x.direction} ${x.score}/100\nEntry ${price(x.entry)}   SL ${price(x.sl)}\nTP1 ${price(x.tp1)}   TP2 ${price(x.tp2)}";showSignalOverlay(d);return};SignalStore.acceptCandidate(this,s);startStateService();showExisting();showSignalOverlay(SignalStore.loadActive(this,symbol,period))}

    private fun renderHistory(data:List<Candle>){if(!chartReady)return;val a=JSONArray();data.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null)}
    private fun currentDisplayedSignal()=SignalStore.displayState(this,symbol,period)
    private fun showSignalOverlay(a:ActiveSignal?){if(!chartReady)return;if(a==null){chart.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val j=JSONObject().put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("state",a.state).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh);chart.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})",null)}
    private fun showExisting(){if(!::status.isInitialized)return;val a=currentDisplayedSignal();if(a==null){status.text="$symbol • $period\nLIVE WEBSOCKET CHART RUNNING • PRESS NEW ANALYZE FOR A FRESH SETUP";showSignalOverlay(null);return};val s=a.signal;val why=s.reasons.take(6).joinToString("\n");status.text="${s.direction} • ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\nWHY THIS TRADE\n${s.setupReason}\n\nCONFIRMATIONS\n$why";showSignalOverlay(a)}

    private fun showRecords(){val days=lastThreeDays();val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(12),dp(8),dp(12),dp(8))};val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV24,android.R.layout.simple_spinner_dropdown_item,days)};val tv=TextView(this).apply{setTextColor(Color.BLACK);textSize=13f};fun refresh(){val day=sp.selectedItem?.toString()?:days.first();val b=StringBuilder(SignalStore.stats(this,day)).append("\n\n");SignalStore.openForDay(this,day).forEach{b.append("OPEN ${it.signal.symbol} ${it.signal.timeframe} ${it.signal.direction} Entry ${price(it.signal.entry)}\n")};SignalStore.recordsForDay(this,day).forEach{b.append("${it.result} ${it.symbol} ${it.timeframe} ${it.direction} ${it.score}/100\n")};tv.text=b.toString()};sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()};override fun onNothingSelected(p:AdapterView<*>?){}};box.addView(sp);box.addView(ScrollView(this).apply{addView(tv)},LinearLayout.LayoutParams(-1,dp(420)));AlertDialog.Builder(this).setTitle("MS Records • Last 3 Days").setView(box).setNeutralButton("Reset"){_,_->SignalStore.reset(this);showExisting()}.setNegativeButton("Close",null).show()}
    private fun alarmAndShow(){SignalStore.loadActive(this,symbol,period)?.takeIf{it.state=="PENDING"}?.let{AlarmStore.addSaved(this,it.signal)};val items=AlarmStore.list(this);val text=if(items.isEmpty())"No alarms." else items.joinToString("\n\n"){"${it.symbol} ${it.timeframe} ${it.direction}\nEntry ${price(it.entry)} • ${it.status}"};AlertDialog.Builder(this).setTitle("MS Alarm Lifecycle").setMessage(text).setPositiveButton("ARM CURRENT"){_,_->SignalStore.loadActive(this,symbol,period)?.let{a->AlarmStore.addSaved(this,a.signal);AlarmStore.list(this).firstOrNull{it.signalId==a.signal.id}?.let{x->AlarmStore.setEnabled(this,x.id,true)};startStateService()}}.setNegativeButton("Close",null).show()}

    private fun savedHistoryKey()=prefs.getString("api_key","")?.trim().orEmpty();private fun savedSocketKey()=prefs.getString("socket_api_key","")?.trim().orEmpty()
    private fun updateKeyUi(){val h=savedHistoryKey().isNotBlank();historyInput.visibility=if(h&&!editHistory)View.GONE else View.VISIBLE;historyStatus.text=if(h&&!editHistory)"● ANALYSIS HISTORY KEY SAVED" else "ANALYSIS/HISTORY KEY";historyButton.text=if(h&&!editHistory)"UPDATE HISTORY KEY" else "SAVE HISTORY KEY";val s=savedSocketKey().isNotBlank();socketInput.visibility=if(s&&!editSocket)View.GONE else View.VISIBLE;socketStatus.text=if(s&&!editSocket)"● LIVE WEBSOCKET KEY SAVED • AUTO-CONNECT" else "LIVE WEBSOCKET KEY";socketButton.text=if(s&&!editSocket)"UPDATE LIVE KEY" else "SAVE LIVE KEY"}
    private fun saveHistoryKey(){if(savedHistoryKey().isNotBlank()&&!editHistory){editHistory=true;updateKeyUi();return};val x=historyInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();editHistory=false;historyInput.setText("");updateKeyUi();Toast.makeText(this,"Analysis/history key saved",Toast.LENGTH_SHORT).show()}
    private fun saveSocketKey(){if(savedSocketKey().isNotBlank()&&!editSocket){editSocket=true;updateKeyUi();return};val x=socketInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("socket_api_key",x).apply();editSocket=false;socketInput.setText("");updateKeyUi();startVisibleSocket();LiveSocketHub.start(this,x);startStateService();Toast.makeText(this,"WebSocket key saved • live chart starting",Toast.LENGTH_LONG).show()}

    private fun startStateService(){if(savedSocketKey().isBlank())return;val i=Intent(this,AlarmService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}
    private fun enableFloat(){if(savedSocketKey().isBlank()){Toast.makeText(this,"Save WebSocket key first",Toast.LENGTH_LONG).show();return};if(!Settings.canDrawOverlays(this))startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")))else{val i=Intent(this,OverlayService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}}
    private fun lastThreeDays():List<String>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return(0..2).map{val c=Calendar.getInstance();c.add(Calendar.DAY_OF_YEAR,-it);f.format(c.time)}}
    private fun month()=SimpleDateFormat("yyyy-MM",Locale.US).format(Date());private fun usage():Int{val m=month();if(prefs.getString("usage_month","")!=m)prefs.edit().putString("usage_month",m).putInt("usage",0).apply();return prefs.getInt("usage",0)};private fun addUsage(n:Int){prefs.edit().putInt("usage",usage()+n.coerceAtLeast(0)).apply()}
    private fun price(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun pairButton(t:String,click:()->Unit)=Button(this).apply{text=t;setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{click()}}
    private fun actionButton(t:String,p:Boolean,click:()->Unit)=Button(this).apply{text=t;textSize=11f;setTypeface(typeface,Typeface.BOLD);setTextColor(if(p)Color.BLACK else Color.WHITE);background=if(p)round(Color.WHITE,12f)else round(Color.rgb(24,24,24),12f,Color.GRAY);setOnClickListener{click()}}
    private fun input(h:String)=EditText(this).apply{hint=h;setHintTextColor(Color.GRAY);setTextColor(Color.WHITE);textSize=13f;setSingleLine(true);background=round(Color.rgb(20,20,20),12f,Color.DKGRAY);setPadding(dp(14),0,dp(14),0)}
    private fun lp48(top:Int)=LinearLayout.LayoutParams(-1,dp(48)).apply{topMargin=dp(top)};private fun lp46(top:Int)=LinearLayout.LayoutParams(-1,dp(46)).apply{topMargin=dp(top)}
    private fun section(s:String)=txt(s,11f,true,Color.GRAY).apply{setPadding(0,dp(18),0,dp(8))};private fun card()=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),dp(14),dp(14),dp(14));background=round(Color.rgb(8,8,8),16f,Color.rgb(45,45,45))}
    private fun txt(s:String,z:Float,b:Boolean=false,c:Int=Color.WHITE)=TextView(this).apply{text=s;textSize=z;setTextColor(c);if(b)setTypeface(typeface,Typeface.BOLD)};private fun round(c:Int,r:Float,stroke:Int?=null)=GradientDrawable().apply{setColor(c);cornerRadius=dp(r.toInt()).toFloat();if(stroke!=null)setStroke(dp(1),stroke)};private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
}
