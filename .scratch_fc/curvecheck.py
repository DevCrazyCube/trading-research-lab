import pickle, statistics as st
from collections import Counter
S='/home/anont/meme/.scratch_fc/'
D=pickle.load(open(S+'data1.pkl','rb'))
OUT=open(S+'curvecheck.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
launch=D['launch']; mint2comp=D['mint2comp']; bars=D['bars']
c=Counter(mint2comp.get(m) for m in launch)
P('b11a-covered h12 launches:',len(launch),'complete flag dist',dict(c))
P('base rate of complete among ALL h12 launches:',
  round(sum(1 for v in mint2comp.values() if v==1)/len(mint2comp),4))
P('covered launches that are also in grad_ohlcv:',sum(1 for m in launch if m in bars))
nt=[v['n_trades'] for v in launch.values()]
nt.sort()
P('n_trades per covered launch p10/p50/p90/max',nt[len(nt)//10],nt[len(nt)//2],nt[9*len(nt)//10],nt[-1])
P('covered launches with >=10 trades',sum(1 for x in nt if x>=10))
# graduated among covered
gc=sum(1 for m in launch if mint2comp.get(m)==1)
P('covered & graduated',gc,'rate',round(gc/len(launch),4))
OUT.close()
