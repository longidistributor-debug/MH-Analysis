from pathlib import Path

f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=f.read_text()

# V.05: provider consistently accepts the two history requests but rejects the third latest request.
# Keep the whole analysis inside the user's <=3 calls/min requirement by using only TWO FCS REST calls.
old='''        val htfResult=fetchMarket(sym,accessKey,htf,SAFE_HISTORY_LENGTH)\n        credits+=htfResult.second;lastFailedAttemptCredits=credits\n        val quoteResult=fetchLatest(sym,accessKey)\n        credits+=quoteResult.second;lastFailedAttemptCredits=credits\n\n        val selected=selectedResult.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}\n        val higher=htfResult.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}'''
new='''        val htfResult=fetchMarket(sym,accessKey,htf,SAFE_HISTORY_LENGTH)\n        credits+=htfResult.second;lastFailedAttemptCredits=credits\n\n        val selected=selectedResult.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}\n        val higher=htfResult.first.sortedBy{normalizeTs(it.t)}.map{it.copy(t=normalizeTs(it.t))}'''
if old not in s: raise SystemExit('V05 manual pack anchor A not found')
s=s.replace(old,new,1)
old='''        putCache(sym,tf,selected,true);putCache(sym,htf,higher,true)\n        quoteResult.first.bid?.let{b->quoteResult.first.ask?.let{a->LiveMarketState.update(sym,b,a,System.currentTimeMillis())}}\n        lastFailedAttemptCredits=0\n        return ManualAnalysisPack(selected.takeLast(SAFE_HISTORY_LENGTH),higher.takeLast(SAFE_HISTORY_LENGTH),htf,quoteResult.first,credits)'''
new='''        putCache(sym,tf,selected,true);putCache(sym,htf,higher,true)\n        val latest=selected.last()\n        // Execution snapshot is derived from the freshest accepted selected-TF candle.\n        // No third FCS REST request is made; bid/ask remain unknown and execution scoring\n        // handles that conservatively instead of failing the entire analysis.\n        val quote=MarketQuote(latest.c,null,null,normalizeTs(latest.t))\n        lastFailedAttemptCredits=0\n        return ManualAnalysisPack(selected.takeLast(SAFE_HISTORY_LENGTH),higher.takeLast(SAFE_HISTORY_LENGTH),htf,quote,credits)'''
if old not in s: raise SystemExit('V05 manual pack anchor B not found')
s=s.replace(old,new,1)
s=s.replace('V.03 contract: fresh FCS REST traffic','V.05 contract: fresh FCS REST traffic',1)
s=s.replace('One manual analysis = exactly 3 provider calls:', 'One manual analysis = exactly 2 provider calls (within the <=3/min plan):',1)
s=s.replace('1) selected timeframe history, 2) true provider HTF history,\n     * 3) latest execution snapshot. Everything else is local/cache/socket/calendar.', '1) selected timeframe history, 2) true provider HTF history.\n     * Latest execution price is derived from the freshest selected-TF candle; everything else is local/cache/calendar.',1)
f.write_text(s)

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
x=m.read_text()
# Force-remove the exact auto-socket paths even if an earlier patch failed to match formatting.
x=x.replace('LiveSocketHub.addListener(this)','LiveSocketHub.stop()')
x=x.replace('savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}','LiveSocketHub.stop()')
x=x.replace('updateKeyUi();LiveSocketHub.start(this,x)','updateKeyUi();LiveSocketHub.stop()')
x=x.replace('MH - V.04','MH - V.05')
x=x.replace('FCS CHART • FRESH ANALYSIS USES EXACTLY 3 FCS REST CALLS','FCS CHART • FRESH ANALYSIS USES 2 FCS REST CALLS')
x=x.replace('3 calls per manual analysis • READY','2 calls per manual analysis • READY')
x=x.replace('next 3-call pack in ${left}s','next analysis in ${left}s')
x=x.replace('MANUAL 3-CALL PACK COOLDOWN','MANUAL ANALYSIS COOLDOWN')
x=x.replace('1/3 selected timeframe • 2/3 true HTF • 3/3 execution snapshot…','1/2 selected timeframe • 2/2 true HTF…')
x=x.replace('FCS PROVIDER WINDOW ACTIVE\\n${partial.coerceAtLeast(1)} request(s) were accepted in this pack. Next fresh 3-call pack in ${localWait}s.','FCS PROVIDER WINDOW ACTIVE\\n${partial.coerceAtLeast(1)} request(s) were accepted. Next fresh analysis in ${localWait}s.')
x=x.replace('FCS CHART • PRESS NEW ANALYZE / RE-EVALUATE FOR FRESH 3-CALL ANALYSIS','FCS CHART • PRESS NEW ANALYZE / RE-EVALUATE FOR FRESH 2-CALL ANALYSIS')
if 'savedHistoryKey().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start' in x: raise SystemExit('V05 failed to remove main auto socket start')
if 'updateKeyUi();LiveSocketHub.start(this,x)' in x: raise SystemExit('V05 failed to remove key-save socket start')
m.write_text(x)

# Floating overlay must also never auto-open an FCS socket.
o=Path('app/src/main/java/com/mh/analysis/OverlayService.kt')
y=o.read_text()
y=y.replace('startFg();createBubble();LiveSocketHub.addListener(this)','startFg();createBubble();LiveSocketHub.stop()')
y=y.replace('prefs.getString("api_key","")?.trim().orEmpty().takeIf{it.isNotBlank()}?.let{LiveSocketHub.start(this,it)}','LiveSocketHub.stop()')
y=y.replace('LiveSocketHub.addListener(this)','LiveSocketHub.stop()')
if 'takeIf{it.isNotBlank()}?.let{LiveSocketHub.start' in y: raise SystemExit('V05 failed to remove overlay auto socket start')
o.write_text(y)

b=Path('app/build.gradle.kts')
z=b.read_text().replace('versionCode = 36','versionCode = 37').replace('versionName = "V.04"','versionName = "V.05"')
b.write_text(z)

print('V.05 reliable two-call FCS analysis pack + forced socket isolation applied')
