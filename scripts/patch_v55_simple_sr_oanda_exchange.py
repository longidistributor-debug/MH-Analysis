from pathlib import Path
import re

# v55: remove the FCS 400 source and make S/R exactly match the requested simple rule.
# - Gold API format: symbol=XAUUSD&type=commodity&exchange=ONA (documented FCS provider filter).
# - Fresh OANDA-only cache namespace; never reuse failed/legacy Gold cache.
# - Selected timeframe S/R is intentionally simple and deterministic:
#     SUPPORT = previous CLOSED candle low.
#     RESISTANCE = highest CLOSED candle high in a recent selected-timeframe window.
# - Running candle never creates a new S/R level; it only trades around/breaks the closed-candle levels.
# - Every timeframe uses its own native/aggregated candle set, so values can differ by timeframe.

# -----------------------------------------------------------------------------
# FCS request format
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Fresh namespace so no earlier generic/provider-experiment Gold history survives.
s=s.replace('mh_candle_cache_v53_oanda','mh_candle_cache_v55_oanda_exchange')

# History call: plain XAUUSD commodity + explicit OANDA exchange filter.
s=s.replace(
    '"XAUUSD"->fetch("forex",key,"ONA:XAUUSD",period,length,"");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")',
    '"XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity","ONA");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto","")',
    1
)

# Shared fetch helper: add explicit exchange query only when requested.
s=s.replace(
    'private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String):Pair<List<Candle>,Int>{',
    'private fun fetch(group:String,key:String,symbol:String,period:String,length:Int,type:String,exchange:String=""):Pair<List<Candle>,Int>{',
    1
)
old='''        val p=normalizePeriod(period)\n        val typeQ=if(type.isBlank())"" else "&type=${enc(type)}"\n        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0${typeQ}&access_key=${enc(key)}"'''
new='''        val p=normalizePeriod(period)\n        val typeQ=if(type.isBlank())"" else "&type=${enc(type)}"\n        val exchangeQ=if(exchange.isBlank())"" else "&exchange=${enc(exchange)}"\n        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0${typeQ}${exchangeQ}&access_key=${enc(key)}"'''
if old not in s:
    raise SystemExit('v55 history URL anchor not found')
s=s.replace(old,new,1)

# Latest call uses the same exact symbol/type/exchange contract as History.
old='''            "XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("ONA:XAUUSD")}&period=${enc(p)}&get_profile=1&access_key=${enc(key)}"'''
new='''            "XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("XAUUSD")}&period=${enc(p)}&type=commodity&exchange=ONA&get_profile=1&access_key=${enc(key)}"'''
if old not in s:
    raise SystemExit('v55 latest URL anchor not found')
s=s.replace(old,new,1)

# Provider verification now expects the explicit exchange filter response. If FCS
# identifies another provider, block the signal instead of silently mixing feeds.
old='''            val ticker=item.optString("ticker",item.optString("symbol","")).uppercase()\n            val exchange=item.optString("exchange","").ifBlank{item.optJSONObject("profile")?.optString("exchange","").orEmpty()}.uppercase()\n            val tickerOanda=ticker.startsWith("ONA:")\n            if(exchange.isNotBlank()&&exchange!="ONA"&&!tickerOanda)\n                throw IllegalStateException("Gold provider mismatch detected ($exchange). OANDA data was required; signal blocked.")'''
new='''            val exchange=item.optString("exchange","").ifBlank{item.optJSONObject("profile")?.optString("exchange","").orEmpty()}.uppercase()\n            if(exchange.isNotBlank()&&exchange!="ONA")\n                throw IllegalStateException("Gold provider mismatch detected ($exchange). OANDA data was required; signal blocked.")'''
if old in s:
    s=s.replace(old,new,1)

p.write_text(s)

# -----------------------------------------------------------------------------
# AnalysisEngine: user's deterministic selected-timeframe S/R rule.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
start=s.index('    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{')
end=s.index('\n\n    fun chartLevels',start)
new_levels='''    fun majorRangeLevels(timeframe:String,c:List<Candle>):Pair<Double,Double>?{
        if(c.size<4)return null
        // Last candle is the running candle. S/R must come from CLOSED candles only.
        val closed=c.dropLast(1);if(closed.size<3)return null
        val previous=closed.last()
        val tf=tfMinutes(timeframe)
        // Recent structure window, measured in candles of the SELECTED timeframe.
        // Keeping a candle-count window (rather than one global time range) means
        // 5m/15m/30m/1h each naturally produce their own structure.
        val look=when{
            tf<=1->36;tf<=5->30;tf<=10->28;tf<=15->24;tf<=30->22;tf<=60->20;
            tf<=120->18;tf<=300->16;tf<=1440->14;tf<=10080->12;else->10
        }
        val w=closed.takeLast(min(look,closed.size))
        val support=previous.l
        val resistance=w.maxOf{it.h}
        if(!support.isFinite()||!resistance.isFinite()||resistance<=support)return null
        return support to resistance
    }'''
s=s[:start]+new_levels+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# UI: simple labels and a clean one-time Gold reset for the new feed contract.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
m=p.read_text()
m=m.replace('➜ MAJOR SUPPORT: ${price(lv.support)}$supportState','➜ SUPPORT: ${price(lv.support)}$supportState')
m=m.replace('➜ MAJOR RESISTANCE: ${price(lv.resistance)}$resistanceState','➜ RESISTANCE: ${price(lv.resistance)}$resistanceState')

anchor='        setContentView(buildUi())\n'
if 'v55_feed_migrated' not in m:
    if anchor not in m: raise SystemExit('v55 MainActivity migration anchor not found')
    m=m.replace(anchor,anchor+'''        if(!prefs.getBoolean("v55_feed_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD")
            prefs.edit().putBoolean("v55_feed_migrated",true).apply()
        }
''',1)
p.write_text(m)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 55',g);g=re.sub(r'versionName = "[^"]+"','versionName = "55.0"',g);p.write_text(g)
print('v55 documented OANDA exchange request + simple selected-timeframe S/R applied')
