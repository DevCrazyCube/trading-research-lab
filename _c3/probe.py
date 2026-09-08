import sys, os, sqlite3, json, hashlib
O = open('/home/anont/meme/_c3/probe.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
try:
    import numpy as np; p("numpy", np.__version__)
except Exception as e: p("numpy MISSING", e)
p("python", sys.version.split()[0])

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
c=sqlite3.connect('file:%s?mode=ro'%DB, uri=True)
p("tables", c.execute("select name from sqlite_master where type='table'").fetchall())
cur=c.execute("select * from ohlcv limit 1"); cols=[d[0] for d in cur.description]; p("cols", cols)
p("count,bars", c.execute("select count(*), sum(n_bars) from ohlcv").fetchone())
p("status", c.execute("select status, count(*) from ohlcv group by status").fetchall())

def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
# sample ONE mint with h in (1,2)
row=None
for mint,bj,nb,ft,lt,st in c.execute("select mint,bars_json,n_bars,first_ts,last_ts,status from ohlcv"):
    if h(mint) in (1,2) and nb and nb>60:
        row=(mint,bj,nb,ft,lt,st); break
mint,bj,nb,ft,lt,st = row
bars=json.loads(bj)
p("sample mint", mint, "n_bars", nb, "first_ts",ft,"last_ts",lt,"status",st)
p("len(bars)", len(bars))
p("bars[0]", bars[0]); p("bars[1]", bars[1]); p("bars[-1]", bars[-1])
b=sorted(bars, key=lambda x:x[0])
p("asc first3", b[:3]); p("asc last3", b[-3:])
ts=[x[0] for x in b]
d=[ts[i+1]-ts[i] for i in range(len(ts)-1)]
from collections import Counter
p("ts deltas top", Counter(d).most_common(8))
p("span_min", (ts[-1]-ts[0]))
p("zero-vol bars", sum(1 for x in b if x[5]==0), "of", len(b))
p("close range", min(x[4] for x in b), max(x[4] for x in b))
p("vol range", min(x[5] for x in b), max(x[5] for x in b))

# h distribution over ohlcv mints -- count only 1,2 vs 'other' aggregate (no per-mint read of h0 features)
cnt={0:0,1:0,2:0}
nb_by={0:0,1:0,2:0}
for mint,nbv in c.execute("select mint,n_bars from ohlcv"):
    k=h(mint); cnt[k]+=1; nb_by[k]+= (nbv or 0)
p("h counts (aggregate only)", cnt, nb_by)

# window labels
W='/home/anont/meme/research/b11a/window_labels.sqlite'
w=sqlite3.connect('file:%s?mode=ro'%W, uri=True)
p("wl tables", w.execute("select name from sqlite_master where type='table'").fetchall())
cur=w.execute("select * from window_label limit 2"); p("wl cols", [d[0] for d in cur.description]); p("wl rows", cur.fetchall())
p("wl count", w.execute("select count(*), sum(complete) from window_label").fetchone())
p("wl block_time range", w.execute("select min(block_time), max(block_time) from window_label").fetchone())

# snapshots
S='/home/anont/meme/research/midcap/fresh_snapshots.jsonl'
p("snap size", os.path.getsize(S))
n=0
with open(S) as f:
    for line in f:
        n+=1
        if n<=2:
            p("snapline", line[:600])
p("snap lines", n)

# attention
A='/home/anont/meme/research/midcap/attention.jsonl'
if os.path.exists(A):
    with open(A) as f:
        ls=f.readlines()
    p("attention lines", len(ls))
    for l in ls[:2]: p("att", l[:500])
O.close()
