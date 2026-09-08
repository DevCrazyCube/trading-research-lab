import numpy as np, sys, itertools, pickle, time
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']; VN=FI['vol_now']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)

print('=== liquidity census (h in 1,2 entries) ===')
for th in (0,10,50,100,300,1000,3000):
    m=FEAT[:,NN]>=th
    mm=set(E_mint[m].tolist())
    print(f'notional20>={th:6.0f}: entries={int(m.sum()):6d} mints={len(mm):4d} trainE={int((m&TR).sum()):6d} valE={int((m&VA).sum()):6d}')

FLOOR=300.0   # $300/min median volume -> a $60 clip is 20% of one minute
FEAS=FEAT[:,NN]>=FLOOR
print('FEASIBLE floor',FLOOR,'entries',int(FEAS.sum()),'mints',len(set(E_mint[FEAS].tolist())))

THR={
 'volrel20':[0.3,0.6,1.0,1.5,2.5,4.0,8.0],
 'volrel5':[0.3,0.6,1.0,1.5,2.5,4.0,8.0],
 'volaccel':[0.2,0.5,1.0,2.0,4.0],
 'rangerel20':[0.25,0.5,1.0,2.0,4.0],
 'density20':[0.25,0.5,0.75,0.95],
 'gap_prev':[1.0,2.0,3.0,5.0],
 'eff20':[0.05,0.15,0.30,0.50,0.70,0.90],
 'rvol20':[0.002,0.005,0.01,0.02,0.05],
 'vwapdev20':[-0.15,-0.05,0.0,0.05,0.15],
 'clsloc':[0.1,0.25,0.5,0.75,0.9],
 'ret5':[-0.20,-0.08,0.0,0.08,0.20],
 'ret15':[-0.25,-0.10,0.0,0.10,0.25],
 'age_min':[15.0,60.0,240.0,1440.0],
 'volshare20':[0.05,0.10,0.20,0.35],
 'maxgap20':[1.0,2.0,5.0],
 'upvolfrac10':[0.2,0.35,0.5,0.65,0.8],
 'range_now':[0.005,0.02,0.05,0.15],
 'ret1':[-0.05,0.0,0.05],
}
PR=[]
for f,ths in THR.items():
    for t in ths: PR.append((f,'>',t)); PR.append((f,'<=',t))
def pmask(p):
    c=FEAT[:,FI[p[0]]]
    return (c>p[2]) if p[1]=='>' else (c<=p[2])
def pn(p): return f'{p[0]}{p[1]}{p[2]:g}'
MASK={pn(p):pmask(p) for p in PR}; FEATOF={pn(p):p[0] for p in PR}; NAMES=[pn(p) for p in PR]
print('prims',len(NAMES))

ALLEX=[]
for hidx,H in enumerate(HOR): ALLEX.append((hidx,-1,-1,0))
for hidx in [HOR.index(x) for x in (3,5,10,15,30,60)]:
    for tpi in range(len(TPS)):
        ALLEX.append((hidx,tpi,-1,0)); ALLEX.append((hidx,tpi,-1,1))
    for sli in range(len(SLS)): ALLEX.append((hidx,-1,sli,0))
    for tpi in (0,1,2,3):
        for sli in (0,1,2):
            ALLEX.append((hidx,tpi,sli,0)); ALLEX.append((hidx,tpi,sli,1))
CORE=[(HOR.index(h),-1,-1,0) for h in (3,5,10,15,30,60)]+[
 (HOR.index(5),0,0,0),(HOR.index(5),1,1,0),(HOR.index(10),0,0,0),(HOR.index(10),1,1,1),
 (HOR.index(15),2,1,0),(HOR.index(15),3,-1,1),(HOR.index(15),-1,1,0),(HOR.index(30),3,1,1),
 (HOR.index(5),0,-1,0),(HOR.index(3),0,0,0)]
print('exits',len(ALLEX),'core',len(CORE))

CTRL={}
def ctrl(ex,split,base):
    k=(ex,split,base)
    if k not in CTRL:
        bm=FEAS if base else np.ones(NE,bool)
        CTRL[k]=evaluate(IDX[bm&(TR if split=='tr' else VA)].tolist(),*ex,full=True)
    return CTRL[k]
for ex in ALLEX:
    ctrl(ex,'tr',True); ctrl(ex,'va',True)
