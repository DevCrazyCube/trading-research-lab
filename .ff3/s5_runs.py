import sqlite3,collections
o=open('/home/anont/meme/.ff3/step5.txt','w')
con=sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)
slots=[x[0] for x in con.execute("select slot from raw_block_signatures order by slot")]
runs=[]
s=slots[0]; p=slots[0]
GAP=8
for x in slots[1:]:
    if x-p>GAP:
        runs.append((s,p)); s=x
    p=x
runs.append((s,p))
o.write("n runs (gap>%d) = %d\n"%(GAP,len(runs)))
tot=sum(b-a+1 for a,b in runs)
o.write("covered slots in runs %d ; distinct slots %d ; ratio %.3f\n"%(tot,len(slots),len(slots)/tot))
runs_sorted=sorted(runs,key=lambda r:-(r[1]-r[0]))
o.write("top 15 runs by length:\n")
for a,b in runs_sorted[:15]: o.write("  %d..%d len %d\n"%(a,b,b-a+1))
lens=sorted(b-a+1 for a,b in runs)
o.write("run len p50 %d p90 %d\n"%(lens[len(lens)//2],lens[int(len(lens)*0.9)]))
# how much of total span covered
o.write("total span %d, sum runlen %d, frac %.3f\n"%(slots[-1]-slots[0]+1,tot,tot/(slots[-1]-slots[0]+1)))
o.close()
