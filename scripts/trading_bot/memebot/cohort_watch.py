"""PROSPECTIVE watcher v2 (after Codex handoff 470) for the frozen 30/30 roster.
Fixes vs v1: receipt clock taken AFTER the transaction is fetched and parsed (availability, not poll start);
cursor never advances past a failed fetch (failures retried; after 5 attempts recorded as permanent and skipped
explicitly); signature pagination until the cursor with an explicit cap flag; first-sight stores the raw
DexScreener response and labels oldest-pair vs largest-pool fields separately; poll order alternates arms and
shuffles wallets. Writes a NEW epoch database; v1 data is retained untouched. Paper only; no keys, no orders."""
import json,sqlite3,time,urllib.request,zlib,os,datetime,random,hashlib
RPC="https://api.mainnet-beta.solana.com"; SOL="So11111111111111111111111111111111111111112"; USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ROSTER=os.environ.get("COHORT_WATCH_ROSTER","research/midcap/fomo_private/cohort_roster_v1_20260909/roster.json"); DB=os.environ.get("COHORT_WATCH_DB","research/midcap/cohort_watch_v2.sqlite")
PAGE=100; CAP=500; MAX_ATTEMPTS=5
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(); err=None
    for i in range(4):
        try:
            r=urllib.request.Request(RPC,data=b,headers={"content-type":"application/json","User-Agent":"Mozilla/5.0"})
            j=json.loads(urllib.request.urlopen(r,timeout=40).read())
            if "error" in j: raise RuntimeError(str(j["error"])[:120])
            return j["result"],None
        except Exception as e: err=str(e)[:160]; time.sleep(1.5*(i+1))
    return None,err
def dex_raw(mint):
    try:
        r=urllib.request.Request(f"https://api.dexscreener.com/tokens/v1/solana/{mint}",headers={"User-Agent":"Mozilla/5.0"})
        return urllib.request.urlopen(r,timeout=20).read()
    except Exception: return None
ro=json.load(open(ROSTER)); roster_sha=hashlib.sha256(open(ROSTER,'rb').read()).hexdigest()
arms={w:"board" for w in ro["rosters"]["board"]}; arms.update({w:"control" for w in ro["rosters"]["controls"]})
db=sqlite3.connect(DB,timeout=60); db.execute("PRAGMA journal_mode=WAL")
db.executescript("""CREATE TABLE IF NOT EXISTS epoch(start_ns INT, roster_sha TEXT, code_sha TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS ev(wallet TEXT, arm TEXT, sig TEXT, ts INT, avail_ns INT, mint TEXT, raw_delta INT, decimals INT, sol_lamports INT, usdc_delta REAL, fee_payer INT, PRIMARY KEY(sig,wallet,mint));
CREATE TABLE IF NOT EXISTS rawtx(sig TEXT PRIMARY KEY, ts INT, zjson BLOB);
CREATE TABLE IF NOT EXISTS firstsight(mint TEXT PRIMARY KEY, seen_ns INT, oldest_pair_created INT, oldest_pair TEXT, largest_pool TEXT, largest_pool_price REAL, largest_pool_mcap REAL, largest_pool_liq REAL, zraw BLOB);
CREATE TABLE IF NOT EXISTS cursor(wallet TEXT PRIMARY KEY, last_sig TEXT, last_ts INT);
CREATE TABLE IF NOT EXISTS pending(wallet TEXT, sig TEXT, ts INT, attempts INT, last_err TEXT, PRIMARY KEY(wallet,sig));
CREATE TABLE IF NOT EXISTS skipped(wallet TEXT, sig TEXT, ts INT, attempts INT, last_err TEXT, at INT);
CREATE TABLE IF NOT EXISTS poll(at INT, order_first TEXT, wallets INT, new_rows INT, errors INT, capped INT, secs REAL);""")
if not db.execute("SELECT 1 FROM epoch").fetchone():
    code_sha=hashlib.sha256(open(__file__,'rb').read()).hexdigest()
    db.execute("INSERT INTO epoch VALUES(?,?,?,?)",(time.time_ns(),roster_sha,code_sha,"v2 epoch: eligible events start here; v1 (15:20 UTC ->) is development-only")); db.commit()
EPOCH=db.execute("SELECT start_ns FROM epoch").fetchone()[0]/1e9
print(f"v2 epoch start {datetime.datetime.fromtimestamp(EPOCH,datetime.UTC).isoformat()} roster {roster_sha[:12]}",flush=True)
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
    return lam,usdc,int(w==payer),{k:v for k,v in agg.items() if k!=USDC and v[0]!=0}
