package com.mh.analysis

import android.content.Context
import android.os.Handler
import android.os.Looper
import okhttp3.*
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.TimeUnit

object LiveSocketHub {
    interface Listener { fun onSocketState(state:String){}; fun onLiveCandle(symbol:String,timeframe:String,candle:Candle){} }

    private val listeners=CopyOnWriteArraySet<Listener>()
    private val main=Handler(Looper.getMainLooper())
    private val client=OkHttpClient.Builder()
        .pingInterval(25,TimeUnit.SECONDS)
        .readTimeout(0,TimeUnit.MILLISECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private const val endpoint="wss://ws-v4.fcsapi.com/ws"
    private val periods=listOf("1","5","15","30","60")
    private val symbols=listOf("FX:XAUUSD","BINANCE:BTCUSDT")

    private var socket:WebSocket?=null
    private var apiKey=""
    private var connected=false
    private var manualStop=false
    private var reconnectAttempt=0
    private var reconnectPosted=false
    private var joinedRooms=0
    private var generation=0L
    private var lastState="LIVE STREAM OFF"

    private val heartbeat=object:Runnable{
        override fun run(){
            val ws=synchronized(this@LiveSocketHub){if(connected)socket else null}
            if(ws!=null){
                ws.send(JSONObject().put("type","ping").put("timestamp",System.currentTimeMillis()).toString())
                main.postDelayed(this,25_000L)
            }
        }
    }

    @Synchronized fun addListener(l:Listener){listeners.add(l);runCatching{l.onSocketState(lastState)}}
    @Synchronized fun removeListener(l:Listener){listeners.remove(l)}
    @Synchronized fun isConnected()=connected
    @Synchronized fun currentState()=lastState

    @Synchronized fun start(context:Context,key:String){
        FcsClient.init(context)
        val k=key.trim()
        if(k.isBlank()){notifyState("LIVE WEBSOCKET KEY REQUIRED");return}
        if(apiKey==k&&(connected||socket!=null))return
        apiKey=k
        manualStop=false
        reconnectAttempt=0
        reconnectPosted=false
        joinedRooms=0
        generation++
        stopHeartbeat()
        socket?.cancel()
        socket=null
        connected=false
        connect(generation)
    }

    @Synchronized fun stop(){
        manualStop=true
        generation++
        connected=false
        joinedRooms=0
        reconnectPosted=false
        stopHeartbeat()
        socket?.close(1000,"manual")
        socket=null
        notifyState("LIVE STREAM OFF")
    }

    @Synchronized private fun connect(gen:Long){
        if(gen!=generation||manualStop||apiKey.isBlank()||socket!=null)return
        val url="$endpoint?access_key=${URLEncoder.encode(apiKey,"UTF-8")}" 
        notifyState("LIVE STREAM CONNECTING")

        // Intentionally no custom Origin/User-Agent headers: this matches FCS's official client.
        val req=Request.Builder().url(url).build()
        socket=client.newWebSocket(req,object:WebSocketListener(){
            override fun onOpen(ws:WebSocket,response:Response){
                if(gen!=generation){ws.close(1000,"stale");return}
                notifyState("LIVE SOCKET OPEN • WAITING FOR FCS WELCOME")
            }

            override fun onMessage(ws:WebSocket,text:String){
                if(gen==generation)handleMessage(ws,text)
            }

            override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){
                if(gen!=generation)return
                val http=response?.let{" • HTTP ${it.code} ${it.message}"}.orEmpty()
                val detail="${t.javaClass.simpleName}: ${t.message?:"network failure"}".take(130)
                handleClosed("LIVE CONNECTION FAILED$http • $detail",response?.code,gen)
            }

            override fun onClosed(ws:WebSocket,code:Int,reason:String){
                if(gen!=generation)return
                val why=reason.takeIf{it.isNotBlank()}?.let{" • ${it.take(100)}"}.orEmpty()
                handleClosed("LIVE DISCONNECTED • $code$why",null,gen)
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
                synchronized(this){
                    connected=true
                    reconnectAttempt=0
                    reconnectPosted=false
                    joinedRooms=0
                    socket=ws
                }
                startHeartbeat()
                notifyState("LIVE STREAM CONNECTED • JOINING FEEDS")
                subscribeAll(ws)
                return
            }
            "message"->{
                if(j.optString("short").equals("joined_room",true)){
                    val n=synchronized(this){joinedRooms++;joinedRooms}
                    notifyState("LIVE STREAM CONNECTED • $n/${symbols.size*periods.size} FEEDS")
                }
                return
            }
            "error"->{
                val m=j.optString("message",j.optString("msg","subscription error")).take(120)
                notifyState("LIVE FEED ERROR • $m")
                return
            }
            "price"->handlePrice(j)
        }
    }

    private fun subscribeAll(ws:WebSocket){
        var delay=0L
        for(s in symbols)for(tf in periods){
            val sym=s
            val period=tf
            main.postDelayed({
                if(isConnected()&&socket===ws){
                    ws.send(JSONObject().put("type","join_symbol").put("symbol",sym).put("timeframe",period).toString())
                }
            },delay)
            delay+=180L
        }
    }

    private fun handlePrice(j:JSONObject){
        val internal=when{
            j.optString("symbol").endsWith("XAUUSD",true)->"XAUUSD"
            j.optString("symbol").endsWith("BTCUSDT",true)->"BTCUSDT"
            else->return
        }
        val tf=when(j.optString("timeframe").lowercase()){
            "1","1m"->"1m"
            "5","5m"->"5m"
            "15","15m"->"15m"
            "30","30m"->"30m"
            "60","1h"->"1h"
            else->return
        }
        val p=j.optJSONObject("prices")?:return
        val mode=p.optString("mode").lowercase()
        if(mode=="profile")return

        val applied:Candle?=if(mode=="initial"||mode=="candle"||(p.has("o")&&p.has("h")&&p.has("l")&&p.has("c"))){
            val close=p.optDouble("c")
            FcsClient.applyLiveCandle(
                internal,tf,
                Candle(
                    p.optLong("t",p.optLong("update",0L)),
                    p.optDouble("o",close),p.optDouble("h",close),p.optDouble("l",close),close,p.optDouble("v",0.0)
                )
            )
        }else if(p.has("c")){
            FcsClient.applyLivePrice(internal,tf,p.optLong("t",p.optLong("update",0L)),p.optDouble("c"))
        }else null

        if(applied!=null)listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}}
    }

    private fun startHeartbeat(){
        main.removeCallbacks(heartbeat)
        main.postDelayed(heartbeat,25_000L)
    }

    private fun stopHeartbeat(){main.removeCallbacks(heartbeat)}

    private fun handleClosed(state:String,httpCode:Int?,gen:Long){
        synchronized(this){connected=false;socket=null;joinedRooms=0}
        stopHeartbeat()
        notifyState(state)
        if(manualStop||gen!=generation)return

        if(httpCode==401||httpCode==403){
            notifyState("FCS REJECTED LIVE KEY / SOCKET SUBSCRIPTION • HTTP $httpCode")
            return
        }
        if(httpCode==404){
            notifyState("FCS WEBSOCKET ENDPOINT RETURNED HTTP 404")
            return
        }
        scheduleReconnect(gen)
    }

    @Synchronized private fun scheduleReconnect(gen:Long){
        if(reconnectPosted||manualStop||gen!=generation)return
        reconnectPosted=true
        reconnectAttempt++
        val delay=(3000L*reconnectAttempt.coerceAtMost(5)).coerceAtMost(15_000L)
        notifyState("LIVE STREAM RECONNECTING • ${delay/1000}s")
        main.postDelayed({
            synchronized(this){reconnectPosted=false}
            connect(gen)
        },delay)
    }

    private fun notifyState(s:String){
        lastState=s
        listeners.forEach{runCatching{it.onSocketState(s)}}
    }
}
