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
    private var symbolIndex=0
    private var tfIndex=0
    private var lastStructureCheck=0L

    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate(){super.onCreate();createChannels();startForeground(311,serviceNotification("Background market-state monitor active"));thread(name="mh-state-monitor"){monitorLoop()}}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};return START_STICKY}

    private fun monitorLoop(){
        while(running){
            try{
                val key=prefs.getString("api_key","")?.trim().orEmpty()
                if(key.isBlank()){updateService("Data key missing");sleep(20_000);continue}
                val pending=SignalStore.pendingSignals(this);val open=SignalStore.openTrades(this);val armed=AlarmStore.armed(this)
                val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}+armed.map{it.symbol}).distinct()
                if(symbols.isEmpty()){updateService("No pending/open signals • service ready");sleep(25_000);continue}

                val symbol=symbols[symbolIndex%symbols.size];symbolIndex++
                val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}

                // Do not let the background service steal a quota slot from the visible chart.
                // Use an already-fetched real 1m feed first; only request if absolutely no 1m data exists.
                val oneMin=FcsClient.peek(symbol,"1m",180) ?: runCatching{FcsClient.history(key,symbol,"1m",180,false).first}.getOrNull()
                val last=oneMin?.lastOrNull()
                if(last!=null){
                    if(AnalysisEngine.isHighVolatility(oneMin)){
                        val lastVol=prefs.getLong("vol_notice_$symbol",0L)
                        if(System.currentTimeMillis()-lastVol>10*60_000L){
                            prefs.edit().putLong("vol_notice_$symbol",System.currentTimeMillis()).apply()
                            val expired=SignalStore.expireAllPendingForVolatility(this,symbol,lastTime(last.t))
                            notifyVolatility(symbol,expired.size)
                        }
                    }else{
                        val events=SignalStore.processMinuteCandle(this,symbol,last)
                        events.forEach{e->
                            val alarm=armedBefore[e.signal.id]
                            when(e.state){
                                "ACTIVE"->if(alarm!=null){val hit=alarm.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null);AlarmStore.update(this,hit);fireThreeCycles(hit)}
                                "EXPIRED"->alarm?.let{notifyState(it.copy(status="EXPIRED",enabled=false),"SETUP NO LONGER VALID before entry. It was removed from active monitoring and recorded as expired.")}
                                "WIN","LOSS"->notifyTrade(e.signal,e.state)
                            }
                        }
                    }
                }

                // Validate pending setup structure from that signal's exact timeframe feed.
                // Cache-first means 1m/5m/15m/30m/1h remain independent without quota fights.
                val now=System.currentTimeMillis()
                if(now-lastStructureCheck>=45_000L){
                    val tfPending=SignalStore.pendingSignals(this)
                    if(tfPending.isNotEmpty()){
                        val a=tfPending[tfIndex%tfPending.size];tfIndex++
                        val candles=FcsClient.peek(a.signal.symbol,a.signal.timeframe,180)
                        if(candles!=null&&candles.size>=60){
                            val before=SignalStore.loadActive(this,a.signal.symbol,a.signal.timeframe)
                            if(before!=null){
                                val result=SignalStore.evaluate(this,a.signal.symbol,a.signal.timeframe,candles)
                                if(result?.state=="EXPIRED")notifySignalExpired(a.signal,SignalStore.lifecycleReason(this,a.signal.id).ifBlank{"Live structure invalidated the pending setup."})
                            }
                        }
                    }
                    lastStructureCheck=now
                }
                updateService("Pending ${SignalStore.pendingSignals(this).size} • Open ${SignalStore.openTrades(this).size} • Armed ${AlarmStore.armed(this).size}")
            }catch(_:Exception){updateService("Background tracking active • market sync waiting")}
            sleep(8_000)
        }
    }

    private fun fireThreeCycles(a:AlarmEntry){
        notifyState(a,"ENTRY REACHED at ${price(a.entry)} • ${a.symbol} ${a.timeframe}. Trade is now ACTIVE.")
        val uri=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)?:RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        for(i in 1..3){val ring=runCatching{RingtoneManager.getRingtone(this,uri)}.getOrNull();runCatching{ring?.play()};sleep(6_000);runCatching{ring?.stop()};if(i<3)sleep(10_000)}
        notifyState(a,"ALARM COMPLETED — entry was reached. This signal is no longer pending; it remains tracked in Records until TP1 or SL.")
    }

    private fun notifyVolatility(symbol:String,expired:Int){
        val text=if(expired>0)"Abnormal volatility detected on $symbol. $expired pending setup(s) were invalidated and moved to Records." else "Abnormal volatility detected on $symbol. New setups are blocked until structure stabilizes."
        val n=builder("mh_alarm_alert_v12").setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle("MH Volatility Alert • $symbol").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build()
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((symbol+"vol").hashCode()),n)
    }
    private fun notifySignalExpired(s:Signal,reason:String){val text="${s.symbol} ${s.timeframe} • ${s.direction} pending setup expired. $reason";val n=builder("mh_alarm_alert_v12").setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle("MH Setup Expired").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+"expired").hashCode()),n)}
    private fun notifyTrade(s:Signal,state:String){val text="$state • ${s.symbol} ${s.timeframe} • Entry ${price(s.entry)} • TP1 ${price(s.tp1)} • SL ${price(s.sl)}";val n=builder("mh_alarm_alert_v12").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Trade $state").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+state).hashCode()),n)}
    private fun createChannels(){if(Build.VERSION.SDK_INT>=26){val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager;nm.createNotificationChannel(NotificationChannel("mh_alarm_service_v12","MH Background Market Tracking",NotificationManager.IMPORTANCE_LOW));nm.createNotificationChannel(NotificationChannel("mh_alarm_alert_v12","MH Market and Signal Alerts",NotificationManager.IMPORTANCE_HIGH).apply{enableVibration(true)})}}
    private fun builder(channel:String):Notification.Builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,channel)else Notification.Builder(this)
    private fun serviceNotification(text:String):Notification{val stop=Intent(this,AlarmService::class.java).apply{action="STOP"};val pi=PendingIntent.getService(this,91,stop,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE);return builder("mh_alarm_service_v12").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Analysis • live background tracking").setContentText(text).setOngoing(true).addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pi).build()).build()}
    private fun updateService(text:String){(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(311,serviceNotification(text))}
    private fun notifyState(a:AlarmEntry,text:String){val n=builder("mh_alarm_alert_v12").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("${a.symbol} ${a.timeframe} • ${a.status}").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs(a.id.hashCode()),n)}
    private fun lastTime(t:Long)=if(t in 1..9_999_999_999L)t*1000L else t
    private fun sleep(ms:Long){try{Thread.sleep(ms)}catch(_:InterruptedException){}}
    private fun price(v:Double)=if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    override fun onDestroy(){running=false;super.onDestroy()}
}
