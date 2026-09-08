import json,pickle,collections,hashlib,sqlite3
o=open('/home/anont/meme/.ff3/step10.txt','w')
tapes=pickle.load(open('/home/anont/meme/.ff3/tapes.pkl','rb'))
allowed=json.load(open('/home/anont/meme/.ff3/allowed.json'))
tmints=set(allowed[bc][0] for bc in tapes)
o.write("taped mints %d\n"%len(tmints))
# fresh_snapshots
snap={}
nl=0; bad=0
for line in open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl'):
    nl+=1
    try: r=json.loads(line)
    except Exception: bad+=1; continue
    m=r.get('mint')
    if not m: continue
    if int(hashlib.md5(m.encode()).hexdigest(),16)%3==0: continue
    if m in tmints:
        snap.setdefault(m,[]).append(r)
o.write("snapshot lines %d bad %d ; taped mints with snapshots %d\n"%(nl,bad,len(snap)))
if snap:
    k=list(snap)[0]
    o.write("sample: %s\n"%json.dumps(snap[k][0])[:600])
    hx=sum(1 for m,v in snap.items() if v[0].get('has_x')); ht=sum(1 for m,v in snap.items() if v[0].get('has_tg'))
    hw=sum(1 for m,v in snap.items() if v[0].get('has_web'))
    o.write("has_x %d has_tg %d has_web %d\n"%(hx,ht,hw))
    rep=sorted(int(v[0].get('replies') or 0) for v in snap.values())
    o.write("replies p50 %s p90 %s\n"%(rep[len(rep)//2],rep[int(len(rep)*0.9)]))
    ts=[min(r['ts_ms'] for r in v) for v in snap.values()]
    o.write("snapshot ts range %s..%s\n"%(min(ts),max(ts)))
# grad_ohlcv overlap
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
ov=[m for (m,) in g.execute("select mint from ohlcv where status='ok'") if m in tmints]
o.write("grad_ohlcv ok mints overlapping taped: %d\n"%len(ov))
o.close()
