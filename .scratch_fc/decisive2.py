"""(1) does np==0 survive at OLDER entry ages (executable, post-graduation)?
   (2) tail decomposition  (3) cap sensitivity"""
import pickle, statistics as st, random, os
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
FEAT=pickle.load(open(S+'feat.pkl','rb'))
OUT=open(S+'decisive2.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
random.seed(11)
for tag in ['_c1','_c3','_c10','']:
    fp=S+'res%s.pkl'%tag
    if not os.path.exists(fp): P('missing',fp); continue
    R=pickle.load(open(fp,'rb'))
    RES=R['RES']; STRUCTS=R['STRUCTS']; BFS=R['BFS']; MINTS=R['MINTS']
    HORIZ=R['HORIZ']; TPS=R['TPS']; SLS=R['SLS']; TRS=R['TRS']
    CRE=[FEAT[m]['cre'] for m in MINTS]
    NP0=[FEAT[m]['n_prior']==0 for m in MINTS]
    VAL=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==2]
    TRN=[i for i,m in enumerate(MINTS) if FEAT[m]['h']==1]
    ALLI=list(range(len(MINTS)))
    def sname(s):
        hh,tpi,sli,tri,pos=s
        return 'H%d|TP%s|SL%s|TR%s|P%s'%(HORIZ[hh],('%.2f'%TPS[tpi]) if tpi is not None else '-',
          ('%.2f'%SLS[sli]) if sli is not None else '-',('%.2f'%TRS[tri]) if tri is not None else '-',pos)
    def stats(key,idxs,toll=0.0114,charge=-0.30):
        n_res,s_g,n_do=RES[key]; per={}; tot=0; res=0
        for i in idxs:
            nr=n_res[i]; nd=n_do[i]
            if nr+nd==0: continue
            per[i]=((1-toll)*(nr+s_g[i])-nr+nd*((1+charge)*(1-toll)-1))/(nr+nd); tot+=nr+nd; res+=nr
        if not per: return None
        v=list(per.values())
        return dict(mean=sum(v)/len(v),median=st.median(v),k=len(v),n=tot,per=per,res=res/tot if tot else 0)
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
    # locate the reference structure H120|TR0.30|POS C
    si_ref=[i for i,s in enumerate(STRUCTS) if HORIZ[s[0]]==120 and s[1] is None and s[2] is None and s[3]==0 and s[4]=='C'][0]
    P('')
    P('############ CAP TAG %r  ref structure %s'%(tag or 'uncapped', sname(STRUCTS[si_ref])))
    P('--- np==0 vs np>=1 across ENTRY-AGE bands (validate h==2, then all h12) ---')
    for bname in BFS:
        bi=BFS.index(bname)
        r=[]
        for lab,idx in [('np0',[i for i in VAL if NP0[i]]),('np1+',[i for i in VAL if not NP0[i]]),
                        ('np0_all',[i for i in ALLI if NP0[i]]),('np1+_all',[i for i in ALLI if not NP0[i]])]:
            a=stats((si_ref,bi),idx)
            r.append((lab,a))
        line='  %-12s'%bname
        for lab,a in r:
            if a is None: line+=' %s: n/a'%lab; continue
            line+=' %s mean=%+.4f med=%+.4f k=%d |'%(lab,a['mean'],a['median'],a['k'])
        P(line)
    # tail decomposition at age<20
    bi=BFS.index('age<20')
    a=stats((si_ref,bi),[i for i in VAL if NP0[i]])
    v=sorted(a['per'].values(),reverse=True)
    P('--- tail decomposition, np==0 age<20 VALIDATE (k=%d) ---'%len(v))
    P('   top5 per-mint means: %s'%['%+.2f'%x for x in v[:5]])
    for drop in [0,1,2,3,5,8]:
        w=v[drop:]
        P('   drop top %d -> mean=%+.4f  median=%+.4f  k=%d'%(drop,sum(w)/len(w),st.median(w),len(w)))
    P('   frac of mints with positive mean: %.3f'%(sum(1 for x in v if x>0)/len(v)))
    lo,nc=blo(a['per']); P('   bootLO(creator clusters)=%s nc=%s'%(lo,nc))
OUT.close()
