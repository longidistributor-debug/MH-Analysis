from pathlib import Path
import re

# v68:
# - Fix Previous Day High/Low session mismatch by using the provider's native 1D candle,
#   NOT grouping 15m/1h candles by the phone/Pakistan calendar date.
# - Refresh the native daily history once per UTC market date on manual ANALYZE.
# - TradingView remains visual-only. Existing analysis/SR/OB/video-reference logic is untouched.
# - Remove backend/vendor/API wording from user-visible Android text. Backend code remains unchanged.

# -----------------------------------------------------------------------------
# FcsClient: maintain a native 1D cache and expose the previous COMPLETED day.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Ensure native daily history is restored from disk across app restarts.
s=s.replace('private val periods=listOf("1m","5m","15m","30m","1h")',
            'private val periods=listOf("1m","5m","15m","30m","1h","1d")')

anchor='    private fun fetchMarket(symbol:String,key:String,period:String,length:Int):Pair<List<Candle>,Int>{'
if 'fun refreshPreviousCompletedDay(' not in s:
    if anchor not in s: raise SystemExit('v68 fetchMarket anchor missing')
    helper=r'''    @Synchronized fun previousCompletedDayCached():Candle?{
        val src=cache[cacheKey("XAUUSD","1d")]?.candles.orEmpty()
            .map{it.copy(t=normalizeTs(it.t))}.filter{it.t>0L}.sortedBy{it.t}
        if(src.isEmpty())return null
        val now=System.currentTimeMillis()/1000L
        val last=src.last()
        // Native history may include today's/running D candle. Only a completed
        // D candle can become Previous Day High/Low.
        val closed=if(now < last.t + 86_400L) src.dropLast(1) else src
        return closed.lastOrNull()
    }

    @Synchronized fun refreshPreviousCompletedDay(accessKey:String):Pair<Candle?,Int>{
        val cleanKey=normalizeAccessKey(accessKey)
        if(cleanKey.isBlank())return null to 0
        val ctx=appContext
        val utcDay=java.text.SimpleDateFormat("yyyy-MM-dd",java.util.Locale.US).apply{
            timeZone=java.util.TimeZone.getTimeZone("UTC")
        }.format(java.util.Date())
        val meta=ctx?.getSharedPreferences("mh_daily_range_v68",Context.MODE_PRIVATE)
        val cached=previousCompletedDayCached()
        if(cached!=null && meta?.getString("refresh_day","")==utcDay)return cached to 0

        val out=fetchMarket("XAUUSD",cleanKey,"1d",90)
        noteRequest()
        val fresh=out.first.map{it.copy(t=normalizeTs(it.t))}
            .filter{it.t>0L&&it.o.isFinite()&&it.h.isFinite()&&it.l.isFinite()&&it.c.isFinite()}
            .distinctBy{it.t}.sortedBy{it.t}
        if(fresh.size<2)throw IllegalStateException("DAILY MARKET HISTORY INCOMPLETE")
        putCache("XAUUSD","1d",fresh,true)
        meta?.edit()?.putString("refresh_day",utcDay)?.apply()
        return previousCompletedDayCached() to out.second
    }

'''
    s=s.replace(anchor,helper+anchor,1)

p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: refresh native D data during manual analysis and use it for map.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

# Replace v67 intraday calendar grouping with the provider-native completed D bar.
start=s.index('    private fun previousDayRange(primary:List<Candle>?):Triple<Double,Double,String>?{')
end=s.index('\n\n    private fun updateSnapshot',start)
new_pd=r'''    private fun previousDayRange(primary:List<Candle>?):Triple<Double,Double,String>?{
        val d=FcsClient.previousCompletedDayCached()?:return null
        val sec=if(d.t>9_999_999_999L)d.t/1000L else d.t
        if(sec<=0L||!d.h.isFinite()||!d.l.isFinite())return null
        // Native daily candle timestamp defines the market day. Do not rebuild the
        // day from intraday bars in the phone timezone.
        val fmt=java.text.SimpleDateFormat("dd MMM yyyy",java.util.Locale.US).apply{
            timeZone=java.util.TimeZone.getTimeZone("UTC")
        }
        return Triple(d.h,d.l,fmt.format(java.util.Date(sec*1000L)))
    }'''
s=s[:start]+new_pd+s[end:]

# Manual analyze: selected timeframe remains the analysis source. The native 1D
# request is an independent map refresh and must never block an otherwise valid analysis.
old='''                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)
                runOnUiThread{
                    busy=false;if(credits>0)addUsage(credits);calls.text="Analysis calls: ${usage()}/500"'''
new='''                val(out,credits)=FcsClient.seedForPeriod(key,reqSymbol,reqPeriod,true)
                var mapCredits=0
                if(reqSymbol=="XAUUSD")runCatching{FcsClient.refreshPreviousCompletedDay(key)}.onSuccess{mapCredits=it.second}
                runOnUiThread{
                    busy=false;val used=credits+mapCredits;if(used>0)addUsage(used);calls.text="Analysis calls: ${usage()}/500"'''
if old not in s:
    raise SystemExit('v68 analyzeNow anchor missing')
s=s.replace(old,new,1)

# User-facing privacy/neutral wording. Do not expose backend/vendor/API details.
s=s.replace('Not available in current FCS history','Not available in current market history')
s=s.replace('current FCS history','current market history')
s=s.replace('FCS XAUUSD','MARKET DATA')
s=s.replace('FCS','MARKET DATA')
s=s.replace('API','DATA')

p.write_text(s)

# -----------------------------------------------------------------------------
# Other user-visible Android surfaces: neutralize transport/provider terminology.
# Internal class names and URLs are untouched because replacements are only uppercase UI words.
# -----------------------------------------------------------------------------
for fn in ['OverlayService.kt','AlarmService.kt']:
    p=Path('app/src/main/java/com/mh/analysis')/fn
    if not p.exists():continue
    x=p.read_text()
    x=x.replace('FCS XAUUSD','MARKET DATA').replace('FCS','MARKET DATA').replace('API','DATA')
    x=x.replace('REST TRACKING','MARKET TRACKING').replace('REST RECOVERY','MARKET RECOVERY')
    p.write_text(x)

# Neutralize any final surfaced exception wording while preserving backend behavior.
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
x=p.read_text()
x=x.replace('FCS ','Market ').replace('FCS\u2019','Market\u2019')
x=x.replace('provider mismatch','market-source mismatch')
p.write_text(x)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 68',g);g=re.sub(r'versionName = "[^"]+"','versionName = "68.0"',g);p.write_text(g)
print('v68 native daily PDH/PDL + private backend wording applied')
