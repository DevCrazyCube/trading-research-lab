import json, pickle, collections, hashlib
SCR='/home/anont/meme/.scr2'
D=pickle.load(open(SCR+'/data.pkl','rb'))
BARS=D['bars']; META=D['meta']
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
first={}
n=0
keys=None
for line in open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl'):
    line=line.strip()
    if not line: continue
    try: r=json.loads(line)
    except Exception: continue
    n+=1
    if r.get('mint') is None: continue
    m=r['mint']
    if keys is None: keys=sorted(r.keys())
    if m not in first or r.get('ts_ms',0)<first[m].get('ts_ms',1e18):
        first[m]=r
p("rows",n,"distinct mints",len(first))
p("keys",keys)
hit=[m for m in BARS if m in first]
p("our mints covered by snapshots:",len(hit),"of",len(BARS))
if hit:
    ex=first[hit[0]]
    p("example",json.dumps(ex)[:600])
    for f in ('has_x','has_tg','has_web','replies'):
        vals=[first[m].get(f) for m in hit]
        p(f,collections.Counter(str(v) for v in vals).most_common(8))
    # snapshot age at first observation
    ages=[]
    for m in hit:
        r=first[m]
        if r.get('created_ms') and r.get('ts_ms'):
            ages.append((r['ts_ms']-r['created_ms'])/1000.0)
    ages.sort()
    p("age at first snapshot (s) deciles:",[round(ages[int(i*len(ages)/10)],0) for i in range(10)] if ages else None)
open(SCR+'/snap_probe.out','w').write("\n".join(o))
