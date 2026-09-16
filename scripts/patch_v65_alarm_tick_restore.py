from pathlib import Path
import re

# v65 compile fix for v64: v64 removed the old socket block too broadly and
# accidentally removed AlarmService.tick. Restore the REST recovery scheduler.
p=Path('app/src/main/java/com/mh/analysis/AlarmService.kt')
s=p.read_text()
if 'private val tick:Runnable' not in s:
    anchor='    private fun scheduleNext(ms:Long)'
    if anchor not in s: raise SystemExit('AlarmService scheduleNext anchor missing')
    tick='''    private val tick:Runnable=object:Runnable{
        override fun run(){
            if(!running)return
            if(fetching){scheduleNext(3000L);return}
            val key=prefs.getString("api_key","")?.trim().orEmpty()
            val pending=SignalStore.pendingSignals(this@AlarmService)
            val open=SignalStore.openTrades(this@AlarmService)
            if(key.isBlank()){updateService("Analysis key missing • background tracking paused");scheduleNext(60_000L);return}
            if(pending.isEmpty()&&open.isEmpty()){updateService("No pending/open trades • background monitor idle");stopSelf();return}

            pending.forEach{AlarmStore.ensureArmed(this@AlarmService,it.signal)}
            val symbols=(pending.map{it.signal.symbol}+open.map{it.signal.symbol}).distinct()
            val lifeTasks=symbols.map{Task("LIFE",it,"1m")}
            val structureTasks=pending.map{it.signal}.distinctBy{"${it.symbol}|${it.timeframe}"}.map{Task("STRUCT",it.symbol,it.timeframe)}
            if(lifeTasks.isEmpty()){scheduleNext(30_000L);return}
            val useStructure=structureTasks.isNotEmpty()&&cursor%3==2
            val task=if(useStructure)structureTasks[(cursor/3)%structureTasks.size] else lifeTasks[cursor%lifeTasks.size]
            cursor=(cursor+1)%100000
            updateService("REST TRACKING • ${pending.size} pending • ${open.size} open • ${task.symbol} ${task.timeframe}")
            fetching=true
            thread(name="mh-rest-tracking"){
                try{if(task.kind=="LIFE")pollLifecycle(key,task.symbol) else pollStructure(key,task.symbol,task.timeframe)}catch(_:Throwable){}
                finally{fetching=false;scheduleNext(21_000L)}
            }
        }
    }

'''
    s=s.replace(anchor,tick+anchor,1)

p.write_text(s)

p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \\d+','versionCode = 65',g);g=re.sub(r'versionName = "[^"]+"','versionName = "65.0"',g);p.write_text(g)
print('v65 AlarmService REST tick restored')
