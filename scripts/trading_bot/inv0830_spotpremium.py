#!/usr/bin/env python3
"""INVENT 2026-08-30 03:00 — spot-BTC ETF closing premium vs 24/7 instant spot, next-open hedged.
Pre-registered in research/trading_bot/INVENT_2026-08-30_0300_spotpremium_PREREG.md (sha f87fe7f6...).
Pure python. Held-out is printed/stored ONLY if every design gate passes."""
import json, csv, math, random, datetime as dt, statistics as st
ETF='research/data/exo0823_cache/IBIT_1Day_2024-01-01_2026-08-20_sip_all.json'
BTC='research/data/inv0830_cache/BTCUSDT_30m.csv'
OUT='research/trading_bot/INVENT_2026-08-30_0300_spotpremium.json'
DESIGN=(dt.date(2024,2,9),dt.date(2025,8,31)); HELD=(dt.date(2025,9,1),dt.date(2026,8,19))
FLOOR=9.0; TBAR=2.5; NWBAR=2.0; PBAR=0.01; THR=10.0

def nth_sunday(y,m,n):
    d=dt.date(y,m,1); d+=dt.timedelta(days=(6-d.weekday())%7); return d+dt.timedelta(days=7*(n-1))
def edt(d):  # US DST: 2nd Sunday March .. 1st Sunday November
    return nth_sunday(d.year,3,2)<=d<nth_sunday(d.year,11,1)
def utc_ms(d,h,mi):
    off=4 if edt(d) else 5
    return int(dt.datetime(d.year,d.month,d.day,tzinfo=dt.timezone.utc).timestamp()*1000)+((h+off)*60+mi)*60000

bars=json.load(open(ETF))['bars']
etf={dt.date.fromisoformat(b['t'][:10]):(b['o'],b['c']) for b in bars}
btc={}
for r in csv.DictReader(open(BTC)): btc[int(r['ms'])]=float(r['o'])
sess=sorted(d for d in etf if utc_ms(d,16,0) in btc and utc_ms(d,9,30) in btc)
p={d:math.log(etf[d][1]/btc[utc_ms(d,16,0)]) for d in sess}
prem={}
for i,d in enumerate(sess):
    if i>=20: prem[d]=(p[d]-st.median(p[x] for x in sess[i-20:i]))*1e4
def hedged(i):  # next-session open->close hedged return, bp, for signal at sess[i]
    n=sess[i+1]; o,c=etf[n]; return 1e4*(math.log(c/o)-math.log(btc[utc_ms(n,16,0)]/btc[utc_ms(n,9,30)]))
def ownprint(i):
    d,n=sess[i],sess[i+1]; return 1e4*(math.log(etf[n][1]/etf[d][1])-math.log(btc[utc_ms(n,16,0)]/btc[utc_ms(d,16,0)]))
def sgn(x): return -1.0 if x>0 else (1.0 if x<0 else 0.0)
def nw_t(x,L=5):
    n=len(x); m=st.fmean(x); e=[v-m for v in x]; g0=sum(v*v for v in e)/n; s=g0
    for l in range(1,L+1): s+=2*(1-l/(L+1))*sum(e[i]*e[i-l] for i in range(l,n))/n
    return m/math.sqrt(s/n) if s>0 else float('nan')
def stats(x,seed=20260830):
    n=len(x); m=st.fmean(x); sd=st.stdev(x); t=m/(sd/math.sqrt(n)); rnd=random.Random(seed)
    ge=sum(1 for _ in range(2000) if st.fmean(v*rnd.choice((-1,1)) for v in x)>=m)
    return dict(n=n,mean_bp=round(m,2),sd_bp=round(sd,1),t=round(t,2),nw5_t=round(nw_t(x),2),signflip_p=round(ge/2000,4))
def series(win,formula,shift=0):
    lo,hi=win; xs=[]
    for i,d in enumerate(sess[:-1]):
        if not (lo<=d<=hi): continue
        sd_=sess[i-shift] if i-shift>=0 else None
        if sd_ is None or sd_ not in prem: continue
        pr=prem[sd_]
        if formula=='F2' and abs(pr)<=THR: continue
        xs.append(sgn(pr)*hedged(i))
    return xs
def gates(s,shifted):
    g=dict(G1_floor=s['mean_bp']>=FLOOR,G2_t=s['t']>=TBAR and s['nw5_t']>=NWBAR,G3_placebo=s['signflip_p']<PBAR,
           G4_shift_not_pass=not (shifted['mean_bp']>=FLOOR and shifted['t']>=TBAR))
    g['PASS']=all(g.values()); return g
out={'prereg_sha256':'f87fe7f6528d51a295a9987ba96ea9420120905b27ff1230cbb8fc49200a43bf','sessions':len(sess),
     'first_session':str(sess[0]),'last_session':str(sess[-1]),'design':{},'held_out':{}}
# D1 object size (design window only)
pd=[prem[d] for d in sess if DESIGN[0]<=d<=DESIGN[1] and d in prem]
rho=sum((a-st.fmean(pd))*(b-st.fmean(pd)) for a,b in zip(pd,pd[1:]))/sum((a-st.fmean(pd))**2 for a in pd)
out['design']['D1_prem']=dict(n=len(pd),sd_bp=round(st.stdev(pd),1),mean_abs_bp=round(st.fmean(abs(v) for v in pd),1),rho1=round(rho,3),
                              frac_abs_gt_10bp=round(sum(1 for v in pd if abs(v)>THR)/len(pd),3))
d0=[sgn(prem[sess[i]])*ownprint(i) for i in range(len(sess)-1) if sess[i] in prem and DESIGN[0]<=sess[i]<=DESIGN[1]]
out['design']['D0_ownprint_F1']=stats(d0)
for f in ('F1','F2'):
    s=stats(series(DESIGN,f)); sh=stats(series(DESIGN,f,shift=5)); g=gates(s,sh)
    out['design'][f]=dict(stats=s,shifted5=sh,gates=g)
    if g['PASS']:
        out['held_out'][f]=stats(series(HELD,f))
    else:
        out['held_out'][f]='SEALED (design gate failed; never computed)'
json.dump(out,open(OUT,'w'),indent=1)
print(json.dumps(out,indent=1))
