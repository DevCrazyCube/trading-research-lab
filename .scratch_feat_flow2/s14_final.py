"""Final: state the survivor as what it actually is (an age filter) and stress it properly."""
import pickle, numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/final.txt','w')
def p(*a): print(*a,file=out); out.flush()
exec(open(W+'/s13_kill.py').read().split("ug=X[:,FI['ubgrow_120']]")[0].replace(
     "out=open(W+'/kill.txt','w')","out=open(W+'/_dev_null.txt','w')"))
out=open(W+'/final.txt','w')
def p(*a): print(*a,file=out); out.flush()
ug=X[:,FI['ubgrow_120']]; age=X[:,FI['age']]
q75=float(np.percentile(ug[TR][np.isfinite(ug[TR])],75))
base=(ug>=q75)&np.isfinite(ug)
S=sidx[(1,1)]
def ev(mask,s=S,fc=None,toll=TOLL,split=VA):
    sel=np.flatnonzero(mask&split&(~CENS[struct_h[s]]))
    if len(sel)<10: return None
    r=stats(greedy(sel.tolist(),s),s,fc,toll)
    if r is None: return None
    lo,hi=boot(r['mu']); r['lo']=lo; r['hi']=hi; return r
def line(tag,mask,s=S,fc=None,toll=TOLL):
    for split,nm in ((TR,'train'),(VA,'valid')):
        r=ev(mask,s,fc,toll,split)
        if r is None: p('%-44s %-6s n/a'%(tag,nm)); continue
        p('%-44s %-6s mean=%7.4f med=%7.4f CI=[%7.4f,%7.4f] n=%5d k=%4d'%(
          tag,nm,r['mean'],r['med'],r['lo'],r['hi'],r['n'],r['k']))

p('=== the survivor restated: it is an AGE filter, not a flow filter ===')
p('overlap: P(age<=120 | ubgrow_120>=p75) = %.3f'%float((age[base]<=120).mean()))
p('overlap: P(ubgrow_120>=p75 | age<=120) = %.3f'%float((base[age<=120]).mean()))
p('')
for amax in [60,120,180,300]:
    line('age<=%ds  -> H180|flowrev.lag1|P2'%amax,(age<=amax))
p('')
p('=== direct age entry under the mandated dropout charges (validate) ===')
for tag,fc,tl in [('frozen=0   toll1.14',None,0.0114),('frozen=-30%% toll1.14',-0.30,0.0114),
                  ('frozen=-50%% toll1.14',-0.50,0.0114),('frozen=-100%% toll1.14',-1.00,0.0114),
                  ('frozen=-100%% toll2.5 ',-1.00,0.025)]:
    r=ev(age<=120,S,fc,tl,VA)
    p('  age<=120s  %-22s mean=%7.4f med=%7.4f CI=[%7.4f,%7.4f]'%(tag,r['mean'],r['med'],r['lo'],r['hi']))
p('')
p('=== concentration of the direct age rule (validate) ===')
r=ev(age<=120,S,None,TOLL,VA); mu=r['mu']; o=np.argsort(-mu)
for k in [0,1,3,5,10,20]:
    m=np.ones(len(mu),bool); m[o[:k]]=False
    p('  drop top-%2d mints: mean=%7.4f med=%7.4f k=%d'%(k,mu[m].mean(),np.median(mu[m]),m.sum()))
p('  per-trade: frac>0=%.3f  median=%.4f  max=%.2f'%((r['net']>0).mean(),np.median(r['net']),r['net'].max()))
p('')
p('=== is the flow-reversal exit doing anything beyond a very short hold? ===')
for hi_,H in [(0,60),(1,180),(2,600)]:
    line('age<=120 -> H%d|flowrev.lag1|P2'%H,(age<=120),sidx[(hi_,1)])
p('')
p('=== RANDOM-ENTRY control with the identical structure, matched rate ===')
rng2=np.random.default_rng(31337)
for rt in [0.005,0.01,0.02]:
    vals=[]
    for _ in range(8):
        m=np.zeros(NDP,bool); m[rng2.choice(NDP,int(NDP*rt),replace=False)]=True
        r=ev(m,S,None,TOLL,VA)
        if r: vals.append(r['mean'])
    p('  random %.1f%% of dp -> H180|flowrev.lag1|P2 : validate mean=%7.4f (sd %.4f, %d reps)'%(
      rt*100,np.mean(vals),np.std(vals),len(vals)))
p('  selection rate of age<=120s: %.4f'%float((age<=120).mean()))
p('  selection rate of ubgrow>=p75: %.4f'%float(base.mean()))
out.close()
