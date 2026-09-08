import json, hashlib, collections
OUT=open('/home/anont/meme/.scratch_att2/p2.txt','w')
def P(*a): print(*a, file=OUT)
def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

ev=[]; meta=[]
for line in open('/home/anont/meme/research/midcap/attention.jsonl'):
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    (ev if d.get('ev')=='EVENT' else meta).append(d)
P('meta sample keys', collections.Counter(tuple(sorted(m.keys())) for m in meta).most_common(5))
P('meta[0]', json.dumps(meta[0])[:800])
P('meta[-1]', json.dumps(meta[-1])[:800])
P('meta ev values', collections.Counter(m.get('ev') for m in meta))
tss=[m.get('ts_ms') for m in meta if m.get('ts_ms')]
if tss: P('meta ts range',min(tss),max(tss), (max(tss)-min(tss))/3.6e6,'hours')

# fresh snapshots
snap_mints=set(); n=0
per=collections.defaultdict(int)
tsmin=None; tsmax=None
for line in open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl'):
    line=line.strip()
    if not line: continue
    try: d=json.loads(line)
    except Exception: continue
    if 'mint' not in d: continue
    n+=1
    m=d['mint']; snap_mints.add(m); per[m]+=1
    t=d.get('ts_ms')
    if t:
        tsmin=t if tsmin is None or t<tsmin else tsmin
        tsmax=t if tsmax is None or t>tsmax else tsmax
P('snapshot rows',n,'unique mints',len(snap_mints))
P('snap ts range',tsmin,tsmax,(tsmax-tsmin)/3.6e6 if tsmin else None,'hours')
cnt=sorted(per.values())
P('per-mint snapshot count: min',cnt[0],'p25',cnt[len(cnt)//4],'med',cnt[len(cnt)//2],'p75',cnt[3*len(cnt)//4],'max',cnt[-1])

evm=set(r['mint'] for r in ev); ctm=set(r['control'] for r in ev if r.get('control'))
P('attention event mints in snapshots', len(evm & snap_mints), 'of', len(evm))
P('attention control mints in snapshots', len(ctm & snap_mints), 'of', len(ctm))
ev12=set(m for m in evm if h(m) in (1,2))
P('h12 event mints', len(ev12), 'of which in snapshots', len(ev12 & snap_mints))
P('snap counts for h12 event mints', sorted(per[m] for m in (ev12&snap_mints)))
ct12=set(m for m in ctm if h(m) in (1,2))
P('h12 control mints', len(ct12), 'in snapshots', len(ct12&snap_mints))
P('snap counts for h12 control mints', sorted(per[m] for m in (ct12&snap_mints)))
OUT.close()
