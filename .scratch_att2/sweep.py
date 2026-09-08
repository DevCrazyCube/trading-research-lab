import sys, json, statistics as st, collections, math, random
sys.path.insert(0,'/home/anont/meme/.scratch_att2')
from engine import *

OUT=open('/home/anont/meme/.scratch_att2/sweep_out.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()

ev,g,FEND=load()
EVS=build(ev,g,FEND,use_control=False)     # attention-event mints, h12 only
CTL=build(ev,g,FEND,use_control=True)      # matched control mints, h12 only (placebo)
P('event series h12:',len(EVS),' train(h=1):',sum(1 for s in EVS if s.half==1),' val(h=2):',sum(1 for s in EVS if s.half==2))
P('placebo control series (h12 mint AND h12 ctrl):',len(CTL))

TOLLS={'1.14':0.0114,'2.50':0.025}
DROP_CHARGES={'-30':-0.30,'-50':-0.50,'-100':-1.00}

def run_all(series_list, S,H,ekind,eparams,pkind,pparams):
    """-> list of (series, gross_r, legs, resolved, eligible)"""
    res=[]
    params=dict(eparams); params.update(pparams)
    for s in series_list:
        ei=entry_index(s,S)
        if ei is None:
            res.append((s,None,None,None,None)); continue   # no fill
        eligible = s.avail >= s.t[ei]+H
        o=sim(s,ei,H,ekind,pkind,params)
        if o is None: res.append((s,None,None,None,eligible)); continue
        if o[0]=='DROP': res.append((s,None,None,False,eligible)); continue
        res.append((s,o[0],o[1],True,eligible))
    return res

def headline(res, mask_name, toll, drop_charge, require_eligible=True):
    """Mint-equal weighted. Returns dict or None."""
    vals=[]; ndrop=0; nfill=0; ntot=0
    for (s,r,legs,resolved,eligible) in res:
        if r is None and resolved is None and eligible is None:
            continue  # no fill: not a trade
        ei=entry_index(s,0.0)  # for cond eval we need the actual entry index; recompute below
        ntot+=1
    # recompute properly with per-series entry index
    vals=[]; ndrop=0; nfilled=0; nelig=0
    for (s,r,legs,resolved,eligible) in res:
        if eligible is None: continue
        if require_eligible and not eligible: continue
        nelig+=1
        ei=res_entry.get(id(s))
        if ei is None: continue
        if not cond_mask(s,ei,mask_name): continue
        nfilled+=1
        if resolved:
            vals.append(net(r,legs,toll))
        else:
            ndrop+=1
            vals.append(drop_charge)
    if not vals: return None
    return dict(mean=st.mean(vals), median=st.median(vals), n=len(vals),
                res=(len(vals)-ndrop)/len(vals), vals=vals)

# entry indices cached per (S, series)
res_entry={}

def sweep(series_list, S,H,ekind,eparams,pkind,pparams):
    global res_entry
    res_entry={}
    params=dict(eparams); params.update(pparams)
    out=[]
    for s in series_list:
        ei=entry_index(s,S)
        res_entry[id(s)]=ei
        if ei is None:
            out.append((s,None,None,None,None)); continue
        eligible = s.avail >= s.t[ei]+H
        o=sim(s,ei,H,ekind,pkind,params)
        if o is None: out.append((s,None,None,None,eligible)); continue
        if o[0]=='DROP': out.append((s,None,None,False,eligible)); continue
        out.append((s,o[0],o[1],True,eligible))
    return out

TRAIN=[s for s in EVS if s.half==1]
VAL  =[s for s in EVS if s.half==2]
CTRAIN=[s for s in CTL if s.half==1]
CVAL  =[s for s in CTL if s.half==2]

toll=TOLLS['1.14']; dc=DROP_CHARGES['-30']

rows=[]; combos=0
for S in S_GRID:
    for H in H_GRID:
        for ekind,ep in EXITS:
            for pkind,pp in POS:
                rt=sweep(TRAIN,S,H,ekind,ep,pkind,pp); ent_t=dict(res_entry)
                for c in CONDS:
                    combos+=1
                    res_entry=ent_t
                    a=headline(rt,c,toll,dc)
                    if a is None or a['n']<6: continue
                    rows.append(dict(S=S,H=H,exit=ekind,pos=pkind,cond=c,
                                     tmean=a['mean'],tmed=a['median'],tn=a['n'],tres=a['res']))
P('combos swept on TRAIN:',combos)
P('cells with n>=6:',len(rows))
pos=[r for r in rows if r['tmean']>0]
P('cells with POSITIVE train mean:',len(pos))
pos.sort(key=lambda r:-r['tmean'])
P('top 40 train cells:')
for r in pos[:40]:
    P('  ',f"S={r['S']:>5} H={r['H']:>5} {r['exit']:<14} {r['pos']:<9} {r['cond']:<32} mean={r['tmean']*100:+7.2f}% med={r['tmed']*100:+7.2f}% n={r['tn']}")
json.dump(rows,open('/home/anont/meme/.scratch_att2/train_rows.json','w'))
P('saved.')
OUT.close()
