import pickle,json,collections,hashlib,math,sys
import numpy as np
o=open('/home/anont/meme/.ff3/step8.txt','w')
tapes=pickle.load(open('/home/anont/meme/.ff3/tapes.pkl','rb'))
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
CUTOFF=437211659

# creator prior-create counts using ONLY allowed (h1,h2) mints
bycreator=collections.defaultdict(list)
for bc,(mint,cr,cs,bt,comp,h) in allowed.items():
    if cr: bycreator[cr].append((cs,comp))
for cr in bycreator: bycreator[cr].sort()
def creator_prior(cr,cs):
    if not cr: return 0,0
    lst=bycreator[cr]
    n=0; g=0
    for s,c in lst:
        if s<cs: n+=1; g+= (1 if c==1 else 0)
        else: break
    return n,g

WINS=[150,450,900]
HORS=[450,900,2250,4500]
TPS=[0.15,0.30,0.60,1.00]
SLS=[-0.20,-0.35,-0.50]
ADD=0.10
MAXDP=300

feat_names=[]
for W in WINS:
    for nm in ['uniqbuy','buygrowth','imb','maxshare','repeat','newwal','meansz','rate','sellratio','netsol']:
        feat_names.append('%s_%d'%(nm,W))
meta_names=['age','prog','ddown','ntr','devsold','cprior','cpriorgrad','pxlevel']
allnames=feat_names+meta_names

rows_feat=[]; rows_meta=[]
rows_curve=[]; rows_h=[]; rows_entry_slot=[]
rows_exit_slot=[[] for _ in HORS]
rows_rend=[[] for _ in HORS]
rows_tphit=[[[] for _ in TPS] for _ in HORS]   # index of first hit (relative) or -1
rows_slhit=[[[] for _ in SLS] for _ in HORS]
rows_tppx=[[[] for _ in TPS] for _ in HORS]
rows_slpx=[[[] for _ in SLS] for _ in HORS]
rows_addhit=[[] for _ in HORS]
rows_addpx=[[] for _ in HORS]
rows_grad=[[] for _ in HORS]
rows_valid=[[] for _ in HORS]

