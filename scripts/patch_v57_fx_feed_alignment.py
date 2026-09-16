from pathlib import Path
import re

# v57: align the visible TradingView Gold feed and the analysis feed to FX.
# User-requested architecture:
#   TradingView: FX:XAUUSD
#   FCS: XAUUSD commodity filtered with exchange=FX
# Also remove the v56 pre-validation round-trip so a manual ANALYZE goes directly
# to the market-data request. Authentication/API errors stay fail-closed but are
# presented generically rather than accusing the user's key.

# -----------------------------------------------------------------------------
# FCS: FX feed instead of OANDA, fresh cache, no separate validation call.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=p.read_text()

# Fresh cache namespace: never mix OANDA-era or previous generic history with FX.
s=s.replace('mh_candle_cache_v55_oanda_exchange','mh_candle_cache_v57_fx')
s=s.replace('mh_candle_cache_v53_oanda','mh_candle_cache_v57_fx')

# v55 history contract -> FX exchange.
s=s.replace(
    '"XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity","ONA")',
    '"XAUUSD"->fetch("forex",key,"XAUUSD",period,length,"commodity","FX")'
)

# v55 latest contract -> FX exchange.
s=s.replace('&type=commodity&exchange=ONA&get_profile=1&access_key=',
            '&type=commodity&exchange=FX&get_profile=1&access_key=')

# Provider verification follows FX now. Empty exchange is tolerated, but an
# explicitly different provider is blocked rather than silently mixed.
s=s.replace('if(exchange.isNotBlank()&&exchange!="ONA")',
            'if(exchange.isNotBlank()&&exchange!="FX")')
s=s.replace('OANDA data was required; signal blocked.',
            'FX feed data was required; signal blocked.')

# Remove v56's extra validation round-trip. The actual history/latest endpoint
# remains the source of truth and still fails closed if FCS returns an error.
s=s.replace('        if(force)validateAccessKey(cleanKey)\n','')

# Do not show "access key rejected" wording. Keep authentication failure honest
# but neutral because FCS can return code 101 for request/auth parsing failures.
s=s.replace('IllegalStateException("FCS ACCESS KEY REJECTED — UPDATE ANALYSIS KEY")',
            'IllegalStateException("MARKET DATA CONNECTION UNAVAILABLE — RETRY OR UPDATE ANALYSIS KEY")')
s=s.replace('IllegalStateException("FCS ACCESS KEY MISSING — UPDATE ANALYSIS KEY")',
            'IllegalStateException("ANALYSIS ACCESS KEY REQUIRED")')
s=s.replace('IllegalStateException("FCS ACCOUNT INACTIVE / EXPIRED — UPDATE OR RENEW ANALYSIS KEY")',
            'IllegalStateException("MARKET DATA ACCOUNT UNAVAILABLE — CHECK ANALYSIS KEY / PLAN")')
s=s.replace('IllegalStateException("FCS KEY HAS NO PERMISSION FOR THIS MARKET DATA")',
            'IllegalStateException("MARKET DATA PERMISSION UNAVAILABLE FOR THIS FEED")')
s=s.replace('IllegalStateException("FCS RATE LIMIT REACHED — WAIT AND ANALYZE AGAIN")',
            'IllegalStateException("MARKET DATA RATE LIMIT REACHED — WAIT AND ANALYZE AGAIN")')
s=s.replace('IllegalStateException("FCS MARKET DATA ERROR $apiCode${if(msg.isNotBlank())" • $msg" else ""}")',
            'IllegalStateException("MARKET DATA ERROR $apiCode${if(msg.isNotBlank())" • $msg" else ""}")')

p.write_text(s)

# -----------------------------------------------------------------------------
# TradingView: exact requested FX:XAUUSD instead of OANDA:XAUUSD.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
h=p.read_text()
h=h.replace("'OANDA:XAUUSD'","'FX:XAUUSD'")
h=h.replace('OANDA:XAUUSD','FX:XAUUSD')
p.write_text(h)

# -----------------------------------------------------------------------------
# Clear any Gold signal created under OANDA/generic feed assumptions once.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
m=p.read_text()
anchor='        setContentView(buildUi())\n'
if 'v57_fx_feed_migrated' not in m:
    if anchor not in m: raise SystemExit('v57 migration anchor not found')
    m=m.replace(anchor,anchor+'''        if(!prefs.getBoolean("v57_fx_feed_migrated",false)){
            SignalStore.clearActiveForSymbol(this,"XAUUSD")
            prefs.edit().putBoolean("v57_fx_feed_migrated",true).apply()
        }
''',1)
p.write_text(m)

# Version
p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 57',g);g=re.sub(r'versionName = "[^"]+"','versionName = "57.0"',g);p.write_text(g)
print('v57 FX:XAUUSD TradingView + FCS exchange=FX alignment applied')
