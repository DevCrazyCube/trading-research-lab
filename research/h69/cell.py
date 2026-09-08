import json,random,statistics as st

LO,HI,HOLD,LOOK = 0.048,0.095,15,5

def med(v):
    v=sorted(v); n=len(v)
    return None if n==0 else (v[n//2] if n%2 else 0.5*(v[n//2-1]+v[n//2]))

def _exit(bars, k0, entry_ts, hold, mode):
    # mode 'time': first REAL bar at/after entry_ts+hold min.  mode 'bars': the 15th REAL bar after entry.
    if mode=='bars':
        return bars[k0+hold-1] if k0+hold-1 < len(bars) else None
    want=entry_ts+60*hold
    for k in bars[k0:]:
        if k[0]>=want: return k
    return None

def cell_trades(bars, lo=LO, hi=HI, hold=HOLD, gap_tol=None, mode='time'):
    """bars: ascending [ts,o,h,l,c,v]. Returns list of (entry_ts, raw_gross_ret or None).
    None = unresolved (no real exit bar). Signal on bar i, ENTER at next REAL bar's open."""
    ts={b[0]:k for k,b in enumerate(bars)}
    out=[]
    for i,b in enumerate(bars):
        t=b[0]
        j=ts.get(t-60*LOOK)
        if j is None: continue                 # need a REAL bar exactly 5 min earlier
        c0,c1=bars[j][4],b[4]
        if c0<=0 or c1<=0: continue
        r=c1/c0-1.0
        if not (lo<=r<=hi): continue
        if i+1>=len(bars): out.append((t,None)); continue
        e=bars[i+1]
        if e[0]<=t: continue                   # never the signal bar itself
        if gap_tol is not None and e[0]-t>gap_tol: out.append((t,None)); continue
        ep=e[1]
        if ep<=0: continue
        # exit: first REAL bar at or after entry_ts + hold minutes
        x=_exit(bars,i+2,e[0],hold,mode)
        out.append((t, (x[1]/ep-1.0) if x is not None else None))
    return out

def rand_trades(bars, n, rnd, hold=HOLD, gap_tol=None, mode='time'):
    """same-mint random-bar control: uniformly random signal bars, identical entry/exit machinery."""
    out=[]
    if len(bars)<3: return out
    for _ in range(n):
        i=rnd.randrange(len(bars)-1)
        t=bars[i][0]; e=bars[i+1]
        if e[0]<=t: continue
        if gap_tol is not None and e[0]-t>gap_tol: out.append((t,None)); continue
        ep=e[1]
        if ep<=0: continue
        x=_exit(bars,i+2,e[0],hold,mode)
        out.append((t,(x[1]/ep-1.0) if x is not None else None))
    return out

def charge(trs, ch, toll):
    return [ (r-toll) if r is not None else ch for _,r in trs ]

def summarize(bymint, ch, toll):
    vals=[]; res=0; tot=0
    for m,trs in bymint.items():
        for _,r in trs:
            tot+=1
            if r is None: vals.append(ch)
            else: vals.append(r-toll); res+=1
    return vals, (100.0*res/tot if tot else 0.0), tot

def boot_diff(bymint_a, bymint_b, ch, toll, draws=2000, seed=11):
    """cluster bootstrap by mint of mean(cell) - mean(control); mints resampled JOINTLY."""
    mints=[m for m in bymint_a if bymint_a[m]]
    A={m:charge(bymint_a[m],ch,toll) for m in mints}
    B={m:charge(bymint_b.get(m,[]),ch,toll) for m in mints}
    rnd=random.Random(seed); out=[]
    for _ in range(draws):
        a=[];b=[]
        for _ in mints:
            m=mints[rnd.randrange(len(mints))]
            a+=A[m]; b+=B[m]
        if a and b: out.append(st.mean(a)-st.mean(b))
    out.sort()
    return out

def boot_mean(bymint, ch, toll, draws=2000, seed=11):
    mints=[m for m in bymint if bymint[m]]
    A={m:charge(bymint[m],ch,toll) for m in mints}
    rnd=random.Random(seed); out=[]
    for _ in range(draws):
        a=[]
        for _ in mints: a+=A[mints[rnd.randrange(len(mints))]]
        if a: out.append(st.mean(a))
    out.sort(); return out

def pct(v,p):
    if not v: return float('nan')
    i=int(round((len(v)-1)*p)); return v[i]
