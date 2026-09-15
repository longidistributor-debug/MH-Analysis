package com.mh.analysis

import android.app.*
import android.content.Intent
import android.media.RingtoneManager
import android.os.*
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import kotlin.concurrent.thread
import kotlin.math.abs

class AlarmService:Service(),LiveSocketHub.Listener{
    private val prefs by lazy{getSharedPreferences("mh",MODE_PRIVATE)}
    @Volatile private var running=true
    private val lastEval=ConcurrentHashMap<String,Long>()
    private val h=Handler(Looper.getMainLooper())
    private val statusTick=object:Runnable{override fun run(){if(running){updateService("${if(LiveSocketHub.isConnected())"LIVE SOCKET" else "RECONNECTING"} • Pending ${SignalStore.pendingSignals(this@AlarmService).size} • Open ${SignalStore.openTrades(this@AlarmService).size} • Armed ${AlarmStore.armed(this@AlarmService).size}");h.postDelayed(this,10_000)}}}

    override fun onBind(intent:Intent?):IBinder?=null
    override fun onCreate(){
        super.onCreate();FcsClient.init(this);createChannels();startForeground(311,serviceNotification("Starting persistent WebSocket market engine"));LiveSocketHub.addListener(this)
        val socketKey=prefs.getString("socket_api_key","")?.trim().orEmpty();if(socketKey.isNotBlank())LiveSocketHub.start(this,socketKey) else updateService("Live stream key required")
        thread(name="mh-history-bootstrap"){bootstrapNeededHistory()};h.post(statusTick)
    }
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int{if(intent?.action=="STOP"){stopSelf();return START_NOT_STICKY};val k=prefs.getString("socket_api_key","")?.trim().orEmpty();if(k.isNotBlank())LiveSocketHub.start(this,k);return START_STICKY}

    private fun bootstrapNeededHistory(){
        val rest=prefs.getString("api_key","")?.trim().orEmpty();if(rest.isBlank())return
        val selectedSymbol=prefs.getString("symbol","XAUUSD")?:"XAUUSD";val selectedTf=prefs.getString("period","15m")?:"15m"
        val needs=mutableListOf(selectedSymbol to selectedTf)
        SignalStore.pendingSignals(this).forEach{needs+=it.signal.symbol to it.signal.timeframe}
        SignalStore.openTrades(this).forEach{needs+=it.signal.symbol to it.signal.timeframe}
        for((s,tf) in needs.distinct()){
            if(!running)return
            if(!FcsClient.hasUsableHistory(s,tf,60))runCatching{FcsClient.seedForPeriod(rest,s,tf,false)}
        }
    }

    override fun onSocketState(state:String){updateService(state)}

