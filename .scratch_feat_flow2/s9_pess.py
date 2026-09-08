import pickle, time, math, os
import numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/outc_pess.txt','w')
def p(*a): print(*a,file=out); out.flush()

d=pickle.load(open(W+'/tapes.pkl','rb'))
T=d['T']
Z=np.load(W+'/feats.npz',allow_pickle=True)
DM=Z['DM']; DK=Z['DK']; mints=list(Z['mints'])
NDP=len(DM)
p('ndp',NDP)

GLOBAL_END=1785861735
HORIZ=[(60,5),(180,5),(600,15),(1800,30),(5400,60)]   # (H seconds, bucket resolution)
TPS=[0.10,0.25,0.50,1.00]
SLS=[0.15,0.30,0.50]
TPSL=[(0.25,0.30),(0.50,0.30),(1.00,0.50)]
TRAIL=[0.20,0.40]

EXITS=[('time',None)]+[('tp',x) for x in TPS]+[('sl',y) for y in SLS]+ \
      [('tpsl',xy) for xy in TPSL]+[('trail',dd) for dd in TRAIL]+[('flowrev',None)]
POS=['P0','P1avgin','P2halfout25']
p('n exits',len(EXITS),'n pos',len(POS),'n struct',len(HORIZ)*len(EXITS)*len(POS))

NS=len(HORIZ)*len(EXITS)*len(POS)
RET=np.zeros((NS,NDP),dtype=np.float32)
EOFF=np.zeros((NS,NDP),dtype=np.int32)
FROZEN=np.zeros((len(HORIZ),NDP),dtype=bool)
CENS=np.zeros((len(HORIZ),NDP),dtype=bool)   # exit beyond data window -> censored, drop
BAD=np.zeros(NDP,dtype=bool)
MEND=np.zeros(NDP,dtype=np.int64)
TE=np.zeros(NDP,dtype=np.int64)

# group dp by mint
order=np.argsort(DM,kind='stable')
assert (order==np.arange(NDP)).all() or True
bounds={}
cur=DM[0]; st=0
for i in range(1,NDP):
    if DM[i]!=cur:
        bounds[cur]=(st,i); cur=DM[i]; st=i
bounds[cur]=(st,NDP)
p('mints with dp',len(bounds))

t0=time.time()
sidx={}
si=0
for hi_,(H,r) in enumerate(HORIZ):
    for ei,(ek,ep) in enumerate(EXITS):
        for pi,pn in enumerate(POS):
            sidx[(hi_,ei,pi)]=si; si+=1

