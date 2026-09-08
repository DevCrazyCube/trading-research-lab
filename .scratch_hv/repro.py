import sys, statistics, random
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load, signals, run_trades, aggregate, boot_ci, net_ret, simulate
O=open('/home/anont/meme/.scratch_hv/repro.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n'); O.flush()

def evaluate(hset, label, rvol_max=0.05, not_min=300.0, hold=45):
    data=load(hset)
    per={}
    nsig=0
    for m,b in data:
        sg=signals(b, rvol_max, not_min)
        nsig+=len(sg)
        tr=run_trades(b,sg,hold_min=hold)
        if tr: per[m]=tr
    for toll,tl in ((0.0114,'1.14%'),):
        for dc,dl in ((-0.30,'-30%'),):
            mm,at,rn,tn=aggregate(per,toll,dc)
            p(f'[{label}] mints={len(data)} raw_signals={nsig} trades={tn} clusters={len(mm)} res={rn/tn*100 if tn else 0:.1f}% '
              f'mint-mean={statistics.mean(mm)*100 if mm else float("nan"):.4f}% mint-median={statistics.median(mm)*100 if mm else float("nan"):.4f}% '
              f'trade-median={statistics.median(at)*100 if at else float("nan"):.4f}%')
    return per

for hs,lab in (({1},'h==1'),({2},'h==2'),({1,2},'h in 1,2')):
    evaluate(hs,lab)
O.close()
