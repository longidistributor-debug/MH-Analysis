from pathlib import Path

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=m.read_text()

# V.04: absolutely no automatic FCS socket/network activity from main screen lifecycle.
s=s.replace('''    override fun onResume(){\n        super.onResume()\n        LiveSocketHub.addListener(this)\n        savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}\n        updateCallLabel()\n    }''','''    override fun onResume(){\n        super.onResume()\n        // V.04: do not auto-connect FCS WebSocket. Manual analysis owns the provider window.\n        LiveSocketHub.stop()\n        updateCallLabel()\n    }''',1)

s=s.replace('''    override fun onPause(){\n        LiveSocketHub.removeListener(this)\n        super.onPause()\n    }''','''    override fun onPause(){\n        super.onPause()\n    }''',1)

s=s.replace('updateKeyUi();LiveSocketHub.start(this,x)','updateKeyUi();LiveSocketHub.stop()',1)

# Ensure any socket started by a prior component is closed before a fresh manual pack.
s=s.replace('''        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"\n        busy=true;status.text=''', '''        LiveSocketHub.stop()\n        val token=++analyzeGeneration;val reqSymbol=symbol;val reqPeriod=period;val reqContext="$reqSymbol|$reqPeriod"\n        busy=true;status.text=''',1)

s=s.replace('MH - V.03','MH - V.04')
m.write_text(s)

# Floating overlay must not auto-open an FCS socket either; it can use the last manual pack/cache.
o=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
x=o.read_text()
x=x.replace('''        startFg();createBubble();LiveSocketHub.addListener(this)\n        prefs.getString("api_key","")?.trim().orEmpty().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}''','''        startFg();createBubble()\n        // V.04: no automatic provider socket. Floating view uses cached/manual-pack data only.\n        LiveSocketHub.stop()''',1)
x=x.replace('override fun onDestroy(){LiveSocketHub.removeListener(this);hidePanel();','override fun onDestroy(){hidePanel();',1)
o.write_text(x)

b=Path('app/build.gradle.kts')
y=b.read_text().replace('versionCode = 35','versionCode = 36').replace('versionName = "V.03"','versionName = "V.04"')
b.write_text(y)

print('V.04 isolated manual FCS 3-call pack applied')
