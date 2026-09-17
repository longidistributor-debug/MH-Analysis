from pathlib import Path
import re

# -----------------------------------------------------------------------------
# One-click = at most one HTTP market-history request.
# Previous-day H/L is now memory/disk/current-history derived only. Never issue
# a second daily HTTP request from NEW ANALYZE or RE-EVALUATE.
# -----------------------------------------------------------------------------
f=Path('app/src/main/java/com/mh/analysis/FcsClient.kt')
s=f.read_text()
pattern=re.compile(r'''    /\*\* Previous day high/low is fixed after the day closes, so it is cached by UTC date\. \*/\n    @Synchronized fun previousDayRange\(accessKey:String,symbol:String\):Pair<PreviousDayRange\?,Int>\{.*?\n    \}\n\n    @Synchronized fun history''',re.S)
replacement='''    /**
     * Previous day H/L without another network call.
     * NEW ANALYZE / RE-EVALUATE must spend at most one history API credit.
     * We first use the already-persisted daily value, then derive an exact UTC
     * previous-day range only from a locally cached timeframe that covers the
     * complete previous day. Partial intraday history is deliberately rejected.
     */
    @Synchronized fun previousDayRange(accessKey:String,symbol:String):Pair<PreviousDayRange?,Int>{
        val sym=symbol.uppercase();val todayDate=LocalDate.now(ZoneOffset.UTC);val today=todayDate.toString()
        previousDayCache[sym]?.let{if(it.first==today)return it.second to 0}
        val p=appContext?.getSharedPreferences("mh_previous_day_v33",Context.MODE_PRIVATE)
        val persisted=p?.getString("$sym|$today",null)
        if(!persisted.isNullOrBlank()){
            val j=runCatching{JSONObject(persisted)}.getOrNull()
            if(j!=null){
                val r=PreviousDayRange(j.getDouble("h"),j.getDouble("l"),j.getLong("t"))
                previousDayCache[sym]=today to r
                return r to 0
            }
        }

        val target=todayDate.minusDays(1)
        val start=target.atStartOfDay(ZoneOffset.UTC).toEpochSecond()
        val end=target.plusDays(1).atStartOfDay(ZoneOffset.UTC).toEpochSecond()-1L
        // Prefer a larger cached timeframe when available: fewer candles, same day range.
        val local=periods.sortedByDescending{timeframeSeconds(it)}.mapNotNull{tf->
            cache[cacheKey(sym,tf)]?.candles?.let{tf to it}
        }
        for((tf,data) in local){
            val sec=timeframeSeconds(tf)
            val day=data.filter{
                val t=normalizeTs(it.t)
                t in start..end
            }
            if(day.isEmpty())continue
            val first=day.minOf{normalizeTs(it.t)};val last=day.maxOf{normalizeTs(it.t)}
            // Require near-complete day coverage; never label a partial range as PDH/PDL.
            if(first>start+sec*2L || last<end-sec*2L)continue
            val r=PreviousDayRange(day.maxOf{it.h},day.minOf{it.l},first)
            previousDayCache[sym]=today to r
            p?.edit()?.putString("$sym|$today",JSONObject().put("h",r.high).put("l",r.low).put("t",r.candleTime).toString())?.apply()
            return r to 0
        }
        return null to 0
    }

    @Synchronized fun history'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v75 previousDayRange anchor not found')
f.write_text(s)

# -----------------------------------------------------------------------------
# Clean UI text: no HTML line-break rendering and no Unicode arrow glyph that
# can degrade into visible "\\n"/garbage on some Android fonts. Use actual
# newlines + ASCII arrows; retain green headings with Spannable styling.
# -----------------------------------------------------------------------------
main=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt')
s=main.read_text()

pattern=re.compile(r'''    private fun showSetup\(a:ActiveSignal\?,headline:String,note:String=""\)\{.*?\n    \}\n\n    private fun marketContext''',re.S)
replacement='''    private fun showSetup(a:ActiveSignal?,headline:String,note:String=""){
        if(a==null){signalHeading.text="";renderSignalMap(null,lastMarketMap,headline);status.text="$headline\\n${marketContext()}";showSignalCard(null);return}
        val sig=a.signal
        val arrow=if(sig.direction=="BUY")"BUY ↑" else "SELL ↓"
        signalHeading.setTextColor(Color.rgb(61,220,132))
        signalHeading.text="$arrow • ${sig.timeframe} • ${a.state} • ${sig.score}/100"
        renderSignalMap(a,lastMarketMap,headline)

        val why=sig.reasons.take(3).joinToString("\\n") { "-> $it" }
        val confirmations=sig.reasons.take(8).joinToString("\\n") { "-> $it" }
        val m=lastMarketMap
        val risk=kotlin.math.abs(sig.entry-sig.sl).coerceAtLeast(1e-9)
        val rr1=kotlin.math.abs(sig.tp1-sig.entry)/risk
        val rr2=kotlin.math.abs(sig.tp2-sig.entry)/risk
        val conclusion=buildList<String>{
            add("Signal quality ${sig.score}/100 • Grade ${AdvancedMarketEngine.grade(sig.score)}")
            m?.let{add("Market regime ${it.regime} • ADX ${String.format(Locale.US,"%.1f",it.adx)}")}
            add("Risk/Reward TP1 ${String.format(Locale.US,"%.2f",rr1)}R • TP2 ${String.format(Locale.US,"%.2f",rr2)}R")
            lastAssessment?.decision?.takeIf{it.isNotBlank()}?.let{add(it)}
        }.joinToString("\\n") { "-> $it" }
        val text=buildString{
            append("TRADE PLAN\\n")
            append("“ ENTRY ” : ${price(sig.entry)}\\n")
            append("-> TP1 : ${price(sig.tp1)}   |   TP2 : ${price(sig.tp2)}\\n")
            append("-> SL : ${price(sig.sl)}\\n\\n")
            append("WHY THIS TRADE\\n$why\\n\\n")
            append("WHY STOP LOSS\\n-> ${sig.slReason}\\n\\n")
            append("WHY TP1\\n-> ${sig.tp1Reason}\\n\\n")
            append("WHY TP2\\n-> ${sig.tp2Reason}\\n\\n")
            append("TRADE CONCLUSION\\n$conclusion\\n\\n")
            append("CONFIRMATIONS\\n$confirmations")
            if(note.isNotBlank())append("\\n\\nUPDATE\\n-> $note")
        }
        status.text=greenSections(text,listOf("TRADE PLAN","WHY THIS TRADE","WHY STOP LOSS","WHY TP1","WHY TP2","TRADE CONCLUSION","CONFIRMATIONS","UPDATE"))
        showSignalCard(a)
    }

    private fun marketContext'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v75 showSetup anchor not found')

