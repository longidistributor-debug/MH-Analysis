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

    private const val SOCKET_URL="wss://ws-v4.fcsapi.com/ws"
    private val listeners=CopyOnWriteArraySet<Listener>()
    private val main=Handler(Looper.getMainLooper())
    private val client=OkHttpClient.Builder()
        .pingInterval(30,TimeUnit.SECONDS)
        .readTimeout(0,TimeUnit.MILLISECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private var socket:WebSocket?=null
    private var apiKey=""
    private var connected=false
    private var manualStop=false
    private var reconnects=0
    private var reconnectPosted=false
    private var joinedRooms=0
    private var heartbeatRunning=false
    private var lastState="LIVE STREAM OFF"

    private val periods=listOf("1m","5m","15m","30m","1h")
    private val symbols=listOf("XAUUSD","BTCUSDT")

    private val heartbeat=object:Runnable{
        override fun run(){
            val ws= synchronized(this@LiveSocketHub){ if(connected) socket else null }
            if(ws!=null){
                ws.send(JSONObject().put("type","ping").put("timestamp",System.currentTimeMillis()).toString())
                main.postDelayed(this,25_000L)
            }else heartbeatRunning=false
        }
    }

    @Synchronized fun addListener(l:Listener){listeners.add(l);runCatching{l.onSocketState(lastState)}}
    @Synchronized fun removeListener(l:Listener){listeners.remove(l)}
    @Synchronized fun isConnected()=connected

    @Synchronized fun start(context:Context,key:String){
        val k=key.trim()
        if(k.isBlank()){notifyState("LIVE STREAM KEY REQUIRED");return}
        if(apiKey==k&&(connected||socket!=null))return
        apiKey=k
        manualStop=false
        reconnects=0
        reconnectPosted=false
        joinedRooms=0
        stopHeartbeat()
        socket?.cancel()
        socket=null
        connected=false
        connect()
    }

    @Synchronized fun stop(){
        manualStop=true
        connected=false
        joinedRooms=0
        stopHeartbeat()
        socket?.close(1000,"manual")
        socket=null
        notifyState("LIVE STREAM OFF")
    }

    @Synchronized private fun connect(){
        if(manualStop||apiKey.isBlank()||socket!=null)return
        notifyState(if(reconnects==0)"LIVE STREAM CONNECTING" else "LIVE STREAM RECONNECTING • attempt $reconnects")
        val req=Request.Builder().url("$SOCKET_URL?access_key=${apiKey}").build()
        socket=client.newWebSocket(req,object:WebSocketListener(){
            override fun onOpen(ws:WebSocket,response:Response){notifyState("LIVE SOCKET OPEN • AUTHENTICATING")}
            override fun onMessage(ws:WebSocket,text:String){handleMessage(ws,text)}
            override fun onClosing(ws:WebSocket,code:Int,reason:String){
                notifyState("LIVE STREAM CLOSING • $code${if(reason.isNotBlank())" • $reason" else ""}")
            }
            override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){
                val http=response?.code?.let{"HTTP $it"}.orEmpty()
                val why=t.message?.take(90).orEmpty()
                handleClosed("LIVE STREAM CONNECTION LOST${if(http.isNotBlank())" • $http" else ""}${if(why.isNotBlank())" • $why" else ""}")
            }
            override fun onClosed(ws:WebSocket,code:Int,reason:String){
                handleClosed("LIVE STREAM DISCONNECTED • $code${if(reason.isNotBlank())" • $reason" else ""}")
            }
        })
    }

    private fun handleMessage(ws:WebSocket,text:String){
        val j=runCatching{JSONObject(text)}.getOrNull()?:return
        when(j.optString("type").lowercase()){
            "ping"->{
                ws.send(JSONObject().put("type","pong").put("timestamp",System.currentTimeMillis()).toString())
                return
            }
            "welcome"->{
                synchronized(this){connected=true;reconnects=0;joinedRooms=0;socket=ws}
                subscribeAll(ws)
                startHeartbeat()
                notifyState("LIVE STREAM CONNECTED • subscribing feeds")
                return
            }
            "message"->{
                if(j.optString("short").equals("joined_room",true)){
                    synchronized(this){joinedRooms++}
                    notifyState("LIVE STREAM CONNECTED • $joinedRooms FEEDS")
                }else{
                    val m=j.optString("message","")
                    if(m.isNotBlank())notifyState("LIVE STREAM • ${m.take(100)}")
                }
                return
            }
            "error"->{
                val m=j.optString("message",j.optString("msg","check WebSocket subscription/key"))
                notifyState("LIVE STREAM ERROR • ${m.take(120)}")
                return
            }
            "price"->handlePrice(j)
        }
    }

    private fun subscribeAll(ws:WebSocket){
        // FCS examples use numeric minute values for socket rooms. Use the same canonical
        // values even though text aliases are also documented.
        for(s in symbols)for(tf in periods){
            ws.send(JSONObject()
                .put("type","join_symbol")
                .put("symbol",socketSymbol(s))
                .put("timeframe",socketPeriod(tf))
                .toString())
        }
    }

    private fun handlePrice(j:JSONObject){
        val internal=internalSymbol(j.optString("symbol"))?:return
        val tf=internalPeriod(j.optString("timeframe"))?:return
        val p=j.optJSONObject("prices")?:return
        val mode=p.optString("mode").lowercase()
        if(mode=="profile")return

        if(mode=="initial"||mode=="candle"||(p.has("c")&&p.has("o")&&p.has("h")&&p.has("l"))){
            if(!p.has("c"))return
            val close=p.optDouble("c")
            val c=Candle(
                p.optLong("t",0L),
                p.optDouble("o",close),
                p.optDouble("h",close),
                p.optDouble("l",close),
                close,
                p.optDouble("v",0.0)
            )
            val applied=FcsClient.applyLiveCandle(internal,tf,c)
            listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}}
            return
        }

        if(mode=="askbid"||p.has("c")){
            val price=p.optDouble("c",Double.NaN)
            if(price.isNaN())return
            val applied=FcsClient.applyLivePrice(internal,tf,p.optLong("t",0L),price)?:return
            listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}}
        }
    }

    private fun startHeartbeat(){
        synchronized(this){
            if(heartbeatRunning)return
            heartbeatRunning=true
        }
        main.removeCallbacks(heartbeat)
        main.postDelayed(heartbeat,25_000L)
    }

    private fun stopHeartbeat(){
        heartbeatRunning=false
        main.removeCallbacks(heartbeat)
    }

    private fun handleClosed(state:String){
        synchronized(this){connected=false;socket=null;joinedRooms=0}
        stopHeartbeat()
        notifyState(state)
        if(manualStop)return
        scheduleReconnect()
    }

    @Synchronized private fun scheduleReconnect(){
        if(reconnectPosted||manualStop)return
        reconnectPosted=true
        reconnects++
        val delay=(3000L*reconnects.coerceAtMost(5)).coerceAtMost(15_000L)
        main.postDelayed({synchronized(this){reconnectPosted=false};connect()},delay)
    }

    private fun notifyState(s:String){
        lastState=s
        listeners.forEach{runCatching{it.onSocketState(s)}}
    }

    private fun socketSymbol(s:String)=when(s.uppercase()){
        "XAUUSD"->"FX:XAUUSD"
        else->"BINANCE:BTCUSDT"
    }
    private fun socketPeriod(tf:String)=when(tf.lowercase()){
        "1m"->"1";"5m"->"5";"15m"->"15";"30m"->"30";"1h"->"60";else->tf
    }
    private fun internalSymbol(s:String):String?=when{
        s.endsWith("XAUUSD",true)->"XAUUSD"
        s.endsWith("BTCUSDT",true)->"BTCUSDT"
        else->null
    }
    private fun internalPeriod(tf:String):String?=when(tf.trim().lowercase()){
        "1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->null
    }
}
