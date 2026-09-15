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
import android.text.InputType
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
    private lateinit var keyInput:EditText;private lateinit var keyStatus:TextView;private lateinit var keyButton:Button
    private lateinit var chart:WebView;private lateinit var status:TextView;private lateinit var calls:TextView;private lateinit var pairLabel:TextView
    private var symbol="XAUUSD";private var period="15m";private var chartReady=false;private var busy=false;private var editingKey=false
    private var candles:List<Candle> = emptyList();private var loadedSymbol="";private var loadedPeriod="";private var loadedAt=0L
    private var selectionGeneration=0L;private var queuedLoad=false;private var queuedForce=false;private var queuedPassive=true;private var queuedAfter:(()->Unit)?=null
    private val liveHandler=Handler(Looper.getMainLooper())
    private val liveRefresh=object:Runnable{override fun run(){if(chartReady&&savedKey().isNotBlank())load(false,true);liveHandler.postDelayed(this,10_000)}}

    override fun onCreate(b:Bundle?){super.onCreate(b);if(Build.VERSION.SDK_INT>=33)requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS),12);window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK;symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";period=prefs.getString("period","15m")?:"15m";setContentView(ui());if(savedKey().isNotBlank())startStateService()}
    override fun onResume(){super.onResume();liveHandler.removeCallbacks(liveRefresh);if(savedKey().isNotBlank())liveHandler.postDelayed(liveRefresh,3_000);showExisting();showStalePopupIfNeeded();if(Settings.canDrawOverlays(this)&&prefs.getBoolean("want_float",false)){prefs.edit().putBoolean("want_float",false).apply();startOverlay()}}
    override fun onPause(){liveHandler.removeCallbacks(liveRefresh);super.onPause()}

    private fun ui():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(14),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        root.addView(txt("بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",21f,true).apply{gravity=Gravity.CENTER;textAlignment=View.TEXT_ALIGNMENT_CENTER;setPadding(0,dp(3),0,dp(14))},LinearLayout.LayoutParams(-1,-2))
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(TextView(this).apply{text="MS";gravity=Gravity.CENTER;textSize=22f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=round(Color.BLACK,18f,Color.WHITE)},LinearLayout.LayoutParams(dp(64),dp(64)))
        header.addView(LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0);addView(txt("MH ANALYSIS",26f,true));addView(txt("Live Market Structure Engine",11f,false,Color.LTGRAY));addView(txt("MS • v14 • BEST SETUP",10f,true));addView(txt("◉ WhatsApp  +92 343 4824609",11f,false,Color.LTGRAY))},LinearLayout.LayoutParams(0,-2,1f));root.addView(header)

        val kc=card();keyStatus=txt("",12f,true,Color.LTGRAY);kc.addView(keyStatus);keyInput=input("Enter market data key","").apply{inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD};kc.addView(keyInput,LinearLayout.LayoutParams(-1,dp(52)).apply{topMargin=dp(8)});keyButton=Button(this).apply{setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{handleKeyButton()}};kc.addView(keyButton,LinearLayout.LayoutParams(-1,dp(50)).apply{topMargin=dp(10)});updateKeyUi();root.addView(kc,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(12)})

        root.addView(section("MARKET"));val mc=card();val pairRow=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};pairRow.addView(Button(this).apply{text="GOLD\nXAUUSD";setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{switchPair("XAUUSD")}},LinearLayout.LayoutParams(0,dp(58),1f).apply{rightMargin=dp(6)});pairRow.addView(Button(this).apply{text="BTC\nBTCUSDT";setTextColor(Color.BLACK);background=round(Color.WHITE,12f);setOnClickListener{switchPair("BTCUSDT")}},LinearLayout.LayoutParams(0,dp(58),1f).apply{leftMargin=dp(6)});mc.addView(pairRow)
        val row2=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL};pairLabel=txt("$symbol • $period",13f,true);row2.addView(pairLabel,LinearLayout.LayoutParams(0,dp(48),1f));val periods=arrayOf("1m","5m","15m","30m","1h");if(period !in periods)period="15m";val sp=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,periods);setSelection(periods.indexOf(period).coerceAtLeast(0))};row2.addView(sp,LinearLayout.LayoutParams(dp(135),dp(48)));mc.addView(row2);root.addView(mc)
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){val np=periods[pos];if(np==period)return;period=np;prefs.edit().putString("period",period).apply();selectionGeneration++;invalidateLoadedChart("SWITCHING TO $symbol • $period…");if(chartReady&&savedKey().isNotBlank())load(false,true)};override fun onNothingSelected(p:AdapterView<*>?){}}

        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;setBackgroundColor(Color.BLACK);webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;if(savedKey().isNotBlank())load(false,true)}};loadUrl("file:///android_asset/chart.html")};cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)

        root.addView(section("SIGNAL CONTROL"));val ac=card();calls=txt("Calls: ${usage()}/500",11f,true,Color.LTGRAY);ac.addView(calls);val btns=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};btns.addView(actionButton("NEW ANALYZE",true){newAnalyze()},LinearLayout.LayoutParams(0,dp(54),1f).apply{rightMargin=dp(4)});btns.addView(actionButton("RECORDS",false){showRecords()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(2);rightMargin=dp(2)});btns.addView(actionButton("ALARM",false){alarmAndShow()},LinearLayout.LayoutParams(0,dp(54),1f).apply{leftMargin=dp(4)});ac.addView(btns,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});status=txt("READY",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};ac.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(ac)

        root.addView(section("FLOATING / BACKGROUND"));val fc=card();fc.addView(Button(this).apply{text="ENABLE MS LIVE FLOAT";setTextColor(Color.WHITE);background=round(Color.rgb(25,25,25),12f,Color.GRAY);setOnClickListener{enableFloat()}},LinearLayout.LayoutParams(-1,dp(52)));root.addView(fc)
        return ScrollView(this).apply{isFillViewport=true;setBackgroundColor(Color.BLACK);addView(root)}
    }

    private fun invalidateLoadedChart(message:String){pairLabel.text="$symbol • $period";candles=emptyList();loadedSymbol="";loadedPeriod="";loadedAt=0L;if(::chart.isInitialized&&chartReady)chart.evaluateJavascript("clearChart();showMessage(${JSONObject.quote(message)})",null);if(::status.isInitialized)status.text=message}
    private fun savedKey()=prefs.getString("api_key","")?.trim().orEmpty()
    private fun updateKeyUi(){val saved=savedKey().isNotBlank();if(saved&&!editingKey){keyInput.setText("");keyInput.visibility=View.GONE;keyStatus.text="● DATA KEY SAVED • AUTO-CONNECT";keyButton.text="UPDATE KEY"}else{keyInput.visibility=View.VISIBLE;keyInput.setText("");keyStatus.text=if(saved)"ENTER NEW KEY • CURRENT KEY STAYS ACTIVE UNTIL SAVE" else "DATA KEY REQUIRED • ENTER ONCE AND SAVE";keyButton.text=if(saved)"SAVE NEW KEY" else "SAVE KEY"}}
    private fun handleKeyButton(){val saved=savedKey().isNotBlank();if(saved&&!editingKey){editingKey=true;updateKeyUi();keyInput.requestFocus();return};val entered=keyInput.text.toString().trim();if(entered.isBlank()){Toast.makeText(this,"Enter a valid key",Toast.LENGTH_SHORT).show();return};prefs.edit().putString("api_key",entered).apply();keyInput.setText("");editingKey=false;updateKeyUi();startStateService();Toast.makeText(this,"Data key saved for this installation",Toast.LENGTH_SHORT).show();selectionGeneration++;if(chartReady)load(true,true)}
    private fun switchPair(s:String){if(symbol==s)return;symbol=s;prefs.edit().putString("symbol",s).apply();selectionGeneration++;invalidateLoadedChart("SWITCHING TO $symbol • $period…");if(savedKey().isNotBlank())load(false,true)}

    private fun load(force:Boolean,passive:Boolean=false,after:(()->Unit)?=null){
        if(!chartReady)return;val k=savedKey();if(k.isBlank()){status.text="DATA KEY REQUIRED";return}
        if(busy){queuedLoad=true;queuedForce=queuedForce||force;queuedPassive=passive;if(after!=null)queuedAfter=after;return}
        busy=true;val reqSymbol=symbol;val reqPeriod=period;val reqGeneration=selectionGeneration
        thread{try{val(data,credits)=FcsClient.history(k,reqSymbol,reqPeriod,220,force);val eval=SignalStore.evaluate(this,reqSymbol,reqPeriod,data);runOnUiThread{if(credits>0)addUsage(credits);calls.text="Calls: ${usage()}/500";val current=reqGeneration==selectionGeneration&&reqSymbol==symbol&&reqPeriod==period;if(current){candles=data;loadedSymbol=reqSymbol;loadedPeriod=reqPeriod;loadedAt=System.currentTimeMillis();render(data,reqSymbol,reqPeriod);pairLabel.text="$reqSymbol • $reqPeriod";if(!passive&&eval!=null&&eval.state in setOf("WIN","LOSS","EXPIRED"))status.text="${eval.state} • lifecycle updated" else showExisting();after?.invoke()};busy=false;drainQueuedLoad()}}catch(e:Exception){runOnUiThread{if(reqGeneration==selectionGeneration&&reqSymbol==symbol&&reqPeriod==period)status.text="MARKET SYNC • $reqSymbol $reqPeriod\n${e.message}";busy=false;drainQueuedLoad()}}}
    }
    private fun drainQueuedLoad(){if(!queuedLoad)return;val f=queuedForce;val p=queuedPassive;val a=queuedAfter;queuedLoad=false;queuedForce=false;queuedPassive=true;queuedAfter=null;load(f,p,a)}
    private fun render(data:List<Candle>,renderSymbol:String=symbol,renderPeriod:String=period){if(renderSymbol!=symbol||renderPeriod!=period)return;val a=JSONArray();data.forEach{a.put(JSONObject().put("t",it.t).put("o",it.o).put("h",it.h).put("l",it.l).put("c",it.c).put("v",it.v))};chart.evaluateJavascript("renderCandles(${JSONObject.quote(a.toString())},${JSONObject.quote(renderSymbol)},${JSONObject.quote(renderPeriod)})",null);showSignalOverlay(currentDisplayedSignal())}
    private fun currentDisplayedSignal():ActiveSignal?=SignalStore.displayState(this,symbol,period)

    private fun newAnalyze(){
        if(savedKey().isBlank()){Toast.makeText(this,"Save data key once first",Toast.LENGTH_SHORT).show();return};val have=candles.isNotEmpty()&&loadedSymbol==symbol&&loadedPeriod==period&&System.currentTimeMillis()-loadedAt<35_000
        if(!have){status.text="REFRESHING $symbol • $period…";load(false,false){newAnalyze()};return};if(busy){queuedLoad=true;queuedPassive=false;queuedAfter={newAnalyze()};return}
        SignalStore.evaluate(this,symbol,period,candles)
        val existing=currentDisplayedSignal()
        val s=AnalysisEngine.analyze(symbol,period,candles)
        if(s==null){
            if(existing!=null&&existing.state in setOf("PENDING","ACTIVE")){
                val es=existing.signal
                status.text="EXISTING SETUP • ${es.timeframe} • ${existing.state}\n${es.direction} ${es.score}/100\nEntry ${price(es.entry)}   SL ${price(es.sl)}\nTP1 ${price(es.tp1)}   TP2 ${price(es.tp2)}\n\nNo stronger new setup has replaced this one yet."
                showSignalOverlay(existing)
            }else{
                status.text="NO NEW SETUP\n${AnalysisEngine.noSignalReason(symbol,period,candles)}"
                showSignalOverlay(existing)
            }
            return
        }
        val duplicate=SignalStore.findDuplicate(this,s)
        if(duplicate!=null){
            val ds=duplicate.signal
            status.text="EXISTING SETUP • ${ds.timeframe} • ${duplicate.state}\n${ds.direction} ${ds.score}/100\nEntry ${price(ds.entry)}   SL ${price(ds.sl)}\nTP1 ${price(ds.tp1)}   TP2 ${price(ds.tp2)}\n\nThis remains the best matching setup; no materially new setup is confirmed yet."
            showSignalOverlay(duplicate);return
        }
        SignalStore.acceptCandidate(this,s);startStateService();showExisting();showSignalOverlay(SignalStore.loadActive(this,symbol,period))
    }

    private fun showExisting(){
        if(!::status.isInitialized)return;val a=currentDisplayedSignal();if(a==null){status.text="$symbol • $period\nREADY FOR ANALYSIS";if(::chart.isInitialized&&chartReady)chart.evaluateJavascript("setSignal(null)",null);return};val s=a.signal
        val life=when(a.state){"PENDING"->"PENDING — waiting for entry while live structure remains valid.";"ACTIVE"->"TRIGGERED / ACTIVE — tracking TP1 / SL.";"WIN"->"CLOSED WIN";"LOSS"->"CLOSED LOSS";"EXPIRED"->"EXPIRED / NO LONGER VALID";else->a.state}
        val reason=SignalStore.lifecycleReason(this,s.id);val confirms=s.reasons.take(6).joinToString("\n")
        status.text="${s.direction} • ${s.score}/100 • ${a.state}\n$life\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\nWHY THIS TRADE\n${s.setupReason}\n\nCONFIRMATIONS\n$confirms\n${if(reason.isNotBlank())"\nLIFECYCLE\n$reason" else ""}"
    }
    private fun showSignalOverlay(a:ActiveSignal?){if(!::chart.isInitialized||!chartReady)return;if(a==null){chart.evaluateJavascript("setSignal(null)",null);return};val s=a.signal;val j=JSONObject().put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("state",a.state).put("fvgType",s.fvgType).put("fvgLow",s.fvgLow).put("fvgHigh",s.fvgHigh);chart.evaluateJavascript("setSignal(${JSONObject.quote(j.toString())})",null)}

    private fun showRecords(){
        val days=lastThreeDays();val box=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(16),dp(8),dp(16),dp(8))};val spinner=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,days)};val text=TextView(this).apply{setTextColor(Color.BLACK);textSize=13f;setPadding(0,dp(10),0,dp(10))}
        fun refresh(){val day=spinner.selectedItem?.toString()?:days.first();val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);val pending=SignalStore.pendingSignals(this).filter{f.format(Date(it.signal.createdAt))==day};val open=SignalStore.openForDay(this,day);val closed=SignalStore.recordsForDay(this,day);val b=StringBuilder(SignalStore.stats(this,day)).append("\nPending: ${pending.size}\n\n");if(pending.isNotEmpty()){b.append("PENDING SETUPS\n");pending.forEach{x->b.append("${x.signal.symbol} ${x.signal.timeframe} • ${x.signal.direction} • Entry ${price(x.signal.entry)}\n")};b.append("\n")};if(open.isNotEmpty()){b.append("OPEN / TRIGGERED\n");open.forEach{x->b.append("${x.signal.symbol} ${x.signal.timeframe} • ${x.signal.direction} • Entry ${price(x.signal.entry)} • TP1 ${price(x.signal.tp1)} • SL ${price(x.signal.sl)}\n")};b.append("\n")};if(closed.isNotEmpty()){b.append("CLOSED / EXPIRED\n");closed.forEach{x->b.append("${x.symbol} ${x.timeframe} • ${x.direction} • ${x.result} • ${x.score}/100 • ${time(x.startedAt)}\n")}};if(pending.isEmpty()&&open.isEmpty()&&closed.isEmpty())b.append("No records for this day.");text.text=b.toString()}
        spinner.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()};override fun onNothingSelected(p:AdapterView<*>?){}};box.addView(spinner);box.addView(ScrollView(this).apply{addView(text)},LinearLayout.LayoutParams(-1,dp(430)));val d=AlertDialog.Builder(this).setTitle("MS Records • Last 3 Days").setView(box).setNegativeButton("Close",null).setNeutralButton("Reset Records",null).create();d.setOnShowListener{d.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener{AlertDialog.Builder(this).setTitle("Reset records?").setMessage("Deletes pending/open/closed tracking records.").setPositiveButton("Reset"){_,_->SignalStore.reset(this);refresh();showExisting()}.setNegativeButton("Cancel",null).show()}};d.show()
    }

    private fun alarmAndShow(){val pending=SignalStore.loadActive(this,symbol,period);if(pending!=null&&pending.state=="PENDING"){AlarmStore.addSaved(this,pending.signal);Toast.makeText(this,"Pending signal saved to Alarm list",Toast.LENGTH_SHORT).show()}else Toast.makeText(this,"No PENDING setup to add",Toast.LENGTH_SHORT).show();showAlarms()}
    private fun showAlarms(){val days=lastThreeDays();val outer=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(12),dp(8),dp(12),dp(8))};val spinner=Spinner(this).apply{adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,days)};val listBox=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL};fun refresh(){listBox.removeAllViews();val day=spinner.selectedItem?.toString()?:days.first();val entries=AlarmStore.forDay(this,day);if(entries.isEmpty())listBox.addView(TextView(this).apply{text="No alarm history for this day.";setTextColor(Color.BLACK);setPadding(0,dp(12),0,dp(12))});entries.forEach{a->val block=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(0,dp(7),0,dp(7))};block.addView(TextView(this).apply{text="${a.symbol} ${a.timeframe} • ${a.direction}\nEntry ${price(a.entry)} • ${a.status}";setTextColor(Color.BLACK)});val controls=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL};val terminal=a.status in setOf("TRIGGERED","EXPIRED");controls.addView(Button(this).apply{text=if(terminal)a.status else if(a.status=="ARMED")"OFF" else "ON";isEnabled=!terminal;setOnClickListener{val on=a.status!="ARMED";AlarmStore.setEnabled(this@MainActivity,a.id,on);if(on)startStateService();refresh()}},LinearLayout.LayoutParams(0,dp(46),1f));controls.addView(Button(this).apply{text="DELETE";setOnClickListener{AlarmStore.delete(this@MainActivity,a.id);refresh()}},LinearLayout.LayoutParams(0,dp(46),1f));block.addView(controls);listBox.addView(block)}};spinner.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){refresh()};override fun onNothingSelected(p:AdapterView<*>?){}};outer.addView(spinner);outer.addView(ScrollView(this).apply{addView(listBox)},LinearLayout.LayoutParams(-1,dp(420)));AlertDialog.Builder(this).setTitle("MS Alarm Lifecycle").setView(outer).setNegativeButton("Close",null).setNeutralButton("Reset Alarms"){_,_->AlarmStore.reset(this)}.show()}

    private fun showStalePopupIfNeeded(){val a=currentDisplayedSignal()?:return;if(!SignalStore.isStale(a))return;val k="stale_${a.signal.id}_${a.state}";if(prefs.getBoolean(k,false))return;prefs.edit().putBoolean(k,true).apply();AlertDialog.Builder(this).setTitle("OLD SETUP").setMessage("The saved ${a.signal.symbol} ${a.signal.timeframe} setup is old (${a.state}). History is preserved, but it is not treated as a fresh signal. Tap NEW ANALYZE to assess the current market.").setPositiveButton("NEW ANALYZE"){_,_->newAnalyze()}.setNegativeButton("✕ CLOSE",null).show()}
    private fun startStateService(){if(savedKey().isBlank())return;val i=Intent(this,AlarmService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)}
    private fun enableFloat(){if(savedKey().isBlank()){Toast.makeText(this,"Save data key once first",Toast.LENGTH_LONG).show();return};if(!Settings.canDrawOverlays(this)){prefs.edit().putBoolean("want_float",true).apply();startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")))}else startOverlay()}
    private fun startOverlay(){val i=Intent(this,OverlayService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i);Toast.makeText(this,"MS floating mode active",Toast.LENGTH_SHORT).show()}
    private fun actionButton(label:String,primary:Boolean,click:()->Unit)=Button(this).apply{text=label;textSize=11f;setTypeface(typeface,Typeface.BOLD);setTextColor(if(primary)Color.BLACK else Color.WHITE);background=if(primary)round(Color.WHITE,12f)else round(Color.rgb(24,24,24),12f,Color.GRAY);setOnClickListener{click()}}
    private fun lastThreeDays():List<String>{val f=SimpleDateFormat("yyyy-MM-dd",Locale.US);val cal=Calendar.getInstance();return(0..2).map{d->val c=cal.clone() as Calendar;c.add(Calendar.DAY_OF_YEAR,-d);f.format(c.time)}}
    private fun month()=SimpleDateFormat("yyyy-MM",Locale.US).format(Date());private fun usage():Int{val m=month();if(prefs.getString("usage_month","")!=m)prefs.edit().putString("usage_month",m).putInt("usage",0).apply();return prefs.getInt("usage",0)};private fun addUsage(n:Int){prefs.edit().putInt("usage",usage()+n.coerceAtLeast(0)).apply()}
    private fun time(ms:Long)=SimpleDateFormat("dd MMM HH:mm",Locale.US).format(Date(ms));private fun price(v:Double?)=if(v==null)"-" else if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    private fun input(h:String,v:String)=EditText(this).apply{hint=h;setHintTextColor(Color.GRAY);setTextColor(Color.WHITE);textSize=13f;setSingleLine(true);setText(v);background=round(Color.rgb(20,20,20),12f,Color.DKGRAY);setPadding(dp(14),0,dp(14),0)}
    private fun section(s:String)=txt(s,11f,true,Color.GRAY).apply{setPadding(0,dp(18),0,dp(8))};private fun card()=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),dp(14),dp(14),dp(14));background=round(Color.rgb(8,8,8),16f,Color.rgb(45,45,45))}
    private fun txt(s:String,z:Float,b:Boolean=false,c:Int=Color.WHITE)=TextView(this).apply{text=s;textSize=z;setTextColor(c);if(b)setTypeface(typeface,Typeface.BOLD)};private fun round(c:Int,r:Float,stroke:Int?=null)=GradientDrawable().apply{setColor(c);cornerRadius=dp(r.toInt()).toFloat();if(stroke!=null)setStroke(dp(1),stroke)};private fun dp(v:Int)=(v*resources.displayMetrics.density).toInt()
}
