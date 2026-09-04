import sys,time,csv,pickle,gc
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features

D='/home/anont/meme/research/midcap/featvol2/'
t0=time.time()
mints,data,nres=load()
book=Book(mints,data)
F=build_features(book)
N=book.N
BH=book.hh[book.MID]
TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
print("bars=%d mints=%d train_mints=%d val_mints=%d train_sig=%d val_sig=%d reserved_skipped=%d"%(
    N,book.nm,int((book.hh==1).sum()),int((book.hh==2).sum()),int(TRAIN.sum()),int(VAL.sum()),nres),flush=True)

FEATS=['vrel5','vrel20','vacc','rng','rngrel','dens10','dens30','gap','chop',
       'vwapdev','clspos','body','dvol','vshare','ret1','ret5','vzs','rngz','illiq','tickdir']
QS=[0.01,0.02,0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.95,0.98,0.99]
CONDS=[('>',0.90),('>',0.95),('>',0.98),('>',0.99),('<',0.10),('<',0.05),('<',0.02),('<',0.01),
       ('in',(0.80,0.95)),('in',(0.05,0.20)),('in',(0.35,0.65)),('in',(0.90,0.99)),('in',(0.01,0.10))]
TH={}
for f in FEATS:
    v=F[f][TRAIN]; v=v[np.isfinite(v)]
    TH[f]={q:float(np.quantile(v,q)) for q in QS}
pickle.dump(TH,open(D+'thresholds.pkl','wb'))

CB={};CN=[];COF={}
for f in FEATS:
    x=F[f];fin=np.isfinite(x)
    for op,arg in CONDS:
        if op=='>': m=fin&(x>TH[f][arg]); nm="%s>q%02d"%(f,int(arg*100))
        elif op=='<': m=fin&(x<TH[f][arg]); nm="%s<q%02d"%(f,int(arg*100))
        else:
            a,b=arg; m=fin&(x>=TH[f][a])&(x<=TH[f][b]); nm="%s@q%02d-%02d"%(f,int(a*100),int(b*100))
        CB[nm]=m;CN.append(nm);COF[nm]=f
print("conditions=%d"%len(CN),flush=True)

EXITS=[('H15',15,None,None,1.0),('H30',30,None,None,1.0),('H60',60,None,None,1.0),
       ('H120',120,None,None,1.0),('H15tp30',15,0.30,None,1.0),('H60tp60sl30',60,0.60,-0.30,1.0)]
EX={}
for nm,Hm,tp,sl,sc in EXITS:
    k=build_exit(book,Hm)
    if tp is None and sl is None:
        g=gross_returns(book,k,None,None)
    else:
        span=np.where(k>=0,k-np.arange(N),0)
        mw=int(min(max(3,span.max()+1),160))
        Rmax,Rmin,L=path_extremes(book,k,mw)
        g=gross_returns(book,k,tp,sl,sc,Rmax,Rmin,L)
        del Rmax,Rmin,L; gc.collect()
    EX[nm]=dict(k=k,net=netify(g,k,0.0114,-0.30),g=g,H=Hm,tp=tp,sl=sl,sc=sc)
    print("exit %s built t=%.1f"%(nm,time.time()-t0),flush=True)

R=Runner(book)
MIN_N=60;MIN_K=25
rows=[];combos=0
def ev(mask,exn):
    e=EX[exn]
    js=R.select(mask,e['k'])
    if js.size<MIN_N: return None
    st=R.stats(js,e['net'],e['k'])
    if st['clusters']<MIN_K: return None
    return st

for nm in CN:
    mask=CB[nm]&TRAIN
    if mask.sum()<MIN_N: continue
    for exn in EX:
        combos+=1
        st=ev(mask,exn)
        if st: rows.append((nm,'',exn,st['n'],st['clusters'],st['mean'],st['median'],st['res']))
print("singles: rows=%d combos=%d t=%.1f"%(len(rows),combos,time.time()-t0),flush=True)

nc=len(CN)
for a in range(nc):
    ma=CB[CN[a]]&TRAIN
    if ma.sum()<MIN_N: continue
    fa=COF[CN[a]]
    for b in range(a+1,nc):
        if COF[CN[b]]==fa: continue
        mask=ma&CB[CN[b]]
        if mask.sum()<MIN_N: continue
        for exn in EX:
            combos+=1
            st=ev(mask,exn)
            if st: rows.append((CN[a],CN[b],exn,st['n'],st['clusters'],st['mean'],st['median'],st['res']))
    if a%25==0: print("  pair a=%d/%d combos=%d rows=%d t=%.1f"%(a,nc,combos,len(rows),time.time()-t0),flush=True)

with open(D+'train_rows.csv','w',newline='') as fh:
    w=csv.writer(fh);w.writerow(['c1','c2','exit','n','k','mean','median','res'])
    for r in rows: w.writerow(r)
print("PAIRS DONE combos=%d rows=%d t=%.1f"%(combos,len(rows),time.time()-t0),flush=True)

# baselines on TRAIN: all-bar tiling per exit
with open(D+'train_baseline.csv','w',newline='') as fh:
    w=csv.writer(fh);w.writerow(['exit','n','k','mean','median','res'])
    for exn in EX:
        st=ev(TRAIN,exn)
        if st:
            w.writerow([exn,st['n'],st['clusters'],st['mean'],st['median'],st['res']])
            print("BASE %s n=%d k=%d mean=%.4f med=%.4f res=%.3f"%(exn,st['n'],st['clusters'],st['mean'],st['median'],st['res']),flush=True)
print("ALLDONE combos_swept=%d"%combos,flush=True)
