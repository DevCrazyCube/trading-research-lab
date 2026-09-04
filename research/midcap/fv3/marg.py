import sys,time,collections,pickle
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np, fvh, common
W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'logM.txt','w',buffering=1)
def P(*a): OUT.write(' '.join(str(x) for x in a)+'\n')
E=common.build(log=P); greedy,ev=common.make_eval(E)
TRi=E.TRi; VAi=E.VAi; FN=E.FN
S=['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H30/tpNone/slNone/f1.0','H15/tp0.3/sl-0.25/f1.0']
for s in S:
    bt=ev(TRi,s); bv=ev(VAi,s)
    P('\n########## %s   base tr=%+.4f (k=%d) va=%+.4f (k=%d)'%(s,bt['mean'],bt['clusters'],bv['mean'],bv['clusters']))
    P('%-9s %-28s | %-28s'%('feature','TRAIN decile means','VALIDATE decile means'))
    for i,f in enumerate(FN):
        v=E.Fm[i]
        cuts=np.percentile(v[TRi],[10,20,30,40,50,60,70,80,90])
        tr=[];va=[];trk=[];vak=[]
        edges=[-np.inf]+list(cuts)+[np.inf]
        for d in range(10):
            lo,hi=edges[d],edges[d+1]
            st=TRi[(v[TRi]>=lo)&(v[TRi]<hi)]; sv=VAi[(v[VAi]>=lo)&(v[VAi]<hi)]
            rt=ev(st,s) if st.size>0 else None
            rv=ev(sv,s) if sv.size>0 else None
            tr.append(rt['mean'] if rt else float('nan')); trk.append(rt['clusters'] if rt else 0)
            va.append(rv['mean'] if rv else float('nan')); vak.append(rv['clusters'] if rv else 0)
        P('%-9s T %s'%(f,' '.join('%+.2f'%x for x in tr)))
        P('%-9s V %s   (k %s)'%('',' '.join('%+.2f'%x for x in va),'/'.join(str(x) for x in vak)))
P('MARG_DONE')
OUT.close()
