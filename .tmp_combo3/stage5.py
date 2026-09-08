import sys, time, math, pickle
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *
O=open(D+'out_stage5.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)
s2=pickle.load(open(D+'stage2.pkl','rb')); s3=pickle.load(open(D+'stage3.pkl','rb'))
EDGES=s2['EDGES']; out=s3['out']
BVA={f:bin_of(VA,f,EDGES[f]) for f in EDGES}
BTR={f:bin_of(TR,f,EDGES[f]) for f in EDGES}
def decode(fs,cell):
    nbs=[len(EDGES[f])-1 for f in fs]
    b=[0]*len(fs)
    x=cell
    for i in range(len(fs)-1,-1,-1):
        b[i]=x%nbs[i]; x//=nbs[i]
    parts=[]
    for f,bi in zip(fs,b):
        e=EDGES[f]
        lo=e[bi]; hi=e[bi+1]
        parts.append('%s in [%s, %s)'%(f,'-inf' if not np.isfinite(lo) else '%.4g'%lo,
                                       '+inf' if not np.isfinite(hi) else '%.4g'%hi))
    return ' AND '.join(parts)
def membership(fs,cell,mints,B):
    arrs=[B[f] for f in fs]; o={}
    for m in mints:
        v=None; bad=None
        for b,nb in arrs:
            a=b[m]
            v=a.copy() if v is None else v*nb+a
            bad=(a<0) if bad is None else (bad|(a<0))
        idx=np.nonzero((~bad)&(v==cell))[0]
        if len(idx): o[m]=idx
    return o
def eval_sub(memb,sims):
    per={}; nt=0; nr=0
    for m,pos in memb.items():
        el=st['ELIG'][m]; net,netw,ex_ts,resv=sims[m]; ts=st['panel'][m]['ts']
        sw=0.0; c=0; last=-1.0; rr=0
        for a in pos:
            e=int(el[a])+1
            if ts[e]<last: continue
            sw+=netw[e]; c+=1; last=ex_ts[e]; rr+=1 if resv[e] else 0
        if c: per[m]=(sw/c,c); nt+=c; nr+=rr
    return per,nt,nr
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
cands=sorted(out,key=lambda o:-o['vw'])[:12]
p('=== ROBUSTNESS on the 12 best-on-VALIDATE finalists ===')
for o in cands:
    r=o['r']; spec=r['spec']
    p('\n### %s  cell=%d'%('/'.join(r['f']),r['cell']))
    p('  ENTRY: %s'%decode(r['f'],r['cell']))
    p('  STRUCTURE: hold<=%dmin tp=%s sl=%s trail=%s position=%s'%(spec[0],spec[1],spec[2],spec[3],spec[4]))
    p('  train wmean=%+.4f | validate wmean=%+.4f raw=%+.4f med=%+.4f k=%d n=%d ctrl=%+.4f p0=%.4f'%(
      r['w'],o['vw'],o['vraw'],o['vmed'],o['vk'],o['vn'],o['vbase'],o['p0']))
    sims=sim_all(VA,spec,drop=-0.30)
    per,nt,nr=eval_sub(membership(r['f'],r['cell'],VA,BVA),sims)
    vals=sorted(per.items(),key=lambda x:-x[1][0])
    tot=sum(v[0] for _,v in per.items())
    p('  resolution=%.3f  top-mint share of total = %.3f ; drop best mint -> wmean=%+.4f ; drop best 3 -> %+.4f'%(
      nr/max(nt,1), (vals[0][1][0]/tot if tot!=0 else float("nan")),
      float(np.mean([v[0] for _,v in vals[1:]])) if len(vals)>1 else float('nan'),
      float(np.mean([v[0] for _,v in vals[3:]])) if len(vals)>3 else float('nan')))
    p('  best 3 mints: %s'%[(m[:8],round(v[0],3),v[1]) for m,v in vals[:3]])
    line='  sensitivity: '
    for drop in (-0.30,-0.50,-1.00):
        for toll,tn in ((TOLL,'1.14'),(TOLL_HI,'2.5')):
            sm=sim_all(VA,spec,drop=drop,toll=toll)
            pr2,_,_=eval_sub(membership(r['f'],r['cell'],VA,BVA),sm)
            bw,_=eval_all(VA,sm)
            line+='[d%.0f t%s: %+.4f ctrl %+.4f] '%(drop*100,tn,float(np.mean([v[0] for v in pr2.values()])),float(np.mean(bw)))
    p(line)
p('\ndone'); O.close()
