import pickle,collections
import numpy as np
D=pickle.load(open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/panel.pkl','rb'))
recs=D['recs']; rng=np.random.default_rng(4242)
buckets=collections.defaultdict(list)
for m,ts,r,tag in recs: buckets[ts//900].append(r)
BKR=[v for k,v in buckets.items() if len(v)>=6]
print('buckets %d  sizes min/med/max %d/%d/%d'%(len(BKR),min(map(len,BKR)),
      int(np.median([len(v) for v in BKR])),max(map(len,BKR))))
NPOOL=4000; POOLS={}
def pools(k,toll,drop):
    key=(k,toll,drop)
    if key in POOLS: return POOLS[key]
    out=np.empty((len(BKR),NPOOL))
    for i,v in enumerate(BKR):
        a=np.array([drop if r is None else r for r in v]); a=(1+a)*(1-toll)-1
        n=len(a); kk=min(k,n)
        ky=rng.random((NPOOL,n)); idx=np.argpartition(ky,kk-1,axis=1)[:,:kk]
        out[i]=a[idx].sum(1)
    POOLS[key]=out; return out
def sim(frac,k,cycles,paths,toll,drop,gas,W0=60.0,fixed=None):
    P=pools(k,toll,drop); W=np.full(paths,W0); alive=np.ones(paths,bool)
    for t in range(cycles):
        S=P[rng.integers(0,len(BKR),paths),rng.integers(0,NPOOL,paths)]
        stake=(W*frac/k) if fixed is None else np.minimum(fixed,W/k)
        dead=(stake<0.50)|(~alive); stake=np.where(dead,0,stake)
        W=np.where(dead,W,np.maximum(0,W+stake*S-k*gas)); alive=alive&~dead
    return W
POL=[('F  FLAT    dep0.40 N=5  $4.80/tkt',0.40,5,None),
     ('B  BARBELL dep0.10 N=2  $3.00/tkt',0.10,2,None),
     ('B2 BARBELL fixed $3 x2 no-compound',None,2,3.0),
     ('B3 BARBELL dep0.10 N=1  $6.00/tkt',0.10,1,None),
     ('B4 ULTRA   dep0.05 N=1  $3.00/tkt',0.05,1,None)]
PATHS=20000
import sys
for gas in (0.20,0.02):
  for toll,drop in ((0.0114,-1.00),(0.030,-1.00)):
    for cycles in (100,500):
        print('\n== gas $%.2f/pos | toll %.2f%%RT | dropout %.0f%% | %d x15m cycles | %dk paths | W0=$60 =='%(
              gas,toll*100,drop*100,cycles,PATHS//1000))
        for nm,f,k,fx in POL:
            W=sim(f,k,cycles,PATHS,toll,drop,gas,fixed=fx)
            print('  %-36s med $%7.2f mean $%8.2f P(>120) %6.4f P(>300) %6.4f P(<20) %6.4f P(<5) %6.4f max $%8.0f'%(
              nm,np.median(W),W.mean(),(W>120).mean(),(W>300).mean(),(W<20).mean(),(W<5).mean(),W.max()))
            sys.stdout.flush()
