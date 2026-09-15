package com.mh.analysis

import android.content.Context
import android.os.Handler
import android.os.Looper
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.TimeUnit

object LiveSocketHub {
    interface Listener {
        fun onSocketState(state:String) {}
        fun onLiveCandle(symbol:String,timeframe:String,candle:Candle) {}
    }

    private val listeners=CopyOnWriteArraySet<Listener>()
    private val main=Handler(Looper.getMainLooper())
    private val client=OkHttpClient.Builder()
        .pingInterval(20,TimeUnit.SECONDS)
        .readTimeout(0,TimeUnit.MILLISECONDS)
        .build()
    private var socket:WebSocket?=null
    private var apiKey=""
    private var connected=false
    private var manualStop=false
    private var reconnects=0
    private var reconnectPosted=false
    private val periods=listOf("1m","5m","15m","30m","1h")
    private val symbols=listOf("XAUUSD","BTCUSDT")

    @Synchronized fun addListener(l:Listener){listeners.add(l)}
    @Synchronized fun removeListener(l:Listener){listeners.remove(l)}
    @Synchronized fun isConnected()=connected

    @Synchronized fun start(context:Context,key:String){
        val k=key.trim()
        if(k.isBlank()){notifyState("LIVE STREAM KEY REQUIRED");return}
        if(apiKey==k&&(connected||socket!=null))return
        apiKey=k;manualStop=false;reconnects=0
        socket?.cancel();socket=null;connected=false
        connect()
    }

    @Synchronized fun stop(){manualStop=true;connected=false;socket?.close(1000,"manual");socket=null;notifyState("LIVE STREAM OFF")}

    @Synchronized private fun connect(){
        if(manualStop||apiKey.isBlank()||socket!=null)return
        notifyState(if(reconnects==0)"LIVE STREAM CONNECTING" else "LIVE STREAM RECONNECTING")
        val req=Request.Builder().url("wss://ws-v4.fcsapi.com/ws?access_key=${apiKey}").build()
        socket=client.newWebSocket(req,object:WebSocketListener(){
            override fun onOpen(ws:WebSocket,response:Response){ }
            override fun onMessage(ws:WebSocket,text:String){handleMessage(ws,text)}
            override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){handleClosed("LIVE STREAM CONNECTION LOST")}
            override fun onClosed(ws:WebSocket,code:Int,reason:String){handleClosed("LIVE STREAM DISCONNECTED")}
        })
    }

    private fun handleMessage(ws:WebSocket,text:String){
        val j=runCatching{JSONObject(text)}.getOrNull()?:return
        when(j.optString("type")){
            "ping"->{ws.send(JSONObject().put("type","pong").put("timestamp",System.currentTimeMillis()).toString());return}
            "welcome"->{
                synchronized(this){connected=true;reconnects=0;socket=ws}
                subscribeAll(ws)
                notifyState("LIVE STREAM CONNECTED")
                return
            }
            "error"->{notifyState("LIVE STREAM ERROR • ${j.optString("message","check key/subscription")}");return}
            "price"->handlePrice(j)
        }
    }

    private fun subscribeAll(ws:WebSocket){
        for(s in symbols)for(tf in periods){
            val q=JSONObject().put("type","join_symbol").put("symbol",socketSymbol(s)).put("timeframe",socketPeriod(tf))
            ws.send(q.toString())
        }
    }

    private fun handlePrice(j:JSONObject){
        val internal=internalSymbol(j.optString("symbol"))?:return
        val tf=internalPeriod(j.optString("timeframe"))?:return
        val p=j.optJSONObject("prices")?:return
        when(p.optString("mode")){
            "initial","candle"->{
                if(!p.has("t")||!p.has("c"))return
                val c=Candle(p.optLong("t"),p.optDouble("o",p.optDouble("c")),p.optDouble("h",p.optDouble("c")),p.optDouble("l",p.optDouble("c")),p.optDouble("c"),p.optDouble("v",0.0))
                FcsClient.applyLiveCandle(internal,tf,c)
                listeners.forEach{runCatching{it.onLiveCandle(internal,tf,c)}}
            }
            "askbid"->{
                if(!p.has("c"))return
                val c=FcsClient.applyLivePrice(internal,tf,p.optLong("t"),p.optDouble("c"))?:return
                listeners.forEach{runCatching{it.onLiveCandle(internal,tf,c)}}
            }
        }
    }

    private fun handleClosed(state:String){
        synchronized(this){connected=false;socket=null}
        notifyState(state)
        if(manualStop)return
        scheduleReconnect()
    }

    @Synchronized private fun scheduleReconnect(){
        if(reconnectPosted||manualStop)return
        reconnectPosted=true;reconnects++
        val delay=(3000L*(reconnects.coerceAtMost(5))).coerceAtMost(15000L)
        main.postDelayed({synchronized(this){reconnectPosted=false};connect()},delay)
    }

    private fun notifyState(s:String){listeners.forEach{runCatching{it.onSocketState(s)}}}
    private fun socketSymbol(s:String)=when(s.uppercase()){ "XAUUSD"->"FX:XAUUSD";else->"BINANCE:BTCUSDT" }
    private fun internalSymbol(s:String):String?=when{s.endsWith("XAUUSD",true)->"XAUUSD";s.endsWith("BTCUSDT",true)->"BTCUSDT";else->null}
    private fun socketPeriod(tf:String)=when(tf.lowercase()){ "1m"->"1";"5m"->"5";"15m"->"15";"30m"->"30";"1h"->"60";else->tf }
    private fun internalPeriod(tf:String):String?=when(tf.lowercase()){ "1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->null }
}