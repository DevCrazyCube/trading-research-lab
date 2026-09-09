"""Follower-wave watcher (FOLLOWER_WAVE_PREREGISTRATION.md). Websocket logsSubscribe on the frozen 30/30 roster;
records every roster fill with receipt clocks; schedules a +20 min pool-trades/minute-bars fetch per BUY. Paper only."""
import json,sqlite3,time,urllib.request,zlib,threading,queue,datetime,os
import websocket
WSS="wss://api.mainnet-beta.solana.com"; RPC="https://api.mainnet-beta.solana.com"
ROSTER="research/midcap/fomo_private/cohort_roster_v1_20260909/roster.json"; DB="research/midcap/follower_wave.sqlite"
SOL="So11111111111111111111111111111111111111112"; USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"; UA={"User-Agent":"Mozilla/5.0"}
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for i in range(4):
        try:
            j=json.loads(urllib.request.urlopen(urllib.request.Request(RPC,data=b,headers={"content-type":"application/json",**UA}),timeout=40).read())
            if "error" in j: raise RuntimeError(str(j["error"])[:100])
            return j["result"]
        except Exception: time.sleep(1.5*(i+1))
    return None
def get(u):
    try: return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25).read()
    except Exception: return None
ro=json.load(open(ROSTER)); arms={w:"board" for w in ro["rosters"]["board"]}; arms.update({w:"control" for w in ro["rosters"]["controls"]})
db=sqlite3.connect(DB,timeout=60,check_same_thread=False); db.execute("PRAGMA journal_mode=WAL"); lock=threading.Lock()
db.executescript("""CREATE TABLE IF NOT EXISTS notif2(sig TEXT, wallet TEXT, arm TEXT, slot INT, recv_ns INT, err TEXT, processed INT DEFAULT 0, PRIMARY KEY(sig,wallet));
CREATE TABLE IF NOT EXISTS ev(sig TEXT, wallet TEXT, arm TEXT, mint TEXT, blocktime INT, avail_ns INT, raw_delta INT, decimals INT, sol_lamports INT, usdc_delta REAL, PRIMARY KEY(sig,wallet,mint));
CREATE TABLE IF NOT EXISTS rawtx(sig TEXT PRIMARY KEY, zjson BLOB);
CREATE TABLE IF NOT EXISTS followup(sig TEXT, mint TEXT, due INT, done INT, pool TEXT, ztrades BLOB, zbars BLOB, zdex BLOB, fetched_ns INT, attempts INT DEFAULT 0, PRIMARY KEY(sig,mint));
CREATE TABLE IF NOT EXISTS conn(at INT, event TEXT, detail TEXT);""")
q=queue.Queue()
def log(ev,detail=""):
    with lock: db.execute("INSERT INTO conn VALUES(?,?,?)",(int(time.time()),ev,detail)); db.commit()
    print(json.dumps({"utc":datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S'),"event":ev,"detail":detail[:120]}),flush=True)
def decode(t,w):
    m=t["meta"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in t["transaction"]["message"]["accountKeys"]]
    payer=keys[0]; i=keys.index(w) if w in keys else None
    lam=(m["postBalances"][i]-m["preBalances"][i]) if i is not None else 0
    if w==payer: lam+=m.get("fee",0)
    agg={}
    for side,sign in (("preTokenBalances",-1),("postTokenBalances",1)):
        for b_ in m.get(side) or []:
            if b_.get("owner")!=w: continue
            ua=b_["uiTokenAmount"]; a=agg.setdefault(b_["mint"],[0,int(ua.get("decimals") or 0)]); a[0]+=sign*int(ua.get("amount") or 0)
    lam+=agg.pop(SOL,[0,9])[0]; usdc=agg.get(USDC,[0,6])[0]/1e6
    return lam,usdc,{k:v for k,v in agg.items() if k!=USDC and v[0]!=0}
def worker():
    while True:
        sig,w,slot,recv=q.get()
        t=None
        for _ in range(6):
            t=rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
            if t and t.get("meta"): break
            time.sleep(2)
        if not t or not t.get("meta"):
            with lock: db.execute("UPDATE notif2 SET err='tx_unavailable',processed=1 WHERE sig=? AND wallet=?",(sig,w)); db.commit()
            continue
        if t["meta"].get("err") is not None:
            with lock: db.execute("UPDATE notif2 SET processed=1 WHERE sig=? AND wallet=?",(sig,w)); db.commit()
            continue
        lam,usdc,agg=decode(t,w); avail=time.time_ns()
        with lock:
            db.execute("INSERT OR IGNORE INTO rawtx VALUES(?,?)",(sig,zlib.compress(json.dumps(t).encode())))
            for mint,(d,dec) in agg.items():
                db.execute("INSERT OR IGNORE INTO ev VALUES(?,?,?,?,?,?,?,?,?,?)",(sig,w,arms[w],mint,t.get("blockTime"),avail,d,dec,lam,usdc))
                if d>0 and (usdc<=-1.0 or lam<=-1_000_000):
                    db.execute("INSERT OR IGNORE INTO followup VALUES(?,?,?,?,?,?,?,?,?)",(sig,mint,int(time.time())+1200,0,None,None,None,None,None))
            db.execute("UPDATE notif2 SET processed=1 WHERE sig=? AND wallet=?",(sig,w)); db.commit()
        log("fill",f"{arms[w]} {w[:6]} {len(agg)} mints")
def followups():
    while True:
        time.sleep(30)
        with lock: rows=db.execute("SELECT sig,mint FROM followup WHERE done=0 AND due<=?",(int(time.time()),)).fetchall()
        for sig,mint in rows:
            dex=get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}"); time.sleep(0.6); pool=None
            try:
                ps=[p for p in json.loads(dex) if p.get("pairAddress")]; pool=max(ps,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0))["pairAddress"] if ps else None
            except Exception: pool=None
            tr=bars=None
            if pool:
                tr=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/trades?trade_volume_in_usd_greater_than=0"); time.sleep(2.2)
                bars=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute?aggregate=1&limit=120&currency=usd"); time.sleep(2.2)
            with lock:
                att=(db.execute("SELECT COALESCE(attempts,0) FROM followup WHERE sig=? AND mint=?",(sig,mint)).fetchone() or (0,))[0]
                if tr is None and att<3:      # rate-limited or unindexed: retry in 10 min, up to 3 times
                    db.execute("UPDATE followup SET due=?,attempts=? WHERE sig=? AND mint=?",(int(time.time())+600,att+1,sig,mint)); db.commit(); continue
                db.execute("UPDATE followup SET done=1,pool=?,ztrades=?,zbars=?,zdex=?,fetched_ns=?,attempts=? WHERE sig=? AND mint=?",(pool,zlib.compress(tr) if tr else None,zlib.compress(bars) if bars else None,zlib.compress(dex) if dex else None,time.time_ns(),att+1,sig,mint)); db.commit()
            log("followup",f"{mint[:8]} pool {str(pool)[:8]} trades {'ok' if tr else 'none'}")
with lock:
    if db.execute("SELECT name FROM sqlite_master WHERE name='notif'").fetchone():
        db.execute("INSERT OR IGNORE INTO notif2 SELECT sig,wallet,arm,slot,recv_ns,err,1 FROM notif"); db.commit()
    for sig,w,slot,recv in db.execute("SELECT sig,wallet,slot,recv_ns FROM notif2 WHERE processed=0 AND err IS NULL"): q.put((sig,w,slot,recv))
    log("requeued",f"{q.qsize()} unprocessed notifications")
threading.Thread(target=worker,daemon=True).start(); threading.Thread(target=followups,daemon=True).start()
subs={}
def on_message(ws,msg):
    d=json.loads(msg)
    if "result" in d and "id" in d: subs[d["id"]]=d["result"]; return
    if d.get("method")!="logsNotification": return
    r=d["params"]["result"]; sub=d["params"]["subscription"]; w=next((wl for wl,sid in subs_w.items() if subs.get(sid)==sub),None)
    if not w or r["value"].get("err") is not None: return
    sig=r["value"]["signature"]; recv=time.time_ns()
    with lock:
        cur=db.execute("INSERT OR IGNORE INTO notif2 VALUES(?,?,?,?,?,?,0)",(sig,w,arms[w],r["context"]["slot"],recv,None)); db.commit()
        new=cur.rowcount
    if new: q.put((sig,w,r["context"]["slot"],recv))
subs_w={}
def on_open(ws):
    for i,w in enumerate(arms,1):
        ws.send(json.dumps({"jsonrpc":"2.0","id":i,"method":"logsSubscribe","params":[{"mentions":[w]},{"commitment":"confirmed"}]})); subs_w[w]=i
    log("subscribed",f"{len(arms)} wallets")
def on_error(ws,e): log("ws_error",str(e))
def on_close(ws,a,b): log("ws_close",f"{a} {b}")
while True:
    ws=websocket.WebSocketApp(WSS,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
    ws.run_forever(ping_interval=20,ping_timeout=10)
    log("reconnect","5s"); subs.clear(); subs_w.clear(); time.sleep(5)
