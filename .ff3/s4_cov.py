import sqlite3,json,pickle,collections
o=open('/home/anont/meme/.ff3/step4.txt','w')
con=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
r=con.execute("select min(slot),max(slot),count(*),count(distinct slot) from b11a_bodies.raw_block_signatures" if False else "select min(slot),max(slot),count(*) from raw_block_signatures").fetchone()
o.write("raw_block_signatures min %s max %s n %s span %s\n"%(r[0],r[1],r[2],r[1]-r[0]+1))
r2=con.execute("select min(slot),max(slot),count(distinct slot) from instruction").fetchone()
o.write("instruction slots min %s max %s distinct %s\n"%r2)
# gaps: histogram of consecutive slot diffs in raw_block_signatures
slots=[x[0] for x in con.execute("select slot from raw_block_signatures order by slot")]
d=collections.Counter()
for i in range(1,len(slots)): d[min(slots[i]-slots[i-1],20)]+=1
o.write("slot gap hist (capped 20): %s\n"%sorted(d.items()))
o.write("metadata:\n")
for k,v in con.execute("select key,value from metadata"): o.write("  %s = %s\n"%(k,str(v)[:300]))
o.close()
