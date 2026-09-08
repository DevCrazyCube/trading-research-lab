import pickle, collections, gc
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
def cb(v,k,reps=2000,seed=3):
    v=np.asarray(v,float);k=np.asarray(k,np.int64)
    o=np.argsort(k,kind='stable');v=v[o];k=k[o]
    uk,st=np.unique(k,return_index=True); en=np.append(st[1:],len(k))
    n=len(uk); rng=np.random.default_rng(seed); mm=np.empty(reps)
    for r in range(reps):
        idx=rng.integers(0,n,n); mm[r]=np.concatenate([v[st[i]:en[i]] for i in idx]).mean()
    mm.sort(); return mm[int(.025*reps)],mm[int(.975*reps)]

HT=10; TOLL=0.0114
for LAT,tag in ((0,'NO-LATENCY (mirage: fill at signal post-price, exit 10 trades later)'),
                (2,'LATENCY-ADJ L=2 slots (fill at pool price 2 slots later, exit 10 trades AFTER the fill)'),
                (5,'LATENCY-ADJ L=5 slots (~2.1s)')):
    rows=[];jgt=0
    for m in mints:
        seq=by[m]; nn=len(seq)
        for i in range(nn):
            tr=seq[i]
            if tr[3]<=0 or m not in B or tr[4] not in TOP: continue
            if LAT==0: j=i
            else:
                j=i
                while j+1<nn and seq[j+1][0]<tr[0]+LAT: j+=1
            if j>i+HT: jgt+=1
            pen=seq[j][2]; e=j+HT
            resolved=e<nn
            pex=seq[e][2] if resolved else seq[nn-1][2]
            rows.append((mi[m],pex/pen-1-TOLL,resolved))
    res=sum(1 for r in rows if r[2])/len(rows)
    print('\n%s | n=%d clusters=%d resolution=%.4f | events where >%d trades landed before our fill: %d (%.4f)'%(
      tag,len(rows),len(set(r[0] for r in rows)),res,HT,jgt,jgt/len(rows)),flush=True)
    for dch in (None,-0.30,-0.50,-1.00):
        v=[];k=[]
        for r in rows:
            if r[2]: x=r[1]
            elif dch is None: continue
            else: x=dch
            v.append(x);k.append(r[0])
        a=np.array(v); lo,hi=cb(v,k)
        print('   drop=%-5s n=%5d clus=%4d mean %+8.3f%% median %+8.3f%% ci_mean[%+8.3f%%,%+8.3f%%]'%(
          'excl' if dch is None else '%.0f'%(100*dch),len(v),len(set(k)),100*a.mean(),100*np.median(a),100*lo,100*hi),flush=True)
