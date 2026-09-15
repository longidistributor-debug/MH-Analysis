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
        .pingInterval(20,TimeUnit.SECONDS)
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

    // These are the exact app timeframes and are supported directly by FCS WebSocket v4.
    private val periods=listOf("1m","5m","15m","30m","1h")
    private val symbols=listOf("XAUUSD","BTCUSDT")

    @Synchronized fun addListener(l:Listener){listeners.add(l)}
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
        socket?.cancel()
        socket=null
        connected=false
        connect()
    }

    @Synchronized fun stop(){
        manualStop=true
        connected=false
        joinedRooms=0
        socket?.close(1000,"manual")
        socket=null
        notifyState("LIVE STREAM OFF")
    }

    @Synchronized private fun connect(){
        if(manualStop||apiKey.isBlank()||socket!=null)return
        notifyState(if(reconnects==0)"LIVE STREAM CONNECTING" else "LIVE STREAM RECONNECTING")
        val req=Request.Builder().url("$SOCKET_URL?access_key=${apiKey}").build()
        socket=client.newWebSocket(req,object:WebSocketListener(){
            override fun onOpen(ws:WebSocket,response:Response){notifyState("LIVE STREAM AUTHENTICATING")}
            override fun onMessage(ws:WebSocket,text:String){handleMessage(ws,text)}
            override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){
                val suffix=response?.code?.let{" • HTTP $it"}.orEmpty()
                handleClosed("LIVE STREAM CONNECTION LOST$suffix")
            }
            override fun onClosed(ws:WebSocket,code:Int,reason:String){handleClosed("LIVE STREAM DISCONNECTED")}
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
                notifyState("LIVE STREAM CONNECTED")
                return
            }
            "message"->{
                if(j.optString("short").equals("joined_room",true)){
                    synchronized(this){joinedRooms++}
                    notifyState("LIVE STREAM CONNECTED • $joinedRooms FEEDS")
                }
                return
            }
            "error"->{
                val m=j.optString("message",j.optString("msg","check WebSocket subscription/key"))
                notifyState("LIVE STREAM ERROR • $m")
                return
            }
            "price"->handlePrice(j)
        }
    }

    private fun subscribeAll(ws:WebSocket){
        // Use the exact text timeframes documented by FCS. One socket carries all rooms;
        // changing timeframe in the UI never needs another REST history request.
        for(s in symbols)for(tf in periods){
            val q=JSONObject()
                .put("type","join_symbol")
                .put("symbol",socketSymbol(s))
                .put("timeframe",tf)
            ws.send(q.toString())
        }
    }

    private fun handlePrice(j:JSONObject){
        val internal=internalSymbol(j.optString("symbol"))?:return
        val tf=internalPeriod(j.optString("timeframe"))?:return
        val p=j.optJSONObject("prices")?:return
        val mode=p.optString("mode").lowercase()

        // FCS sends profile first. It contains no OHLC data.
        if(mode=="profile")return

        // Initial + candle are complete current-candle OHLCV snapshots.
        if(mode=="initial"||mode=="candle"||(
                p.has("c")&&p.has("o")&&p.has("h")&&p.has("l")
            )){
            if(!p.has("c"))return
            val t=p.optLong("t",0L)
            val close=p.optDouble("c")
            val c=Candle(
                t,
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

        // askbid updates can arrive several times inside the same candle. They update the
        // visible candle close/high/low without consuming REST credits.
        if(mode=="askbid"||p.has("c")){
            val price=p.optDouble("c",Double.NaN)
            if(price.isNaN())return
            val t=p.optLong("t",0L)
            val applied=FcsClient.applyLivePrice(internal,tf,t,price)?:return
            listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}}
        }
    }

    private fun handleClosed(state:String){
        synchronized(this){connected=false;socket=null;joinedRooms=0}
        notifyState(state)
        if(manualStop)return
        scheduleReconnect()
    }

    @Synchronized private fun scheduleReconnect(){
        if(reconnectPosted||manualStop)return
        reconnectPosted=true
        reconnects++
        val delay=(3000L*(reconnects.coerceAtMost(5))).coerceAtMost(15000L)
        main.postDelayed({synchronized(this){reconnectPosted=false};connect()},delay)
    }

    private fun notifyState(s:String){listeners.forEach{runCatching{it.onSocketState(s)}}}
    private fun socketSymbol(s:String)=when(s.uppercase()){
        "XAUUSD"->"FX:XAUUSD"
        else->"BINANCE:BTCUSDT"
    }
    private fun internalSymbol(s:String):String?=when{
        s.endsWith("XAUUSD",true)->"XAUUSD"
        s.endsWith("BTCUSDT",true)->"BTCUSDT"
        else->null
    }
    private fun internalPeriod(tf:String):String?=when(tf.trim().lowercase()){
        "1","1m"->"1m"
        "5","5m"->"5m"
        "15","15m"->"15m"
        "30","30m"->"30m"
        "60","1h"->"1h"
        else->null
    }
}