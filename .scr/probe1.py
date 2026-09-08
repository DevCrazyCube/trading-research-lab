import sqlite3, json, hashlib, os
D='/home/anont/meme/research/'
c=sqlite3.connect('file:'+D+'midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
print(c.execute("select name,sql from sqlite_master where type='table'").fetchall())
print('rows', c.execute("select count(*) from ohlcv").fetchone())
r=c.execute("select mint,pool,n_bars,first_ts,last_ts,status,length(bars_json) from ohlcv limit 3").fetchall()
for x in r: print(x[:6], x[6])
m,b=c.execute("select mint,bars_json from ohlcv where n_bars>50 limit 1").fetchone()
bb=json.loads(b)
print('sample bars', bb[:3], '...', bb[-3:])
print('nbars',len(bb))
# holdout accounting WITHOUT reading h==0 content: only count
tot=0; h12=0
for (mint,nb) in c.execute("select mint,n_bars from ohlcv").fetchall():
    tot+=1
    h=int(hashlib.md5(mint.encode()).hexdigest(),16)%3
    if h in (1,2): h12+=1
print('total mints',tot,'h12',h12)

c2=sqlite3.connect('file:'+D+'b11a/window_labels.sqlite?mode=ro',uri=True)
print(c2.execute("select name,sql from sqlite_master where type='table'").fetchall())
print('wl rows',c2.execute("select count(*),sum(complete) from window_label").fetchone())
