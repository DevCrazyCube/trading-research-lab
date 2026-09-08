import sys, math, pickle
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *
O=open(D+'out_stage7.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); VA=mints_of(2)
s2=pickle.load(open(D+'stage2.pkl','rb')); s3=pickle.load(open(D+'stage3.pkl','rb'))
EDGES=s2['EDGES']; out=s3['out']
BV={f:bin_of(VA,f,EDGES[f]) for f in EDGES}
def decode(fs,cell):
    nbs=[len(EDGES[f])-1 for f in fs]; b=[0]*len(fs); x=cell
    for i in range(len(fs)-1,-1,-1): b[i]=x%nbs[i]; x//=nbs[i]
    return b
def memb(fs,bs):
    o={}
    for m in VA:
        ok=None
        for f,bi in zip(fs,bs):
            c=(BV[f][0][m]==bi); ok=c if ok is None else (ok&c)
        idx=np.nonzero(ok)[0]
        if len(idx): o[m]=idx
    return o
def ev(mb,sims):
    per=[]; nt=0
    for m,pos in mb.items():
        el=st['ELIG'][m]; net,netw,ex,rv=sims[m]; ts=st['panel'][m]['ts']
        s=0.0; c=0; last=-1.0
        for a in pos:
            e=int(el[a])+1
            if ts[e]<last: continue
            s+=netw[e]; c+=1; last=ex[e]
        if c: per.append(s/c); nt+=c
    return per,nt
rows=[]
for o in out:
    r=o['r']; bs=decode(r['f'],r['cell'])
    sims=sim_all(VA,r['spec'],drop=-0.30)
    v,nt=ev(memb(r['f'],bs),sims); v=np.array(v); k=len(v)
    rng=np.random.default_rng(3); mus=v[rng.integers(0,k,size=(20000,k))].mean(axis=1)
    p1=float((mus<=0).mean())
    rows.append((p1,'/'.join(r['f']),r['cell'],str(r['spec']),float(v.mean()),k,nt))
rows.sort()
n=len(rows)
p('one-sided bootstrap p(mean<=0) for all %d validate finalists, BH q=0.10 thresholds:'%n)
p('%-4s %-9s %-9s %-24s %-30s %8s %4s %5s'%('rk','p1','BHthr','triple','structure','va_w','k','n'))
for i,(p1,f,c,sp,w,k,nt) in enumerate(rows,1):
    p('%-4d %-9.5f %-9.5f %-24s %-30s %+8.4f %4d %5d'%(i,p1,0.10*i/n,f[:24],sp,w,k,nt))
surv=[i for i,(p1,*_ ) in enumerate(rows,1) if p1<=0.10*i/n]
p('BH survivors: %s'%surv)
# how many DISTINCT rules are among the finalists
d=set((r[1],r[2]) for r in rows)
p('distinct (triple,cell) among finalists: %d'%len(d))
p('  if BH were applied over %d distinct rules, rank-1 threshold = %.5f ; smallest p1 = %.5f -> %s'%(
   len(d),0.10/len(d),rows[0][0],'would survive' if rows[0][0]<=0.10/len(d) else 'still dead'))
p('done'); O.close()
