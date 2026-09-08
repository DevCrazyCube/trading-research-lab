import sys, time, math, json, pickle
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *

t0=time.time(); O=open(D+'out_stage1.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)
p('train mints %d  validate mints %d'%(len(TR),len(VA)))
p('train elig bars %d  validate elig bars %d'%(sum(len(st['ELIG'][m]) for m in TR),sum(len(st['ELIG'][m]) for m in VA)))

CANON=[(5,None,None,None,'flat'),(15,None,None,None,'flat'),(30,None,None,None,'flat'),
       (60,None,None,None,'flat'),(15,0.20,-0.25,None,'flat'),(30,0.30,-0.35,None,'flat'),
       (15,None,None,0.30,'flat')]

def allcell(ms): return {m:np.zeros(len(st['ELIG'][m]),dtype=np.int64) for m in ms}

p('=== BASELINES: every eligible bar, mint-equal, no-overlap, entry at next real bar open ===')
p('%-32s | %-28s | %-28s'%('structure','TRAIN wmean/raw/med n k res','VALID wmean/raw/med n k res'))
BASE={}
for spec in CANON:
    line=str(spec).ljust(32)
    for tag,ms in (('tr',TR),('va',VA)):
        sims=sim_all(ms,spec,drop=-0.30)
        r=eval_cells(ms,allcell(ms),sims)[0]
        sw=stats(r[0]); sr=stats(r[1])
        BASE[(tag,spec)]=dict(w=sw[0],raw=sr[0],med=sw[1],n=r[2],k=sw[4],res=r[3]/max(r[2],1))
        line+=' | %+.4f %+8.3f %+.4f %5d %3d %.3f'%(sw[0],sr[0],sw[1],r[2],sw[4],r[3]/max(r[2],1))
    p(line)
p('')
p('=== dropout-charge sensitivity + toll sensitivity (TRAIN, 15m flat) ===')
for drop in (-0.30,-0.50,-1.00):
    for toll,tn in ((TOLL,'1.14%'),(TOLL_HI,'2.5%')):
        sims=sim_all(TR,(15,None,None,None,'flat'),drop=drop,toll=toll)
        r=eval_cells(TR,allcell(TR),sims)[0]; sw=stats(r[0]); sr=stats(r[1])
        p('  drop=%5.0f%% toll=%-5s  wmean=%+.4f raw=%+.4f med=%+.4f'%(drop*100,tn,sw[0],sr[0],sw[1]))
p('')
p('=== 1-WAY SCREEN (train, winsorised mint-equal mean vs same-structure baseline) ===')
FEATS=st['FEATS']; EDGES={}; one={}; combos=0
simc={spec:sim_all(TR,spec,drop=-0.30) for spec in CANON}
rows=[]
for f in FEATS:
    e=make_edges(TR,f)
    if e is None: p('feat %-12s NO EDGES'%f); continue
    b,nb=bin_of(TR,f,e)
    nm=sum(1 for m in TR if (b[m]>=0).any())
    if nm<80: p('feat %-12s DROP only %d/%d mints have values'%(f,nm,len(TR))); continue
    EDGES[f]=e; best=None
    for spec in CANON:
        r=eval_cells(TR,b,simc[spec]); base=BASE[('tr',spec)]['w']
        for c,v in r.items():
            s=stats(v[0]); combos+=1
            if s is None or s[4]<25 or v[2]<40: continue
            t=tstat(s,base)
            rows.append((f,c,spec,s[0],s[1],s[4],v[2],base,t))
            if best is None or t>best[0]: best=(t,c,spec,s[0],s[4],v[2])
    if best:
        p('feat %-12s bestT=%5.2f bin=%d %-28s wmean=%+.4f k=%d n=%d'%(f,best[0],best[1],str(best[2]),best[3],best[4],best[5]))
        one[f]=best[0]
rows.sort(key=lambda x:-x[8])
p('1-way combos evaluated %d'%combos)
p('--- top 20 1-way cells ---')
for r in rows[:20]:
    p('  %-10s bin%d %-28s wmean=%+.4f med=%+.4f k=%3d n=%4d base=%+.4f t=%5.2f'%(r[0],r[1],str(r[2]),r[3],r[4],r[5],r[6],r[7],r[8]))
p('--- feature ranking ---')
for f,t in sorted(one.items(),key=lambda x:-x[1]): p('  %-12s %.2f'%(f,t))
pickle.dump(dict(EDGES=EDGES,one=one,BASE=BASE,CANON=CANON,combos=combos),open(D+'stage1.pkl','wb'))
p('done t=%.1f'%(time.time()-t0)); O.close()
