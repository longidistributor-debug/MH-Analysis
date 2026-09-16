from pathlib import Path
import re

# v54: fix FCS HTTP 400 for OANDA Gold.
# Exchange-qualified ONA:XAUUSD must not be combined with the generic
# commodity filter. Request the exact OANDA ticker directly and verify profile.

p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# History: exact OANDA ticker, no conflicting type=commodity filter.
s=s.replace(
    '"XAUUSD"->fetch("forex",key,"ONA:XAUUSD",period,length,"commodity");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")',
    '"XAUUSD"->fetch("forex",key,"ONA:XAUUSD",period,length,"");else->fetch("crypto",key,"BINANCE:BTCUSDT",period,length,"crypto")',
    1
)

# Make the shared history helper omit `type` completely when blank.
old='''        val p=normalizePeriod(period)\n        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0&type=${enc(type)}&access_key=${enc(key)}"'''
new='''        val p=normalizePeriod(period)\n        val typeQ=if(type.isBlank())"" else "&type=${enc(type)}"\n        val u="https://api-v4.fcsapi.com/$group/history?symbol=${enc(symbol)}&period=${enc(p)}&length=$length&is_chart=0${typeQ}&access_key=${enc(key)}"'''
if old not in s:
    raise SystemExit('v54 history URL anchor not found')
s=s.replace(old,new,1)

# Latest: exact OANDA ticker, no commodity filter. Ask for profile so provider
# verification is deterministic.
old='''            "XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("ONA:XAUUSD")}&period=${enc(p)}&type=commodity&access_key=${enc(key)}"'''
new='''            "XAUUSD"->"https://api-v4.fcsapi.com/forex/latest?symbol=${enc("ONA:XAUUSD")}&period=${enc(p)}&get_profile=1&access_key=${enc(key)}"'''
if old not in s:
    raise SystemExit('v54 latest URL anchor not found')
s=s.replace(old,new,1)

# Improve provider verification: accept explicit top-level exchange or profile
# exchange, and fail closed if the response clearly identifies a non-OANDA feed.
old='''            val ticker=item.optString("ticker","").uppercase()\n            val exchange=item.optJSONObject("profile")?.optString("exchange","")?.uppercase().orEmpty()\n            if(ticker.isNotBlank()&&!ticker.startsWith("ONA:")&&exchange.isNotBlank()&&exchange!="ONA")\n                throw IllegalStateException("Gold provider mismatch detected. OANDA data was required; signal blocked.")'''
new='''            val ticker=item.optString("ticker",item.optString("symbol","")).uppercase()\n            val exchange=item.optString("exchange","").ifBlank{item.optJSONObject("profile")?.optString("exchange","").orEmpty()}.uppercase()\n            val tickerOanda=ticker.startsWith("ONA:")\n            if(exchange.isNotBlank()&&exchange!="ONA"&&!tickerOanda)\n                throw IllegalStateException("Gold provider mismatch detected ($exchange). OANDA data was required; signal blocked.")'''
if old not in s:
    raise SystemExit('v54 provider verification anchor not found')
s=s.replace(old,new,1)

# Include a short server message for non-200 responses so future endpoint errors
# are diagnosable instead of only saying HTTP 400.
s=s.replace(
    'if(code !in 200..299)throw IllegalStateException("Latest market data HTTP $code")',
    'if(code !in 200..299)throw IllegalStateException("Latest market data HTTP $code • ${body.take(180)}")',
    1
)
s=s.replace(
    'if(code !in 200..299)throw IllegalStateException("Market data HTTP $code")',
    'if(code !in 200..299)throw IllegalStateException("Market data HTTP $code • ${body.take(180)}")',
    1
)

p.write_text(s)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text()
g=re.sub(r'versionCode = \\d+','versionCode = 54',g)
g=re.sub(r'versionName = "[^"]+"','versionName = "54.0"',g)
p.write_text(g)
print('v54 OANDA Gold FCS request fix applied')
