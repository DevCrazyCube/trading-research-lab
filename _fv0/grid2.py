import numpy as np, sys, itertools, pickle, time
sys.path.insert(0,'/home/anont/meme/_fv0')
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
# coarse threshold set for pairing (replicate 0 = widest/coarsest)
THR2={
 'volrel20':[0.6,1.5,4.0,16.0],
 'volrel5':[0.6,1.5,4.0,16.0],
 'volaccel':[0.5,1.0,2.0,8.0],
 'rangerel20':[0.5,1.0,2.0,8.0],
 'density20':[0.1,0.25,0.5,0.95],
 'gap_prev':[1.0,2.0,5.0,30.0],
 'eff20':[0.15,0.30,0.50,0.90],
 'rvol20':[0.005,0.02,0.05,0.10],
 'vwapdev20':[-0.15,0.0,0.05,0.30],
 'clsloc':[0.1,0.5,0.75,0.9],
 'ret5':[-0.20,0.0,0.08,0.40],
 'ret15':[-0.25,0.0,0.10,0.50],
 'notional20':[5.0,50.0,500.0,5000.0],
 'age_min':[5.0,15.0,60.0,240.0],
 'volshare20':[0.05,0.20,0.35,0.60],
 'maxgap20':[1.0,2.0,5.0,15.0],
 'upvolfrac10':[0.2,0.5,0.8],
 'vol_now':[1.0,100.0,1000.0],
 'range_now':[0.005,0.05,0.40],
 'ret1':[-0.05,0.0,0.05],
}
PR=[]
for f,ths in THR2.items():
    for t in ths:
        PR.append((f,'>',t)); PR.append((f,'<=',t))
def pmask(p):
    c=FEAT[:,FI[p[0]]]
    return (c>p[2]) if p[1]=='>' else (c<=p[2])
def pn(p): return f'{p[0]}{p[1]}{p[2]:g}'
MASK={pn(p):pmask(p) for p in PR}
FEATOF={pn(p):p[0] for p in PR}
NAMES=[pn(p) for p in PR]
print('prims for pairing',len(NAMES))

TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
CORE=[(HOR.index(h),-1,-1,0) for h in (3,5,10,15,30,60)]+[
  (HOR.index(15),2,-1,0),(HOR.index(15),3,-1,1),(HOR.index(15),-1,1,0),
  (HOR.index(15),2,1,0),(HOR.index(30),3,1,1),(HOR.index(5),0,0,0),
  (HOR.index(10),1,1,1),(HOR.index(60),3,2,0)]
ALLEX=[]
for hidx,H in enumerate(HOR): ALLEX.append((hidx,-1,-1,0))
for hidx in [HOR.index(x) for x in (5,10,15,30,60)]:
    for tpi in range(len(TPS)):
        ALLEX.append((hidx,tpi,-1,0)); ALLEX.append((hidx,tpi,-1,1))
    for sli in range(len(SLS)): ALLEX.append((hidx,-1,sli,0))
    for tpi in (1,2,3):
        for sli in (1,2):
            ALLEX.append((hidx,tpi,sli,0)); ALLEX.append((hidx,tpi,sli,1))

CTRL={}
def ctrl(ex,split):
    k=(ex,split)
    if k not in CTRL:
        CTRL[k]=evaluate((IDX[TR] if split=='tr' else IDX[VA]).tolist(),*ex)
    return CTRL[k]
for ex in ALLEX: ctrl(ex,'tr'); ctrl(ex,'va')

combos=0
def sweep(mask,label,exlist,split,minK=25,minN=50):
    global combos
    idx=IDX[mask & (TR if split=='tr' else VA)]
    if len(idx)<minN:
        combos+=len(exlist); return []
    il=idx.tolist(); out=[]
    for ex in exlist:
        combos+=1
        r=evaluate(il,*ex)
        if r is None or r['k']<minK or r['n']<minN: continue
        c=ctrl(ex,split)
        r['ex']=ex; r['label']=label
        r['dmed']=r['med']-c['med']; r['dmean']=r['mean']-c['mean']; r['dtrim']=r['trim']-c['trim']
        out.append(r)
    return out

t0=time.time()
pairs=[]
for a,b in itertools.combinations(NAMES,2):
    if FEATOF[a]==FEATOF[b]: continue
    pairs.append((a,b))
print('pairs',len(pairs))

hits=[]; allres=[]
for n,(a,b) in enumerate(pairs):
    m=MASK[a]&MASK[b]
    rs=sweep(m,a+' & '+b,CORE,'tr')
    for r in rs:
        allres.append((r['dmean'],r['dtrim'],r['dmed'],r['mean'],r['trim'],r['med'],r['k'],r['n'],r['label'],r['ex']))
        if r['mean']>0 and r['trim']>0:
            hits.append(r)
    if n%2000==0: print(n,time.time()-t0,'combos',combos,'hits',len(hits))
print('PAIR STAGE combos',combos,'t',time.time()-t0)
print('train-positive-expectancy pairs:',len(hits))
hits.sort(key=lambda r:-r['trim'])
for r in hits[:60]:
    ex=r['ex']
    print(f"{r['label']:52s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} | mean={r['mean']*100:8.2f} trim={r['trim']*100:7.2f} med={r['med']*100:7.2f} dmean={r['dmean']*100:7.2f} dtrim={r['dtrim']*100:7.2f} k={r['k']} n={r['n']} res={r['res']*100:.1f}")

allres.sort(key=lambda x:-x[1])
print('\n--- top 40 pairs by dtrim (regardless of sign) ---')
for x in allres[:40]:
    print(f'{x[8]:52s} H={HOR[x[9][0]]:3d} tp={x[9][1]} sl={x[9][2]} pa={x[9][3]} | mean={x[3]*100:8.2f} trim={x[4]*100:7.2f} med={x[5]*100:7.2f} dtrim={x[1]*100:6.2f} k={x[6]} n={x[7]}')

pickle.dump({'hits':[{k:v for k,v in r.items() if k not in('mm','sel')} for r in hits],
             'combos':combos,'top':allres[:400]},open('/home/anont/meme/_fv0/stage2.pkl','wb'))
print('COMBOS',combos)