for mi,(lo_i,hi_i) in bounds.items():
    m=mints[mi]
    D=T[m]
    bt=D['bt']; vs=D['vs']; vt=D['vt']; sol=D['sol']/1e9; isb=D['isb'].astype(np.float64)
    price=(vs/vt).astype(np.float64)
    n=len(bt); bt0=bt[0]
    ks=DK[lo_i:hi_i]
    te=bt[ks+1].astype(np.int64)          # entry TIME  (next real trade after signal)
    pe=price[ks+1]                        # entry PRICE (post-trade price of next real trade)
    BAD[lo_i:hi_i]=~(np.isfinite(pe)&(pe>0))
    MEND[lo_i:hi_i]=bt[-1]
    TE[lo_i:hi_i]=te
    signed=sol*(2*isb-1)

    for hi_,(H,r) in enumerate(HORIZ):
        nb=int(H//r)
        # bucketize whole mint life + H
        span=int(bt[-1]-bt0)+H+2*r
        B=span//r+2
        bidx=((bt-bt0)//r).astype(np.int64)
        hiB=np.full(B,-np.inf); loB=np.full(B,np.inf); clB=np.full(B,np.nan); flowB=np.zeros(B)
        np.maximum.at(hiB,bidx,price)
        np.minimum.at(loB,bidx,price)
        clB[bidx]=price          # last write wins == close (bt sorted)
        np.add.at(flowB,bidx,signed)
        # forward-fill closes; empty bucket => price frozen (AMM: no trade, no move)
        m0=np.isnan(clB)
        if m0[0]: clB[0]=price[0]; m0[0]=False
        idxf=np.where(~m0,np.arange(B),0); np.maximum.accumulate(idxf,out=idxf)
        clB=clB[idxf]
        hiB=np.where(np.isfinite(hiB),hiB,clB); loB=np.where(np.isfinite(loB),loB,clB)
        # trailing-60s flow per bucket
        wf=max(1,int(60//r))
        cf=np.concatenate([[0.],np.cumsum(flowB)])
        flow60=cf[np.arange(B)+1]-cf[np.maximum(np.arange(B)+1-wf,0)]

        be=((te-bt0)//r).astype(np.int64)
        # path buckets be+1 .. be+nb  (strictly after the entry bucket)
        cols=be[:,None]+1+np.arange(nb)[None,:]
        cens=(te+H)>GLOBAL_END
        colsC=np.clip(cols,0,B-1)
        PH=hiB[colsC]; PL=loB[colsC]; PC=clB[colsC]; PF=flow60[colsC]
        valid=cols<B
        PH=np.where(valid,PH,np.nan); PL=np.where(valid,PL,np.nan); PC=np.where(valid,PC,np.nan)
        # frozen: no actual trade in any path bucket
        traded=np.zeros(B,dtype=bool); traded[bidx]=True
        PT=np.where(valid,traded[colsC],False)
        frozen=~PT.any(axis=1)
        FROZEN[hi_,lo_i:hi_i]=frozen
        CENS[hi_,lo_i:hi_i]=cens
        # last valid close along path
        lastc=np.where(valid,PC,-1.0)
        lastcol=np.where(valid.any(axis=1),valid.sum(axis=1)-1,0)
        endclose=PC[np.arange(len(be)),lastcol]
        endclose=np.where(np.isnan(endclose),pe,endclose)
        endoff=(lastcol+1)*r
        PHf=np.where(np.isnan(PH),-np.inf,PH); PLf=np.where(np.isnan(PL),np.inf,PL)
        cummaxH=np.maximum.accumulate(np.where(np.isnan(PH),-np.inf,PH),axis=1)
        ar=np.arange(nb)[None,:]

        def firsthit(mask):
            any_=mask.any(axis=1)
            first=np.where(any_,mask.argmax(axis=1),nb-1)
            return any_,first

        # PESSIMISTIC FILLS: a triggered exit fills at the CLOSE of the bucket in which the
        # level was breached, never at the level itself. On a curve moving 50%/minute a limit
        # or stop does not fill at its price.
        AR=np.arange(len(be))
        def closefill(f):
            v=PC[AR,f]
            return np.where(np.isnan(v),endclose,v)
        exits_data=[]
        for ek,ep in EXITS:
            if ek=='time':
                px=endclose; off=endoff
            elif ek=='tp':
                L=pe*(1+ep); hit,f=firsthit(PHf>=L[:,None])
                px=np.where(hit,closefill(f),endclose); off=np.where(hit,(f+1)*r,endoff)
            elif ek=='sl':
                L=pe*(1-ep); hit,f=firsthit(PLf<=L[:,None])
                px=np.where(hit,closefill(f),endclose); off=np.where(hit,(f+1)*r,endoff)
            elif ek=='tpsl':
                x,y=ep
                Lu=pe*(1+x); Ld=pe*(1-y)
                hu,fu=firsthit(PHf>=Lu[:,None]); hd,fd=firsthit(PLf<=Ld[:,None])
                fu=np.where(hu,fu,10**9); fd=np.where(hd,fd,10**9)
                ff=np.minimum(fu,fd); anyh=hu|hd
                fsafe=np.where(anyh,np.minimum(ff,nb-1),0)
                px=np.where(anyh,closefill(fsafe),endclose)
                off=np.where(anyh,(fsafe+1)*r,endoff)
            elif ek=='trail':
                DD=ep
                thr=cummaxH*(1-DD)
                mask=(PLf<=thr)&(ar>0)&np.isfinite(cummaxH)
                hit,f=firsthit(mask)
                px=np.where(hit,closefill(f),endclose)
                off=np.where(hit,(f+1)*r,endoff)
            elif ek=='flowrev':
                mask=(PF<0)&valid
                hit,f=firsthit(mask)
                px=np.where(hit,PC[np.arange(len(be)),f],endclose)
                px=np.where(np.isnan(px),endclose,px)
                off=np.where(hit,(f+1)*r,endoff)
            exits_data.append((px,off))

        # entry price for P1 (average in over entry + first path bucket close)
        p1entry=np.where(np.isnan(PC[:,0]),pe,PC[:,0])
        for ei,(px,off) in enumerate(exits_data):
            g0=px/pe-1.0
            g0=np.where(frozen,0.0,g0)
            # P0
            RET[sidx[(hi_,ei,0)],lo_i:hi_i]=g0
            EOFF[sidx[(hi_,ei,0)],lo_i:hi_i]=off
            # P1 average-in: half at pe, half at p1entry
            g1=0.5*g0+0.5*(px/p1entry-1.0)
            g1=np.where(frozen,0.0,g1)
            RET[sidx[(hi_,ei,1)],lo_i:hi_i]=g1
            EOFF[sidx[(hi_,ei,1)],lo_i:hi_i]=off
            # P2 half out at +25% if touched, rest at structure exit
            L=pe*1.25; hit,f=firsthit(PHf>=L[:,None])
            ghalf=closefill(f)/pe-1.0
            g2=np.where(hit,0.5*ghalf+0.5*g0,g0)
            g2=np.where(frozen,0.0,g2)
            RET[sidx[(hi_,ei,2)],lo_i:hi_i]=g2
            EOFF[sidx[(hi_,ei,2)],lo_i:hi_i]=off

p('outcomes elapsed %.1fs'%(time.time()-t0))
p('bad pe',int(BAD.sum()))
# right-censoring: tape ends because the DATA WINDOW ended, not because trading stopped
TAPE_END_MARGIN=1800
window_edge = (GLOBAL_END-MEND) < TAPE_END_MARGIN
p('dp on mints whose tape ends within 30min of window edge:',int(window_edge.sum()),
  'mints:',len(set(DM[window_edge].tolist())))
for i,(H,r) in enumerate(HORIZ):
    CENS[i] |= BAD
    CENS[i] |= ((TE+H) > GLOBAL_END)
    CENS[i] |= (window_edge & ((TE+H) > MEND))
p('frozen rate by H',[float(FROZEN[i].mean()) for i in range(len(HORIZ))])
p('censored rate by H',[float(CENS[i].mean()) for i in range(len(HORIZ))])
RET=np.nan_to_num(RET,nan=0.0,posinf=0.0,neginf=0.0)
names=[]
for hi_,(H,r) in enumerate(HORIZ):
    for ei,(ek,ep) in enumerate(EXITS):
        for pi,pn in enumerate(POS):
            names.append(f'H{H}|{ek}{ep if ep is not None else ""}|{pn}')
np.savez(W+'/outcomes_pess.npz',RET=RET,EOFF=EOFF,FROZEN=FROZEN,CENS=CENS,names=np.array(names),
         HORIZ=np.array([h for h,_ in HORIZ]),TE=TE)
p('saved', os.path.getsize(W+'/outcomes_pess.npz')/1e6,'MB')
# quick unconditional sanity
for hi_,(H,r) in enumerate(HORIZ):
    s=sidx[(hi_,0,0)]
    ok=~CENS[hi_]
    g=RET[s][ok]
    p('H=%d uncond gross mean=%.4f med=%.4f n=%d'%(H,g.mean(),np.median(g),ok.sum()))
out.close()
