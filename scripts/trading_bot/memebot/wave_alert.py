"""Telegram alerts for the owner from the follower-wave watcher: a board-roster leader BUY on-chain (within seconds of the
websocket notification), then the +5 min and +15 min wave delta (new distinct buyers / buy volume vs the 15 min before the
fill). Read-only decision support; no orders. The owner's own wallet is excluded from wave counts."""
import json,sqlite3,time,urllib.request,urllib.parse,os,datetime,zlib,fcntl
_lock=open("research/midcap/wave_alert.lock","w")
try: fcntl.flock(_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except OSError: raise SystemExit("another wave_alert instance holds the lock")
DB="research/midcap/follower_wave.sqlite"; STATE="research/midcap/wave_alert_state.json"
OWNER="3kcHjvyKT7SvmJXTcUobZzbPkhtLo9waeUiXgzLhzJSZ"; UA={"User-Agent":"Mozilla/5.0"}
env={l.split("=",1)[0].replace("export ","").strip():l.split("=",1)[1].strip().strip('"').strip("'") for l in open(".env") if "=" in l and not l.startswith("#")}
TOK=env["TELEGRAM_BOT_TOKEN"]; CHAT=env["TELEGRAM_CHAT_ID"]
L=json.load(open("research/midcap/leaderboard_7d_20260909.json"))["traders"]
who={e["wallets"]["solana"]:(e["rank"],e["handle"],e.get("followers")) for e in L if e.get("wallets",{}).get("solana")}
def tg(text):
    try:
        d=urllib.parse.urlencode({"chat_id":CHAT,"text":text,"disable_web_page_preview":"true"}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOK}/sendMessage",data=d),timeout=20).read()
    except Exception as e: print("telegram error",str(e)[:100],flush=True)
def get(u):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25).read())
    except Exception: return None
def dex(mint):
    ps=get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}") or []
    ps=[p for p in ps if p.get("pairCreatedAt")]
    if not ps: return None
    o=min(ps,key=lambda p:p["pairCreatedAt"]); b=max(ps,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0))
    return dict(sym=b["baseToken"]["symbol"],age_h=(time.time()-o["pairCreatedAt"]/1000)/3600,mcap=float(b.get("marketCap") or 0),liq=float((b.get("liquidity") or {}).get("usd") or 0),pool=b["pairAddress"],dex=b.get("dexId"))
def txsnap(mint):
    ps=get(f"https://api.dexscreener.com/tokens/v1/solana/{mint}") or []
    ps=[p for p in ps if p.get("pairCreatedAt")]
    if not ps: return None
    b=max(ps,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0)); t=b.get("txns") or {}
    return dict(px=float(b.get("priceUsd") or 0),mcap=float(b.get("marketCap") or 0),m5b=(t.get("m5") or {}).get("buys",0),m5s=(t.get("m5") or {}).get("sells",0),h1b=(t.get("h1") or {}).get("buys",0),h1s=(t.get("h1") or {}).get("sells",0))
def wave(pool,t_fill,leader):
    tr=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/trades?trade_volume_in_usd_greater_than=0")
    rows=(tr or {}).get("data") or []
    bef=set();aft=set();vb=va=0.0
    for r in rows:
        a=r.get("attributes",{}); ts=datetime.datetime.fromisoformat(a["block_timestamp"].replace("Z","+00:00")).timestamp()
        if a.get("kind")!="buy": continue
        w=a.get("tx_from_address"); 
        if w in (OWNER,leader): continue
        v=float(a.get("volume_in_usd") or 0)
        if t_fill-900<=ts<t_fill: bef.add(w); vb+=v
        elif t_fill<ts<=t_fill+900: aft.add(w); va+=v
    return len(bef),vb,len(aft),va,len(rows)
