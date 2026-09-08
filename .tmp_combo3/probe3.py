import sqlite3, json, hashlib
R='/home/anont/meme/research/'
OUT=open('/home/anont/meme/.tmp_combo3/out_probe3.txt','w')
def p(*a): print(*a, file=OUT); OUT.flush()
db=sqlite3.connect(R+'b11a/b11a_bodies.sqlite')
p('tables', db.execute("select name from sqlite_master where type='table'").fetchall())
for t in [r[0] for r in db.execute("select name from sqlite_master where type='table'")]:
    try:
        p('--',t,[d[1] for d in db.execute('PRAGMA table_info(%s)'%t)])
        p('   n=', db.execute('select count(*) from %s'%t).fetchone()[0])
    except Exception as e: p('  err',e)
p('indexes', db.execute("select name,tbl_name,sql from sqlite_master where type='index'").fetchall()[:40])
try:
    r=db.execute('select * from reserve_observation limit 2').fetchall()
    p('ro sample', r)
except Exception as e: p('ro err', e)
try:
    r=db.execute('select * from instruction limit 1').fetchall()
    p('ins sample', str(r)[:1200])
except Exception as e: p('ins err', e)
db2=sqlite3.connect(R+'b11a/window_labels.sqlite')
oh=sqlite3.connect(R+'midcap/grad_ohlcv.sqlite')
ohm=[m for (m,) in oh.execute('select mint from ohlcv where n_bars>0')]
ohm=[m for m in ohm if int(hashlib.md5(m.encode()).hexdigest(),16)%3!=0]
q=','.join('?'*len(ohm))
p('complete dist for ohlcv mints', db2.execute('select complete,count(*) from window_label where mint in (%s) group by complete'%q, ohm).fetchall())
p('creator dupes', db2.execute('select count(distinct creator), count(*) from window_label where mint in (%s)'%q, ohm).fetchone())
OUT.close()
