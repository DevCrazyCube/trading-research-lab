import pickle, json, statistics as st
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb')); FEAT=pickle.load(open(S+'feat.pkl','rb'))
bars=D['bars']
OUT=open(S+'tails.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
# bar-to-bar sanity: max high/low ratio per bar, and open-to-open jumps
worst=[]
for m,B in bars.items():
    mx=0; bad=None
    for r in B:
        ts,o,h,l,c,v=r
        if l and l>0 and h/l>mx: mx=h/l; bad=r
    lo=min(r[3] for r in B if r[3]>0) if any(r[3]>0 for r in B) else 0
    hi=max(r[2] for r in B)
    worst.append((hi/lo if lo>0 else 9e9, mx, m, len(B), FEAT[m]['h']))
worst.sort(reverse=True)
P('top 20 mints by (max high / min low) over whole series:')
for w in worst[:20]: P('  range=%.1fx  maxbar h/l=%.1f  %s nbars=%d h=%d'%(w[0],w[1],w[2],w[3],w[4]))
P('median whole-series range', round(st.median([w[0] for w in worst]),2))
P('n mints with range>100x', sum(1 for w in worst if w[0]>100))
P('n mints with single-bar h/l>20', sum(1 for w in worst if w[1]>20))
# show the worst mint's bars around the extreme
m=worst[0][2]; B=bars[m]
P('worst mint',m,'first 6 bars',B[:6])
P('   extreme bars:')
mn=min(r[3] for r in B if r[3]>0)
for i,r in enumerate(B):
    if r[3]<=mn*1.0001 or r[2]>=max(x[2] for x in B)*0.999: P('   i=%d %s'%(i,r))
# distribution of 15m forward gross from every bar open (no filter) to gauge tails
import bisect
alls=[]
for m,B in bars.items():
    ts=[r[0] for r in B]
    for j in range(1,len(B)):
        e=B[j][1]
        if not e or e<=0: continue
        k=bisect.bisect_left(ts,ts[j]+900)
        if k<=j: k=j+1
        if k<len(B): alls.append(B[k][1]/e-1)
alls.sort()
n=len(alls)
P('15m gross from open->open, n=%d'%n)
for q in [0.001,0.01,0.05,0.25,0.5,0.75,0.95,0.99,0.999,0.9999]:
    P('  q%.4f %+ .4f'%(q,alls[min(n-1,int(q*n))]))
P('  max',alls[-1],'mean',sum(alls)/n)
P('  n>10x',sum(1 for x in alls if x>9),'n>100x',sum(1 for x in alls if x>99))
OUT.close()
