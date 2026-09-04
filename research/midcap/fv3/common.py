import sys,os,json,time,math,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np
import fvh

TOLL=0.0114; TOLL2=0.025; DROPS=[-0.30,-0.50,-1.00]
PRIMARY=(-0.30,TOLL)
HOLDS=[5,10,15,30,60]
EXITS=[(None,None,1.0),(0.15,None,1.0),(0.30,None,1.0),(0.60,None,1.0),(None,-0.25,1.0),
       (0.15,-0.25,1.0),(0.30,-0.25,1.0),(0.30,-0.40,1.0),(0.60,-0.40,1.0),
       (0.15,-0.25,0.5),(0.30,-0.25,0.5),(0.60,-0.30,0.5)]

class Env: pass

def build(log=print):
    E=Env()
    mints,arrs,meta=fvh.load(minbars=22)
    b=fvh.Book(mints,arrs,meta); E.b=b
    log('mints %d bars %d'%(b.nm,b.N))
    eps=1e-300; N=b.N
    rng_abs=b.HI-b.LO; rng_pc=rng_abs/np.maximum(b.C,eps)
    typ=(b.HI+b.LO+b.C)/3.0
    clv=np.where(rng_abs>0,(b.C-b.LO)/np.maximum(rng_abs,eps),0.5)
    medV5=fvh.roll_med(b.V,b,5,1); medV20=fvh.roll_med(b.V,b,20,1)
    medV5_0=fvh.roll_med(b.V,b,5,0); medV15_5=fvh.roll_med(b.V,b,15,5)
    medR10=fvh.roll_med(rng_pc,b,10,1)
    sumV5=fvh.roll_sum(b.V,b,5,0); sumV20=fvh.roll_sum(b.V,b,20,0)
    sumTV5=fvh.roll_sum(typ*b.V,b,5,0); sumTV20=fvh.roll_sum(typ*b.V,b,20,0)
    sumHL5=fvh.roll_sum(rng_abs,b,5,0); sumCLV5=fvh.roll_sum(clv,b,5,0)
    C1=fvh.lag(b.C,b,1); C5=fvh.lag(b.C,b,5); C10=fvh.lag(b.C,b,10)
    TS1=fvh.lag(b.TS,b,1); gap1=(b.TS-TS1)/60.0
    sumGAP5=fvh.roll_sum(np.nan_to_num(gap1,nan=1.0),b,5,0)
    up=(b.C>C1).astype(float); sumUP10=fvh.roll_sum(np.nan_to_num(up,nan=0.0),b,10,0)
    absr=np.abs(b.C/np.maximum(C1,eps)-1.0); sumABS5=fvh.roll_sum(np.nan_to_num(absr,nan=0.0),b,5,0)
    rmaxC=fvh.runmax(b.C,b)
    F=collections.OrderedDict()
    F['vrel5']=b.V/np.maximum(medV5,eps)
    F['vrel20']=b.V/np.maximum(medV20,eps)
    F['vacc']=medV5_0/np.maximum(medV15_5,eps)
    F['vshare']=b.V/np.maximum(sumV20,eps)
    F['vsol5']=sumV5
    F['vsol1']=b.V
    F['rngrel']=rng_pc/np.maximum(medR10,eps)
    F['rngpc']=rng_pc
    F['dens10']=fvh.density(b,10)
    F['dens30']=fvh.density(b,30)
    F['gap']=gap1
    F['gapavg5']=sumGAP5/5.0
    F['eff5']=np.abs(b.C-C5)/np.maximum(sumHL5,eps)
    F['hlcc']=rng_abs/np.maximum(np.abs(b.C-C1),eps)
    F['vwdev5']=b.C/np.maximum(sumTV5/np.maximum(sumV5,eps),eps)-1.0
    F['vwdev20']=b.C/np.maximum(sumTV20/np.maximum(sumV20,eps),eps)-1.0
    F['clv']=clv
    F['clv5']=sumCLV5/5.0
    F['upfrac']=sumUP10/10.0
    F['illiq']=sumABS5/np.maximum(sumV5,eps)
    F['age']=(b.TS-b.btime[b.MID])/60.0
    F['mcap']=b.C*1e9
    F['dd']=b.C/np.maximum(rmaxC,eps)
    F['ret5']=b.C/np.maximum(C5,eps)-1.0
    F['ret10']=b.C/np.maximum(C10,eps)-1.0
    E.F=F; E.FN=list(F.keys()); E.nf=len(E.FN)
    E.Fm=np.vstack([F[k] for k in E.FN])
    elig=np.ones(N,bool)
    elig&=(b.idx>=21)
    elig&=(np.arange(N)+1)<b.ends[b.MID]
    elig&=np.all(np.isfinite(E.Fm),axis=0)
    E.elig=elig
    E.TR=elig&(b.mhh==1); E.VA=elig&(b.mhh==2)
    E.TRi=np.flatnonzero(E.TR); E.VAi=np.flatnonzero(E.VA)
    log('eligible %d train %d bars/%d mints  valid %d bars/%d mints'%(
        int(elig.sum()),E.TRi.size,len(set(b.MID[E.TRi].tolist())),
        E.VAi.size,len(set(b.MID[E.VAi].tolist()))))
    # structures
    STRUCT=collections.OrderedDict()
    for H in HOLDS:
        k=fvh.build_exit(b,H); mw=min(H+1,65)
        Rmax,Rmin,L=fvh.path_ext(b,k,mw); klist=k.tolist()
        for (tp,sl,fr) in EXITS:
            g=fvh.gross(b,k,Rmax,Rmin,L,tp=tp,sl=sl,tp_frac=fr)
            nm='H%d/tp%s/sl%s/f%s'%(H,tp,sl,fr)
            nets={}
            for d in DROPS: nets[(d,TOLL)]=fvh.netify(g,k,TOLL,d)
            nets[(-0.30,TOLL2)]=fvh.netify(g,k,TOLL2,-0.30)
            STRUCT[nm]=dict(k=klist,karr=k,nets=nets,H=H,tp=tp,sl=sl,fr=fr)
        del Rmax,Rmin,L
    E.STRUCT=STRUCT; E.SN=list(STRUCT.keys())
    E.MIDl=b.MID.tolist(); E.ENDl=b.ends.tolist()
    return E

def make_eval(E):
    MIDl=E.MIDl; ENDl=E.ENDl; MIDa=E.b.MID; STRUCT=E.STRUCT
    def greedy(sig,klist):
        taken=[]; cur=-1; nxt=-1
        for i in sig:
            m=MIDl[i]
            if m!=cur: cur=m; nxt=-1
            if i<nxt: continue
            j=i+1; e=ENDl[m]
            if j>=e: continue
            taken.append(j); kk=klist[j]
            nxt=kk if kk>=0 else e+1
        return taken
    def ev(sig,sname,key=PRIMARY,boot=0):
        st=STRUCT[sname]
        js=greedy(sig.tolist() if hasattr(sig,'tolist') else sig,st['k'])
        if not js: return None
        js=np.asarray(js,dtype=np.int64)
        r=st['nets'][key][js]; mid=MIDa[js]
        u,inv=np.unique(mid,return_inverse=True)
        pm=np.bincount(inv,weights=r)/np.bincount(inv)
        d=dict(n=int(js.size),clusters=int(u.size),mean=float(pm.mean()),
               median=float(np.median(pm)),res=float((st['karr'][js]>=0).mean()),pm=pm,js=js)
        if boot: d['lo']=fvh.boot_lo(pm,B=boot)
        return d
    return greedy,ev
