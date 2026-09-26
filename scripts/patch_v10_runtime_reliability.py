from pathlib import Path

# V.10: make economic calendar first-load deterministic and align execution quality
# with the reliable two-call candle architecture. No new FCS REST calls are added.

cal=Path('app/src/main/java/com/mh/analysis/EconomicCalendarClient.kt')
s=cal.read_text()
s=s.replace('private const val MAX_CACHE_AGE_MS=72L*60L*60L*1000L','private const val MAX_CACHE_AGE_MS=7L*24L*60L*60L*1000L')
if '@Volatile private var lastRefreshError:String=""' not in s:
    s=s.replace('@Volatile private var events:List<Event> = emptyList()','@Volatile private var events:List<Event> = emptyList()\n    @Volatile private var lastRefreshError:String=""')
old='''        thread(name="mh-calendar-refresh"){
            try{refreshNow()}finally{refreshing.set(false)}
        }
    }
'''
new='''        thread(name="mh-calendar-refresh"){
            try{refreshNow();lastRefreshError=""}
            catch(e:Exception){lastRefreshError=e.message.orEmpty().ifBlank{"calendar refresh failed"}}
            finally{refreshing.set(false)}
        }
    }

    fun ensureReady(timeoutMs:Long=8000L):Boolean{
        if(events.isNotEmpty())return true
        refreshIfStale()
        val deadline=System.currentTimeMillis()+timeoutMs.coerceAtLeast(500L)
        while(refreshing.get()&&System.currentTimeMillis()<deadline){
            try{Thread.sleep(80L)}catch(_:InterruptedException){break}
            if(events.isNotEmpty())return true
        }
        if(events.isNotEmpty())return true
        if(refreshing.compareAndSet(false,true)){
            try{refreshNow();lastRefreshError=""}
            catch(e:Exception){lastRefreshError=e.message.orEmpty().ifBlank{"calendar refresh failed"}}
            finally{refreshing.set(false)}
        }
        return events.isNotEmpty()
    }
'''
if old not in s: raise SystemExit('V10 calendar refresh anchor not found')
s=s.replace(old,new,1)
s=s.replace('''        if(clean.isEmpty())return
        synchronized(this){''','''        if(clean.isEmpty())throw IllegalStateException("no calendar data from primary/fallback feeds")
        synchronized(this){''',1)
s=s.replace('c.connectTimeout=4500;c.readTimeout=6500;c.requestMethod="GET"','c.connectTimeout=2500;c.readTimeout=3500;c.requestMethod="GET"')
s=s.replace('c.setRequestProperty("User-Agent","MH-Analysis/V.01")','c.setRequestProperty("User-Agent","Mozilla/5.0 (Android) MH-Analysis/V.10")\n        c.setRequestProperty("Accept","application/json")')
oldrisk='''        refreshIfStale()
        val snapshot=events
        if(snapshot.isEmpty())return Risk(false,0,"Economic calendar: waiting for first free-feed refresh")
'''
newrisk='''        refreshIfStale()
        if(events.isEmpty())ensureReady(8000L)
        val snapshot=events
        if(snapshot.isEmpty()){
            val err=lastRefreshError.takeIf{it.isNotBlank()}?.let{" • $it"}.orEmpty()
            return Risk(false,4,"Economic calendar: primary/fallback feeds unavailable after verified refresh • risk score -4$err")
        }
'''
if oldrisk not in s: raise SystemExit('V10 calendar risk anchor not found')
s=s.replace(oldrisk,newrisk,1)
cal.write_text(s)

u=Path('app/src/main/java/com/mh/analysis/UnifiedAnalysisEngine.kt')
x=u.read_text()
x=x.replace('val execution=execution(symbol,current,quote)','val execution=execution(symbol,timeframe,current,quote)',1)
start=x.find('    private fun execution(symbol:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution{')
end=x.find('    /**\n     * Controlled calibration',start)
if start==-1 or end==-1: raise SystemExit('V10 execution function boundary not found')
new_exec='''    private fun execution(symbol:String,timeframe:String,c:List<Candle>,quote:FcsClient.MarketQuote):Execution{
        val a=atr(c,14).coerceAtLeast(1e-9)
        val last=c.last();val prev=c.getOrNull(c.lastIndex-1)?:last
        val nowSec=System.currentTimeMillis()/1000L
        val lastTs=if(last.t>9_999_999_999L)last.t/1000L else last.t
        val tfSec=when(timeframe.lowercase()){
            "1m"->60L;"5m"->300L;"15m"->900L;"30m"->1800L;"1h"->3600L;else->900L
        }
        val ageSec=(nowSec-lastTs).coerceAtLeast(0L)
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

        if(!quote.price.isFinite()||quote.price<=0.0)return Execution(true,99,"Execution blocked: invalid current market price")
        if(gold&&weekend)return Execution(true,99,"Gold weekend quality filter blocked execution")
        if(gold&&fridayClose)return Execution(true,99,"Gold Friday-close quality filter blocked execution")
        if(gold&&rollover)return Execution(true,99,"Gold rollover-quality window blocked execution")
        if(ageSec>tfSec*2L+120L)return Execution(true,99,"Execution blocked: selected-timeframe market data is stale (${ageSec}s old)")
        if(spreadAtr!=null&&spreadAtr>.18)return Execution(true,99,"Live spread is abnormal (${two(spreadAtr)} ATR)")
        if(rangeAtr>4.5)return Execution(true,99,"Execution blocked: current candle volatility shock ${two(rangeAtr)} ATR")

        var penalty=0
        if(spreadAtr!=null&&spreadAtr>.08)penalty+=6
        if(rangeAtr>2.5)penalty+=4 else if(rangeAtr>1.8)penalty+=2
        if(gapAtr>1.0)penalty+=4 else if(gapAtr>.60)penalty+=2
        if(ageSec>tfSec+120L)penalty+=2
        penalty=penalty.coerceIn(0,12)

        val session=when(utc.hour){
            in 7..11->"London"
            in 12..16->"London/New York overlap"
            in 17..20->"New York"
            else->"off-peak"
        }
        val ageText=if(ageSec<60L)"${ageSec}s" else "${ageSec/60L}m"
        val spreadText=spreadAtr?.let{" • live spread ${two(it)} ATR"}.orEmpty()
        val quality=if(penalty==0)"acceptable" else "caution -$penalty"
        return Execution(false,penalty,"Execution quality: $session UTC • candle age $ageText • range ${two(rangeAtr)} ATR • gap ${two(gapAtr)} ATR$spreadText • $quality")
    }

'''
x=x[:start]+new_exec+x[end:]
u.write_text(x)

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
y=m.read_text().replace('MH - V.09','MH - V.10')
m.write_text(y)

b=Path('app/build.gradle.kts')
g=b.read_text().replace('versionCode = 41','versionCode = 42').replace('versionName = "V.09"','versionName = "V.10"')
b.write_text(g)
print('V.10 runtime reliability layer applied')
