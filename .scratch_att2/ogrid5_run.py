import sqlite3, json, hashlib, collections, statistics as st, math, random, sys, time
OUT=open('/home/anont/meme/.scratch_att2/ogrid5_out.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def hh(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

T0=time.time()
# ---------- load bars (h12 only) ----------
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
M={}
for mint,bj,nb in c.execute('select mint,bars_json,n_bars from ohlcv where n_bars>0'):
    if hh(mint) not in (1,2): continue          # NEVER touch h==0
    b=json.loads(bj)
    b.sort(key=lambda x:x[0])                    # ASCENDING
    if len(b)<3: continue
    M[mint]=b
P('h12 mints loaded',len(M),'bars',sum(len(v) for v in M.values()))

# ---------- deployer metadata (ex-ante) ----------
w=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
wl=[r for r in w.execute('select mint,creator,create_slot,block_time,complete,virtual_token_reserves,real_token_reserves from window_label')]
by_creator=collections.defaultdict(list)
info={}
for mint,cr,cs,bt,comp,vt,rt in wl:
    by_creator[cr].append((cs,comp))
    info[mint]=(cr,cs,bt,comp,vt,rt)
for k in by_creator: by_creator[k].sort()
META={}
for mint in M:
    if mint not in info: META[mint]=None; continue
    cr,cs,bt,comp,vt,rt = info[mint]
    prior=[x for x in by_creator[cr] if x[0]<cs]
    META[mint]=dict(creator=cr,create_slot=cs,block_time=bt,
                    prior_n=len(prior), prior_grad=sum(1 for x in prior if x[1]==1),
                    vt=vt, rt=rt)
P('mints with metadata',sum(1 for v in META.values() if v))

# ---------- per-bar features ----------
HG=[1,2,3,5,15,30,60,120,240,360,720]
MAXH=720
UPS=[0.05,0.10,0.25,0.50,1.00,3.00,10.00]
DNS=[0.15,0.25,0.50,0.80]
TRS=[0.25,0.50]

FEAT={}; TRIG={}
for mint,b in M.items():
    n=len(b)
    ts=[x[0] for x in b]; op=[x[1] for x in b]; hi=[x[2] for x in b]; lo=[x[3] for x in b]; cl=[x[4] for x in b]; vo=[x[5] for x in b]
    md=META[mint]
    bt=md['block_time'] if md else None
    runmax=[0.0]*n; runmin=[0.0]*n
    rm=cl[0]; rn=cl[0]
    for i in range(n):
        rm=max(rm,cl[i]); rn=min(rn,cl[i]); runmax[i]=rm; runmin[i]=rn
    f=[None]*n
    for i in range(n):
        def R(k):
            j=i-k
            return (cl[i]/cl[j]-1.0) if j>=0 and cl[j]>0 else None
        v10=vo[max(0,i-10):i]
        mv=(sum(v10)/len(v10)) if v10 else 0.0
        gap=(ts[i]-ts[i-1])/60.0 if i>0 else None
        span=(ts[i]-ts[max(0,i-10)])/60.0
        gaps10 = span-(i-max(0,i-10)) if i>0 else 0
        f[i]=dict(r1=R(1),r5=R(5),r15=R(15),r30=R(30),
                  volz=(vo[i]/mv if mv>0 else None), vabs=vo[i],
                  rng=((hi[i]-lo[i])/cl[i]) if cl[i]>0 else None,
                  dd=(cl[i]/runmax[i]-1.0) if runmax[i]>0 else None,
                  ru=(cl[i]/runmin[i]-1.0) if runmin[i]>0 else None,
                  gap=gap, gaps10=gaps10, nb=i+1,
                  age=((ts[i]-bt)/60.0 if bt else None))
    FEAT[mint]=f
    # ---- trigger precompute per entry bar j (entry price = open[j]) ----
    tg=[None]*n
    for j in range(n):
        e=op[j]
        if e<=0: continue
        marks={}; fu={}; fd={}; ftr={}; fgap=None
        rmx=e
        k=j
        lim=ts[j]+MAXH*60
        lastin={H:None for H in HG}
        while k<n and ts[k]<=lim:
            if k>j:
                px=cl[k]
                if px>rmx: rmx=px
                for x in UPS:
                    if x not in fu and px>=e*(1+x): fu[x]=k
                for y in DNS:
                    if y not in fd and px<=e*(1-y): fd[y]=k
                for z in TRS:
                    if z not in ftr and rmx>e and px<=rmx*(1-z): ftr[z]=k
                if fgap is None and ts[k]-ts[k-1]>=5*60: fgap=k
            dtm=(ts[k]-ts[j])/60.0
            for H in HG:
                if dtm<=H: lastin[H]=k
            k+=1
        endts=ts[-1]
        for H in HG:
            marks[H]= lastin[H] if (endts>=ts[j]+H*60) else None
        tg[j]=(e,marks,fu,fd,ftr,fgap)
    TRIG[mint]=tg
P('features+triggers built  t=%.0fs'%(time.time()-T0))
json.dump({'n_mints':len(M)},open('/home/anont/meme/.scratch_att2/ogrid_meta.json','w'))

# ---------- conditions ----------
def mk(name,fn): return (name,fn)
def g(f,k):
    v=f.get(k); return v
CONDS=[]
def add(n,fn): CONDS.append((n,fn))
add('all', lambda f,m: True)
add('r5<=-50', lambda f,m: f['r5'] is not None and f['r5']<=-0.50)
add('r5<=-30', lambda f,m: f['r5'] is not None and f['r5']<=-0.30)
add('r5>=+50', lambda f,m: f['r5'] is not None and f['r5']>=0.50)
add('r5>=+100',lambda f,m: f['r5'] is not None and f['r5']>=1.00)
add('r15<=-60',lambda f,m: f['r15'] is not None and f['r15']<=-0.60)
add('r15>=+100',lambda f,m: f['r15'] is not None and f['r15']>=1.00)
add('r1<=-20', lambda f,m: f['r1'] is not None and f['r1']<=-0.20)
add('r1>=+20', lambda f,m: f['r1'] is not None and f['r1']>=0.20)
add('r1>=+40', lambda f,m: f['r1'] is not None and f['r1']>=0.40)
add('r30<=-70',lambda f,m: f['r30'] is not None and f['r30']<=-0.70)
add('r30>=+150',lambda f,m: f['r30'] is not None and f['r30']>=1.50)
add('volz>=5', lambda f,m: f['volz'] is not None and f['volz']>=5)
add('volz>=10',lambda f,m: f['volz'] is not None and f['volz']>=10)
add('volz<=0.2',lambda f,m: f['volz'] is not None and f['volz']<=0.2)
add('vabs>=5k',lambda f,m: f['vabs']>=5000)
add('vabs<=100',lambda f,m: f['vabs']<=100)
add('rng>=30', lambda f,m: f['rng'] is not None and f['rng']>=0.30)
add('rng<=2',  lambda f,m: f['rng'] is not None and f['rng']<=0.02)
add('dd<=-80', lambda f,m: f['dd'] is not None and f['dd']<=-0.80)
add('dd<=-50', lambda f,m: f['dd'] is not None and f['dd']<=-0.50)
add('dd>=-5',  lambda f,m: f['dd'] is not None and f['dd']>=-0.05)
add('ru>=200', lambda f,m: f['ru'] is not None and f['ru']>=2.0)
add('ru<=5',   lambda f,m: f['ru'] is not None and f['ru']<=0.05)
add('gap>=5m', lambda f,m: f['gap'] is not None and f['gap']>=5)
add('gap>=15m',lambda f,m: f['gap'] is not None and f['gap']>=15)
add('gap==1m', lambda f,m: f['gap'] is not None and f['gap']<=1.01)
add('gaps10>=5',lambda f,m: f['gaps10']>=5)
add('gaps10==0',lambda f,m: f['gaps10']<=0.01)
add('age<=30m',lambda f,m: f['age'] is not None and f['age']<=30)
add('age>=24h',lambda f,m: f['age'] is not None and f['age']>=1440)
add('cprior==0',lambda f,m: m and m['prior_n']==0)
add('cprior>=5',lambda f,m: m and m['prior_n']>=5)
add('cgrad>=1', lambda f,m: m and m['prior_grad']>=1)
add('cgrad==0', lambda f,m: m and m['prior_grad']==0)
add('nb<=5',   lambda f,m: f['nb']<=5)
add('nb>=200', lambda f,m: f['nb']>=200)
add('flush',   lambda f,m: f['r5'] is not None and f['r5']<=-0.30 and f['volz'] is not None and f['volz']>=5)
add('burst',   lambda f,m: f['r5'] is not None and f['r5']>=0.50 and f['volz'] is not None and f['volz']>=5)
add('deepflush',lambda f,m: f['dd'] is not None and f['dd']<=-0.80 and f['volz'] is not None and f['volz']>=5)
add('pullback',lambda f,m: f['r15'] is not None and f['r15']>=1.00 and f['r1'] is not None and f['r1']<=0)
add('bounce',  lambda f,m: f['r15'] is not None and f['r15']<=-0.60 and f['r1'] is not None and f['r1']>=0.10)
add('reawake', lambda f,m: f['gap'] is not None and f['gap']>=5 and f['volz'] is not None and f['volz']>=5)
add('gapup',   lambda f,m: f['gap'] is not None and f['gap']>=5 and f['r1'] is not None and f['r1']>=0.20)
add('widedown',lambda f,m: f['rng'] is not None and f['rng']>=0.30 and f['r1'] is not None and f['r1']<=-0.20)
add('volz10_cg',lambda f,m: f['volz'] is not None and f['volz']>=10 and m and m['prior_grad']>=1)
add('young_burst',lambda f,m: f['age'] is not None and f['age']<=30 and f['volz'] is not None and f['volz']>=5)
add('old_burst',lambda f,m: f['age'] is not None and f['age']>=1440 and f['volz'] is not None and f['volz']>=10)
add('ddbounce',lambda f,m: f['dd'] is not None and f['dd']<=-0.50 and f['ru'] is not None and f['ru']>=0.20)
add('liqflush',lambda f,m: f['r5'] is not None and f['r5']<=-0.50 and f['gaps10']<=0.01)
add('liqburst',lambda f,m: f['r5'] is not None and f['r5']>=1.00 and f['gaps10']<=0.01)
add('serial_burst',lambda f,m: m and m['prior_n']>=5 and f['r5'] is not None and f['r5']>=0.50)
P('n conditions',len(CONDS))

EXITS=[('hold',None,None,None,False),
       ('tp10',0.10,None,None,False),('tp25',0.25,None,None,False),('tp50',0.50,None,None,False),('tp100',1.00,None,None,False),
       ('sl25',None,0.25,None,False),('sl50',None,0.50,None,False),
       ('tp25_sl25',0.25,0.25,None,False),('tp50_sl25',0.50,0.25,None,False),('tp100_sl50',1.00,0.50,None,False),
       ('trail25',None,None,0.25,False),('trail50',None,None,0.50,False),
       ('gapexit',None,None,None,True),('tp50_gap',0.50,None,None,True)]
POS=['flat','dip_add','brk_add','half_out']
TOLL=0.0114

def outcome(tg,H,tp,sl,tr,gx,pos,dc):
    e,marks,fu,fd,ftr,fgap = tg
    mk_=marks.get(H)
    if mk_ is None: return (dc,True)          # dropout charged
    cands=[]
    if tp is not None and tp in fu and fu[tp]<=mk_: cands.append((fu[tp],'tp'))
    if sl is not None and sl in fd and fd[sl]<=mk_: cands.append((fd[sl],'sl'))
    if tr is not None and tr in ftr and ftr[tr]<=mk_: cands.append((ftr[tr],'tr'))
    if gx and fgap is not None and fgap<=mk_: cands.append((fgap,'gap'))
    xi = min(cands)[0] if cands else mk_
    return (xi,False)

def px_at(mint,i): return CL[mint][i]
CL={m:[x[4] for x in b] for m,b in M.items()}
OPEN={m:[x[1] for x in b] for m,b in M.items()}

def trade_ret(mint,j,H,tp,sl,tr,gx,pos,dc):
    tg=TRIG[mint][j]
    if tg is None: return None
    e,marks,fu,fd,ftr,fgap = tg
    r=outcome(tg,H,tp,sl,tr,gx,pos,dc)
    if r[1]: return (dc,None)                 # dropout: charged, blocks nothing further
    xi=r[0]; xpx=CL[mint][xi]
    w=0.5 if pos in ('dip_add','brk_add') else 1.0
    base=(xpx/e-1.0)
    if pos=='half_out':
        hi_=fu.get(0.50)
        if hi_ is not None and hi_<=xi:
            base=0.5*(CL[mint][hi_]/e-1.0)+0.5*(xpx/e-1.0)
    legs=w; ret=w*base
    if pos=='dip_add':
        ai=fd.get(0.25)
        if ai is not None and ai<xi:
            ret+=0.5*(xpx/CL[mint][ai]-1.0); legs+=0.5
    if pos=='brk_add':
        ai=fu.get(0.25)
        if ai is not None and ai<xi:
            ret+=0.5*(xpx/CL[mint][ai]-1.0); legs+=0.5
    return (ret-legs*TOLL, xi)

# precompute signal index lists per condition
SIG={}
for cname,fn in CONDS:
    d={}
    for mint,f in FEAT.items():
        md=META[mint]
        idx=[i for i in range(len(f)-1) if fn(f[i],md)]   # need bar i+1 to exist for entry
        if idx: d[mint]=idx
    SIG[cname]=d
P('signals precomputed t=%.0fs'%(time.time()-T0))
P('signal counts:', {c:sum(len(v) for v in SIG[c].values()) for c,_ in CONDS[:6]})

def evaluate(cname,H,ex,pos,dc,halves):
    tp,sl,tr,gx = ex[1],ex[2],ex[3],ex[4]
    per_mint={}
    for mint,idx in SIG[cname].items():
        if hh(mint) not in halves: continue
        rs=[]; blocked=-1
        for i in idx:
            j=i+1
            if j<=blocked: continue
            o=trade_ret(mint,j,H,tp,sl,tr,gx,pos,dc)
            if o is None: continue
            rs.append(o[0])
            blocked = o[1] if o[1] is not None else j   # no-overlap
        if rs: per_mint[mint]=sum(rs)/len(rs)
    if not per_mint: return None
    vals=list(per_mint.values())
    return (st.mean(vals), st.median(vals), len(vals), sum(len(SIG[cname][m]) for m in per_mint))

EXITS=[('hold',None,None,None,False),('tp5',0.05,None,None,False),('tp10',0.10,None,None,False),
 ('tp25',0.25,None,None,False),('tp50',0.50,None,None,False),('tp100',1.00,None,None,False),
 ('tp300',3.00,None,None,False),('tp1000',10.00,None,None,False),
 ('sl15',None,0.15,None,False),('sl25',None,0.25,None,False),('sl50',None,0.50,None,False),('sl80',None,0.80,None,False),
 ('tp5_sl15',0.05,0.15,None,False),('tp25_sl25',0.25,0.25,None,False),('tp50_sl25',0.50,0.25,None,False),
 ('tp100_sl50',1.00,0.50,None,False),('tp1000_sl80',10.00,0.80,None,False),('tp300_sl50',3.00,0.50,None,False),
 ('trail25',None,None,0.25,False),('trail50',None,None,0.50,False),
 ('gapexit',None,None,None,True),('tp300_gap',3.00,None,None,True),('tp50_gap',0.50,None,None,True)]

def evaluate3(cname,H,ex,pos,dc,halves,toll=None):
    global TOLL
    old=TOLL
    if toll is not None: TOLL=toll
    tp,sl,tr,gx = ex[1],ex[2],ex[3],ex[4]
    per_mint={}; ndrop=0; ntr=0
    for mint,idx in SIG[cname].items():
        if hh(mint) not in halves: continue
        rs=[]; blocked=-1
        for i in idx:
            j=i+1
            if j<=blocked: continue
            o=trade_ret(mint,j,H,tp,sl,tr,gx,pos,dc)
            if o is None: continue
            rs.append(o[0]); ntr+=1
            if o[1] is None:
                ndrop+=1; blocked=j
            else:
                blocked=o[1]
        if rs: per_mint[mint]=sum(rs)/len(rs)
    TOLL=old
    if not per_mint: return None
    return (per_mint, ntr, ndrop)

def trim_mean(v,f=0.10):
    s=sorted(v); n=len(s); k=int(n*f)
    s2=s[k:n-k] if n-2*k>=3 else s
    return sum(s2)/len(s2)
def boot(v,stat,B=1500,seed=17):
    if len(v)<5: return None
    rnd=random.Random(seed); n=len(v); ms=[]
    for _ in range(B): ms.append(stat([v[rnd.randrange(n)] for _ in range(n)]))
    ms.sort(); return ms[int(0.05*B)]
def stats(t):
    pm,ntr,nd=t; v=list(pm.values())
    return dict(mean=st.mean(v),med=st.median(v),trim=trim_mean(v),k=len(v),n=ntr,
                res=((ntr-nd)/ntr if ntr else 0),vals=v)

P('=== COMBINED FULL-RANGE PASS ===')
P('%5s %10s %10s %10s %6s %8s %7s'%('H','ctrl_mean','ctrl_med','ctrl_trim','k','trades','res%'))
CTRL={}
for H in HG:
    for ex in EXITS:
        for pos in POS:
            a=evaluate3('all',H,ex,pos,-0.30,{1}); b=evaluate3('all',H,ex,pos,-0.30,{2})
            CTRL[(H,ex[0],pos)]=(stats(a) if a else None, stats(b) if b else None)
for H in HG:
    c=CTRL[(H,'hold','flat')][1]
    P('%5d %+9.2f%% %+9.2f%% %+9.2f%% %6d %8d %6.1f'%(H,c['mean']*100,c['med']*100,c['trim']*100,c['k'],c['n'],c['res']*100))
P('controls built t=%.0fs'%(time.time()-T0))

near=[]; rows=[]; combos=0; g1=g2=g3=g4=g5=0
for cname,_ in CONDS:
    if cname=='all': continue
    for H in HG:
        for ex in EXITS:
            for pos in POS:
                combos+=1
                A=evaluate3(cname,H,ex,pos,-0.30,{1})
                if A is None or len(A[0])<10: continue
                a=stats(A); ct,cv=CTRL[(H,ex[0],pos)]
                if ct is None or cv is None: continue
                if a['trim']<=ct['trim']: continue
                g1+=1
                B=evaluate3(cname,H,ex,pos,-0.30,{2})
                if B is None or len(B[0])<10: continue
                b=stats(B)
                if b['trim']<=cv['trim']: continue
                g2+=1
                if b['trim']<=0: continue
                g3+=1
                if a['trim']<=0: continue
                g4+=1
                lo=boot(b['vals'],trim_mean)
                rec=dict(cond=cname,H=H,exit=ex[0],pos=pos,ttrim=a['trim'],tmed=a['med'],tk=a['k'],tn=a['n'],
                         vtrim=b['trim'],vmed=b['med'],vmean=b['mean'],vk=b['k'],vn=b['n'],vres=b['res'],
                         vlo=(lo if lo is not None else -9),cv=cv['trim'],edge=b['trim']-cv['trim'])
                near.append(rec)
                if lo is not None and lo>0: g5+=1; rows.append(rec)
P('combos (excl all): %d'%combos)
P('R1 train trimmed > control trimmed      : %d'%g1)
P('R2 + validate trimmed > control trimmed : %d'%g2)
P('R3 + validate trimmed > 0               : %d'%g3)
P('R4 + train trimmed > 0 (BOTH halves +)  : %d'%g4)
P('R5 + validate bootstrap lo(trim) > 0    : %d'%g5)
near.sort(key=lambda r:-r['vlo'])
P('--- the %d cells positive on BOTH halves, ranked by validate bootstrap lower bound ---'%len(near))
for r in near[:45]:
    P('  %-14s H=%4d %-12s %-9s tr=%+7.2f%%(med%+7.2f%%,k%d,n%d) va=%+7.2f%%(med%+7.2f%%,mean%+9.2f%%,k%d,n%d) lo=%+7.2f%% ctrl=%+7.2f%% res=%.0f%%'%(
      r['cond'],r['H'],r['exit'],r['pos'],r['ttrim']*100,r['tmed']*100,r['tk'],r['tn'],
      r['vtrim']*100,r['vmed']*100,r['vmean']*100,r['vk'],r['vn'],r['vlo']*100,r['cv']*100,r['vres']*100))
json.dump(near,open('/home/anont/meme/.scratch_att2/ogrid5_near.json','w'))
P('FINAL survivors: %d'%len(rows))
P('done t=%.0fs'%(time.time()-T0))
OUT.close()
