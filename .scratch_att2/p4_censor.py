import json, hashlib, collections, statistics as st
OUT=open('/home/anont/meme/.scratch_att2/p4.txt','w')
def P(*a): print(*a, file=OUT)
def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

ev={}; tk=[]
for line in open('/home/anont/meme/research/midcap/attention.jsonl'):
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    if d.get('ev')=='EVENT': ev.setdefault((d['mint'],d['ts_ms']),d)
    elif d.get('ev')=='TICK': tk.append(d)
FEND=max(t['ts_ms'] for t in tk)
P('file end ts',FEND)
g=collections.defaultdict(list)
for t in tk: g[(t['mint'],t['t0'])].append(t)
for v in g.values(): v.sort(key=lambda x:x['ts_ms'])

rows=[]
for (m,t0),v in g.items():
    if h(m) not in (1,2): continue
    last=v[-1]['ts_ms']
    avail=(FEND-t0)/60000.0        # calendar horizon available
    obs=(last-t0)/60000.0          # observed horizon
    rows.append((m,t0,avail,obs,len(v),h(m)))
rows.sort(key=lambda r:r[2])
P('n h12 series',len(rows))
P('avail vs obs (minutes): showing gap = avail-obs')
gaps=sorted(r[2]-r[3] for r in rows)
P(' gap min/p25/med/p75/max',[round(gaps[i],1) for i in (0,len(gaps)//4,len(gaps)//2,3*len(gaps)//4,-1)])
P(' series where gap > 5m (i.e. TRULY stopped early):',sum(1 for r in rows if r[2]-r[3]>5))
P(' series where gap > 20m:',sum(1 for r in rows if r[2]-r[3]>20))
P('avail horizon distribution:',[round(r[2],0) for r in rows])
for H in (5,15,30,60,120,180,240):
    elig=[r for r in rows if r[2]>=H]
    has=[r for r in elig if r[3]>=H-1.6]
    P(f'H={H}m: calendar-eligible={len(elig)} (h1={sum(1 for r in elig if r[5]==1)},h2={sum(1 for r in elig if r[5]==2)}) with-data={len(has)} resolution={len(has)/len(elig)*100 if elig else 0:.1f}%')

# event metadata joined to h12 series
P('--- event metadata for h12 ---')
md=[]
for (m,t0) in g:
    if h(m) not in (1,2): continue
    e=ev.get((m,t0))
    md.append((m,t0,e['feed'] if e else None,(e or {}).get('total'),(e or {}).get('amount'),(e or {}).get('mcap'),(e or {}).get('liq'),(e or {}).get('age_h')))
P('joined events',sum(1 for x in md if x[2]),'of',len(md))
P('feed',collections.Counter(x[2] for x in md))
mc=sorted(x[5] for x in md if x[5] is not None)
P('mcap n',len(mc),'min/p25/med/p75/max',[round(mc[i]) for i in (0,len(mc)//4,len(mc)//2,3*len(mc)//4,-1)] if mc else None)
lq=sorted(x[6] for x in md if x[6] is not None)
P('liq n',len(lq),'quantiles',[round(lq[i]) for i in (0,len(lq)//4,len(lq)//2,3*len(lq)//4,-1)] if lq else None)
ag=sorted(x[7] for x in md if x[7] is not None)
P('age_h n',len(ag),'quantiles',[round(ag[i],2) for i in (0,len(ag)//4,len(ag)//2,3*len(ag)//4,-1)] if ag else None)
P('total(paid) values',collections.Counter(x[3] for x in md))
OUT.close()
