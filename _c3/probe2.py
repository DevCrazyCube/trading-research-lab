import sqlite3, json, hashlib, os
from collections import Counter, defaultdict
O=open('/home/anont/meme/_c3/probe2.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
ohl={m for (m,) in c.execute("select mint from ohlcv where status='ok'")}
p("ohlcv ok mints", len(ohl))
w=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
wl={}
for m,cr,cs,bt,comp,vtr,rtr,dl in w.execute("select mint,creator,create_slot,block_time,complete,virtual_token_reserves,real_token_reserves,data_len from window_label"):
    wl[m]=(cr,cs,bt,comp,vtr,rtr,dl)
p("wl mints", len(wl))
p("ohlcv in wl", len(ohl & set(wl)))
snapm=set(); snapfirst={}
import io
with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        if '"_meta"' in line[:30]: continue
        try: d=json.loads(line)
        except: continue
        m=d.get('mint')
        if not m: continue
        snapm.add(m)
p("snap mints", len(snapm))
p("ohlcv in snap", len(ohl & snapm))
p("wl in snap", len(set(wl) & snapm))
# time ranges
p("wl block_time", min(v[2] for v in wl.values()), max(v[2] for v in wl.values()))
firsts=[r for r in c.execute("select first_ts,last_ts from ohlcv where status='ok'")]
p("ohlcv first_ts", min(x[0] for x in firsts), max(x[0] for x in firsts))
p("ohlcv last_ts", min(x[1] for x in firsts), max(x[1] for x in firsts))
# graduated flag among ohlcv mints
g=Counter(wl[m][3] for m in ohl if m in wl)
p("ohlcv complete dist", g)
# creator prior counts feasible?
cc=Counter(v[0] for v in wl.values())
p("creators", len(cc), "multi-create creators", sum(1 for v in cc.values() if v>1), "max", max(cc.values()))
p("ohlcv mints whose creator has >1 create", sum(1 for m in ohl if m in wl and cc[wl[m][0]]>1))
# bodies db
B='/home/anont/meme/research/b11a/b11a_bodies.sqlite'
p("bodies size", os.path.getsize(B))
b=sqlite3.connect('file:%s?mode=ro'%B,uri=True)
p("bodies tables", b.execute("select name from sqlite_master where type='table'").fetchall())
for t in ['instruction','reserve_observation']:
    try:
        cur=b.execute("select * from %s limit 1"%t)
        p(t,"cols",[d[0] for d in cur.description])
        p(t,"row", str(cur.fetchone())[:800])
        p(t,"count", b.execute("select count(*) from %s"%t).fetchone())
    except Exception as e: p(t,"ERR",e)
O.close()
