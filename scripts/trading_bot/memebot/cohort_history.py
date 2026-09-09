"""On-chain trade history of a wallet roster (per-owner balance deltas; free public RPC). v2 after Codex audit
(COHORT_EVIDENCE_AUDIT_20260909): fee credited only to the fee payer (accountKeys[0]); token deltas summed in RAW
units across all of an owner's accounts for a mint; raw transaction JSON retained (zlib) for offline replay; RPC
failures recorded, never silently skipped; history bounds and caps recorded per wallet.
Read-only, resumable. HISTORY OF TODAY'S LEADERBOARD IS DEVELOPMENT DATA (roster lookahead) - never a result."""
import json,sqlite3,time,urllib.request,sys,os,zlib
RPC="https://api.mainnet-beta.solana.com"; CAP=1500; DAYS=14
SOL="So11111111111111111111111111111111111111112"
DB=os.environ.get("COHORT_DB","research/midcap/cohort_history.sqlite")
ROSTER=os.environ.get("COHORT_ROSTER","research/midcap/leaderboard_7d_20260909.json")
def rpc(m,p):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(); err=None
    for i in range(6):
        try:
            r=urllib.request.Request(RPC,data=b,headers={"content-type":"application/json","User-Agent":"Mozilla/5.0"})
            j=json.loads(urllib.request.urlopen(r,timeout=45).read())
            if "error" in j: raise RuntimeError(str(j["error"])[:120])
            return j["result"],None
        except Exception as e: err=str(e)[:160]; time.sleep(2*(i+1))
    return None,err
db=sqlite3.connect(DB,timeout=60); db.execute("PRAGMA journal_mode=WAL")
db.executescript("""CREATE TABLE IF NOT EXISTS row(wallet TEXT, sig TEXT, ts INT, mint TEXT, raw_delta INT, decimals INT, sol_lamports INT, fee_payer INT, PRIMARY KEY(sig,wallet,mint));
CREATE TABLE IF NOT EXISTS rawtx(sig TEXT PRIMARY KEY, ts INT, zjson BLOB);
CREATE TABLE IF NOT EXISTS fail(wallet TEXT, sig TEXT, kind TEXT, err TEXT, at INT);
CREATE TABLE IF NOT EXISTS done(wallet TEXT PRIMARY KEY, n_sigs INT, n_rows INT, n_fail INT, oldest INT, newest INT, cap INT, since INT, capped INT, finished_at INT);""")
L=json.load(open(ROSTER))["traders"]
wallets=[(e.get("rank"),e.get("handle"),e["wallets"]["solana"]) for e in L if e.get("wallets",{}).get("solana")]
SINCE=int(time.time()-DAYS*86400)
have={r[0] for r in db.execute("SELECT wallet FROM done")}
for rank,handle,w in wallets:
    if w in have: continue
    sigs=[];before=None;capped=0
    while True:
        b,err=rpc("getSignaturesForAddress",[w,{"limit":1000,**({"before":before} if before else {})}]); time.sleep(0.35)
        if b is None: db.execute("INSERT INTO fail VALUES(?,?,?,?,?)",(w,None,"sigs",err,int(time.time()))); break
        if not b: break
        sigs+=b; before=b[-1]["signature"]
        if len(b)<1000 or (b[-1].get("blockTime") or 0)<SINCE: break
        if len(sigs)>=CAP: capped=1; break
    sigs=[s for s in sigs if s.get("blockTime") and s["blockTime"]>=SINCE and not s.get("err")][:CAP]
    n=0;nf=0
    for s in sigs:
        t,err=rpc("getTransaction",[s["signature"],{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]); time.sleep(0.3)
        if not t or not t.get("meta"):
            db.execute("INSERT INTO fail VALUES(?,?,?,?,?)",(w,s["signature"],"tx",err or "null",int(time.time()))); nf+=1; continue
        db.execute("INSERT OR IGNORE INTO rawtx VALUES(?,?,?)",(s["signature"],s["blockTime"],zlib.compress(json.dumps(t).encode())))
        m=t["meta"]; keys=[k["pubkey"] if isinstance(k,dict) else k for k in t["transaction"]["message"]["accountKeys"]]
        payer=keys[0]; i=keys.index(w) if w in keys else None
        lam=(m["postBalances"][i]-m["preBalances"][i]) if i is not None else 0
        if w==payer: lam+=m.get("fee",0)              # fee is not consideration; add back ONLY for the payer
        agg={}
        for side,sign in (("preTokenBalances",-1),("postTokenBalances",1)):
            for b_ in m.get(side) or []:
                if b_.get("owner")!=w: continue
                mint=b_["mint"]; ua=b_["uiTokenAmount"]; amt=int(ua.get("amount") or 0); dec=int(ua.get("decimals") or 0)
                a=agg.setdefault(mint,[0,dec]); a[0]+=sign*amt
        wsol=agg.pop(SOL,[0,9])[0]; lam+=wsol
        for mint,(d,dec) in agg.items():
            if d!=0:
                db.execute("INSERT OR IGNORE INTO row VALUES(?,?,?,?,?,?,?,?)",(w,s["signature"],s["blockTime"],mint,d,dec,lam,int(w==payer))); n+=1
        if n%50==0: db.commit()
    db.execute("INSERT OR REPLACE INTO done VALUES(?,?,?,?,?,?,?,?,?,?)",(w,len(sigs),n,nf,min((s["blockTime"] for s in sigs),default=None),max((s["blockTime"] for s in sigs),default=None),CAP,SINCE,capped,int(time.time()))); db.commit()
    print(f"rank {str(rank):>4} {str(handle)[:14]:14} sigs {len(sigs):4d} rows {n:4d} fail {nf:3d} capped {capped}",flush=True)
print("ALL DONE",flush=True)
