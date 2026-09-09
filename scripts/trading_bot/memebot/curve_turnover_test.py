"""Evaluator for CURVE_TURNOVER_PREREGISTRATION.md. Paper only."""
import sqlite3,json,time,urllib.request,collections,statistics as st,bisect,random
UA={'User-Agent':'Mozilla/5.0'}
def get(u,tries=5):
    for i in range(tries):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25).read())
        except urllib.error.HTTPError as e:
            time.sleep(20 if e.code==429 else 3+3*i)      # back off hard on rate limit; shared budget with live watchers
        except Exception: time.sleep(3+3*i)
    return None
c=sqlite3.connect('file:research/midcap/birth_stream_forward_v3_20260908T1901.sqlite?mode=ro',uri=True); t=sqlite3.connect('file:research/midcap/tape_v3.sqlite?mode=ro',uri=True)
births={}
for slot,oj in c.execute("select slot,observation_json from create_observation where succeeded=1"):
    f=json.loads(oj)['fields']; births.setdefault(f['mint'],(slot,int(f['timestamp'])))
done={m:s for m,s in t.execute("select mint,min(slot) from event where name='CompleteEvent' group by mint")}
turn={}
for m,bs,ss,rs in t.execute("select mint, sum(case when is_buy=1 then sol_amount else 0 end), sum(case when is_buy=0 then sol_amount else 0 end), max(rsol) from trade where mint in (select mint from event where name='CompleteEvent') group by mint"):
    if m in births: turn[m]=(bs+ss)/max(rs or 85e9,1)
rows=[r for r in json.load(open('research/midcap/postgrad_lp_result.json'))['rows'] if r.get('created') and r['mint'] in turn]
print(f"graduates with turnover + pool: {len(rows)} | turnover q25/med/q75: {sorted(turn[r['mint']] for r in rows)[len(rows)//4]:.2f} / {st.median(turn[r['mint']] for r in rows):.2f} / {sorted(turn[r['mint']] for r in rows)[3*len(rows)//4]:.2f}",flush=True)
res={}
for i,r in enumerate(rows,1):
    ds=get(f"https://api.dexscreener.com/tokens/v1/solana/{r['mint']}") or []; time.sleep(0.4)
    ps=[p for p in ds if p.get('dexId') in ('pumpswap','raydium') and p.get('pairCreatedAt')]
    if not ps: res[r['mint']]=None; continue
    p=min(ps,key=lambda x:x['pairCreatedAt']); cr=p['pairCreatedAt']/1000
    o=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{p['pairAddress']}/ohlcv/minute?aggregate=1&limit=90&before_timestamp={int(cr+5400)}&currency=usd"); time.sleep(5.0)
    b=sorted((o or {}).get('data',{}).get('attributes',{}).get('ohlcv_list') or [])
    if not b: res[r['mint']]=None; continue
    ts=[x[0] for x in b]; i0=bisect.bisect_right(ts,cr)
    if i0>=len(b) or not b[i0][1]: res[r['mint']]=None; continue
    p0=b[i0][1]; out={}
    for h in (15,60):
        j=bisect.bisect_left(ts,ts[i0]+h*60); out[h]=(b[j][1]/p0)*(1-0.0114)-1 if (j<len(b) and ts[j]<=ts[i0]+h*60+600 and b[j][1]) else None
    res[r['mint']]=out
    if i%60==0: print(f"  {i}/{len(rows)}",flush=True)
mints=sorted(res,key=lambda m:done[m]); cut=int(len(mints)*.6); ex,ho=mints[:cut],mints[cut:]
def cellstats(ms,h,drop=-1.0):
    v=[(drop if (res[m] is None or res[m].get(h) is None) else res[m][h]) for m in ms]; ses=[births[m][1]//1800 for m in ms]
    if not v: return None
    by=collections.defaultdict(list)
    for x,s in zip(v,ses): by[s].append(x)
    keys=list(by); rng=random.Random(4); ms_=[]
    for _ in range(1500):
        sm=[y for k in (rng.choice(keys) for _ in keys) for y in by[k]]; ms_.append(sum(sm)/len(sm))
    ms_.sort(); vs=sorted(v); return dict(n=len(v),mean=st.fmean(v),median=vs[len(vs)//2],win=sum(x>0 for x in v)/len(v),ci=(ms_[37],ms_[1462]),unres=sum(1 for m in ms if res[m] is None or res[m].get(h) is None))
def quart(ms,key):
    s=sorted(ms,key=key); q=len(s)//4; return {'Q1':s[:q],'Q2':s[q:2*q],'Q3':s[2*q:3*q],'Q4':s[3*q:]}
print("\nEXPLORATION (60%), dropouts -100%, entry = first bar open after pool creation:")
qs=quart(ex,lambda m:turn[m]); rng=random.Random(9); sh=dict(zip(ex,rng.sample([turn[m] for m in ex],len(ex)))); qp=quart(ex,lambda m:sh[m])
for h in (15,60):
    for q in ('Q1','Q2','Q3','Q4'):
        s=cellstats(qs[q],h); print(f"  +{h:2}m {q} (turnover {'low' if q=='Q1' else 'high' if q=='Q4' else 'mid'}): n {s['n']:3d} mean {s['mean']*100:+6.1f}% median {s['median']*100:+6.1f}% win {s['win']*100:3.0f}% ci [{s['ci'][0]*100:+.1f},{s['ci'][1]*100:+.1f}] unres {s['unres']}")
    sp=cellstats(qp['Q1'],h); print(f"  +{h:2}m PLACEBO Q1 (shuffled): mean {sp['mean']*100:+6.1f}% median {sp['median']*100:+6.1f}%")
hq=quart(ho,lambda m:turn[m]); s=cellstats(hq['Q1'],60); s50=cellstats(hq['Q1'],60,drop=-0.5)
print(f"\nHOLDOUT (single read) Q1 @ +60m: n {s['n']} mean {s['mean']*100:+.2f}% median {s['median']*100:+.2f}% win {s['win']*100:.0f}% ci [{s['ci'][0]*100:+.1f},{s['ci'][1]*100:+.1f}]  at -50% dropout mean {s50['mean']*100:+.2f}%")
json.dump({'turnover':{m:turn[m] for m in res},'returns':res},open('research/midcap/curve_turnover_result.json','w'),default=str)
