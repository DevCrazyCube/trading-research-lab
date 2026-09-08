import sqlite3, json, sys, os
OUT = open('/home/anont/meme/.scratch_fc/p1.txt','w')
def P(*a): print(*a, file=OUT)

def conn(p):
    return sqlite3.connect('file:%s?mode=ro' % p, uri=True)

for p in ['/home/anont/meme/research/midcap/grad_ohlcv.sqlite',
          '/home/anont/meme/research/b11a/window_labels.sqlite']:
    P('=====', p)
    try:
        c = conn(p)
        for name, sql in c.execute("select name,sql from sqlite_master where type='table'"):
            P(' TABLE', name)
            P('  ', (sql or '').replace('\n',' ')[:600])
            try:
                n = c.execute('select count(*) from "%s"' % name).fetchone()[0]
                P('   rows=', n)
            except Exception as e:
                P('   count err', e)
        c.close()
    except Exception as e:
        P(' ERR', e)

c = conn('/home/anont/meme/research/midcap/grad_ohlcv.sqlite')
r = c.execute("select mint,pool,n_bars,first_ts,last_ts,status,substr(bars_json,1,300) from ohlcv limit 3").fetchall()
for x in r: P('OHLCV SAMPLE', x)
P('status dist', c.execute("select status,count(*) from ohlcv group by status").fetchall())
P('nbars', c.execute("select min(n_bars),max(n_bars),avg(n_bars),count(*) from ohlcv").fetchone())
c.close()

c = conn('/home/anont/meme/research/b11a/window_labels.sqlite')
P('WL SAMPLE', c.execute("select * from window_label limit 3").fetchall())
P('WL count', c.execute("select count(*), sum(complete) from window_label").fetchone())
P('WL creators', c.execute("select count(distinct creator) from window_label").fetchone())
P('WL bt range', c.execute("select min(block_time),max(block_time) from window_label").fetchone())
P('WL cols', [d[0] for d in c.execute("select * from window_label limit 1").description])
c.close()
OUT.close()
