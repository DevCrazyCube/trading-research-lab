import sqlite3, hashlib, pickle, os
import numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/tapes.txt','w')
def p(*a): print(*a,file=out); out.flush()

def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

TA='/home/anont/meme/research/b11a/b11a_trade_attribution.sqlite'
c=sqlite3.connect('file:'+TA+'?mode=ro',uri=True)
q="""select mint,slot,txi,oi,ii,blocktime,trader,is_buy,sol_amount,virtual_sol,virtual_token,idl_name
     from trade_attribution where mint is not null and is_buy is not null
     order by mint, slot, txi, oi, ii"""
rows=c.execute(q).fetchall()
c.close()
p('rows fetched',len(rows))

# ---- HOLDOUT GUARD: drop h==0 immediately, never counted or used ----
hcache={}
def hh(m):
    v=hcache.get(m)
    if v is None:
        v=h3(m); hcache[m]=v
    return v

tapes={}
n_drop=0
for r in rows:
    m=r[0]
    hv=hh(m)
    if hv==0:
        n_drop+=1
        continue
    tapes.setdefault(m,[]).append(r)
p('rows kept (h in 1,2)',len(rows)-n_drop)
p('mints kept',len(tapes))
from collections import Counter
p('h split mints',Counter(hh(m) for m in tapes))

# window labels
wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
lab={}
for mint,creator,create_slot,block_time,complete in wl.execute(
        "select mint,creator,create_slot,block_time,complete from window_label"):
    if mint is None: continue
    if hh(mint)==0: continue
    lab[mint]=(creator,create_slot,block_time,complete)
wl.close()
p('labels kept',len(lab))
p('tapes with label',sum(1 for m in tapes if m in lab))

# grad ohlcv
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
grad={}
for mint,n_bars,status,bars_json,first_ts,last_ts in g.execute(
        "select mint,n_bars,status,bars_json,first_ts,last_ts from ohlcv"):
    if hh(mint)==0: continue
    grad[mint]=(n_bars,status,bars_json,first_ts,last_ts)
g.close()
p('grad kept',len(grad))
p('grad overlap with tapes',sum(1 for m in grad if m in tapes))

# build arrays
T={}
tmin=10**18; tmax=0
for m,rs in tapes.items():
    n=len(rs)
    bt=np.array([r[5] for r in rs],dtype=np.int64)
    isb=np.array([r[7] for r in rs],dtype=np.int8)
    sol=np.array([r[8] for r in rs],dtype=np.float64)
    vs=np.array([r[9] for r in rs],dtype=np.float64)
    vt=np.array([r[10] for r in rs],dtype=np.float64)
    tr=[r[6] for r in rs]
    T[m]=dict(bt=bt,isb=isb,sol=sol,vs=vs,vt=vt,tr=tr)
    if n: tmin=min(tmin,bt[0]); tmax=max(tmax,bt[-1])
p('global bt range',tmin,tmax,'span_days',(tmax-tmin)/86400.)
lens=np.array([len(T[m]['bt']) for m in T])
p('trades/mint  n=%d mean=%.1f med=%.0f p90=%.0f max=%d'%(len(lens),lens.mean(),np.median(lens),np.percentile(lens,90),lens.max()))
p('mints with >=20 trades',int((lens>=20).sum()))
p('mints with >=50 trades',int((lens>=50).sum()))

# sanity: price
m0=[m for m in T if len(T[m]['bt'])>50][0]
d=T[m0]
pr=d['vs']/d['vt']
p('sample mint',m0,'first vs',d['vs'][0],'first vt',d['vt'][0],'price0',pr[0],'pricemax',pr.max(),'ret',pr[-1]/pr[0]-1)
p('vs monotone-with-buy check: corr(sign(dvs), isb) =',
  np.corrcoef(np.sign(np.diff(d['vs'])), d['isb'][1:])[0,1])

with open(W+'/tapes.pkl','wb') as f:
    pickle.dump(dict(T=T,lab=lab,grad=grad,hh={m:hh(m) for m in T}),f,protocol=4)
p('saved', os.path.getsize(W+'/tapes.pkl'))
out.close()
