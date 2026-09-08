import sqlite3, json
OUT = open('/home/anont/meme/.scratch_fc/p3.txt','w')
def P(*a): print(*a, file=OUT)
c = sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro', uri=True)
for name, sql in c.execute("select name,sql from sqlite_master"):
    P('OBJ', name); P('   ', (sql or '').replace('\n',' ')[:800])
for t in ['instruction','reserve_observation']:
    try:
        P(t, 'sample')
        cur = c.execute('select * from %s limit 2'%t)
        cols=[d[0] for d in cur.description]; P(' cols',cols)
        for r in cur.fetchall(): P('  ', str(r)[:900])
    except Exception as e: P(' err',e)
c.close()
OUT.close()
