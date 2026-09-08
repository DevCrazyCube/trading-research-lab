import sys,json,math,collections,time
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
rng=np.random.default_rng(12345)
o=open('/home/anont/meme/.ff3/drive_out.txt','w',buffering=1)
t0=time.time()
TRAIN=(h==1); VAL=(h==2)
o.write("rows %d train %d val %d curves %d structs %d\n"%(NR,TRAIN.sum(),VAL.sum(),NC,len(STRUCTS)))
TOLL=0.025
MI=0
MINN=200; MINK=40
NSW=[0]

def ev(hi,mask,struct,split,toll=TOLL):
    NSW[0]+=1
    return evaluate(MI,hi,mask&(TRAIN if split=='train' else VAL),struct,toll)

PS=[10,20,30,40,50,60,70,80,90]
BANDS=[(10,50),(50,90),(30,70),(70,95),(80,99),(1,20),(0,10),(90,100)]
conds=[]
for fi in range(NFLOW):
    col=FEAT[:,fi]; tr=col[TRAIN]
    q={p:float(np.percentile(tr,p)) for p in set(PS+[0,1,95,99,100])}
    nm=str(names[fi])
    for p in PS:
        v=q[p]
        for op,m in (('>=',col>=v),('<=',col<=v)):
            s=int(m[TRAIN].sum())
            if 0<s<int(TRAIN.sum()): conds.append(('%s%sq%d(%.6g)'%(nm,op,p,v),m))
    for a,b in BANDS:
        va,vb=q[a],q[b]
        if not (vb>va): continue
        m=(col>=va)&(col<=vb)
        if int(m[TRAIN].sum())>0: conds.append(('%s@q%d-q%d[%.6g,%.6g]'%(nm,a,b,va,vb),m))
o.write("flow conditions %d\n"%len(conds))
metaconds=[]
for j in range(len(names)-NFLOW):
    fi=NFLOW+j; nm=str(names[fi]); col=FEAT[:,fi]; tr=col[TRAIN]
    u=np.unique(tr)
    if len(u)<=3:
        for v in u:
            m=col==v
            if 0<int(m[TRAIN].sum())<int(TRAIN.sum()): metaconds.append(('%s==%g'%(nm,v),m))
        continue
    q33,q66,q50,q80,q20=[float(np.percentile(tr,p)) for p in (33,66,50,80,20)]
    metaconds.append(('%s<=q33'%nm,col<=q33)); metaconds.append(('%s@q33-q66'%nm,(col>q33)&(col<=q66)))
    metaconds.append(('%s>q66'%nm,col>q66)); metaconds.append(('%s<=q50'%nm,col<=q50))
    metaconds.append(('%s>q50'%nm,col>q50)); metaconds.append(('%s>q80'%nm,col>q80)); metaconds.append(('%s<=q20'%nm,col<=q20))
o.write("meta conditions %d\n"%len(metaconds))

CTRL={}
for hi,H in enumerate(HORS):
    allm=np.ones(NR,dtype=bool)
    for split in ('train','val'):
        r=ev(hi,allm,('hold',None,None),split)
        CTRL[(hi,0,split)]=r
        o.write("CONTROL %s H=%d hold n=%d k=%d mean %.4f med %.4f grad %.3f\n"%(split,H,r['n'],r['k'],r['mean'],r['median'],r['gradfrac']))

# STAGE 1a
res1=[]
for cn,cm in conds:
    for hi in range(len(HORS)):
        r=ev(hi,cm,('hold',None,None),'train')
        if r is None or r['n']<MINN or r['k']<MINK: continue
        res1.append(dict(mean=r['mean'],med=r['median'],n=r['n'],k=r['k'],hi=hi,cn=cn,
                         edge=r['mean']-CTRL[(hi,0,'train')]['mean']))
res1.sort(key=lambda d:-d['mean'])
o.write("\n=== STAGE1a: %d qualifying, %d with mean>0. top 40 ===\n"%(len(res1),sum(1 for d in res1 if d['mean']>0)))
for d in res1[:40]:
    o.write("  mean %+.4f med %+.4f n %5d k %4d H=%4d edge %+.4f  %s\n"%(d['mean'],d['med'],d['n'],d['k'],HORS[d['hi']],d['edge'],d['cn']))
o.write("  --- bottom 10 ---\n")
for d in res1[-10:]:
    o.write("  mean %+.4f n %5d k %4d H=%4d  %s\n"%(d['mean'],d['n'],d['k'],HORS[d['hi']],d['cn']))
o.write("nswept %d elapsed %.0f\n"%(NSW[0],time.time()-t0))

cmap=dict(conds)
# STAGE 1b: top flow conds x meta
top1=[]
seen=set()
for d in res1:
    key=d['cn']
    if key in seen: continue
    seen.add(key); top1.append(d)
    if len(top1)>=150: break
