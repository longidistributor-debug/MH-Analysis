from pathlib import Path
import re

# v46: make the controlled chart visually light and make displayed S/R come from
# confirmed selected-timeframe swing pivots. Core signal generation/lifecycle is
# intentionally left unchanged.

# -----------------------------------------------------------------------------
# AnalysisEngine.chartLevels: display-only S/R = confirmed pivots / multi-touch.
# -----------------------------------------------------------------------------
p=Path('app/src/main/java/com/mh/analysis/AnalysisEngine.kt')
s=p.read_text()
start=s.index('    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{')
end=s.index('\n\n    private fun validatedOrderBlock',start)
new_chart_levels='''    fun chartLevels(timeframe:String,c:List<Candle>):ChartLevels?{
        if(c.size<30)return null
        val a=atr(c,14).coerceAtLeast(1e-9);val tf=tfMinutes(timeframe);val current=c.last().c
        val look=when{tf<=1->88;tf<=5->76;tf<=10->70;tf<=15->64;tf<=30->56;tf<=60->50;tf<=120->46;tf<=300->42;tf<=1440->38;tf<=10080->34;else->30}
        val raw=c.takeLast(min(look,c.size))
        // Last two candles are deliberately excluded: a swing is not confirmed
        // until candles exist on its right side. This prevents a current wick from
        // being mislabeled as support/resistance.
        val w=if(raw.size>8)raw.dropLast(2) else raw
        val lows=mutableListOf<Pair<Double,Int>>();val highs=mutableListOf<Pair<Double,Int>>()
        for(i in 2 until w.size-2){
            val x=w[i]
            if(x.l<=w[i-1].l&&x.l<=w[i-2].l&&x.l<=w[i+1].l&&x.l<=w[i+2].l)lows+=x.l to i
            if(x.h>=w[i-1].h&&x.h>=w[i-2].h&&x.h>=w[i+1].h&&x.h>=w[i+2].h)highs+=x.h to i
        }
        val tolerance=max(a*.16,abs(current)*0.000025)
        fun clusters(src:List<Pair<Double,Int>>):List<Triple<Double,Int,Int>>{
            if(src.isEmpty())return emptyList()
            val groups=mutableListOf<MutableList<Pair<Double,Int>>>()
            for(p in src.sortedBy{it.first}){
                val g=groups.lastOrNull();val center=g?.map{it.first}?.average()
                if(g!=null&&center!=null&&abs(center-p.first)<=tolerance)g+=p else groups+=mutableListOf(p)
            }
            return groups.map{g->Triple(g.map{it.first}.average(),g.size,g.maxOf{it.second})}
        }
        val lowClusters=clusters(lows);val highClusters=clusters(highs)
        val supportCandidates=lowClusters.filter{it.first<=current+a*.04}
        val resistanceCandidates=highClusters.filter{it.first>=current-a*.04}
        // Prefer the nearest confirmed multi-touch level. A single-pivot fallback
        // is allowed only if no repeated level exists.
        var support=supportCandidates.filter{it.second>=2}.maxByOrNull{it.first}?.first
            ?:supportCandidates.maxByOrNull{it.first}?.first
        var resistance=resistanceCandidates.filter{it.second>=2}.minByOrNull{it.first}?.first
            ?:resistanceCandidates.minByOrNull{it.first}?.first
        val local=w.takeLast(min(24,w.size))
        if(support==null||support>current+a*.08)support=local.minOfOrNull{it.l}?:current
        if(resistance==null||resistance<current-a*.08)resistance=local.maxOfOrNull{it.h}?:current
        if(support!!>=resistance!!){support=local.minOfOrNull{it.l}?:current;resistance=local.maxOfOrNull{it.h}?:current}
        val bo=validatedOrderBlock(c,"BUY",a);val so=validatedOrderBlock(c,"SELL",a)
        return ChartLevels(support!!,resistance!!,bo?.let{min(it.o,it.c)},bo?.let{max(it.o,it.c)},so?.let{min(it.o,it.c)},so?.let{max(it.o,it.c)})
    }'''
s=s[:start]+new_chart_levels+s[end:]
p.write_text(s)

