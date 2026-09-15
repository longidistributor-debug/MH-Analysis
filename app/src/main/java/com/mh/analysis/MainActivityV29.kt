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
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import kotlin.concurrent.thread
import kotlin.math.abs

class MainActivityV29:Activity(){
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private lateinit var chart:WebView
    private lateinit var historyStatus:TextView
    private lateinit var historyInput:EditText
    private lateinit var historyButton:Button
    private lateinit var status:TextView
    private lateinit var calls:TextView
    private lateinit var pairLabel:TextView
    private var symbol="XAUUSD"
    private var period="15m"
    private var chartReady=false
    private var busy=false
    private var editHistory=false
    private var candles:List<Candle> = emptyList()

    override fun onCreate(b:Bundle?){
        super.onCreate(b);FcsClient.init(this)
        if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12)
        window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK
        symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD"
        period=prefs.getString("period","15m")?:"15m"
        setContentView(buildUi())
        showExisting()
        maybeShowOldSetupPopup()
        startMonitorIfNeeded()
    }

    private fun buildUi():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(14),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        root.addView(txt("بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",21f,true).apply{gravity=Gravity.CENTER;textAlignment=View.TEXT_ALIGNMENT_CENTER;setPadding(0,dp(3),0,dp(14))},LinearLayout.LayoutParams(-1,-2))
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(TextView(this).apply{text="MS";gravity=Gravity.CENTER;textSize=22f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=round(Color.BLACK,18f,Color.WHITE)},LinearLayout.LayoutParams(dp(64),dp(64)))
        header.addView(LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0);addView(txt("MH ANALYSIS",26f,true));addView(txt("Live Market Structure Engine",11f,false,Color.LTGRAY));addView(txt("MS • v29 • TRADINGVIEW LIVE",10f,true));addView(txt("◉ WhatsApp  +92 343 4824609",11f,false,Color.LTGRAY))},LinearLayout.LayoutParams(0,-2,1f))
        root.addView(header)

        val keyCard=card();historyStatus=txt("",12f,true,Color.LTGRAY);keyCard.addView(historyStatus)
        historyInput=input("Enter analysis access key").apply{inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD};keyCard.addView(historyInput,lp48(7))
        historyButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{saveHistoryKey()}};keyCard.addView(historyButton,lp46(8));updateKeyUi();root.addView(keyCard,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(12)})

        root.addView(section("MARKET"));val mc=card();val pairs=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL}
        pairs.addView(pairButton("GOLD\nXAUUSD"){switchPair("XAUUSD")},LinearLayout.LayoutParams(0,dp(58),1f).apply{rightMargin=dp(6)})
        pairs.addView(pairButton("BTC\nBTCUSDT"){switchPair("BTCUSDT")},LinearLayout.LayoutParams(0,dp(58),1f).apply{leftMargin=dp(6)})
        mc.addView(pairs)
        val row=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};pairLabel=txt("$symbol • $period",13f,true);row.addView(pairLabel,LinearLayout.LayoutParams(0,dp(48),1f))
        val periods=arrayOf("1m","5m","15m","30m","1h");if(period !in periods)period="15m"
        val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV29,android.R.layout.simple_spinner_dropdown_item,periods);setSelection(periods.indexOf(period))};row.addView(sp,LinearLayout.LayoutParams(dp(135),dp(48)));mc.addView(row);root.addView(mc)
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np==period)return;period=np;prefs.edit().putString("period",period).apply();switchVisibleChart()};override fun onNothingSelected(p:AdapterView<*>?){}}

        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{
            settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.mediaPlaybackRequiresUserGesture=false
            CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true)
            setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;switchVisibleChart();showSignalCard(currentDisplayedSignal())}}
            val html=assets.open("tradingview_live.html").bufferedReader().use{it.readText()};loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)
        };cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)

        root.addView(section("SIGNAL CONTROL"));val sc=card();calls=txt("Analysis calls: ${usage()}/500",11f,true,Color.LTGRAY);sc.addView(calls)
        val br=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};br.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(4)});br.addView(actionButton("RECORDS",false){showRecords()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(2);rightMargin=dp(2)});br.addView(actionButton("ALARM",false){alarmAndShow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(4)});sc.addView(br,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)})
        status=txt("READY",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)

        root.addView(section("FLOATING / BACKGROUND"));val fc=card();fc.addView(Button(this).apply{text="ENABLE MS LIVE FLOAT";setTextColor(Color.WHITE);background=round(Color.rgb(25,25,25),12f,Color.GRAY);setOnClickListener{enableFloat()}},LinearLayout.LayoutParams(-1,dp(52)));root.addView(fc)
        return ScrollView(this).apply{isFillViewport=true;setBackgroundColor(Color.BLACK);addView(root)}
    }

    private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();switchVisibleChart()}
    private fun switchVisibleChart(){pairLabel.text="$symbol • $period";if(chartReady)chart.evaluateJavascript("loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null);showExisting()}

    private fun analyzeNow(){
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}
        if(busy){status.text="ANALYSIS REQUEST ALREADY RUNNING";return}
        busy=true;val reqSymbol=symbol;val reqPeriod=period;status.text="NEW ANALYZE • reading current $reqSymbol $reqPeriod structure…"
        thread{
            try{
                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)
                runOnUiThread{
                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"
                    if(reqSymbol!=symbol||reqPeriod!=period){status.text="MARKET CHANGED • press NEW ANALYZE for $symbol $period";return@runOnUiThread}
                    candles=out;performAnalysis()
                }
            }catch(e:Exception){runOnUiThread{busy=false;status.text="ANALYSIS DATA UNAVAILABLE\n${e.message}\nTradingView live chart is unaffected."}}
        }
    }

    private fun performAnalysis(){
        if(candles.size<60){status.text="NOT ENOUGH MARKET HISTORY FOR RELIABLE ANALYSIS";return}
        SignalStore.evaluate(this,symbol,period,candles)
        val existing=currentDisplayedSignal();val s=AnalysisEngine.analyze(symbol,period,candles)
        if(s==null){
            if(existing!=null&&existing.state in setOf("PENDING","ACTIVE")){val x=existing.signal;status.text="EXISTING SETUP • ${existing.state}\n${x.direction} ${x.score}/100\nEntry ${price(x.entry)}   SL ${price(x.sl)}\nTP1 ${price(x.tp1)}   TP2 ${price(x.tp2)}\n\nNo materially better replacement yet.";showSignalCard(existing)}
            else{status.text="NO NEW SETUP\n${AnalysisEngine.noSignalReason(symbol,period,candles)}";showSignalCard(existing)}
            return
        }
        val d=SignalStore.findDuplicate(this,s);if(d!=null){status.text="EXISTING SETUP • ${d.state}\n${d.signal.direction} ${d.signal.score}/100\nEntry ${price(d.signal.entry)}   SL ${price(d.signal.sl)}\nTP1 ${price(d.signal.tp1)}   TP2 ${price(d.signal.tp2)}";showSignalCard(d);return}
        SignalStore.acceptCandidate(this,s);startMonitorIfNeeded();showExisting()
    }

    private fun currentDisplayedSignal()=SignalStore.displayState(this,symbol,period)
    private fun showSignalCard(a:ActiveSignal?){
        if(!chartReady)return
        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}
        val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)
        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }
    private fun showExisting(){
        if(!::status.isInitialized)return
        val a=currentDisplayedSignal();if(a==null){status.text="$symbol • $period\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH SETUP";showSignalCard(null);return}
        val s=a.signal;val why=s.reasons.take(6).joinToString("\n")
        status.text="${s.direction} • ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\nWHY THIS TRADE\n${s.setupReason}\n\nCONFIRMATIONS\n$why";showSignalCard(a)
    }

    private fun showRecords(){
        val days=lastThreeDays();val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(12),dp(8),dp(12),dp(8))};val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivityV29,android.R.layout.simple_spinner_dropdown_item,days)};val tv=TextView(this).apply{setTextColor(Color.BLACK);textSize=13f}
        fun refresh(){val day=sp.selectedItem?.toString()?:days.first();val b=StringBuilder(SignalStore.stats(this,day)).append("\n\n");SignalStore.openForDay(this,day).forEach{b.append("OPEN ${it.signal.symbol} ${it.signal.timeframe} ${it.signal.direction} Entry ${price(it.signal.entry)}\n")};SignalStore.recordsForDay(this,day).forEach{b.append("${it.result} ${it.symbol} ${it.timeframe} ${it.direction} ${it.score}/100\n")};tv.text=b.toString()}
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()};override fun onNothingSelected(p:AdapterView<*>?){}}
        box.addView(sp);box.addView(ScrollView(this).apply{addView(tv)},LinearLayout.LayoutParams(-1,dp(420)));AlertDialog.Builder(this).setTitle("MS Records • Last 3 Days").setView(box).setNeutralButton("Reset"){_,_->SignalStore.reset(this);showExisting()}.setNegativeButton("Close",null).show()
    }

    private fun alarmAndShow(){
        SignalStore.loadActive(this,symbol,period)?.takeIf{it.state=="PENDING"}?.let{AlarmStore.addSaved(this,it.signal)}
        val items=AlarmStore.list(this);val text=if(items.isEmpty())"No alarms." else items.joinToString("\n\n"){"${it.symbol} ${it.timeframe} ${it.direction}\nEntry ${price(it.entry)} • ${it.status}"}
        AlertDialog.Builder(this).setTitle("MS Alarm Lifecycle").setMessage(text).setPositiveButton("ARM CURRENT"){_,_->SignalStore.loadActive(this,symbol,period)?.takeIf{it.state=="PENDING"}?.let{a->AlarmStore.addSaved(this,a.signal);AlarmStore.list(this).firstOrNull{it.signalId==a.signal.id}?.let{x->AlarmStore.setEnabled(this,x.id,true)};startMonitorIfNeeded()}}.setNegativeButton("Close",null).show()
    }

    private fun maybeShowOldSetupPopup(){
        val a=currentDisplayedSignal()?:return;if(!SignalStore.isStale(a))return
        AlertDialog.Builder(this).setTitle("Old setup").setMessage("The saved ${a.signal.timeframe} setup is old. TradingView is live; press NEW ANALYZE when you want a fresh market setup.").setPositiveButton("NEW ANALYZE"){_,_->analyzeNow()}.setNegativeButton("×",null).show()
    }

    private fun savedHistoryKey()=prefs.getString("api_key","")?.trim().orEmpty()
    private fun updateKeyUi(){val h=savedHistoryKey().isNotBlank();historyInput.visibility=if(h&&!editHistory)View.GONE else View.VISIBLE;historyStatus.text=if(h&&!editHistory)"● ANALYSIS KEY SAVED" else "ANALYSIS DATA KEY";historyButton.text=if(h&&!editHistory)"UPDATE ANALYSIS KEY" else "SAVE ANALYSIS KEY"}
    private fun saveHistoryKey(){if(savedHistoryKey().isNotBlank()&&!editHistory){editHistory=true;updateKeyUi();return};val x=historyInput.text.toString().trim();if(x.isBlank())return;prefs.edit().putString("api_key",x).apply();editHistory=false;historyInput.setText("");updateKeyUi();Toast.makeText(this,"Analysis key saved",Toast.LENGTH_SHORT).show();startMonitorIfNeeded()}

    private fun startMonitorIfNeeded(){if(savedHistoryKey().isBlank())return;if(SignalStore.pendingSignals(this).isEmpty()&&SignalStore.openTrades(this).isEmpty()&&AlarmStore.armed(this).isEmpty())return;val i=Intent(this,AlarmService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}
    private fun enableFloat(){if(!Settings.canDrawOverlays(this)){startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")));return};val i=Intent(this,OverlayService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}

    private fun lastThreeDays():List<String>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);return(0..2).map{val c=Calendar.getInstance();c.add(Calendar.DAY_OF_YEAR,-it);f.format(c.time)}}
    private fun month()=SimpleDateFormat("yyyy-MM",Locale.US).format(Date())
    private fun usage():Int{val m=month();if(prefs.getString("usage_month","")!=m)prefs.edit().putString("usage_month",m).putInt("usage",0).apply();return prefs.getInt("usage",0)}
    private fun addUsage(n:Int){prefs.edit().putInt("usage",usage()+n.coerceAtLeast(0)).apply()}
    private fun price(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun pairButton(t:String,click:()->Unit)=Button(this).apply{text=t;setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{click()}}
    private fun actionButton(t:String,p:Boolean,click:()->Unit)=Button(this).apply{text=t;textSize=11f;setTypeface(typeface,Typeface.BOLD);setTextColor(if(p)Color.BLACK else Color.WHITE);background=if(p)round(Color.WHITE,12f)else round(Color.rgb(24,24,24),12f,Color.GRAY);setOnClickListener{click()}}
    private fun input(h:String)=EditText(this).apply{hint=h;setHintTextColor(Color.GRAY);setTextColor(Color.WHITE);textSize=13f;setSingleLine(true);background=round(Color.rgb(20,20,20),12f,Color.DKGRAY);setPadding(dp(14),0,dp(14),0)}
    private fun lp48(top:Int)=LinearLayout.LayoutParams(-1,dp(48)).apply{topMargin=dp(top)}
    private fun lp46(top:Int)=LinearLayout.LayoutParams(-1,dp(46)).apply{topMargin=dp(top)}
    private fun section(s:String)=txt(s,11f,true,Color.GRAY).apply{setPadding(0,dp(18),0,dp(8))}
    private fun card()=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),dp(14),dp(14),dp(14));background=round(Color.rgb(8,8,8),16f,Color.rgb(45,45,45))}
    private fun txt(s:String,z:Float,b:Boolean=false,c:Int=Color.WHITE)=TextView(this).apply{text=s;textSize=z;setTextColor(c);if(b)setTypeface(typeface,Typeface.BOLD)}
    private fun round(c:Int,r:Float,stroke:Int?=null)=GradientDrawable().apply{setColor(c);cornerRadius=dp(r.toInt()).toFloat();if(stroke!=null)setStroke(dp(1),stroke)}
    private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
}
