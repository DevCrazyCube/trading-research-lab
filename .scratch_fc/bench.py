"""Reconcile my harness against the stated random-bar 15m benchmark (-2.92% @ -30% dropout)."""
import pickle, statistics as st, os
S='/home/anont/meme/.scratch_fc/'
FEAT=pickle.load(open(S+'feat.pkl','rb'))
OUT=open(S+'bench.txt','w')
def P(*a): print(*a,file=OUT); OUT.flush()
for tag in ['','_c3']:
    R=pickle.load(open(S+'res%s.pkl'%tag,'rb'))
    RES=R['RES']; STRUCTS=R['STRUCTS']; BFS=R['BFS']; MINTS=R['MINTS']; HORIZ=R['HORIZ']
    ALL=list(range(len(MINTS)))
    bi=BFS.index('all')
    P('=== cap tag %r'%(tag or 'none'))
    for si,(hh,tpi,sli,tri,pos) in enumerate(STRUCTS):
        if tpi is not None or sli is not None or tri is not None or pos!='A': continue
        n_res,s_g,n_do=RES[(si,bi)]
        for charge in [-0.30,-0.50,-1.00]:
            means=[]; tot=0; res=0
            for i in ALL:
                nr=n_res[i]; nd=n_do[i]
                if nr+nd==0: continue
                tn=(1-0.0114)*(nr+s_g[i])-nr+nd*((1-0.0114)*(1+charge)-1)
                means.append(tn/(nr+nd)); tot+=nr+nd; res+=nr
            P('  H=%3d charge=%.2f  mintEqualMean=%+0.4f median=%+0.4f k=%d n=%d res=%.3f'%(
                HORIZ[hh],charge,sum(means)/len(means),st.median(means),len(means),tot,res/tot))
OUT.close()
