import pickle,json,collections,hashlib,math,sys
import numpy as np
o=open('/home/anont/meme/.ff3/step9.txt','w')
tapes=pickle.load(open('/home/anont/meme/.ff3/tapes.pkl','rb'))
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
CUTOFF=437211659

bycreator=collections.defaultdict(list)
for bc,(mint,cr,cs,bt,comp,h) in allowed.items():
    if cr: bycreator[cr].append((cs,comp))
for cr in bycreator: bycreator[cr].sort()
def creator_prior(cr,cs):
    if not cr: return 0,0
    n=0;g=0
    for s,c in bycreator[cr]:
        if s<cs: n+=1; g+=(1 if c==1 else 0)
        else: break
    return n,g

WINS=[150,450,900]
HORS=[450,900,2250,4500]
TPS=[0.15,0.30,0.60,1.00]
SLS=[-0.20,-0.35,-0.50]
ADD=0.10
MAXDP=300
MODES=['S','L1']   # S = next-block fill (headline), L1 = one competing trade ahead
NF=['uniqbuy','buygrowth','imb','maxshare','repeat','newwal','meansz','rate','sellratio','netsol']
feat_names=['%s_%d'%(nm,W) for W in WINS for nm in NF]
meta_names=['age','prog','ddown','ntr','devsold','cprior','cpriorgrad','logpx','buyfrac_all','uniqwal_all']
allnames=feat_names+meta_names

R={}
def push(k,v):
    R.setdefault(k,[]).append(v)

nmode=len(MODES); nh=len(HORS); ntp=len(TPS); nsl=len(SLS)
F=[];MM=[];CU=[];HH=[]
ENT=np.empty((0,),dtype=np.int64)
ent=[[ ] for _ in range(nmode)]
val=[[[] for _ in range(nh)] for _ in range(nmode)]
rend=[[[] for _ in range(nh)] for _ in range(nmode)]
grad=[[[] for _ in range(nh)] for _ in range(nmode)]
tpp=[[[[] for _ in range(ntp)] for _ in range(nh)] for _ in range(nmode)]
tph=[[[[] for _ in range(ntp)] for _ in range(nh)] for _ in range(nmode)]
slp=[[[[] for _ in range(nsl)] for _ in range(nh)] for _ in range(nmode)]
slh=[[[[] for _ in range(nsl)] for _ in range(nh)] for _ in range(nmode)]
adp=[[[] for _ in range(nh)] for _ in range(nmode)]
adh=[[[] for _ in range(nh)] for _ in range(nmode)]
eslot=[[[] for _ in range(nh)] for _ in range(nmode)]
xslot=[[[] for _ in range(nh)] for _ in range(nmode)]

