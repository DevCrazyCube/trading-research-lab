import sqlite3, os, json
for p in ['/home/anont/meme/research/midcap/grad_ohlcv.sqlite',
          '/home/anont/meme/research/b11a/window_labels.sqlite']:
    c = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
    print('==', p, os.path.getsize(p))
    for (n, s) in c.execute("select name,sql from sqlite_master where type='table'"):
        print(' TBL', n)
        print('  ', s)
    c.close()
print('files:', os.listdir('/home/anont/meme/research/midcap'))
c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
print(c.execute('select count(*), sum(n_bars) from ohlcv').fetchone())
print(c.execute('select status, count(*) from ohlcv group by 1').fetchall())
r = c.execute('select mint,pool,n_bars,first_ts,last_ts,substr(bars_json,1,300),status from ohlcv where n_bars>10 limit 2').fetchall()
for x in r:
    print(x)
c.close()
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
print(w.execute('select count(*), count(distinct creator), sum(complete) from window_label').fetchone())
print(w.execute('select * from window_label limit 3').fetchall())
w.close()
try:
    import numpy
    print('numpy', numpy.__version__)
except Exception as e:
    print('no numpy', e)
