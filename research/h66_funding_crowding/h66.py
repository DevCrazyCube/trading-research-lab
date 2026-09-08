import csv, collections, math, json, sys
import numpy as np

PANEL='/home/anont/meme/research/data/t23_cache/panel/'
DAY=86400000

# ---- memecoin universe (curated; base ticker after stripping 1000x prefixes / quote) ----
MEME_BASES = set("""
DOGE SHIB PEPE FLOKI BONK WIF BOME BRETT POPCAT PNUT ACT NEIRO NEIROETH MEW MYRO SLERF PONKE
CHILLGUY MOODENG GOAT FARTCOIN MEME MEMEFI TURBO BABYDOGE HIPPO MUBARAK BROCCOLI714 BROCCOLIF3B
BANANA BANANAS31 TRUMP MELANIA JELLYJELLY PIPPIN ZEREBRO VINE TST USELESS GIGGLE PENGU SPX
TOSHI DEGEN CATI HMSTR WEN MOG BOB CAT CHEEMS WHY RATS SATS BTTC BTT XEC LUNC PEOPLE DOGS
SWARMS AI16Z GRIFFAIN BILL KOMA SIREN TUT BIRB DOOD PUMP SPORTFUN AIXBT
""".split())

def base_of(sym):
    s=sym
    for q in ('USDT','USDC','BUSD','USD1'):
        if s.endswith(q): s=s[:-len(q)]; break
    for p in ('1000000','1M','1000'):
        if s.startswith(p) and len(s)>len(p): s=s[len(p):]; break
    return s

# ---- load funding, aggregate to per-8h-equivalent daily rate ----
fund=collections.defaultdict(dict)   # sym -> day -> sum rate
with open(PANEL+'funding.csv') as f:
    r=csv.reader(f); next(r)
    for row in r:
        d=(int(row[1])//DAY)*DAY
        fund[row[0]][d]=fund[row[0]].get(d,0.0)+float(row[3])

px=collections.defaultdict(dict)
with open(PANEL+'perp_daily.csv') as f:
    r=csv.reader(f); next(r)
    for row in r:
        try: c=float(row[2])
        except: continue
        if c>0: px[row[0]][int(row[1])]=(c,float(row[3]))

def run(symbols, side, pctl, absmin, Hs, label, min_hist=90, trail=30, minqv=0.0, gap=None):
    trades=[]
    for sym in symbols:
        if sym not in fund or sym not in px: continue
        days=sorted(set(fund[sym]) & set(px[sym]))
        if len(days)<min_hist+trail+max(Hs)+2: continue
        pdays=sorted(px[sym])
        pidx={d:i for i,d in enumerate(pdays)}
        f8={d:fund[sym][d]/3.0 for d in days}   # per-8h equivalent
        arr=[f8[d] for d in days]
        tr=[]
        for i in range(len(days)):
            if i<trail-1: tr.append(None)
            else: tr.append(sum(arr[i-trail+1:i+1])/trail)
        hist=[]
        last=-10**18
        for i,d in enumerate(days):
            v=tr[i]
            if v is None: continue
            hist.append(v)
            if len(hist)<min_hist: continue
            thr=np.percentile(hist,pctl)     # expanding, uses only data <= t
            hit = (v>=thr and v>=absmin) if side=='short' else (v<=thr and v<=-absmin)
            if not hit: continue
            if gap is not None and (d-last)<gap*DAY: continue
            # entry at NEXT real price bar strictly after d
            j=pidx.get(d)
            if j is None or j+1>=len(pdays): continue
            ed=pdays[j+1]
            if ed-d>3*DAY: continue          # next real bar must be near
            ep,eqv=px[sym][ed]
            if eqv<minqv: continue
            last=d
            rec={'sym':sym,'sig_day':d,'entry_day':ed,'entry':ep,'f8':v,'thr':float(thr)}
            for H in Hs:
                k=j+1+H
                if k<len(pdays) and pdays[k]-ed<=(H+3)*DAY:
                    xp=px[sym][pdays[k]][0]
                    rec['r%d'%H]= (ep-xp)/ep if side=='short' else (xp-ep)/ep
                else:
                    rec['r%d'%H]=None
            trades.append(rec)
    return trades

def boot(vals, clusters, nb=4000, seed=7):
    rng=np.random.default_rng(seed)
    byc=collections.defaultdict(list)
    for v,c in zip(vals,clusters): byc[c].append(v)
    keys=list(byc); K=len(keys)
    if K<2: return (float('nan'),float('nan'))
    sums=np.array([sum(byc[k]) for k in keys],float)
    cnts=np.array([len(byc[k]) for k in keys],float)
    pick=rng.integers(0,K,(nb,K))
    m=sums[pick].sum(1)/cnts[pick].sum(1)
    return float(np.percentile(m,2.5)), float(np.percentile(m,97.5))

def summarize(trades,H,fee,drop_charge,tag):
    vals=[];cl=[];res=0;tot=0
    for t in trades:
        tot+=1
        r=t['r%d'%H]
        if r is None:
            if drop_charge is None: continue
            v=drop_charge
        else:
            res+=1
            v=max(r,-1.0)-fee
        vals.append(v); cl.append(t['sym'])
    if not vals: return None
    lo,hi=boot(vals,cl)
    return dict(tag=tag,H=H,n=len(vals),clusters=len(set(cl)),
                mean=100*float(np.mean(vals)),median=100*float(np.median(vals)),
                ci_lo=100*lo,ci_hi=100*hi,resolution=100*res/tot if tot else 0.0,
                winrate=100*float(np.mean([v>0 for v in vals])))
