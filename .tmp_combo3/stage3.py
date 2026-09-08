import sys, time, math, json, pickle, itertools
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *

t0=time.time(); O=open(D+'out_stage3.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1); VA=mints_of(2)
s2=pickle.load(open(D+'stage2.pkl','rb'))
TOPC=s2['top']; EDGES=s2['EDGES']; combos=s2['combos']
p('carry-in combos from stage1+2: %d'%combos)
p('entry cells entering the structure sweep: %d'%len(TOPC))

BTR={f:bin_of(TR,f,EDGES[f]) for f in EDGES}
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
    pw=[]; pr=[]; nt=0; nr=0
    for m,pos in memb.items():
        el=st['ELIG'][m]; net,netw,ex_ts,resv=sims[m]; ts=st['panel'][m]['ts']
        sw=0.0; sr=0.0; c=0; last=-1.0; rr=0
        for a in pos:
            e=int(el[a])+1
            if ts[e]<last: continue
            sw+=netw[e]; sr+=net[e]; c+=1; last=ex_ts[e]; rr+=1 if resv[e] else 0
        if c: pw.append(sw/c); pr.append(sr/c); nt+=c; nr+=rr
    return pw,pr,nt,nr

def eval_all(mints,sims):
    pw=[]; pr=[]; nt=0; nr=0
    for m in mints:
        el=st['ELIG'][m]; net,netw,ex_ts,resv=sims[m]; ts=st['panel'][m]['ts']
        sw=0.0; sr=0.0; c=0; last=-1.0; rr=0
        for a in range(len(el)):
            e=int(el[a])+1
            if ts[e]<last: continue
            sw+=netw[e]; sr+=net[e]; c+=1; last=ex_ts[e]; rr+=1 if resv[e] else 0
        if c: pw.append(sw/c); pr.append(sr/c); nt+=c; nr+=rr
    return pw,pr,nt,nr

HS=[2,3,5,10,15,20,30,45,60]; TPS=[None]+st['TPS']; SLS=[None]+st['SLS']; TRS=[None]+st['TRS']
POS=['flat','split3','dip3','str3']
GRID=[(H,tp,sl,tr,pos) for H in HS for tp in TPS for sl in SLS for tr in TRS for pos in POS]
p('structure grid: %d = H%d x TP%d x SL%d x TRAIL%d x POS%d'%(len(GRID),len(HS),len(TPS),len(SLS),len(TRS),len(POS)))
MEMB=[membership(c['f'],c['cell'],TR,BTR) for c in TOPC]
p('membership built t=%.1f'%(time.time()-t0))

res=[]; nsw=0; BASEG={}
for gi,spec in enumerate(GRID):
    sims=sim_all(TR,spec,drop=-0.30)
    bw,br,bn,bnr=eval_all(TR,sims); bs=stats(bw); base=bs[0]
    BASEG[spec]=dict(w=base,med=bs[1],n=bn,res=bnr/max(bn,1))
    for ci,c in enumerate(TOPC):
        pw,pr,nt,nr=eval_sub(MEMB[ci],sims); nsw+=1
        s=stats(pw)
        if s is None or s[4]<25 or nt<40: continue
        res.append(dict(ci=ci,f=c['f'],cell=c['cell'],spec=spec,w=s[0],med=s[1],k=s[4],se=s[3],
                        n=nt,base=base,t=tstat(s,base),tz=(s[0]/s[3] if s[3]>0 else 0.0),
                        res=nr/max(nt,1)))
    if gi%200==0: p('  grid %d/%d evals=%d t=%.1f'%(gi,len(GRID),nsw,time.time()-t0))
combos+=nsw+len(GRID)
p('structure-sweep evaluations %d ; TOTAL COMBOS SWEPT %d ; t=%.1f'%(nsw,combos,time.time()-t0))

p('\n=== UNCONDITIONAL STRUCTURE SURFACE (train, all bars = random entry control) ===')
def marg(keyf,name):
    d={}
    for spec,b in BASEG.items(): d.setdefault(keyf(spec),[]).append(b['w'])
    p('  %-9s : %s'%(name,' '.join('%s=%+.3f'%(k,np.mean(v)) for k,v in sorted(d.items(),key=lambda x:str(x[0])))))
marg(lambda s:s[0],'horizon'); marg(lambda s:s[1],'takeprofit'); marg(lambda s:s[2],'stoploss')
marg(lambda s:s[3],'trailing'); marg(lambda s:s[4],'position')
bb=sorted(BASEG.items(),key=lambda x:-x[1]['w'])
p('  best unconditional structures: '+' | '.join('%s %+.4f'%(str(k),v['w']) for k,v in bb[:5]))
p('  worst: '+' | '.join('%s %+.4f'%(str(k),v['w']) for k,v in bb[-3:]))
p('  unconditional structures with wmean>0: %d of %d'%(sum(1 for _,v in BASEG.items() if v['w']>0),len(BASEG)))

res.sort(key=lambda x:-x['tz'])
p('\n=== TRAIN: top 30 joint (entry x position x exit) by t-vs-ZERO ===')
for r in res[:30]:
    p('  %-26s c%-6d %-32s wmean=%+.4f med=%+.4f k=%3d n=%5d ctrl=%+.4f edge=%+.4f tz=%5.2f t=%5.2f res=%.2f'%(
      '/'.join(r['f'])[:26],r['cell'],str(r['spec']),r['w'],r['med'],r['k'],r['n'],r['base'],r['w']-r['base'],r['tz'],r['t'],r['res']))
p('\njoint combos with train wmean>0: %d of %d evaluated-and-sized'%(sum(1 for r in res if r['w']>0),len(res)))

FIN=[]; seen=set()
for r in res:
    if r['w']<=0: continue
    k=(r['f'],r['cell'],r['spec'])
    if k in seen: continue
    seen.add(k); FIN.append(r)
    if len(FIN)>=25: break
res2=sorted(res,key=lambda x:-x['t'])
for r in res2:
    k=(r['f'],r['cell'],r['spec'])
    if k in seen: continue
    seen.add(k); FIN.append(r)
    if len(FIN)>=35: break
p('\nfinalists carried to VALIDATE: %d'%len(FIN))

p('\n=== VALIDATE (h==2, train-fitted bin edges + train-selected structures, identical harness) ===')
p('%-24s %-30s %8s %8s %8s %5s %6s %8s %8s %7s'%('triple','structure','tr_w','va_w','va_med','k','n','ctrl','edge','p_boot'))
out=[]; bcache={}
for r in FIN:
    spec=r['spec']
    if spec not in bcache:
        sims=sim_all(VA,spec,drop=-0.30)
        bw,br,bn,bnr=eval_all(VA,sims); bcache[spec]=(sims,stats(bw)[0])
    sims,vbase=bcache[spec]
    memb=membership(r['f'],r['cell'],VA,BVA)
    pw,pr,nt,nr=eval_sub(memb,sims); s=stats(pw)
    if s is None:
        p('  %-24s %-30s NO VALIDATE DATA'%('/'.join(r['f'])[:24],str(spec))); continue
    lo,hi,pb=boot(pw,0.0)
    lo2,hi2,pc=boot(pw,vbase)
    out.append(dict(r=r,vw=s[0],vmed=s[1],vk=s[4],vn=nt,vres=nr/max(nt,1),vbase=vbase,
                    vt=tstat(s,vbase),vtz=(s[0]/s[3] if s[3]>0 else 0.0),p0=pb,pctrl=pc,lo=lo,hi=hi,
                    vraw=stats(pr)[0]))
    p('%-24s %-30s %+8.4f %+8.4f %+8.4f %5d %6d %+8.4f %+8.4f %7.4f'%(
      '/'.join(r['f'])[:24],str(spec),r['w'],s[0],s[1],s[4],nt,vbase,s[0]-vbase,pb))

p('\n--- validate summary ---')
p('finalists with validate wmean>0            : %d of %d'%(sum(1 for o in out if o['vw']>0),len(out)))
p('finalists with validate wmean>0 AND >ctrl  : %d'%sum(1 for o in out if o['vw']>0 and o['vw']>o['vbase']))
pv=[o['p0'] for o in out]; keep=bh(pv,0.10)
p('BH q=0.10 on validate p(mean>0) over %d finalists: %d survive'%(len(pv),len(keep)))
pv2=[o['pctrl'] for o in out]; keep2=bh(pv2,0.10)
p('BH q=0.10 on validate p(mean>random control): %d survive'%len(keep2))
p('SURVIVE BOTH + profitable: %d'%sum(1 for i,o in enumerate(out) if i in keep and i in keep2 and o['vw']>0))
for i,o in enumerate(out):
    if o['vw']>0:
        p('  VA-PROFITABLE %s %s vw=%+.4f raw=%+.4f med=%+.4f k=%d n=%d ci95=[%+.3f,%+.3f] p0=%.4f pctrl=%.4f BH0=%s BHc=%s'%(
          '/'.join(o['r']['f']),str(o['r']['spec']),o['vw'],o['vraw'],o['vmed'],o['vk'],o['vn'],
          o['lo'],o['hi'],o['p0'],o['pctrl'],i in keep,i in keep2))
pickle.dump(dict(res=res[:600],out=out,combos=combos,keep=list(keep),keep2=list(keep2),BASEG=BASEG),
            open(D+'stage3.pkl','wb'))
p('\nTOTAL COMBOS SWEPT (all stages): %d'%combos)
p('done t=%.1f'%(time.time()-t0)); O.close()
