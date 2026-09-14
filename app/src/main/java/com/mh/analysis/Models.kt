package com.mh.analysis

data class Candle(val t:Long,val o:Double,val h:Double,val l:Double,val c:Double,val v:Double=0.0)

data class Signal(
    val id:String,val symbol:String,val timeframe:String,val direction:String,
    val entry:Double,val sl:Double,val tp1:Double,val tp2:Double,
    val score:Int,val bullScore:Int,val bearScore:Int,val validBars:Int,
    val createdAt:Long,val createdCandleTime:Long,val status:String,
    val reasons:List<String>,val ema20:Double,val ema50:Double,val rsi:Double,
    val macd:Double,val atr:Double,val fvgType:String?,val fvgLow:Double?,val fvgHigh:Double?,
    val validityReason:String,val slReason:String,val tp1Reason:String,val tp2Reason:String,val setupReason:String
)

data class ActiveSignal(val signal:Signal,val activatedAt:Long?=null,val barsSeen:Int=0,val state:String="PENDING")

data class TradeRecord(
    val id:String,val symbol:String,val timeframe:String,val direction:String,
    val entry:Double,val sl:Double,val tp1:Double,val score:Int,
    val startedAt:Long,val activatedAt:Long?,val endedAt:Long?,val result:String
)

data class AlarmEntry(
    val id:String,val signalId:String,val symbol:String,val timeframe:String,val direction:String,
    val entry:Double,val expiresAt:Long,val createdAt:Long,val enabled:Boolean=true,
    val status:String="ARMED",val triggeredAt:Long?=null
)
