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

    override fun onCreate(){
        super.onCreate();createChannels();startForeground(311,serviceNotification("Watching armed MH signals"));thread(name="mh-alarm-monitor"){monitorLoop()}
    }

    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{
        if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};return START_STICKY
    }

    private fun monitorLoop(){
        while(running){
            try{
                val armed=AlarmStore.armed(this)
                if(armed.isEmpty()){updateService("No armed signals");Thread.sleep(15_000);continue}
                val symbols=armed.map{it.symbol}.distinct();val symbol=symbols[index%symbols.size];index++
                val key=prefs.getString("api_key","")?.trim().orEmpty()
                if(key.isBlank()){updateService("FCS key missing");Thread.sleep(20_000);continue}
                val data=FcsClient.history(key,symbol,"1m",80,false).first
                val last=data.lastOrNull()
                if(last!=null){
                    val candleMs=toMillis(last.t)
                    armed.filter{it.symbol==symbol}.forEach{a->
                        val armedAt=a.armedAt?:Long.MAX_VALUE
                        // Never allow the candle that already existed when the alarm was armed to trigger it.
                        if(candleMs>armedAt && last.l<=a.entry&&last.h>=a.entry){
                            val hit=a.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis())
                            AlarmStore.update(this,hit)
                            fireThreeCycles(hit)
                        }
                    }
                }
                updateService("Watching ${AlarmStore.armed(this).size} armed signal(s) • waiting for fresh entry touch")
            }catch(_:Exception){}
            try{Thread.sleep(30_000)}catch(_:InterruptedException){break}
        }
    }

    private fun fireThreeCycles(a:AlarmEntry){
        notifyState(a,"ENTRY REACHED — alarm sequence started at ${price(a.entry)} • ${a.symbol} ${a.timeframe}")
        val uri=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)?:RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        for(i in 1..3){
            val ring=runCatching{RingtoneManager.getRingtone(this,uri)}.getOrNull()
            runCatching{ring?.play()}
            try{Thread.sleep(6_000)}catch(_:InterruptedException){}
            runCatching{ring?.stop()}
            if(i<3)try{Thread.sleep(10_000)}catch(_:InterruptedException){}
        }
        notifyState(a,"ALARM COMPLETED — entry was reached and all 3 alert cycles were played. Signal remains recorded in Alarm history.")
    }

    private fun createChannels(){
        if(Build.VERSION.SDK_INT>=26){
            val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(NotificationChannel("mh_alarm_service","MH Signal Watch",NotificationManager.IMPORTANCE_LOW))
            nm.createNotificationChannel(NotificationChannel("mh_alarm_alert","MH Signal Alerts",NotificationManager.IMPORTANCE_HIGH).apply{enableVibration(true);description="Entry-hit and completed alarm notifications"})
        }
    }

    private fun builder(channel:String):Notification.Builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,channel)else Notification.Builder(this)
    private fun serviceNotification(text:String):Notification{
        val stop=Intent(this,AlarmService::class.java).apply{action="STOP"}
        val pi=PendingIntent.getService(this,91,stop,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return builder("mh_alarm_service").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Analysis Alarm").setContentText(text).setOngoing(true).addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pi).build()).build()
    }
    private fun updateService(text:String){(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(311,serviceNotification(text))}
    private fun notifyState(a:AlarmEntry,text:String){
        val n=builder("mh_alarm_alert").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("${a.symbol} ${a.timeframe} • ${a.status}").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build()
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs(a.id.hashCode()),n)
    }
    private fun toMillis(t:Long)=if(t in 1..9_999_999_999L)t*1000L else t
    private fun price(v:Double)=if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    override fun onDestroy(){running=false;super.onDestroy()}
}
