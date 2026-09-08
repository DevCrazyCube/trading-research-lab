import sqlite3, json, hashlib, os, sys, statistics
OUT=open('/home/anont/meme/.c2w/probe.txt','w')
def p(*a): print(*a, file=OUT)

try:
    import numpy as np
    p("numpy", np.__version__)
except Exception as e:
    p("numpy MISSING", e)

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
c=sqlite3.connect(DB)
p("tables", c.execute("select name,sql from sqlite_master where type='table'").fetchall())
p("count", c.execute("select count(*) from ohlcv").fetchone())
p("status dist", c.execute("select status, count(*) from ohlcv group by status").fetchall())
p("nbars dist", c.execute("select min(n_bars),max(n_bars),avg(n_bars) from ohlcv where n_bars>0").fetchone())

# pick a h in (1,2) mint
rows=c.execute("select mint,pool,n_bars,first_ts,last_ts,status,bars_json from ohlcv where n_bars>5").fetchall()
sel=None
for r in rows:
    h=int(hashlib.md5(r[0].encode()).hexdigest(),16)%3
    if h in (1,2):
        sel=r; break
p("sample mint h", int(hashlib.md5(sel[0].encode()).hexdigest(),16)%3, sel[0], sel[1], sel[2], sel[3], sel[4], sel[5])
b=json.loads(sel[6])
p("bars type", type(b), "len", len(b))
p("first3", b[:3])
p("last3", b[-3:])
# gap analysis on a few mints
import collections
gapc=collections.Counter(); volzero=0; tot=0; nm=0
for r in rows:
    h=int(hashlib.md5(r[0].encode()).hexdigest(),16)%3
    if h==0: continue
    nm+=1
    if nm>60: break
    bb=sorted(json.loads(r[6]), key=lambda x:x[0])
    for i in range(1,len(bb)):
        gapc[bb[i][0]-bb[i-1][0]]+=1
    for x in bb:
        tot+=1
        if x[5]==0: volzero+=1
p("gap top20", gapc.most_common(20))
p("volzero", volzero, "of", tot)
p("ts units sample", b[0][0], b[-1][0])
OUT.close()
