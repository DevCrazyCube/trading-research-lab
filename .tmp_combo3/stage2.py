import sys, time, math, json, pickle, itertools
sys.path.insert(0,'/home/anont/meme/.tmp_combo3')
import numpy as np
from lib import *

t0=time.time(); O=open(D+'out_stage2.txt','w')
def p(*a): print(*a,file=O); O.flush()
st=S(); TR=mints_of(1)
s1=pickle.load(open(D+'stage1.pkl','rb'))
EDGES=s1['EDGES']; one=s1['one']; BASE=s1['BASE']; CANON=s1['CANON']; combos=s1['combos']
simc={spec:sim_all(TR,spec,drop=-0.30) for spec in CANON}
BINS={f:bin_of(TR,f,EDGES[f]) for f in EDGES}
rank=sorted(EDGES.keys(),key=lambda f:-one.get(f,-9))
TOP=rank[:9]
p('feature pool (1-way ranked): %s'%[(f,round(one.get(f,0),2)) for f in rank])
p('top9 into 2-way: %s'%TOP)

MINK=25; MINN=40
def cid_n(fs,mints):
    arrs=[BINS[f] for f in fs]
    out={}; nc=1
    for _,nb in arrs: nc*=nb
    for m in mints:
        v=None; bad=None
        for b,nb in arrs:
            a=b[m]
            v=a.copy() if v is None else v*nb+a
            bad=(a<0) if bad is None else (bad|(a<0))
        out[m]=np.where(bad,-1,v)
    return out,nc

p('\n=== 2-WAY (train) ===')
two=[]; pairfeat={}
for f1,f2 in itertools.combinations(TOP,2):
    cid,nc=cid_n((f1,f2),TR)
    for spec in CANON:
        r=eval_cells(TR,cid,simc[spec]); base=BASE[('tr',spec)]['w']
        for c,v in r.items():
            s=stats(v[0]); combos+=1
            if s is None or s[4]<MINK or v[2]<MINN: continue
            t=tstat(s,base)
            two.append((f1,f2,int(c),spec,s[0],s[1],s[4],v[2],base,t))
            if t>=1.5:
                pairfeat[f1]=pairfeat.get(f1,0)+1; pairfeat[f2]=pairfeat.get(f2,0)+1
two.sort(key=lambda x:-x[9])
p('2-way cells passing size filter: %d   combos so far %d   t=%.1f'%(len(two),combos,time.time()-t0))
for r in two[:15]:
    p('  %-9s x %-9s c%-4d %-27s wmean=%+.4f med=%+.4f k=%3d n=%4d base=%+.4f t=%5.2f'%(r[0],r[1],r[2],str(r[3]),r[4],r[5],r[6],r[7],r[8],r[9]))
p('features in t>=1.5 2-way cells: %s'%sorted(pairfeat.items(),key=lambda x:-x[1]))
FS=[f for f,_ in sorted(pairfeat.items(),key=lambda x:-x[1])][:8]
if len(FS)<5: FS=TOP[:8]
p('3-way feature set (%d): %s'%(len(FS),FS))

p('\n=== 3-WAY (train) ===')
three=[]; ntrip=0
for f1,f2,f3 in itertools.combinations(FS,3):
    ntrip+=1
    cid,nc=cid_n((f1,f2,f3),TR)
    for spec in CANON:
        r=eval_cells(TR,cid,simc[spec]); base=BASE[('tr',spec)]['w']
        for c,v in r.items():
            s=stats(v[0]); combos+=1
            if s is None or s[4]<MINK or v[2]<MINN: continue
            three.append(dict(f=(f1,f2,f3),cell=int(c),spec=spec,w=s[0],med=s[1],k=s[4],se=s[3],
                              n=v[2],base=base,t=tstat(s,base),tz=(s[0]/s[3] if s[3]>0 else 0.0),
                              res=v[3]/max(v[2],1)))
    if ntrip%8==0: p('  triples=%d combos=%d kept=%d t=%.1f'%(ntrip,combos,len(three),time.time()-t0))
three.sort(key=lambda x:-x['t'])
p('triples=%d  3-way cells passing size filter=%d  TOTAL combos=%d'%(ntrip,len(three),combos))
p('--- top 30 3-way (train) ---')
for r in three[:30]:
    p('  %-30s c%-6d %-27s wmean=%+.4f med=%+.4f k=%3d n=%4d base=%+.4f t=%5.2f res=%.2f'%(
        '/'.join(r['f']),r['cell'],str(r['spec']),r['w'],r['med'],r['k'],r['n'],r['base'],r['t'],r['res']))
pv=[pval_t(r['t']) for r in three]
p('BH q=0.10 survivors among %d 3-way train cells: %d'%(len(pv),len(bh(pv,0.10))))
p('cells with t>0: %d ; t>2: %d ; t>3: %d'%(sum(1 for r in three if r['t']>0),
   sum(1 for r in three if r['t']>2),sum(1 for r in three if r['t']>3)))
p('cells with wmean>0 (absolute profit): %d'%sum(1 for r in three if r['w']>0))
money=[r for r in three if r['w']>0]
money.sort(key=lambda x:-x['tz'])
p('\n--- top 25 PROFITABLE (train wmean>0) 3-way cells, ranked by t vs ZERO ---')
for r in money[:25]:
    p('  %-30s c%-6d %-27s wmean=%+.4f med=%+.4f k=%3d n=%4d ctrl=%+.4f tz=%5.2f res=%.2f'%(
        '/'.join(r['f']),r['cell'],str(r['spec']),r['w'],r['med'],r['k'],r['n'],r['base'],r['tz'],r['res']))
p('profitable-on-train cells: %d ; of those tz>2: %d ; tz>3: %d'%(
   len(money),sum(1 for r in money if r['tz']>2),sum(1 for r in money if r['tz']>3)))
seenA={}
for r in money:
    key=(r['f'],r['cell'])
    if key not in seenA or r['tz']>seenA[key]['tz']: seenA[key]=r
topA=sorted(seenA.values(),key=lambda x:-x['tz'])[:40]
seenB={}
for r in three:
    key=(r['f'],r['cell'])
    if key not in seenB or r['t']>seenB[key]['t']: seenB[key]=r
topB=sorted(seenB.values(),key=lambda x:-x['t'])[:10]
kk=set(); top=[]
for r in topA+topB:
    key=(r['f'],r['cell'])
    if key in kk: continue
    kk.add(key); top.append(r)
p('unique (triple,cell) for stage3: %d  (%d money-ranked + %d edge-ranked)'%(len(top),len(topA),len(topB)))
pickle.dump(dict(top=top,FS=FS,EDGES=EDGES,combos=combos,ntrip=ntrip,two=two[:200],three_n=len(three),
                 money=money,allthree=three),open(D+'stage2.pkl','wb'))
p('done t=%.1f'%(time.time()-t0)); O.close()
