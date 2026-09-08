"""Build bar panel + precomputed exit-return matrices. h in (1,2) mints ONLY.
Harness contract:
 A entry at OPEN of next REAL bar after the signal bar
 B non-overlap enforced later at eval time (per mint)
 C mint-equal weighting at eval time
 D dropouts charged at -30/-50/-100
 E toll 1.14% round trip (and 2.5% variant at eval time)
 F simple returns
 G no conditioning on total bar count / continued listing
"""
import sqlite3, json, hashlib, os, pickle, math, time
import numpy as np
from collections import defaultdict

OUT='/home/anont/meme/_c3'
L=open(OUT+'/build.log','w')
def p(*a):
    L.write(' '.join(str(x) for x in a)+'\n'); L.flush()
T0=time.time()

def H(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

w=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
wl={}; creates=[]
for m,cr,cs,bt in w.execute("select mint,creator,create_slot,block_time from window_label"):
    if H(m)==0: continue          # reserved holdout: never touched
    wl[m]=(cr,cs,bt); creates.append((cs,bt,cr,m))
creates.sort()
p("window_label rows kept (h in 1,2):", len(wl))
seen=defaultdict(int); creator_prior={}
for cs,bt,cr,m in creates:
    creator_prior[m]=seen[cr]; seen[cr]+=1
bts_arr=np.array([x[1] for x in creates])
cohort10={m:int(np.searchsorted(bts_arr,bt,'left')-np.searchsorted(bts_arr,bt-600,'left'))
          for cs,bt,cr,m in creates}

c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
mints=[]; barsets=[]
for m,nb,bj,st in c.execute("select mint,n_bars,bars_json,status from ohlcv"):
    if H(m)==0: continue
    if st!='ok' or not bj: continue
    b=json.loads(bj)
    if not b or len(b)<3: continue
    b.sort(key=lambda x:x[0])
    mints.append(m); barsets.append(b)
p("mints with bars (h in 1,2):", len(mints), "bars:", sum(len(b) for b in barsets))

FEATNAMES=['ret1','ret5m','ret15m','ret30m','dd_ath','runup','rng','body','upwick',
           'rvol10','volratio','volaccel','density5','age_min','px_vs_start','logpx',
           'cumvol_log','trailvol_log']
MNAMES=['m_ttg_log','m_hour','m_creator_prior','m_cohort10','m_px0_log','m_v0_log']
NF=len(FEATNAMES); NM=len(MNAMES)

mint_bars=[]; segs_f=[]; segs_m=[]; segs_id=[]; segs_ts=[]; segs_pos=[]
for mid,(m,b) in enumerate(zip(mints,barsets)):
    a=np.asarray(b,dtype=np.float64)
    ts,op,hi,lo,cl,vol=a[:,0],a[:,1],a[:,2],a[:,3],a[:,4],a[:,5]
    n=len(ts); mint_bars.append((ts,op,hi,lo,cl,vol))
    F=np.zeros((n,NF))
    prev=np.empty(n); prev[0]=cl[0]; prev[1:]=cl[:-1]
    F[:,0]=cl/np.maximum(prev,1e-300)-1
    for k,Ls in enumerate([300,900,1800]):
        idx=np.maximum(np.searchsorted(ts,ts-Ls,'right')-1,0)
        F[:,1+k]=cl/np.maximum(cl[idx],1e-300)-1
    rmax=np.maximum.accumulate(hi); rmin=np.minimum.accumulate(lo)
    F[:,4]=cl/np.maximum(rmax,1e-300)-1
    F[:,5]=cl/np.maximum(rmin,1e-300)-1
    F[:,6]=(hi-lo)/np.maximum(cl,1e-300)
    F[:,7]=(cl-op)/np.maximum(op,1e-300)
    F[:,8]=(hi-np.maximum(op,cl))/np.maximum(cl,1e-300)
    r1=F[:,0]; rv=np.zeros(n); tv=np.zeros(n)
    for i in range(n):
        s=max(0,i-9); rv[i]=r1[s:i+1].std() if i>=2 else 0.0
        s2=max(0,i-19); tv[i]=np.median(vol[s2:i+1])
    F[:,9]=rv; F[:,10]=vol/np.maximum(tv,1e-12); F[:,17]=np.log10(np.maximum(tv,1e-9))
    cv=np.cumsum(vol); cvp=np.concatenate([[0.0],cv])
    i5=np.searchsorted(ts,ts-300,'left'); i10=np.searchsorted(ts,ts-600,'left')
    F[:,11]=(cv-cvp[i5])/np.maximum(cvp[i5]-cvp[i10],1e-9)
    F[:,12]=np.arange(n)-i5+1
    F[:,13]=(ts-ts[0])/60.0
    F[:,14]=cl/max(op[0],1e-300)-1
    F[:,15]=np.log10(np.maximum(cl,1e-300))
    F[:,16]=np.log10(np.maximum(cv,1e-9))
    bt = wl[m][2] if m in wl else ts[0]
    M=np.array([math.log10(max(1.0,ts[0]-bt)), (bt//3600)%24,
                min(creator_prior.get(m,0),20), min(cohort10.get(m,0),200),
                math.log10(max(op[0],1e-300)), math.log10(max(vol[0],1e-9))])
    segs_f.append(F); segs_m.append(np.tile(M,(n,1)))
    segs_id.append(np.full(n,mid,dtype=np.int32)); segs_ts.append(ts)
    segs_pos.append(np.arange(n,dtype=np.int32))

FEAT=np.concatenate(segs_f); META=np.concatenate(segs_m)
mint_id=np.concatenate(segs_id); TS=np.concatenate(segs_ts); bar_pos=np.concatenate(segs_pos)
N=len(TS); p("panel bars:",N, "t=%.1f"%(time.time()-T0))

# ---------------- exit / position simulator ----------------
TOLL_LEG=0.0114/2.0
def sim(mid,i,Hm,tp=None,sl=None,trail=None,half_tp=None,pos='flat'):
    ts,op,hi,lo,cl,vol=mint_bars[mid]
    n=len(ts); j=i+1
    if j>=n: return (np.nan,0,0.0)          # no entry possible
    e=op[j]
    if not (e>0): return (np.nan,0,0.0)
    t0=ts[j]; dl=t0+Hm*60.0
    k=int(np.searchsorted(ts,dl,'left')); resolved = k<n
    last = k if resolved else n
    add_f=0.0; add_px=0.0
    if pos in ('pyr','avg'):
        j2=int(np.searchsorted(ts,t0+300.0,'left'))
        if j2<n and j2<last:
            px2=op[j2]
            # BOUNDED add-legs: an unbounded average-down manufactures fiction
            # (buying an arbitrarily small price tick -> unbounded multiple).
            if pos=='pyr' and e<px2<=2.0*e: add_f=0.5; add_px=px2
            elif pos=='avg' and 0.5*e<=px2<0.9*e: add_f=0.5; add_px=px2
    base=0.5 if pos in ('pyr','avg') else 1.0
    x=None; part=None; peak=e
    for t in range(j,last):
        o_,h_,l_,c_=op[t],hi[t],lo[t],cl[t]
        if sl is not None:
            s=e*(1-sl)
            if l_<=s: x=min(o_,s); break
        if tp is not None:
            q=e*(1+tp)
            if h_>=q: x=max(o_,q); break
        if half_tp is not None and part is None:
            q=e*(1+half_tp)
            if h_>=q: part=max(o_,q)
        if trail is not None:
            if h_>peak: peak=h_
            if peak>e and c_<=peak*(1-trail): x=c_; break
    tot=base+add_f
    cost=(base+add_f)*2*TOLL_LEG
    if x is None and not resolved:
        return (np.nan,-1,tot)              # dropout, charged at eval time
    if x is None: x=op[k]
    if part is not None:
        g=base*(0.5*(part/e-1.0)+0.5*(x/e-1.0))
    else:
        g=base*(x/e-1.0)
    if add_f>0: g+=add_f*(x/add_px-1.0)
    return (g,1,tot)

EXITS=[
 ('t5',   dict(Hm=5)),   ('t10',  dict(Hm=10)),  ('t15', dict(Hm=15)),
 ('t30',  dict(Hm=30)),  ('t60',  dict(Hm=60)),  ('t120',dict(Hm=120)),
 ('t240', dict(Hm=240)),
 ('t15tp25', dict(Hm=15,tp=0.25)), ('t15tp50', dict(Hm=15,tp=0.50)),
 ('t30tp25', dict(Hm=30,tp=0.25)), ('t30tp50', dict(Hm=30,tp=0.50)),
 ('t60tp100',dict(Hm=60,tp=1.00)),
 ('t15sl25', dict(Hm=15,sl=0.25)), ('t30sl30', dict(Hm=30,sl=0.30)),
 ('t60sl30', dict(Hm=60,sl=0.30)),
 ('t30tp50sl25', dict(Hm=30,tp=0.50,sl=0.25)),
 ('t30tr25', dict(Hm=30,trail=0.25)), ('t60tr35', dict(Hm=60,trail=0.35)),
 ('t15h25', dict(Hm=15,half_tp=0.25)), ('t60h50', dict(Hm=60,half_tp=0.50)),
]
POS_EXTRA=['t15','t30','t60','t30tp50','t60tr35','t30sl30']
COMBOS=[(nm,dict(kw),'flat') for nm,kw in EXITS]
for nm,kw in EXITS:
    if nm in POS_EXTRA:
        for ps in ('pyr','avg'):
            COMBOS.append((nm+'_'+ps,dict(kw),ps))
p("exit x position combos:", len(COMBOS))

GROSS=np.full((len(COMBOS),N),np.nan,dtype=np.float32)
STATE=np.zeros((len(COMBOS),N),dtype=np.int8)
SIZE=np.zeros((len(COMBOS),N),dtype=np.float32)
for ci,(nm,kw,ps) in enumerate(COMBOS):
    o=0
    for mid,b in enumerate(barsets):
        n=len(b)
        for i in range(n):
            g,st,tot=sim(mid,i,pos=ps,**kw)
            GROSS[ci,o+i]=g; STATE[ci,o+i]=st; SIZE[ci,o+i]=tot
        o+=n
    p("  done",nm,ps,"t=%.1f"%(time.time()-T0))

pickle.dump(dict(mints=mints,mint_id=mint_id,TS=TS,FEAT=FEAT,META=META,bar_pos=bar_pos,
                 FEATNAMES=FEATNAMES,MNAMES=MNAMES,
                 COMBONAMES=[x[0]+('' if x[2]=='flat' else '') for x in COMBOS],
                 COMBOS=[(x[0],x[1],x[2]) for x in COMBOS],
                 GROSS=GROSS,STATE=STATE,SIZE=SIZE),
            open(OUT+'/panel.pkl','wb'),protocol=4)
p("written",os.path.getsize(OUT+'/panel.pkl'),"t=%.1f"%(time.time()-T0))

# also need exit TIMES for the non-overlap rule -> recompute exit ts per combo
EXTS=np.full((len(COMBOS),N),np.nan,dtype=np.float64)
ENTTS=np.full(N,np.nan,dtype=np.float64)
o=0
for mid,b in enumerate(barsets):
    ts=mint_bars[mid][0]; n=len(ts)
    ENTTS[o:o+n-1]=ts[1:]; o+=n
o=0
for mid,b in enumerate(barsets):
    ts,op,hi,lo,cl,vol=mint_bars[mid]; n=len(ts)
    for ci,(nm,kw,ps) in enumerate(COMBOS):
        Hm=kw['Hm']; tp=kw.get('tp'); sl=kw.get('sl'); tr=kw.get('trail')
        for i in range(n-1):
            j=i+1; e=op[j]; t0=ts[j]; dl=t0+Hm*60.0
            k=int(np.searchsorted(ts,dl,'left')); resolved=k<n; last=k if resolved else n
            xt=None; peak=e
            for t in range(j,last):
                if sl is not None and lo[t]<=e*(1-sl): xt=ts[t]; break
                if tp is not None and hi[t]>=e*(1+tp): xt=ts[t]; break
                if tr is not None:
                    if hi[t]>peak: peak=hi[t]
                    if peak>e and cl[t]<=peak*(1-tr): xt=ts[t]; break
            if xt is None: xt = ts[k] if resolved else ts[n-1]+Hm*60.0
            EXTS[ci,o+i]=xt
    o+=n
np.save(OUT+'/exts.npy',EXTS); np.save(OUT+'/entts.npy',ENTTS)
p("exit-times written t=%.1f"%(time.time()-T0))
L.close()
