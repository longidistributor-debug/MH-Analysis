(function (global) {
    const isNode = typeof window === 'undefined';
    const WebSocketImpl = isNode ? require('ws') : WebSocket;
    class FCSClient {
        constructor(apiKey,url=null) {
            this.url = url ? url : 'wss://ws-v4.fcsapi.com/ws';
            this.apiKey = apiKey; this.socket = null; this.activeSubscriptions = new Map();
            this.heartbeat = null; this.reconnectDelay = 3000; this.manualClose = false;
            this.isConnected = false; this.showLogs = false; this.onconnected = null;
            this.onclose = null; this.onmessage = null; this.onerror = null; this.onreconnect = null;
            this.countreconnects = 0; this.reconnectlimit = 5; this.isreconnect = false;
            this.focusTimeout = 15; this.visibilityTimeout = null; this.visibilityDisconnectTime = null;
            this.intentionalDisconnect = false;
            if (!isNode && this.focusTimeout > 0) this.initVisibilityHandling();
        }
        connect() {
            if (this.focusTimeout > 0) this.focusTimeout = this.focusTimeout * 60 * 1000;
            if (!this.apiKey) return Promise.reject(new Error('API Key required'));
            return new Promise((resolve, reject) => {
                const wsUrl = `${this.url}?access_key=${this.apiKey}`;
                this.socket = new WebSocketImpl(wsUrl);
                this.socket.onopen = () => { this.manualClose = false; resolve(this); };
                this.socket.onmessage = (event) => {
                    let data; try { data = JSON.parse(isNode ? event.data.toString() : event.data); } catch(e) { return; }
                    if (data.type === 'ping') { this.send({type:'pong',timestamp:Date.now()}); return; }
                    if (data.type === 'welcome') {
                        this.isConnected = true; this.countreconnects = 0; this.intentionalDisconnect = false;
                        this.visibilityDisconnectTime = null; this.rejoinAll(); this.startHeartbeat();
                        if (this.isreconnect && typeof this.onreconnect === 'function') this.onreconnect();
                        if (!this.isreconnect && typeof this.onconnected === 'function') this.onconnected();
                        return;
                    } else if (data.type === 'message' && data.short === 'joined_room') {
                        if (data.symbol && data.timeframe) {
                            const key = `${data.symbol.toUpperCase()}_${data.timeframe}`;
                            this.activeSubscriptions.set(key,{symbol:data.symbol,timeframe:data.timeframe});
                        }
                    }
                    if (typeof this.onmessage === 'function') this.onmessage(data);
                };
                this.socket.onerror = (err) => { if (typeof this.onerror === 'function') this.onerror(err); };
                this.socket.onclose = (event) => {
                    this.stopHeartbeat(); this.isConnected = false; this.socket = null;
                    if (typeof this.onclose === 'function') this.onclose(event);
                    if (!this.manualClose && !this.intentionalDisconnect) {
                        this.countreconnects++; if (this.countreconnects > this.reconnectlimit && this.reconnectlimit > 0) return;
                        this.isreconnect = true; setTimeout(() => this.connect(), this.reconnectDelay);
                    }
                };
            });
        }
        disconnect(){ this.manualClose=true; this.isConnected=false; this.clearVisibilityTimeout(); if(this.socket){this.socket.close();this.socket=null;this.stopHeartbeat();} }
        startHeartbeat(){ if(!this.socket)return; this.stopHeartbeat(); this.heartbeat=setInterval(()=>{ if(this.socket&&this.socket.readyState===WebSocketImpl.OPEN&&isNode)this.socket.ping(); this.send({type:'ping',timestamp:Date.now()}); },25000); }
        stopHeartbeat(){ if(this.heartbeat){clearInterval(this.heartbeat);this.heartbeat=null;} }
        send(data){ if(!this.socket||this.socket.readyState!==WebSocketImpl.OPEN)return false; try{this.socket.send(JSON.stringify(data));return true;}catch(e){return false;} }
        join(symbol,timeframe){ if(!symbol||!timeframe||!symbol.includes(':'))return; this.send({type:'join_symbol',symbol,timeframe}); }
        leave(symbol,timeframe){ if(!symbol||!timeframe)return; const key=`${symbol.toUpperCase()}_${timeframe}`;this.activeSubscriptions.delete(key);this.send({type:'leave_symbol',symbol,timeframe}); }
        removeAll(){this.activeSubscriptions.clear();this.send({type:'remove_all'});}
        rejoinAll(){this.activeSubscriptions.forEach(({symbol,timeframe})=>this.send({type:'join_symbol',symbol,timeframe}));}
        initVisibilityHandling(){ if(typeof document==='undefined')return; document.addEventListener('visibilitychange',()=>{if(document.hidden)this.handleTabHidden();else this.handleTabVisible();}); }
        handleTabHidden(){this.clearVisibilityTimeout();const delay=this.focusTimeout;this.visibilityDisconnectTime=Date.now();this.visibilityTimeout=setTimeout(()=>{if(this.isConnected){this.intentionalDisconnect=true;this.manualClose=true;this.disconnect();this.manualClose=false;}},delay);}
        handleTabVisible(){this.clearVisibilityTimeout();if(this.manualClose)return;if(this.visibilityDisconnectTime){const elapsed=Date.now()-this.visibilityDisconnectTime;if(elapsed<this.focusTimeout)this.visibilityDisconnectTime=null;}if(!this.isConnected&&this.activeSubscriptions.size>0){this.intentionalDisconnect=false;this.visibilityDisconnectTime=null;this.connect();}}
        clearVisibilityTimeout(){if(this.visibilityTimeout){clearTimeout(this.visibilityTimeout);this.visibilityTimeout=null;}}
    }
    if(isNode)module.exports=FCSClient;else global.FCSClient=FCSClient;
})(typeof window!=='undefined'?window:global);
