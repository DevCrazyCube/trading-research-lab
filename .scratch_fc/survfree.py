"""SURVIVORSHIP-FREE test of the deployer-identity finding.
Universe: the 2,187 h12 launches covered by b11a_bodies (2.74% graduation rate vs a
3.16% base rate -> essentially unbiased), including the 2,127 that NEVER graduated.
Price path is the bonding curve itself: p = virtual_quote_after / virtual_token_after.
Harness: signal at trade j -> enter at the price of trade j+1; no overlap; mint-equal;
dropout charged at -30/-50/-100%; toll 1.14% and 2.5%."""
import sqlite3, pickle, json, hashlib, bisect, statistics as st, random, time
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb'))
OUT=open(S+'survfree.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
curve2mint=D['curve2mint']; mint2cre=D['mint2cre']; mint2bt=D['mint2bt']
mint2slot=D['mint2slot']; mint2comp=D['mint2comp']; WL=D['WL']
slope=D['slope']; inter=D['inter']
# slot->time residuals
res=[abs((inter+slope*s)-b) for (_,_,_,s,b,_) in WL]
res.sort()
P('slot->time |residual| sec p50/p90/p99: %.1f %.1f %.1f'%(res[len(res)//2],res[9*len(res)//10],res[99*len(res)//100]))
def slot2t(s): return inter+slope*s

curves=set(curve2mint)
cb=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
paths=defaultdict(list)
q="""select bonding_curve,slot,transaction_index,outer_index,inner_index,
      virtual_quote_after,virtual_token_after from reserve_observation"""
for bc,slot,txi,oi,ii,vqa,vta in cb.execute(q):
    if bc not in curves: continue
    if not vqa or not vta: continue
    paths[bc].append((slot,txi,oi,ii,vqa/vta))
cb.close()
for v in paths.values(): v.sort()
P('curves with a price path',len(paths))

# creator history (h12 only, strictly prior) -- same definition as the main sweep
bycre=defaultdict(list)
for bc,m,cr,slot,bt,comp in WL: bycre[cr].append(bt)
for v in bycre.values(): v.sort()
FT={}
for bc,pth in paths.items():
    m=curve2mint[bc]; cr=mint2cre[m]; bt=mint2bt[m]
    cl=bycre[cr]
    npri=bisect.bisect_left(cl,bt)
    FT[m]=dict(cre=cr,bt=bt,n_prior=npri,h=h3(m),comp=mint2comp[m],bc=bc,ntr=len(pth))
P('launches with path',len(FT))
P('np==0 count',sum(1 for v in FT.values() if v['n_prior']==0),
  'np>=1',sum(1 for v in FT.values() if v['n_prior']>0))
P('grad rate np==0 %.4f  np>=1 %.4f'%(
  sum(1 for v in FT.values() if v['n_prior']==0 and v['comp']==1)/max(1,sum(1 for v in FT.values() if v['n_prior']==0)),
  sum(1 for v in FT.values() if v['n_prior']>0 and v['comp']==1)/max(1,sum(1 for v in FT.values() if v['n_prior']>0))))

def backtest(mints, agemax_min, H_min, trail=None, cap=3.0):
    """returns per-mint (n_res, sum_gross, n_dropout)"""
    out={}
    for m in mints:
        f=FT[m]; pth=paths[f['bc']]
        ts=[slot2t(p[0]) for p in pth]; px=[p[4] for p in pth]
        n=len(pth); bt=f['bt']
        nr=0; sg=0.0; nd=0; free=-1.0
        for j in range(0,n-1):
            if (ts[j]-bt)/60.0 >= agemax_min: break     # signal-bar age gate
            if ts[j] < free: continue
            e=px[j+1]; et=ts[j+1]
            if e<=0: continue
            cut=et+H_min*60
            runmax=e; exitpx=None; exitts=None
            k=j+1
            while k<n and ts[k]<=cut:
                if px[k]>runmax: runmax=px[k]
                if trail is not None and px[k]<=runmax*(1-trail):
                    exitpx=px[k]; exitts=ts[k]; break
                k+=1
            if exitpx is None:
                # first trade at/after the horizon
                while k<n and ts[k]<cut: k+=1
                if k<n: exitpx=px[k]; exitts=ts[k]
            if exitpx is None:
                nd+=1; free=cut
            else:
                g=min(exitpx/e-1.0,cap); nr+=1; sg+=g; free=exitts
        if nr+nd: out[m]=(nr,sg,nd)
    return out

def agg(out, toll=0.0114, charge=-0.30):
    per={}; tot=0; r=0
    for m,(nr,sg,nd) in out.items():
        per[m]=((1-toll)*(nr+sg)-nr+nd*((1+charge)*(1-toll)-1))/(nr+nd); tot+=nr+nd; r+=nr
    if not per: return None
    v=list(per.values())
    return dict(mean=sum(v)/len(v),median=st.median(v),k=len(v),n=tot,res=r/tot,per=per)
random.seed(3)
def blo(per,reps=800):
    byc=defaultdict(list)
    for m,v in per.items(): byc[FT[m]['cre']].append(v)
    cs=list(byc); nc=len(cs)
    if nc<6: return None,nc
    o=[]
    for _ in range(reps):
        a=[]
        for _ in range(nc): a.extend(byc[cs[random.randrange(nc)]])
        o.append(sum(a)/len(a))
    o.sort(); return o[int(0.05*reps)],nc

ALLM=list(FT)
GRPS=[('np==0',[m for m in ALLM if FT[m]['n_prior']==0]),
      ('np>=1',[m for m in ALLM if FT[m]['n_prior']>0]),
      ('ALL',ALLM),
      ('np==0 h2',[m for m in ALLM if FT[m]['n_prior']==0 and FT[m]['h']==2]),
      ('np>=1 h2',[m for m in ALLM if FT[m]['n_prior']>0 and FT[m]['h']==2]),
      ('np==0 h1',[m for m in ALLM if FT[m]['n_prior']==0 and FT[m]['h']==1]),
      ('np>=1 h1',[m for m in ALLM if FT[m]['n_prior']>0 and FT[m]['h']==1]),
      ('GRADUATED only',[m for m in ALLM if FT[m]['comp']==1]),
      ('np==0 & GRAD',[m for m in ALLM if FT[m]['comp']==1 and FT[m]['n_prior']==0])]
t0=time.time()
for (agemax,H,trail) in [(20,120,0.30),(20,120,None),(20,60,0.30),(60,120,0.30),(20,30,None),(1e9,120,0.30)]:
    P('')
    P('=== ENTRY age<%s min | HOLD %dm | trail %s | cap +300%% | toll 1.14%% | dropout -30%%'%(
        agemax if agemax<1e8 else 'inf',H,trail))
    for lab,ms in GRPS:
        o=backtest(ms,agemax,H,trail)
        a=agg(o)
        if a is None: P('   %-16s no data'%lab); continue
        lo,nc=blo(a['per'])
        a100=agg(o,charge=-1.00); a25=agg(o,toll=0.025)
        P('   %-16s mean=%+.4f med=%+.4f k=%4d n=%5d res=%.3f clus=%4s bootLO=%s | d-100=%+.4f toll2.5=%+.4f'%(
            lab,a['mean'],a['median'],a['k'],a['n'],a['res'],nc,
            ('%+.4f'%lo) if lo is not None else 'NA',a100['mean'],a25['mean']))
P('elapsed',round(time.time()-t0,1))
OUT.close()
