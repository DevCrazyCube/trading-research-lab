import pickle, collections, bisect, gc
import numpy as np
gc.disable()
SP='/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/'
tape=pickle.load(open(SP+'tape.pkl','rb'))
bt=pickle.load(open(SP+'blocktime.pkl','rb'))
split=pickle.load(open(SP+'h33_split.pkl','rb'))
B=set(split['B']); TOP=set(split['TOP'])
by=collections.defaultdict(list)
for (slot,ti,oi,ii,mint,bc,user,vqb,vtb,vqa,vta,name,e,ok) in tape:
    t=bt.get(slot)
    if t is None: continue
    dq=vqa-vqb
    by[mint].append((slot,t,vqa/vta,1 if dq>0 else (-1 if dq<0 else 0),user))
del tape
mints=sorted(by)
for m in mints: by[m].sort(key=lambda r:r[0])
mi={m:i for i,m in enumerate(mints)}

def cluster_boot(v,k,reps=2000,seed=3):
    v=np.asarray(v,dtype=np.float64); k=np.asarray(k,dtype=np.int64)
    order=np.argsort(k,kind='stable'); v=v[order]; k=k[order]
    uk,start=np.unique(k,return_index=True)
    end=np.append(start[1:],len(k))
    nC=len(uk); rng=np.random.default_rng(seed)
    mm=np.empty(reps); md=np.empty(reps)
    for r in range(reps):
        idx=rng.integers(0,nC,nC)
        parts=[v[start[i]:end[i]] for i in idx]
        s=np.concatenate(parts)
        mm[r]=s.mean(); md[r]=np.median(s)
    mm.sort(); md.sort()
    lo=int(.025*reps); hi=int(.975*reps)
    return mm[lo],mm[hi],md[lo],md[hi]

for lab,filt in (('ALL BUYS',lambda m,tr:True),('TOP-DECILE on held-out B',lambda m,tr: m in B and tr[4] in TOP)):
    v=[];k=[]
    for m in mints:
        seq=by[m]; nn=len(seq)
        for i in range(nn):
            tr=seq[i]
            if tr[3]<=0 or not filt(m,tr): continue
            j=i
            while j+1<nn and seq[j+1][0]<tr[0]+2: j+=1
            v.append(seq[j][2]/tr[2]-1.0); k.append(mi[m])
    a=np.array(v); lo,hi,mlo,mhi=cluster_boot(v,k,reps=1500)
    print('HAIRCUT c(L=2 slots) %-26s n=%6d clusters=%4d | mean %+.4f%% ci[%+.4f%%,%+.4f%%] | median %+.4f%% ci[%+.4f%%,%+.4f%%]'%(
      lab,len(v),len(set(k)),100*a.mean(),100*lo,100*hi,100*np.median(a),100*mlo,100*mhi),flush=True)

def trade_horizon(filt,HT,LAT,toll):
    rows=[]
    for m in mints:
        seq=by[m]; nn=len(seq)
        for i in range(nn):
            tr=seq[i]
            if tr[3]<=0 or not filt(m,tr): continue
            j=i
            while j+1<nn and seq[j+1][0]<tr[0]+LAT: j+=1
            p0=tr[2]; plat=seq[j][2]; e=i+HT
            resolved=e<nn
            pex=seq[e][2] if resolved else seq[nn-1][2]
            rows.append((mi[m],pex/p0-1-toll,pex/plat-1-toll,resolved))
    return rows
rows=trade_horizon(lambda m,tr: m in B and tr[4] in TOP,10,2,0.0114)
res=sum(1 for r in rows if r[3])/len(rows)
print('\nH=10 TRADES horizon (the earlier probe shape), TOP-DECILE on held-out B, toll=1.14%%  n=%d clusters=%d resolution=%.4f'%(
  len(rows),len(set(r[0] for r in rows)),res),flush=True)
print('  NOTE: a fixed TRADE-COUNT horizon conditions on continued trading, the repo-flagged inverting filter.',flush=True)
for tag,idx in (('NO-LATENCY(mirage)',1),('LATENCY-ADJ L=2',2)):
    for dch in (None,-0.30,-0.50,-1.00):
        v=[];k=[]
        for r in rows:
            if r[3]: x=r[idx]
            elif dch is None: continue
            else: x=dch
            v.append(x); k.append(r[0])
        a=np.array(v); lo,hi,mlo,mhi=cluster_boot(v,k,reps=2000)
        print('  %-20s drop=%-5s n=%5d clus=%4d mean %+8.3f%% median %+8.3f%% ci_mean[%+8.3f%%,%+8.3f%%]'%(
          tag,'excl' if dch is None else '%.0f'%(100*dch),len(v),len(set(k)),100*a.mean(),100*np.median(a),100*lo,100*hi),flush=True)
