import sys, math, pickle
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *
O=open(D+'out_diag.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)

def gross(mints,H):
    """pure open->open gross return over H minutes, every eligible bar, no overlap rule, no toll"""
    per=[]; allr=[]; drop=0; tot=0
    for m in mints:
        P=st['panel'][m]; PA=st['PATH'][m]; el=st['ELIG'][m]
        op=P['op']; te=PA['T'][H]
        rs=[]
        for i in el:
            e=i+1; k=te[e]; tot+=1
            if k<0: drop+=1; continue
            rs.append(op[k]/op[e]-1.0)
        if rs:
            per.append(float(np.mean(rs))); allr.extend(rs)
    a=np.array(allr); pm=np.array(per)
    return pm,a,drop,tot

for H in (5,15,60):
    for nm,ms in (('TRAIN',TR),('VALID',VA)):
        pm,a,drop,tot=gross(ms,H)
        p('%s H=%d  mint-equal mean=%.4f median=%.4f | pooled mean=%.4f median=%.4f | n=%d k=%d dropfrac=%.3f'%(
            nm,H,pm.mean(),np.median(pm),a.mean(),np.median(a),len(a),len(pm),drop/max(tot,1)))
        p('    per-trade quantiles: '+' '.join('%.3f'%np.quantile(a,q) for q in (0.01,0.1,0.25,0.5,0.75,0.9,0.99,0.999)))
        p('    max per-trade %.1f ; per-mint mean top5 %s'%(a.max(),np.sort(pm)[-5:]))
        wm=np.clip(a,-1,3.0)
        p('    winsor[-100%%,+300%%] pooled mean=%.4f'%wm.mean())

# find the monster
p('--- biggest single moves (validate, H=15) ---')
rows=[]
for m in VA:
    P=st['panel'][m]; PA=st['PATH'][m]; el=st['ELIG'][m]
    op=P['op']; te=PA['T'][15]; ts=P['ts']
    for i in el:
        e=i+1; k=te[e]
        if k<0: continue
        r=op[k]/op[e]-1.0
        if r>5: rows.append((r,m,int(ts[e]),float(op[e]),float(op[k]),int(k-e)))
rows.sort(reverse=True)
p('n moves >+500%%: %d'%len(rows))
for r in rows[:12]: p('   %.1fx mint=%s ts=%d op_in=%.3e op_out=%.3e bars=%d'%(r[0],r[1][:12],r[2],r[3],r[4],r[5]))
# how concentrated
mm={}
for r in rows: mm[r[1]]=mm.get(r[1],0)+1
p('distinct mints with >+500%% 15m moves: %d'%len(mm))
# intrabar sanity: open outside [low,high]?
bad=0; tot=0
for m in TR+VA:
    P=st['panel'][m]
    tot+=P['n']
    bad+=int(np.sum((P['op']>P['hi']*1.0000001)|(P['op']<P['lo']*0.9999999)))
p('bars with open outside [low,high]: %d of %d'%(bad,tot))
O.close()