npoll=0
while True:
    t0=time.time(); new=0; errs=0; capped=0
    order=["board","control"] if npoll%2==0 else ["control","board"]
    ws=[w for arm in order for w in sorted([x for x,a in arms.items() if a==arm],key=lambda x:random.random())]
    for w in ws:
        arm=arms[w]; cur=db.execute("SELECT last_sig FROM cursor WHERE wallet=?",(w,)).fetchone()
        if not cur:   # initialize at the newest signature: nothing before the epoch is ever scanned
            sigs,err=rpc("getSignaturesForAddress",[w,{"limit":1}]); time.sleep(0.2)
            if sigs is None: errs+=1; continue
            db.execute("INSERT OR REPLACE INTO cursor VALUES(?,?,?)",(w,sigs[0]["signature"] if sigs else None,sigs[0].get("blockTime") if sigs else None)); db.commit(); continue
        # paginate newest->older until the cursor
        fresh=[]; before=None
        while True:
            sigs,err=rpc("getSignaturesForAddress",[w,{"limit":PAGE,**({"until":cur[0]} if cur[0] else {}),**({"before":before} if before else {})}]); time.sleep(0.2)
            if sigs is None: errs+=1; break
            fresh+=sigs
            if len(sigs)<PAGE: break
            before=sigs[-1]["signature"]
            if len(fresh)>=CAP: capped+=1; break
        if sigs is None: continue
        fresh=[s for s in fresh if s.get("blockTime") and s["blockTime"]*1e9>=EPOCH*1e9 and not s.get("err")]
        # retry pending failures first
        pend=db.execute("SELECT sig,ts,attempts FROM pending WHERE wallet=?",(w,)).fetchall()
        todo=[{"signature":p[0],"blockTime":p[1],"_attempts":p[2]} for p in pend]+[s for s in reversed(fresh)]
        advance=True; newest_ok=None
        for s in todo:
            t,err=rpc("getTransaction",[s["signature"],{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]); time.sleep(0.25)
            if not t or not t.get("meta"):
                att=s.get("_attempts",0)+1; errs+=1
                if att>=MAX_ATTEMPTS:
                    db.execute("DELETE FROM pending WHERE wallet=? AND sig=?",(w,s["signature"])); db.execute("INSERT INTO skipped VALUES(?,?,?,?,?,?)",(w,s["signature"],s["blockTime"],att,err,int(time.time())))
                else:
                    db.execute("INSERT OR REPLACE INTO pending VALUES(?,?,?,?,?)",(w,s["signature"],s["blockTime"],att,err)); advance=False
                continue
            db.execute("DELETE FROM pending WHERE wallet=? AND sig=?",(w,s["signature"]))
            lam,usdc,fp,agg=decode(t,w); avail=time.time_ns()        # availability = after fetch+parse
            db.execute("INSERT OR IGNORE INTO rawtx VALUES(?,?,?)",(s["signature"],s["blockTime"],zlib.compress(json.dumps(t).encode())))
            for mint,(d,dec) in agg.items():
                db.execute("INSERT OR IGNORE INTO ev VALUES(?,?,?,?,?,?,?,?,?,?,?)",(w,arm,s["signature"],s["blockTime"],avail,mint,d,dec,lam,usdc,fp)); new+=1
                if d>0 and not db.execute("SELECT 1 FROM firstsight WHERE mint=?",(mint,)).fetchone():
                    raw=dex_raw(mint); time.sleep(0.3); seen=time.time_ns()
                    oc=op=lp=None; pr=mc=lq=None
                    if raw:
                        try:
                            ps=[p for p in json.loads(raw) if p.get("pairCreatedAt")]
                            if ps:
                                o=min(ps,key=lambda p:p["pairCreatedAt"]); b=max(ps,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0))
                                oc=int(o["pairCreatedAt"]/1000); op=o["pairAddress"]; lp=b["pairAddress"]; pr=float(b.get("priceUsd") or 0); mc=float(b.get("marketCap") or 0); lq=float((b.get("liquidity") or {}).get("usd") or 0)
                        except Exception: pass
                    db.execute("INSERT OR IGNORE INTO firstsight VALUES(?,?,?,?,?,?,?,?,?)",(mint,seen,oc,op,lp,pr,mc,lq,zlib.compress(raw) if raw else None))
            if s in fresh or s.get("_attempts") is None: newest_ok=s if advance else newest_ok
        if advance and fresh: db.execute("INSERT OR REPLACE INTO cursor VALUES(?,?,?)",(w,fresh[0]["signature"],fresh[0]["blockTime"]))
        db.commit()
    npoll+=1
    db.execute("INSERT INTO poll VALUES(?,?,?,?,?,?,?)",(int(time.time()),order[0],len(ws),new,errs,capped,round(time.time()-t0,1))); db.commit()
    print(json.dumps({"poll_utc":datetime.datetime.utcnow().strftime('%H:%M'),"first":order[0],"new_rows":new,"errors":errs,"capped":capped,"secs":round(time.time()-t0)}),flush=True)
    time.sleep(max(20,180-(time.time()-t0)))
