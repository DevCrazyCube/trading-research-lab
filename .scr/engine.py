"""Precompute per-entry-bar path outcomes (horizon-independent touch indices)."""
import pickle, math, os, sys
import numpy as np

SCR='/home/anont/meme/.scr/'
db=pickle.load(open(SCR+'db.pkl','rb'))
DB=db['DB']; FEATN=db['FEATN']; gmax=db['gmax']

TPS=[0.10,0.25,0.50,1.00,2.00]
SLS=[0.15,0.35,0.60]
TRS=[0.15,0.35]
ADDS=[0.20,0.40]
HS=[5,15,30,60,120,240]
WINDOW=240*60
INF=10**9

mints=sorted(DB.keys())
rows=[]           # global flat rows
per={}
for mint in mints:
    d=DB[mint]
    ts=d['ts']; op=d['op']; hi=d['hi']; lo=d['lo']; cl=d['cl']; vo=d['vo']
    n=len(ts)
    # launch features
    j=0
    while j+1<n and ts[j+1]<=ts[0]+900: j+=1
    lret=cl[j]/cl[0]-1
    lvol=math.log10(sum(vo[:j+1])+1)
    lmc0=math.log10(cl[0]*1e9+1)
    # last-bar index within each horizon, and time-exit index
    eidx=[[-1]*n for _ in HS]; lastidx=[[0]*n for _ in HS]
    for hk,H in enumerate(HS):
        p=0
        for a in range(n):
            if p<a: p=a
            lim=ts[a]+H*60
            while p+1<n and ts[p+1]<lim: p+=1
            lastidx[hk][a]=p
            eidx[hk][a]= p+1 if (p+1<n and ts[p+1]>=lim) else -1
    # path touches from entry bar a over 240m window
    ntp=len(TPS); nsl=len(SLS); ntr=len(TRS); nad=len(ADDS)
    TP=np.full((n,ntp),INF,dtype=np.int32)
    SL=np.full((n,nsl),INF,dtype=np.int32)
    TR=np.full((n,ntr),INF,dtype=np.int32)
    AD=np.full((n,nad),INF,dtype=np.int32)
    for a in range(n):
        P=op[a]
        if P<=0: continue
        lim=ts[a]+WINDOW
        tpt=[INF]*ntp; slt=[INF]*nsl; trt=[INF]*ntr; adt=[INF]*nad
        rmax=P
        ktp=0; ksl=0; kad=0
        done_tr=[False]*ntr
        j=a
        while j<n and ts[j]<=lim:
            h=hi[j]; l=lo[j]
            while ktp<ntp and h>=P*(1+TPS[ktp]):
                tpt[ktp]=j; ktp+=1
            while ksl<nsl and l<=P*(1-SLS[ksl]):
                slt[ksl]=j; ksl+=1
            while kad<nad and l<=P*(1-ADDS[kad]):
                adt[kad]=j; kad+=1
            for t in range(ntr):
                if not done_tr[t] and l<=rmax*(1-TRS[t]):
                    trt[t]=j; done_tr[t]=True
            if h>rmax: rmax=h
            if ktp>=ntp and ksl>=nsl and kad>=nad and all(done_tr): break
            j+=1
        TP[a]=tpt; SL[a]=slt; TR[a]=trt; AD[a]=adt
    per[mint]=dict(ts=np.array(ts,dtype=np.int64),op=np.array(op),hi=np.array(hi),lo=np.array(lo),
                   cl=np.array(cl),TP=TP,SL=SL,TR=TR,AD=AD,
                   eidx=np.array(eidx,dtype=np.int32),lastidx=np.array(lastidx,dtype=np.int32),
                   F=np.array(d['F']),MF=d['MF'],h=d['h'],
                   launch=(lret,lvol,lmc0))
    print(mint,n,file=sys.stderr)

with open(SCR+'paths.pkl','wb') as f:
    pickle.dump(dict(per=per,TPS=TPS,SLS=SLS,TRS=TRS,ADDS=ADDS,HS=HS,FEATN=FEATN,gmax=gmax),f)
print('done',len(per))
