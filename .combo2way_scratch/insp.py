import sqlite3,json,hashlib,collections
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=c.execute('select mint,n_bars,status,first_ts,last_ts,bars_json from ohlcv').fetchall()
print(collections.Counter(r[2] for r in rows))
ok=[r for r in rows if r[1] and r[1]>0]
print('with bars',len(ok))
print('hash', collections.Counter(int(hashlib.md5(r[0].encode()).hexdigest(),16)%3 for r in ok))
mine=[x for x in ok if int(hashlib.md5(x[0].encode()).hexdigest(),16)%3 in (1,2)]
print('mine',len(mine),'bars',sum(x[1] for x in mine))
r=mine[0]
b=json.loads(r[5]); print(r[0],r[1],len(b))
print(b[:3]); print(b[-2:])
gaps=collections.Counter(); zerovol=0; tot=0
for x in mine:
    bb=sorted(json.loads(x[5]),key=lambda z:z[0])
    for i in range(1,len(bb)): gaps[bb[i][0]-bb[i-1][0]]+=1
    for z in bb:
        tot+=1
        if not z[5]: zerovol+=1
print('gaps',gaps.most_common(10))
print('zerovol',zerovol,'/',tot)
nb=[x[1] for x in mine]; nb.sort()
print('nbars quantiles',[nb[int(q*(len(nb)-1))] for q in (0,.1,.25,.5,.75,.9,1)])
print('ts range', min(x[3] for x in mine), max(x[4] for x in mine))
