"""Mechanical read of the prospective cohort test (prereg 91b47ac2 + addenda). Computes original cells (k-th BUY, N in {2,24}h)
and coincidence cells C(K,W,N) x {buy, position} from a watcher DB; entry at next bar OPEN after avail_ns; fixed exits;
toll by venue; dropouts; mint- and session-clustered bootstrap. Bars fetched from GeckoTerminal and cached. Paper only.
Usage: python -m scripts.trading_bot.memebot.cohort_prospective_eval <db> [--dev]  (--dev labels output DEVELOPMENT_ONLY)"""
import sqlite3,json,time,urllib.request,collections,statistics as st,bisect,random,sys,zlib,datetime
UA={'User-Agent':'Mozilla/5.0'}
def get(u,tries=3):
    for i in range(tries):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25).read())
        except Exception: time.sleep(2+2*i)
    return None
class Bars:
    def __init__(self,db): self.db=db; db.execute("CREATE TABLE IF NOT EXISTS barcache(pool TEXT PRIMARY KEY, fetched INT, zjson BLOB)"); db.commit()
    def bars(self,pool,since):
        r=self.db.execute("SELECT fetched,zjson FROM barcache WHERE pool=?",(pool,)).fetchone()
        if r and time.time()-r[0]<1800: return json.loads(zlib.decompress(r[1]))
        tf='minute' if time.time()-since<3*86400 else 'hour'; out={}; before=int(time.time())
        for _ in range(3):
            o=get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/{tf}?aggregate=1&limit=1000&before_timestamp={before}&currency=usd"); time.sleep(2.1)
            b=(o or {}).get('data',{}).get('attributes',{}).get('ohlcv_list') or []
            if not b: break
            for x in b: out[x[0]]=x
            before=min(x[0] for x in b)-1
            if len(b)<1000 or before<since: break
        bl=sorted(out.values()); self.db.execute("INSERT OR REPLACE INTO barcache VALUES(?,?,?)",(pool,int(time.time()),zlib.compress(json.dumps(bl).encode()))); self.db.commit(); return bl
def load(dbpath):
    c=sqlite3.connect(dbpath,timeout=60)
    ep=c.execute("SELECT start_ns FROM epoch").fetchone() if c.execute("SELECT name FROM sqlite_master WHERE name='epoch'").fetchone() else None
    cols=[r[1] for r in c.execute("pragma table_info(ev)")]
    tcol="avail_ns" if "avail_ns" in cols else "recv_ns"
    ev=c.execute(f"SELECT wallet,arm,sig,ts,{tcol},mint,raw_delta,sol_lamports,usdc_delta FROM ev").fetchall()
    fs={r[0]:r[1:] for r in c.execute("SELECT mint,oldest_pair_created,oldest_pair,largest_pool FROM firstsight" if 'oldest_pair_created' in [r[1] for r in c.execute("pragma table_info(firstsight)")] else "SELECT mint,pair_created,pool,pool FROM firstsight")}
    return c,(ep[0] if ep else None),ev,fs
def events(ev,fs,arm,kind):
    """per mint: sorted list of (avail_s, wallet) positioning events for the arm"""
    per=collections.defaultdict(dict)
    for w,a,sig,ts,av,m,d,lam,usdc in ev:
        if a!=arm or d<=0: continue
        paid=(usdc is not None and usdc<=-1.0) or (lam is not None and lam<=-1_000_000)
        if kind=='buy' and not paid: continue
        t=av/1e9
        if w not in per[m] or t<per[m][w]: per[m][w]=t
    return {m:sorted((t,w) for w,t in d.items()) for m,d in per.items()}
def signals(per,fs,K,W,N):
    out=[]
    for m,lst in per.items():
        if len(lst)<K: continue
        for i in range(K-1,len(lst)):
            t0=lst[i-K+1][0]; tk=lst[i][0]
            if W is not None and tk-t0>W*60: continue
            cr=(fs.get(m) or (None,))[0]; age=None if not cr else (tk-cr)/3600
            if N is not None and age is not None and age>N: continue
            if N is not None and age is None and W is None: pass
            out.append((m,tk,age)); break
    return out
