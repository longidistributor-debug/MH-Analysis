package com.mh.analysis

import android.app.*
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.*
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONObject
import java.util.Locale
import kotlin.concurrent.thread
import kotlin.math.abs

class OverlayService:Service(){
    private lateinit var wm:WindowManager;private lateinit var bubble:TextView;private var panel:LinearLayout?=null;private var chart:WebView?=null;private var status:TextView?=null
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)};private var symbol="XAUUSD";private var period="15m";private var busy=false
    override fun onBind(i:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();FcsClient.init(this);wm=getSystemService(WINDOW_SERVICE) as WindowManager;startFg();createBubble()}
    private fun read(){symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m"}
    private fun startFg(){val id="mh_float_v29";if(Build.VERSION.SDK_INT>=26)(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(NotificationChannel(id,"MS Floating TradingView",NotificationManager.IMPORTANCE_LOW));val b=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,id)else Notification.Builder(this);startForeground(210,b.setSmallIcon(android.R.drawable.ic_menu_compass).setContentTitle("MS floating chart").setContentText("TradingView live chart").setOngoing(true).build())}
    private fun type()=if(Build.VERSION.SDK_INT>=26)WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
    private fun createBubble(){bubble=TextView(this).apply{text="MS";textSize=15f;gravity=Gravity.CENTER;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=GradientDrawable().apply{shape=GradientDrawable.OVAL;setColor(Color.rgb(16,16,16));setStroke(dp(1),Color.DKGRAY)}};val p=WindowManager.LayoutParams(dp(48),dp(48),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.START;x=dp(16);y=dp(190)};var sx=0;var sy=0;var tx=0f;var ty=0f;var moved=false;bubble.setOnTouchListener{_,e->when(e.action){MotionEvent.ACTION_DOWN->{sx=p.x;sy=p.y;tx=e.rawX;ty=e.rawY;moved=false;true};MotionEvent.ACTION_MOVE->{val dx=(e.rawX-tx).toInt();val dy=(e.rawY-ty).toInt();if(abs(dx)>dp(4)||abs(dy)>dp(4))moved=true;p.x=sx+dx;p.y=sy+dy;wm.updateViewLayout(bubble,p);true};MotionEvent.ACTION_UP->{if(!moved)toggle();true};else->false}};wm.addView(bubble,p)}
    private fun toggle(){if(panel==null)showPanel()else hidePanel()}
    private fun showPanel(){read();val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(10),dp(10),dp(10),dp(10));background=GradientDrawable().apply{setColor(Color.rgb(5,5,5));cornerRadius=dp(14).toFloat();setStroke(dp(1),Color.GRAY)}};panel=root;val head=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};head.addView(tv("MS • TRADINGVIEW LIVE",14f,true),LinearLayout.LayoutParams(0,dp(40),1f));head.addView(Button(this).apply{text="×";setOnClickListener{hidePanel()}},LinearLayout.LayoutParams(dp(46),dp(40)));root.addView(head)
        val pair=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};pair.addView(Button(this).apply{text="GOLD";setOnClickListener{switch("XAUUSD",period)}},LinearLayout.LayoutParams(0,dp(42),1f));pair.addView(Button(this).apply{text="BTC";setOnClickListener{switch("BTCUSDT",period)}},LinearLayout.LayoutParams(0,dp(42),1f));root.addView(pair)
        val periods=arrayOf("1m","5m","15m","30m","1h");if(period !in periods)period="15m";val tfRow=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};tfRow.addView(tv("TIMEFRAME",10f,true),LinearLayout.LayoutParams(0,dp(46),1f));val sp=Spinner(this).apply{adapter=ArrayAdapter(this@OverlayService,android.R.layout.simple_spinner_dropdown_item,periods);setSelection(periods.indexOf(period).coerceAtLeast(0))};tfRow.addView(sp,LinearLayout.LayoutParams(dp(145),dp(46)));root.addView(tfRow);sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(parent:AdapterView<*>?,view:android.view.View?,position:Int,id:Long){val p=periods[position];if(p!=period)switch(symbol,p)};override fun onNothingSelected(parent:AdapterView<*>?){}}
        chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true);setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){loadChart();showState()}};val html=assets.open("tradingview_live.html").bufferedReader().use{it.readText()};loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)};root.addView(chart,LinearLayout.LayoutParams(-1,dp(390)))
        root.addView(Button(this).apply{text="NEW ANALYZE";setTextColor(Color.BLACK);setBackgroundColor(Color.WHITE);setOnClickListener{analyze()}},LinearLayout.LayoutParams(-1,dp(46)));status=tv("$symbol • $period",10.5f);root.addView(status)
        wm.addView(root,WindowManager.LayoutParams(dp(390),dp(720),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.END;x=dp(6);y=dp(35)})}
    private fun switch(s:String,p:String){if(symbol==s&&period==p)return;symbol=s;period=p;prefs.edit().putString("symbol",s).putString("period",p).apply();loadChart();showState()}
    private fun loadChart(){chart?.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);overlay(SignalStore.displayState(this,symbol,period))}
    private fun displayed()=SignalStore.displayState(this,symbol,period)
    private fun analyze(){if(busy)return;val key=prefs.getString("api_key","")?.trim().orEmpty();if(key.isBlank()){status?.text="Save analysis key in main app first";return};busy=true;status?.text="Analyzing $symbol $period…";val s0=symbol;val p0=period;thread{runCatching{FcsClient.seedForPeriod(key,s0,p0,true)}.onSuccess{pair->Handler(Looper.getMainLooper()).post{busy=false;if(symbol!=s0||period!=p0)return@post;val data=pair.first;if(data.size<60){status?.text="Not enough history";return@post};SignalStore.evaluate(this,symbol,period,data);val s=AnalysisEngine.analyze(symbol,period,data);if(s==null){showState();return@post};val dup=SignalStore.findDuplicate(this,s);if(dup==null)SignalStore.acceptCandidate(this,s);startMonitor();showState()}}.onFailure{e->Handler(Looper.getMainLooper()).post{busy=false;status?.text="Analysis unavailable: ${e.message}"}}}}
    private fun startMonitor(){val i=Intent(this,AlarmService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}
    private fun showState(){val a=displayed();if(a==null){status?.text="$symbol • $period • TradingView live\nPress NEW ANALYZE for setup";overlay(null);return};val s=a.signal;status?.text="${s.direction} ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}  SL ${price(s.sl)}  TP1 ${price(s.tp1)}";overlay(a)}
    private fun overlay(a:ActiveSignal?){if(a==null){chart?.evaluateJavascript("clearSignalCard()",null);return};val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score);chart?.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)}
    private fun hidePanel(){panel?.let{runCatching{wm.removeView(it)}};panel=null;chart=null;status=null;busy=false}
    private fun price(v:Double?)=when{v==null->"-";abs(v)>=100->String.format(Locale.US,"%.2f",v);else->String.format(Locale.US,"%.5f",v)}
    private fun tv(v:String,s:Float,b:Boolean=false)=TextView(this).apply{text=v;textSize=s;setTextColor(Color.WHITE);if(b)setTypeface(typeface,Typeface.BOLD)}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
    override fun onDestroy(){hidePanel();if(::bubble.isInitialized)runCatching{wm.removeView(bubble)};super.onDestroy()}
}
