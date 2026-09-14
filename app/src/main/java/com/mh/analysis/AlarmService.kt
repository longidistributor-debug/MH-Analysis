package com.mh.analysis

import android.app.*
import android.content.Intent
import android.media.RingtoneManager
import android.os.*
import java.util.Locale
import kotlin.concurrent.thread
import kotlin.math.abs

class AlarmService:Service(){
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    @Volatile private var running=true
    private var index=0

    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();createChannels();startForeground(311,serviceNotification("Tracking signals in background"));thread(name="mh-state-monitor"){monitorLoop()}}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};return START_STICKY}

    private fun monitorLoop(){
        while(running){
            try{
                val key=prefs.getString("api_key","")?.trim().orEmpty()
                if(key.isBlank()){updateService("FCS key missing");Thread.sleep(30_000);continue}
                val pending=SignalStore.pendingSignals(this)
                val open=SignalStore.openTrades(this)
                val armed=AlarmStore.armed(this)
                val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}+armed.map{it.symbol}).distinct()
                if(symbols.isEmpty()){updateService("No pending/open signals");Thread.sleep(30_000);continue}
                val symbol=symbols[index%symbols.size];index++
                val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
                val data=FcsClient.history(key,symbol,"1m",90,false).first
                val last=data.lastOrNull()
                if(last!=null){
                    val events=SignalStore.processMinuteCandle(this,symbol,last)
                    events.forEach{e->
                        val alarm=armedBefore[e.signal.id]
                        when(e.state){
                            "ACTIVE"-> if(alarm!=null){
                                val hit=alarm.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null)
                                AlarmStore.update(this,hit);fireThreeCycles(hit)
                            }
                            "EXPIRED"-> alarm?.let{notifyState(it.copy(status="EXPIRED",enabled=false),"SETUP EXPIRED / MISSED before entry. Alarm removed from active monitoring.")}
                            "WIN","LOSS"-> notifyTrade(e.signal,e.state)
                        }
                    }
                }
                updateService("Pending ${SignalStore.pendingSignals(this).size} • Open ${SignalStore.openTrades(this).size} • Armed ${AlarmStore.armed(this).size}")
            }catch(_:Exception){}
            try{Thread.sleep(35_000)}catch(_:InterruptedException){break}
        }
    }

    private fun fireThreeCycles(a:AlarmEntry){
        notifyState(a,"ENTRY REACHED at ${price(a.entry)} • ${a.symbol} ${a.timeframe}. Alert sequence started.")
        val uri=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)?:RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        for(i in 1..3){
            val ring=runCatching{RingtoneManager.getRingtone(this,uri)}.getOrNull();runCatching{ring?.play()}
            try{Thread.sleep(6_000)}catch(_:InterruptedException){};runCatching{ring?.stop()}
            if(i<3)try{Thread.sleep(10_000)}catch(_:InterruptedException){}
        }
        notifyState(a,"ALARM COMPLETED — entry was reached and all 3 alert cycles were played. Trade is now tracked in Records, not as a pending alarm.")
    }

    private fun notifyTrade(s:Signal,state:String){
        val text="$state • ${s.symbol} ${s.timeframe} • Entry ${price(s.entry)} • TP1 ${price(s.tp1)} • SL ${price(s.sl)}"
        val n=builder("mh_alarm_alert").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Trade $state").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build()
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+state).hashCode()),n)
    }
    private fun createChannels(){if(Build.VERSION.SDK_INT>=26){val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager;nm.createNotificationChannel(NotificationChannel("mh_alarm_service","MH Background Signal Tracking",NotificationManager.IMPORTANCE_LOW));nm.createNotificationChannel(NotificationChannel("mh_alarm_alert","MH Signal Alerts",NotificationManager.IMPORTANCE_HIGH).apply{enableVibration(true)})}}
    private fun builder(channel:String):Notification.Builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,channel)else Notification.Builder(this)
    private fun serviceNotification(text:String):Notification{val stop=Intent(this,AlarmService::class.java).apply{action="STOP"};val pi=PendingIntent.getService(this,91,stop,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE);return builder("mh_alarm_service").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Analysis background tracking").setContentText(text).setOngoing(true).addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pi).build()).build()}
    private fun updateService(text:String){(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(311,serviceNotification(text))}
    private fun notifyState(a:AlarmEntry,text:String){val n=builder("mh_alarm_alert").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("${a.symbol} ${a.timeframe} • ${a.status}").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs(a.id.hashCode()),n)}
    private fun price(v:Double)=if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    override fun onDestroy(){running=false;super.onDestroy()}
}
