"""Grid sweep: mint-level (deployer) filters x bar filters x exit/position structures.
TRAIN = h==1 mints, VALIDATE = h==2 mints. h==0 never touched."""
import pickle, statistics as st, time, os
TAG=os.environ.get('TAG','')
S='/home/anont/meme/.scratch_fc/'
R=pickle.load(open(S+'res%s.pkl'%TAG,'rb'))
FEAT=pickle.load(open(S+'feat.pkl','rb'))
RES=R['RES']; STRUCTS=R['STRUCTS']; BFS=R['BFS']; MINTS=R['MINTS']
HORIZ=R['HORIZ']; TPS=R['TPS']; SLS=R['SLS']; TRS=R['TRS']
OUT=open(S+'sweep%s.txt'%TAG,'w')
def P(*a): print(*a,file=OUT); OUT.flush()
NM=len(MINTS)
TRAIN=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==1]
VALID=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==2]
P('train mints',len(TRAIN),'validate mints',len(VALID))
F=[FEAT[m] for m in MINTS]
MF=[]
def mk(name,fn): MF.append((name,[bool(fn(f)) for f in F]))
mk('ALL',lambda f:True)
mk('np==0',lambda f:f['n_prior']==0)
for k in [1,2,3,4,5,6,7,8,10,12,15,20,30,50]: mk('np>=%d'%k,(lambda k:(lambda f:f['n_prior']>=k))(k))
for a,b in [(1,3),(2,5),(3,7),(4,9),(5,11),(6,13),(8,17),(10,21),(12,26),(16,41)]:
    mk('np%d_%d'%(a,b-1),(lambda a,b:(lambda f:a<=f['n_prior']<b))(a,b))
mk('np>=41',lambda f:f['n_prior']>=41)
for k in [1,2,3,5]: mk('gradn>=%d'%k,(lambda k:(lambda f:f['grad_n']>=k))(k))
mk('gradn==0&np>=1',lambda f:f['n_prior']>=1 and f['grad_n']==0)
mk('gradn==0&np>=3',lambda f:f['n_prior']>=3 and f['grad_n']==0)
mk('gf==0&np>=1',lambda f:f['n_prior']>=1 and f['grad_frac']==0)
mk('gf>0',lambda f:f['n_prior']>=1 and f['grad_frac']>0)
for q in [0.10,0.15,0.20,0.25,0.30,0.35,0.40,0.50,0.67]:
    mk('gf>=%.2f'%q,(lambda q:(lambda f:f['n_prior']>=1 and f['grad_frac']>=q))(q))
for a,b in [(0.001,0.25),(0.10,0.40),(0.20,0.60),(0.05,0.35)]:
    mk('gf%.2f_%.2f'%(a,b),(lambda a,b:(lambda f:f['n_prior']>=1 and a<=f['grad_frac']<b))(a,b))
for lab,fn in [('gap<5',lambda f:0<=f['gap_prev']<5),('gap<10',lambda f:0<=f['gap_prev']<10),
               ('gap5_20',lambda f:5<=f['gap_prev']<20),('gap10_40',lambda f:10<=f['gap_prev']<40),
               ('gap20_60',lambda f:20<=f['gap_prev']<60),('gap30_120',lambda f:30<=f['gap_prev']<120),
               ('gap>=60',lambda f:f['gap_prev']>=60),('gap>=120',lambda f:f['gap_prev']>=120)]: mk(lab,fn)
for lab,fn in [('p1h==0&np>=1',lambda f:f['n_prior']>=1 and f['n_prior_1h']==0),
               ('p1h>=1',lambda f:f['n_prior_1h']>=1),('p1h>=2',lambda f:f['n_prior_1h']>=2),
               ('p1h>=3',lambda f:f['n_prior_1h']>=3),('p1h>=5',lambda f:f['n_prior_1h']>=5),
               ('p1h>=8',lambda f:f['n_prior_1h']>=8),('p1h1_3',lambda f:1<=f['n_prior_1h']<=3),
               ('p1h2_6',lambda f:2<=f['n_prior_1h']<=6)]: mk(lab,fn)
for lab,fn in [('cov',lambda f:f['covered']==1),('devbuy>=1',lambda f:f['dev_buy_sol']>=1),
               ('devbuy>=2',lambda f:f['dev_buy_sol']>=2),('devbuy>=3',lambda f:f['dev_buy_sol']>=3),
               ('devbuy>=5',lambda f:f['dev_buy_sol']>=5),
               ('devbuy0_1',lambda f:0<=f['dev_buy_sol']<1),('devbuy1_3',lambda f:1<=f['dev_buy_sol']<3),
               ('pdevbuy>=2',lambda f:f['prior_devbuy_med']>=2),('pdevbuy0_2',lambda f:0<=f['prior_devbuy_med']<2)]: mk(lab,fn)
