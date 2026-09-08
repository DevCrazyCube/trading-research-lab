import sqlite3, json, hashlib, os
R='/home/anont/meme/research/'
o=[]
db=sqlite3.connect(R+'midcap/grad_ohlcv.sqlite')
o.append('cols '+str([d[1] for d in db.execute('PRAGMA table_info(ohlcv)')]))
o.append('cnt '+str(db.execute('select count(*), sum(n_bars) from ohlcv').fetchone()))
o.append('status '+str(db.execute('select status, count(*) from ohlcv group by status').fetchall()))
r=db.execute('select mint,pool,n_bars,first_ts,last_ts,status,bars_json from ohlcv where n_bars>20 limit 1').fetchone()
b=json.loads(r[6])
o.append('sample n=%d st=%s first3=%s'%(r[2],r[5],b[:3]))
o.append('last1='+str(b[-1]))
h={0:0,1:0,2:0}; nb={0:0,1:0,2:0}
gaps={}
for m,n,bj in db.execute('select mint,n_bars,bars_json from ohlcv'):
    k=int(hashlib.md5(m.encode()).hexdigest(),16)%3
    h[k]+=1; nb[k]+=(n or 0)
    if k!=0 and n and n>3:
        bb=sorted(json.loads(bj), key=lambda x:x[0])
        for i in range(1,min(len(bb),200)):
            d=(bb[i][0]-bb[i-1][0])
            gaps[d]=gaps.get(d,0)+1
o.append('splitmints '+str(h)+' bars '+str(nb))
gg=sorted(gaps.items(), key=lambda x:-x[1])[:8]
o.append('ts gaps top: '+str(gg))
db2=sqlite3.connect(R+'b11a/window_labels.sqlite')
o.append('wl '+str([d[1] for d in db2.execute('PRAGMA table_info(window_label)')]))
o.append('wlcnt '+str(db2.execute('select count(*), sum(complete) from window_label').fetchone()))
try:
    import numpy; o.append('numpy '+numpy.__version__)
except Exception as e: o.append('NO numpy')
print(' || '.join(o))
