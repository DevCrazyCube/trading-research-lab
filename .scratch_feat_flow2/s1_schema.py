import sqlite3, sys
out = open('/home/anont/meme/.scratch_feat_flow2/schema.txt','w')
def p(*a):
    print(*a, file=out)
for db in ['b11a_bodies','window_labels','b11a_trade_attribution']:
    path=f'/home/anont/meme/research/b11a/{db}.sqlite'
    c=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
    p('=====',db)
    for n,s in c.execute("select name,sql from sqlite_master where type in ('table','index')"):
        p(repr(s)[:1000])
    c.close()
path='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
c=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
p('===== grad_ohlcv')
for n,s in c.execute("select name,sql from sqlite_master"):
    p(repr(s)[:1000])
p('ohlcv count', c.execute('select count(*) from ohlcv').fetchone())
c.close()
out.close()