for lab,fn in [('np>=3&gf>=0.25',lambda f:f['n_prior']>=3 and f['grad_frac']>=0.25),
               ('np>=3&gf==0',lambda f:f['n_prior']>=3 and f['grad_frac']==0),
               ('np>=5&gradn>=2',lambda f:f['n_prior']>=5 and f['grad_n']>=2),
               ('np>=2&gap<20',lambda f:f['n_prior']>=2 and 0<=f['gap_prev']<20),
               ('np>=8&gf>=0.20',lambda f:f['n_prior']>=8 and f['grad_frac']>=0.20),
               ('np>=2&gf>=0.34',lambda f:f['n_prior']>=2 and f['grad_frac']>=0.34),
               ('np2_8&gf>0',lambda f:2<=f['n_prior']<9 and f['grad_frac']>0),
               ('np>=4&p1h>=2',lambda f:f['n_prior']>=4 and f['n_prior_1h']>=2),
               ('np>=4&p1h==0',lambda f:f['n_prior']>=4 and f['n_prior_1h']==0),
               ('np>=6&gap>=60',lambda f:f['n_prior']>=6 and f['gap_prev']>=60)]: mk(lab,fn)
P('mint filters',len(MF))
IDT=[[i for i in TRAIN if v[i]] for _,v in MF]
IDV=[[i for i in VALID if v[i]] for _,v in MF]
P('sizes(train,val):')
for j,(n,_) in enumerate(MF): P('   %-18s %3d %3d'%(n,len(IDT[j]),len(IDV[j])))

def sname(s):
    hh,tpi,sli,tri,pos=s
    return 'H%d|TP%s|SL%s|TR%s|P%s'%(HORIZ[hh],('%.2f'%TPS[tpi]) if tpi is not None else '-',
        ('%.2f'%SLS[sli]) if sli is not None else '-',('%.2f'%TRS[tri]) if tri is not None else '-',pos)
TOLL1=0.0114
def stats(key,idxs,toll=TOLL1,charge=-0.30):
    n_res,s_g,n_do=RES[key]
    means=[]; tot=0; res=0
    for i in idxs:
        nr=n_res[i]; nd=n_do[i]
        if nr+nd==0: continue
        tn=(1-toll)*(nr+s_g[i])-nr+nd*((1+charge)*(1-toll)-1)
        means.append(tn/(nr+nd)); tot+=nr+nd; res+=nr
    if not means: return None
    return (sum(means)/len(means), st.median(means), len(means), tot, res/tot if tot else 0.0, means)

t0=time.time(); rows=[]; combos=0
region={}   # (dim-> mean of train means) surface diagnostics
allmeans=[]
for si in range(len(STRUCTS)):
    for bi in range(len(BFS)):
        key=(si,bi)
        b=stats(key,TRAIN)
        ctrl=b[0] if b else float('nan')
        for mi in range(len(MF)):
            combos+=1
            idT=IDT[mi]
            if len(idT)<15: continue
            a=stats(key,idT)
            if a is None: continue
            allmeans.append((si,bi,mi,a[0]))
            if a[2]<15 or a[3]<40: continue
            if a[0]<=0: continue
            rows.append((si,bi,mi,a[0],a[1],a[2],a[3],a[4],ctrl))
P('combos swept',combos,'evaluated',len(allmeans),'train-positive(with n gates)',len(rows),'elapsed',round(time.time()-t0,1))
rows.sort(key=lambda r:-r[3])
P('TOP 60 TRAIN:')
for r in rows[:60]:
    P('  %-20s %-12s %-26s trmean=%+.4f trmed=%+.4f k=%d n=%d res=%.3f ctrlALL=%+.4f edge=%+.4f'%(
        MF[r[2]][0],BFS[r[1]],sname(STRUCTS[r[0]]),r[3],r[4],r[5],r[6],r[7],r[8],r[3]-r[8]))
pickle.dump(dict(rows=rows,MFN=[m[0] for m in MF],IDT=IDT,IDV=IDV,combos=combos,allmeans=allmeans),
            open(S+'train_rows%s.pkl'%TAG,'wb'),protocol=4)
# ---- surface diagnostics on TRAIN ----
import collections
def agg(getter,label):
    d=collections.defaultdict(list)
    for si,bi,mi,mu in allmeans: d[getter(si,bi,mi)].append(mu)
    P('SURFACE by',label)
    for k in sorted(d, key=lambda k:-sum(d[k])/len(d[k])):
        v=d[k]; P('   %-22s n=%6d meanTrainMean=%+.4f fracPos=%.3f best=%+.4f'%(
            str(k),len(v),sum(v)/len(v),sum(1 for x in v if x>0)/len(v),max(v)))
agg(lambda si,bi,mi:HORIZ[STRUCTS[si][0]],'HOLD')
agg(lambda si,bi,mi:('TP%.2f'%TPS[STRUCTS[si][1]]) if STRUCTS[si][1] is not None else 'TPnone','TP')
agg(lambda si,bi,mi:('SL%.2f'%SLS[STRUCTS[si][2]]) if STRUCTS[si][2] is not None else 'SLnone','SL')
agg(lambda si,bi,mi:('TR%.2f'%TRS[STRUCTS[si][3]]) if STRUCTS[si][3] is not None else 'TRnone','TRAIL')
agg(lambda si,bi,mi:'POS'+STRUCTS[si][4],'POSITION')
agg(lambda si,bi,mi:BFS[bi],'BARFILTER')
agg(lambda si,bi,mi:MF[mi][0],'MINTFILTER')
OUT.close()
