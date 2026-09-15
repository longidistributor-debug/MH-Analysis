package com.mh.analysis

import android.app.*
import android.content.Intent
import android.media.RingtoneManager
import android.os.*
import java.text.SimpleDateFormat
import java.util.*
import kotlin.concurrent.thread
import kotlin.math.abs

class AlarmService:Service(){
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    private val h=Handler(Looper.getMainLooper())
    private var running=true
    private var cursor=0
    private data class Task(val kind:String,val symbol:String,val timeframe:String="1m")

    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();FcsClient.init(this);createChannels();startForeground(311,serviceNotification("Starting background signal tracking"));h.post(tick)}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};if(running)h.removeCallbacks(tick);h.post(tick);return START_STICKY}

    private val tick:Runnable=object:Runnable{
        override fun run(){
            if(!running)return
            val key=prefs.getString("api_key","")?.trim().orEmpty()
            val pending=SignalStore.pendingSignals(this@AlarmService)
            val open=SignalStore.openTrades(this@AlarmService)
            if(key.isBlank()){updateService("Analysis key missing • background tracking paused");h.postDelayed(this,60_000L);return}
            if(pending.isEmpty()&&open.isEmpty()){updateService("No pending/open trades • background monitor idle");stopSelf();return}
            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()
            val tasks=mutableListOf<Task>()
            symbols.forEach{tasks+=Task("LIFE",it,"1m")}
            pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.forEach{if(it.timeframe!="1m")tasks+=Task("STRUCT",it.symbol,it.timeframe)}
            if(tasks.isEmpty()){h.postDelayed(this,60_000L);return}
            val task=tasks[cursor%tasks.size];cursor=(cursor+1)%100000
            updateService("Tracking ${pending.size} pending • ${open.size} open • ${task.symbol} ${task.timeframe}")
            thread(name="mh-rest-monitor"){
                runCatching{if(task.kind=="LIFE")pollLifecycle(key,task.symbol) else pollStructure(key,task.symbol,task.timeframe)}
                scheduleNext(21_500L)
            }
        }
    }

    private fun scheduleNext(ms:Long){h.postDelayed({if(running)tick.run()},ms)}

    private fun pollLifecycle(key:String,symbol:String){
        val(out,credits)=FcsClient.history(key,symbol,"1m",220,true);addUsage(credits)
        if(out.isEmpty())return
        if(AnalysisEngine.isHighVolatility(out)){
            val last=prefs.getLong("vol_notice_$symbol",0L)
            if(System.currentTimeMillis()-last>10*60_000L){prefs.edit().putLong("vol_notice_$symbol",System.currentTimeMillis()).apply();val expired=SignalStore.expireAllPendingForVolatility(this,symbol,toMillis(out.last().t));notifyVolatility(symbol,expired.size)}
            return
        }
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        val events=SignalStore.processMinuteCandle(this,symbol,out.last())
        events.forEach{e->
            when(e.state){
                "ACTIVE"->{val alarm=armedBefore[e.signal.id];if(alarm!=null){val hit=alarm.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null);AlarmStore.update(this,hit);thread(name="mh-entry-alarm"){fireThreeCycles(hit)}}}
                "EXPIRED"->notifySignalExpired(e.signal,SignalStore.lifecycleReason(this,e.signal.id).ifBlank{"Pending setup expired before entry."})
                "WIN","LOSS"->notifyTrade(e.signal,e.state)
            }
        }
    }

    private fun pollStructure(key:String,symbol:String,timeframe:String){
        val(out,credits)=FcsClient.history(key,symbol,timeframe,220,true);addUsage(credits)
        if(out.size<60)return
        val before=SignalStore.loadActive(this,symbol,timeframe)?:return
        SignalStore.evaluate(this,symbol,timeframe,out)
        val after=SignalStore.loadActive(this,symbol,timeframe)
        if(after==null||after.signal.id!=before.signal.id){val reason=SignalStore.lifecycleReason(this,before.signal.id);if(reason.isNotBlank())notifySignalExpired(before.signal,reason)}
    }

    private fun fireThreeCycles(a:AlarmEntry){
        notifyState(a,"ENTRY REACHED at ${price(a.entry)} • trade is ACTIVE.")
        val uri=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)?:RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        for(i in 1..3){val ring=runCatching{RingtoneManager.getRingtone(this,uri)}.getOrNull();runCatching{ring?.play()};sleep(6_000);runCatching{ring?.stop()};if(i<3)sleep(10_000)}
        notifyState(a,"ALARM COMPLETED — entry was reached. Trade remains tracked until TP1 or SL.")
    }

    private fun notifyVolatility(symbol:String,expired:Int){val text=if(expired>0)"Abnormal volatility detected on $symbol. $expired pending setup(s) expired." else "Abnormal volatility detected on $symbol. New setup validation is paused until structure stabilizes.";val n=builder("mh_alert_v29").setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle("MH Volatility Alert • $symbol").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((symbol+"vol").hashCode()),n)}
    private fun notifySignalExpired(s:Signal,reason:String){val text="${s.symbol} ${s.timeframe} • ${s.direction} pending setup expired. $reason";val n=builder("mh_alert_v29").setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle("MH Setup Expired").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+"expired").hashCode()),n)}
    private fun notifyTrade(s:Signal,state:String){val text="$state • ${s.symbol} ${s.timeframe} • Entry ${price(s.entry)} • TP1 ${price(s.tp1)} • SL ${price(s.sl)}";val n=builder("mh_alert_v29").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Trade $state").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+state).hashCode()),n)}

    private fun createChannels(){if(Build.VERSION.SDK_INT>=26){val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager;nm.createNotificationChannel(NotificationChannel("mh_monitor_v29","MH Background Trade Tracking",NotificationManager.IMPORTANCE_LOW));nm.createNotificationChannel(NotificationChannel("mh_alert_v29","MH Signal Alerts",NotificationManager.IMPORTANCE_HIGH).apply{enableVibration(true)})}}
    private fun builder(channel:String):Notification.Builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,channel)else Notification.Builder(this)
    private fun serviceNotification(text:String):Notification{val stop=Intent(this,AlarmService::class.java).apply{action="STOP"};val pi=PendingIntent.getService(this,91,stop,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE);return builder("mh_monitor_v29").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Analysis • signal monitor").setContentText(text).setOngoing(true).addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pi).build()).build()}
    private fun updateService(text:String){(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(311,serviceNotification(text))}
    private fun notifyState(a:AlarmEntry,text:String){val n=builder("mh_alert_v29").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("${a.symbol} ${a.timeframe} • ${a.status}").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs(a.id.hashCode()),n)}

    private fun addUsage(n:Int){if(n<=0)return;val m=SimpleDateFormat("yyyy-MM",Locale.US).format(Date());if(prefs.getString("usage_month","")!=m)prefs.edit().putString("usage_month",m).putInt("usage",0).apply();prefs.edit().putInt("usage",prefs.getInt("usage",0)+n).apply()}
    private fun toMillis(t:Long)=if(t in 1..9_999_999_999L)t*1000L else t
    private fun sleep(ms:Long){try{Thread.sleep(ms)}catch(_:InterruptedException){}}
    private fun price(v:Double)=if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    override fun onDestroy(){running=false;h.removeCallbacks(tick);super.onDestroy()}
}
