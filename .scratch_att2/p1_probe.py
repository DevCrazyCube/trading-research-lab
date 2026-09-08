import json, sqlite3, hashlib, collections, sys, os
OUT=open('/home/anont/meme/.scratch_att2/p1.txt','w')
def P(*a): print(*a, file=OUT)

def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

rows=[]; metas=[]
for line in open('/home/anont/meme/research/midcap/attention.jsonl'):
    line=line.strip()
    if not line: continue
    try: d=json.loads(line)
    except Exception: continue
    if d.get('ev')=='EVENT': rows.append(d)
    else: metas.append(d)
P('n_event_rows',len(rows),'n_meta',len(metas))
P('keys',sorted(rows[0].keys()))
P('feeds',collections.Counter(r.get('feed') for r in rows))
P('ts range',min(r['ts_ms'] for r in rows),max(r['ts_ms'] for r in rows))
P('unique mints',len(set(r['mint'] for r in rows)))
P('unique controls',len(set(r['control'] for r in rows if r.get('control'))))
P('amount dist',collections.Counter(r.get('amount') for r in rows).most_common(20))
P('total dist',collections.Counter(r.get('total') for r in rows).most_common(20))
# dedupe: same mint+total?
P('unique (mint,total)',len(set((r['mint'],r.get('total')) for r in rows)))
P('unique (mint,ts)',len(set((r['mint'],r['ts_ms']) for r in rows)))

# ohlcv
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
try:
    cols=[r[1] for r in c.execute('pragma table_info(ohlcv)')]
    P('ohlcv cols',cols)
except Exception as e:
    P('err',e)
mints=[r[0] for r in c.execute('select mint from ohlcv where n_bars>0')]
P('ohlcv mints with bars',len(mints))
S=set(mints)
P('ohlcv h dist',collections.Counter(h(m) for m in mints))
ev_in=[r for r in rows if r['mint'] in S]
P('event rows whose mint in ohlcv',len(ev_in),'unique',len(set(r['mint'] for r in ev_in)))
ct_in=[r for r in rows if r.get('control') in S]
P('event rows whose control in ohlcv',len(ct_in),'unique',len(set(r['control'] for r in ct_in)))
both=[r for r in rows if r['mint'] in S and r.get('control') in S]
P('rows with BOTH in ohlcv',len(both),'unique mints',len(set(r['mint'] for r in both)))
# restricted to h in (1,2) for the event mint
b12=[r for r in both if h(r['mint']) in (1,2) and h(r['control']) in (1,2)]
P('BOTH and both h in (1,2)',len(b12),'unique',len(set(r['mint'] for r in b12)))
ev12=[r for r in ev_in if h(r['mint']) in (1,2)]
P('event-mint-only h12',len(ev12),'unique',len(set(r['mint'] for r in ev12)))

# time coverage of bars vs event ts
import json as J
q=c.execute('select mint,first_ts,last_ts,n_bars from ohlcv where n_bars>0')
info={m:(a,b,n) for m,a,b,n in q}
k=0
for r in ev12[:]:
    m=r['mint']; a,b,n=info[m]
    # detect ts units
    if k<5: P('sample first_ts,last_ts,n',a,b,n,'event ts_ms',r['ts_ms']); k+=1
cov=0
for r in ev12:
    a,b,n=info[r['mint']]
    t=r['ts_ms']//1000
    if a<=t<=b: cov+=1
P('ev12 with event ts inside bar range (sec assumption)',cov,'of',len(ev12))
OUT.close()
