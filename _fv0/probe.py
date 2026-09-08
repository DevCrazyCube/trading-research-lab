import sqlite3, json, hashlib, statistics, sys
DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
c=sqlite3.connect(DB)
print(c.execute("select name from sqlite_master where type='table'").fetchall())
cur=c.execute("select * from ohlcv limit 1")
print([d[0] for d in cur.description])
print(c.execute("select count(*), sum(n_bars) from ohlcv").fetchone())
print(c.execute("select status, count(*) from ohlcv group by 1").fetchall())
rows=c.execute("select mint,pool,n_bars,first_ts,last_ts,bars_json,status from ohlcv limit 3").fetchall()
for r in rows:
    b=json.loads(r[5])
    print(r[0], r[2], r[3], r[4], r[6], 'len',len(b))
    print(' first3', b[:3])
    print(' last3', b[-3:])
# distribution of h
hs={0:0,1:0,2:0}
nb={0:0,1:0,2:0}
gaps={}
zerovol=0; tot=0
for mint,nbars,bj in c.execute("select mint,n_bars,bars_json from ohlcv"):
    h=int(hashlib.md5(mint.encode()).hexdigest(),16)%3
    hs[h]+=1; nb[h]+=nbars or 0
    if h==0: continue
    b=json.loads(bj)
    b.sort(key=lambda x:x[0])
    for k in range(1,len(b)):
        d=(b[k][0]-b[k-1][0])
        gaps[d]=gaps.get(d,0)+1
    for x in b:
        tot+=1
        if x[5]==0: zerovol+=1
print('h counts',hs, 'bars',nb)
print('zero vol bars', zerovol, 'of', tot)
gg=sorted(gaps.items(), key=lambda kv:-kv[1])[:15]
print('top gaps (sec)', gg)
print('ts units sample', rows[0][3], rows[0][4])
