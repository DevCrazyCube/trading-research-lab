import sqlite3, json, hashlib, os, statistics
from collections import Counter, defaultdict
O=open('/home/anont/meme/_c3/probe3.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
def H(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=[(m,pool,nb,ft,lt,bj) for m,pool,nb,ft,lt,bj in c.execute("select mint,pool,n_bars,first_ts,last_ts,bars_json from ohlcv where status='ok'")]
rows=[r for r in rows if H(r[0]) in (1,2)]
p("usable mints (h in 1,2)", len(rows))
p("n_bars stats", min(r[2] for r in rows), statistics.median(r[2] for r in rows), max(r[2] for r in rows), sum(r[2] for r in rows))
w=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
bc={}; wl={}
for bcv,m,cr,cs,bt,comp in w.execute("select bonding_curve,mint,creator,create_slot,block_time,complete from window_label"):
    wl[m]=(bcv,cr,cs,bt,comp); bc[bcv]=m
mints={r[0] for r in rows}
bcs={wl[m][0] for m in mints if m in wl}
p("bcs", len(bcs))
b=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
b.execute("create temp table t(bc text primary key)")
b.executemany("insert or ignore into t values(?)", [(x,) for x in bcs])
p("ro rows for our bcs", b.execute("select count(*) from reserve_observation r join t on t.bc=r.bonding_curve").fetchone())
p("distinct bcs with ro", b.execute("select count(distinct bonding_curve) from reserve_observation r join t on t.bc=r.bonding_curve").fetchone())
p("ro index?", b.execute("select name,sql from sqlite_master where type='index'").fetchall())
# time to grad
tt=[]
for m,pool,nb,ft,lt,bj in rows:
    if m in wl: tt.append(ft-wl[m][3])
p("first_ts - block_time (sec): min/med/max", min(tt), statistics.median(tt), max(tt))
p("neg", sum(1 for x in tt if x<0))
# price levels
import json as J
pl=[]; vl=[]
for m,pool,nb,ft,lt,bj in rows[:200]:
    bars=sorted(J.loads(bj), key=lambda x:x[0])
    pl.append(bars[0][1]); vl.append(statistics.median(x[5] for x in bars))
p("first open px: min/med/max", min(pl), statistics.median(pl), max(pl))
p("median bar volume: min/med/max", min(vl), statistics.median(vl), max(vl))
# gaps
gaps=Counter()
for m,pool,nb,ft,lt,bj in rows:
    bars=sorted(J.loads(bj), key=lambda x:x[0])
    ts=[x[0] for x in bars]
    for i in range(len(ts)-1): gaps[(ts[i+1]-ts[i])//60]+=1
p("gap dist (bars) top", gaps.most_common(12))
p("total intervals", sum(gaps.values()))
# survival: how far into the future do bars extend
spans=[(lt-ft)/60 for m,pool,nb,ft,lt,bj in rows]
p("span minutes min/med/max", min(spans), statistics.median(spans), max(spans))
p("frac of span covered by bars (nb/span)", statistics.median([nb/max(1,(lt-ft)/60) for m,pool,nb,ft,lt,bj in rows]))
O.close()
