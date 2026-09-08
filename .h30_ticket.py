import pickle,collections,statistics
import numpy as np
D=pickle.load(open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/panel.pkl','rb'))
recs=D['recs']
rng=np.random.default_rng(7)
by=collections.defaultdict(list)
for m,ts,r,tag in recs: by[m].append(r)
mk=list(by.keys())
n_res=sum(1 for x in recs if x[2] is not None)
print('n windows %d | mint clusters %d | resolution %.2f%%'%(len(recs),len(mk),100*n_res/len(recs)))
print('drop%  toll%   mean%    median%     p1%      p99%   P(>+100%)   ci_lo%   ci_hi%')
RES={}
for drop in (-0.30,-0.50,-1.00):
  for toll in (0.0114,0.030):
    per={m:((1+np.array([drop if r is None else r for r in v]))*(1-toll)-1) for m,v in by.items()}
    S=np.array([per[m].sum() for m in mk]); C=np.array([len(per[m]) for m in mk],float)
    allv=np.concatenate([per[m] for m in mk])
    B=4000; idx=rng.integers(0,len(mk),(B,len(mk)))
    bm=S[idx].sum(1)/C[idx].sum(1)
    lo,hi=np.percentile(bm,[2.5,97.5])
    RES[(drop,toll)]=(allv.mean(),np.median(allv),lo,hi)
    print('%5.0f %6.2f %8.3f %9.3f %9.2f %8.3f %9.4f %9.3f %8.3f'%(drop*100,toll*100,
      100*allv.mean(),100*np.median(allv),100*np.percentile(allv,1),100*np.percentile(allv,99),
      (allv>1.0).mean(),100*lo,100*hi))
# benchmark = this same universe random bar (that IS the barbell's draw) -> identical by construction
import pickle as P; P.dump(RES,open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/ticket.pkl','wb'))
# gas drag as a % of stake
for stake in (3.0,4.8,6.0,60.0):
    print('gas drag at $%.2f stake: %.2f%% per round trip'%(stake,100*0.20/stake))
