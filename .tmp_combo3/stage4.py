import sys, time, math, pickle, random
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *
t0=time.time(); O=open(D+'out_stage4.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)
s2=pickle.load(open(D+'stage2.pkl','rb'))
EDGES=s2['EDGES']; money=s2.get('money',[]); allthree=s2.get('allthree',[])
p('train-positive 3-way (cell,structure) combos: %d ; all sized combos: %d'%(len(money),len(allthree)))
BVA={f:bin_of(VA,f,EDGES[f]) for f in EDGES}
def membership(fs,cell,mints,B):
    arrs=[B[f] for f in fs]; out={}
    for m in mints:
        v=None; bad=None
        for b,nb in arrs:
            a=b[m]
            v=a.copy() if v is None else v*nb+a
            bad=(a<0) if bad is None else (bad|(a<0))
        idx=np.nonzero((~bad)&(v==cell))[0]
        if len(idx): out[m]=idx
    return out
def eval_sub(memb,sims):
    pw=[]; nt=0
    for m,pos in memb.items():
        el=st['ELIG'][m]; net,netw,ex_ts,resv=sims[m]; ts=st['panel'][m]['ts']
        sw=0.0; c=0; last=-1.0
        for a in pos:
            e=int(el[a])+1
            if ts[e]<last: continue
            sw+=netw[e]; c+=1; last=ex_ts[e]
        if c: pw.append(sw/c); nt+=c
    return pw,nt
def eval_all(mints,sims):
    pw=[]; nt=0
    for m in mints:
        el=st['ELIG'][m]; net,netw,ex_ts,resv=sims[m]; ts=st['panel'][m]['ts']
        sw=0.0; c=0; last=-1.0
        for a in range(len(el)):
            e=int(el[a])+1
            if ts[e]<last: continue
            sw+=netw[e]; c+=1; last=ex_ts[e]
        if c: pw.append(sw/c); nt+=c
    return pw,nt
SPECS=sorted({r['spec'] for r in money}|{r['spec'] for r in allthree},key=str)
sims={s:sim_all(VA,s,drop=-0.30) for s in SPECS}
vbase={s:stats(eval_all(VA,sims[s])[0])[0] for s in SPECS}
p('validate baselines: '+' | '.join('%s %+.4f'%(str(s),vbase[s]) for s in SPECS))
def repl(group,name,cap=1500):
    g=group[:cap]
    npos=0; nn=0; ws=[]; edges=[]
    for r in g:
        memb=membership(r['f'],r['cell'],VA,BVA)
        pw,nt=eval_sub(memb,sims[r['spec']])
        s=stats(pw)
        if s is None or s[4]<15 or nt<20: continue
        nn+=1; ws.append(s[0]); edges.append(s[0]-vbase[r['spec']])
        if s[0]>0: npos+=1
    if nn==0: p('%s: no evaluable'%name); return
    p('%-34s validated=%4d  frac wmean>0 on VALIDATE = %.3f  mean va_wmean=%+.4f  median va_wmean=%+.4f  mean edge vs ctrl=%+.4f'%(
      name,nn,npos/nn,float(np.mean(ws)),float(np.median(ws)),float(np.mean(edges))))
    return npos/nn
money.sort(key=lambda x:-x['tz'])
r1=repl(money,'TRAIN-POSITIVE cells (all)')
r2=repl(money[:200],'TRAIN-POSITIVE top200 by t-vs-0')
r3=repl(money[:50],'TRAIN-POSITIVE top50 by t-vs-0')
rnd=[r for r in allthree]
random.Random(11).shuffle(rnd)
r4=repl(rnd,'RANDOM 3-way cells (control)')
neg=[r for r in allthree if r['w']<=0]
random.Random(12).shuffle(neg)
r5=repl(neg,'TRAIN-NEGATIVE cells (control)')
p('\nIf selection carried real information, TRAIN-POSITIVE would replicate far above RANDOM.')
p('done t=%.1f'%(time.time()-t0)); O.close()
