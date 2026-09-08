import json, hashlib, collections, statistics as st
OUT=open('/home/anont/meme/.scratch_att2/p5.txt','w')
def P(*a): print(*a, file=OUT)
def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
tk=[]
for line in open('/home/anont/meme/research/midcap/attention.jsonl'):
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    if d.get('ev')=='TICK': tk.append(d)
g=collections.defaultdict(list)
for t in tk: g[(t['mint'],t['t0'])].append(t)
for v in g.values(): v.sort(key=lambda x:x['ts_ms'])
sr=[]; liqmov=0; liqconst=0
allsame=0
for (m,t0),v in g.items():
    if h(m) not in (1,2): continue
    if len(v)<5: continue
    same=sum(1 for a,b in zip(v,v[1:]) if a['px']==b['px'])
    sr.append(same/(len(v)-1))
    if len(set(x.get('liq') for x in v))>1: liqmov+=1
    else: liqconst+=1
    if same==len(v)-1: allsame+=1
sr.sort()
P('n series',len(sr))
P('fraction of consecutive ticks with UNCHANGED px: min/p25/med/p75/max',[round(sr[i],3) for i in (0,len(sr)//4,len(sr)//2,3*len(sr)//4,-1)])
P('series with px NEVER changing (fully dead/stale):',allsame)
P('series with liq varying',liqmov,'liq constant',liqconst)
# raw event-window returns using px path
def ret(v,a,b):
    pa=None;pb=None
    for x in v:
        dt=(x['ts_ms']-v[0]['t0'])/60000.
        if pa is None and dt>=a: pa=x['px']
        if dt<=b: pb=x['px']
    return (pb/pa-1) if pa and pb else None
for H in (5,15,30,60,120):
    rs=[];cs=[]
    for (m,t0),v in g.items():
        if h(m) not in (1,2): continue
        avail=(max(x['ts_ms'] for x in v)-t0)/60000.
        if avail< H: continue
        p0=v[0]['px'];
        pn=[x['px'] for x in v if (x['ts_ms']-t0)/60000.<=H][-1]
        rs.append(pn/p0-1)
        c0=v[0].get('ctrl_px'); cl=[x.get('ctrl_px') for x in v if (x['ts_ms']-t0)/60000.<=H and x.get('ctrl_px')]
        if c0 and cl: cs.append(cl[-1]/c0-1)
    rs.sort(); cs.sort()
    P(f'H={H}: EVENT n={len(rs)} mean={st.mean(rs)*100:.2f}% med={rs[len(rs)//2]*100:.2f}% | CTRL n={len(cs)} mean={st.mean(cs)*100:.2f}% med={cs[len(cs)//2]*100:.2f}%')
OUT.close()
