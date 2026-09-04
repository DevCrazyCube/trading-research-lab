"""Different search SHAPE: greedy forward selection of up to 5 stacked entry filters,
maximising TRAIN mint-equal mean, then honest evaluation of the selected stack on VALIDATE.
Also reports the 'least-bad composite' -- the best achievable filter stack -- because the
distance from that to zero is the real answer to 'can this universe be traded long'."""
import sys,time,collections,pickle
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np, fvh, common
W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'logG.txt','w',buffering=1)
def P(*a): OUT.write(' '.join(str(x) for x in a)+'\n')
T0=time.time()
E=common.build(log=P); greedy,ev=common.make_eval(E)
b=E.b; TRi=E.TRi; VAi=E.VAi; SN=E.SN; FN=E.FN; Fm=E.Fm
QC=[5,10,20,25,33,50,66,75,80,90,95]
CONDS=[]
for i in range(E.nf):
    v=Fm[i][TRi]
    cuts=sorted(set(np.percentile(v,QC).tolist()))
    cand=[]
    for c in cuts:
        cand.append((-np.inf,c,'<%.4g'%c)); cand.append((c,np.inf,'>=%.4g'%c))
    for a in range(len(cuts)):
        for z in range(a+1,len(cuts)): cand.append((cuts[a],cuts[z],'[%.4g,%.4g)'%(cuts[a],cuts[z])))
    keep=[];seen=set()
    for lo,hi,lab in cand:
        m=(v>=lo)&(v<hi); cnt=int(m.sum()); frac=cnt/TRi.size
        if cnt<250 or frac>0.80: continue
        h=hash(m.tobytes())
        if h in seen: continue
        seen.add(h); keep.append((lo,hi,lab,frac))
    keep.sort(key=lambda x:x[3])
    if len(keep)>16:
        step=len(keep)/16.0; keep=[keep[int(j*step)] for j in range(16)]
    for lo,hi,lab,frac in keep: CONDS.append((i,lo,hi,'%s%s'%(FN[i],lab)))
nC=len(CONDS)
P('conditions %d'%nC)
CTR=np.zeros((nC,TRi.size),bool); CVA=np.zeros((nC,VAi.size),bool)
for ci,(fi,lo,hi,lab) in enumerate(CONDS):
    CTR[ci]=(Fm[fi][TRi]>=lo)&(Fm[fi][TRi]<hi)
    CVA[ci]=(Fm[fi][VAi]>=lo)&(Fm[fi][VAi]<hi)
cfeat=[c[0] for c in CONDS]

STR=['H5/tpNone/slNone/f1.0','H10/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0',
     'H30/tpNone/slNone/f1.0','H15/tp0.3/sl-0.25/f1.0','H5/tp0.15/sl-0.25/f1.0',
     'H15/tp0.15/sl-0.25/f0.5','H60/tp0.3/slNone/f1.0']
combos=0
P('\n=== greedy forward selection (max TRAIN mint-equal mean), 5 steps ===')
results=[]
for s in STR:
    bt=ev(TRi,s); bv=ev(VAi,s)
    cur=np.ones(TRi.size,bool); chosen=[]; used=set()
    P('\n-- %s   base tr=%+.4f (k=%d)  base va=%+.4f (k=%d)'%(s,bt['mean'],bt['clusters'],bv['mean'],bv['clusters']))
    for step in range(5):
        best=None
        for ci in range(nC):
            if cfeat[ci] in used: continue
            m=cur&CTR[ci]
            cnt=int(m.sum())
            if cnt<80:
                combos+=1; continue
            combos+=1
            r=ev(TRi[m],s)
            if r is None or r['clusters']<25: continue
            if best is None or r['mean']>best[1]['mean']: best=(ci,r)
        if best is None: break
        ci,r=best
        cur=cur&CTR[ci]; chosen.append(ci); used.add(cfeat[ci])
        mv=np.ones(VAi.size,bool)
        for c in chosen: mv=mv&CVA[c]
        rv=ev(VAi[mv],s,boot=2000) if mv.sum()>0 else None
        P('  step%d + %-28s TRAIN mean=%+.4f med=%+.4f n=%d k=%d   | VALIDATE mean=%s med=%s lo=%s n=%s k=%s'%(
            step+1,CONDS[ci][3],r['mean'],r['median'],r['n'],r['clusters'],
            ('%+.4f'%rv['mean']) if rv else 'na',('%+.4f'%rv['median']) if rv else 'na',
            ('%+.4f'%rv['lo']) if rv else 'na',rv['n'] if rv else 0,rv['clusters'] if rv else 0))
        results.append((s,tuple(chosen),r['mean'],rv['mean'] if rv else float('nan'),
                        rv['lo'] if rv else float('nan'),rv['n'] if rv else 0,rv['clusters'] if rv else 0))
P('\ngreedy combos swept: %d  (%.1fs)'%(combos,time.time()-T0))

# same greedy but run ON VALIDATE to show the ceiling (in-sample on validate, NOT a candidate)
P('\n=== ceiling check: same greedy fit directly ON VALIDATE (in-sample, not a candidate) ===')
for s in ['H5/tpNone/slNone/f1.0','H15/tp0.3/sl-0.25/f1.0']:
    cur=np.ones(VAi.size,bool); used=set(); ch=[]
    for step in range(5):
        best=None
        for ci in range(nC):
            if cfeat[ci] in used: continue
            m=cur&CVA[ci]
            if int(m.sum())<80: continue
            r=ev(VAi[m],s)
            if r is None or r['clusters']<25: continue
            if best is None or r['mean']>best[1]['mean']: best=(ci,r)
        if best is None: break
        ci,r=best; cur=cur&CVA[ci]; ch.append(ci); used.add(cfeat[ci])
        P('  %s step%d + %-28s VALIDATE-in-sample mean=%+.4f med=%+.4f n=%d k=%d'%(
            s,step+1,CONDS[ci][3],r['mean'],r['median'],r['n'],r['clusters']))
pickle.dump(dict(results=results,CONDS=CONDS,combos=combos),open(W+'stageG.pkl','wb'))
P('GREEDY_DONE %.1fs'%(time.time()-T0))
OUT.close()
