import numpy as np, math

C=np.load('/home/anont/meme/_fv0/cache.npz',allow_pickle=True)
E_mint=C['E_mint'].astype(np.int64); E_bar=C['E_bar'].astype(np.int64); E_h=C['E_h']
E_P=C['E_P']; TPIDX=C['TPIDX']; SLIDX=C['SLIDX']; HIDX=C['HIDX']; FEAT=C['FEAT']
OPEN=C['OPEN']; offs=C['offs']; NBAR=C['NBAR']
FEATNAMES=[str(x) for x in C['featnames']]
HOR=[int(x) for x in C['horizons']]; TPS=[float(x) for x in C['tps']]; SLS=[float(x) for x in C['sls']]
MINTS=[str(x) for x in C['mints']]
NM=len(NBAR); BIG=10**9; NE=len(E_mint)
TOLL=0.0114; TOLL2=0.025

_EB_l=E_bar.tolist(); _EM_l=E_mint.tolist()
_cache={}

def exit_arrays(hi,tpi,sli,partial=0):
    """partial=0 full exit at first trigger; partial=1 sell HALF at TP, rest runs to SL/time.
    returns dict of arrays: w1,g1,r1,w2,g2,r2,exitbar   (w1+w2==1)"""
    key=(hi,tpi,sli,partial)
    if key in _cache: return _cache[key]
    hb=HIDX[:,hi]
    heff=np.where(hb<0,BIG,hb)
    tp=TPIDX[:,tpi] if tpi>=0 else np.full(NE,BIG,dtype=np.int64)
    sl=SLIDX[:,sli] if sli>=0 else np.full(NE,BIG,dtype=np.int64)
    tprice=np.full(NE,np.nan)
    okh=hb>=0
    idx=np.where(okh)[0]
    tprice[idx]=OPEN[offs[E_mint[idx]]+hb[idx]]/E_P[idx]-1.0

    w1=np.ones(NE); g1=np.full(NE,np.nan); r1=np.zeros(NE,bool)
    w2=np.zeros(NE); g2=np.full(NE,np.nan); r2=np.zeros(NE,bool)

    if partial==0 or tpi<0:
        is_sl=(sl<=tp)&(sl<=heff)&(sl<BIG)
        is_tp=(~is_sl)&(tp<heff)&(tp<BIG)
        is_t =(~is_sl)&(~is_tp)&(heff<BIG)
        if sli>=0: g1[is_sl]=-SLS[sli]
        if tpi>=0: g1[is_tp]=TPS[tpi]
        g1[is_t]=tprice[is_t]
        r1=is_sl|is_tp|is_t
        k=np.minimum(np.minimum(tp,sl),heff)
    else:
        p=TPS[tpi]
        is_sl_first=(sl<=tp)&(sl<=heff)&(sl<BIG)
        tp_first=(~is_sl_first)&(tp<heff)&(tp<BIG)
        is_t=(~is_sl_first)&(~tp_first)&(heff<BIG)
        # stopped out before any TP -> full position at -sl
        g1[is_sl_first]=-SLS[sli] if sli>=0 else np.nan
        r1|=is_sl_first
        # plain time exit, no tp
        g1[is_t]=tprice[is_t]; r1|=is_t
        # tp first: leg1 = half at +p (resolved), leg2 = rest
        w1[tp_first]=0.5; w2[tp_first]=0.5
        g1[tp_first]=p; r1|=tp_first
        rem_sl=tp_first&(sl<heff)&(sl<BIG)
        rem_t =tp_first&(~rem_sl)&(heff<BIG)
        if sli>=0: g2[rem_sl]=-SLS[sli]
        g2[rem_t]=tprice[rem_t]
        r2=rem_sl|rem_t
        k=np.where(tp_first,np.minimum(np.where(sl<heff,sl,heff),BIG),np.minimum(np.minimum(tp,sl),heff))
    anyres=r1|(w2>0)
    exitbar=np.where(k<BIG,np.minimum(k,BIG-1),NBAR[E_mint]+10**6)
    out=dict(w1=w1,g1=g1,r1=r1,w2=w2,g2=g2,r2=r2,exitbar=exitbar,
             eb_l=exitbar.tolist())
    _cache[key]=out
    return out

def walk(sig_idx, eb_l):
    out=[]; cur=-1; cm=-1
    EB=_EB_l; EM=_EM_l
    for k in sig_idx:
        m=EM[k]
        if m!=cm: cm=m; cur=-1
        b=EB[k]
        if b>cur:
            out.append(k); cur=eb_l[k]
    return out

def net_of(A,sel,toll,drop):
    w1=A['w1'][sel]; g1=A['g1'][sel]; r1=A['r1'][sel]
    w2=A['w2'][sel]; g2=A['g2'][sel]; r2=A['r2'][sel]
    n1=np.where(r1,(1.0+np.nan_to_num(g1))*(1.0-toll)-1.0,drop)
    n2=np.where(r2,(1.0+np.nan_to_num(g2))*(1.0-toll)-1.0,drop)
    return w1*n1+w2*n2

def stats(sel,A,toll=TOLL,drop=-0.30):
    net=net_of(A,sel,toll,drop)
    m=E_mint[sel]
    s=np.bincount(m,weights=net,minlength=NM); c=np.bincount(m,minlength=NM)
    act=c>0; mm=s[act]/c[act]
    return mm

def trimmed(mm,f=0.05):
    if len(mm)<10: return float(mm.mean())
    x=np.sort(mm); k=int(f*len(x))
    return float(x[k:len(x)-k].mean())

def evaluate(sig_idx,hi,tpi,sli,partial=0,full=False):
    A=exit_arrays(hi,tpi,sli,partial)
    sel=walk(sig_idx,A['eb_l'])
    if len(sel)<5: return None
    sel=np.array(sel,dtype=np.int64)
    mm=stats(sel,A)
    r=dict(n=int(len(sel)),k=int(len(mm)),
           mean=float(mm.mean()),med=float(np.median(mm)),trim=trimmed(mm),
           fpos=float((mm>0).mean()))
    tot=A['w1'][sel]+A['w2'][sel]
    resw=A['w1'][sel]*A['r1'][sel]+A['w2'][sel]*A['r2'][sel]
    r['res']=float(resw.sum()/tot.sum())
    if full:
        r['mm']=mm; r['sel']=sel
        for tag,toll,drop in (('b',TOLL,-0.50),('c',TOLL,-1.00),('d',TOLL2,-0.30),('e',TOLL2,-1.00)):
            m2=stats(sel,A,toll,drop)
            r['mean_'+tag]=float(m2.mean()); r['med_'+tag]=float(np.median(m2)); r['trim_'+tag]=trimmed(m2)
    return r

def boot_ci(mm,B=4000,seed=7):
    rng=np.random.default_rng(seed); k=len(mm)
    if k<5: return (float('nan'),float('nan'))
    bs=mm[rng.integers(0,k,size=(B,k))].mean(axis=1)
    return (float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5)))

def boot_ci_med(mm,B=4000,seed=7):
    rng=np.random.default_rng(seed); k=len(mm)
    if k<5: return (float('nan'),float('nan'))
    bs=np.median(mm[rng.integers(0,k,size=(B,k))],axis=1)
    return (float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5)))
