import sys,json,math,collections,time
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
o=open('/home/anont/meme/.ff3/drive_out.txt','w')
t0=time.time()
TRAIN=(h==1); VAL=(h==2)
o.write("rows %d train %d val %d curves %d\n"%(NR,TRAIN.sum(),VAL.sum(),NC))
o.write("structs %d\n"%len(STRUCTS))
TOLL=0.025   # honest on-chain all-in; 1.14% reported for finalists
MI=0         # mode S headline
MINN=200; MINK=40

# ---- build entry conditions on flow features, thresholds from TRAIN
conds=[]   # (name, boolmask over all rows)
PS=[10,20,30,40,50,60,70,80,90]
BANDS=[(10,50),(50,90),(30,70),(70,95),(80,99),(1,20),(0,10),(90,100)]
for fi in range(NFLOW):
    col=FEAT[:,fi]
    tr=col[TRAIN]
    q={p:float(np.percentile(tr,p)) for p in set(PS+[0,1,95,99,100])}
    nm=names[fi]
    for p in PS:
        v=q[p]
        m=col>=v
        if m[TRAIN].sum()>0 and m[TRAIN].sum()<TRAIN.sum(): conds.append(('%s>=q%d(%.6g)'%(nm,p,v),m))
        m2=col<=v
        if m2[TRAIN].sum()>0 and m2[TRAIN].sum()<TRAIN.sum(): conds.append(('%s<=q%d(%.6g)'%(nm,p,v),m2))
    for a,b in BANDS:
        va,vb=q[a],q[b]
        if not (vb>va): continue
        m=(col>=va)&(col<=vb)
        if m[TRAIN].sum()>0: conds.append(('%s in q%d..q%d[%.6g,%.6g]'%(nm,a,b,va,vb),m))
o.write("flow conditions %d\n"%len(conds))

# ---- meta buckets
metaconds=[]
for j,nm in enumerate(names[NFLOW:]):
    fi=NFLOW+j
    col=FEAT[:,fi]
    tr=col[TRAIN]
    u=np.unique(tr)
    if len(u)<=2:
        for v in u:
            m=col==v
            if 0<m[TRAIN].sum()<TRAIN.sum(): metaconds.append(('%s==%g'%(nm,v),m))
        continue
    q33,q66=float(np.percentile(tr,33)),float(np.percentile(tr,66))
    if q33<q66:
        metaconds.append(('%s<=q33(%.6g)'%(nm,q33),col<=q33))
        metaconds.append(('%s in q33..q66'%nm,(col>q33)&(col<=q66)))
        metaconds.append(('%s>q66(%.6g)'%(nm,q66),col>q66))
    q50=float(np.percentile(tr,50))
    metaconds.append(('%s<=q50(%.6g)'%(nm,q50),col<=q50))
    metaconds.append(('%s>q50(%.6g)'%(nm,q50),col>q50))
o.write("meta conditions %d\n"%len(metaconds))

nswept=0
# ---- controls: unconditional, per horizon, hold
CTRL={}
for hi,H in enumerate(HORS):
    allm=np.ones(NR,dtype=bool)
    for split,sm in (('train',TRAIN),('val',VAL)):
        r=evaluate(MI,hi,allm&sm,('hold',None,None),TOLL)
        CTRL[(hi,'hold',None,None,split)]=(r['mean'],r['median'],r['n'],r['k'])
        o.write("CONTROL %s H=%d hold: mean %.4f med %.4f n %d k %d gradfrac %.3f\n"%(split,H,r['mean'],r['median'],r['n'],r['k'],r['gradfrac']))
        nswept+=1
o.flush()

# ---- STAGE 1a: flow condition x horizon, hold
res1=[]
for ci,(cn,cm) in enumerate(conds):
    for hi,H in enumerate(HORS):
        m=cm&TRAIN
        r=evaluate(MI,hi,m,('hold',None,None),TOLL)
        nswept+=1
        if r is None or r['n']<MINN or r['k']<MINK: continue
        base=CTRL[(hi,'hold',None,None,'train')][0]
        res1.append((r['mean'],r['median'],r['n'],r['k'],cn,hi,r['mean']-base))
res1.sort(key=lambda x:-x[0])
o.write("\n=== STAGE1a top 40 (train, hold, toll2.5%%) ===\n")
for x in res1[:40]:
    o.write("mean %.4f med %.4f n %d k %d H=%d edge %.4f  %s\n"%(x[0],x[1],x[2],x[3],HORS[x[5]],x[6],x[4]))
o.write("stage1a evaluated %d ; qualifying %d ; positive-mean %d\n"%(nswept,len(res1),sum(1 for x in res1 if x[0]>0)))
o.flush()
np.save('/home/anont/meme/.ff3/nswept1.npy',np.array([nswept]))
pickle_out=open('/home/anont/meme/.ff3/res1.json','w')
json.dump([[float(a),float(b),int(c),int(d),e,int(f),float(g)] for a,b,c,d,e,f,g in res1],pickle_out)
pickle_out.close()
o.write("elapsed %.1f s\n"%(time.time()-t0))
o.close()
