package com.mh.analysis

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
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import kotlin.concurrent.thread
import kotlin.math.abs

class MainActivityV29:Activity(),LiveSocketHub.Listener{
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
    private var analyzeGeneration=0L
    private var analysisContext:String?=null
    private var lastUnified:UnifiedAnalysisEngine.Result?=null

    override fun onCreate(b:Bundle?){
        super.onCreate(b);FcsClient.init(this)
        window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK
        symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD"
        period=prefs.getString("period","15m")?:"15m"
        setContentView(buildUi())
    }

    override fun onResume(){
        super.onResume()
        LiveSocketHub.addListener(this)
        savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}
        updateCallLabel()
    }

    override fun onPause(){
        LiveSocketHub.removeListener(this)
        super.onPause()
    }

    override fun onSocketState(state:String){ /* socket state stays out of the product UI */ }

    override fun onLiveCandle(liveSymbol:String,timeframe:String,candle:Candle){
        if(liveSymbol!=symbol||timeframe!=period)return
        runOnUiThread{
            val live=FcsClient.freshSnapshot(symbol,period,60,2200)?:return@runOnUiThread
            candles=live
            renderFcsChart(live)
            if(analysisContext==contextKey()){
                val ev=LiveSetupStore.evaluate(this,symbol,period,live)
                if(ev.changed)showSetup(ev.setup,"LIVE CONDITION UPDATED",ev.reason)
            }
        }
    }

    private fun buildUi():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(14),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        root.addView(txt("بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",21f,true).apply{gravity=Gravity.CENTER;textAlignment=View.TEXT_ALIGNMENT_CENTER;setPadding(0,dp(3),0,dp(14))},LinearLayout.LayoutParams(-1,-2))
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(ImageView(this).apply{setImageResource(R.drawable.mh_logo_pc);scaleType=ImageView.ScaleType.CENTER_INSIDE;setPadding(dp(3),dp(3),dp(3),dp(3))},LinearLayout.LayoutParams(dp(64),dp(64)))
        header.addView(LinearLayout(this).apply{
            orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0)
            addView(txt("MH ANALYSIS",26f,true))
            addView(txt("Live Market Structure Engine",11f,false,Color.LTGRAY))
            addView(txt("MH - V.02",10f,true))
        },LinearLayout.LayoutParams(0,-2,1f))
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
        sp.onItemSelectedListener=object:AdapterView.OnItemSelectedListener{
            override fun onItemSelected(p:AdapterView<*>?,v:View?,pos:Int,id:Long){
                val np=periods[pos];if(np==period)return
                period=np;prefs.edit().putString("period",period).apply();resetForMarketChange();switchVisibleChart()
            }
            override fun onNothingSelected(p:AdapterView<*>?){}
        }

        root.addView(section("FCS MARKET CHART"));val cc=card();chart=WebView(this).apply{
            settings.javaScriptEnabled=true;settings.domStorageEnabled=true
            setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;switchVisibleChart()}}
            val html=assets.open("fcs_chart.html").bufferedReader().use{it.readText()};loadDataWithBaseURL(null,html,"text/html","UTF-8",null)
        };cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)

        root.addView(section("SIGNAL CONTROL"));val sc=card();calls=txt("",11f,true,Color.LTGRAY);sc.addView(calls);updateCallLabel()
        sc.addView(actionButton("NEW ANALYZE / RE-EVALUATE",true){analyzeNow()},LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})
        status=txt("$symbol • $period\nFCS CHART • FRESH ANALYSIS USES EXACTLY 3 FCS REST CALLS",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)

        root.addView(section("FLOATING"));val fc=card();fc.addView(Button(this).apply{text="ENABLE MS LIVE FLOAT";setTextColor(Color.WHITE);background=round(Color.rgb(25,25,25),12f,Color.GRAY);setOnClickListener{enableFloat()}},LinearLayout.LayoutParams(-1,dp(52)));root.addView(fc)
        return ScrollView(this).apply{isFillViewport=true;setBackgroundColor(Color.BLACK);addView(root)}
    }

    private fun switchPair(s:String){
        if(symbol==s)return
        symbol=s;prefs.edit().putString("symbol",s).apply();resetForMarketChange();switchVisibleChart()
    }

    private fun resetForMarketChange(){
        analyzeGeneration++
        busy=false
        analysisContext=null
        lastUnified=null
        candles=emptyList()
        if(::status.isInitialized)status.text="$symbol • $period\nMARKET CHANGED • 0 FCS REST CALLS USED • PRESS NEW ANALYZE / RE-EVALUATE"
        if(chartReady)chart.evaluateJavascript("clearSignalCard()",null)
    }

    private fun switchVisibleChart(){
        pairLabel.text="$symbol • $period"
        val cached=FcsClient.peek(symbol,period,300).orEmpty()
        if(cached.isNotEmpty()){candles=cached;renderFcsChart(cached)}
        else if(chartReady)chart.evaluateJavascript("setEmptyMarket(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null)
        if(analysisContext!=contextKey()&&::status.isInitialized)status.text="$symbol • $period\nFCS CHART • PRESS NEW ANALYZE / RE-EVALUATE FOR FRESH 3-CALL ANALYSIS"
        updateCallLabel()
    }

    private fun updateCallLabel(){
        if(!::calls.isInitialized)return
        val left=FcsClient.manualCooldownSeconds()
        calls.text=if(left>0)"FCS calls: ${usage()}/500 • next 3-call pack in ${left}s" else "FCS calls: ${usage()}/500 • 3 calls per manual analysis • READY"
    }

    private fun analyzeNow(){
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}
        if(busy){status.text="MANUAL ANALYSIS IS ALREADY RUNNING FOR $symbol • $period";return}
        val wait=FcsClient.manualCooldownSeconds()
        if(wait>0){status.text="MANUAL 3-CALL PACK COOLDOWN\nNext fresh analysis available in ${wait}s.\nNo extra FCS REST call was sent.";updateCallLabel();return}
        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"
        busy=true;status.text="NEW ANALYZE / RE-EVALUATE\n1/3 selected timeframe • 2/3 true HTF • 3/3 execution snapshot…"
        thread{
            try{
                val pack=FcsClient.manualAnalysisPack(key,reqSymbol,reqPeriod)
                val result=UnifiedAnalysisEngine.analyze(this,reqSymbol,reqPeriod,pack.selected,pack.higherTimeframe,pack.higherTimeframePeriod,pack.quote)
                runOnUiThread{
                    if(token!=analyzeGeneration||reqSymbol!=symbol||reqPeriod!=period)return@runOnUiThread
                    busy=false
                    if(pack.credits>0)addUsage(pack.credits);updateCallLabel()
                    candles=pack.selected;analysisContext=reqContext;lastUnified=result
                    renderFcsChart(pack.selected)
                    performFreshAnalysis(result)
                }
            }catch(e:Exception){
                runOnUiThread{
                    if(token!=analyzeGeneration)return@runOnUiThread
                    busy=false;updateCallLabel()
                    val msg=e.message.orEmpty()
                    val providerRate=msg.contains("rate",true)||msg.contains("too many",true)||msg.contains("limit",true)
                    status.text=if(providerRate)
                        "FCS PROVIDER COOLDOWN\nProvider still has requests inside its rolling 60-second window. Wait for the countdown, then press NEW ANALYZE / RE-EVALUATE.\nNo stale signal was generated."
                    else "3-CALL ANALYSIS UNAVAILABLE\n$msg\nNo stale signal was generated. Cached/live FCS chart remains available."
                    showSignalCard(LiveSetupStore.load(this,symbol,period))
                }
            }
        }
    }

    private fun performFreshAnalysis(result:UnifiedAnalysisEngine.Result){
        if(candles.size<100){status.text="NOT ENOUGH FRESH MARKET HISTORY FOR RELIABLE $period ANALYSIS";showSignalCard(null);return}
        val before=LiveSetupStore.load(this,symbol,period)
        val candidate=result.signal

        if(candidate==null){
            val current=LiveSetupStore.evaluate(this,symbol,period,candles).setup
            val title=if(result.blocked)"EXECUTION BLOCKED" else "NO NEW SIGNAL"
            if(current!=null&&current.state in setOf("PENDING","TRIGGERED")){
                showSetup(current,"$title • EXISTING SETUP PRESERVED",result.decision)
            }else{
                status.text="$title\n${result.decision}\n\n${marketContext()}"
                showSignalCard(current)
            }
            return
        }

        val changed=before==null||before.state !in setOf("PENDING","TRIGGERED")||LiveSetupStore.materiallyChanged(before.signal,candidate)
        val accepted=LiveSetupStore.acceptFresh(this,candidate)
        val title=when{
            accepted.state=="TRIGGERED"->"TRIGGERED SETUP RE-EVALUATED"
            changed->"NEW FRESH SIGNAL"
            else->"RE-EVALUATED • SETUP UNCHANGED"
        }
        showSetup(accepted,title,result.decision)
    }

    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){
        if(a==null){status.text="$headline\n${marketContext()}";showSignalCard(null);return}
        val s=a.signal;val why=s.reasons.take(8).joinToString("\n")
        status.text="$headline • ${s.timeframe}\n${s.direction} • ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\n${marketContext()}\n\nWHY THIS TRADE\n${s.setupReason}\n\nCONFIRMATIONS\n$why${if(note.isBlank())"" else "\n\n$note"}"
        showSignalCard(a)
    }

    private fun marketContext():String{
        val u=lastUnified?:return "TRUE HTF / EXECUTION / CALIBRATION • waiting for manual analysis"
        return "${u.htfSummary}\n${u.executionSummary}\n${u.calibrationSummary}"
    }

    private fun renderFcsChart(data:List<Candle>){
        if(!chartReady)return
        val arr=JSONArray()
        data.takeLast(180).forEach{c->arr.put(JSONObject().put("t",if(c.t>9_999_999_999L)c.t/1000L else c.t).put("o",c.o).put("h",c.h).put("l",c.l).put("c",c.c))}
        chart.evaluateJavascript("setMarketData(${JSONObject.quote(symbol)},${JSONObject.quote(period)},${JSONObject.quote(arr.toString())})",null)
    }

    private fun showSignalCard(a:ActiveSignal?){
        if(!chartReady)return
        if(a==null){chart.evaluateJavascript("clearSignalCard()",null);return}
        val s=a.signal;val j=JSONObject().put("direction",s.direction).put("state",a.state).put("entry",s.entry).put("sl",s.sl).put("tp1",s.tp1).put("tp2",s.tp2).put("score",s.score)
        chart.evaluateJavascript("setSignalCard(${JSONObject.quote(j.toString())})",null)
    }

    private fun contextKey()="$symbol|$period"
    private fun savedHistoryKey()=prefs.getString("api_key","")?.trim().orEmpty()
    private fun updateKeyUi(){val h=savedHistoryKey().isNotBlank();historyInput.visibility=if(h&&!editHistory)View.GONE else View.VISIBLE;historyStatus.text=if(h&&!editHistory)"● ANALYSIS KEY SAVED" else "ANALYSIS DATA KEY";historyButton.text=if(h&&!editHistory)"UPDATE ANALYSIS KEY" else "SAVE ANALYSIS KEY"}
    private fun saveHistoryKey(){
        if(savedHistoryKey().isNotBlank()&&!editHistory){editHistory=true;updateKeyUi();return}
        val x=historyInput.text.toString().trim();if(x.isBlank())return
        prefs.edit().putString("api_key",x).apply();editHistory=false;historyInput.setText("");updateKeyUi();LiveSocketHub.start(this,x)
        Toast.makeText(this,"Analysis key saved • no REST analysis call used",Toast.LENGTH_SHORT).show()
    }

    private fun enableFloat(){
        if(!Settings.canDrawOverlays(this)){startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName")));return}
        val i=Intent(this,OverlayService::class.java);if(Build.VERSION.SDK_INT>=26)startForegroundService(i)else startService(i)
    }

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
