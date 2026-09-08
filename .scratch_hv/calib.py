import sys, statistics, random
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load, simulate, aggregate
O=open('/home/anont/meme/.scratch_hv/calib.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n'); O.flush()

# Canonical random-bar 15m benchmark: EVERY bar i is a signal, enter at open of bar i+1,
# exit at open of first real bar with ts >= entry_ts+15min. NO stop, NO tp.
# Contract B (no overlap) applied.
def bench(hset, hold=15, label=''):
    data=load(hset)
    per={}
    for m,b in data:
        tr=[]; busy=-1
        for i in range(0,len(b)-1):
            j=i+1
            if j<=busy: continue
            r=simulate(b,j,hold_min=hold,stop_mult=0.0,tp_mult=1e18)
            if r is None: continue
            k,acc,drop,res=r
            busy=k; tr.append((acc,drop,res))
        if tr: per[m]=tr
    for dc,dl in ((-0.30,'-30%'),(-0.50,'-50%'),(-1.00,'-100%')):
        mm,at,rn,tn=aggregate(per,0.0114,dc)
        p(f'{label} drop{dl}: n={tn} k={len(mm)} res={rn/tn*100:.1f}% mint-mean={statistics.mean(mm)*100:.3f}% '
          f'mint-median={statistics.median(mm)*100:.3f}% trade-median={statistics.median(at)*100:.3f}%')
    # gross (no toll)
    mm,at,rn,tn=aggregate(per,0.0,-0.30)
    p(f'{label} GROSS drop-30%: mint-mean={statistics.mean(mm)*100:.3f}%')

bench({1,2},15,'RANDOMBAR15 h12')
O.close()
