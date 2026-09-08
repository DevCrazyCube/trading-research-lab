import numpy as np, bisect, json, itertools, sys, math, collections, pickle
D=np.load('/home/anont/meme/.ff3/panel2.npz',allow_pickle=False)
X=D['X']; M=D['M']; curves=D['curves']; h=D['h']
valid=D['valid']; rend=D['rend']; grad=D['grad']
tph=D['tph']; tpp=D['tpp']; slh=D['slh']; slp=D['slp']; adh=D['adh']; adp=D['adp']
eslot=D['eslot']; xslot=D['xslot']
names=list(D['names']); WINS=list(D['WINS']); HORS=list(D['HORS']); TPS=list(D['TPS']); SLS=list(D['SLS']); MODES=[str(x) for x in D['MODES']]
NR=X.shape[0]
FEAT=np.concatenate([X,M],axis=1)
NFLOW=X.shape[1]

# curve ids
uc,cid=np.unique(curves,return_inverse=True)
NC=len(uc)

TOLLS={'toll114':0.0114,'toll250':0.025}

# ---- ordering + nxt per (mode,horizon)
ORD={}
for mi in range(len(MODES)):
    for hi in range(len(HORS)):
        v=valid[mi,hi]
        es=eslot[mi,hi]
        key=cid.astype(np.int64)*(10**10)+np.where(v,es,10**9)
        order=np.argsort(key,kind='stable')
        order=order[v[order]]
        c_o=cid[order]; e_o=es[order]
        n=len(order)
        H=HORS[hi]
        nxt=np.empty(n,dtype=np.int64)
        # boundaries
        starts={}
        b=0
        while b<n:
            c=c_o[b]; e=b
            while e<n and c_o[e]==c: e+=1
            sub=e_o[b:e]
            # first j>i in [b,e) with e_o[j] > e_o[i]+H
            pos=np.searchsorted(sub,sub+H,side='right')+b
            nxt[b:e]=np.minimum(pos,e)
            b=e
        ORD[(mi,hi)]=(order,c_o,e_o,nxt,n)

def greedy(mi,hi,mask):
    order,c_o,e_o,nxt,n=ORD[(mi,hi)]
    sel=mask[order]
    idxsel=np.flatnonzero(sel)
    if len(idxsel)==0: return np.empty(0,dtype=np.int64)
    lst=idxsel.tolist()
    acc=[]
    p=0; L=len(lst)
    while p<L:
        i=lst[p]; acc.append(i)
        t=int(nxt[i])
        p=bisect.bisect_left(lst,t,p+1)
    return order[np.array(acc,dtype=np.int64)]

# ---- structures
def struct_ret(mi,hi,rows,kind,tp=None,sl=None):
    re=rend[mi,hi][rows]
    if kind=='hold': return re
    if kind=='tp':
        hgt=tph[mi,hi,tp][rows]; v=tpp[mi,hi,tp][rows]
        return np.where(hgt>=0,v,re)
    if kind=='sl':
        hgs=slh[mi,hi,sl][rows]; v=slp[mi,hi,sl][rows]
        return np.where(hgs>=0,v,re)
    if kind=='brk':
        a=tph[mi,hi,tp][rows]; av=tpp[mi,hi,tp][rows]
        b=slh[mi,hi,sl][rows]; bv=slp[mi,hi,sl][rows]
        A=np.where(a>=0,a,np.iinfo(np.int32).max); B=np.where(b>=0,b,np.iinfo(np.int32).max)
        r=re.copy()
        tpfirst=(A<B)&(a>=0)
        slfirst=(B<=A)&(b>=0)
        r=np.where(tpfirst,av,r); r=np.where(slfirst,bv,r)
        return r
    if kind=='scale':
        hgt=tph[mi,hi,tp][rows]; v=tpp[mi,hi,tp][rows]
        return np.where(hgt>=0,0.5*v+0.5*re,re)
    if kind=='scalesl':
        a=tph[mi,hi,tp][rows]; av=tpp[mi,hi,tp][rows]
        b=slh[mi,hi,sl][rows]; bv=slp[mi,hi,sl][rows]
        A=np.where(a>=0,a,np.iinfo(np.int32).max); B=np.where(b>=0,b,np.iinfo(np.int32).max)
        r=re.copy()
        r=np.where((A<B)&(a>=0),0.5*av+0.5*re,r)
        r=np.where((B<=A)&(b>=0),bv,r)
        return r
    if kind=='pyr':
        a=adh[mi,hi][rows]; ap=adp[mi,hi][rows]
        fin=1.0+re
        r2=np.where(a>=0,fin/np.maximum(ap,1e-12)-1.0,0.0)
        return np.where(a>=0,0.5*re+0.5*r2,0.5*re)
    raise ValueError(kind)

STRUCTS=[('hold',None,None)]
for t in range(len(TPS)): STRUCTS.append(('tp',t,None))
for s in range(len(SLS)): STRUCTS.append(('sl',None,s))
for t in range(len(TPS)):
    for s in range(len(SLS)): STRUCTS.append(('brk',t,s))
for t in range(len(TPS)): STRUCTS.append(('scale',t,None))
for t in range(len(TPS)):
    for s in range(len(SLS)): STRUCTS.append(('scalesl',t,s))
STRUCTS.append(('pyr',None,None))

def evaluate(mi,hi,mask,struct,toll,gradcharge=None):
    rows=greedy(mi,hi,mask)
    if len(rows)==0: return None
    kind,t,s=struct
    r=struct_ret(mi,hi,rows,kind,t,s).astype(np.float64)-toll
    if gradcharge is not None:
        g=grad[mi,hi][rows].astype(bool)
        r=np.where(g,gradcharge,r)
    c=cid[rows]
    ucc,inv=np.unique(c,return_inverse=True)
    sm=np.bincount(inv,weights=r); cn=np.bincount(inv)
    per=sm/cn
    return dict(n=len(rows),k=len(ucc),mean=float(per.mean()),median=float(np.median(per)),
                permint=per,rows=rows,trade_mean=float(r.mean()),trade_median=float(np.median(r)),
                gradfrac=float(grad[mi,hi][rows].mean()))
if __name__=='__main__':
    pass
