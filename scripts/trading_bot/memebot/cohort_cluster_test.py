"""Board-wallet early-cluster test with placebo (the bar set by the deep-search refuter).
Event: the k-th distinct roster wallet BUYS mint m (tok>0, sol<0) within N hours of the mint's first pair creation.
Outcome: forward return of the pool price from the event bar to +1h/+6h/+24h/+72h, net of 1.14%/side, mint-equal;
plus P(max mcap later >= $500k / $10M). Same statistic on the control roster = placebo. Paper only, no keys."""
import sqlite3,json,time,urllib.request,collections,statistics as st,bisect,sys
UA={'User-Agent':'Mozilla/5.0'}; TOLL_RT=0.0114   # 1.14% ROUND TRIP (direct routing), applied once
def get(u,tries=4):
    for i in range(tries):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read())
        except Exception: time.sleep(2+2*i)
    return None
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"; SOLM="So11111111111111111111111111111111111111112"
def touches(db):
    """first BUY touch per (wallet,mint): meme tokens in AND (USDC out or SOL out) in the same tx. Returns {mint:[ts,...]}"""
    c=sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=60)
    bysig=collections.defaultdict(list)
    for w,sig,ts,m,raw,dec,lam in c.execute("select wallet,sig,ts,mint,raw_delta,decimals,sol_lamports from row order by ts"): bysig[(w,sig)].append((ts,m,raw/10**dec,lam/1e9))
    first={}
    for (w,sig),rs in bysig.items():
        usdc=sum(r[2] for r in rs if r[1]==USDC); sol=rs[0][3]
        for ts,m,tok,_ in rs:
            if m in (USDC,SOLM) or tok<=0: continue
            if usdc<-0.5 or sol<-0.001:
                first.setdefault((w,m),ts)
    per=collections.defaultdict(list)
    for (w,m),ts in first.items(): per[m].append(ts)
    return {m:sorted(v) for m,v in per.items()}
_pc={}
def pair_created(mints):
    out={}
    for i in range(0,len(mints),30):
        chunk=[m for m in mints[i:i+30] if m not in _pc]
        if not chunk: continue
        r=get("https://api.dexscreener.com/tokens/v1/solana/"+",".join(chunk)) or []; time.sleep(0.5)
        for p in r:
            a=p['baseToken']['address']; cr=p.get('pairCreatedAt')
            if cr and (a not in _pc or cr<_pc[a][0]): _pc[a]=(cr/1000,p['pairAddress'],float(p.get('marketCap') or 0)/max(float(p.get('priceUsd') or 1),1e-18))
    return {m:_pc[m] for m in mints if m in _pc}
def bars(pool,since):
    tf='minute' if time.time()-since<3*86400 else 'hour'; out={}; before=int(time.time())
    for _ in range(3):
        o=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/{tf}?aggregate=1&limit=1000&before_timestamp={before}&currency=usd"); time.sleep(2.1)
        b=(o or {}).get('data',{}).get('attributes',{}).get('ohlcv_list') or []
        if not b: break
        for x in b: out[x[0]]=x
        before=min(x[0] for x in b)-1
        if len(b)<1000 or before<since: break
    return sorted(out.values())
def evaluate(per,k,N_h,max_mints=None,label=''):
    events=[]
    for m,ts in per.items():
        if len(ts)>=k: events.append((m,ts[k-1]))
    mints=[m for m,_ in events]; pc=pair_created(mints)
    ev=[(m,t,pc[m]) for m,t in events if m in pc and 0<=t-pc[m][0]<=N_h*3600]
    ev.sort(key=lambda x:x[1])
    if max_mints: ev=ev[:max_mints]
    res=collections.defaultdict(list); hit5=hit10=0; n=0
    for m,t,(cr,pool,supply) in ev:
        b=bars(pool,cr)
        if not b: continue
        ts=[x[0] for x in b]; i=bisect.bisect_right(ts,t)      # first bar STRICTLY after the event
        if i>=len(b): continue
        p0=b[i][1]; n+=1                                        # entry at that bar's OPEN (harness A)
        mx=max(x[2] for x in b[i:])*supply; hit5+=mx>=5e5; hit10+=mx>=1e7
        for h,sec in (('1h',3600),('6h',6*3600),('24h',86400),('72h',3*86400)):
            j=bisect.bisect_left(ts,t+sec)
            res[h].append((b[j][1]/p0)*(1-TOLL_RT)-1 if j<len(b) and ts[j]<=t+sec+max(3600,0.5*sec) else None)
    print(f"{label} k={k} N={N_h}h: events {len(events)} early {len(ev)} priced {n}  P(>=500k) {hit5/max(1,n)*100:.0f}%  P(>=10M) {hit10/max(1,n)*100:.1f}%")
    for h,v in res.items():
        unres=sum(1 for x in v if x is None)
        for drop in (-0.3,-0.5,-1.0):
            vv=[drop if x is None else x for x in v]; vs=sorted(vv)
            print(f"   +{h:3} drop{drop*100:5.0f}%: mean {st.fmean(vv)*100:+7.1f}%  median {vs[len(vs)//2]*100:+7.1f}%  win {sum(x>0 for x in vv)/len(vv)*100:3.0f}%  unresolved {unres}/{len(vv)}")
    return res
if __name__=="__main__":
    cap=int(sys.argv[1]) if len(sys.argv)>1 else None
    board=touches("research/midcap/cohort_history.sqlite")
    try: ctrl=touches("research/midcap/cohort_history_controls.sqlite")
    except Exception: ctrl={}
    print("STATUS: DEVELOPMENT_ONLY_ROSTER_LOOKAHEAD — today's leaderboard replayed on its own past; NOT out-of-sample, NOT a result")
    print(f"board mints {len(board)} | control mints {len(ctrl)}")
    for k,N in ((2,2),(2,24),(3,24)):
        evaluate(board,k,N,cap,'BOARD  ')
        if ctrl: evaluate(ctrl,k,N,cap,'PLACEBO')
