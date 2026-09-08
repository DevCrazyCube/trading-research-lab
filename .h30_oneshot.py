import pickle,collections,numpy as np
D=pickle.load(open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/panel.pkl','rb'))
recs=D['recs']
for drop in (-1.00,-0.30):
  for toll in (0.0114,0.030):
    a=np.array([drop if r is None else r for m,t,r,g in recs]); a=(1+a)*(1-toll)-1
    print('drop%3.0f%% toll%5.2f%%  P(tkt>+400%%)=%.5f  P(>+100%%)=%.5f  P(>+900%%)=%.6f  max=%.1fx'%(
      drop*100,toll*100,(a>4.0).mean(),(a>1.0).mean(),(a>9.0).mean(),1+a.max()))
# one-shot all-in $60 minus $0.20 gas, then STOP  vs  k consecutive all-ins
rng=np.random.default_rng(11)
buckets=collections.defaultdict(list)
for m,ts,r,tag in recs: buckets[ts//900].append(r)
BKR=[np.array([-1.0 if r is None else r for r in v]) for k,v in buckets.items() if len(v)>=6]
BKR=[(1+v)*(1-0.0114)-1 for v in BKR]
P=20000
print('\nONE-SHOT / SHORT-BURST ALL-IN (toll 1.14%, dropout -100%, gas $0.20/trade, start $60)')
print(' trades   med$    mean$   P(>$120) P(>$300) P(>$600) P(<$20)  P(<$5)')
for nt in (1,2,3,5,10,20):
    W=np.full(P,60.0)
    for t in range(nt):
        b=rng.integers(0,len(BKR),P)
        S=np.array([BKR[bb][rng.integers(0,len(BKR[bb]))] for bb in b])
        W=np.maximum(0,W*(1+S)-0.20)
    print('%6d %8.2f %8.2f %8.4f %8.4f %8.4f %8.4f %8.4f'%(nt,np.median(W),W.mean(),
      (W>120).mean(),(W>300).mean(),(W>600).mean(),(W<20).mean(),(W<5).mean()))
