import sqlite3, json, hashlib
import numpy as np
OUT='/home/anont/meme/_r0'
o=open(OUT+'/diag2.log','w')
def L(*a): o.write(' '.join(str(x) for x in a)+'\n')
con=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
for mint in ['mwzjM1TRzc5sYm1sp4QKi54QuPTqthA7grBY5Vcpump','3aaMozqFHp6KEaGFQQ8bm5ii7os75uBdRZNzZn4epump']:
    assert int(hashlib.md5(mint.encode()).hexdigest(),16)%3 in (1,2)
    r=con.execute('select pool,n_bars,status,bars_json from ohlcv where mint=?',(mint,)).fetchone()
    b=json.loads(r[3]); b.sort(key=lambda x:x[0])
    L('==',mint,'pool',r[0],'n',r[1],r[2])
    for row in b[:6]: L('   ',row)
    L('   ...')
    # find biggest consecutive close-to-close jump
    c=np.array([x[4] for x in b]); ts=np.array([x[0] for x in b])
    j=np.abs(np.log(c[1:]/c[:-1]))
    k=int(np.argmax(j))
    L('   biggest consecutive jump at idx',k,'ratio %.4g'%(c[k+1]/c[k]))
    for row in b[max(0,k-3):k+4]: L('    >',row)
# how widespread: count mints with any consecutive close ratio > 10x or < 0.1x
n_bad=0; tot=0; ratios=[]
for mint,bj in con.execute('select mint,bars_json from ohlcv where n_bars>5'):
    if int(hashlib.md5(mint.encode()).hexdigest(),16)%3==0: continue
    b=json.loads(bj); b.sort(key=lambda x:x[0])
    c=np.array([x[4] for x in b],dtype=float)
    if len(c)<6 or (c<=0).any(): continue
    tot+=1
    rr=c[1:]/c[:-1]
    mx=float(max(rr.max(),1.0/rr.min()))
    ratios.append(mx)
    if mx>10: n_bad+=1
L('mints with a >10x consecutive close jump:',n_bad,'of',tot)
L('max-consecutive-jump pctiles',[float(np.percentile(ratios,q)) for q in (50,75,90,95,99,100)])
o.close()
