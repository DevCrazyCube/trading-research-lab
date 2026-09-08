import sys, json, statistics as st, collections, math, random
sys.path.insert(0,'/home/anont/meme/.scratch_att2')
from engine import *

OUT=open('/home/anont/meme/.scratch_att2/full_out.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()

ev,g,FEND=load()
EVS=build(ev,g,FEND,False)
CTL=build(ev,g,FEND,True)
TRAIN=[s for s in EVS if s.half==1]; VAL=[s for s in EVS if s.half==2]
CTRAIN=[s for s in CTL if s.half==1]; CVAL=[s for s in CTL if s.half==2]
P('n TRAIN',len(TRAIN),'VAL',len(VAL),'placeboTRAIN',len(CTRAIN),'placeboVAL',len(CVAL))

TOLL=0.0114; TOLL2=0.025
DC={-0.30:'-30',-0.50:'-50',-1.00:'-100'}

def arm(series_list,S,H,ekind,ep,pkind,pp):
    params=dict(ep); params.update(pp)
    out=[]
    for s in series_list:
        ei=entry_index(s,S)
        if ei is None: out.append((s,None,None,None,None)); continue
        eligible = s.avail >= s.t[ei]+H
        o=sim(s,ei,H,ekind,pkind,params)
        if o is None: out.append((s,ei,None,None,eligible)); continue
        if o[0]=='DROP': out.append((s,ei,None,None,eligible)); continue
        out.append((s,ei,o[0],o[1],eligible))
    return out

def cell(res,cname,toll,dc):
    vals=[];nd=0
    for (s,ei,r,legs,elig) in res:
        if ei is None or elig is None: continue
        if not elig: continue
        if not cond_mask(s,ei,cname): continue
        if r is None: vals.append(dc); nd+=1
        else: vals.append(r-legs*toll)
    if not vals: return None
    return (st.mean(vals), st.median(vals), len(vals), (len(vals)-nd)/len(vals), vals)

def boot_lo(vals,B=2000,seed=7):
    if len(vals)<3: return None
    rnd=random.Random(seed); n=len(vals); ms=[]
    for _ in range(B):
        ms.append(sum(vals[rnd.randrange(n)] for _ in range(n))/n)
    ms.sort(); return ms[int(0.05*B)]

rows=[]; combos=0
for S in S_GRID:
    for H in H_GRID:
        for ekind,ep in EXITS:
            for pkind,pp in POS:
                A=arm(TRAIN,S,H,ekind,ep,pkind,pp)
                B=arm(VAL,  S,H,ekind,ep,pkind,pp)
                C=arm(CTRAIN,S,H,ekind,ep,pkind,pp)
                D=arm(CVAL, S,H,ekind,ep,pkind,pp)
                for c in CONDS:
                    combos+=1
                    a=cell(A,c,TOLL,-0.30)
                    if a is None or a[2]<6: continue
                    b=cell(B,c,TOLL,-0.30)
                    cc=cell(C,c,TOLL,-0.30); dd=cell(D,c,TOLL,-0.30)
                    rows.append(dict(S=S,H=H,exit=ekind,pos=pkind,cond=c,
                        tmean=a[0],tmed=a[1],tn=a[2],tres=a[3],
                        vmean=(b[0] if b else None),vmed=(b[1] if b else None),vn=(b[2] if b else 0),vres=(b[3] if b else None),
                        pcmean=(cc[0] if cc else None),pcn=(cc[2] if cc else 0),
                        pdmean=(dd[0] if dd else None),pdn=(dd[2] if dd else 0),
                        vvals=(b[4] if b else [])))
P('combos evaluated:',combos)
P('cells with train n>=6:',len(rows))
tp=[r for r in rows if r['tmean']>0]
P('train-positive:',len(tp),f'({len(tp)/len(rows)*100:.1f}%)')
# survive validate
sv=[r for r in tp if r['vn']>=6 and r['vmean'] is not None and r['vmean']>0]
P('train-positive AND validate-positive (n>=6):',len(sv))
P('  expected by chance if independent coin flips: ~', int(len(tp)*0.5))
# beat placebo on validate
sv2=[r for r in sv if r['pdmean'] is not None and r['vmean']>r['pdmean']]
P('  ... AND validate mean > placebo-validate mean:',len(sv2))
# also beat placebo on train
sv3=[r for r in sv2 if r['pcmean'] is not None and r['tmean']>r['pcmean']]
P('  ... AND train mean > placebo-train mean:',len(sv3))
# bootstrap lower bound > 0 on validate
sv4=[]
for r in sv3:
    lo=boot_lo(r['vvals'])
    r['vlo']=lo
    if lo is not None and lo>0: sv4.append(r)
P('  ... AND validate bootstrap 5% lower bound > 0:',len(sv4))
sv4.sort(key=lambda r:-r['vmean'])
P('SURVIVORS (top 40):')
for r in sv4[:40]:
    P('  ',f"S={r['S']:>5} H={r['H']:>5} {r['exit']:<14} {r['pos']:<9} {r['cond']:<32} "
          f"train={r['tmean']*100:+7.2f}%(n{r['tn']}) val={r['vmean']*100:+7.2f}%(med{r['vmed']*100:+6.2f}%,n{r['vn']},lo{r['vlo']*100:+6.2f}%) "
          f"plc_v={r['pdmean']*100 if r['pdmean'] is not None else float('nan'):+7.2f}%(n{r['pdn']})")
json.dump([{k:v for k,v in r.items() if k!='vvals'} for r in rows],open('/home/anont/meme/.scratch_att2/all_rows.json','w'))
json.dump([{k:v for k,v in r.items() if k!='vvals'} for r in sv4],open('/home/anont/meme/.scratch_att2/survivors.json','w'))
P('done')
OUT.close()
