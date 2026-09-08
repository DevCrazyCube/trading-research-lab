import numpy as np, json, os, sqlite3, hashlib
OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix.npz',allow_pickle=True)
G=d['gross']; M=d['mint']; P=d['pos']; HV=d['hv']; EX=d['exitpos']
mints=json.load(open(OUT+'/mints.json'))
fin=np.isfinite(G)
g=G[fin]
print('n resolved',len(g))
for q in [0,0.1,1,5,25,50,75,95,99,99.9,100]:
    print('  p%-5s %+.4f'%(q,np.percentile(g,q)))
print('mean',g.mean(),'winsor99 mean',np.clip(g,np.percentile(g,0.5),np.percentile(g,99.5)).mean())
top=np.argsort(-G[fin])[:15]
idx=np.where(fin)[0][top]
con=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
cache={}
def bars(m):
    if m not in cache:
        cache[m]=sorted(json.loads(con.execute('select bars_json from ohlcv where mint=?',(m,)).fetchone()[0]),key=lambda z:z[0])
    return cache[m]
print('\nTOP 15 single-trade gross returns:')
for i in idx:
    m=mints[M[i]]; b=bars(m); k=int(P[i]); x=int(EX[i])
    print('%s h=%d entrypos=%d exitpos=%d gap_entry=%ds hold=%ds entry_open=%.3e exit_open=%.3e ret=%+.1fx'%(
        m[:12],HV[i],k,x,b[k][0]-b[k-1][0],b[x][0]-b[k][0],b[k][1],b[x][1],1+G[i]))
    lo=max(0,k-2); hi=min(len(b),x+2)
    print('    ',[ (b[j][0]-b[k][0], round(b[j][1],12), round(b[j][4],12), round(b[j][5],2)) for j in range(lo,hi)][:8])
# how much of the mint-equal val mean comes from the top few mints
val=(HV==2)
per={}
for i in np.where(val)[0]:
    pass
print('\nentry gap distribution (signal bar -> entry bar):')
gaps=[]
for i in range(len(M)):
    m=mints[M[i]]; b=bars(m); k=int(P[i]); gaps.append(b[k][0]-b[k-1][0])
gaps=np.array(gaps)
print('  ',[(q,int(np.percentile(gaps,q))) for q in (50,75,90,95,99,100)])
print('hold length distribution:')
hs=[]
for i in np.where(fin)[0]:
    m=mints[M[i]]; b=bars(m); hs.append(b[int(EX[i])][0]-b[int(P[i])][0])
hs=np.array(hs); print('  ',[(q,int(np.percentile(hs,q))) for q in (50,75,90,95,99,100)])
