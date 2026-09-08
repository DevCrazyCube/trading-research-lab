import json, hashlib, collections, statistics as st
OUT=open('/home/anont/meme/.scratch_att2/p3.txt','w')
def P(*a): print(*a, file=OUT)
def h(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

ev=[]; tk=[]
for line in open('/home/anont/meme/research/midcap/attention.jsonl'):
    line=line.strip()
    if not line: continue
    d=json.loads(line)
    if d.get('ev')=='EVENT': ev.append(d)
    elif d.get('ev')=='TICK': tk.append(d)
P('events',len(ev),'ticks',len(tk))

# group ticks by (mint,t0)
g=collections.defaultdict(list)
for t in tk:
    g[(t['mint'],t['t0'])].append(t)
P('tick series (mint,t0)',len(g))
P('unique tick mints',len(set(t['mint'] for t in tk)))
lens=sorted(len(v) for v in g.values())
P('series lengths min/p25/med/p75/max',lens[0],lens[len(lens)//4],lens[len(lens)//2],lens[3*len(lens)//4],lens[-1])
# cadence + horizon
cad=[]; hor=[]
for k,v in g.items():
    v.sort(key=lambda x:x['ts_ms'])
    for a,b in zip(v,v[1:]): cad.append((b['ts_ms']-a['ts_ms'])/60000.0)
    hor.append((v[-1]['ts_ms']-k[1])/60000.0)
cad.sort(); hor.sort()
P('cadence min (minutes) p10/med/p90',round(cad[len(cad)//10],3),round(cad[len(cad)//2],3),round(cad[9*len(cad)//10],3))
P('horizon minutes min/med/max',round(hor[0],1),round(hor[len(hor)//2],1),round(hor[-1],1))
# missing px?
P('ticks with px None',sum(1 for t in tk if t.get('px') is None))
P('ticks with ctrl_px None',sum(1 for t in tk if t.get('ctrl_px') is None))
P('ticks with ctrl None',sum(1 for t in tk if not t.get('ctrl')))
# per series: does ctrl stay constant?
nc=0
for k,v in g.items():
    if len(set(x.get('ctrl') for x in v))>1: nc+=1
P('series with changing ctrl',nc)
# h12 series
s12=[k for k in g if h(k[0]) in (1,2)]
P('series with h(mint) in 1,2',len(s12))
P('  h=1',sum(1 for k in s12 if h(k[0])==1),' h=2',sum(1 for k in s12 if h(k[0])==2))
ctl12=sum(1 for k in s12 if h(g[k][0].get('ctrl','x')) in (1,2))
P('  of those, ctrl also h12',ctl12)
# how many series have >=15 min of ticks
for m in (5,10,15,30,60,120):
    P(f'  h12 series with horizon >= {m}m', sum(1 for k in s12 if (g[k][-1]['ts_ms']-k[1])/60000.0>=m))
# event->tick join
evk=set((e['mint'],e['ts_ms']) for e in ev)
P('event keys that appear as tick t0 keys',len(evk & set(g.keys())))
P('event mints with any tick series',len(set(e['mint'] for e in ev) & set(t['mint'] for t in tk)))
# sample a series
k=s12[0]; v=g[k]
P('sample series',k[0][:8],[(round((x['ts_ms']-k[1])/60000.,1),x['px'],x['ctrl_px']) for x in v[:12]])
OUT.close()
