import sys,json,pickle; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
sys.argv=sys.argv
exec(open('/home/anont/meme/.fc3/b10_stress.py').read().split("CAND={")[0])
# --- neighbourhood of E: age band x v0 threshold x H x SL, validate, pessimistic 'close' fill
L=[]
V0Q=[0,207,5040,20000]
def mk(a0,a1,v0t,pri0):
    return lambda f,i,d: (a0<=f['age'][i]<a1) and f['v0']>=v0t and (f['pri']==0 if pri0 else True)
L.append('=== E-neighbourhood: validate, fill=close (pessimistic), toll 1.14%, drop -30% ===')
L.append('%-14s %-7s %-5s %-4s %-5s | %-9s %-9s %-6s %-5s'%('age','v0thr','H','SL','pri0','mean','cilo','n','k'))
best=[]
for (a0,a1) in [(0,30),(10,30),(20,45),(30,60),(30,90),(45,75),(60,120),(20,60),(30,120)]:
    for v0t in V0Q:
        for H in (15,30,60):
            for sl in (None,-0.25,-0.40):
                for pri0 in (True,False):
                    r=backtest(mk(a0,a1,v0t,pri0),H,None,sl,'all','validate',fill='close')
                    if r is None or r['k']<12 or r['n']<25: continue
                    lo=blo(r['pm'])
                    best.append((r['mean'],lo,a0,a1,v0t,H,sl,pri0,r['n'],r['k']))
best.sort(key=lambda x:-x[0])
for m,lo,a0,a1,v0t,H,sl,p0,n,k in best[:30]:
    L.append('%-14s %-7s %-5d %-5s %-5s | %+.4f  %+.4f  n=%-4d k=%-4d'%('%d-%d'%(a0,a1),v0t,H,str(sl),p0,m,lo,n,k))
L.append('... total neighbourhood cells evaluated: %d ; positive-mean: %d'%(len(best),sum(1 for b in best if b[0]>0)))
# train side of the same neighbourhood
L.append('')
L.append('=== same neighbourhood on TRAIN (fill=close) ===')
bt=[]
for (a0,a1) in [(0,30),(10,30),(20,45),(30,60),(30,90),(45,75),(60,120),(20,60),(30,120)]:
    for v0t in V0Q:
        for H in (15,30,60):
            for sl in (None,-0.25,-0.40):
                for pri0 in (True,False):
                    r=backtest(mk(a0,a1,v0t,pri0),H,None,sl,'all','train',fill='close')
                    if r is None or r['k']<12 or r['n']<25: continue
                    bt.append((r['mean'],a0,a1,v0t,H,sl,pri0,r['n'],r['k']))
d={(b[1],b[2],b[3],b[4],b[5],b[6]):b[0] for b in bt}
agree=0; tot=0
for m,lo,a0,a1,v0t,H,sl,p0,n,k in best:
    key=(a0,a1,v0t,H,sl,p0)
    if key in d:
        tot+=1
        if (d[key]>0)==(m>0): agree+=1
L.append('train/validate sign agreement across neighbourhood: %d/%d'%(agree,tot))
bt.sort(key=lambda x:-x[0])
for m,a0,a1,v0t,H,sl,p0,n,k in bt[:15]:
    L.append('TRAIN %-10s v0>=%-6s H=%-3d SL=%-5s pri0=%-5s mean=%+.4f n=%-4d k=%-4d'%('%d-%d'%(a0,a1),v0t,H,str(sl),p0,m,n,k))
# random-entry control under identical structure and fill, matched count per mint
L.append('')
L.append('=== matched-random control for E (same mints/counts, random bars, fill=close) ===')
import numpy.random as npr
def rand_cond_factory(seed,frac):
    rng=np.random.default_rng(seed)
    cache={}
    def c(f,i,d):
        return rng.random()<frac
    return c
Ecnd=mk(30,60,5040,True)
r=backtest(Ecnd,30,None,-0.25,'all','validate',fill='close')
L.append('E validate fill=close mean=%+.4f n=%d k=%d'%(r['mean'],r['n'],r['k']))
# frac of bars selected by E among the E-mints
vals=[]
for s in range(12):
    rc=rand_cond_factory(100+s,0.02)
    rr=backtest(rc,30,None,-0.25,'all','validate',fill='close')
    if rr: vals.append(rr['mean'])
L.append('random 2%%-of-bars entries, same exit+fill: mean=%+.4f (sd %.4f, %d draws)'%(np.mean(vals),np.std(vals),len(vals)))
open(SP+'/b11.log','w').write('\n'.join(L))
