import sqlite3, hashlib, pickle, json, os
import numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/meta.txt','w')
def p(*a): print(*a,file=out); out.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

Z=np.load(W+'/feats.npz',allow_pickle=True)
mints=list(Z['mints']); mset=set(mints)

# ---- creator priors, computed ONLY over h in (1,2) creates (holdout never read) ----
wl=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
rows=[]
for mint,creator,cs,bt,comp in wl.execute(
      "select mint,creator,create_slot,block_time,complete from window_label order by create_slot"):
    if mint is None or h3(mint)==0: continue
    rows.append((mint,creator,cs,bt,comp))
wl.close()
p('creates kept (h in 1,2)',len(rows))
from collections import defaultdict
seen=defaultdict(lambda:[0,0])
prior={}
for mint,creator,cs,bt,comp in rows:
    a,b=seen[creator]
    prior[mint]=(a,b,(b/a) if a>0 else -1.0)
    seen[creator]=[a+1,b+(1 if comp else 0)]
p('mints with prior',len(prior))
have=[m for m in mints if m in prior]
p('tape mints with prior info',len(have))
pc=np.array([prior[m][0] for m in have])
p('prior_creates dist', np.percentile(pc,[50,75,90,95,99]), 'frac>0', float((pc>0).mean()))

# ---- socials / snapshot metadata ----
snap={}
nline=0
with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        nline+=1
        try: j=json.loads(line)
        except Exception: continue
        m=j.get('mint')
        if not m or m=='_meta': continue
        if h3(m)==0: continue
        if m not in mset: continue
        cur=snap.get(m)
        if cur is None or j.get('ts_ms',0)<cur.get('ts_ms',0):
            snap[m]=j          # keep EARLIEST snapshot (least look-ahead)
p('snapshot lines',nline,'tape mints with snapshot',len(snap))
if snap:
    k=list(snap.values())[0]
    p('snapshot keys',sorted(k.keys()))

# ---- full-history flag ----
d=pickle.load(open(W+'/tapes.pkl','rb'))
T=d['T']
fullhist={m:(float(T[m]['vs'][0])<=30.05e9) for m in mints}
p('full-history fraction',float(np.mean([fullhist[m] for m in mints])))

# ---- grad_ohlcv overlap ----
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
gr={}
for mint,n_bars,status,bars_json in g.execute("select mint,n_bars,status,bars_json from ohlcv"):
    if h3(mint)==0: continue
    if mint not in mset: continue
    gr[mint]=(n_bars,status,bars_json)
g.close()
p('tape mints in grad_ohlcv',len(gr),'with bars',sum(1 for v in gr.values() if v[0]))

M={}
for m in mints:
    pr=prior.get(m,(0,0,-1.0))
    sn=snap.get(m,{})
    M[m]=dict(prior_creates=pr[0],prior_grads=pr[1],prior_gradrate=pr[2],
              fullhist=1 if fullhist[m] else 0,
              has_x=int(bool(sn.get('has_x'))) if sn else -1,
              has_tg=int(bool(sn.get('has_tg'))) if sn else -1,
              has_web=int(bool(sn.get('has_web'))) if sn else -1,
              replies=sn.get('replies',-1) if sn else -1,
              hassnap=1 if sn else 0,
              ingrad=1 if m in gr else 0)
pickle.dump(M,open(W+'/meta.pkl','wb'))
p('saved meta for',len(M))
out.close()
