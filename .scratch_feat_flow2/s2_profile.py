import sqlite3, hashlib, json
out=open('/home/anont/meme/.scratch_feat_flow2/profile.txt','w')
def p(*a): print(*a,file=out)

TA='/home/anont/meme/research/b11a/b11a_trade_attribution.sqlite'
c=sqlite3.connect('file:'+TA+'?mode=ro',uri=True)
p('rows', c.execute('select count(*) from trade_attribution').fetchone())
p('distinct mint', c.execute('select count(distinct mint) from trade_attribution').fetchone())
p('nulls mint', c.execute('select count(*) from trade_attribution where mint is null').fetchone())
p('nulls trader', c.execute('select count(*) from trade_attribution where trader is null').fetchone())
p('nulls blocktime', c.execute('select count(*) from trade_attribution where blocktime is null').fetchone())
p('bt range', c.execute('select min(blocktime),max(blocktime) from trade_attribution').fetchone())
p('slot range', c.execute('select min(slot),max(slot) from trade_attribution').fetchone())
p('is_buy dist', c.execute('select is_buy,count(*) from trade_attribution group by 1').fetchall())
p('idl_name dist', c.execute('select idl_name,count(*) from trade_attribution group by 1 order by 2 desc limit 20').fetchall())
p('sample', c.execute('select * from trade_attribution limit 3').fetchall())
p('cols', [d[0] for d in c.execute('select * from trade_attribution limit 1').description])
p('sol_amount stats', c.execute('select min(sol_amount),max(sol_amount),avg(sol_amount) from trade_attribution').fetchone())
c.close()

# grad_ohlcv mints
g=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=g.execute("select mint,n_bars,status,first_ts,last_ts from ohlcv").fetchall()
p('grad rows',len(rows))
from collections import Counter
p('status',Counter(r[2] for r in rows))
p('with bars', sum(1 for r in rows if r[1] and r[1]>0))
g.close()
out.close()