state=json.load(open(STATE)) if os.path.exists(STATE) else {"seen":[],"followups":[]}
recent={}   # (wallet,mint) -> [first_ts, n_buys, total_usd, msg_sent]
AGG_WINDOW=600; MIN_PREWATCH_SELL=10000; BIG_OLD_MCAP=5_000_000; OLD_AGE_H=48
seen=set(state["seen"]); fol=state["followups"]
tg("wave_alert online: leader fills from the frozen board roster will be posted here, then +5/+15 min wave deltas. Decision support only.")
print("wave_alert started",flush=True)
while True:
    c=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=30)
    rows=c.execute("SELECT sig,wallet,mint,blocktime,avail_ns,usdc_delta,sol_lamports,raw_delta FROM ev WHERE arm='board' AND ((raw_delta>0 AND (usdc_delta<=-1.0 OR sol_lamports<=-1000000)) OR (raw_delta<0 AND (usdc_delta>=1.0 OR sol_lamports>=1000000))) ORDER BY avail_ns").fetchall()
    for sig,w,mint,bt,av,usdc,lam,raw in rows:
        key=sig+mint
        if key in seen: continue
        seen.add(key); rank,handle,fol_n=who.get(w,("?","?",None))
        if raw<0:
            hist=c.execute("SELECT usdc_delta,sol_lamports,raw_delta FROM ev WHERE wallet=? AND mint=? AND blocktime<=?",(w,mint,bt)).fetchall()
            spent=sum((-u if u and u<0 else 0)+(-l/1e9*103 if l and l<0 and not (u and u<0) else 0) for u,l,r in hist)
            got=sum((u if u and u>0 else 0)+(l/1e9*103 if l and l>0 and not (u and u>0) else 0) for u,l,r in hist)
            left=sum(r for _,_,r in hist)
            sell_usd=(usdc if usdc and usdc>=1 else (lam/1e9*103 if lam and lam>0 else 0))
            if spent<=0 and sell_usd<MIN_PREWATCH_SELL: print(f"(silenced pre-watch sell {handle} ${sell_usd:,.0f} {mint[:8]})",flush=True); continue
            d=dex(mint); time.sleep(0.5)
            msg=(f"LEADER SELL  rank {rank} @{handle}\n{('$%.0f USDC'%usdc) if usdc and usdc>=1 else ('%.2f SOL'%(lam/1e9))} out of {d['sym'] if d else mint[:8]}  mint {mint}\n"
                 + (f"this mint since watch started: spent ~${spent:,.0f}, received ~${got:,.0f} ({'+' if got>=spent else ''}{got-spent:,.0f}); tokens left {left:,.0f}"+(" -> FLAT" if left==0 else "") if spent>0 else "position was opened BEFORE the watcher started: cost basis unknown"))
            tg(msg); print(msg.replace("\n"," | "),flush=True); continue
        d=dex(mint); time.sleep(0.5)
        usd_in=(-usdc if usdc and usdc<=-1 else (-lam/1e9*103 if lam and lam<0 else 0))
        k2=(w,mint); r=recent.get(k2)
        if r and time.time()-r[0]<=AGG_WINDOW:
            r[1]+=1; r[2]+=usd_in; print(f"(aggregated: {handle} +${usd_in:,.0f} into {mint[:8]}, {r[1]} buys ${r[2]:,.0f} in window)",flush=True); continue
        recent[k2]=[time.time(),1,usd_in,True]
        if d and d['age_h']>OLD_AGE_H and d['mcap']>BIG_OLD_MCAP:
            tg(f"(old/large) rank {rank} @{handle} ${usd_in:,.0f} into {d['sym']} — mcap ${d['mcap']:,.0f}, age {d['age_h']/24:.0f}d; not a launch, no wave tracking"); continue
        size=f"${-usdc:,.0f} USDC" if usdc and usdc<=-1 else f"{-lam/1e9:.2f} SOL"
        lag=(time.time()-bt) if bt else None
        msg=(f"LEADER BUY  rank {rank} @{handle} ({(fol_n or 0):,} followers)\n{size} into {d['sym'] if d else mint[:8]}  mint {mint}\n"
             + (f"mcap ${d['mcap']:,.0f}  liq ${d['liq']:,.0f}  age {d['age_h']:.1f}h  dex {d['dex']}\n" if d else "pair: not on DexScreener yet (pre-pool / curve)\n")
             + f"seen {lag:.0f}s after fill" if lag is not None else "")
        tg(msg); print(msg.replace("\n"," | "),flush=True)
        snap=txsnap(mint); time.sleep(0.3)
        fol.append({"key":key,"mint":mint,"pool":d["pool"] if d else None,"t":bt,"leader":w,"handle":handle,"sym":d["sym"] if d else mint[:8],"due":[bt+300,bt+900],"done":[],"snap0":snap})
    c.close(); now=time.time()
    for f in fol:
        for i,due in enumerate(f["due"]):
            if i in f["done"] or now<due: continue
            if not f["pool"]:
                d=dex(f["mint"]); f["pool"]=d["pool"] if d else None; time.sleep(0.5)
            if f["pool"]:
                nb,vb,na,va,n=wave(f["pool"],f["t"],f["leader"]); time.sleep(2.2)
                mult=(va/vb) if vb>0 else float('inf') if va>0 else 0
                s1=txsnap(f["mint"]); s0=f.get("snap0")
                pxc=((s1["px"]/s0["px"]-1)*100) if (s0 and s1 and s0.get("px")) else None
                agg=recent.get((f['leader'],f['mint'])); extra=(f" | leader added: {agg[1]} buys ${agg[2]:,.0f} total" if agg and agg[1]>1 else "")
                tg(f"WAVE +{'5' if i==0 else '15'}m  {f['sym']} (after @{f['handle']}){extra}\ntrades-sample: buyers before/after {nb} -> {na}, buy-vol ${vb:,.0f} -> ${va:,.0f} (x{mult:.1f}) [{n} sampled{'; sample too short for before-window' if n>=300 else ''}]\n"
                   + (f"dexscreener 5-min buys/sells at alert {s0['m5b']}/{s0['m5s']} -> now {s1['m5b']}/{s1['m5s']}   price since alert {pxc:+.0f}%   mcap ${s1['mcap']:,.0f}" if (s0 and s1 and pxc is not None) else "dexscreener snapshot unavailable"))
            else: tg(f"WAVE +{'5' if i==0 else '15'}m {f['sym']}: no pool visible yet")
            f["done"].append(i)
    fol[:]=[f for f in fol if len(f["done"])<2]
    json.dump({"seen":list(seen)[-5000:],"followups":fol},open(STATE,"w"))
    time.sleep(10)
