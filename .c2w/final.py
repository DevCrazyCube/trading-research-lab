import numpy as np, itertools
OUT=open('/home/anont/meme/.c2w/final.txt','w')
def p(*a): print(*a,file=OUT); OUT.flush()
d=np.load('/home/anont/meme/.c2w/mat.npz',allow_pickle=True)
X=d['X'].astype(float); mint_id=d['mint_id']; ent=d['ent_ts']; xit=d['exit_ts']
g=d['ret_g']; ok=d['ok'].astype(bool); hs=d['hs']
FN=[str(x) for x in d['featnames']]; NF=len(FN)
X=np.where(np.isfinite(X),X,np.nan)
for k in range(NF):
    c=X[:,k]; c[~np.isfinite(c)]=np.nanmedian(c)
    a,b=np.nanpercentile(c,[0.2,99.8]); X[:,k]=np.clip(c,a,b)
NET=np.where(ok,(1+np.nan_to_num(g))*(1-0.0114)-1,-0.30)
class S:
    def __init__(s,idx):
        s.mid=mint_id[idx]; s.ent=ent[idx]; s.xit=xit[idx]; s.ok=ok[idx]
        s.net=NET[idx]; s.X=X[idx]
        u,inv=np.unique(s.mid,return_inverse=True); s.inv=inv; s.nm=len(u); s.n=len(idx)
A=S(np.nonzero(hs==1)[0]); B=S(np.nonzero(hs==2)[0])
def greedy(s,mask):
    idx=np.nonzero(mask)[0]
    if idx.size==0: return idx
    sel=[]; cur=-1; last=-1e18
    for k in idx:
        m=s.mid[k]
        if m!=cur: cur=m; last=-1e18
        if s.ent[k]>=last: sel.append(k); last=s.xit[k]
    return np.array(sel,np.int64)
def mm_(s,sel):
    inv=s.inv[sel]; r=s.net[sel]
    cnt=np.bincount(inv,minlength=s.nm).astype(float)
    tot=np.bincount(inv,weights=r,minlength=s.nm); live=cnt>0
    return tot[live]/cnt[live]
E=[np.unique(np.percentile(A.X[:,k],[20,40,60,80])) for k in range(NF)]
BA=[np.searchsorted(E[k],A.X[:,k],side='right') for k in range(NF)]
BB=[np.searchsorted(E[k],B.X[:,k],side='right') for k in range(NF)]

# Region map: mean validate return by 1-way quintile, showing the whole surface's shape
p("=== 1-WAY REGION MAP ON VALIDATE (h2), net a30, mint-equal ===")
p("feature          q0      q1      q2      q3      q4   (blank = no support)")
for k in range(NF):
    row=[]
    for q in range(5):
        sel=greedy(B,BB[k]==q)
        if sel.size<60: row.append("   .   "); continue
        mm=mm_(B,sel)
        row.append("%+.3f " % mm.mean() if len(mm)>=20 else "   .   ")
    p("%-16s %s" % (FN[k], " ".join(row)))

# The least-bad ROBUST cells: require high resolution, tight bootstrap, survive drop-top-3
p("\n=== LEAST-BAD ROBUST CELLS (validate) ===")
p("filter: n>=150, k>=30, resolution>=0.95, and mean survives dropping the 3 best mints")
rows=[]
for ka,kb in itertools.combinations(range(NF),2):
    for qa in range(BB[ka].max()+1):
        ma=BB[ka]==qa
        if not ma.any(): continue
        for qb in range(BB[kb].max()+1):
            mask=ma&(BB[kb]==qb)
            if mask.sum()<150: continue
            sel=greedy(B,mask)
            if sel.size<150: continue
            mm=mm_(B,sel)
            if len(mm)<30: continue
            res=float(B.ok[sel].mean())
            if res<0.95: continue
            o=np.argsort(mm)
            d3=float(np.delete(mm,o[-3:]).mean())
            rows.append((float(mm.mean()),d3,float(np.median(mm)),int(sel.size),len(mm),res,
                         FN[ka],qa,FN[kb],qb))
rows.sort(key=lambda z:-z[1])
p("cells meeting the filter: %d" % len(rows))
for r in rows[:20]:
    p("  mean=%+.4f drop3=%+.4f med=%+.4f n=%d k=%d res=%.3f | %s q%d & %s q%d"
      % (r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9]))
p("  best drop-3-robust validate mean over the whole grid: %+.4f" % (rows[0][1] if rows else float('nan')))

# how many cells anywhere reach >0 after dropping the 3 best mints, on validate
pos=[r for r in rows if r[1]>0]
p("\ncells with drop-top-3 validate mean > 0 : %d of %d" % (len(pos),len(rows)))
for r in pos: p("   %s" % str(r))
OUT.close()
