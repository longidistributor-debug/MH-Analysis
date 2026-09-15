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
    private val endpoints=listOf("wss://ws-v4.fcsapi.com/ws","wss://fcsapi.com/socket4/ws")
    private val listeners=CopyOnWriteArraySet<Listener>(); private val main=Handler(Looper.getMainLooper())
    private val client=OkHttpClient.Builder().pingInterval(30,TimeUnit.SECONDS).readTimeout(0,TimeUnit.MILLISECONDS).retryOnConnectionFailure(true).build()
    private var socket:WebSocket?=null;private var apiKey="";private var connected=false;private var manualStop=false;private var reconnects=0;private var reconnectPosted=false;private var joinedRooms=0;private var heartbeatRunning=false;private var lastState="LIVE STREAM OFF";private var endpointIndex=0
    private val periods=listOf("1","5","15","30","60");private val symbols=listOf("FX:XAUUSD","BINANCE:BTCUSDT")
    private val heartbeat=object:Runnable{override fun run(){val ws=synchronized(this@LiveSocketHub){if(connected)socket else null};if(ws!=null){ws.send(JSONObject().put("type","ping").put("timestamp",System.currentTimeMillis()).toString());main.postDelayed(this,25_000)}else heartbeatRunning=false}}
    @Synchronized fun addListener(l:Listener){listeners.add(l);runCatching{l.onSocketState(lastState)}}
    @Synchronized fun removeListener(l:Listener){listeners.remove(l)}
    @Synchronized fun isConnected()=connected
    @Synchronized fun start(context:Context,key:String){FcsClient.init(context);val k=key.trim();if(k.isBlank()){notifyState("LIVE STREAM KEY REQUIRED");return};if(apiKey==k&&(connected||socket!=null))return;apiKey=k;manualStop=false;reconnects=0;endpointIndex=0;reconnectPosted=false;joinedRooms=0;stopHeartbeat();socket?.cancel();socket=null;connected=false;connect()}
    @Synchronized fun stop(){manualStop=true;connected=false;joinedRooms=0;stopHeartbeat();socket?.close(1000,"manual");socket=null;notifyState("LIVE STREAM OFF")}
    @Synchronized private fun connect(){if(manualStop||apiKey.isBlank()||socket!=null)return;val ep=endpoints[endpointIndex];notifyState("BACKGROUND LIVE CONNECTING • ${endpointIndex+1}/${endpoints.size}");val url="$ep?access_key=${URLEncoder.encode(apiKey,"UTF-8")}";val req=Request.Builder().url(url).build();socket=client.newWebSocket(req,object:WebSocketListener(){override fun onOpen(ws:WebSocket,response:Response){notifyState("BACKGROUND SOCKET OPEN • AUTHENTICATING")};override fun onMessage(ws:WebSocket,text:String){handleMessage(ws,text)};override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){val code=response?.code;handleClosed("BACKGROUND LIVE LOST${code?.let{" • HTTP $it"}.orEmpty()}",code)};override fun onClosed(ws:WebSocket,code:Int,reason:String){handleClosed("BACKGROUND LIVE DISCONNECTED • $code",code)}})}
    private fun handleMessage(ws:WebSocket,text:String){val j=runCatching{JSONObject(text)}.getOrNull()?:return;when(j.optString("type").lowercase()){ "ping"->{ws.send(JSONObject().put("type","pong").put("timestamp",System.currentTimeMillis()).toString());return};"welcome"->{synchronized(this){connected=true;reconnects=0;joinedRooms=0;socket=ws};subscribeAll(ws);startHeartbeat();notifyState("BACKGROUND LIVE CONNECTED");return};"message"->{if(j.optString("short").equals("joined_room",true)){synchronized(this){joinedRooms++};notifyState("BACKGROUND LIVE CONNECTED • $joinedRooms FEEDS")};return};"error"->{notifyState("BACKGROUND LIVE ERROR • ${j.optString("message",j.optString("msg","subscription error")).take(100)}");return};"price"->handlePrice(j)}}
    private fun subscribeAll(ws:WebSocket){for(s in symbols)for(tf in periods)ws.send(JSONObject().put("type","join_symbol").put("symbol",s).put("timeframe",tf).toString())}
    private fun handlePrice(j:JSONObject){val internal=when{j.optString("symbol").endsWith("XAUUSD",true)->"XAUUSD";j.optString("symbol").endsWith("BTCUSDT",true)->"BTCUSDT";else->return};val tf=when(j.optString("timeframe").lowercase()){"1","1m"->"1m";"5","5m"->"5m";"15","15m"->"15m";"30","30m"->"30m";"60","1h"->"1h";else->return};val p=j.optJSONObject("prices")?:return;val mode=p.optString("mode").lowercase();if(mode=="profile")return;if(mode=="initial"||mode=="candle"||(p.has("o")&&p.has("h")&&p.has("l")&&p.has("c"))){val close=p.optDouble("c");val x=Candle(p.optLong("t",0),p.optDouble("o",close),p.optDouble("h",close),p.optDouble("l",close),close,p.optDouble("v",0.0));val applied=FcsClient.applyLiveCandle(internal,tf,x);listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}};return};if(mode=="askbid"&&p.has("c")){val applied=FcsClient.applyLivePrice(internal,tf,p.optLong("t",p.optLong("update",0)),p.optDouble("c"))?:return;listeners.forEach{runCatching{it.onLiveCandle(internal,tf,applied)}}}}
    private fun startHeartbeat(){synchronized(this){if(heartbeatRunning)return;heartbeatRunning=true};main.removeCallbacks(heartbeat);main.postDelayed(heartbeat,25_000)}
    private fun stopHeartbeat(){heartbeatRunning=false;main.removeCallbacks(heartbeat)}
    private fun handleClosed(state:String,httpCode:Int?){synchronized(this){connected=false;socket=null;joinedRooms=0};stopHeartbeat();notifyState(state);if(manualStop)return;if((httpCode==404||httpCode==403||httpCode==400)&&endpointIndex<endpoints.lastIndex){endpointIndex++;reconnects=0;main.postDelayed({connect()},500);return};scheduleReconnect()}
    @Synchronized private fun scheduleReconnect(){if(reconnectPosted||manualStop)return;reconnectPosted=true;reconnects++;if(reconnects%4==0)endpointIndex=(endpointIndex+1)%endpoints.size;val delay=(3000L*reconnects.coerceAtMost(5)).coerceAtMost(15_000);main.postDelayed({synchronized(this){reconnectPosted=false};connect()},delay)}
    private fun notifyState(s:String){lastState=s;listeners.forEach{runCatching{it.onSocketState(s)}}}
}
