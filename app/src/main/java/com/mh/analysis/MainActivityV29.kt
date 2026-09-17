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
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
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
    private var previousDay:FcsClient.PreviousDayRange?=null
    private var analyzeGeneration=0L
    private var analysisContext:String?=null

    override fun onCreate(b:Bundle?){
        super.onCreate(b);FcsClient.init(this)
        window.statusBarColor=Color.BLACK;window.navigationBarColor=Color.BLACK
        symbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD"
        period=prefs.getString("period","15m")?:"15m"
        removeLegacyAlarmAndRecordData()
        setContentView(buildUi())
    }

    override fun onResume(){
        super.onResume()
        LiveSocketHub.addListener(this)
        savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}
    }

    override fun onPause(){
        LiveSocketHub.removeListener(this)
        super.onPause()
    }

    override fun onSocketState(state:String){ /* intentionally not shown in the product UI */ }

    override fun onLiveCandle(liveSymbol:String,timeframe:String,candle:Candle){
        if(liveSymbol!=symbol||timeframe!=period)return
        runOnUiThread{
            val live=FcsClient.freshSnapshot(symbol,period,60,2200)?:return@runOnUiThread
            candles=live
            if(analysisContext==contextKey()){
                val ev=LiveSetupStore.evaluate(this,symbol,period,live)
                if(ev.changed){
                    showSetup(ev.setup,"LIVE CONDITION UPDATED",ev.reason)
                }
            }
        }
    }

    private fun buildUi():View{
        val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(18),dp(14),dp(18),dp(28));setBackgroundColor(Color.BLACK)}
        root.addView(txt("بِسْمِ ٱللَّٰهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ",21f,true).apply{gravity=Gravity.CENTER;textAlignment=View.TEXT_ALIGNMENT_CENTER;setPadding(0,dp(3),0,dp(14))},LinearLayout.LayoutParams(-1,-2))
        val header=LinearLayout(this).apply{orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL}
        header.addView(TextView(this).apply{text="MS";gravity=Gravity.CENTER;textSize=22f;setTextColor(Color.WHITE);setTypeface(typeface,Typeface.BOLD);background=round(Color.BLACK,18f,Color.WHITE)},LinearLayout.LayoutParams(dp(64),dp(64)))
        header.addView(LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(dp(14),0,0,0);addView(txt("MH ANALYSIS",26f,true));addView(txt("Live Market Structure Engine",11f,false,Color.LTGRAY));addView(txt("MS • v33 • FRESH TIMEFRAME ENGINE",10f,true));addView(txt("◉ WhatsApp  +92 343 4824609",11f,false,Color.LTGRAY))},LinearLayout.LayoutParams(0,-2,1f))
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

        root.addView(section("LIVE MARKET CHART"));val cc=card();chart=WebView(this).apply{
            settings.javaScriptEnabled=true;settings.domStorageEnabled=true;settings.mediaPlaybackRequiresUserGesture=false
            CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(this,true)
            setBackgroundColor(Color.rgb(19,23,34));webViewClient=object:WebViewClient(){override fun onPageFinished(v:WebView?,u:String?){chartReady=true;switchVisibleChart()}}
            val html=assets.open("tradingview_live.html").bufferedReader().use{it.readText()};loadDataWithBaseURL("https://s3.tradingview.com/",html,"text/html","UTF-8",null)
        };cc.addView(chart,LinearLayout.LayoutParams(-1,dp(560)));root.addView(cc)

        root.addView(section("SIGNAL CONTROL"));val sc=card();calls=txt("Analysis calls: ${usage()}/500",11f,true,Color.LTGRAY);sc.addView(calls)
        sc.addView(actionButton("NEW ANALYZE",true){analyzeNow()},LinearLayout.LayoutParams(-1,dp(54)).apply{topMargin=dp(10)})
        status=txt("$symbol • $period\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH SETUP",12f,false).apply{setPadding(dp(12),dp(12),dp(12),dp(12));background=round(Color.rgb(12,12,12),12f,Color.DKGRAY)};sc.addView(status,LinearLayout.LayoutParams(-1,-2).apply{topMargin=dp(10)});root.addView(sc)

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
        candles=emptyList()
        previousDay=null
        if(::status.isInitialized)status.text="$symbol • $period\nTIMEFRAME CHANGED • PRESS NEW ANALYZE FOR FRESH DATA"
        if(chartReady)chart.evaluateJavascript("clearSignalCard()",null)
    }

    private fun switchVisibleChart(){
        pairLabel.text="$symbol • $period"
        if(chartReady){
            chart.evaluateJavascript("clearSignalCard();loadTradingView(${JSONObject.quote(symbol)},${JSONObject.quote(period)})",null)
        }
        if(analysisContext!=contextKey()&&::status.isInitialized){
            status.text="$symbol • $period\nTRADINGVIEW LIVE • PRESS NEW ANALYZE FOR A FRESH $period SETUP"
        }
    }

    private fun analyzeNow(){
        val key=savedHistoryKey();if(key.isBlank()){status.text="SAVE ANALYSIS ACCESS KEY ONCE";return}
        if(busy){status.text="FRESH ANALYSIS IS ALREADY RUNNING FOR $symbol • $period";return}
        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"
        busy=true;status.text="NEW ANALYZE • refreshing current $reqSymbol $reqPeriod candle and structure…"
        thread{
            try{
                var credits=0
                val data=FcsClient.freshSnapshot(reqSymbol,reqPeriod,100,2200) ?: run{
                    val pair=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true);credits+=pair.second;pair.first
                }
                val pdPair=runCatching{FcsClient.previousDayRange(key,reqSymbol)}.getOrElse{null to 0}
                credits+=pdPair.second
                runOnUiThread{
                    if(token!=analyzeGeneration||reqSymbol!=symbol||reqPeriod!=period)return@runOnUiThread
                    busy=false
                    if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"
                    candles=data;previousDay=pdPair.first;analysisContext=reqContext
                    performFreshAnalysis()
                }
            }catch(e:Exception){
                runOnUiThread{
                    if(token!=analyzeGeneration)return@runOnUiThread
                    busy=false
                    status.text="FRESH ANALYSIS UNAVAILABLE\n${e.message}\nNo stale signal was generated. TradingView remains live."
                    showSignalCard(null)
                }
            }
        }
    }

    private fun performFreshAnalysis(){
        if(candles.size<100){status.text="NOT ENOUGH FRESH MARKET HISTORY FOR RELIABLE $period ANALYSIS";showSignalCard(null);return}

        val before=LiveSetupStore.evaluate(this,symbol,period,candles).setup
        val raw=AnalysisEngine.analyze(symbol,period,candles)
        val candidate=raw?.let{applyPreviousDayContext(it)}

        if(candidate==null){
            val after=LiveSetupStore.evaluate(this,symbol,period,candles).setup
            if(after!=null&&after.state in setOf("PENDING","TRIGGERED")){
                showSetup(after,"RE-EVALUATED • NO NEW REPLACEMENT",AnalysisEngine.noSignalReason(symbol,period,candles))
            }else{
                val terminal=after?.takeIf{it.state !in setOf("PENDING","TRIGGERED")}
                if(terminal!=null)showSetup(terminal,"SETUP ${terminal.state}","Press NEW ANALYZE for the next fresh setup.")
                else{
                    status.text="NO CURRENT SETUP\n${marketContext()}\n\n${AnalysisEngine.noSignalReason(symbol,period,candles)}"
                    showSignalCard(null)
                }
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
        showSetup(accepted,title,if(changed)"Generated from the current $symbol $period snapshot." else "Current candle and structure still support the same setup.")
    }

    private fun applyPreviousDayContext(s:Signal):Signal{
        val pd=previousDay?:return s
        val last=candles.lastOrNull()?:return s
        val reasons=s.reasons.toMutableList();var score=s.score
        val bullSweep=last.l<pd.low&&last.c>pd.low
        val bearSweep=last.h>pd.high&&last.c<pd.high
        when{
            bullSweep&&s.direction=="BUY"->{reasons.add(0,"Previous-day low liquidity sweep reclaimed (+4)");score+=4}
            bearSweep&&s.direction=="SELL"->{reasons.add(0,"Previous-day high liquidity sweep rejected (+4)");score+=4}
            bullSweep&&s.direction=="SELL"->{reasons.add(0,"Counter-signal: previous-day low was reclaimed (-4)");score-=4}
            bearSweep&&s.direction=="BUY"->{reasons.add(0,"Counter-signal: previous-day high was rejected (-4)");score-=4}
            last.c>pd.high&&s.direction=="BUY"->{reasons.add(0,"Price holding above previous-day high (+2)");score+=2}
            last.c<pd.low&&s.direction=="SELL"->{reasons.add(0,"Price holding below previous-day low (+2)");score+=2}
        }
        return s.copy(score=score.coerceIn(60,99),reasons=reasons.take(12))
    }

    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){
        if(a==null){status.text="$headline\n${marketContext()}";showSignalCard(null);return}
        val s=a.signal;val why=s.reasons.take(7).joinToString("\n")
        status.text="$headline • ${s.timeframe}\n${s.direction} • ${s.score}/100 • ${a.state}\nEntry ${price(s.entry)}   SL ${price(s.sl)}\nTP1 ${price(s.tp1)}   TP2 ${price(s.tp2)}\n\n${marketContext()}\n\nWHY THIS TRADE\n${s.setupReason}\n\nCONFIRMATIONS\n$why${if(note.isBlank())"" else "\n\n$note"}"
        showSignalCard(a)
    }

    private fun marketContext():String{
        val pd=previousDay
        return if(pd==null)"PREVIOUS DAY • HIGH/LOW unavailable for this refresh" else "PREVIOUS DAY • HIGH ${price(pd.high)}   LOW ${price(pd.low)}"
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
        Toast.makeText(this,"Analysis key saved",Toast.LENGTH_SHORT).show()
    }

    private fun removeLegacyAlarmAndRecordData(){
        if(prefs.getBoolean("v33_legacy_cleanup",false))return
        getSharedPreferences("mh_records",MODE_PRIVATE).edit().clear().apply()
        getSharedPreferences("mh_alarms",MODE_PRIVATE).edit().clear().apply()
        prefs.edit().putBoolean("v33_legacy_cleanup",true).apply()
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