pattern=re.compile(r'''    private fun escapeHtml\(x:String\)=.*?\n\n    private fun zoneText.*?\n\n    private fun renderSignalMap\(.*?\n    \}\n\n    private fun reevaluateNow''',re.S)
replacement='''    private fun greenSections(text:String,headings:List<String>):CharSequence{
        val sp=android.text.SpannableString(text)
        val green=Color.rgb(61,220,132)
        headings.distinct().forEach{h->
            var from=0
            while(true){
                val i=text.indexOf(h,from);if(i<0)break
                sp.setSpan(android.text.style.ForegroundColorSpan(green),i,i+h.length,android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                sp.setSpan(android.text.style.StyleSpan(Typeface.BOLD),i,i+h.length,android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                from=i+h.length
            }
        }
        return sp
    }

    private fun zoneText(lo:Double?,hi:Double?):String=if(lo==null||hi==null)"-" else "${price(lo)} – ${price(hi)}"

    private fun renderSignalMap(a:ActiveSignal?,m:AdvancedMarketEngine.MarketMap?,label:String=""){
        if(!::signalMapCard.isInitialized)return
        val pd=previousDay
        val top=if(a==null)"NO ACTIVE SIGNAL • $symbol • $period" else {
            val x=a.signal;val ar=if(x.direction=="BUY")"BUY ↑" else "SELL ↓"
            "$ar • ${x.score}/100 • ${AdvancedMarketEngine.grade(x.score)} • ${a.state}"
        }
        val lines=buildList<String>{
            add("Previous Day High : ${pd?.let{price(it.high)}?:"-"}")
            add("Previous Day Low : ${pd?.let{price(it.low)}?:"-"}")
            m?.let{
                add("Bull OB : ${zoneText(it.bullObLow,it.bullObHigh)}")
                add("Bear OB : ${zoneText(it.bearObLow,it.bearObHigh)}")
                add("Regime : ${it.regime} • ADX ${String.format(Locale.US,"%.1f",it.adx)}")
                it.fvgType?.let{ft->add("$ft FVG : ${zoneText(it.fvgLow,it.fvgHigh)} • ${it.fvgFillPct}% filled")}
                it.divergence?.let{d->add("Divergence : $d")}
                if(it.spreadWarning)add("Execution : spread wider than normal")
            }
        }
        val text=buildString{
            append(top)
            if(a!=null){
                val x=a.signal
                append("\\n“ ENTRY ” : ${price(x.entry)}")
                append("\\n-> TP1 : ${price(x.tp1)}   |   TP2 : ${price(x.tp2)}")
                append("\\n-> SL : ${price(x.sl)}")
            }
            append("\\n\\nMARKET MAP")
            lines.forEach{append("\\n-> $it")}
        }
        signalMapCard.text=greenSections(text,listOf(top,"MARKET MAP"))
    }

    private fun reevaluateNow'''
if pattern.search(s):
    s=pattern.sub(lambda m:replacement,s,count=1)
else:
    raise SystemExit('v75 renderSignalMap anchor not found')

# All remaining reason-list arrows use ASCII to avoid glyph/font surprises.
s=s.replace('"→ $it"','"-> $it"').replace('"→ ${escapeHtml(it)}"','"-> ${escapeHtml(it)}"')
s=s.replace('"→ No active','"-> No active').replace('\\n→ Press','\\n-> Press').replace('"→ Refreshing','"-> Refreshing').replace('\\n→ Existing','\\n-> Existing')

# Visible version label after v74.
s=re.sub(r'MS • v\d+ • [^"\\n]+','MS • v75 • ONE-CALL QUALITY ENGINE',s,count=1)
main.write_text(s)

# Version metadata.
build=Path('app/build.gradle.kts')
b=build.read_text();b=re.sub(r'versionCode = \d+','versionCode = 75',b);b=re.sub(r'versionName = "[^"]+"','versionName = "75.0"',b);build.write_text(b)

print('v75 one-call analysis and clean text rendering applied')
