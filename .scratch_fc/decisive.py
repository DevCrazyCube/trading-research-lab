"""Is the np==0 survivor a DEPLOYER effect or a left-censoring / calendar artifact?
Stratify by creation time inside the 24h observation window and re-test."""
import pickle, statistics as st, random
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
R=pickle.load(open(S+'res_c3.pkl','rb')); FEAT=pickle.load(open(S+'feat.pkl','rb'))
D=pickle.load(open(S+'data1.pkl','rb'))
RES=R['RES']; STRUCTS=R['STRUCTS']; BFS=R['BFS']; MINTS=R['MINTS']; HORIZ=R['HORIZ']
TPS=R['TPS']; SLS=R['SLS']; TRS=R['TRS']
OUT=open(S+'decisive.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
CRE=[FEAT[m]['cre'] for m in MINTS]
T0=min(FEAT[m]['bt'] for m in MINTS); T1=max(FEAT[m]['bt'] for m in MINTS)
def third(m):
    x=(FEAT[m]['bt']-T0)/(T1-T0+1e-9)
    return 0 if x<1/3 else (1 if x<2/3 else 2)
TH=[third(m) for m in MINTS]
VAL=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==2]
TRN=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==1]
ALL=list(range(len(MINTS)))
NP0=[FEAT[m]['n_prior']==0 for m in MINTS]
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
        per[i]=((1-toll)*(nr+s_g[i])-nr+nd*((1+charge)*(1-toll)-1))/(nr+nd); tot+=nr+nd; res+=nr
    if not per: return None
    v=list(per.values())
    return dict(mean=sum(v)/len(v),median=st.median(v),k=len(v),n=tot,per=per,res=res/tot if tot else 0)
random.seed(7)
def blo(per,reps=800):
    byc=defaultdict(list)
    for i,v in per.items(): byc[CRE[i]].append(v)
    cs=list(byc); nc=len(cs)
    if nc<6: return None,nc
    o=[]
    for _ in range(reps):
        acc=[]
        for _ in range(nc): acc.extend(byc[cs[random.randrange(nc)]])
        o.append(sum(acc)/len(acc))
    o.sort(); return o[int(0.05*reps)],nc

# best survivors from the capped validate
CAND=[(267,1),(266,1),(201,1),(318,1),(267,2),(320,1),(333,1)]
P('T0..T1 hours',round((T1-T0)/3600,2))
P('creation-time third x np==0 counts:')
cnt=defaultdict(int)
for i in ALL: cnt[(TH[i],NP0[i])]+=1
for k in sorted(cnt): P('   third=%d np0=%s  n=%d'%(k[0],k[1],cnt[k]))

for (si,bi) in CAND:
    P('')
    P('STRUCTURE',sname(STRUCTS[si]),'BARFILTER',BFS[bi])
    groups=[
      ('np==0            (val)',      [i for i in VAL if NP0[i]]),
      ('np>=1            (val)',      [i for i in VAL if not NP0[i]]),
      ('ALL              (val)',      VAL),
      ('third0 ALL       (val)',      [i for i in VAL if TH[i]==0]),
      ('third1+2 ALL     (val)',      [i for i in VAL if TH[i]>0]),
      ('third0 np==0     (val)',      [i for i in VAL if TH[i]==0 and NP0[i]]),
      ('third0 np>=1     (val)',      [i for i in VAL if TH[i]==0 and not NP0[i]]),
      ('third1+2 np==0   (val)',      [i for i in VAL if TH[i]>0 and NP0[i]]),
      ('third1+2 np>=1   (val)',      [i for i in VAL if TH[i]>0 and not NP0[i]]),
      ('third1+2 np==0   (all h12)',  [i for i in ALL if TH[i]>0 and NP0[i]]),
      ('third1+2 np>=1   (all h12)',  [i for i in ALL if TH[i]>0 and not NP0[i]]),
      ('third0 ALL       (all h12)',  [i for i in ALL if TH[i]==0]),
      ('third1+2 ALL     (all h12)',  [i for i in ALL if TH[i]>0]),
    ]
    for lab,idx in groups:
        if len(idx)<6: P('   %-26s k<6 skip'%lab); continue
        a=stats((si,bi),idx)
        if a is None: P('   %-26s no data'%lab); continue
        lo,nc=blo(a['per'])
        P('   %-26s mean=%+.4f med=%+.4f k=%3d n=%4d clus=%3s bootLO=%s'%(
            lab,a['mean'],a['median'],a['k'],a['n'],nc,('%+.4f'%lo) if lo is not None else 'NA'))
OUT.close()
