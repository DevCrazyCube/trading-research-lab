import pickle,collections,sys
import numpy as np
D=pickle.load(open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/panel.pkl','rb'))
recs=D['recs']; rng=np.random.default_rng(99)
buckets=collections.defaultdict(list)
for m,ts,r,tag in recs: buckets[ts//900].append(r)
BKR=[v for k,v in buckets.items() if len(v)>=6]
import os
GAS=float(os.environ.get("GAS","0.20")); NPOOL=8000
POOLS={}
def pools(k,toll,drop):
    key=(k,toll,drop)
    if key in POOLS: return POOLS[key]
    out=np.empty((len(BKR),NPOOL))
    for i,v in enumerate(BKR):
        a=np.array([drop if r is None else r for r in v]); a=(1+a)*(1-toll)-1
        n=len(a); kk=min(k,n)
        keys=rng.random((NPOOL,n)); idx=np.argpartition(keys,kk-1,axis=1)[:,:kk]
        out[i]=a[idx].sum(1)
    POOLS[key]=out; return out
def sim(frac,k,cycles,paths,toll,drop,W0=60.0):
    P=pools(k,toll,drop); W=np.full(paths,W0); alive=np.ones(paths,bool)
    for t in range(cycles):
        S=P[rng.integers(0,len(BKR),paths),rng.integers(0,NPOOL,paths)]
        stake=W*frac/k
        dead=(stake<0.50)|(~alive); stake=np.where(dead,0,stake)
        W=np.where(dead,W,np.maximum(0,W+stake*S-k*GAS)); alive=alive&~dead
    return W
toll,drop,cycles,paths=0.0114,-1.00,int(sys.argv[1]) if len(sys.argv)>1 else 500,30000
print('SIZING FRONTIER  toll 1.14%% RT, dropout -100%%, gas $%.2f/pos, %d x15m cycles, start $60, %dk paths'%(GAS,cycles,paths//1000))
print('deployed  N  $/tkt   med$    mean$   P(>$120) P(>$300) P(>$600) P(<$20)  P(<$5)')
for frac,k in [(1.00,5),(0.80,5),(0.60,5),(0.40,5),(0.25,5),(0.10,5),(0.40,2),(0.20,2),(0.10,2),(0.05,2),(0.02,2),(0.10,1),(0.05,1),(0.02,1),(1.00,1),(0.50,1)]:
    W=sim(frac,k,cycles,paths,toll,drop)
    print('%7.0f%% %2d %6.2f %8.2f %8.2f %8.3f %8.3f %8.3f %8.3f %8.3f'%(
      frac*100,k,60*frac/k,np.median(W),W.mean(),(W>120).mean(),(W>300).mean(),(W>600).mean(),(W<20).mean(),(W<5).mean()))
