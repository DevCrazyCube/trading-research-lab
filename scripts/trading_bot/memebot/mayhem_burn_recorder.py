"""Records DexScreener price/liquidity/mcap at +23h/+24h/+25h/+26h for the tape's mayhem graduates and the non-mayhem
placebo graduates (MAYHEM_BURN_PREREGISTRATION.md). Runs ~8 hours, then exits. Read-only."""
import json,sqlite3,time,urllib.request,datetime,os
UA={'User-Agent':'Mozilla/5.0'}; OUT='research/midcap/mayhem_burn_obs.sqlite'
def get(u):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20).read())
    except Exception: return None
c=sqlite3.connect('file:research/midcap/birth_stream_forward_v3_20260908T1901.sqlite?mode=ro',uri=True); t=sqlite3.connect('file:research/midcap/tape_v3.sqlite?mode=ro',uri=True)
births={}; mayhem=set()
for slot,oj in c.execute("select slot,observation_json from create_observation where succeeded=1"):
    f=json.loads(oj)['fields']; births.setdefault(f['mint'],int(f['timestamp']))
    if f.get('is_mayhem_mode'): mayhem.add(f['mint'])
done={m for (m,) in t.execute("select distinct mint from event where name='CompleteEvent'")}
resid={r['mint']:r['resid_tokens'] for r in json.load(open('research/midcap/mayhem_burn_candidates.json'))}
coins=[(m,births[m],'mayhem' if m in mayhem else 'placebo',resid.get(m)) for m in done if m in births]
db=sqlite3.connect(OUT); db.execute("PRAGMA journal_mode=WAL")
db.execute("CREATE TABLE IF NOT EXISTS obs(mint TEXT, arm TEXT, born INT, resid REAL, mark INT, due INT, at INT, price REAL, liq REAL, mcap REAL, pool TEXT, PRIMARY KEY(mint,mark))"); db.commit()
print(f"tracking {len(coins)} graduates ({sum(1 for x in coins if x[2]=='mayhem')} mayhem / {sum(1 for x in coins if x[2]=='placebo')} placebo)",flush=True)
while True:
    now=time.time(); pending=0; n=0
    for m,born,arm,rs in coins:
        for h in (23,24,25,26):
            due=born+h*3600
            if now<due: pending+=1; continue
            if db.execute("SELECT 1 FROM obs WHERE mint=? AND mark=?",(m,h)).fetchone(): continue
            ps=get(f"https://api.dexscreener.com/tokens/v1/solana/{m}") or []; time.sleep(0.35)
            p=max(ps,key=lambda x:float((x.get('liquidity') or {}).get('usd') or 0)) if ps else None
            db.execute("INSERT OR IGNORE INTO obs VALUES(?,?,?,?,?,?,?,?,?,?,?)",(m,arm,born,rs,h,due,int(time.time()),float(p.get('priceUsd') or 0) if p else None,float((p.get('liquidity') or {}).get('usd') or 0) if p else None,float(p.get('marketCap') or 0) if p else None,p['pairAddress'] if p else None)); n+=1
        db.commit()
    print(json.dumps({"utc":datetime.datetime.now(datetime.UTC).strftime('%H:%M'),"recorded":n,"pending_marks":pending}),flush=True)
    if pending==0: print("ALL MARKS RECORDED",flush=True); break
    time.sleep(120)
