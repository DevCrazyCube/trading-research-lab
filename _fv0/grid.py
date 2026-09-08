import numpy as np, sys, itertools, json, time
sys.path.insert(0,'/home/anont/meme/_fv0')
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}

THR={
 'volrel20':[0.3,0.6,1.0,1.5,2.5,4.0,8.0,16.0],
 'volrel5':[0.3,0.6,1.0,1.5,2.5,4.0,8.0,16.0],
 'volaccel':[0.2,0.5,1.0,2.0,4.0,8.0],
 'rangerel20':[0.25,0.5,1.0,2.0,4.0,8.0],
 'density20':[0.1,0.25,0.5,0.75,0.95],
 'gap_prev':[1.0,2.0,3.0,5.0,10.0,30.0,120.0],
 'eff20':[0.05,0.15,0.30,0.50,0.70,0.90],
 'rvol20':[0.002,0.005,0.01,0.02,0.05,0.10],
 'vwapdev20':[-0.30,-0.15,-0.05,0.0,0.05,0.15,0.30],
 'clsloc':[0.1,0.25,0.5,0.75,0.9],
 'ret5':[-0.40,-0.20,-0.08,0.0,0.08,0.20,0.40],
 'ret15':[-0.50,-0.25,-0.10,0.0,0.10,0.25,0.50],
 'notional20':[0.5,5.0,50.0,500.0,5000.0],
 'age_min':[5.0,15.0,60.0,240.0,1440.0],
 'volshare20':[0.05,0.10,0.20,0.35,0.60],
 'maxgap20':[1.0,2.0,5.0,15.0,60.0],
 'upvolfrac10':[0.2,0.35,0.5,0.65,0.8],
 'vol_now':[1.0,10.0,100.0,1000.0,10000.0],
 'range_now':[0.005,0.02,0.05,0.15,0.40],
 'ret1':[-0.20,-0.05,0.0,0.05,0.20],
}

PRIMS=[]
for f,ths in THR.items():
    for t in ths:
        PRIMS.append((f,'>',t)); PRIMS.append((f,'<=',t))

def pmask(p):
    f,op,t=p
    col=FEAT[:,FI[f]]
    return (col>t) if op=='>' else (col<=t)

def pname(p): return f'{p[0]}{p[1]}{p[2]:g}'

TR=(E_h==1); VA=(E_h==2)
IDX=np.arange(NE)

# ---------------- exit grid ----------------
EXITS=[]
for hidx,H in enumerate(HOR):
    EXITS.append((hidx,-1,-1,0))
for hidx in [HOR.index(x) for x in (5,10,15,30,60)]:
    for tpi in range(len(TPS)):
        EXITS.append((hidx,tpi,-1,0))
        EXITS.append((hidx,tpi,-1,1))
    for sli in range(len(SLS)):
        EXITS.append((hidx,-1,sli,0))
    for tpi in (1,2,3):
        for sli in (1,2):
            EXITS.append((hidx,tpi,sli,0))
            EXITS.append((hidx,tpi,sli,1))
CORE=[(HOR.index(h),-1,-1,0) for h in (3,5,10,15,30,60)]+[
  (HOR.index(15),2,-1,0),(HOR.index(15),3,-1,1),(HOR.index(15),-1,1,0),
  (HOR.index(15),2,1,0),(HOR.index(30),3,1,1),(HOR.index(5),0,0,0),
  (HOR.index(10),1,1,1),(HOR.index(60),3,2,0)]
print('n exits',len(EXITS),'n core',len(CORE),'n prims',len(PRIMS))

# control per (exit, split)
CTRL={}
def ctrl(ex,split):
    key=(ex,split)
    if key in CTRL: return CTRL[key]
    idx=IDX[TR] if split=='tr' else IDX[VA]
    r=evaluate(idx.tolist(),*ex)
    CTRL[key]=r
    return r

t0=time.time()
for ex in EXITS:
    ctrl(ex,'tr'); ctrl(ex,'va')
print('controls done',time.time()-t0)

combos=0
res=[]
def run(mask,label,exlist,split,minsupport=(20,50)):
    global combos
    idx=IDX[mask & (TR if split=='tr' else VA)]
    if len(idx)<minsupport[1]: return []
    il=idx.tolist()
    out=[]
    for ex in exlist:
        combos+=1
        r=evaluate(il,*ex)
        if r is None: continue
        if r['k']<minsupport[0] or r['n']<minsupport[1]: continue
        c=ctrl(ex,split)
        r['ex']=ex; r['label']=label
        r['dmed']=r['med']-c['med']; r['dmean']=r['mean']-c['mean']; r['dtrim']=r['trim']-c['trim']
        r['dfpos']=r['fpos']-c['fpos']
        out.append(r)
    return out

# ---------------- STAGE 1: single primitives ----------------
print('\n=== STAGE 1 ===')
s1=[]
pmasks={}
for p in PRIMS:
    m=pmask(p); pmasks[pname(p)]=(m,p)
    s1+=run(m,pname(p),EXITS,'tr')
print('stage1 evals',combos,'kept',len(s1),'t',time.time()-t0)
s1.sort(key=lambda r:-(r['dmed']))
print('--- top 40 by train dmed ---')
for r in s1[:40]:
    ex=r['ex']
    print(f"{r['label']:24s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} | med={r['med']*100:7.2f} dmed={r['dmed']*100:6.2f} mean={r['mean']*100:8.2f} dmean={r['dmean']*100:8.2f} trim={r['trim']*100:7.2f} dtrim={r['dtrim']*100:6.2f} fpos={r['fpos']*100:5.1f} k={r['k']} n={r['n']} res={r['res']*100:.1f}")

# rank primitives by best-of and by mean dmed across core exits
byprim={}
for r in s1:
    byprim.setdefault(r['label'],[]).append(r)
primscore=[]
for lab,rs in byprim.items():
    v=[x['dmed'] for x in rs]
    primscore.append((float(np.mean(v)),float(np.max(v)),lab,len(rs)))
primscore.sort(key=lambda x:-x[0])
print('\n--- primitives ranked by MEAN dmed across all exits ---')
for a,b,lab,n in primscore[:50]:
    print(f'{lab:26s} meandmed={a*100:7.2f} maxdmed={b*100:7.2f} nex={n}')
print('\n--- worst 20 (dead regions) ---')
for a,b,lab,n in primscore[-20:]:
    print(f'{lab:26s} meandmed={a*100:7.2f} maxdmed={b*100:7.2f} nex={n}')

np.save('/home/anont/meme/_fv0/primscore.npy',np.array([(x[2],x[0],x[1]) for x in primscore],dtype=object),allow_pickle=True)
import pickle
pickle.dump({'s1':[{k:v for k,v in r.items() if k not in('mm','sel')} for r in s1],'primscore':primscore,'combos':combos},
            open('/home/anont/meme/_fv0/stage1.pkl','wb'))
print('COMBOS',combos,'t',time.time()-t0)
