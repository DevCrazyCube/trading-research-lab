import pickle, time, math
import numpy as np
from collections import Counter, defaultdict
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/feat.txt','w')
def p(*a): print(*a,file=out); out.flush()

d=pickle.load(open(W+'/tapes.pkl','rb'))
T=d['T']; lab=d['lab']; hh=d['hh']

WINDOWS=[30,120,600]
FEATS=[]
for w in WINDOWS:
    for nm in ['rate','ub','ubgrow','vimb','bvol','topshr','repeat','newrate','meansz','ret']:
        FEATS.append(f'{nm}_{w}')
FEATS += ['prog','age','ntot','ubtot','solincurve']
NF=len(FEATS)
p('n features',NF,FEATS)

GLOBAL_END=1785861735
MINPRIOR=5
CAPW=400

rows_m=[]; rows_k=[]; X=[]
t0=time.time()
mints=sorted(T.keys())
for m in mints:
    D=T[m]
    bt=D['bt']; isb=D['isb'].astype(np.float64); sol=D['sol']/1e9
    vs=D['vs']; vt=D['vt']; tr=D['tr']
    n=len(bt)
    if n < MINPRIOR+2: continue
    price=vs/vt
    # trader ids
    ids={}
    tid=np.empty(n,dtype=np.int64)
    prev=np.full(n,-1,dtype=np.int64)
    lastseen={}
    for j,w_ in enumerate(tr):
        i=ids.get(w_)
        if i is None:
            i=len(ids); ids[w_]=i
        tid[j]=i
        prev[j]=lastseen.get(i,-1)
        lastseen[i]=j
    is_first=(prev<0).astype(np.float64)
    seen_before=(prev>=0).astype(np.float64)
    cs_first=np.concatenate([[0.],np.cumsum(is_first)])
    cs_seen=np.concatenate([[0.],np.cumsum(seen_before)])
    buysol=sol*isb; sellsol=sol*(1-isb)
    cs_buy=np.concatenate([[0.],np.cumsum(buysol)])
    cs_sell=np.concatenate([[0.],np.cumsum(sellsol)])
    cs_sol=np.concatenate([[0.],np.cumsum(sol)])
    # cumulative unique traders
    ubtot=np.cumsum(is_first)

    featw={}
    for Wn in WINDOWS:
        lo=np.searchsorted(bt, bt-Wn, side='right')      # first idx with bt> bt[k]-Wn
        lo2=np.searchsorted(bt, bt-2*Wn, side='right')
        cnt=np.arange(n)-lo+1
        rate=cnt/(Wn/60.0)
        bv=cs_buy[np.arange(n)+1]-cs_buy[lo]
        sv=cs_sell[np.arange(n)+1]-cs_sell[lo]
        tv=bv+sv
        vimb=np.where(tv>0,(bv-sv)/np.maximum(tv,1e-12),0.0)
        meansz=np.where(cnt>0,tv/np.maximum(cnt,1),0.0)
        nfirst=cs_first[np.arange(n)+1]-cs_first[lo]
        nseen=cs_seen[np.arange(n)+1]-cs_seen[lo]
        repeat=np.where(cnt>0,nseen/np.maximum(cnt,1),0.0)
        newrate=nfirst/(Wn/60.0)
        ret=price/np.maximum(price[lo],1e-300)-1.0
        # unique traders in window: two-pointer
        ub=np.zeros(n); cc=Counter(); l=0
        for k in range(n):
            cc[tid[k]]+=1
            while l<lo[k]:
                v=tid[l]; cc[v]-=1
                if cc[v]==0: del cc[v]
                l+=1
            ub[k]=len(cc)
        # unique traders in the PREVIOUS window [k-2W, k-W)
        ubprev=np.zeros(n); cc2=Counter(); l2=0; r2=0
        for k in range(n):
            while r2<lo[k]:
                cc2[tid[r2]]+=1; r2+=1
            while l2<lo2[k]:
                v=tid[l2]
                if v in cc2:
                    cc2[v]-=1
                    if cc2[v]==0: del cc2[v]
                l2+=1
            ubprev[k]=len(cc2)
        ubgrow=(ub+1.0)/(ubprev+1.0)
        # top buyer share of buy volume in window (recompute per k, capped)
        topshr=np.zeros(n)
        for k in range(n):
            a=max(lo[k], k-CAPW+1)
            if a>k: topshr[k]=0.; continue
            dd={}
            tot=0.0
            for j in range(a,k+1):
                if isb[j]>0:
                    v=tid[j]; dd[v]=dd.get(v,0.0)+sol[j]; tot+=sol[j]
            topshr[k]= (max(dd.values())/tot) if tot>0 else 0.0
        featw[Wn]=dict(rate=rate,ub=ub,ubgrow=ubgrow,vimb=vimb,bvol=np.log10(bv+1e-6),
                       topshr=topshr,repeat=repeat,newrate=newrate,meansz=meansz,ret=ret)

    prog=(vs-30e9)/(85e9-30e9)
    age=(bt-bt[0]).astype(np.float64)
    ntot=np.arange(1,n+1,dtype=np.float64)
    solincurve=(vs-30e9)/1e9

    for k in range(MINPRIOR, n-1):
        if bt[k+1] > GLOBAL_END: break
        rows_m.append(m); rows_k.append(k)
        v=[]
        for Wn in WINDOWS:
            fw=featw[Wn]
            for nm in ['rate','ub','ubgrow','vimb','bvol','topshr','repeat','newrate','meansz','ret']:
                v.append(fw[nm][k])
        v += [prog[k],age[k],ntot[k],ubtot[k],solincurve[k]]
        X.append(v)

X=np.asarray(X,dtype=np.float32)
p('decision points',X.shape,'elapsed %.1fs'%(time.time()-t0))
mi={m:i for i,m in enumerate(mints)}
DM=np.array([mi[m] for m in rows_m],dtype=np.int32)
DK=np.array(rows_k,dtype=np.int32)
p('unique mints with decision points',len(set(rows_m)))
hv=np.array([hh[m] for m in mints],dtype=np.int8)
p('train dp (h=1)',int((hv[DM]==1).sum()),'validate dp (h=2)',int((hv[DM]==2).sum()))
for i,f in enumerate(FEATS):
    c=X[:,i]
    p('%-12s p1=%.4g p25=%.4g p50=%.4g p75=%.4g p99=%.4g'%(f,*np.percentile(c,[1,25,50,75,99])))

np.savez_compressed(W+'/feats.npz',X=X,DM=DM,DK=DK,hv=hv,FEATS=np.array(FEATS),mints=np.array(mints))
p('saved')
out.close()
