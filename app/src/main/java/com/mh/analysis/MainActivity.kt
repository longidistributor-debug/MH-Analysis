package com.mh.analysis

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.*
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import kotlin.concurrent.thread
import kotlin.math.abs

class MainActivity:Activity(){
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private lateinit var key:EditText
    private lateinit var chart:WebView
    private lateinit var status:TextView
    private lateinit var calls:TextView
    private lateinit var pairLabel:TextView
    private var symbol="XAUUSD"
    private var period="15m"
    private var chartReady=false
    private var busy=false
    private var candles:List<Candle> = emptyList()
    private var loadedSymbol=""
    private var loadedPeriod=""
    private var loadedAt=0L

    override fun onCreate(b:Bundle?){super.onCreate(b);if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12);window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK;symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";setContentView(ui())}

    private fun ui():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(18),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(TextView(this).apply{text="MH";gravity=Gravity.CENTER;textSize=22f;setTextColor(Color.BLACK);setTypeface(typeface,Typeface.BOLD);background=round(Color.WHITE,30f)},LinearLayout.LayoutParams(dp(64),dp(64)))
        header.addView(LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0);addView(txt("MH ANALYSIS",26f,true));addView(txt("Gold + BTC Confluence Engine",11f,false,Color.LTGRAY));addView(txt("v1 • AUDITABLE SIGNALS",10f,true,Color.WHITE))},LinearLayout.LayoutParams(0,-2,1f));root.addView(header)

        root.addView(section("FCS CONNECTION"));val kc=card();key=input("FCS REST Access Key",prefs.getString("api_key","")?:"");kc.addView(key,LinearLayout.LayoutParams(-1,dp(52)));kc.addView(Button(this).apply{text="SAVE KEY + LOAD";setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{prefs.edit().putString("api_key",key.text.toString().trim()).apply();load(false)}},LinearLayout.LayoutParams(-1,dp(50)).apply{topMargin=dp(10)});root.addView(kc)

        root.addView(section("MARKET"));val mc=card();val row=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL}
        row.addView(Button(this).apply{text="GOLD\nXAUUSD";setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{switchPair("XAUUSD")}},LinearLayout.LayoutParams(0,dp(58),1f).apply{rightMargin=dp(6)})
        row.addView(Button(this).apply{text="BTC\nBTCUSDT";setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{switchPair("BTCUSDT")}},LinearLayout.LayoutParams(0,dp(58),1f).apply{leftMargin=dp(6)});mc.addView(row)
        val row2=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};pairLabel=txt("$symbol • $period",13f,true);row2.addView(pairLabel,LinearLayout.LayoutParams(0,dp(48),1f));val periods=arrayOf("1m","5m","15m","30m","1h","4h","1D");val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,periods);setSelection(periods.indexOf(period).coerceAtLeast(0))};row2.addView(sp,LinearLayout.LayoutParams(dp(110),dp(48)));mc.addView(row2);root.addView(mc)
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np!=period){period=np;prefs.edit().putString("period",period).apply();pairLabel.text="$symbol • $period";candles=emptyList();if(chartReady&&key.text.toString().trim().isNotBlank())load(false)}};override fun onNothingSelected(p:AdapterView<*>?){}}

        root.addView(section("INTERACTIVE CHART"));val cc=card();chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true}};loadUrl("file:///android_asset/chart.html")};cc.addView(chart,LinearLayout.LayoutParams(-1,dp(430)));cc.addView(txt("Pinch to zoom • drag to pan • green/red candles • FVG + Entry/SL/TP overlays",10f,false,Color.GRAY));root.addView(cc)

        root.addView(section("ANALYSIS"));val ac=card();calls=txt("Calls: ${usage()}/500",11f,true,Color.LTGRAY);ac.addView(calls);val btns=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};btns.addView(Button(this).apply{text="NEW ANALYZE";setTextColor(Color.BLACK);setTypeface(typeface,Typeface.BOLD);background=round(Color.WHITE,12f);setOnClickListener{newAnalyze()}},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(6)});btns.addView(Button(this).apply{text="RECORDS";setTextColor(Color.WHITE);background=round(Color.rgb(24,24,24),12f,Color.GRAY);setOnClickListener{showRecords()}},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(6)});ac.addView(btns,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});status=txt("READY\nLoad Gold or BTC. Existing signal remains until resolved or NEW ANALYZE is pressed.",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};ac.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(ac)

        root.addView(section("FLOATING MODE"));val fc=card();fc.addView(Button(this).apply{text="ENABLE MH FLOAT";setTextColor(Color.WHITE);background=round(Color.rgb(25,25,25),12f,Color.GRAY);setOnClickListener{enableFloat()}},LinearLayout.LayoutParams(-1,dp(52)));root.addView(fc)
        return ScrollView(this).apply{isFillViewport=true;setBackgroundColor(Color.BLACK);addView(root)}
    }

    private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();pairLabel.text="$symbol • $period";candles=emptyList();loadedSymbol="";loadedPeriod="";chart.evaluateJavascript("clearChart()",null);status.text="SWITCHED TO $symbol\nLoading fresh chart...";load(false)}

    private fun load(force:Boolean,after:(()->Unit)?=null){
        if(busy||!chartReady)return;val k=key.text.toString().trim();if(k.isBlank()){status.text="FCS KEY REQUIRED";return};busy=true;chart.evaluateJavascript("clearChart();showMessage(${JSONObject.quote("Loading $symbol • $period...")})",null)
        thread{try{val(data,credits)=FcsClient.history(k,symbol,period,220,force);candles=data;loadedSymbol=symbol;loadedPeriod=period;loadedAt=System.currentTimeMillis();val eval=SignalStore.evaluate(this,symbol,data);runOnUiThread{if(credits>0)addUsage(credits);calls.text="Calls: ${usage()}/500";render(data);pairLabel.text="$symbol • $period";busy=false;if(eval!=null&&(eval.state=="WIN"||eval.state=="LOSS"||eval.state=="EXPIRED"))status.text="SIGNAL ${eval.state}\nRecord saved. Press NEW ANALYZE for a new setup." else showExisting();after?.invoke()}}catch(e:Exception){runOnUiThread{busy=false;chart.evaluateJavascript("showMessage(${JSONObject.quote("Load failed: ${e.message}")})",null);status.text="LOAD FAILED\n${e.message}"}}}
    }

    private fun render(data:List<Candle>){val a=JSONArray();data.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showSignalOverlay(SignalStore.loadActive(this,symbol))}

    private fun newAnalyze(){
        if(busy)return;val have=candles.isNotEmpty()&&loadedSymbol==symbol&&loadedPeriod==period&&System.currentTimeMillis()-loadedAt<60_000
        if(!have){status.text="REFRESHING DATA BEFORE ANALYSIS...";load(false){newAnalyze()};return}
        val s=AnalysisEngine.analyze(symbol,period,candles);if(s==null){status.text="NO VALID EDGE\nBullish and bearish evidence is too balanced. Existing signal, if any, is unchanged.";return}
        SignalStore.replaceWith(this,s);showExisting();showSignalOverlay(SignalStore.loadActive(this,symbol))
    }

    private fun showExisting(){val a=SignalStore.loadActive(this,symbol);if(a==null){status.text="NO ACTIVE SIGNAL\nPress NEW ANALYZE when you want a new setup.";chart.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val conf=when{s.score>=85->"VERY HIGH";s.score>=75->"HIGH";s.score>=65->"MEDIUM";else->"EARLY"};val fvg=if(s.fvgLow!=null&&s.fvgHigh!=null)"${s.fvgType} FVG ${price(s.fvgLow)} - ${price(s.fvgHigh)}" else "No recent 3-candle FVG";val reasons=s.reasons.joinToString("\n"){"✓ $it"};status.text="${s.direction} • $conf • ${s.score}/100\nSTATE: ${a.state} • Valid ${s.validBars} candles\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\nCONFLUENCE: Bull ${s.bullScore} / Bear ${s.bearScore}\nEMA20 ${price(s.ema20)} • EMA50 ${price(s.ema50)}\nRSI14 ${"%.1f".format(s.rsi)} • MACD ${price(s.macd)} • ATR ${price(s.atr)}\n$fvg\n\nBEST MATCHES\n$reasons\n\nStarted: ${time(s.createdAt)}"}

    private fun showSignalOverlay(a:ActiveSignal?){if(a==null){chart.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val j=JSONObject().put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("state",a.state).put("validBars",s.validBars).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh);chart.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})",null)}

    private fun showRecords(){val r=SignalStore.records(this);val body=StringBuilder(SignalStore.stats(this)).append("\n\n");r.take(50).forEachIndexed{i,x->body.append("${i+1}. ${x.symbol} ${x.timeframe} • ${x.direction} • ${x.result} • ${x.score}/100\nEntry ${price(x.entry)} • ${time(x.startedAt)}\n\n")};AlertDialog.Builder(this).setTitle("MH Signal Records").setMessage(body.toString()).setPositiveButton("Close",null).show()}

    private fun enableFloat(){val k=key.text.toString().trim();if(k.isBlank()){Toast.makeText(this,"Enter FCS key first",Toast.LENGTH_LONG).show();return};prefs.edit().putString("api_key",k).apply();if(!Settings.canDrawOverlays(this))startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")))else startOverlay()}
    override fun onResume(){super.onResume();if(Settings.canDrawOverlays(this)&&prefs.getBoolean("want_float",false)){prefs.edit().putBoolean("want_float",false).apply();startOverlay()}}
    private fun startOverlay(){val i=Intent(this,OverlayService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i);Toast.makeText(this,"MH floating mode active",Toast.LENGTH_SHORT).show()}

    private fun month()=SimpleDateFormat("yyyy-MM",Locale.US).format(Date())
    private fun usage():Int{val m=month();if(prefs.getString("usage_month","")!=m)prefs.edit().putString("usage_month",m).putInt("usage",0).apply();return prefs.getInt("usage",0)}
    private fun addUsage(n:Int){prefs.edit().putInt("usage",usage()+n.coerceAtLeast(0)).apply()}
    private fun time(ms:Long)=SimpleDateFormat("dd MMM HH:mm",Locale.US).format(Date(ms))
    private fun price(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v) else String.format(Locale.US,"%.5f",v)
    private fun input(h:String,v:String)=EditText(this).apply{hint=h;setHintTextColor(Color.GRAY);setTextColor(Color.WHITE);textSize=13f;setSingleLine(true);setText(v);background=round(Color.rgb(20,20,20),12f,Color.DKGRAY);setPadding(dp(14),0,dp(14),0)}
    private fun section(s:String)=txt(s,11f,true,Color.GRAY).apply{setPadding(0,dp(18),0,dp(8))}
    private fun card()=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),dp(14),dp(14),dp(14));background=round(Color.rgb(8,8,8),16f,Color.rgb(45,45,45))}
    private fun txt(s:String,z:Float,b:Boolean=false,c:Int=Color.WHITE)=TextView(this).apply{text=s;textSize=z;setTextColor(c);if(b)setTypeface(typeface,Typeface.BOLD)}
    private fun round(c:Int,r:Float,stroke:Int?=null)=GradientDrawable().apply{setColor(c);cornerRadius=dp(r.toInt()).toFloat();if(stroke!=null)setStroke(dp(1),stroke)}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
}
