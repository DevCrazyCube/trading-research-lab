import sqlite3, json, hashlib, collections
OUT=open('/home/anont/meme/.c2w/probe2.txt','w')
def p(*a): print(*a, file=OUT)

# window_labels
c=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
p("wl tables", [r[0] for r in c.execute("select name from sqlite_master where type='table'")])
p("wl cols", [d[0] for d in c.execute("select * from window_label limit 1").description])
p("wl count", c.execute("select count(*), sum(complete) from window_label").fetchone())
p("wl sample", c.execute("select * from window_label limit 2").fetchall())

# snapshots
n=0; keys=None; mints=set(); per=collections.Counter()
with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except Exception: continue
        if d.get('mint') is None:
            if n<3: p("meta line keys", list(d.keys())[:20])
            continue
        n+=1
        if keys is None: keys=sorted(d.keys()); p("snap keys", keys); p("snap sample", d)
        mints.add(d['mint']); per[d['mint']]+=1
p("snap rows", n, "distinct mints", len(mints))
p("snaps per mint quantiles", sorted(per.values())[::max(1,len(per)//10)][:12])

# overlap with ohlcv
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
om=[r[0] for r in g.execute("select mint from ohlcv where status='ok' and n_bars>0")]
om12=[m for m in om if int(hashlib.md5(m.encode()).hexdigest(),16)%3 in (1,2)]
p("ohlcv ok mints", len(om), "h12", len(om12))
p("overlap with snapshots", len(set(om12)&mints))
wl={r[0]:r for r in c.execute("select mint,creator,create_slot,block_time,complete from window_label")}
p("overlap with window_labels", len(set(om12)&set(wl.keys())))
h1=[m for m in om12 if int(hashlib.md5(m.encode()).hexdigest(),16)%3==1]
h2=[m for m in om12 if int(hashlib.md5(m.encode()).hexdigest(),16)%3==2]
p("train(h1)", len(h1), "validate(h2)", len(h2))
tot=0
for m in om12:
    tot+=g.execute("select n_bars from ohlcv where mint=?", (m,)).fetchone()[0]
p("total bars h12", tot)
OUT.close()
