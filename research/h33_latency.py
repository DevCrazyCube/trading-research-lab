import pickle, statistics, random, collections, bisect, gc, sys
gc.disable()
SP='/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/'
tape=pickle.load(open(SP+'tape.pkl','rb'))
bt=pickle.load(open(SP+'blocktime.pkl','rb'))
by=collections.defaultdict(list)
miss=0
for (slot,ti,oi,ii,mint,bc,user,vqb,vtb,vqa,vta,name,ev,ok) in tape:
    t=bt.get(slot)
    if t is None: miss+=1; continue
    dq=vqa-vqb
    by[mint].append((slot,t,vqa/vta,1 if dq>0 else (-1 if dq<0 else 0),user))
del tape
mints=sorted(by)
for m in mints: by[m].sort(key=lambda r:r[0])
print('missing_blocktime',miss,'mints',len(mints),'trades',sum(len(v) for v in by.values()),flush=True)
T=[r[1] for m in mints for r in by[m]]
TLO,TEND=min(T),max(T)
print('time range',TLO,TEND,'span_days %.2f'%((TEND-TLO)/86400),flush=True)
h=collections.Counter(int((r[1]-TLO)//86400) for m in mints for r in by[m])
print('trades per day-index',sorted(h.items()),flush=True)
print('total buys',sum(1 for m in mints for r in by[m] if r[3]>0),flush=True)
del T

LS=[1,2,3,5,8,12]
def q(sv,p): return sv[min(len(sv)-1,max(0,int(p*len(sv))))]
def mean(v): return sum(v)/len(v)

def measure(filt,label,dump=None):
    gaps=[];cs={L:[] for L in LS};dead60=0;nonext=0;n=0;cl=set();ev=[]
    for m in mints:
        seq=by[m]; nn=len(seq); times=[r[1] for r in seq]
        for i in range(nn):
            tr=seq[i]
            if tr[3]<=0: continue
            if not filt(m,i,tr): continue
            n+=1; cl.add(m)
            if i+1<nn: gaps.append(seq[i+1][0]-tr[0])
            else: nonext+=1
            j=i; cl_=[]
            for L in LS:
                lim=tr[0]+L
                while j+1<nn and seq[j+1][0]<lim: j+=1
                c=seq[j][2]/tr[2]-1.0
                cs[L].append(c); cl_.append(c)
            k=bisect.bisect_right(times,tr[1],i+1)
            d=1 if (k>=nn or times[k]>tr[1]+60) else 0
            dead60+=d
            ev.append((m,i,tr[1],tr[2],cl_[1],d))
    print('\n=== %s'%label,flush=True)
    print('n_events=%d  clusters(mints)=%d'%(n,len(cl)),flush=True)
    if n==0: return ev
    sg=sorted(gaps)
    print('(a) slot gap to NEXT trade in mint: mean %.1f median %.0f p10 %.0f p25 %.0f p75 %.0f p90 %.0f'%(
      mean(gaps),q(sg,.5),q(sg,.10),q(sg,.25),q(sg,.75),q(sg,.90)),flush=True)
    for th in (0,1,2,4):
        print('    frac next-trade gap <= %d slots: %.4f'%(th,bisect.bisect_right(sg,th)/len(sg)),flush=True)
    print('    events with no next trade anywhere in tape: %d (%.4f)'%(nonext,nonext/n),flush=True)
    print('(b/c) NO trade within 60s after event: %d (%.4f)'%(dead60,dead60/n),flush=True)
    for L in LS:
        v=cs[L]; sv=sorted(v)
        print('  L=%2d (%.2fs): c mean %+.4f%% median %+.4f%% p25 %+.4f%% p75 %+.4f%% p90 %+.4f%% p99 %+.4f%% | frac c>1.14%%=%.4f frac c>0=%.4f frac c<0=%.4f'%(
          L,L*0.4223,100*mean(v),100*q(sv,.5),100*q(sv,.25),100*q(sv,.75),100*q(sv,.90),100*q(sv,.99),
          1-bisect.bisect_right(sv,0.0114)/len(sv),1-bisect.bisect_right(sv,0.0)/len(sv),bisect.bisect_left(sv,0.0)/len(sv)),flush=True)
    if dump: pickle.dump(ev,open(SP+dump,'wb'),protocol=4)
    return ev

measure(lambda m,i,tr:True,'ALL BUYS (full tape) -- base microstructure measurement','h33_all.pkl')

rnd=random.Random(20260903)
sh=mints[:]; rnd.shuffle(sh)
A=set(sh[:len(sh)//2]); B=set(sh[len(sh)//2:])
pairs=collections.defaultdict(list)
for m in A:
    for r in by[m]: pairs[(r[4],m)].append(r)
rt=collections.defaultdict(list)
for (u,m),seq in pairs.items():
    inv=[]
    for r in seq:
        if r[3]>0: inv.append(r[2])
        elif r[3]<0 and inv:
            e=inv.pop(0); rt[u].append(r[2]/e-1.0)
sc={u:mean(v) for u,v in rt.items() if len(v)>=3}
print('\nwallets ranked on mint-half A: %d (>=3 round trips)'%len(sc),flush=True)
rk=sorted(sc.items(),key=lambda kv:-kv[1]); k=max(1,len(rk)//10)
TOP=set(u for u,_ in rk[:k])
print('top decile n=%d cutoff mean round-trip simple return=%+.4f'%(len(TOP),rk[k-1][1]),flush=True)
measure(lambda m,i,tr: m in B and tr[4] in TOP,'TOP-DECILE WALLET BUYS on held-out mint-half B','h33_top.pkl')
measure(lambda m,i,tr: m in B,'ALL BUYS on held-out mint-half B (benchmark population)','h33_allB.pkl')
pickle.dump({'A':sorted(A),'B':sorted(B),'TOP':sorted(TOP)},open(SP+'h33_split.pkl','wb'),protocol=4)
print('\nTEND',TEND,flush=True)
