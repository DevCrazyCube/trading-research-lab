"""Evaluator for POSTGRAD_LP_PREREGISTRATION.md (Grok round-3 #1/#4). Paper only."""
import sqlite3,json,time,urllib.request,collections,statistics as st,bisect,random,math
UA={'User-Agent':'Mozilla/5.0'}
def get(u,tries=3):
    for i in range(tries):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25).read())
        except Exception: time.sleep(2+3*i)
    return None
c=sqlite3.connect('file:research/midcap/birth_stream_forward_v3_20260908T1901.sqlite?mode=ro',uri=True)
t=sqlite3.connect('file:research/midcap/tape_v3.sqlite?mode=ro',uri=True)
births={}
for slot,oj in c.execute("select slot,observation_json from create_observation where succeeded=1"):
    f=json.loads(oj)['fields']; births.setdefault(f['mint'],(slot,int(f['timestamp'])))
done={m:s for m,s in t.execute("select mint,min(slot) from event where name='CompleteEvent' group by mint")}
buyers=collections.defaultdict(set)
for m,u in t.execute("select mint,user from trade where is_buy=1"):
    if m in done: buyers[m].add(u)
grads=[m for m in done if m in births]
screen={m:((done[m]-births[m][0])*0.4>300 and len(buyers[m])>=40) for m in grads}
print(f"graduates {len(grads)} | ORGANIC screen pass {sum(screen.values())} | placebo {len(grads)-sum(screen.values())}",flush=True)
SOLUSD=(get("https://api.dexscreener.com/tokens/v1/solana/So11111111111111111111111111111111111111112") or [{}])[0].get('priceUsd'); SOLUSD=float(SOLUSD or 100)
POOL_USD=2*79*SOLUSD; SHARE=0.005; POS=POOL_USD*SHARE; LPFEE=0.002; RT=0.0114; TXF=2*105000/1e9*SOLUSD
rows=[]
for i,m in enumerate(sorted(grads,key=lambda m:births[m][0]),1):
    ds=get(f"https://api.dexscreener.com/tokens/v1/solana/{m}") or []; time.sleep(0.5)
    ps=[p for p in ds if p.get('dexId') in ('pumpswap','raydium') and p.get('pairCreatedAt')]
    if not ps: rows.append(dict(mint=m,org=screen[m],bars=None)); continue
    p=min(ps,key=lambda x:x['pairCreatedAt']); cr=p['pairCreatedAt']/1000
    o=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{p['pairAddress']}/ohlcv/minute?aggregate=1&limit=1000&before_timestamp={int(cr+16*3600)}&currency=usd"); time.sleep(2.1)
    b=sorted((o or {}).get('data',{}).get('attributes',{}).get('ohlcv_list') or [])
    rows.append(dict(mint=m,org=screen[m],created=cr,bars=b))
    if i%40==0: print(f"  fetched {i}/{len(grads)}",flush=True)
def lp(bars,cr,t_entry,hold_min):
    ts=[x[0] for x in bars]; i=bisect.bisect_left(ts,t_entry)
    if i>=len(bars) or ts[i]>t_entry+600: return None
    p0=bars[i][1]; j=bisect.bisect_left(ts,ts[i]+hold_min*60)
    if j>=len(bars): j=len(bars)-1
    if ts[j]<ts[i]+hold_min*60-600 and j==len(bars)-1: return None
    p1=bars[j][1]; r=p1/p0 if p0>0 else 0
    if r<=0: return -1.0
    il=2*math.sqrt(r)/(1+r)-1; hodl=(1+r)/2-1          # LP value vs holding 50/50: LP = hodl + il
    vol=sum(x[5] for x in bars[i:j]); fees=LPFEE*vol*SHARE
    net=(hodl+il)*POS+fees-RT*POS/2-TXF
    return net/POS
def cellA(hold): return {r['mint']:lp(r['bars'],r['created'],r['created']+600,hold) for r in rows if r['bars']}
def cellB():
    out={}
    for r in rows:
        if not r['bars']: continue
        b=r['bars']; hi=None; t_e=None
        for x in b:
            if x[0]>r['created']+3600: break
            hi=max(hi or x[2],x[2])
            if hi and x[4]<=0.8*hi: t_e=x[0]+60; break
        out[r['mint']]=lp(b,r['created'],t_e,60) if t_e else None
    return out
def summarize(cell,arm,drop=-1.0):
    vals=[];ses=[]
    for r in rows:
        if r['org']!=arm: continue
        if not r['bars']: vals.append(drop); ses.append(births[r['mint']][1]//1800); continue
        v=cell.get(r['mint']); vals.append(drop if v is None else v); ses.append(births[r['mint']][1]//1800)
    if not vals: return None
    by=collections.defaultdict(list)
    for v,s in zip(vals,ses): by[s].append(v)
    keys=list(by); rng=random.Random(3); ms=[]
    for _ in range(1500):
        sm=[x for k in (rng.choice(keys) for _ in keys) for x in by[k]]; ms.append(sum(sm)/len(sm))
    ms.sort(); vs=sorted(vals)
    return dict(n=len(vals),unres=sum(1 for r in rows if r['org']==arm and (not r['bars'] or cell.get(r['mint']) is None)),mean=st.fmean(vals),median=vs[len(vs)//2],win=sum(x>0 for x in vals)/len(vals),ci=(ms[37],ms[1462]))
mints=sorted(grads,key=lambda m:births[m][0]); cut=int(len(mints)*.6); ex=set(mints[:cut]); ho=set(mints[cut:])
def show(lab,cell,subset):
    for arm in (True,False):
        rows_bak=rows[:]
        sub=[r for r in rows if r['mint'] in subset]
        globals()['rows']=sub; s=summarize(cell,arm); globals()['rows']=rows_bak
        if s: print(f"  {lab:14} {'ORGANIC' if arm else 'placebo':8} n {s['n']:3d} unres {s['unres']:3d} mean {s['mean']*100:+7.1f}% median {s['median']*100:+7.1f}% win {s['win']*100:3.0f}% ci [{s['ci'][0]*100:+.1f},{s['ci'][1]*100:+.1f}]",flush=True)
print(f"\nSOL/USD {SOLUSD:.0f}  position ${POS:.0f} (0.5% of ~${POOL_USD:,.0f} pool)  LP fee {LPFEE*100:.2f}% of volume",flush=True)
print("EXPLORATION (60%), dropouts -100%:")
A45,A90,B=cellA(45),cellA(90),cellB()
show("A hold45",A45,ex); show("A hold90",A90,ex); show("B pullback60",B,ex)
print("HOLDOUT (single read) cell A-90:")
show("A hold90",A90,ho)
json.dump({'rows':[{k:v for k,v in r.items() if k!='bars'} for r in rows]},open('research/midcap/postgrad_lp_result.json','w'))
