import sys,json,math
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
rng=np.random.default_rng(99)
o=open('/home/anont/meme/.ff3/confirm_out.txt','w',buffering=1)
TRAIN=(h==1); VAL=(h==2); TOLL=0.025; MI=0
NSW=[0]
def boot(per,B=3000):
    n=len(per)
    if n<5: return (float('nan'),float('nan'))
    idx=rng.integers(0,n,size=(B,n)); s=per[idx].mean(axis=1)
    return float(np.percentile(s,2.5)),float(np.percentile(s,97.5))

# --- A) decile table per flow feature, both splits, hold
o.write("=== A) DECILE MONOTONICITY (mint-equal, no-overlap, toll 2.5%%, mode S) ===\n")
o.write("feature | H | decile means TRAIN -> VALIDATE (d1=lowest .. d10=highest)\n")
mono=[]
for fi in range(NFLOW):
    col=FEAT[:,fi]; nm=str(names[fi])
    qs=[float(np.percentile(col[TRAIN],p)) for p in range(0,101,10)]
    for hi,H in enumerate(HORS):
        if H!=450 and H!=2250: continue
        tr=[];va=[]
        for d in range(10):
            lo,hiq=qs[d],qs[d+1]
            m=(col>=lo)&(col<=hiq) if d==9 else (col>=lo)&(col<hiq)
            a=evaluate(MI,hi,m&TRAIN,('hold',None,None),TOLL); NSW[0]+=1
            b=evaluate(MI,hi,m&VAL,('hold',None,None),TOLL); NSW[0]+=1
            tr.append(a['mean'] if a and a['k']>=20 else float('nan'))
            va.append(b['mean'] if b and b['k']>=20 else float('nan'))
        t=np.array(tr);v=np.array(va)
        ok=~np.isnan(t)&~np.isnan(v)
        if ok.sum()>=6:
            rc=float(np.corrcoef(t[ok],v[ok])[0,1])
            sp=float(np.nanmax(v)-np.nanmin(v))
            mono.append((abs(rc),rc,nm,H,sp,t.copy(),v.copy()))
mono.sort(key=lambda x:-x[0])
for _,rc,nm,H,sp,t,v in mono[:14]:
    o.write("%-18s H=%4d corr(tr,val)=%+.2f val-spread %.3f\n"%(nm,H,rc,sp))
    o.write("   TR: "+" ".join("%+.3f"%x for x in t)+"\n")
    o.write("   VA: "+" ".join("%+.3f"%x for x in v)+"\n")
o.write("swept %d\n"%NSW[0])

# --- B) every single flow condition, hold, BOTH splits
o.write("\n=== B) SINGLE FLOW CONDITIONS: train vs validate (hold) ===\n")
PS=[10,20,30,40,50,60,70,80,90]
rows=[]
for fi in range(NFLOW):
    col=FEAT[:,fi]; nm=str(names[fi])
    q={p:float(np.percentile(col[TRAIN],p)) for p in PS}
    for p in PS:
        for lab,m in (('>=q%d'%p,col>=q[p]),('<=q%d'%p,col<=q[p])):
            for hi,H in enumerate(HORS):
                a=evaluate(MI,hi,m&TRAIN,('hold',None,None),TOLL); NSW[0]+=1
                b=evaluate(MI,hi,m&VAL,('hold',None,None),TOLL); NSW[0]+=1
                if a is None or b is None or a['k']<40 or b['k']<40: continue
                rows.append((a['mean'],b['mean'],a['n'],b['n'],a['k'],b['k'],nm+lab,H))
T=np.array([r[0] for r in rows]); V=np.array([r[1] for r in rows])
o.write("n conditions %d ; corr(train_mean,val_mean)=%.3f\n"%(len(rows),float(np.corrcoef(T,V)[0,1])))
o.write("train>0 count %d ; val>0 count %d ; both>0 %d\n"%(int((T>0).sum()),int((V>0).sum()),int(((T>0)&(V>0)).sum())))
o.write("best VAL (ignoring train, i.e. what an oracle would pick):\n")
for i in np.argsort(-V)[:12]:
    r=rows[i]; o.write("   val %+.4f train %+.4f n %d k %d  %s H=%d\n"%(r[1],r[0],r[3],r[5],r[6],r[7]))
o.write("best TRAIN and its validate:\n")
for i in np.argsort(-T)[:12]:
    r=rows[i]; o.write("   train %+.4f -> val %+.4f n %d k %d  %s H=%d\n"%(r[0],r[1],r[3],r[5],r[6],r[7]))
both=[rows[i] for i in range(len(rows)) if T[i]>0 and V[i]>0]
o.write("conditions positive on BOTH splits: %d\n"%len(both))
for r in sorted(both,key=lambda x:-x[1]):
    a=evaluate(MI,[450,900,2250,4500].index(r[7]),None,None,TOLL) if False else None
    o.write("   train %+.4f val %+.4f n %d k %d  %s H=%d\n"%(r[0],r[1],r[3],r[5],r[6],r[7]))
o.write("swept %d\n"%NSW[0])

# --- C) CI on the both-positive set
o.write("\n=== C) cluster-bootstrap CI on both-positive conditions (validate) ===\n")
for r in sorted(both,key=lambda x:-x[1])[:20]:
    nm=r[6]; H=r[7]; hi=[450,900,2250,4500].index(H)
    base=nm
    for fi in range(NFLOW):
        if base.startswith(str(names[fi])):
            fnm=str(names[fi]); rest=base[len(fnm):]
            if rest[:2] in ('>=','<='):
                p=int(rest[3:]); col=FEAT[:,fi]; q=float(np.percentile(col[TRAIN],p))
                m=(col>=q) if rest[0]=='>' else (col<=q)
                break
    b=evaluate(MI,hi,m&VAL,('hold',None,None),TOLL)
    lo,hh2=boot(b['permint'])
    cu=evaluate(MI,hi,VAL,('hold',None,None),TOLL)
    o.write("   %s H=%d val %+.4f med %+.4f ci[%+.4f,%+.4f] ctrl %+.4f n %d k %d\n"%(nm,H,b['mean'],b['median'],lo,hh2,cu['mean'],b['n'],b['k']))
o.write("TOTAL SWEPT IN CONFIRM %d\n"%NSW[0])
o.close()
