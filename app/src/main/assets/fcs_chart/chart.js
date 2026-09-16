(() => {
  "use strict";

  const SYMBOL = "FX:XAUUSD";
  const WS_URL = "wss://ws-v4.fcsapi.com/ws";
  const TIMEFRAMES = ["1m","5m","15m","30m","1h","2h","4h","1D","1W"];
  const cache = Object.fromEntries(TIMEFRAMES.map(tf => [tf, []]));

  let client = null;
  let currentTf = "15m";
  let apiKey = null;
  let analysis = null;
  let signal = null;
  let viewBars = 80;
  let panBars = 0;
  let dragStartX = null;
  let dragStartPan = 0;
  let pinchStartDistance = 0;
  let pinchStartBars = 80;

  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const emptyState = document.getElementById("emptyState");
  const statusEl = document.getElementById("status");
  const priceEl = document.getElementById("price");
  const fields = {o:document.getElementById("o"),h:document.getElementById("h"),l:document.getElementById("l"),c:document.getElementById("c")};

  function setStatus(text, cls){statusEl.textContent=text;statusEl.className="status "+(cls||"");}
  function normalizeTf(tf){
    const x=String(tf||"").trim();
    const m={"1":"1m","5":"5m","15":"15m","30":"30m","60":"1h","1H":"1h","2H":"2h","4H":"4h","1d":"1D","1w":"1W"};
    const y=m[x]||x;
    return TIMEFRAMES.includes(y)?y:"15m";
  }
  function formatPrice(v){const n=Number(v);return Number.isFinite(n)?n.toFixed(2):"--";}
  function parse(raw){if(!raw)return null;if(typeof raw==="string"){try{return JSON.parse(raw)}catch(_){return null}}return raw;}
  function bridge(name,args){try{if(window.AndroidFcs&&typeof window.AndroidFcs[name]==="function")window.AndroidFcs[name](...args);}catch(_){}}

  function resizeCanvas(){
    const rect=canvas.getBoundingClientRect();const dpr=Math.max(1,window.devicePixelRatio||1);
    canvas.width=Math.max(1,Math.floor(rect.width*dpr));canvas.height=Math.max(1,Math.floor(rect.height*dpr));
    ctx.setTransform(dpr,0,0,dpr,0,0);draw();
  }

  function upsertCandle(tf,p,fromSocket=true){
    tf=normalizeTf(tf);if(!p)return;
    const candle={time:Number(p.t??p.time),open:Number(p.o??p.open),high:Number(p.h??p.high),low:Number(p.l??p.low),close:Number(p.c??p.close),volume:Number(p.v??p.volume??0)};
    if(![candle.time,candle.open,candle.high,candle.low,candle.close].every(Number.isFinite))return;
    const arr=cache[tf]||(cache[tf]=[]);const last=arr[arr.length-1];
    if(last&&last.time===candle.time)arr[arr.length-1]=candle;else{arr.push(candle);arr.sort((a,b)=>a.time-b.time);if(arr.length>500)arr.splice(0,arr.length-500);}
    if(fromSocket)bridge("onCandle",[tf,candle.time,candle.open,candle.high,candle.low,candle.close,candle.volume]);
  }

  window.setHistoricalCandles=function(tf,candles){
    tf=normalizeTf(tf);if(!Array.isArray(candles))return;
    cache[tf]=candles.map(c=>({time:Number(c.time??c.t),open:Number(c.open??c.o),high:Number(c.high??c.h),low:Number(c.low??c.l),close:Number(c.close??c.c),volume:Number(c.volume??c.v??0)}))
      .filter(c=>[c.time,c.open,c.high,c.low,c.close].every(Number.isFinite)).sort((a,b)=>a.time-b.time).slice(-500);
    if(tf===currentTf){panBars=0;draw();}
  };

  function overlayNumbers(){
    const out=[];const add=v=>{v=Number(v);if(Number.isFinite(v))out.push(v)};
    if(analysis){add(analysis.support);add(analysis.resistance);add(analysis.bullObLow);add(analysis.bullObHigh);add(analysis.bearObLow);add(analysis.bearObHigh)}
    if(signal){add(signal.entry);add(signal.sl);add(signal.tp1);add(signal.tp2)}
    return out;
  }

  function visibleCandles(){
    const all=cache[currentTf]||[];if(!all.length)return [];
    const count=Math.max(20,Math.min(240,Math.round(viewBars)));const maxPan=Math.max(0,all.length-count);panBars=Math.max(0,Math.min(maxPan,Math.round(panBars)));
    const end=Math.max(0,all.length-panBars);const start=Math.max(0,end-count);return all.slice(start,end);
  }

  function draw(){
    const rect=canvas.getBoundingClientRect(),w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);
    const candles=visibleCandles();if(!candles.length){emptyState.style.display="flex";return}emptyState.style.display="none";
    const padL=8,padR=64,padT=10,padB=22,cw=Math.max(1,w-padL-padR),ch=Math.max(1,h-padT-padB);
    let min=Math.min(...candles.map(c=>c.low)),max=Math.max(...candles.map(c=>c.high));
    overlayNumbers().forEach(v=>{min=Math.min(min,v);max=Math.max(max,v)});if(max===min){max+=1;min-=1}let span=max-min;max+=span*.055;min-=span*.055;span=max-min;
    const y=price=>padT+(max-price)/span*ch;

    ctx.strokeStyle="#18202a";ctx.fillStyle="#75808d";ctx.lineWidth=1;ctx.font="10px Arial";
    for(let i=0;i<=5;i++){const yy=padT+ch*i/5;ctx.beginPath();ctx.moveTo(padL,yy);ctx.lineTo(w-padR,yy);ctx.stroke();ctx.fillText((max-span*i/5).toFixed(2),w-padR+6,yy+3)}

    function zone(lo,hi,color){lo=Number(lo);hi=Number(hi);if(!Number.isFinite(lo)||!Number.isFinite(hi))return;const a=y(Math.max(lo,hi)),b=y(Math.min(lo,hi));ctx.save();ctx.globalAlpha=.16;ctx.fillStyle=color;ctx.fillRect(padL,Math.min(a,b),cw,Math.max(2,Math.abs(b-a)));ctx.globalAlpha=.65;ctx.strokeStyle=color;ctx.lineWidth=1;ctx.strokeRect(padL,Math.min(a,b),cw,Math.max(2,Math.abs(b-a)));ctx.restore()}
    function line(price,color,label,dash){price=Number(price);if(!Number.isFinite(price))return;const yy=y(price);ctx.save();ctx.strokeStyle=color;ctx.lineWidth=1;ctx.setLineDash(dash?[5,4]:[]);ctx.beginPath();ctx.moveTo(padL,yy);ctx.lineTo(w-padR,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font="bold 9px Arial";ctx.fillText(label+" "+price.toFixed(2),padL+4,Math.max(9,yy-3));ctx.restore()}

    if(analysis){zone(analysis.bullObLow,analysis.bullObHigh,"#3ec9d0");zone(analysis.bearObLow,analysis.bearObHigh,"#ef5350");line(analysis.support,"#42a5f5","S",true);line(analysis.resistance,"#ce93d8","R",true)}

    const step=cw/candles.length,bodyW=Math.max(2,Math.min(10,step*.62));
    candles.forEach((c,i)=>{const x=padL+step*i+step/2,yo=y(c.open),yh=y(c.high),yl=y(c.low),yc=y(c.close),up=c.close>=c.open;ctx.strokeStyle=up?"#36c98f":"#f35b66";ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.15;ctx.beginPath();ctx.moveTo(x,yh);ctx.lineTo(x,yl);ctx.stroke();const top=Math.min(yo,yc),bh=Math.max(1.5,Math.abs(yc-yo));ctx.fillRect(x-bodyW/2,top,bodyW,bh)});

    if(signal){line(signal.entry,"#f2c94c","ENTRY",false);line(signal.sl,"#ff5a67","SL",true);line(signal.tp1,"#3ddc84","TP1",true);line(signal.tp2,"#56d7d1","TP2",true)}

    const last=(cache[currentTf]||[]).slice(-1)[0]||candles[candles.length-1];if(last){const py=y(last.close);ctx.strokeStyle="#9aa6b2";ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(padL,py);ctx.lineTo(w-padR,py);ctx.stroke();ctx.setLineDash([]);priceEl.textContent=formatPrice(last.close);fields.o.textContent=formatPrice(last.open);fields.h.textContent=formatPrice(last.high);fields.l.textContent=formatPrice(last.low);fields.c.textContent=formatPrice(last.close)}
  }

  function handlePrice(data){
    const tf=normalizeTf(String(data.timeframe||currentTf)),p=data.prices||{},mode=String(p.mode||"").toLowerCase();
    if(mode==="candle"||mode==="initial"||(p.o!=null&&p.h!=null&&p.l!=null&&p.c!=null)){upsertCandle(tf,p,true);if(tf===currentTf)draw();}
    else if(mode==="askbid"||p.c!=null){const price=Number(p.c);const t=Number(p.t??p.update??Math.floor(Date.now()/1000));if(Number.isFinite(price)){priceEl.textContent=formatPrice(price);bridge("onPrice",[tf,t,price]);}}
  }

  function subscribeAll(){TIMEFRAMES.forEach(tf=>{try{client.join(SYMBOL,tf)}catch(_){}})}
  function disconnect(){if(client){try{client.disconnect()}catch(_){}client=null}}
  function connect(){
    if(!apiKey){setStatus("API key required","error");return}if(typeof FCSClient==="undefined"){setStatus("FCS library failed","error");return}
    disconnect();try{
      client=new FCSClient(apiKey,WS_URL);client.focusTimeout=0;client.reconnectDelay=3000;client.reconnectlimit=8;
      client.onconnected=()=>{setStatus("LIVE • FX:XAUUSD","connected");subscribeAll()};client.onreconnect=()=>setStatus("Reconnected","connected");client.onclose=()=>setStatus("Disconnected","disconnected");client.onerror=()=>setStatus("Socket reconnecting","reconnecting");
      client.onmessage=data=>{if(!data)return;if(data.type==="price"&&String(data.symbol||"").toUpperCase()===SYMBOL)handlePrice(data);if(data.type==="error")setStatus(data.message||"Market stream error","error")};
      setStatus("Connecting…","reconnecting");client.connect();
    }catch(e){console.error(e);setStatus("Connection failed","error")}
  }

  window.setFcsApiKey=function(key){if(!key||typeof key!=="string"){setStatus("API key required","error");return}const k=key.trim();if(!k)return;if(apiKey===k&&client)return;apiKey=k;connect()};
  window.switchTimeframe=function(tf){currentTf=normalizeTf(tf);panBars=0;document.querySelectorAll("#timeframes button").forEach(b=>b.classList.toggle("active",b.dataset.tf===currentTf));draw()};
  window.setAnalysisLevels=function(raw){analysis=parse(raw);draw()};window.clearAnalysisLevels=function(){analysis=null;draw()};
  window.setSignalCard=function(raw){signal=parse(raw);draw()};window.clearSignalCard=function(){signal=null;draw()};
  window.loadTradingView=function(_symbol,tf){window.switchTimeframe(tf)};
  window.setChartData=function(raw){const d=parse(raw);if(Array.isArray(d))window.setHistoricalCandles(currentTf,d)};window.clearChartData=function(){cache[currentTf]=[];draw()};
  window.updateLivePrice=function(price,ts){const p=Number(price);if(Number.isFinite(p))bridge("onPrice",[currentTf,Number(ts||Math.floor(Date.now()/1000)),p])};

  function dist(a,b){const dx=a.clientX-b.clientX,dy=a.clientY-b.clientY;return Math.sqrt(dx*dx+dy*dy)}
  canvas.addEventListener("touchstart",e=>{if(e.touches.length===2){pinchStartDistance=dist(e.touches[0],e.touches[1]);pinchStartBars=viewBars;dragStartX=null}else if(e.touches.length===1){dragStartX=e.touches[0].clientX;dragStartPan=panBars}},{passive:false});
  canvas.addEventListener("touchmove",e=>{e.preventDefault();if(e.touches.length===2&&pinchStartDistance>0){const d=dist(e.touches[0],e.touches[1]);if(d>0){viewBars=Math.max(20,Math.min(240,pinchStartBars*(pinchStartDistance/d)));draw()}}else if(e.touches.length===1&&dragStartX!=null){const rect=canvas.getBoundingClientRect();const pxPerBar=Math.max(3,(rect.width-72)/Math.max(20,viewBars));panBars=Math.max(0,dragStartPan+Math.round((e.touches[0].clientX-dragStartX)/pxPerBar));draw()}},{passive:false});
  canvas.addEventListener("touchend",()=>{dragStartX=null;pinchStartDistance=0},{passive:true});
  canvas.addEventListener("wheel",e=>{e.preventDefault();viewBars=Math.max(20,Math.min(240,viewBars+(e.deltaY>0?8:-8)));draw()},{passive:false});

  document.querySelectorAll("#timeframes button").forEach(btn=>btn.addEventListener("click",()=>window.switchTimeframe(btn.dataset.tf)));
  window.addEventListener("resize",resizeCanvas);new ResizeObserver(resizeCanvas).observe(canvas.parentElement);resizeCanvas();
})();
