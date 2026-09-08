"""Full deployer-identity grid on the SURVIVORSHIP-FREE on-chain universe
(2,187 h12 launches from b11a_bodies; 2.74% graduation rate vs 3.16% base rate).
TRAIN = h==1, VALIDATE = h==2. Harness A-G. Mint-equal. Cap +300%."""
import sqlite3, pickle, hashlib, bisect, statistics as st, random, time
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb'))
OUT=open(S+'survgrid.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
curve2mint=D['curve2mint']; mint2cre=D['mint2cre']; mint2bt=D['mint2bt']
mint2comp=D['mint2comp']; WL=D['WL']; launch=D['launch']
slope=D['slope']; inter=D['inter']
def slot2t(s): return inter+slope*s
curves=set(curve2mint)
cb=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
tmp=defaultdict(list)
for bc,slot,txi,oi,ii,vqa,vta in cb.execute(
    "select bonding_curve,slot,transaction_index,outer_index,inner_index,virtual_quote_after,virtual_token_after from reserve_observation"):
    if bc in curves and vqa and vta: tmp[bc].append((slot,txi,oi,ii,vqa/vta))
cb.close()
bycre=defaultdict(list)
for bc,m,cr,slot,bt,comp in WL: bycre[cr].append(bt)
for v in bycre.values(): v.sort()
prior_grad=defaultdict(list)
for bc,m,cr,slot,bt,comp in WL: prior_grad[cr].append((bt,comp))
for v in prior_grad.values(): v.sort()

PX={}; TS={}; FT={}
for bc,pth in tmp.items():
    pth.sort()
    m=curve2mint[bc]; cr=mint2cre[m]; bt=mint2bt[m]
    cl=bycre[cr]; npri=bisect.bisect_left(cl,bt)
    pg=[c for (b,c) in prior_grad[cr] if b<bt]
    L=launch.get(m,{})
    TS[m]=[slot2t(p[0]) for p in pth]; PX[m]=[p[4] for p in pth]
    FT[m]=dict(cre=cr,bt=bt,h=h3(m),comp=mint2comp[m],n_prior=npri,
               grad_n=sum(pg), grad_frac=(sum(pg)/len(pg)) if pg else -1.0,
               gap_prev=((bt-cl[npri-1])/60.0) if npri>0 else -1.0,
               n_prior_1h=sum(1 for b in cl[:npri] if b>=bt-3600),
               dev_buy_sol=L.get('dev_buy_sol',-1.0), dev_first=L.get('dev_first',-1),
               n_traders=L.get('traders',-1))
del tmp
MS=list(FT)
P('launches',len(MS),'trades',sum(len(v) for v in PX.values()))
P('h1',sum(1 for m in MS if FT[m]['h']==1),'h2',sum(1 for m in MS if FT[m]['h']==2))

CAP=3.0
def backtest(ms, agelo, agehi, H, trail, tp, sl):
    out={}
    for m in ms:
        ts=TS[m]; px=PX[m]; n=len(ts); bt=FT[m]['bt']
        nr=0; sg=0.0; nd=0; free=-1.0
        for j in range(0,n-1):
            a=(ts[j]-bt)/60.0
            if a>=agehi: break
            if a<agelo: continue
            if ts[j]<free: continue
            e=px[j+1]
            if e<=0: continue
            et=ts[j+1]; cut=et+H*60
            runmax=e; ex=None; ext=None; k=j+1
            tpv=e*(1+tp) if tp else None; slv=e*(1-sl) if sl else None
            while k<n and ts[k]<=cut:
                p=px[k]
                if p>runmax: runmax=p
                if slv is not None and p<=slv: ex=p; ext=ts[k]; break
                if trail is not None and p<=runmax*(1-trail): ex=p; ext=ts[k]; break
                if tpv is not None and p>=tpv: ex=p; ext=ts[k]; break
                k+=1
            if ex is None:
                while k<n and ts[k]<cut: k+=1
                if k<n: ex=px[k]; ext=ts[k]
            if ex is None: nd+=1; free=cut
            else:
                nr+=1; sg+=min(ex/e-1.0,CAP); free=ext
        if nr+nd: out[m]=(nr,sg,nd)
    return out
def agg(out,toll=0.0114,charge=-0.30):
    per={}; tot=0; r=0
    for m,(nr,sg,nd) in out.items():
        per[m]=((1-toll)*(nr+sg)-nr+nd*((1+charge)*(1-toll)-1))/(nr+nd); tot+=nr+nd; r+=nr
    if not per: return None
    v=list(per.values())
    return dict(mean=sum(v)/len(v),median=st.median(v),k=len(v),n=tot,res=r/tot,per=per)
random.seed(5)
def blo(per,reps=600):
    byc=defaultdict(list)
    for m,v in per.items(): byc[FT[m]['cre']].append(v)
    cs=list(byc); nc=len(cs)
    if nc<8: return None,nc
    o=[]
    for _ in range(reps):
        a=[]
        for _ in range(nc): a.extend(byc[cs[random.randrange(nc)]])
        o.append(sum(a)/len(a))
    o.sort(); return o[int(0.05*reps)],nc

MF=[]
def mk(n,f): MF.append((n,[m for m in MS if f(FT[m])]))
mk('ALL',lambda f:True)
mk('np==0',lambda f:f['n_prior']==0)
for k in [1,2,3,4,5,6,8,10,15,20,30]: mk('np>=%d'%k,(lambda k:(lambda f:f['n_prior']>=k))(k))
for a,b in [(1,3),(2,5),(3,8),(5,13),(8,21),(12,31)]:
    mk('np%d_%d'%(a,b-1),(lambda a,b:(lambda f:a<=f['n_prior']<b))(a,b))
mk('gradn>=1',lambda f:f['grad_n']>=1)
mk('gradn>=2',lambda f:f['grad_n']>=2)
mk('gf==0&np>=1',lambda f:f['n_prior']>=1 and f['grad_frac']==0)
mk('gf>=0.05',lambda f:f['grad_frac']>=0.05)
mk('gf>=0.15',lambda f:f['grad_frac']>=0.15)
mk('gf>=0.30',lambda f:f['grad_frac']>=0.30)
mk('gap<5',lambda f:0<=f['gap_prev']<5)
mk('gap5_30',lambda f:5<=f['gap_prev']<30)
mk('gap>=30',lambda f:f['gap_prev']>=30)
mk('p1h==0&np>=1',lambda f:f['n_prior']>=1 and f['n_prior_1h']==0)
mk('p1h>=3',lambda f:f['n_prior_1h']>=3)
mk('p1h>=8',lambda f:f['n_prior_1h']>=8)
for lab,f in [('dev<0.5',lambda f:0<=f['dev_buy_sol']<0.5),('dev0.5_1.5',lambda f:0.5<=f['dev_buy_sol']<1.5),
              ('dev1.5_3',lambda f:1.5<=f['dev_buy_sol']<3),('dev>=3',lambda f:f['dev_buy_sol']>=3),
              ('dev>=5',lambda f:f['dev_buy_sol']>=5),('dev>=10',lambda f:f['dev_buy_sol']>=10),
              ('dev==0',lambda f:f['dev_buy_sol']==0),('devfirst',lambda f:f['dev_first']==1)]: mk(lab,f)
mk('np==0&dev>=2',lambda f:f['n_prior']==0 and f['dev_buy_sol']>=2)
mk('np==0&dev<1',lambda f:f['n_prior']==0 and 0<=f['dev_buy_sol']<1)
mk('np>=3&dev>=2',lambda f:f['n_prior']>=3 and f['dev_buy_sol']>=2)
mk('np>=3&gf>0',lambda f:f['n_prior']>=3 and f['grad_frac']>0)
P('mint filters',len(MF),[(n,len(v)) for n,v in MF][:6])
AGE=[('a<5',0,5),('a<20',0,20),('a<60',0,60),('a20_120',20,120),('a>=60',60,1e9),('any',0,1e9)]
EX=[(15,None,None,None),(60,None,None,None),(120,None,None,None),
    (60,0.30,None,None),(120,0.30,None,None),(120,0.50,None,None),
    (120,None,0.80,0.30),(60,None,0.40,0.25),(120,None,1.60,0.40)]
P('grid =',len(MF),'x',len(AGE),'x',len(EX),'=',len(MF)*len(AGE)*len(EX))
TR=[m for m in MS if FT[m]['h']==1]; VA=[m for m in MS if FT[m]['h']==2]
t0=time.time(); combos=0; pos=[]
cache={}
for ai,(an,alo,ahi) in enumerate(AGE):
    for ei,(H,trail,tp,sl) in enumerate(EX):
        full=backtest(MS,alo,ahi,H,trail,tp,sl)
        for mn,ms in MF:
            combos+=1
            sub={m:full[m] for m in ms if m in full}
            t={m:v for m,v in sub.items() if FT[m]['h']==1}
            if len(t)<25: continue
            a=agg(t)
            if a is None or a['mean']<=0: continue
            pos.append((mn,an,(H,trail,tp,sl),a['mean'],a['median'],a['k'],a['n']))
        if ei==0: P('  age %s done %.1fs'%(an,time.time()-t0))
P('combos swept',combos,'TRAIN-positive',len(pos),'elapsed',round(time.time()-t0,1))
for r in sorted(pos,key=lambda r:-r[3])[:40]: P('   ',r)
# validate any train-positives
P('--- VALIDATE (h==2) for train-positives ---')
surv=[]
for (mn,an,ex,trm,trmed,trk,trn) in pos:
    alo,ahi=[(x[1],x[2]) for x in AGE if x[0]==an][0]
    H,trail,tp,sl=ex
    ms=dict(MF)[mn]
    full=backtest([m for m in ms if FT[m]['h']==2],alo,ahi,H,trail,tp,sl)
    a=agg(full)
    if a is None or a['k']<20: continue
    ctrl=agg(backtest(VA,alo,ahi,H,trail,tp,sl))
    lo,nc=blo(a['per'])
    P('   %-14s %-8s %-22s trm=%+.4f vm=%+.4f vmed=%+.4f ctrl=%+.4f k=%d n=%d clus=%s bootLO=%s'%(
       mn,an,str(ex),trm,a['mean'],a['median'],ctrl['mean'],a['k'],a['n'],nc,
       ('%+.4f'%lo) if lo is not None else 'NA'))
    if a['mean']>0 and a['mean']>ctrl['mean'] and lo is not None and lo>0:
        surv.append((mn,an,ex,trm,a['mean'],a['median'],a['k'],a['n'],nc,lo,ctrl['mean']))
P('SURVIVORS (validate mean>0, beats control, bootLO>0):',len(surv))
for s in surv: P('   ',s)
OUT.close()