ncurve=0; nrows=0
for bc,tr0 in tapes.items():
    tr=[r for r in tr0 if not (r[10] or '').startswith('create')]
    n=len(tr)
    if n<6: continue
    mint,cr,cs,bt,comp,h=allowed[bc]
    slot=np.array([r[0] for r in tr],dtype=np.int64)
    vqb=np.array([r[4] for r in tr],dtype=np.float64)
    vqa=np.array([r[6] for r in tr],dtype=np.float64)
    vta=np.array([r[7] for r in tr],dtype=np.float64)
    rqa=np.array([(r[8] or 0) for r in tr],dtype=np.float64)
    px=vqa/np.maximum(vta,1.0)
    dq=(vqa-vqb)/1e9
    isbuy=dq>0
    sz=np.abs(dq)
    wal=[r[11] for r in tr]
    firstseen={};fs=np.zeros(n,dtype=np.int64)
    for i,w in enumerate(wal):
        if w not in firstseen: firstseen[w]=i
        fs[i]=firstseen[w]
    cprior,cpriorgrad=creator_prior(cr,cs)
    csold=np.zeros(n,dtype=bool); seen=False
    for i in range(n):
        if (not isbuy[i]) and wal[i]==cr: seen=True
        csold[i]=seen
    runmax=np.maximum.accumulate(px)
    cumbuy=np.cumsum(isbuy)
    cumuniq=np.cumsum(fs==np.arange(n))
    idxs=list(range(5,n-1))
    if len(idxs)>MAXDP:
        st=len(idxs)/MAXDP; idxs=[idxs[int(i*st)] for i in range(MAXDP)]
    if not idxs: continue
    ncurve+=1
    for k in idxs:
        sk=int(slot[k])
        f=[]
        for W in WINS:
            a=int(np.searchsorted(slot,sk-W,side='left')); b=k+1
            a2=int(np.searchsorted(slot,sk-2*W,side='left'))
            ib=isbuy[a:b]; ss=sz[a:b]; ww=wal[a:b]; ff=fs[a:b]
            buysol=float(ss[ib].sum()); sellsol=float(ss[~ib].sum())
            bw=set(); sw=set()
            for i in range(len(ww)):
                (bw if ib[i] else sw).add(ww[i])
            ub=len(bw); us=len(sw)
            ibp=isbuy[a2:a]; wwp=wal[a2:a]
            ubp=len(set(wwp[i] for i in range(len(wwp)) if ibp[i]))
            tot=buysol+sellsol
            f.append(float(ub)); f.append(ub/(ubp+1.0))
            f.append((buysol-sellsol)/tot if tot>0 else 0.0)
            if buysol>0:
                agg=collections.defaultdict(float); rep=0.0; new=0.0
                for i in range(len(ww)):
                    if ib[i]:
                        agg[ww[i]]+=float(ss[i])
                        if ff[i]<a: rep+=float(ss[i])
                        elif ff[i]==a+i: new+=float(ss[i])
                f.append(max(agg.values())/buysol); f.append(rep/buysol); f.append(new/buysol)
            else:
                f+= [0.0,0.0,0.0]
            ntr=b-a
            f.append(tot/ntr if ntr>0 else 0.0)
            f.append(1000.0*ntr/W)
            f.append(us/(ub+1.0))
            f.append(buysol-sellsol)
        meta=[float(sk-cs), float(rqa[k]/1e9), float(px[k]/runmax[k]), float(k+1),
              1.0 if csold[k] else 0.0, float(cprior), float(cpriorgrad),
              float(math.log(max(px[k],1e-30))), float(cumbuy[k])/(k+1.0), float(cumuniq[k])]
        # per-mode outcomes
        modeout=[]
        anyvalid=False
        for mi,mode in enumerate(MODES):
            if mode=='S':
                kk=k
                while kk+1<n and slot[kk+1]==slot[k]: kk+=1
                P=float(px[kk]); pstart=kk+1; entry_slot=sk+1
            else:
                if k+1>=n: modeout.append(None); continue
                e=k+1; P=float(px[e]); pstart=e+1; entry_slot=int(slot[e])
            if P<=0: modeout.append(None); continue
            if pstart<n:
                seg=px[pstart:]/P
                rmx=np.maximum.accumulate(seg); rmn=np.minimum.accumulate(seg); nrmn=-rmn
            else:
                seg=None
            rec=[]
            for hi,H in enumerate(HORS):
                if entry_slot+H>CUTOFF: rec.append(None); continue
                anyvalid=True
                if seg is None:
                    rec.append(dict(rend=0.0,grad=1 if comp==1 else 0,tp=[(-1,0.0)]*ntp,sl=[(-1,0.0)]*nsl,ad=(-1,0.0),xs=entry_slot+H))
                    continue
                j=int(np.searchsorted(slot,entry_slot+H,side='right'))-1
                if j<pstart:
                    rec.append(dict(rend=0.0,grad=1 if (comp==1 and pstart>=n) else 0,tp=[(-1,0.0)]*ntp,sl=[(-1,0.0)]*nsl,ad=(-1,0.0),xs=entry_slot+H))
                    continue
                L=j-pstart+1
                d=dict(rend=float(seg[L-1]-1.0),grad=1 if (comp==1 and j==n-1) else 0,xs=entry_slot+H)
                tl=[]
                for t,tp_ in enumerate(TPS):
                    p=int(np.searchsorted(rmx[:L],1.0+tp_,side='left'))
                    tl.append((p,float(seg[p]-1.0)) if p<L else (-1,0.0))
                d['tp']=tl
                sl_=[]
                for t,s_ in enumerate(SLS):
                    p=int(np.searchsorted(nrmn[:L],-(1.0+s_),side='left'))
                    sl_.append((p,float(seg[p]-1.0)) if p<L else (-1,0.0))
                d['sl']=sl_
                p=int(np.searchsorted(rmx[:L],1.0+ADD,side='left'))
                d['ad']=(p,float(seg[p])) if p<L else (-1,0.0)
                rec.append(d)
            modeout.append(rec)
        if not anyvalid: continue
        F.append(f); MM.append(meta); CU.append(bc); HH.append(h)
        nrows+=1
        for mi in range(nmode):
            rec=modeout[mi] if mi<len(modeout) else None
            for hi in range(nh):
                d=rec[hi] if rec else None
                if d is None:
                    val[mi][hi].append(False); rend[mi][hi].append(0.0); grad[mi][hi].append(0)
                    for t in range(ntp): tph[mi][hi][t].append(-1); tpp[mi][hi][t].append(0.0)
                    for t in range(nsl): slh[mi][hi][t].append(-1); slp[mi][hi][t].append(0.0)
                    adh[mi][hi].append(-1); adp[mi][hi].append(0.0)
                    eslot[mi][hi].append(0); xslot[mi][hi].append(0)
                else:
                    val[mi][hi].append(True); rend[mi][hi].append(d['rend']); grad[mi][hi].append(d['grad'])
                    for t in range(ntp): tph[mi][hi][t].append(d['tp'][t][0]); tpp[mi][hi][t].append(d['tp'][t][1])
                    for t in range(nsl): slh[mi][hi][t].append(d['sl'][t][0]); slp[mi][hi][t].append(d['sl'][t][1])
                    adh[mi][hi].append(d['ad'][0]); adp[mi][hi].append(d['ad'][1])
                    eslot[mi][hi].append(d['xs']-HORS[hi]); xslot[mi][hi].append(d['xs'])

