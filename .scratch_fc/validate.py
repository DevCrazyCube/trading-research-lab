"""Re-test every TRAIN-positive combo on VALIDATE (h==2). Nothing from h==0 is touched."""
import pickle, statistics as st, random, time, os
TAG=os.environ.get('TAG','')
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
R=pickle.load(open(S+'res%s.pkl'%TAG,'rb')); FEAT=pickle.load(open(S+'feat.pkl','rb'))
T=pickle.load(open(S+'train_rows%s.pkl'%TAG,'rb'))
RES=R['RES']; STRUCTS=R['STRUCTS']; BFS=R['BFS']; MINTS=R['MINTS']
HORIZ=R['HORIZ']; TPS=R['TPS']; SLS=R['SLS']; TRS=R['TRS']
rows=T['rows']; MFN=T['MFN']; IDT=T['IDT']; IDV=T['IDV']; combos=T['combos']
OUT=open(S+'validate%s.txt'%TAG,'w')
def P(*a): print(*a,file=OUT); OUT.flush()
TRAIN=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==1]
VALID=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==2]
CRE=[FEAT[m]['cre'] for m in MINTS]
def sname(s):
    hh,tpi,sli,tri,pos=s
    return 'H%d|TP%s|SL%s|TR%s|P%s'%(HORIZ[hh],('%.2f'%TPS[tpi]) if tpi is not None else '-',
        ('%.2f'%SLS[sli]) if sli is not None else '-',('%.2f'%TRS[tri]) if tri is not None else '-',pos)
def stats(key,idxs,toll=0.0114,charge=-0.30):
    n_res,s_g,n_do=RES[key]
    per={}; tot=0; res=0
    for i in idxs:
        nr=n_res[i]; nd=n_do[i]
        if nr+nd==0: continue
        tn=(1-toll)*(nr+s_g[i])-nr+nd*((1+charge)*(1-toll)-1)
        per[i]=tn/(nr+nd); tot+=nr+nd; res+=nr
    if not per: return None
    v=list(per.values())
    return dict(mean=sum(v)/len(v),median=st.median(v),k=len(v),n=tot,
                res=res/tot if tot else 0.0,per=per)

random.seed(12345)
def boot_lo(per, reps=1000, q=0.05):
    byc=defaultdict(list)
    for i,v in per.items(): byc[CRE[i]].append(v)
    cs=list(byc); nc=len(cs)
    if nc<6: return None,nc
    out=[]
    for _ in range(reps):
        acc=[]
        for _ in range(nc):
            acc.extend(byc[cs[random.randrange(nc)]])
        out.append(sum(acc)/len(acc))
    out.sort()
    return out[int(q*reps)], nc

P('train-positive rows to re-test on validate:',len(rows))
surv=[]
for (si,bi,mi,trm,trmed,trk,trn,trres,ctrl) in rows:
    key=(si,bi); idv=IDV[mi]
    if len(idv)<12: continue
    a=stats(key,idv)
    if a is None or a['k']<12 or a['n']<30: continue
    c=stats(key,VALID)
    if c is None: continue
    if a['mean']<=0: continue
    if a['mean']<=c['mean']: continue
    lo,nc=boot_lo(a['per'])
    a2=stats(key,idv,toll=0.025)
    a3=stats(key,idv,toll=0.0114,charge=-1.00)
    a5=stats(key,idv,toll=0.0114,charge=-0.50)
    surv.append(dict(si=si,bi=bi,mi=mi,trm=trm,trmed=trmed,trk=trk,trn=trn,
                     vm=a['mean'],vmed=a['median'],vk=a['k'],vn=a['n'],vres=a['res'],
                     ctrl=c['mean'],ctrlmed=c['median'],edge=a['mean']-c['mean'],
                     lo=lo,nc=nc,vm_toll25=a2['mean'],vm_d100=a3['mean'],vm_d50=a5['mean']))
P('validate-positive & beats validate control:',len(surv))
surv.sort(key=lambda d:-(d['lo'] if d['lo'] is not None else -9))
P('%-20s %-12s %-26s %8s %8s %8s %8s %4s %5s %6s %8s %8s %8s'%(
  'mintfilter','barfilter','structure','trmean','vmean','vmed','ctrl','vk','vn','clus','bootLO','toll2.5','drop100'))
for d in surv[:80]:
    P('%-20s %-12s %-26s %+8.4f %+8.4f %+8.4f %+8.4f %4d %5d %6s %8s %+8.4f %+8.4f'%(
      MFN[d['mi']],BFS[d['bi']],sname(STRUCTS[d['si']]),d['trm'],d['vm'],d['vmed'],d['ctrl'],
      d['vk'],d['vn'],d['nc'],('%+.4f'%d['lo']) if d['lo'] is not None else 'NA',
      d['vm_toll25'],d['vm_d100']))
strict=[d for d in surv if d['lo'] is not None and d['lo']>0 and d['vm_toll25']>0 and d['vm_d100']>0 and d['vmed']>d['ctrlmed']]
P('STRICT survivors (bootLO>0, toll2.5>0, drop-100>0, median beats control median):',len(strict))
for d in strict:
    P('  ',MFN[d['mi']],BFS[d['bi']],sname(STRUCTS[d['si']]),d)
pickle.dump(dict(surv=surv,strict=strict),open(S+'surv%s.pkl'%TAG,'wb'))
OUT.close()
