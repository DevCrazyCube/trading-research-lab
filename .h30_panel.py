import sqlite3,json,statistics,math,os,pickle
DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
c=sqlite3.connect(DB)
rows=c.execute("select mint,n_bars,first_ts,last_ts,bars_json from ohlcv where status='ok'").fetchall()
GLOBAL_MAX=max(r[3] for r in rows)
print('mints ok',len(rows),'global_max_last',GLOBAL_MAX)

H=900          # 15 min
STALE=1800     # allow exit up to 30m late (real bar, no lookahead: it is future)
recs=[]        # (mint, entry_ts, ret_or_None)
per_mint={}
censored=0
for mint,nb,ft,lt,bj in rows:
    bars=sorted(json.loads(bj), key=lambda b:b[0])
    if len(bars)<3: continue
    ts=[b[0] for b in bars]; op=[b[1] for b in bars]; cl=[b[4] for b in bars]
    # per-mint censoring horizon: the tape was pulled up to ~24h from first bar OR the global collection end
    horizon=min(ft+86400, GLOBAL_MAX)
    out=[]
    for i in range(len(bars)-1):
        # signal on bar i -> enter at NEXT REAL bar's OPEN
        e=i+1
        ets=ts[e]; ep=op[e]
        if ep is None or ep<=0: continue
        target=ets+H
        # exit = first REAL bar with ts >= target, use its OPEN
        j=None
        for k in range(e+1,len(bars)):
            if ts[k]>=target: j=k; break
        if j is None:
            # no bar >= entry+15m. censored if the tape simply ran out of collection window
            if target>horizon-60:
                censored+=1
                continue            # right-censored: EXCLUDE (not a death)
            out.append((ets,None,None))   # unresolved = tape died
        else:
            if ts[j]-target>STALE:
                # exit bar exists but very late -> still a real exit, mark stale
                out.append((ets,(op[j]-ep)/ep,'stale'))
            else:
                out.append((ets,(op[j]-ep)/ep,'ok'))
    if out:
        per_mint[mint]=out
        recs.extend((mint,a,b,c2) for a,b,c2 in out)
print('windows',len(recs),'mints',len(per_mint),'censored-excluded',censored)
res=[r for r in recs if r[2] is not None]
unres=[r for r in recs if r[2] is None]
print('resolved',len(res),'unresolved',len(unres),'resolution_rate',round(100*len(res)/len(recs),2))
stale=sum(1 for r in res if r[3]=='stale'); print('stale exits',stale)
g=sorted(r[2] for r in res)
def q(a,p):
    return a[min(len(a)-1,max(0,int(p*len(a))))]
print('GROSS resolved: mean %.4f median %.4f p1 %.4f p25 %.4f p75 %.4f p99 %.4f'%(
 statistics.mean(g),statistics.median(g),q(g,.01),q(g,.25),q(g,.75),q(g,.99)))
print('frac > +100%%: %.4f'%(sum(1 for x in g if x>1.0)/len(g)))
pickle.dump({'recs':recs,'per_mint':per_mint},open('/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad/panel.pkl','wb'))