np.savez_compressed('/home/anont/meme/.ff3/panel2.npz',
  X=np.array(F,dtype=np.float32),M=np.array(MM,dtype=np.float32),curves=np.array(CU),h=np.array(HH,dtype=np.int8),
  valid=np.array(val,dtype=bool),rend=np.array(rend,dtype=np.float32),grad=np.array(grad,dtype=np.int8),
  tph=np.array(tph,dtype=np.int32),tpp=np.array(tpp,dtype=np.float32),
  slh=np.array(slh,dtype=np.int32),slp=np.array(slp,dtype=np.float32),
  adh=np.array(adh,dtype=np.int32),adp=np.array(adp,dtype=np.float32),
  eslot=np.array(eslot,dtype=np.int64),xslot=np.array(xslot,dtype=np.int64),
  names=np.array(allnames),WINS=np.array(WINS),HORS=np.array(HORS),TPS=np.array(TPS),SLS=np.array(SLS),MODES=np.array(MODES))
o.write("curves %d rows %d\n"%(ncurve,nrows))
V=np.array(val); RE=np.array(rend); GR=np.array(grad)
for mi,mode in enumerate(MODES):
    for hi,H in enumerate(HORS):
        v=V[mi,hi]
        o.write("mode %s H=%d n=%d mean %.4f med %.4f p90 %.4f grad %.4f\n"%(mode,H,int(v.sum()),
          float(RE[mi,hi][v].mean()),float(np.median(RE[mi,hi][v])),float(np.percentile(RE[mi,hi][v],90)),float(GR[mi,hi][v].mean())))
o.close()