# -----------------------------------------------------------------------------
# Lightweight chart: thin lines, tiny tags, soft OB zones, no giant axis labels.
# -----------------------------------------------------------------------------
p=Path('app/src/main/assets/tradingview_live.html')
html=r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#111722;font-family:Arial,sans-serif}
#root{position:absolute;inset:0;background:#111722}
#chart{position:absolute;inset:0;z-index:1}
#decor{position:absolute;inset:0;z-index:4;pointer-events:none;overflow:hidden}
#head{position:absolute;left:10px;top:8px;z-index:5;color:#eef2f7;font-size:10px;font-weight:700;pointer-events:none;text-shadow:0 1px 2px #000}
#head small{display:block;color:#8490a3;font-size:7px;font-weight:500;margin-top:1px}
#empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:3;color:#7f8999;font-size:10px;pointer-events:none;text-align:center;padding:24px}
.zone{position:absolute;left:0;right:70px;border-top:1px solid transparent;border-bottom:1px solid transparent;opacity:.11}
.tag{position:absolute;min-width:13px;height:13px;line-height:13px;padding:0 3px;border-radius:3px;color:#fff;font-size:7px;font-weight:700;text-align:center;box-shadow:0 1px 2px rgba(0,0,0,.45);transform:translateY(-50%)}
.tag.left{left:5px}.tag.right{right:72px}
</style>
</head>
<body>
<div id="root">
  <div id="chart"></div>
  <div id="decor"></div>
  <div id="head">XAUUSD • 15m<small>selected-timeframe structure</small></div>
  <div id="empty">Press ANALYZE to load selected-timeframe candles.</div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
<script>
let chart=null,candles=null,volume=null,currentSymbol='XAUUSD',currentPeriod='15m',data=[],analysis=null,signal=null,lines=[];
const C={bg:'#111722',text:'#aeb7c5',grid:'rgba(197,203,211,.065)',up:'#26a69a',down:'#ef5350',support:'#42a5f5',res:'#b783d7',bull:'#26a69a',bear:'#ef5350',entry:'#e6bd47',sl:'#f05b69',tp1:'#3acb7b',tp2:'#55c7c8'};
function init(){
 if(!window.LightweightCharts){document.getElementById('empty').textContent='Chart library unavailable. Check internet connection.';return}
 const host=document.getElementById('chart');
 chart=LightweightCharts.createChart(host,{width:host.clientWidth,height:host.clientHeight,layout:{background:{type:'solid',color:C.bg},textColor:C.text},grid:{vertLines:{color:C.grid},horzLines:{color:C.grid}},rightPriceScale:{borderColor:'#29313d',scaleMargins:{top:.07,bottom:.17}},timeScale:{borderColor:'#29313d',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:8,minBarSpacing:3},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
 candles=chart.addCandlestickSeries({upColor:C.up,downColor:C.down,borderUpColor:C.up,borderDownColor:C.down,wickUpColor:C.up,wickDownColor:C.down,priceLineVisible:true,lastValueVisible:true});
 volume=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'',lastValueVisible:false,priceLineVisible:false});
 volume.priceScale().applyOptions({scaleMargins:{top:.88,bottom:0}});
 new ResizeObserver(()=>chart.applyOptions({width:host.clientWidth,height:host.clientHeight})).observe(host);
 requestAnimationFrame(decorLoop);
}
function psec(p){const x=String(p||'15m');if(x==='1M')return 2592000;const m={'1m':60,'5m':300,'10m':600,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,'5h':18000,'1d':86400,'1w':604800};return m[x]||900}
function bucket(ts){const n=Math.floor(Number(ts)||Date.now()/1000),s=psec(currentPeriod);return Math.floor(n/s)*s}
function setHead(){document.getElementById('head').innerHTML=currentSymbol+' • '+currentPeriod+'<small>selected-timeframe structure</small>'}
function loadTradingView(symbol,period){currentSymbol=String(symbol||'XAUUSD').toUpperCase();currentPeriod=String(period||'15m');setHead();clearChartData();analysis=null;signal=null;redrawLevels()}
function parse(raw){if(!raw)return null;if(typeof raw==='string'){try{return JSON.parse(raw)}catch(e){return null}}return raw}
function setChartData(raw){
 const x=parse(raw);if(!Array.isArray(x)||!candles)return;
 const map=new Map();x.forEach(d=>{const t=Math.floor(Number(d.time));if(Number.isFinite(t))map.set(t,{time:t,open:Number(d.open),high:Number(d.high),low:Number(d.low),close:Number(d.close),volume:Number(d.volume)||0})});
 data=[...map.values()].sort((a,b)=>a.time-b.time);if(!data.length)return clearChartData();
 candles.setData(data.map(d=>({time:d.time,open:d.open,high:d.high,low:d.low,close:d.close})));
 volume.setData(data.map(d=>({time:d.time,value:d.volume,color:d.close>=d.open?'rgba(38,166,154,.28)':'rgba(239,83,80,.28)'})));
 document.getElementById('empty').style.display='none';chart.timeScale().fitContent();redrawLevels();
}
function clearChartData(){data=[];if(candles)candles.setData([]);if(volume)volume.setData([]);document.getElementById('empty').style.display='flex';clearPriceLines();document.getElementById('decor').innerHTML=''}
function updateLivePrice(price,ts){
 const p=Number(price);if(!Number.isFinite(p)||!candles||!data.length)return;const t=bucket(ts);let d=data[data.length-1];
 if(d.time===t){d={...d,high:Math.max(d.high,p),low:Math.min(d.low,p),close:p};data[data.length-1]=d}else if(t>d.time){d={time:t,open:d.close,high:Math.max(d.close,p),low:Math.min(d.close,p),close:p,volume:0};data.push(d)}else return;
 candles.update({time:d.time,open:d.open,high:d.high,low:d.low,close:d.close});volume.update({time:d.time,value:d.volume||0,color:d.close>=d.open?'rgba(38,166,154,.28)':'rgba(239,83,80,.28)'});
}
function clearPriceLines(){if(!candles)return;lines.forEach(l=>{try{candles.removePriceLine(l)}catch(e){}});lines=[]}
function line(price,color,width=1,style=2){const p=Number(price);if(!candles||!Number.isFinite(p))return;try{lines.push(candles.createPriceLine({price:p,color:color,lineWidth:width,lineStyle:style,axisLabelVisible:false,title:''}))}catch(e){}}
function redrawLevels(){
 clearPriceLines();if(!candles||!data.length)return;
 if(analysis){line(analysis.support,C.support,1,LightweightCharts.LineStyle.Dashed);line(analysis.resistance,C.res,1,LightweightCharts.LineStyle.Dashed)}
 if(signal){line(signal.entry,C.entry,1,LightweightCharts.LineStyle.Solid);line(signal.sl,C.sl,1,LightweightCharts.LineStyle.Dashed);line(signal.tp1,C.tp1,1,LightweightCharts.LineStyle.Dashed);line(signal.tp2,C.tp2,1,LightweightCharts.LineStyle.Dashed)}
}
function setAnalysisLevels(raw){analysis=parse(raw);redrawLevels()}
function clearAnalysisLevels(){analysis=null;redrawLevels()}
function setSignalCard(raw){signal=parse(raw);redrawLevels()}
function clearSignalCard(){signal=null;redrawLevels()}
function coord(v){if(!candles)return null;const y=candles.priceToCoordinate(Number(v));return Number.isFinite(y)?y:null}
function addTag(parent,text,price,side,color){const y=coord(price);if(y===null||y<18||y>document.body.clientHeight-18)return;const e=document.createElement('div');e.className='tag '+side;e.textContent=text;e.style.top=y+'px';e.style.background=color;parent.appendChild(e)}
function addZone(parent,low,high,color){const a=coord(low),b=coord(high);if(a===null||b===null)return;const top=Math.min(a,b),bot=Math.max(a,b);if(bot<0||top>document.body.clientHeight)return;const z=document.createElement('div');z.className='zone';z.style.top=Math.max(0,top)+'px';z.style.height=Math.max(2,Math.min(document.body.clientHeight,bot)-Math.max(0,top))+'px';z.style.background=color;z.style.borderColor=color;parent.appendChild(z)}
function drawDecor(){
 const d=document.getElementById('decor');if(!d||!candles||!data.length)return;d.innerHTML='';
 if(analysis){
   if(Number.isFinite(Number(analysis.bullObLow))&&Number.isFinite(Number(analysis.bullObHigh)))addZone(d,analysis.bullObLow,analysis.bullObHigh,C.bull);
   if(Number.isFinite(Number(analysis.bearObLow))&&Number.isFinite(Number(analysis.bearObHigh)))addZone(d,analysis.bearObLow,analysis.bearObHigh,C.bear);
   addTag(d,'S',analysis.support,'left',C.support);addTag(d,'R',analysis.resistance,'left',C.res);
 }
 if(signal){addTag(d,'E',signal.entry,'right',C.entry);addTag(d,'SL',signal.sl,'right',C.sl);addTag(d,'T1',signal.tp1,'right',C.tp1);addTag(d,'T2',signal.tp2,'right',C.tp2)}
}
function decorLoop(){drawDecor();requestAnimationFrame(decorLoop)}
init();setHead();
</script>
</body>
</html>'''
p.write_text(html)

# Version metadata.
p=Path('app/build.gradle.kts');s=p.read_text();s=re.sub(r'versionCode = \d+','versionCode = 46',s);s=re.sub(r'versionName = "[^"]+"','versionName = "46.0"',s);p.write_text(s)
print('v46 light chart + confirmed pivot S/R applied')
