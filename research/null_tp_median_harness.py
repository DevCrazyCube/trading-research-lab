import sqlite3, json, math, random, statistics as st, sys
random.seed(20260903)
DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
TOLL=0.0114   # round trip, direct routing
def load():
    c=sqlite3.connect(DB)
    out=[]
    for mint,bj in c.execute('select mint,bars_json from ohlcv where status="ok" and n_bars>0'):
        b=json.loads(bj)
        b=sorted(b,key=lambda r:r[0])   # ascending
        # dedupe ts
        seen=set(); bb=[]
        for r in b:
            if r[0] in seen: continue
            seen.add(r[0]); bb.append(r)
        if len(bb)>=3: out.append((mint,bb))
    return out

def gap_stats(data):
    g=[]
    for m,b in data:
        for i in range(1,len(b)): g.append((b[i][0]-b[i-1][0])//60)
    g.sort()
    return len(g), g[len(g)//2], g[int(len(g)*.9)], sum(1 for x in g if x==1)/len(g)

# --- one trade: signal at index i, ENTER at open of bar i+1 (real next bar) ---
# TP overlay: fraction `frac` sold at entry*(1+tp) the first bar in the hold window whose HIGH >= that.
# Remainder held to horizon.
def sim(bars,i,H,tp,frac):
    """returns (resolved, gross_mult_resolved_part, tp_filled_frac, ) or None if not eligible"""
    n=len(bars)
    if i+1>=n: return None
    ts_e=bars[i+1][0]
    if ts_e<=bars[i][0]: return None
    entry=bars[i+1][1]           # OPEN of next real bar
    if entry<=0: return None
    t_tgt=ts_e+H*60
    tgt=entry*(1.0+tp) if tp is not None else None
    filled=0.0
    fill_px=0.0
    exit_px=None
    last_close_le=None
    saw_after=False
    for j in range(i+1,n):
        ts,o,h,l,cl,v=bars[j]
        if ts>t_tgt:
            saw_after=True
            break
        if ts>ts_e and tgt is not None and filled==0.0 and h>=tgt:
            filled=frac; fill_px=tgt
        last_close_le=cl
    else:
        saw_after=False
    resolved = saw_after and last_close_le is not None
    if last_close_le is None: last_close_le=bars[i+1][4]
    return dict(entry=entry, filled=filled, fill_px=fill_px,
                rem_px=last_close_le, resolved=resolved, mint=None)

def ret_of(r,drop):
    """simple NET return of the position, dropout charge `drop` (e.g. -1.0) applied to the
       unresolved remainder only."""
    e=r['entry']; f=r['filled']
    part_tp = f*(r['fill_px']/e)*(1-TOLL) if f>0 else 0.0
    rem=1.0-f
    if r['resolved']:
        part_rem = rem*(r['rem_px']/e)*(1-TOLL)
    else:
        part_rem = rem*(1.0+drop)      # -30/-50/-100% on the stuck remainder
    return part_tp+part_rem-1.0

def cluster_boot(vals_by_mint, B=2000):
    keys=list(vals_by_mint.keys())
    means=[]
    for _ in range(B):
        s=[]
        for _ in range(len(keys)):
            s.extend(vals_by_mint[keys[random.randrange(len(keys))]])
        if s: means.append(sum(s)/len(s))
    means.sort()
    return means[int(.025*len(means))], means[int(.975*len(means))]

def run(data,H,tp,frac,drop,B=2000):
    by={}
    allv=[]; nres=0; ntot=0; ntpfill=0
    for mint,bars in data:
        v=[]
        for i in range(len(bars)-1):
            r=sim(bars,i,H,tp,frac)
            if r is None: continue
            ntot+=1
            if r['resolved']: nres+=1
            if r['filled']>0: ntpfill+=1
            x=ret_of(r,drop)
            v.append(x)
        if v: by[mint]=v; allv.extend(v)
    if not allv: return None
    allv_s=sorted(allv)
    mean=sum(allv)/len(allv)
    med=allv_s[len(allv_s)//2]
    lo,hi=cluster_boot(by,B)
    return dict(H=H,tp=tp,frac=frac,drop=drop,n=len(allv),clusters=len(by),
                mean=mean*100,median=med*100,ci_lo=lo*100,ci_hi=hi*100,
                res=nres/ntot*100 if ntot else 0.0, tpfill=ntpfill/ntot*100 if ntot else 0.0)

# ---- signal-conditioned variant: only enter when prior 5-min return in [lo,hi] ----
def run_signal(data,H,tp,frac,drop,lo,hi,B=1500):
    by={}; allv=[]; nres=0; ntot=0; ntp=0
    for mint,bars in data:
        v=[]
        for i in range(5,len(bars)-1):
            # prior 5-min return: close[i] vs close of the last bar at/ before ts[i]-5min
            t0=bars[i][0]-300
            k=None
            for j in range(i-1,-1,-1):
                if bars[j][0]<=t0: k=j; break
            if k is None: continue
            if bars[k][4]<=0: continue
            pr=bars[i][4]/bars[k][4]-1.0
            if not (lo<=pr<=hi): continue
            r=sim(bars,i,H,tp,frac)
            if r is None: continue
            ntot+=1
            if r['resolved']: nres+=1
            if r['filled']>0: ntp+=1
            v.append(ret_of(r,drop))
        if v: by[mint]=v; allv.extend(v)
    if not allv: return None
    s=sorted(allv); mean=sum(allv)/len(allv); med=s[len(s)//2]
    l,h=cluster_boot(by,B)
    return dict(H=H,tp=tp,frac=frac,drop=drop,n=len(allv),clusters=len(by),
                mean=mean*100,median=med*100,ci_lo=l*100,ci_hi=h*100,
                res=nres/ntot*100,tpfill=ntp/ntot*100)
