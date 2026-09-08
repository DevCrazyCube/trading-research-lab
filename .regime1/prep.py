import sqlite3, json, os, hashlib, time
from collections import defaultdict

OUT=open('/home/anont/meme/.regime1/prep.txt','w')
def P(*a):
    print(*a, file=OUT)

def h(m):
    return int(hashlib.md5(m.encode()).hexdigest(),16)%3

# ---------- OHLCV ----------
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=c.execute("select mint,pool,n_bars,bars_json,status from ohlcv").fetchall()
P('total ohlcv rows', len(rows))
mints={}
skipped_h0=0
for mint,pool,nb,bj,status in rows:
    hh=h(mint)
    if hh==0:
        skipped_h0+=1
        continue
    if not bj: continue
    b=json.loads(bj)
    if not b: continue
    b=sorted(b, key=lambda x:x[0])
    # dedupe ts
    out=[]
    seen=set()
    for r in b:
        if r[0] in seen: continue
        seen.add(r[0]); out.append(r)
    if len(out)<2: continue
    mints[mint]=(hh,out)
P('h0 skipped (never parsed)', skipped_h0)
P('allowed mints with >=2 bars', len(mints))
P('train(h=1)', sum(1 for v in mints.values() if v[0]==1), 'validate(h=2)', sum(1 for v in mints.values() if v[0]==2))
allts=[]
for m,(hh,b) in mints.items():
    allts.append(b[0][0]); allts.append(b[-1][0])
P('ts range', min(allts), max(allts), 'span_days', (max(allts)-min(allts))/86400.)
nb=sorted(len(v[1]) for v in mints.values())
P('bars per mint q', nb[0], nb[len(nb)//4], nb[len(nb)//2], nb[3*len(nb)//4], nb[-1], 'total', sum(nb))
# gap structure
gaps=[]
for m,(hh,b) in mints.items():
    for i in range(1,len(b)):
        gaps.append(b[i][0]-b[i-1][0])
gaps.sort()
P('gap secs q', gaps[0], gaps[len(gaps)//4], gaps[len(gaps)//2], gaps[int(.9*len(gaps))], gaps[-1])
P('frac gaps==60', sum(1 for g in gaps if g==60)/len(gaps))

# ---------- window_labels (creates) ----------
try:
    c2=sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro',uri=True)
    P('wl tables', [r[0] for r in c2.execute("select name from sqlite_master where type='table'")])
    P('wl cols', [d[0] for d in c2.execute('select * from window_label limit 1').description])
    n=0; kept=0; tmin=None; tmax=None
    creates=[]
    for mint, bt in c2.execute('select mint, block_time from window_label'):
        n+=1
        if mint is None or bt is None: continue
        if h(mint)==0: continue
        kept+=1
        creates.append(int(bt))
    creates.sort()
    P('wl rows', n, 'allowed creates', kept)
    if creates:
        P('create ts range', creates[0], creates[-1])
    json.dump(creates, open('/home/anont/meme/.regime1/creates.json','w'))
except Exception as e:
    P('wl error', repr(e))

# ---------- snapshots overlap check ----------
try:
    n=0; tmin=None; tmax=None
    with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
        for line in f:
            if '"_meta"' in line[:40]: continue
            n+=1
            i=line.find('"ts_ms":')
            if i<0: continue
            j=line.find(',', i)
            t=int(line[i+8:j])//1000
            tmin=t if tmin is None or t<tmin else tmin
            tmax=t if tmax is None or t>tmax else tmax
    P('snapshots', n, 'ts range', tmin, tmax)
except Exception as e:
    P('snap error', repr(e))

# save bars
json.dump({m:[v[0], v[1]] for m,v in mints.items()}, open('/home/anont/meme/.regime1/bars.json','w'))
P('saved')
OUT.close()
