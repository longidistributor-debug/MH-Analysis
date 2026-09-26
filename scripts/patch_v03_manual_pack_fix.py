from pathlib import Path

f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=f.read_text()
s=s.replace('private const val MANUAL_PACK_COOLDOWN_MS=65_000L','private const val MANUAL_PACK_COOLDOWN_MS=61_000L')
s=s.replace('private const val MANUAL_PREFS="mh_manual_pack_v02"','private const val MANUAL_PREFS="mh_manual_pack_v03"')
s=s.replace('    private var restored=false\n','    private var restored=false\n    private var lastFailedAttemptCredits=0\n',1)
old='''        restored=true\n        val p=appContext?.getSharedPreferences("mh_candle_cache_v22",Context.MODE_PRIVATE)?:return'''
new='''        restored=true\n        // V.03 migration: V.02 reserved a cooldown before any provider request.\n        // Ignore that legacy false-lock state completely.\n        appContext?.getSharedPreferences("mh_manual_pack_v02",Context.MODE_PRIVATE)?.edit()?.clear()?.apply()\n        val p=appContext?.getSharedPreferences("mh_candle_cache_v22",Context.MODE_PRIVATE)?:return'''
if old not in s: raise SystemExit('init anchor not found')
s=s.replace(old,new,1)
old='''    private fun reserveManualPack(){\n        val ctx=appContext?:throw IllegalStateException("FCS client is not initialized")\n        val p=ctx.getSharedPreferences(MANUAL_PREFS,Context.MODE_PRIVATE)\n        val now=System.currentTimeMillis();val next=p.getLong(NEXT_MANUAL_AT,0L)\n        if(next>now){\n            val seconds=((next-now+999L)/1000L).toInt()\n            throw IllegalStateException("Next 3-call manual analysis pack is available in $seconds sec.")\n        }\n        // Reserve before network I/O. This survives app restart and prevents accidental\n        // duplicate packs from breaking the provider's rolling 3-requests/minute plan.\n        p.edit().putLong(NEXT_MANUAL_AT,now+MANUAL_PACK_COOLDOWN_MS).commit()\n    }'''
new='''    private fun requireManualPackAvailable(){\n        val ctx=appContext?:throw IllegalStateException("FCS client is not initialized")\n        val p=ctx.getSharedPreferences(MANUAL_PREFS,Context.MODE_PRIVATE)\n        val now=System.currentTimeMillis();val next=p.getLong(NEXT_MANUAL_AT,0L)\n        if(next>now){\n            val seconds=((next-now+999L)/1000L).toInt()\n            throw IllegalStateException("Next 3-call manual analysis pack is available in $seconds sec.")\n        }\n    }\n\n    private fun beginProviderWindowAfterFirstSuccess(){\n        val ctx=appContext?:return\n        val now=System.currentTimeMillis()\n        ctx.getSharedPreferences(MANUAL_PREFS,Context.MODE_PRIVATE)\n            .edit().putLong(NEXT_MANUAL_AT,now+MANUAL_PACK_COOLDOWN_MS).commit()\n    }\n\n    @Synchronized fun consumeFailedAttemptCredits():Int{\n        val n=lastFailedAttemptCredits\n        lastFailedAttemptCredits=0\n        return n\n    }'''
if old not in s: raise SystemExit('reserve anchor not found')
s=s.replace(old,new,1)
old='''        val sym=symbol.uppercase();val tf=normalizePeriod(period);val htf=higherTimeframe(tf)\n        reserveManualPack()\n\n        var credits=0\n        val selectedResult=fetchMarket(sym,accessKey,tf,SAFE_HISTORY_LENGTH);credits+=selectedResult.second\n        val htfResult=fetchMarket(sym,accessKey,htf,SAFE_HISTORY_LENGTH);credits+=htfResult.second\n        val quoteResult=fetchLatest(sym,accessKey);credits+=quoteResult.second'''
new='''        val sym=symbol.uppercase();val tf=normalizePeriod(period);val htf=higherTimeframe(tf)\n        requireManualPackAvailable()\n        lastFailedAttemptCredits=0\n\n        var credits=0\n        // IMPORTANT V.03: do not start local cooldown until FCS actually accepts call #1.\n        val selectedResult=fetchMarket(sym,accessKey,tf,SAFE_HISTORY_LENGTH)\n        credits+=selectedResult.second;lastFailedAttemptCredits=credits\n        beginProviderWindowAfterFirstSuccess()\n        val htfResult=fetchMarket(sym,accessKey,htf,SAFE_HISTORY_LENGTH)\n        credits+=htfResult.second;lastFailedAttemptCredits=credits\n        val quoteResult=fetchLatest(sym,accessKey)\n        credits+=quoteResult.second;lastFailedAttemptCredits=credits'''
if old not in s: raise SystemExit('manual pack anchor not found')
s=s.replace(old,new,1)
s=s.replace('return ManualAnalysisPack(selected.takeLast(SAFE_HISTORY_LENGTH),higher.takeLast(SAFE_HISTORY_LENGTH),htf,quoteResult.first,credits)','lastFailedAttemptCredits=0\n        return ManualAnalysisPack(selected.takeLast(SAFE_HISTORY_LENGTH),higher.takeLast(SAFE_HISTORY_LENGTH),htf,quoteResult.first,credits)',1)
s=s.replace('V.02 contract: fresh FCS REST traffic','V.03 contract: fresh FCS REST traffic',1)
s=s.replace('/ RE-EVALUATE in V.02.','/ RE-EVALUATE in V.03.')
f.write_text(s)

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
x=m.read_text()
x=x.replace('MH - V.02','MH - V.03')
x=x.replace('''                    busy=false;updateCallLabel()\n                    val msg=e.message.orEmpty()''','''                    busy=false\n                    val partial=FcsClient.consumeFailedAttemptCredits()\n                    if(partial>0)addUsage(partial)\n                    updateCallLabel()\n                    val msg=e.message.orEmpty()''',1)
x=x.replace('''                    status.text=if(providerRate)\n                        "FCS PROVIDER COOLDOWN\\nProvider still has requests inside its rolling 60-second window. Wait for the countdown, then press NEW ANALYZE / RE-EVALUATE.\\nNo stale signal was generated."''','''                    val localWait=FcsClient.manualCooldownSeconds()\n                    status.text=if(providerRate && localWait>0)\n                        "FCS PROVIDER WINDOW ACTIVE\\n${partial.coerceAtLeast(1)} request(s) were accepted in this pack. Next fresh 3-call pack in ${localWait}s.\\nNo stale signal was generated."\n                    else if(providerRate)\n                        "FCS PROVIDER RATE LIMIT\\nThe provider rejected the first request before this app consumed a fresh pack. No local cooldown was created. Try again when the provider window clears.\\nNo stale signal was generated."''',1)
m.write_text(x)

b=Path('app/build.gradle.kts')
y=b.read_text().replace('versionCode = 34','versionCode = 35').replace('versionName = "V.02"','versionName = "V.03"')
b.write_text(y)

print('V.03 manual pack transaction/cooldown migration applied')
