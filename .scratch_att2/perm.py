import sys, json, statistics as st, collections, math, random
sys.path.insert(0,'/home/anont/meme/.scratch_att2')
from engine import *
OUT=open('/home/anont/meme/.scratch_att2/perm_out.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()

ev,g,FEND=load()
EVS=build(ev,g,FEND,False); CTL=build(ev,g,FEND,True)
TOLL=0.0114; DC=-0.30

# cache: for each structure, per-series (entry_idx, ret, legs, eligible)
def cache(series_list):
    C={}
    for S in S_GRID:
        eidx={id(s):entry_index(s,S) for s in series_list}
        for H in H_GRID:
            for ekind,ep in EXITS:
                for pkind,pp in POS:
                    params=dict(ep); params.update(pp)
                    lst=[]
                    for s in series_list:
                        ei=eidx[id(s)]
                        if ei is None: lst.append((s,None,None,None,None)); continue
                        elig = s.avail >= s.t[ei]+H
                        o=sim(s,ei,H,ekind,pkind,params)
                        if o is None or o[0]=='DROP': lst.append((s,ei,None,None,elig))
                        else: lst.append((s,ei,o[0],o[1],elig))
                    C[(S,H,ekind,pkind)]=lst
    return C
P('building caches...')
CE=cache(EVS); CC=cache(CTL)
P('cache size',len(CE))

CONDMASK={}
def cm(s,ei,c):
    k=(id(s),ei,c)
    v=CONDMASK.get(k)
    if v is None:
        v=cond_mask(s,ei,c); CONDMASK[k]=v
    return v

def agg(lst,c,half_of):
    vals=[]
    for (s,ei,r,legs,elig) in lst:
        if ei is None or elig is None or not elig: continue
        if half_of.get(s.mint+str(s.t0)) != 1: continue
        if not cm(s,ei,c): continue
        vals.append(DC if r is None else r-legs*TOLL)
    return vals
def agg2(lst,c,half_of,which):
    vals=[]
    for (s,ei,r,legs,elig) in lst:
        if ei is None or elig is None or not elig: continue
        if half_of.get(s.mint+str(s.t0)) != which: continue
        if not cm(s,ei,c): continue
        vals.append(DC if r is None else r-legs*TOLL)
    return vals

def boot_lo(vals,B=1000,seed=7):
    if len(vals)<3: return None
    rnd=random.Random(seed); n=len(vals); ms=[]
    for _ in range(B): ms.append(sum(vals[rnd.randrange(n)] for _ in range(n))/n)
    ms.sort(); return ms[int(0.05*B)]

def pipeline(split_e, split_c, label):
    n_tp=0;n_v=0;n_pl=0;n_lo=0;best=None; cand=0
    for key,lst in CE.items():
        clst=CC[key]
        for c in CONDS:
            a=agg2(lst,c,split_e,1)
            if len(a)<6: continue
            cand+=1
            ma=st.mean(a)
            if ma<=0: continue
            n_tp+=1
            b=agg2(lst,c,split_e,2)
            if len(b)<6 or st.mean(b)<=0: continue
            n_v+=1
            d=agg2(clst,c,split_c,2); cc2=agg2(clst,c,split_c,1)
            if not d or st.mean(b)<=st.mean(d): continue
            if not cc2 or ma<=st.mean(cc2): continue
            n_pl+=1
            lo=boot_lo(b)
            if lo is not None and lo>0:
                n_lo+=1
                if best is None or st.mean(b)>best[0]: best=(st.mean(b),key,c,len(b))
    P(f'{label}: cells={cand} trainpos={n_tp} +valpos={n_v} +beat_placebo={n_pl} +boot_lo>0={n_lo} ({n_lo/max(n_pl,1)*100:.1f}% of gate-3) best_val={best}')
    return n_lo

# real split (by md5%3)
se={s.mint+str(s.t0):s.half for s in EVS}
sc={s.mint+str(s.t0):s.half for s in CTL}
real=pipeline(se,sc,'REAL SPLIT')

# permutations: shuffle which mints are train vs validate, keeping sizes
keys_e=list(se); keys_c=list(sc)
n1e=sum(1 for k in se if se[k]==1); n1c=sum(1 for k in sc if sc[k]==1)
nulls=[]
for rep in range(5):
    rnd=random.Random(1000+rep)
    ke=keys_e[:]; rnd.shuffle(ke)
    pe={k:(1 if i<n1e else 2) for i,k in enumerate(ke)}
    kc=keys_c[:]; rnd.shuffle(kc)
    pc={k:(1 if i<n1c else 2) for i,k in enumerate(kc)}
    nulls.append(pipeline(pe,pc,f'PERM {rep}'))
P('REAL survivors',real,'PERM survivors',nulls,'mean perm',st.mean(nulls))
OUT.close()