ncurve=0
for bc,tr0 in tapes.items():
    tr=[r for r in tr0 if not (r[10] or '').startswith('create')]
    n=len(tr)
    if n<6: continue
    mint,cr,cs,bt,comp,h=allowed[bc]
    slot=np.array([r[0] for r in tr],dtype=np.int64)
    vqb=np.array([r[4] for r in tr],dtype=np.float64)
    vqa=np.array([r[6] for r in tr],dtype=np.float64)
    vta=np.array([r[7] for r in tr],dtype=np.float64)
    rqa=np.array([r[8] if r[8] is not None else 0 for r in tr],dtype=np.float64)
    px=vqa/np.maximum(vta,1.0)
    dq=(vqa-vqb)/1e9
    isbuy=dq>0
    sz=np.abs(dq)
    wal=[r[11] for r in tr]
    # wallet first-seen index
    firstseen={}
    fs=np.zeros(n,dtype=np.int64)
    for i,w in enumerate(wal):
        if w not in firstseen: firstseen[w]=i
        fs[i]=firstseen[w]
    cprior,cpriorgrad=creator_prior(cr,cs)
    creator_sold=np.zeros(n,dtype=bool)
    seen=False
    for i in range(n):
        if (not isbuy[i]) and wal[i]==cr: seen=True
        creator_sold[i]=seen
    runmaxpx=np.maximum.accumulate(px)
    # decision points
    lo=5
    idxs=list(range(lo,n-1))
    if len(idxs)>MAXDP:
        stride=len(idxs)/MAXDP
        idxs=[idxs[int(i*stride)] for i in range(MAXDP)]
    if not idxs: continue
    ncurve+=1
    for k in idxs:
        e=k+1
        pe=px[e]
        if pe<=0: continue
        # ---- features from trades 0..k
        f=[]
        sk=slot[k]
        for W in WINS:
            a=np.searchsorted(slot,sk-W,side='left')
            b=k+1
            a2=np.searchsorted(slot,sk-2*W,side='left')
            seg=slice(a,b)
            ib=isbuy[seg]; ss=sz[seg]; ww=wal[a:b]; ff=fs[seg]
            bs=ss[ib]; sls_=ss[~ib]
            buysol=float(bs.sum()); sellsol=float(sls_.sum())
            bw=[ww[i] for i in range(len(ww)) if ib[i]]
            sw=[ww[i] for i in range(len(ww)) if not ib[i]]
            ub=len(set(bw)); us=len(set(sw))
            # prior window unique buyers
            ibp=isbuy[a2:a]; wwp=wal[a2:a]
            ubp=len(set(wwp[i] for i in range(len(wwp)) if ibp[i]))
            tot=buysol+sellsol
            f.append(float(ub))
            f.append(ub/(ubp+1.0))
            f.append((buysol-sellsol)/tot if tot>0 else 0.0)
            if buysol>0:
                agg=collections.defaultdict(float)
                for i in range(len(ww)):
                    if ib[i]: agg[ww[i]]+=float(ss[i])
                f.append(max(agg.values())/buysol)
                rep=sum(float(ss[i]) for i in range(len(ww)) if ib[i] and ff[i]<a)
                f.append(rep/buysol)
                new=sum(float(ss[i]) for i in range(len(ww)) if ib[i] and ff[i]>=a and ff[i]==a+i)
                f.append(new/buysol)
            else:
                f.append(0.0); f.append(0.0); f.append(0.0)
            ntr=b-a
            f.append(tot/ntr if ntr>0 else 0.0)
            f.append(1000.0*ntr/W)
            f.append(us/(ub+1.0))
            f.append(buysol-sellsol)
        meta=[float(sk-cs), float(rqa[k]/1e9), float(px[k]/runmaxpx[k]), float(k+1),
              1.0 if creator_sold[k] else 0.0, float(cprior), float(cpriorgrad), float(math.log(max(px[k],1e-30)))]
        # ---- forward paths
        jmax=np.searchsorted(slot,slot[e]+HORS[-1],side='right')-1
        if jmax<e: jmax=e
        seg=px[e:jmax+1]/pe
        rmax=np.maximum.accumulate(seg)
        rmin=np.minimum.accumulate(seg)
        nrmin=-rmin
        ok_any=False
        tmp_valid=[];tmp_exit=[];tmp_rend=[];tmp_grad=[]
        tmp_tph=[[] for _ in TPS];tmp_slh=[[] for _ in SLS];tmp_tpp=[[] for _ in TPS];tmp_slp=[[] for _ in SLS]
        tmp_addh=[];tmp_addp=[]
        for hi,H in enumerate(HORS):
            if slot[e]+H>CUTOFF:
                tmp_valid.append(False);tmp_exit.append(0);tmp_rend.append(0.0);tmp_grad.append(0)
                for t in range(len(TPS)): tmp_tph[t].append(-1); tmp_tpp[t].append(0.0)
                for t in range(len(SLS)): tmp_slh[t].append(-1); tmp_slp[t].append(0.0)
                tmp_addh.append(-1); tmp_addp.append(0.0)
                continue
            ok_any=True
            j=np.searchsorted(slot,slot[e]+H,side='right')-1
            if j<e: j=e
            L=j-e+1
            tmp_valid.append(True)
            tmp_exit.append(int(slot[e]+H))
            tmp_rend.append(float(seg[L-1]-1.0))
            tmp_grad.append(1 if (comp==1 and j==n-1) else 0)
            for t,tp in enumerate(TPS):
                p=int(np.searchsorted(rmax[:L],1.0+tp,side='left'))
                if p<L: tmp_tph[t].append(p); tmp_tpp[t].append(float(seg[p]-1.0))
                else: tmp_tph[t].append(-1); tmp_tpp[t].append(0.0)
            for t,sl in enumerate(SLS):
                p=int(np.searchsorted(nrmin[:L],-(1.0+sl),side='left'))
                if p<L: tmp_slh[t].append(p); tmp_slp[t].append(float(seg[p]-1.0))
                else: tmp_slh[t].append(-1); tmp_slp[t].append(0.0)
            p=int(np.searchsorted(rmax[:L],1.0+ADD,side='left'))
            if p<L: tmp_addh.append(p); tmp_addp.append(float(seg[p]))
            else: tmp_addh.append(-1); tmp_addp.append(0.0)
        if not ok_any: continue
        rows_feat.append(f); rows_meta.append(meta); rows_curve.append(bc); rows_h.append(h)
        rows_entry_slot.append(int(slot[e]))
        for hi in range(len(HORS)):
            rows_valid[hi].append(tmp_valid[hi]); rows_exit_slot[hi].append(tmp_exit[hi])
            rows_rend[hi].append(tmp_rend[hi]); rows_grad[hi].append(tmp_grad[hi])
            for t in range(len(TPS)): rows_tphit[hi][t].append(tmp_tph[t][hi]); rows_tppx[hi][t].append(tmp_tpp[t][hi])
            for t in range(len(SLS)): rows_slhit[hi][t].append(tmp_slh[t][hi]); rows_slpx[hi][t].append(tmp_slp[t][hi])
            rows_addhit[hi].append(tmp_addh[hi]); rows_addpx[hi].append(tmp_addp[hi])

X=np.array(rows_feat,dtype=np.float32)
M=np.array(rows_meta,dtype=np.float32)
curves=np.array(rows_curve)
hh=np.array(rows_h,dtype=np.int8)
es=np.array(rows_entry_slot,dtype=np.int64)
out={'X':X,'M':M,'curves':curves,'h':hh,'entry_slot':es,
     'valid':np.array(rows_valid,dtype=bool),'exit_slot':np.array(rows_exit_slot,dtype=np.int64),
     'rend':np.array(rows_rend,dtype=np.float32),'grad':np.array(rows_grad,dtype=np.int8),
     'tphit':np.array(rows_tphit,dtype=np.int32),'tppx':np.array(rows_tppx,dtype=np.float32),
     'slhit':np.array(rows_slhit,dtype=np.int32),'slpx':np.array(rows_slpx,dtype=np.float32),
     'addhit':np.array(rows_addhit,dtype=np.int32),'addpx':np.array(rows_addpx,dtype=np.float32),
     'names':np.array(allnames),'WINS':np.array(WINS),'HORS':np.array(HORS),'TPS':np.array(TPS),'SLS':np.array(SLS)}
np.savez_compressed('/home/anont/meme/.ff3/panel.npz',**out)
o.write("curves used %d, panel rows %d, feats %d\n"%(ncurve,X.shape[0],X.shape[1]))
import collections as C
o.write("rows by h %s\n"%dict(C.Counter(hh.tolist())))
o.write("curves by h %s\n"%dict(C.Counter(allowed[b][5] for b in set(rows_curve))))
for hi,H in enumerate(HORS):
    v=out['valid'][hi]
    o.write("H=%d valid rows %d curves %d meanret %.4f medret %.4f gradfrac %.4f\n"%(
        H,int(v.sum()),len(set(curves[v])),float(out['rend'][hi][v].mean()),float(np.median(out['rend'][hi][v])),float(out['grad'][hi][v].mean())))
o.write("feature names: %s\n"%allnames)
o.close()