res2=[]
for d in top1:
    cm=cmap[d['cn']]
    for mn,mm in metaconds:
        m=cm&mm
        for hi in range(len(HORS)):
            r=ev(hi,m,('hold',None,None),'train')
            if r is None or r['n']<MINN or r['k']<MINK: continue
            res2.append(dict(mean=r['mean'],med=r['median'],n=r['n'],k=r['k'],hi=hi,cn=d['cn'],mn=mn,
                             edge=r['mean']-CTRL[(hi,0,'train')]['mean']))
res2.sort(key=lambda d:-d['mean'])
o.write("\n=== STAGE1b flow x meta: %d qualifying, %d mean>0. top 40 ===\n"%(len(res2),sum(1 for d in res2 if d['mean']>0)))
for d in res2[:40]:
    o.write("  mean %+.4f med %+.4f n %5d k %4d H=%4d edge %+.4f  %s  &  %s\n"%(d['mean'],d['med'],d['n'],d['k'],HORS[d['hi']],d['edge'],d['cn'],d['mn']))
o.write("nswept %d elapsed %.0f\n"%(NSW[0],time.time()-t0))

# STAGE 1c: flow x flow among top 60 distinct conds
top60=[d['cn'] for d in top1[:60]]
res3=[]
for i in range(len(top60)):
    for j in range(i+1,len(top60)):
        a,b=top60[i],top60[j]
        if a.split('>')[0].split('<')[0].split('@')[0]==b.split('>')[0].split('<')[0].split('@')[0]: continue
        m=cmap[a]&cmap[b]
        for hi in range(len(HORS)):
            r=ev(hi,m,('hold',None,None),'train')
            if r is None or r['n']<MINN or r['k']<MINK: continue
            res3.append(dict(mean=r['mean'],med=r['median'],n=r['n'],k=r['k'],hi=hi,cn=a,mn=b,
                             edge=r['mean']-CTRL[(hi,0,'train')]['mean']))
res3.sort(key=lambda d:-d['mean'])
o.write("\n=== STAGE1c flow x flow: %d qualifying, %d mean>0. top 40 ===\n"%(len(res3),sum(1 for d in res3 if d['mean']>0)))
for d in res3[:40]:
    o.write("  mean %+.4f med %+.4f n %5d k %4d H=%4d edge %+.4f  %s  &  %s\n"%(d['mean'],d['med'],d['n'],d['k'],HORS[d['hi']],d['edge'],d['cn'],d['mn']))
o.write("nswept %d elapsed %.0f\n"%(NSW[0],time.time()-t0))

allres=[]
for d in res1: allres.append((d['mean'],d['cn'],None,d['hi']))
for d in res2: allres.append((d['mean'],d['cn'],d['mn'],d['hi']))
for d in res3: allres.append((d['mean'],d['cn'],d['mn'],d['hi']))
allres.sort(key=lambda x:-x[0])
json.dump([[float(a),b,c,int(dd)] for a,b,c,dd in allres[:400]],open('/home/anont/meme/.ff3/allres.json','w'))

# STAGE 2: structures on top 60 entry sets
MC=dict(metaconds)
def getmask(cn,mn):
    m=cmap[cn]
    if mn is not None: m=m&(cmap[mn] if mn in cmap else MC[mn])
    return m
top=[]
seenk=set()
for a,b,c,hi in allres:
    k=(b,c)
    if k in seenk: continue
    seenk.add(k); top.append((b,c))
    if len(top)>=60: break
res4=[]
for b,c in top:
    m=getmask(b,c)
    for hi in range(len(HORS)):
        for st in STRUCTS:
            r=ev(hi,m,st,'train')
            if r is None or r['n']<MINN or r['k']<MINK: continue
            res4.append(dict(mean=r['mean'],med=r['median'],n=r['n'],k=r['k'],hi=hi,cn=b,mn=c,st=st))
res4.sort(key=lambda d:-d['mean'])
o.write("\n=== STAGE2 structures: %d qualifying, %d mean>0. top 50 ===\n"%(len(res4),sum(1 for d in res4 if d['mean']>0)))
for d in res4[:50]:
    o.write("  mean %+.4f med %+.4f n %5d k %4d H=%4d %s  %s | %s\n"%(d['mean'],d['med'],d['n'],d['k'],HORS[d['hi']],d['st'],d['cn'],d['mn']))
o.write("nswept %d elapsed %.0f\n"%(NSW[0],time.time()-t0))
json.dump([[d['mean'],d['med'],d['n'],d['k'],d['hi'],d['cn'],d['mn'],[d['st'][0],d['st'][1],d['st'][2]]] for d in res4[:400]],open('/home/anont/meme/.ff3/res4.json','w'))
o.write("TOTAL COMBOS SWEPT %d\n"%NSW[0])
o.close()