print('\n=== FEASIBLE-universe unconditional control ===')
for ex in [(HOR.index(h),-1,-1,0) for h in (3,5,10,15,30,60)]:
    a=ctrl(ex,'tr',True); b=ctrl(ex,'va',True)
    print(f"H={HOR[ex[0]]:3d} TRAIN mean={a['mean']*100:8.2f} trim={a['trim']*100:7.2f} med={a['med']*100:7.2f} k={a['k']} n={a['n']} | VAL mean={b['mean']*100:8.2f} trim={b['trim']*100:7.2f} med={b['med']*100:7.2f} k={b['k']} n={b['n']}")

combos=0
def sweep(mask,label,exlist,split,minK=20,minN=60):
    global combos
    idx=IDX[mask&FEAS&(TR if split=='tr' else VA)]
    if len(idx)<minN: combos+=len(exlist); return []
    il=idx.tolist(); out=[]
    for ex in exlist:
        combos+=1
        r=evaluate(il,*ex)
        if r is None or r['k']<minK or r['n']<minN: continue
        c=ctrl(ex,split,True)
        r['ex']=ex; r['label']=label
        r['dmean']=r['mean']-c['mean']; r['dtrim']=r['trim']-c['trim']; r['dmed']=r['med']-c['med']
        out.append(r)
    return out

t0=time.time()
print('\n=== STAGE 3a: single prims inside FEASIBLE, all exits ===')
s1=[]
for p in PR: s1+=sweep(MASK[pn(p)],pn(p),ALLEX,'tr')
print('combos',combos,'kept',len(s1),'t',time.time()-t0)
pos=[r for r in s1 if r['mean']>0 and r['trim']>0]
print('train positive-expectancy singles:',len(pos))
pos.sort(key=lambda r:-r['trim'])
for r in pos[:25]:
    ex=r['ex']
    print(f"{r['label']:22s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} mean={r['mean']*100:7.2f} trim={r['trim']*100:6.2f} med={r['med']*100:7.2f} dtrim={r['dtrim']*100:6.2f} k={r['k']} n={r['n']}")

print('\n=== STAGE 3b: pairs inside FEASIBLE, core exits ===')
pairs=[(a,b) for a,b in itertools.combinations(NAMES,2) if FEATOF[a]!=FEATOF[b]]
print('pairs',len(pairs))
s2=[]
for i,(a,b) in enumerate(pairs):
    s2+=sweep(MASK[a]&MASK[b],a+' & '+b,CORE,'tr')
    if i%3000==0: print(i,round(time.time()-t0,1),'combos',combos)
pos2=[r for r in s2 if r['mean']>0 and r['trim']>0]
print('combos',combos,'kept',len(s2),'train positive pairs',len(pos2),'t',time.time()-t0)
pos2.sort(key=lambda r:-r['trim'])
for r in pos2[:30]:
    ex=r['ex']
    print(f"{r['label']:46s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} mean={r['mean']*100:7.2f} trim={r['trim']*100:6.2f} med={r['med']*100:7.2f} dtrim={r['dtrim']*100:6.2f} k={r['k']} n={r['n']}")

print('\n=== STAGE 3c: triples from top-24 pair-legs, core exits ===')
legcount={}
for r in pos2:
    for lg in r['label'].split(' & '): legcount[lg]=legcount.get(lg,0)+1
top=[x[0] for x in sorted(legcount.items(),key=lambda kv:-kv[1])[:24]]
print('triple legs',top)
s3=[]
tri=[t for t in itertools.combinations(top,3) if len({FEATOF[x] for x in t})==3]
print('triples',len(tri))
for t in tri:
    s3+=sweep(MASK[t[0]]&MASK[t[1]]&MASK[t[2]],' & '.join(t),CORE,'tr')
pos3=[r for r in s3 if r['mean']>0 and r['trim']>0]
print('combos',combos,'train positive triples',len(pos3),'t',time.time()-t0)
pos3.sort(key=lambda r:-r['trim'])
for r in pos3[:20]:
    ex=r['ex']
    print(f"{r['label']:62s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} mean={r['mean']*100:7.2f} trim={r['trim']*100:6.2f} k={r['k']} n={r['n']}")

pickle.dump({'pos':[{k:v for k,v in r.items() if k not in('mm','sel')} for r in pos+pos2+pos3],
             'combos':combos,'floor':FLOOR},open('/home/anont/meme/_fv0/stage3.pkl','wb'))
print('STAGE3 COMBOS',combos)
