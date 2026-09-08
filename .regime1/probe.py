import sqlite3, json, os, hashlib
p='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
print('size', os.path.getsize(p))
c=sqlite3.connect('file:%s?mode=ro'%p, uri=True)
print([r[0] for r in c.execute("select name from sqlite_master where type='table'")])
print(c.execute('select count(*), sum(n_bars) from ohlcv').fetchone())
print(c.execute('select status, count(*) from ohlcv group by status').fetchall())
r=c.execute('select mint,pool,n_bars,first_ts,last_ts,status,bars_json from ohlcv where n_bars>50 limit 1').fetchone()
print(r[:6])
b=json.loads(r[6])
print('nbars', len(b))
print('head', b[:3])
print('tail', b[-3:])
# holdout distribution
rows=c.execute('select mint,n_bars from ohlcv').fetchall()
from collections import Counter
cnt=Counter(int(hashlib.md5(m.encode()).hexdigest(),16)%3 for m,_ in rows)
print('h dist', dict(cnt))
nb=[n for m,n in rows if int(hashlib.md5(m.encode()).hexdigest(),16)%3 in (1,2)]
nb.sort()
print('allowed mints', len(nb), 'bars', sum(nb))
print('nbars quantiles', nb[0], nb[len(nb)//4], nb[len(nb)//2], nb[3*len(nb)//4], nb[-1])
try:
    import numpy; print('numpy', numpy.__version__)
except Exception as e:
    print('no numpy', e)
