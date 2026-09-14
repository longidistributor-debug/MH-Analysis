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
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import kotlin.concurrent.thread
import kotlin.math.abs

class OverlayService:Service(){
    private lateinit var wm:WindowManager;private lateinit var bubble:TextView
    private var panel:LinearLayout?=null;private var chart:WebView?=null;private var status:TextView?=null
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private var symbol="XAUUSD";private var period="15m";private var data:List<Candle> = emptyList();private var loadedAt=0L;private var ready=false;private var busy=false
    override fun onBind(i:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";wm=getSystemService(WINDOW_SERVICE) as WindowManager;foreground();bubble()}
    private fun foreground(){val id="mh_analysis";if(Build.VERSION.SDK_INT>=26)(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(NotificationChannel(id,"MH Analysis",NotificationManager.IMPORTANCE_LOW));val n=(if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,id)else Notification.Builder(this)).setContentTitle("MH Analysis running").setContentText("Gold + BTC floating analysis").setSmallIcon(android.R.drawable.ic_menu_compass).build();startForeground(210,n)}
    private fun type()=if(Build.VERSION.SDK_INT>=26)WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
    private fun bubble(){bubble=TextView(this).apply{text="MH";textSize=16f;gravity=Gravity.CENTER;setTextColor(Color.BLACK);setTypeface(typeface,Typeface.BOLD);background=GradientDrawable().apply{shape=GradientDrawable.OVAL;setColor(Color.WHITE);setStroke(dp(2),Color.GRAY)}};val p=WindowManager.LayoutParams(dp(60),dp(60),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.START;x=dp(18);y=dp(210)};var sx=0;var sy=0;var tx=0f;var ty=0f;var moved=false;bubble.setOnTouchListener{_,e->when(e.action){MotionEvent.ACTION_DOWN->{sx=p.x;sy=p.y;tx=e.rawX;ty=e.rawY;moved=false;true};MotionEvent.ACTION_MOVE->{val dx=(e.rawX-tx).toInt(),dy=(e.rawY-ty).toInt();if(abs(dx)>dp(4)||abs(dy)>dp(4))moved=true;p.x=sx+dx;p.y=sy+dy;wm.updateViewLayout(bubble,p);true};MotionEvent.ACTION_UP->{if(!moved)toggle();true};else->false}};wm.addView(bubble,p)}
    private fun toggle(){if(panel==null)show()else hide()}
    private fun show(){symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(10),dp(10),dp(10),dp(10));background=GradientDrawable().apply{setColor(Color.rgb(6,6,6));cornerRadius=dp(16).toFloat();setStroke(dp(1),Color.GRAY)}};panel=root
        val h=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};h.addView(text("MH ANALYSIS",14f,true),LinearLayout.LayoutParams(0,dp(42),1f));h.addView(Button(this).apply{text="—";setOnClickListener{hide()}},LinearLayout.LayoutParams(dp(48),dp(40)));root.addView(h)
        val pairs=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};pairs.addView(Button(this).apply{text="GOLD";setOnClickListener{switch("XAUUSD")}},LinearLayout.LayoutParams(0,dp(42),1f));pairs.addView(Button(this).apply{text="BTC";setOnClickListener{switch("BTCUSDT")}},LinearLayout.LayoutParams(0,dp(42),1f));root.addView(pairs)
        chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){ready=true;load()}};loadUrl("file:///android_asset/chart.html")};root.addView(chart,LinearLayout.LayoutParams(-1,dp(300)))
        root.addView(Button(this).apply{text="NEW ANALYZE";setTextColor(Color.BLACK);setBackgroundColor(Color.WHITE);setOnClickListener{analyze()}},LinearLayout.LayoutParams(-1,dp(48)))
        status=text("$symbol • $period",11f);status?.setPadding(0,dp(8),0,0);root.addView(status)
        val p=WindowManager.LayoutParams(dp(360),dp(520),type(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.END;x=dp(8);y=dp(55)};wm.addView(root,p)}
    private fun switch(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();data=emptyList();loadedAt=0;chart?.evaluateJavascript("clearChart()",null);load()}
    private fun load(){if(!ready||busy)return;val k=prefs.getString("api_key","")?.trim().orEmpty();if(k.isBlank()){status?.text="API key missing";return};busy=true;thread{try{val(c,_)=FcsClient.history(k,symbol,period,220,false);data=c;loadedAt=System.currentTimeMillis();val ev=SignalStore.evaluate(this,symbol,c);Handler(Looper.getMainLooper()).post{render(c);busy=false;if(ev!=null&&(ev.state=="WIN"||ev.state=="LOSS"||ev.state=="EXPIRED"))status?.text="SIGNAL ${ev.state} • record saved" else showActive()}}catch(e:Exception){Handler(Looper.getMainLooper()).post{busy=false;status?.text="Load failed: ${e.message}"}}}}
    private fun render(c:List<Candle>){val a=JSONArray();c.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart?.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);overlay(SignalStore.loadActive(this,symbol))}
    private fun analyze(){if(busy)return;val fresh=data.isNotEmpty()&&System.currentTimeMillis()-loadedAt<60_000;if(!fresh){load();return};val s=AnalysisEngine.analyze(symbol,period,data);if(s==null){status?.text="NO VALID EDGE";return};SignalStore.replaceWith(this,s);showActive();overlay(SignalStore.loadActive(this,symbol))}
    private fun showActive(){val a=SignalStore.loadActive(this,symbol);if(a==null){status?.text="$symbol • $period • no active signal";overlay(null);return};val s=a.signal;val fvg=if(s.fvgLow!=null)"${s.fvgType} FVG ${price(s.fvgLow)}-${price(s.fvgHigh)}" else "No FVG";status?.text="${s.direction} ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)} SL ${price(s.sl)} TP1 ${price(s.tp1)}\nBull ${s.bullScore} / Bear ${s.bearScore} • RSI ${"%.1f".format(s.rsi)}\n$fvg"}
    private fun overlay(a:ActiveSignal?){if(a==null){chart?.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val j=JSONObject().put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("state",a.state).put("validBars",s.validBars).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh);chart?.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})",null)}
    private fun price(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun hide(){panel?.let{runCatching{wm.removeView(it)}};panel=null;chart=null;status=null;ready=false}
    private fun text(s:String,z:Float,b:Boolean=false)=TextView(this).apply{text=s;textSize=z;setTextColor(Color.WHITE);if(b)setTypeface(typeface,Typeface.BOLD)}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
    override fun onDestroy(){hide();if(::bubble.isInitialized)runCatching{wm.removeView(bubble)};super.onDestroy()}
}
