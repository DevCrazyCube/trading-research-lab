import sqlite3, json, hashlib, statistics, random, sys, math
from collections import Counter

DB='file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro'

def load(hset):
    c=sqlite3.connect(DB,uri=True)
    out=[]
    for mint,bj,st in c.execute("select mint,bars_json,status from ohlcv"):
        h=int(hashlib.md5(mint.encode()).hexdigest(),16)%3
        if h not in hset: continue
        if not bj: continue
        try: b=json.loads(bj)
        except Exception: continue
        if not b or len(b)<25: continue
        b=sorted(b,key=lambda x:x[0])
        out.append((mint,b))
    c.close()
    return out

# ---------- signal ----------
def signals(bars, rvol_max=0.05, not_min=300.0, W=20):
    """rvol20 = vol[i] / mean(vol[i-W:i]) ; notional20 = sum(vol[i-W:i]).
    Both windows are the W bars STRICTLY BEFORE bar i (no lookahead)."""
    sig=[]
    n=len(bars)
    vols=[x[5] for x in bars]
    run=sum(vols[0:W])
    for i in range(W, n-1):   # need a next bar to enter on
        if i>W: run += vols[i-1]-vols[i-1-W]
        notional20=run
        if notional20<=0: continue
        rvol=vols[i]/(notional20/W)
        if rvol<=rvol_max and notional20>=not_min:
            sig.append(i)
    return sig

# ---------- position simulation ----------
def simulate(bars, j, hold_min=45, stop_mult=0.88, tp_mult=1.20, scale_frac=0.5):
    """Enter at OPEN of bar j. Returns (exit_index, gross_factor_resolved, dropout_frac, resolved_bool)
    gross_factor_resolved = sum over resolved legs of frac*exit_px/entry."""
    ts,op,hi,lo,cl,vol = 0,1,2,3,4,5
    entry=bars[j][op]
    if entry<=0: return None
    stop=stop_mult*entry; tp=tp_mult*entry
    texit=bars[j][ts]+hold_min*60
    rem=1.0
    acc=0.0
    half_done=False
    n=len(bars)
    for k in range(j,n):
        b=bars[k]
        # time exit fires at the OPEN of the bar
        if b[ts]>=texit:
            acc += rem*b[op]/entry
            return (k, acc, 0.0, True)
        o=b[op]
        # gap-through stop at the open
        if o<=stop and not (k==j):
            acc += rem*o/entry
            return (k, acc, 0.0, True)
        hit_stop = b[lo]<=stop
        hit_tp   = (not half_done) and b[hi]>=tp
        if hit_stop and hit_tp:
            # conservative: assume stop first, whole remainder out
            acc += rem*stop/entry
            return (k, acc, 0.0, True)
        if hit_stop:
            acc += rem*stop/entry
            return (k, acc, 0.0, True)
        if hit_tp:
            f=min(scale_frac, rem)
            acc += f*tp/entry
            rem-=f
            half_done=True
            if rem<=1e-12:
                return (k, acc, 0.0, True)
    return (n-1, acc, rem, False)

def run_trades(bars, sig, **kw):
    trades=[]
    busy_until=-1
    for i in sig:
        j=i+1
        if j>=len(bars): continue
        if j<=busy_until: continue
        r=simulate(bars,j,**kw)
        if r is None: continue
        k,acc,drop,res=r
        busy_until=k
        trades.append((acc,drop,res))
    return trades

def net_ret(acc, drop, toll, dropcharge):
    f = acc + drop*(1.0+dropcharge)
    return f*(1.0-toll)-1.0

# ---------- aggregation ----------
def aggregate(per_mint, toll, dropcharge):
    """per_mint: dict mint -> list of (acc,drop,res)"""
    mint_means=[]; alltr=[]; res_n=0; tot_n=0
    for m,tr in per_mint.items():
        if not tr: continue
        rs=[net_ret(a,d,toll,dropcharge) for a,d,r in tr]
        mint_means.append(statistics.mean(rs))
        alltr.extend(rs)
        for a,d,r in tr:
            tot_n+=1
            if r: res_n+=1
    return mint_means, alltr, res_n, tot_n

def boot_ci(mint_means, iters=20000, seed=12345, lo=2.5, hi=97.5):
    rnd=random.Random(seed)
    k=len(mint_means)
    if k<2: return (float('nan'),float('nan'),float('nan'))
    means=[]
    for _ in range(iters):
        s=0.0
        for _ in range(k): s+=mint_means[rnd.randrange(k)]
        means.append(s/k)
    means.sort()
    def pc(p):
        idx=p/100.0*(len(means)-1)
        f=int(idx); c=min(f+1,len(means)-1); w=idx-f
        return means[f]*(1-w)+means[c]*w
    pgt0 = sum(1 for x in means if x<=0)/len(means)   # bootstrap p for mean>0
    return pc(lo), pc(hi), pgt0
