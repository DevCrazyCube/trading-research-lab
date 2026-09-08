import sys,json,math,time
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
rng=np.random.default_rng(777)
o=open('/home/anont/meme/.ff3/val_out.txt','w',buffering=1)
TRAIN=(h==1); VAL=(h==2)
TOLL=0.025; MI=0; MINN=200; MINK=40
PS=[10,20,30,40,50,60,70,80,90]
BANDS=[(10,50),(50,90),(30,70),(70,95),(80,99),(1,20),(0,10),(90,100)]
cmap={}
for fi in range(NFLOW):
    col=FEAT[:,fi]; tr=col[TRAIN]
    q={p:float(np.percentile(tr,p)) for p in set(PS+[0,1,95,99,100])}
    nm=str(names[fi])
    for p in PS:
        v=q[p]
        cmap['%s>=q%d(%.6g)'%(nm,p,v)]=col>=v
        cmap['%s<=q%d(%.6g)'%(nm,p,v)]=col<=v
    for a,b in BANDS:
        va,vb=q[a],q[b]
        if vb>va: cmap['%s@q%d-q%d[%.6g,%.6g]'%(nm,a,b,va,vb)]=(col>=va)&(col<=vb)
MC={}
for j in range(len(names)-NFLOW):
    fi=NFLOW+j; nm=str(names[fi]); col=FEAT[:,fi]; tr=col[TRAIN]
    u=np.unique(tr)
    if len(u)<=3:
        for v in u: MC['%s==%g'%(nm,v)]=col==v
        continue
    q33,q66,q50,q80,q20=[float(np.percentile(tr,p)) for p in (33,66,50,80,20)]
    MC['%s<=q33'%nm]=col<=q33; MC['%s@q33-q66'%nm]=(col>q33)&(col<=q66); MC['%s>q66'%nm]=col>q66
    MC['%s<=q50'%nm]=col<=q50; MC['%s>q50'%nm]=col>q50; MC['%s>q80'%nm]=col>q80; MC['%s<=q20'%nm]=col<=q20
def getmask(cn,mn):
    m=cmap[cn].copy()
    if mn is not None: m&= (cmap[mn] if mn in cmap else MC[mn])
    return m

def boot(per,B=2000):
    n=len(per)
    if n<5: return (float('nan'),float('nan'))
    idx=rng.integers(0,n,size=(B,n))
    s=per[idx].mean(axis=1)
    return float(np.percentile(s,2.5)),float(np.percentile(s,97.5))

cands=json.load(open('/home/anont/meme/.ff3/res4.json'))
o.write("finalist candidates from train: %d\n"%len(cands))
out=[]
CTRLC={}
for mean,med,n,k,hi,cn,mn,st in cands[:120]:
    st=(st[0],st[1],st[2])
    m=getmask(cn,mn)
    rv=evaluate(MI,hi,m&VAL,st,TOLL)
    if rv is None or rv['n']<80 or rv['k']<25: continue
    key=(hi,st[0],st[1],st[2])
    if key not in CTRLC:
        CTRLC[key]=evaluate(MI,hi,VAL,st,TOLL)
    cu=CTRLC[key]
    lo,hiCI=boot(rv['permint'])
    # n-matched random control
    rate=float((m&VAL).sum())/float(VAL.sum())
    ms=[]
    for _ in range(30):
        rm=(rng.random(NR)<rate)&VAL
        rr=evaluate(MI,hi,rm,st,TOLL)
        if rr: ms.append(rr['mean'])
    rc=float(np.mean(ms)) if ms else float('nan')
    rvl=evaluate(MI,hi,m&VAL,st,0.0114)
    # latency mode sensitivity
    rl1=evaluate(1,hi,m&VAL,st,TOLL)
    # grad charge sensitivity
    gs={}
    for gc in (-0.30,-0.50,-1.00):
        rg=evaluate(MI,hi,m&VAL,st,TOLL,gradcharge=gc)
        gs[gc]=rg['mean'] if rg else float('nan')
    out.append(dict(cn=cn,mn=mn,hi=hi,st=st,train_mean=mean,train_med=med,train_n=n,train_k=k,
        val_mean=rv['mean'],val_med=rv['median'],val_n=rv['n'],val_k=rv['k'],
        ci_lo=lo,ci_hi=hiCI,ctrl_uncond=cu['mean'],ctrl_rand=rc,
        val_mean_toll114=rvl['mean'] if rvl else None,
        val_mean_lat1=rl1['mean'] if rl1 else None,
        gradfrac=rv['gradfrac'],grad30=gs[-0.30],grad50=gs[-0.50],grad100=gs[-1.00]))
out.sort(key=lambda d:-(d['val_mean']))
o.write("\n=== VALIDATE (h==2), mode S, toll 2.5%% ===\n")
for d in out:
    o.write("val %+.4f med %+.4f n %5d k %4d | ci[%+.4f,%+.4f] | ctrl_unc %+.4f ctrl_rand %+.4f | train %+.4f | toll1.14 %+.4f | lat1 %+.4f | gradf %.3f g30 %+.4f g50 %+.4f g100 %+.4f | H=%d %s | %s & %s\n"%(
      d['val_mean'],d['val_med'],d['val_n'],d['val_k'],d['ci_lo'],d['ci_hi'],d['ctrl_uncond'],d['ctrl_rand'],d['train_mean'],
      d['val_mean_toll114'] or float('nan'),d['val_mean_lat1'] or float('nan'),d['gradfrac'],d['grad30'],d['grad50'],d['grad100'],
      HORS[d['hi']],d['st'],d['cn'],d['mn']))
surv=[d for d in out if d['val_mean']>0 and d['ci_lo']>0 and d['val_mean']>d['ctrl_rand'] and d['train_mean']>0]
o.write("\nSURVIVORS (val_mean>0, CI-lo>0, > random control, train>0): %d\n"%len(surv))
for d in surv: o.write(json.dumps(d,default=str)+"\n")
json.dump(out,open('/home/anont/meme/.ff3/val_out.json','w'),default=str)
o.close()
