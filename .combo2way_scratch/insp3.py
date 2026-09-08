import sqlite3, json, hashlib
ROOT='/home/anont/meme'
c=sqlite3.connect('file:%s/research/b11a/b11a_bodies.sqlite?mode=ro'%ROOT,uri=True)
for (n,s) in c.execute("select name,sql from sqlite_master where type in ('table','index')"):
    print('---',n); print(s)
for t in ('instruction','reserve_observation'):
    try:
        print(t,'count',c.execute('select count(*) from %s'%t).fetchone())
        cur=c.execute('select * from %s limit 2'%t)
        print([d[0] for d in cur.description])
        for r in cur.fetchall(): print(str(r)[:500])
    except Exception as e: print(t,'ERR',e)
