from h66 import *
import json
meme=json.load(open('meme.json'))
FEE=0.001
# unconditional benchmark: short at close(t+1) for EVERY eligible day (same maturity filter, same symbols)
def bench(symbols,Hs,side='short',min_hist=90,trail=30):
    tr=[]
    for sym in symbols:
        if sym not in fund or sym not in px: continue
        days=sorted(set(fund[sym])&set(px[sym]))
        if len(days)<min_hist+trail+max(Hs)+2: continue
        pdays=sorted(px[sym]); pidx={d:i for i,d in enumerate(pdays)}
        n=0
        for i,d in enumerate(days):
            if i<trail-1: continue
            n+=1
            if n<min_hist: continue
            j=pidx.get(d)
            if j is None or j+1>=len(pdays): continue
            ed=pdays[j+1]
            if ed-d>3*DAY: continue
            ep=px[sym][ed][0]
            rec={'sym':sym,'entry_day':ed}
            for H in Hs:
                k=j+1+H
                rec['r%d'%H]=((ep-px[sym][pdays[k]][0])/ep if side=='short' else (px[sym][pdays[k]][0]-ep)/ep) if (k<len(pdays) and pdays[k]-ed<=(H+3)*DAY) else None
            tr.append(rec)
    return tr
b=bench(meme,[3,7,14])
print('=== BENCHMARK: unconditional same-symbol SHORT, every eligible day')
for H in (3,7,14):
    for dc,lab in ((None,'resolved-only'),(-1.00,'drop@-100%')):
        s=summarize(b,H,FEE,dc,lab)
        print('  H=%2d %-13s n=%5d cl=%2d mean=%+7.2f%% med=%+7.2f%% ci=[%+7.2f,%+7.2f] res=%5.1f%%'%(s['H'],s['tag'],s['n'],s['clusters'],s['mean'],s['median'],s['ci_lo'],s['ci_hi'],s['resolution']))
