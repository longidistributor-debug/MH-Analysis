from pathlib import Path

p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
if 'fun reEvaluateSignal(' not in s:
    anchor='''    fun isHighVolatility'''
    if anchor not in s: raise SystemExit('v41 fix insertion anchor not found')
    fn='''    /** Manual re-evaluation of an already-issued signal.
     * Time/candle count alone never invalidates a setup. The original thesis is
     * checked first, then the complete current confluence engine is run again.
     */
    fun reEvaluateSignal(original:Signal,c:List<Candle>):ReEvaluation{
        if(c.size<100)return ReEvaluation("WEAKENING","Not enough fresh selected-timeframe history to confirm the original setup. The signal is not auto-expired by time alone.")
        val check=setupCheck(original,c)
        if(!check.valid)return ReEvaluation("EXPIRED",check.reason)
        val fresh=analyze(original.symbol,original.timeframe,c)
        if(fresh==null){
            return ReEvaluation("WEAKENING","The original thesis is not structurally broken, but the complete confluence engine does not currently have enough fresh alignment for a new confirmation. ${check.reason}")
        }
        val dominance=kotlin.math.abs(fresh.bullScore-fresh.bearScore)
        if(fresh.direction!=original.direction){
            val strongFlip=fresh.score>=maxOf(72,original.score-2)&&dominance>=10
            return if(strongFlip){
                ReEvaluation("EXPIRED","The original ${original.direction} setup is no longer the best market thesis. The full engine now confirms a materially stronger ${fresh.direction} setup (${fresh.score}/100, directional separation $dominance). Press ANALYZE to create the new signal.",fresh)
            }else{
                ReEvaluation("WEAKENING","Opposite-direction evidence is developing, but it is not strong enough to fully invalidate the original setup yet. ${check.reason}",fresh)
            }
        }
        val same=sameSetup(original,fresh)
        val acceptable=fresh.score>=maxOf(52,original.score-10)
        return if(same||acceptable){
            ReEvaluation("STILL VALID","The original ${original.direction} thesis remains aligned with the current full-engine view. Current confirmation is ${fresh.score}/100. ${check.reason}",fresh)
        }else{
            ReEvaluation("WEAKENING","Direction still agrees with the original ${original.direction} setup, but present confluence has weakened (${fresh.score}/100 versus original ${original.score}/100). ${check.reason}",fresh)
        }
    }

'''
    s=s.replace(anchor,fn+anchor,1)
p.write_text(s)
print('v41 re-evaluation function restored')
