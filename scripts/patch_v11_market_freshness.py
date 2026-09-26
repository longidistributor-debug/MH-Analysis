from pathlib import Path

u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt')
x=u.read_text()
start=x.find('    private fun execution(symbol:String,timeframe:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution{')
end=x.find('    /**\n     * Controlled calibration',start)
if start==-1 or end==-1: raise SystemExit('V11 execution function boundary not found')
new_exec='''    private fun execution(symbol:String,timeframe:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution{
        val a=atr(c,14).coerceAtLeast(1e-9)
        val last=c.last();val prev=c.getOrNull(c.lastIndex-1)?:last
        val nowSec=System.currentTimeMillis()/1000L
        val lastTs=if(last.t>9_999_999_999L)last.t/1000L else last.t
        val tfSec=when(timeframe.lowercase()){
            "1m"->60L;"5m"->300L;"15m"->900L;"30m"->1800L;"1h"->3600L;else->900L
        }
        val expectedBucket=(nowSec/tfSec)*tfSec
        val lagSec=(expectedBucket-lastTs).coerceAtLeast(0L)
        val lagBars=(lagSec/tfSec).toInt()
        val rangeAtr=((last.h-last.l).coerceAtLeast(0.0))/a
        val gapAtr=abs(last.o-prev.c)/a
        val live=LiveMarketState.quote(symbol)
        val spread=quote.spread?:live?.spread
        val spreadAtr=spread?.div(a)
        val utc=Instant.now().atZone(ZoneOffset.UTC)
        val weekend=utc.dayOfWeek==DayOfWeek.SATURDAY||utc.dayOfWeek==DayOfWeek.SUNDAY
        val fridayClose=utc.dayOfWeek==DayOfWeek.FRIDAY&&utc.hour>=21
        val rollover=(utc.hour==21&&utc.minute>=50)||(utc.hour==22&&utc.minute<=15)
        val gold=symbol.equals("XAUUSD",true)
        val btc=symbol.equals("BTCUSDT",true)

        if(!quote.price.isFinite()||quote.price<=0.0)return Execution(true,99,"Execution blocked: invalid current market price")
        if(gold&&weekend)return Execution(true,99,"Gold market is closed for the weekend")
        if(gold&&fridayClose)return Execution(true,99,"Gold Friday-close execution window is closed")
        if(gold&&rollover)return Execution(true,99,"Gold rollover execution window is blocked")
        if(spreadAtr!=null&&spreadAtr>.18)return Execution(true,99,"Live spread is abnormal (${two(spreadAtr)} ATR)")
        if(rangeAtr>4.5)return Execution(true,99,"Execution blocked: current candle volatility shock ${two(rangeAtr)} ATR")

        // Provider history endpoints can legitimately return the latest completed bar rather than
        // an in-progress bar. Treat short bar lag as normal/caution; only hard-block genuinely stale
        // market history. BTC is 24/7 and gets a wider tolerance than session-based XAUUSD.
        val hardStaleBars=if(btc)8 else 5
        if(lagBars>=hardStaleBars)return Execution(true,99,"Execution blocked: market history is genuinely stale ($lagBars bars behind)")

        // Sequence integrity: detect badly broken recent history independently of provider bar lag.
        val recent=c.takeLast(8)
        var brokenGaps=0
        for(i in 1 until recent.size){
            val t0=if(recent[i-1].t>9_999_999_999L)recent[i-1].t/1000L else recent[i-1].t
            val t1=if(recent[i].t>9_999_999_999L)recent[i].t/1000L else recent[i].t
            if(t1<=t0 || t1-t0>tfSec*4L)brokenGaps++
        }
        if(brokenGaps>=2)return Execution(true,99,"Execution blocked: recent candle sequence has multiple timestamp gaps")

        var penalty=0
        if(spreadAtr!=null&&spreadAtr>.08)penalty+=6
        if(rangeAtr>2.5)penalty+=4 else if(rangeAtr>1.8)penalty+=2
        if(gapAtr>1.0)penalty+=4 else if(gapAtr>.60)penalty+=2
        penalty+=when{
            lagBars<=1->0
            lagBars==2->2
            lagBars==3->3
            else->4
        }
        if(brokenGaps==1)penalty+=2
        penalty=penalty.coerceIn(0,14)

        val session=when{
            btc->"24/7 crypto"
            utc.hour in 7..11->"London"
            utc.hour in 12..16->"London/New York overlap"
            utc.hour in 17..20->"New York"
            else->"off-peak"
        }
        val spreadText=spreadAtr?.let{" • live spread ${two(it)} ATR"}.orEmpty()
        val lagText=when(lagBars){0->"current bar";1->"1 bar lag";else->"$lagBars bars lag"}
        val quality=if(penalty==0)"acceptable" else "caution -$penalty"
        return Execution(false,penalty,"Execution quality: $session • $lagText • range ${two(rangeAtr)} ATR • gap ${two(gapAtr)} ATR$spreadText • $quality")
    }

'''
x=x[:start]+new_exec+x[end:]
u.write_text(x)

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
y=m.read_text()
y=y.replace('MH - V.10','MH - V.11')
# V.09 used action-style LEVELS OFF/ON labels. V.11 shows the current state explicitly.
y=y.replace('LEVELS OFF','LEVELS: ON')
y=y.replace('LEVELS ON','LEVELS: OFF')
# The replacements above can cross-replace depending on source order; normalize known state strings.
y=y.replace('LEVELS: OFF: ON','LEVELS: ON').replace('LEVELS: ON: OFF','LEVELS: OFF')
m.write_text(y)

b=Path('app/build.gradle.kts')
g=b.read_text().replace('versionCode = 42','versionCode = 43').replace('versionName = "V.10"','versionName = "V.11"')
b.write_text(g)
print('V.11 symbol-aware market freshness + explicit levels state applied')
