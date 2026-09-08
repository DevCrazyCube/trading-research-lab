import sqlite3, json, hashlib
import numpy as np
exec(open('/home/anont/meme/.holdout_rule1.py').read().split('# ---------------- MAIN')[0].replace(
    "OUT=open('/home/anont/meme/.holdout_rule1_out.txt','w')",
    "OUT=open('/home/anont/meme/.holdout_rule1b_out.txt','w')"))

sigs=rule_signals(TH_TRAIN)
res_sigs={m:s for m,s in sigs.items() if hsplit(m)==0}
hold=[]
for m,s in res_sigs.items(): hold+=sim_trades(m,s)
toll,dc=0.0114,-0.30
per,mm=aggregate(hold,toll,dc)
mints_list=sorted(per.keys())
P('holdout n=%d clusters=%d mean %+.4f%% median %+.4f%%'%(len(hold),len(mm),100*np.mean(mm),100*np.median(mm)))

# contribution of TP trades
tp=[t for t in hold if t['kind']=='tp']
P('TP trades %d across %d mints'%(len(tp),len(set(t['mint'] for t in tp))))
no_tp=[t for t in hold if t['kind']!='tp']
per2,mm2=aggregate(no_tp,toll,dc)
P('excluding TP trades: n=%d clusters=%d mean %+.4f%% median %+.4f%%'%(len(no_tp),len(mm2),100*np.mean(mm2),100*np.median(mm2)))

# leave-one-mint-out on the mean
vals=np.array([np.mean(per[m]) for m in mints_list])
loo=[(mints_list[i],100*(vals.sum()-vals[i])/(len(vals)-1)) for i in range(len(vals))]
loo.sort(key=lambda x:x[1])
P('leave-one-mint-out mean range: min %+.4f%% (%s)  max %+.4f%% (%s)'%(loo[0][1],loo[0][0][:8],loo[-1][1],loo[-1][0][:8]))
# how many mints must be dropped for mean<=0
order=np.argsort(-vals)
cum=vals.copy()
for k in range(1,8):
    keep=np.delete(vals,order[:k])
    P('  drop top-%d mints: mean %+.4f%% (n_mints=%d)'%(k,100*keep.mean(),len(keep)))

# high-precision randomization test (within-mint, k matched)
per_mint_k={}
for t in hold: per_mint_k[t['mint']]=per_mint_k.get(t['mint'],0)+1
for toll_,dc_ in ((0.0114,-0.30),(0.025,-0.30),(0.0114,-1.00)):
    per_,mm_=aggregate(hold,toll_,dc_)
    rule_mean=float(np.mean(mm_)); rule_med=float(np.median(mm_))
    ge=0; gem=0; R=4000; draws=[]
    for r in range(R):
        tt=[]
        for m,k in per_mint_k.items():
            lb=legal_bars(m)
            pick=set(rng.choice(lb,size=min(k*4,len(lb)),replace=False).tolist())
            t2=sim_trades(m,pick)[:k]
            tt+=t2
        p2,m2=aggregate(tt,toll_,dc_)
        draws.append(np.mean(m2))
        ge+= (np.mean(m2)>=rule_mean); gem+= (np.median(m2)>=rule_med)
    draws=np.array(draws)
    P('randomization toll %.4f drop %.2f: rule mean %+.4f%% | null mean %+.4f%% sd %.4f%% | one-sided p(mean)=%.5f p(median)=%.5f'%(
        toll_,dc_,100*rule_mean,100*draws.mean(),100*draws.std(),(ge+1)/(R+1),(gem+1)/(R+1)))

# median: cluster bootstrap CI
for toll_ in (0.0114,0.025):
    per_,mm_=aggregate(hold,toll_,-0.30)
    a=np.array(mm_); idx=rng.integers(0,len(a),size=(20000,len(a)))
    bsmed=np.median(a[idx],axis=1)
    P('median toll %.4f: %+.4f%% 95%%CI [%+.4f%%, %+.4f%%] p=%.4f'%(
        toll_,100*np.median(a),100*np.percentile(bsmed,2.5),100*np.percentile(bsmed,97.5),
        2*min((bsmed<=0).mean(),(bsmed>=0).mean())))
OUT.close()
