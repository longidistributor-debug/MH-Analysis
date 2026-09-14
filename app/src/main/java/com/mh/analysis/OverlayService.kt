package com.mh.analysis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import kotlin.concurrent.thread
import kotlin.math.abs

class OverlayService:Service(){
    private lateinit var wm:WindowManager
    private lateinit var bubbleView:TextView
    private var panel:LinearLayout?=null
    private var chart:WebView?=null
    private var status:TextView?=null
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private var symbol="XAUUSD";private var period="15m";private var data:List<Candle> = emptyList();private var loadedAt=0L;private var ready=false;private var busy=false
    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();readSelection();wm=getSystemService(WINDOW_SERVICE) as WindowManager;startForegroundMode();createBubble()}
    private fun readSelection(){symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m"}
    private fun startForegroundMode(){val id="mh_analysis";if(Build.VERSION.SDK_INT>=26)(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(NotificationChannel(id,"MH Analysis",NotificationManager.IMPORTANCE_LOW));val b=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,id)else Notification.Builder(this);startForeground(210,b.setContentTitle("MH Analysis running").setContentText("Gold + BTC floating analysis").setSmallIcon(android.R.drawable.ic_menu_compass).build())}
    private fun overlayType()=if(Build.VERSION.SDK_INT>=26)WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
    private fun createBubble(){
        bubbleView=TextView(this).apply{text="MS";textSize=15f;gravity=Gravity.CENTER;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=GradientDrawable().apply{shape=GradientDrawable.OVAL;setColor(Color.BLACK);setStroke(dp(2),Color.WHITE)}}
        val p=WindowManager.LayoutParams(dp(60),dp(60),overlayType(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.START;x=dp(18);y=dp(210)}
        var sx=0;var sy=0;var tx=0f;var ty=0f;var moved=false
        bubbleView.setOnTouchListener{_,e->when(e.action){MotionEvent.ACTION_DOWN->{sx=p.x;sy=p.y;tx=e.rawX;ty=e.rawY;moved=false;true};MotionEvent.ACTION_MOVE->{val dx=(e.rawX-tx).toInt();val dy=(e.rawY-ty).toInt();if(abs(dx)>dp(4)||abs(dy)>dp(4))moved=true;p.x=sx+dx;p.y=sy+dy;wm.updateViewLayout(bubbleView,p);true};MotionEvent.ACTION_UP->{if(!moved)togglePanel();true};else->false}}
        wm.addView(bubbleView,p)
    }
    private fun togglePanel(){if(panel==null)showPanel()else hidePanel()}
    private fun showPanel(){
        readSelection();val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(10),dp(10),dp(10),dp(10));background=GradientDrawable().apply{setColor(Color.rgb(6,6,6));cornerRadius=dp(16).toFloat();setStroke(dp(1),Color.GRAY)}};panel=root
        val h=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};h.addView(textView("MS • MH ANALYSIS v3",14f,true),LinearLayout.LayoutParams(0,dp(42),1f));h.addView(Button(this).apply{text="—";setOnClickListener{hidePanel()}},LinearLayout.LayoutParams(dp(48),dp(40)));root.addView(h)
        val pr=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};pr.addView(Button(this).apply{text="GOLD";setOnClickListener{switchPair("XAUUSD")}},LinearLayout.LayoutParams(0,dp(42),1f));pr.addView(Button(this).apply{text="BTC";setOnClickListener{switchPair("BTCUSDT")}},LinearLayout.LayoutParams(0,dp(42),1f));root.addView(pr)
        chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){ready=true;loadData()}};loadUrl("file:///android_asset/chart.html")};root.addView(chart,LinearLayout.LayoutParams(-1,dp(290)))
        root.addView(Button(this).apply{text="NEW ANALYZE";setTextColor(Color.BLACK);setBackgroundColor(Color.WHITE);setOnClickListener{analyze()}},LinearLayout.LayoutParams(-1,dp(48)));status=textView("$symbol • $period",10.5f).apply{setPadding(0,dp(8),0,0)};root.addView(status)
        wm.addView(root,WindowManager.LayoutParams(dp(360),dp(570),overlayType(),WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply{gravity=Gravity.TOP or Gravity.END;x=dp(8);y=dp(55)})
    }
    private fun switchPair(next:String){if(symbol==next)return;symbol=next;prefs.edit().putString("symbol",symbol).apply();data=emptyList();loadedAt=0L;chart?.evaluateJavascript("clearChart()",null);status?.text="Loading $symbol...";loadData()}
    private fun loadData(){
        if(!ready||busy)return;val k=prefs.getString("api_key","")?.trim().orEmpty();if(k.isBlank()){status?.text="API key missing";return};busy=true
        thread{try{val(c,_)=FcsClient.history(k,symbol,period,220,false);data=c;loadedAt=System.currentTimeMillis();val ev=SignalStore.evaluate(this,symbol,period,c);Handler(Looper.getMainLooper()).post{render(c);busy=false;if(ev!=null&&ev.state in setOf("WIN","LOSS","EXPIRED"))status?.text="SIGNAL ${ev.state} • record saved" else showActive()}}catch(e:Exception){Handler(Looper.getMainLooper()).post{busy=false;status?.text="Load failed: ${e.message}"}}}
    }
    private fun displayed():ActiveSignal?=SignalStore.loadActive(this,symbol,period)?:SignalStore.openTrades(this).firstOrNull{it.signal.symbol==symbol&&it.signal.timeframe==period}
    private fun render(c:List<Candle>){val a=JSONArray();c.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart?.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showOverlay(displayed())}
    private fun analyze(){
        if(busy)return;val fresh=data.isNotEmpty()&&System.currentTimeMillis()-loadedAt<60_000L;if(!fresh){status?.text="Refreshing data...";loadData();return}
        SignalStore.evaluate(this,symbol,period,data);val s=AnalysisEngine.analyze(symbol,period,data)
        if(s==null){status?.text="NO NEW TRADE\n${AnalysisEngine.noSignalReason(symbol,period,data)}";showOverlay(displayed());return}
        val dup=SignalStore.findDuplicate(this,s)
        if(dup!=null){status?.text="NO NEW TRADE\nSame ${dup.signal.direction} setup already ${if(dup.state=="ACTIVE")"TRIGGERED" else dup.state} near ${price(dup.signal.entry)}. Duplicate not recorded.";showOverlay(dup);return}
        SignalStore.acceptCandidate(this,s);showActive();showOverlay(SignalStore.loadActive(this,symbol,period))
    }
    private fun showActive(){
        val a=displayed();if(a==null){status?.text="$symbol • $period • no active or pending setup";showOverlay(null);return};val s=a.signal;val fvg=if(s.fvgLow!=null&&s.fvgHigh!=null)"${s.fvgType} FVG ${price(s.fvgLow)}-${price(s.fvgHigh)}" else "No recent FVG";val life=if(a.state=="ACTIVE")"Entry triggered; track TP1/SL" else "Pending until structure/confirmation changes — no time expiry"
        status?.text="${s.direction} ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}  SL ${price(s.sl)}  TP1 ${price(s.tp1)}\nBull ${s.bullScore} / Bear ${s.bearScore} • RSI ${String.format(Locale.US,"%.1f",s.rsi)}\n$fvg\n$life"
    }
    private fun showOverlay(a:ActiveSignal?){if(a==null){chart?.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val j=JSONObject().put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("state",a.state).put("validBars",0).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh);chart?.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})",null)}
    private fun price(v:Double?)=when{v==null->"-";abs(v)>=100->String.format(Locale.US,"%.2f",v);else->String.format(Locale.US,"%.5f",v)}
    private fun hidePanel(){panel?.let{runCatching{wm.removeView(it)}};panel=null;chart=null;status=null;ready=false}
    private fun textView(v:String,s:Float,b:Boolean=false)=TextView(this).apply{text=v;textSize=s;setTextColor(Color.WHITE);if(b)setTypeface(typeface,Typeface.BOLD)}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
    override fun onDestroy(){hidePanel();if(::bubbleView.isInitialized)runCatching{wm.removeView(bubbleView)};super.onDestroy()}
}
