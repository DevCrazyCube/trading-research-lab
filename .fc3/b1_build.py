import sqlite3, json, hashlib, bisect, pickle, numpy as np
from collections import defaultdict
SP='/home/anont/meme/.fc3'
W=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
B=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
O=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

anch=sorted(set(W.execute('select create_slot,block_time from window_label where block_time is not null').fetchall()))
slots=[a[0] for a in anch]; times=[a[1] for a in anch]
def slot2t(s):
    i=bisect.bisect_left(slots,s)
    if i<=0: return times[0]+(s-slots[0])*0.4
    if i>=len(slots): return times[-1]+(s-slots[-1])*0.4
    if slots[i]==s: return times[i]
    s0,s1=slots[i-1],slots[i]; t0,t1=times[i-1],times[i]
    return t0+(t1-t0)*(s-s0)/(s1-s0)

meta={}; cr=defaultdict(list)
for bc,mint,creator,cs,bt,comp in W.execute('select bonding_curve,mint,creator,create_slot,block_time,complete from window_label'):
    if h3(mint)==0: continue          # NEVER touch holdout
    meta[mint]=dict(bc=bc,creator=creator,create_slot=cs,create_t=bt,complete=comp)
    cr[creator].append((bt,comp))
for c in cr: cr[c].sort()

usable=[]
for mint,pool,nb,ft,lt,bj in O.execute("select mint,pool,n_bars,first_ts,last_ts,bars_json from ohlcv where status='ok'"):
    if h3(mint)==0: continue
    bars=sorted(json.loads(bj), key=lambda b:b[0])
    if len(bars)<3: continue
    if mint not in meta: continue
    usable.append((mint,pool,bars))

bcs={meta[m]['bc']:m for m,_,_ in usable}
robs=defaultdict(list)
for bc,slot,rqa in B.execute('select bonding_curve,slot,real_quote_after from reserve_observation'):
    if bc in bcs: robs[bc].append((slot,rqa))
for bc in robs: robs[bc].sort()

D={}
for mint,pool,bars in usable:
    md=meta[mint]; ct=md['create_t']
    ts=np.array([b[0] for b in bars],dtype=np.int64)
    o=np.array([b[1] for b in bars],float); hi=np.array([b[2] for b in bars],float)
    lo=np.array([b[3] for b in bars],float); cl=np.array([b[4] for b in bars],float)
    vo=np.array([b[5] for b in bars],float)
    ro=robs.get(md['bc'],[])
    gradt=slot2t(ro[-1][0]) if ro else float('nan')
    prior=cr.get(md['creator'],[])
    D[mint]=dict(pool=pool,ts=ts,o=o,hi=hi,lo=lo,cl=cl,vo=vo,create_t=ct,
        gradt=gradt, grad_speed=(gradt-ct) if ro else float('nan'),
        pri=sum(1 for t,c in prior if t<ct), prig=sum(1 for t,c in prior if t<ct and c),
        h=h3(mint), creator=md['creator'])
pickle.dump(D,open(SP+'/mm.pkl','wb'))
out=[]
out.append('mints=%d train(h1)=%d val(h2)=%d bars=%d'%(len(D),
    sum(1 for m in D if D[m]['h']==1), sum(1 for m in D if D[m]['h']==2),
    sum(len(D[m]['ts']) for m in D)))
out.append('with grad time from reserves: %d'%sum(1 for m in D if D[m]['gradt']==D[m]['gradt']))
import statistics as st
nb=sorted(len(D[m]['ts']) for m in D)
out.append('bars/mint q: '+str([nb[int(q*(len(nb)-1))] for q in (0,.25,.5,.75,.9,1)]))
open(SP+'/b1.log','w').write('\n'.join(out))
