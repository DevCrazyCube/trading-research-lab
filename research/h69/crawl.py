import json,time,datetime,sys,os,sqlite3
sys.path.insert(0,'/home/anont/meme/research/h69')
from gtlib import *
D='/home/anont/meme/research/h69'
db=sqlite3.connect(D+'/h69_ohlcv.sqlite')
db.execute('''create table if not exists t(
  mint text primary key, curve text, pool text, created text, created_ts int,
  reserve real, n_pools int, n_bars int, first_ts int, last_ts int, bars_json text, status text)''')
db.commit()
S=json.load(open(D+'/h69_sample.json'))['sample']
done={r[0] for r in db.execute("select mint from t where status in ('ok','nopool','nobars')")}
print('todo',len(S)-len(done),flush=True)
for i,x in enumerate(S):
    m=x['mint']
    if m in done: continue
    d=pools_for(m); time.sleep(3.0)
    if 'data' not in d:
        db.execute('insert or replace into t(mint,curve,status) values(?,?,?)',(m,x['curve'],'poolerr:'+str(list(d)))); db.commit(); continue
    ps=d.get('data') or []
    if not ps:
        db.execute('insert or replace into t(mint,curve,n_pools,status) values(?,?,0,?)',(m,x['curve'],'nopool')); db.commit()
        print('%3d %s NOPOOL'%(i,m[:12]),flush=True); continue
    # EARLIEST-created pool = the migration pool (outcome-independent choice)
    cand=[]
    for p in ps:
        a=p['attributes']; addr=p['id'].split('solana_')[-1]
        c=a.get('pool_created_at')
        if not c: continue
        ct=int(datetime.datetime.strptime(c,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.UTC).timestamp())
        try: res=float(a.get('reserve_in_usd') or 0)
        except: res=0.0
        cand.append((ct,-res,addr,c))
    if not cand:
        db.execute('insert or replace into t(mint,curve,n_pools,status) values(?,?,?,?)',(m,x['curve'],len(ps),'nocreated')); db.commit(); continue
    cand.sort()
    ct,negres,addr,c = cand[0]
    # post-migration window: 1000 minute bars starting at pool creation
    L,err=ohlcv_minute(addr, before_ts=ct+1000*60); time.sleep(3.0)
    if L is None:
        db.execute('insert or replace into t(mint,curve,pool,created,created_ts,reserve,n_pools,status) values(?,?,?,?,?,?,?,?)',
                   (m,x['curve'],addr,c,ct,-negres,len(ps),'ohlcverr:'+str(err))); db.commit()
        print('%3d %s OHLCVERR %s'%(i,m[:12],err),flush=True); continue
    L=sorted(L,key=lambda z:z[0])
    st='ok' if L else 'nobars'
    db.execute('insert or replace into t(mint,curve,pool,created,created_ts,reserve,n_pools,n_bars,first_ts,last_ts,bars_json,status) values(?,?,?,?,?,?,?,?,?,?,?,?)',
               (m,x['curve'],addr,c,ct,-negres,len(ps),len(L),L[0][0] if L else None,L[-1][0] if L else None,json.dumps(L),st))
    db.commit()
    print('%3d %s pool=%s age=%5.0fd bars=%4d %s'%(i,m[:12],addr[:10],(time.time()-ct)/86400,len(L),st),flush=True)
print('CRAWL COMPLETE',flush=True)
