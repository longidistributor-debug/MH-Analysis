package com.mh.analysis

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.abs

/** Keeps only the latest live quote needed for execution-quality checks. */
object LiveMarketState {
    data class Quote(val bid:Double,val ask:Double,val at:Long){
        val mid:Double get()=(bid+ask)/2.0
        val spread:Double get()=abs(ask-bid)
    }

    private val quotes=ConcurrentHashMap<String,Quote>()

    fun update(symbol:String,bid:Double,ask:Double,at:Long=System.currentTimeMillis()){
        if(!bid.isFinite()||!ask.isFinite()||bid<=0.0||ask<=0.0||ask<bid)return
        quotes[symbol.uppercase()]=Quote(bid,ask,at)
    }

    fun quote(symbol:String,maxAgeMs:Long=120_000L):Quote?{
        val q=quotes[symbol.uppercase()]?:return null
        return if(System.currentTimeMillis()-q.at<=maxAgeMs)q else null
    }

    fun spreadAtr(symbol:String,atr:Double):Double?{
        if(atr<=0.0)return null
        return quote(symbol)?.spread?.div(atr)
    }
}
