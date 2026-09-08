"""Simulator: entry mask x exit structure x position structure -> mint-equal stats."""
import pickle, math, numpy as np
SCR='/home/anont/meme/.scr/'
P=pickle.load(open(SCR+'paths.pkl','rb'))
per=P['per']; TPS=P['TPS']; SLS=P['SLS']; TRS=P['TRS']; ADDS=P['ADDS']; HS=P['HS']
FEATN=P['FEATN']; gmax=P['gmax']
INF=10**9
TOLL=0.0114
MINTS=sorted(per.keys())
HIDX={h:i for i,h in enumerate(HS)}

# ---------------- feature matrix ----------------
MFEATN=['pcreate','pgrad','age_at_first','lret15','lvol15','lmc0']
ALLF=FEATN+MFEATN
NF=len(ALLF)
FM={}; VALID={}
for m in MINTS:
    d=per[m]; n=len(d['ts'])
    X=np.zeros((n,NF))
    X[:,:len(FEATN)]=d['F']
    mf=d['MF']; lr,lv,lm=d['launch']
    X[:,len(FEATN)+0]=mf[4]; X[:,len(FEATN)+1]=mf[5]; X[:,len(FEATN)+2]=mf[6]
    X[:,len(FEATN)+3]=lr;   X[:,len(FEATN)+4]=lv;    X[:,len(FEATN)+5]=lm
    V=np.ones((n,NF),dtype=bool)
    age=d['F'][:,0]
    for k in (len(FEATN)+3,len(FEATN)+4):
        V[:,k]=age>=20.0
    FM[m]=X; VALID[m]=V

TRAIN=[m for m in MINTS if per[m]['h']==1]
VALD =[m for m in MINTS if per[m]['h']==2]

# ---------------- exit structures ----------------
# spec = (kind, params...)
def exit_specs():
    E=[]
    for H in HS: E.append(('H',H))
    for tp in TPS:
        for H in (15,60,240): E.append(('TP',tp,H))
    for tp in (0.25,0.50,1.00,2.00):
        for sl in SLS:
            for H in (60,240): E.append(('BR',tp,sl,H))
    for tr in TRS:
        for H in (60,240): E.append(('TR',tr,H))
    for tp in (0.25,0.50,1.00):
        for H in (60,240): E.append(('SC',tp,0.5,H))
    return E
EXITS=exit_specs()

POS=[('FULL',),('ADD',0.20),('ADD',0.40),('PYR',0.25),('PYR',1.00)]

TPI={v:i for i,v in enumerate(TPS)}; SLI={v:i for i,v in enumerate(SLS)}
TRI={v:i for i,v in enumerate(TRS)}; ADI={v:i for i,v in enumerate(ADDS)}

def resolve(m, a, ex):
    """return (exit_index or -1 for dropout, exit_price, resolved_bool)"""
    d=per[m]; n=len(d['ts']); op=d['op']
    k=ex[0]
    if k=='H':
        H=ex[1]; hk=HIDX[H]; e=d['eidx'][hk][a]
        if e<0: return -1,None,False
        return e,op[e],True
    if k=='TP':
        tp,H=ex[1],ex[2]; hk=HIDX[H]
        L=d['lastidx'][hk][a]; t=d['TP'][a][TPI[tp]]
        e=d['eidx'][hk][a]
        if t<=L: return t, d['op'][a]*(1+tp), True
        if e<0: return -1,None,False
        return e,op[e],True
    if k=='BR':
        tp,sl,H=ex[1],ex[2],ex[3]; hk=HIDX[H]
        L=d['lastidx'][hk][a]; e=d['eidx'][hk][a]
        t=d['TP'][a][TPI[tp]]; s=d['SL'][a][SLI[sl]]
        if s<=L and s<=t: return s, d['op'][a]*(1-sl), True
        if t<=L: return t, d['op'][a]*(1+tp), True
        if e<0: return -1,None,False
        return e,op[e],True
    if k=='TR':
        tr,H=ex[1],ex[2]; hk=HIDX[H]
        L=d['lastidx'][hk][a]; e=d['eidx'][hk][a]
        s=d['TR'][a][TRI[tr]]
        if s<=L:
            # exit price approximated at trailing trigger level using running max up to s-1
            rmax=float(np.max(d['hi'][a:s])) if s>a else d['op'][a]
            return s, rmax*(1-tr), True
        if e<0: return -1,None,False
        return e,op[e],True
    if k=='SC':
        # handled specially in trade_ret
        tp,frac,H=ex[1],ex[2],ex[3]; hk=HIDX[H]
        e=d['eidx'][hk][a]
        if e<0: return -1,None,False
        return e,op[e],True
    raise ValueError(k)

def trade_ret(m,a,ex,pos,toll,drop):
    d=per[m]; P0=d['op'][a]
    ei,px,res=resolve(m,a,ex)
    # position: base deployment
    kind=pos[0]
    if kind=='FULL': base=1.0; extra=0.0; addpx=None; ai=INF
    elif kind=='ADD':
        base=0.5; dfrac=pos[1]; ai=d['AD'][a][ADI[dfrac]]; addpx=P0*(1-dfrac); extra=0.5
    else:
        base=0.5; ufrac=pos[1]; ai=d['TP'][a][TPI[ufrac]]; addpx=P0*(1+ufrac); extra=0.5
    if not res:
        # dropout: use last available bar for add determination
        n=len(d['ts']); L=n-1
        added = 1.0 if ai<=L else 0.0
        dep=base+extra*added
        return drop*dep - toll*dep, False, ei
    added = 1.0 if ai<=ei else 0.0
    dep=base+extra*added
    if ex[0]=='SC':
        tp,frac,H=ex[1],ex[2],ex[3]; hk=HIDX[H]
        L=d['lastidx'][hk][a]; t=d['TP'][a][TPI[tp]]
        if t<=L:
            g = frac*(1+tp) + (1-frac)*(px/P0)
        else:
            g = px/P0
        r0 = g-1.0
    else:
        r0 = px/P0-1.0
    pnl = base*r0
    if added: pnl += extra*(px/addpx-1.0)
    return pnl - toll*dep, True, ei

def run(mask_fn, mset, ex, pos, toll=TOLL, drop=-0.50, need_resolvable=True):
    """mask_fn(m)->bool array over signal bars. returns stats dict."""
    permint=[]; ntr=0; nres=0
    H=ex[-1] if ex[0]!='H' else ex[1]
    for m in mset:
        d=per[m]; n=len(d['ts']); ts=d['ts']
        sig=mask_fn(m)
        if sig is None: continue
        idx=np.flatnonzero(sig)
        if idx.size==0: continue
        rs=[]; block=-1
        for s in idx:
            a=s+1
            if a>=n: break
            if a<=block: continue
            if need_resolvable and ts[a]+H*60>gmax: break
            r,res,ei=trade_ret(m,a,ex,pos,toll,drop)
            rs.append(r); ntr+=1
            if res: nres+=1
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    if not permint: return None
    arr=np.array(permint)
    return dict(mean=float(arr.mean()), median=float(np.median(arr)), n=ntr,
                clusters=len(permint), res=nres/max(1,ntr), arr=arr)
