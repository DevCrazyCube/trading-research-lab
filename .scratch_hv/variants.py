import sys, statistics, sqlite3
from collections import Counter
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load, run_trades, aggregate
O=open('/home/anont/meme/.scratch_hv/variants.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n'); O.flush()

c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
p('fetched_at dist:', Counter(str(r[0])[:13] for r in c.execute('select fetched_at from ohlcv')).most_common(20))

W=20
def sig_A(b):  # v/mean(prev20), sum(prev20)
    v=[x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        s=sum(v[i-W:i])
        if s<=0: continue
        if v[i]/(s/W)<=0.05 and s>=300: out.append(i)
    return out
def sig_B(b):  # window includes bar i
    v=[x[5] for x in b]; out=[]
    for i in range(W-1,len(b)-1):
        s=sum(v[i-W+1:i+1])
        if s<=0: continue
        if v[i]/(s/W)<=0.05 and s>=300: out.append(i)
    return out
def sig_C(b):  # v/sum(prev20)
    v=[x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        s=sum(v[i-W:i])
        if s<=0: continue
        if v[i]/s<=0.05 and s>=300: out.append(i)
    return out
def sig_D(b):  # v/median(prev20)
    v=[x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        w=v[i-W:i]; s=sum(w); md=statistics.median(w)
        if md<=0 or s<=0: continue
        if v[i]/md<=0.05 and s>=300: out.append(i)
    return out
def sig_E(b):  # notional = sum(close*vol) prev20, rvol vs mean
    v=[x[5] for x in b]; n=[x[4]*x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        s=sum(v[i-W:i]); sn=sum(n[i-W:i])
        if s<=0: continue
        if v[i]/(s/W)<=0.05 and sn>=300: out.append(i)
    return out

for name,fn in (('A v/mean20,sumvol>=300',sig_A),('B incl-i',sig_B),('C v/sum20',sig_C),
                ('D v/median20',sig_D),('E notional=px*vol',sig_E)):
    for hs,lab in (({1},'h1'),({2},'h2')):
        data=load(hs); per={}
        for m,b in data:
            tr=run_trades(b,fn(b),hold_min=45)
            if tr: per[m]=tr
        mm,at,rn,tn=aggregate(per,0.0114,-0.30)
        if not mm:
            p(f'{name} {lab}: no trades'); continue
        p(f'{name} {lab}: n={tn} k={len(mm)} res={rn/tn*100:.1f}% mean={statistics.mean(mm)*100:.3f}% '
          f'med={statistics.median(mm)*100:.3f}% tradeMed={statistics.median(at)*100:.3f}%')
O.close()