def evaluate(sigs,fs,bars,horizons=(6,24,72,168),drop=-1.0):
    per_mint=[];sess=[];res=collections.defaultdict(list);unres=collections.Counter();n=0
    for m,t,age in sigs:
        pool=(fs.get(m) or (None,None,None))[2]; cr=(fs.get(m) or (None,))[0]
        if not pool: 
            for h in horizons: res[h].append(None)
            per_mint.append(m); sess.append(int(t//21600)); continue
        b=bars.bars(pool,cr or t-86400); ts=[x[0] for x in b]; i=bisect.bisect_right(ts,t)
        if i>=len(b):
            for h in horizons: res[h].append(None)
            per_mint.append(m); sess.append(int(t//21600)); continue
        p0=b[i][1]; toll=0.0248 if (cr is None) else 0.0114; n+=1
        for h in horizons:
            j=bisect.bisect_left(ts,t+h*3600)
            ok=j<len(b) and ts[j]<=t+h*3600+max(3600,0.25*h*3600)
            res[h].append((b[j][1]/p0)*(1-toll)-1 if ok else None)
        per_mint.append(m); sess.append(int(t//21600))
    out={}
    for h in horizons:
        v=res[h]; unr=sum(1 for x in v if x is None)
        for dr in (-0.3,-0.5,-1.0):
            vv=[dr if x is None else x for x in v]
            if not vv: continue
            by=collections.defaultdict(list)
            for x,s in zip(vv,sess): by[s].append(x)
            keys=list(by); rng=random.Random(1); ms=[]
            for _ in range(1000):
                sm=[y for k in (rng.choice(keys) for _ in keys) for y in by[k]]; ms.append(sum(sm)/len(sm))
            ms.sort(); vs=sorted(vv)
            out[(h,dr)]=dict(n=len(vv),unres=unr,mean=st.fmean(vv),median=vs[len(vs)//2],win=sum(x>0 for x in vv)/len(vv),ci=(ms[25],ms[974]))
    return out,n
def main():
    dbpath=sys.argv[1]; dev='--dev' in sys.argv
    c,epoch,ev,fs=load(dbpath); bars=Bars(c)
    print(("STATUS: DEVELOPMENT_ONLY (v1 watcher / pre-epoch data)" if dev else f"STATUS: PROSPECTIVE READ, epoch {datetime.datetime.fromtimestamp(epoch/1e9,datetime.UTC).isoformat() if epoch else 'n/a'}"),flush=True)
    print(f"events {len(ev)} | mints with firstsight {len(fs)}",flush=True)
    cells=[('orig',K,None,N,'buy') for K in (2,3) for N in (2,24)]+[('coinc',K,W,N,kind) for K in (2,3) for W in (30,90) for N in (2,6) for kind in ('buy','position')]
    for arm in ('board','control'):
        print(f"\n=== {arm} ===",flush=True)
        for fam,K,W,N,kind in cells:
            per=events(ev,fs,arm,kind); sg=signals(per,fs,K,W,N)
            if not sg: print(f"  {fam} K={K} W={W} N={N}h {kind:8}: 0 signals"); continue
            out,priced=evaluate(sg,fs,bars)
            r=out.get((72,-0.5)); r7=out.get((168,-0.5))
            print(f"  {fam} K={K} W={W} N={N}h {kind:8}: signals {len(sg):3d} priced {priced:3d} | 72h@-50%: mean {r['mean']*100:+6.1f}% med {r['median']*100:+6.1f}% win {r['win']*100:3.0f}% ci[{r['ci'][0]*100:+.1f},{r['ci'][1]*100:+.1f}] unres {r['unres']} | 7d: mean {r7['mean']*100:+6.1f}% med {r7['median']*100:+6.1f}%",flush=True)
if __name__=='__main__': main()
