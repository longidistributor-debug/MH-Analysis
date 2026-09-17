from pathlib import Path
import re

# v67 UI-only Market Map update requested by user:
# - Replace Support/Resistance rows in LIVE ANALYSIS SNAPSHOT -> MARKET MAP
#   with Previous Day High / Previous Day Low and the actual date.
# - Values come from the same FCS REST/cache candle data already used by analysis.
# - TradingView remains visual-only.
# - DO NOT change AnalysisEngine S/R, setup, video-reference indicators, signals,
#   OB logic, alarms, re-evaluation or background lifecycle.

p=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=p.read_text()

start=s.index('    private fun updateSnapshot(data:List<Candle>?=null){')
end=s.index('\n    private fun showExisting(){',start)

new_snapshot=r'''    private fun previousDayRange(primary:List<Candle>?):Triple<Double,Double,String>?{
        val tz=java.util.TimeZone.getTimeZone("Asia/Karachi")
        val keyFmt=java.text.SimpleDateFormat("yyyy-MM-dd",java.util.Locale.US).apply{timeZone=tz}
        val labelFmt=java.text.SimpleDateFormat("dd MMM yyyy",java.util.Locale.US).apply{timeZone=tz}
        val today=keyFmt.format(java.util.Date())

        fun rangeFrom(src:List<Candle>):Triple<Double,Double,String>?{
            if(src.size<2)return null
            val byDay=linkedMapOf<String,MutableList<Candle>>()
            src.sortedBy{it.t}.forEach{c->
                val sec=if(c.t>9_999_999_999L)c.t/1000L else c.t
                if(sec<=0L)return@forEach
                val k=keyFmt.format(java.util.Date(sec*1000L))
                byDay.getOrPut(k){mutableListOf()}.add(c)
            }
            // Most recent completed trading date before today. This naturally
            // skips weekends/holidays when no FCS candles exist for them.
            val prevKey=byDay.keys.filter{it<today}.lastOrNull()?:return null
            val rows=byDay[prevKey].orEmpty()
            if(rows.isEmpty())return null
            val high=rows.maxOf{it.h};val low=rows.minOf{it.l}
            if(!high.isFinite()||!low.isFinite())return null
            val first=rows.first()
            val sec=if(first.t>9_999_999_999L)first.t/1000L else first.t
            val date=labelFmt.format(java.util.Date(sec*1000L))
            return Triple(high,low,date)
        }

        val candidates=mutableListOf<List<Candle>>()
        // Weekly/monthly candles cannot represent a previous DAY range.
        val p=period.trim()
        if(primary!=null && !p.equals("1W",true) && p!="1M")candidates+=primary
        FcsClient.peek(symbol,"15m",500)?.takeIf{it.isNotEmpty()}?.let{candidates+=it}
        FcsClient.peek(symbol,"1h",500)?.takeIf{it.isNotEmpty()}?.let{candidates+=it}
        for(src in candidates){val r=rangeFrom(src);if(r!=null)return r}
        return null
    }

    private fun updateSnapshot(data:List<Candle>?=null){
        if(!::snapshot.isInitialized)return
        val active=SignalStore.loadActive(this,symbol,period)
        val basis=data?:FcsClient.peek(symbol,period,300)
        val age=FcsClient.cacheAgeMs(symbol,period);val ageMs=age?:Long.MAX_VALUE
        val freshEnough=ageMs<=90_000L
        val lv=if(freshEnough&&!basis.isNullOrEmpty())AnalysisEngine.chartLevels(period,basis) else null
        val pd=previousDayRange(basis)

        val out=StringBuilder();out.append("CURRENT SETUP\n")
        if(active==null)out.append("➜ SIGNAL: None for $symbol • $period\n") else{
            val sig=active.signal;out.append("➜ SIGNAL: ${sig.direction} • ${active.state} • ${sig.score}/100\n")
            out.append("➜ ENTRY: ${price(sig.entry)}   SL: ${price(sig.sl)}\n")
            out.append("➜ TP1: ${price(sig.tp1)}   TP2: ${price(sig.tp2)}\n")
        }

        out.append("\nMARKET MAP • $period\n")
        if(pd!=null){
            out.append("➜ PREVIOUS DAY HIGH • ${pd.third}: ${price(pd.first)}\n")
            out.append("➜ PREVIOUS DAY LOW • ${pd.third}: ${price(pd.second)}\n")
        }else{
            out.append("➜ PREVIOUS DAY HIGH/LOW: Not available in current FCS history\n")
        }

        // S/R still exists internally for analysis logic; only the Market Map UI
        // rows are replaced by Previous Day High/Low. Preserve OB diagnostics.
        if(!freshEnough){
            out.append("➜ OB MAP: STALE — press ANALYZE for fresh selected-timeframe OB.")
        }else{
            val bull=if(lv?.bullObLow!=null&&lv.bullObHigh!=null)"${price(lv.bullObLow)}–${price(lv.bullObHigh)}" else AnalysisEngine.orderBlockUnavailableReason(basis?:emptyList(),"BUY")
            val bear=if(lv?.bearObLow!=null&&lv.bearObHigh!=null)"${price(lv.bearObLow)}–${price(lv.bearObHigh)}" else AnalysisEngine.orderBlockUnavailableReason(basis?:emptyList(),"SELL")
            out.append("➜ BULL OB: $bull\n")
            out.append("➜ BEAR OB: $bear")
        }
        snapshot.text=styledOutput(out.toString())
    }
'''

s=s[:start]+new_snapshot+s[end:]
p.write_text(s)

p=Path('app/build.gradle.kts')
g=p.read_text();g=re.sub(r'versionCode = \d+','versionCode = 67',g);g=re.sub(r'versionName = "[^"]+"','versionName = "67.0"',g);p.write_text(g)
print('v67 Previous Day High/Low + date Market Map applied')
