import sqlite3, json, time
O='/home/anont/meme/.scr2/probe2.out'; o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
c=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
for r in c.execute("select name,sql from sqlite_master where type='index'"):
    p("IDX",r[0],"|",(r[1] or "")[:200])
p("---- idl_name counts")
t=time.time()
try:
    p(c.execute("select idl_name,count(*) from instruction group by idl_name order by 2 desc limit 40").fetchall())
except Exception as e: p("err",e)
p("t=",time.time()-t)
p("---- reserve_observation sample")
p(c.execute("select * from reserve_observation limit 2").fetchall())
p("---- instruction sample buy")
p(c.execute("select slot,transaction_index,outer_index,inner_index,idl_name,substr(accounts_json,1,400) from instruction where idl_name='buy' limit 2").fetchall())
p("---- metadata")
p(c.execute("select key,substr(value,1,200) from metadata").fetchall())
p("---- slot range")
p(c.execute("select min(slot),max(slot) from reserve_observation").fetchone())
c.close()
open(O,'w').write("\n".join(o))
