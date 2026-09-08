import sys, math, pickle, itertools
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *
O=open(D+'out_stage6.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)
s2=pickle.load(open(D+'stage2.pkl','rb')); s3=pickle.load(open(D+'stage3.pkl','rb'))
EDGES=s2['EDGES']; out=s3['out']
B={1:{f:bin_of(TR,f,EDGES[f]) for f in EDGES},2:{f:bin_of(VA,f,EDGES[f]) for f in EDGES}}
M={1:TR,2:VA}
def decode(fs,cell):
    nbs=[len(EDGES[f])-1 for f in fs]; b=[0]*len(fs); x=cell
    for i in range(len(fs)-1,-1,-1): b[i]=x%nbs[i]; x//=nbs[i]
    return b,' AND '.join('%s in [%s,%s)'%(f,'-inf' if not np.isfinite(EDGES[f][bi]) else '%.5g'%EDGES[f][bi],
        '+inf' if not np.isfinite(EDGES[f][bi+1]) else '%.5g'%EDGES[f][bi+1]) for f,bi in zip(fs,b))
def memb_bins(fs,bs,split):
    o={}
    for m in M[split]:
        ok=None
        for f,bi in zip(fs,bs):
            a=B[split][f][0][m]
            c=(a==bi)
            ok=c if ok is None else (ok&c)
        idx=np.nonzero(ok)[0]
        if len(idx): o[m]=idx
    return o
def ev(memb,sims):
    per=[]; nt=0; nr=0
    for m,pos in memb.items():
        el=st['ELIG'][m]; net,netw,ex,rv=sims[m]; ts=st['panel'][m]['ts']
        s=0.0; c=0; last=-1.0; r=0
        for a in pos:
            e=int(el[a])+1
            if ts[e]<last: continue
            s+=netw[e]; c+=1; last=ex[e]; r+=1 if rv[e] else 0
        if c: per.append((m,s/c,c)); nt+=c; nr+=r
    return per,nt,nr
def ev_all(split,sims):
    per=[]; nt=0
    for m in M[split]:
        el=st['ELIG'][m]; net,netw,ex,rv=sims[m]; ts=st['panel'][m]['ts']
        s=0.0; c=0; last=-1.0
        for a in range(len(el)):
            e=int(el[a])+1
            if ts[e]<last: continue
            s+=netw[e]; c+=1; last=ex[e]
        if c: per.append(s/c); nt+=c
    return per,nt

# ---------- proper one-sided BH over all 35 finalists ----------
p('=== ONE-SIDED BH (H1: validate mean > 0) over all %d finalists ==='%len(out))
ps=[]
for o in out:
    r=o['r']; bs,_=decode(r['f'],r['cell'])
    sims=sim_all(VA,r['spec'],drop=-0.30)
    per,nt,nr=ev(memb_bins(r['f'],bs,2),sims)
    v=np.array([x[1] for x in per]); k=len(v)
    rng=np.random.default_rng(3); mus=v[rng.integers(0,k,size=(4000,k))].mean(axis=1)
    p1=float((mus<=0).mean())
    ps.append(p1)
keep=bh(ps,0.10)
p('one-sided BH q=0.10 survivors: %d'%len(keep))
for i,o in enumerate(out):
    if i in keep:
        p('  SURVIVOR %s c%d %s va_w=%+.4f p1=%.4f'%('/'.join(o['r']['f']),o['r']['cell'],str(o['r']['spec']),o['vw'],ps[i]))
p('finalists both one-sided-BH AND va_w>0: %d'%sum(1 for i,o in enumerate(out) if i in keep and o['vw']>0))

# ---------- deep dive on the best validate survivors ----------
cands=[o for o in sorted(out,key=lambda x:-x['vw'])[:6]]
for o in cands:
    r=o['r']; fs=r['f']; bs,desc=decode(fs,r['cell']); spec=r['spec']
    p('\n########## %s cell=%d %s'%('/'.join(fs),r['cell'],str(spec)))
    p('  ENTRY: %s   (bins %s)'%(desc,bs))
    sims=sim_all(VA,spec,drop=-0.30)
    per,nt,nr=ev(memb_bins(fs,bs,2),sims)
    per.sort(key=lambda x:-x[1]); v=[x[1] for x in per]
    p('  VALIDATE wmean=%+.4f med=%+.4f k=%d n=%d res=%.3f'%(np.mean(v),np.median(v),len(v),nt,nr/max(nt,1)))
    p('  concentration: top1 mint=%+.3f (n=%d) ; drop-best wmean=%+.4f ; drop-best3 %+.4f ; drop-worst %+.4f'%(
      per[0][1],per[0][2],np.mean(v[1:]),np.mean(v[3:]),np.mean(v[:-1])))
    p('  frac of mints with positive mean: %.3f'%(np.mean([x>0 for x in v])))
    line='  robustness: '
    for drop in (-0.30,-0.50,-1.00):
        for toll,tn in ((TOLL,'1.14'),(TOLL_HI,'2.5')):
            sm=sim_all(VA,spec,drop=drop,toll=toll)
            pr,_,_=ev(memb_bins(fs,bs,2),sm); bb,_=ev_all(2,sm)
            line+='[d%.0f/t%s %+.4f vs ctrl %+.4f] '%(drop*100,tn,np.mean([x[1] for x in pr]),np.mean(bb))
    p(line)
    # marginal value of each of the 3 conditions (validate)
    p('  --- does the 3-way beat its own 1-way and 2-way parts? (validate, same structure) ---')
    bb,_=ev_all(2,sims)
    p('    ALL BARS (random ctrl)           wmean=%+.4f k=%d'%(np.mean(bb),len(bb)))
    for r_ in range(1,3):
        for sub in itertools.combinations(range(3),r_):
            f2=[fs[i] for i in sub]; b2=[bs[i] for i in sub]
            pr,n2,_=ev(memb_bins(f2,b2,2),sims); vv=[x[1] for x in pr]
            p('    %-34s wmean=%+.4f med=%+.4f k=%3d n=%5d'%('/'.join(f2),np.mean(vv),np.median(vv),len(vv),n2))
    p('    %-34s wmean=%+.4f med=%+.4f k=%3d n=%5d'%('FULL 3-WAY','%s'%np.mean(v),np.median(v),len(v),nt) if False else
      '    FULL 3-WAY                         wmean=%+.4f med=%+.4f k=%3d n=%5d'%(np.mean(v),np.median(v),len(v),nt))
    # neighbouring bins (is the cell a knife edge?)
    p('  --- neighbouring bins on validate (stability of the cell) ---')
    for i in range(3):
        for d in (-1,1):
            nb=list(bs); nb[i]=bs[i]+d
            if nb[i]<0 or nb[i]>=len(EDGES[fs[i]])-1: continue
            pr,n2,_=ev(memb_bins(fs,nb,2),sims); vv=[x[1] for x in pr]
            if not vv: continue
            p('    %s%+d -> wmean=%+.4f k=%3d n=%4d'%(fs[i],d,np.mean(vv),len(vv),n2))
p('\ndone'); O.close()
