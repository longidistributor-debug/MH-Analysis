package com.mh.analysis

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class BootReceiver:BroadcastReceiver(){
    override fun onReceive(context:Context,intent:Intent?){
        val action=intent?.action?:return
        if(action!=Intent.ACTION_BOOT_COMPLETED&&action!=Intent.ACTION_MY_PACKAGE_REPLACED)return
        val key=context.getSharedPreferences("mh",Context.MODE_PRIVATE).getString("api_key","")?.trim().orEmpty()
        if(key.isBlank())return
        if(SignalStore.pendingSignals(context).isEmpty()&&SignalStore.openTrades(context).isEmpty()&&AlarmStore.armed(context).isEmpty())return
        val service=Intent(context,AlarmService::class.java)
        if(Build.VERSION.SDK_INT>=26)context.startForegroundService(service)else context.startService(service)
    }
}
