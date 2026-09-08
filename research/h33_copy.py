import pickle, random, collections, bisect, gc
gc.disable()
SP='/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/'
tape=pickle.load(open(SP+'tape.pkl','rb'))
bt=pickle.load(open(SP+'blocktime.pkl','rb'))
split=pickle.load(open(SP+'h33_split.pkl','rb'))
B=set(split['B']); TOP=set(split['TOP'])
by=collections.defaultdict(list)
for (slot,ti,oi,ii,mint,bc,user,vqb,vtb,vqa,vta,name,ev,ok) in tape:
    t=bt.get(slot)
    if t is None: continue
    dq=vqa-vqb
    by[mint].append((slot,t,vqa/vta,1 if dq>0 else (-1 if dq<0 else 0),user))
del tape
mints=sorted(by)
for m in mints: by[m].sort(key=lambda r:r[0])
TEND=max(r[1] for m in mints for r in by[m])
def mean(v): return sum(v)/len(v)
def med(v): s=sorted(v); n=len(s); return s[n//2] if n%2 else 0.5*(s[n//2-1]+s[n//2])

def build(filt,H_sec,LAT):
    out=[]
    for m in mints:
        seq=by[m]; nn=len(seq); times=[r[1] for r in seq]
        for i in range(nn):
            tr=seq[i]
            if tr[3]<=0: continue
            if not filt(m,i,tr): continue
            if tr[1] > TEND - H_sec - 1800: continue
            p0=tr[2]; j=i
            while j+1<nn and seq[j+1][0] < tr[0]+LAT: j+=1
            plat=seq[j][2]
            tgt=tr[1]+H_sec
            k=bisect.bisect_right(times,tgt)-1
            if k<j: k=j
            pex=seq[k][2]
            resolved = bisect.bisect_right(times,tgt) < nn
            out.append((m,pex/p0-1.0,pex/plat-1.0,resolved))
    return out

def boot(vals,keys,reps=3000,seed=1):
    rnd=random.Random(seed); grp=collections.defaultdict(list)
    for v,k in zip(vals,keys): grp[k].append(v)
    ks=list(grp); n=len(ks); ms=[]
    for _ in range(reps):
        s=[]
        for _ in range(n): s.extend(grp[ks[rnd.randrange(n)]])
        ms.append(sum(s)/len(s))
    ms.sort(); return ms[int(.025*reps)],ms[int(.975*reps)]

def report(rows,label,toll):
    if not rows: print(label,'EMPTY',flush=True); return
    ms=set(r[0] for r in rows); res=sum(1 for r in rows if r[3])/len(rows)
    print('\n--- %s | toll=%.4f | n=%d clusters=%d resolution=%.4f'%(label,toll,len(rows),len(ms),res),flush=True)
    for tag,idx in (('NO-LATENCY(mirage)',1),('LATENCY-ADJ',2)):
        for dch in (None,-0.30,-0.50,-1.00):
            v=[];k=[]
            for r in rows:
                if r[3]: x=r[idx]-toll
                elif dch is None: continue
                else: x=dch
                v.append(x); k.append(r[0])
            if not v: continue
            lo,hi=boot(v,k)
            print('  %-20s drop=%-5s n=%5d clus=%4d mean %+8.3f%% median %+8.3f%% ci[%+8.3f%%,%+8.3f%%]'%(
              tag,'excl' if dch is None else '%.0f'%(100*dch),len(v),len(set(k)),
              100*mean(v),100*med(v),100*lo,100*hi),flush=True)

for LAT in (2,5):
  for H,hl in ((900,'15min'),(1800,'30min')):
    top=build(lambda m,i,tr: m in B and tr[4] in TOP,H,LAT)
    rnd=random.Random(5)
    ben=build(lambda m,i,tr: m in B and rnd.random()<0.03,H,LAT)
    for toll in (0.0114,0.030):
        report(top,'TOP-DECILE COPY H=%s LAT=%d slots'%(hl,LAT),toll)
        report(ben,'RANDOM-BUY BENCH H=%s LAT=%d slots'%(hl,LAT),toll)