    override fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){
        if(!running)return
        try{
            if(timeframe=="1m")processLifecycleTick(symbol,candle)
            val key="$symbol|$timeframe";val now=System.currentTimeMillis();val prior=lastEval[key]?:0L
            if(now-prior>=5_000L){lastEval[key]=now;validatePendingOnTimeframe(symbol,timeframe)}
        }catch(_:Exception){}
    }

    private fun processLifecycleTick(symbol:String,last:Candle){
        val oneMin=FcsClient.peek(symbol,"1m",220).orEmpty()
        if(oneMin.size>=20&&AnalysisEngine.isHighVolatility(oneMin)){
            val lastVol=prefs.getLong("vol_notice_$symbol",0L)
            if(System.currentTimeMillis()-lastVol>10*60_000L){prefs.edit().putLong("vol_notice_$symbol",System.currentTimeMillis()).apply();val expired=SignalStore.expireAllPendingForVolatility(this,symbol,lastTime(last.t));notifyVolatility(symbol,expired.size)}
            return
        }
        val armedBefore=AlarmStore.armed(this).filter{it.symbol==symbol}.associateBy{it.signalId}
        val events=SignalStore.processMinuteCandle(this,symbol,last)
        events.forEach{e->
            val alarm=armedBefore[e.signal.id]
            when(e.state){
                "ACTIVE"->if(alarm!=null){val hit=alarm.copy(enabled=false,status="TRIGGERED",triggeredAt=System.currentTimeMillis(),armedAt=null);AlarmStore.update(this,hit);thread(name="mh-entry-alarm"){fireThreeCycles(hit)}}
                "EXPIRED"->alarm?.let{notifyState(it.copy(status="EXPIRED",enabled=false),"SETUP NO LONGER VALID before entry. It was removed from active monitoring and recorded as expired.")}
                "WIN","LOSS"->notifyTrade(e.signal,e.state)
            }
        }
    }

    private fun validatePendingOnTimeframe(symbol:String,timeframe:String){
        val pending=SignalStore.pendingSignals(this).filter{it.signal.symbol==symbol&&it.signal.timeframe==timeframe};if(pending.isEmpty())return
        val candles=FcsClient.peek(symbol,timeframe,220)?:return;if(candles.size<60)return
        val before=pending.associateBy{it.signal.id};SignalStore.evaluate(this,symbol,timeframe,candles)
        before.values.forEach{a->val after=SignalStore.loadActive(this,a.signal.symbol,a.signal.timeframe);if(after==null||after.signal.id!=a.signal.id){val reason=SignalStore.lifecycleReason(this,a.signal.id);if(reason.isNotBlank())notifySignalExpired(a.signal,reason)}}
    }

    private fun fireThreeCycles(a:AlarmEntry){
        notifyState(a,"ENTRY REACHED at ${price(a.entry)} • ${a.symbol} ${a.timeframe}. Trade is now ACTIVE.")
        val uri=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)?:RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        for(i in 1..3){val ring=runCatching{RingtoneManager.getRingtone(this,uri)}.getOrNull();runCatching{ring?.play()};sleep(6_000);runCatching{ring?.stop()};if(i<3)sleep(10_000)}
        notifyState(a,"ALARM COMPLETED — entry was reached. This signal is no longer pending; it remains tracked in Records until TP1 or SL.")
    }

    private fun notifyVolatility(symbol:String,expired:Int){val text=if(expired>0)"Abnormal volatility detected on $symbol. $expired pending setup(s) were invalidated and moved to Records." else "Abnormal volatility detected on $symbol. New setups are blocked until structure stabilizes.";val n=builder("mh_alarm_alert_v22").setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle("MH Volatility Alert • $symbol").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((symbol+"vol").hashCode()),n)}
    private fun notifySignalExpired(s:Signal,reason:String){val text="${s.symbol} ${s.timeframe} • ${s.direction} pending setup expired. $reason";val n=builder("mh_alarm_alert_v22").setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle("MH Setup Expired").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+"expired").hashCode()),n)}
    private fun notifyTrade(s:Signal,state:String){val text="$state • ${s.symbol} ${s.timeframe} • Entry ${price(s.entry)} • TP1 ${price(s.tp1)} • SL ${price(s.sl)}";val n=builder("mh_alarm_alert_v22").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Trade $state").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs((s.id+state).hashCode()),n)}
    private fun createChannels(){if(Build.VERSION.SDK_INT>=26){val nm=getSystemService(NOTIFICATION_SERVICE) as NotificationManager;nm.createNotificationChannel(NotificationChannel("mh_alarm_service_v22","MH Persistent Live Market Tracking",NotificationManager.IMPORTANCE_LOW));nm.createNotificationChannel(NotificationChannel("mh_alarm_alert_v22","MH Market and Signal Alerts",NotificationManager.IMPORTANCE_HIGH).apply{enableVibration(true)})}}
    private fun builder(channel:String):Notification.Builder=if(Build.VERSION.SDK_INT>=26)Notification.Builder(this,channel)else Notification.Builder(this)
    private fun serviceNotification(text:String):Notification{val stop=Intent(this,AlarmService::class.java).apply{action="STOP"};val pi=PendingIntent.getService(this,91,stop,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE);return builder("mh_alarm_service_v22").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("MH Analysis • persistent live engine").setContentText(text).setOngoing(true).addAction(Notification.Action.Builder(android.R.drawable.ic_menu_close_clear_cancel,"Stop",pi).build()).build()}
    private fun updateService(text:String){(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(311,serviceNotification(text))}
    private fun notifyState(a:AlarmEntry,text:String){val n=builder("mh_alarm_alert_v22").setSmallIcon(android.R.drawable.ic_lock_idle_alarm).setContentTitle("${a.symbol} ${a.timeframe} • ${a.status}").setContentText(text).setStyle(Notification.BigTextStyle().bigText(text)).setAutoCancel(false).build();(getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(abs(a.id.hashCode()),n)}
    private fun lastTime(t:Long)=if(t in 1..9_999_999_999L)t*1000L else t
    private fun sleep(ms:Long){try{Thread.sleep(ms)}catch(_:InterruptedException){}}
    private fun price(v:Double)=if(abs(v)>=100)String.format(Locale.US,"%.2f",v)else String.format(Locale.US,"%.5f",v)
    override fun onDestroy(){running=false;h.removeCallbacks(statusTick);LiveSocketHub.removeListener(this);super.onDestroy()}
}
