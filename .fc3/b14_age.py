import sys; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
exec(open('/home/anont/meme/.fc3/b10_stress.py').read().split("CAND={")[0])
L=['=== age profile, v0>=5040 & creator pri=0, H=30, SL=-25%, fill=close ===']
L.append('%-10s %-24s %-24s'%('age band','TRAIN','VALIDATE'))
for a0,a1 in [(0,10),(10,20),(20,30),(30,40),(40,50),(50,60),(30,60),(60,90),(90,120),(120,240),(240,480),(480,1440)]:
    cnd=lambda f,i,d,_a=(a0,a1): (_a[0]<=f['age'][i]<_a[1]) and d['vo'][0]>=5040 and d['pri']==0
    rt=backtest(cnd,30,None,-0.25,'all','train',fill='close')
    rv=backtest(cnd,30,None,-0.25,'all','validate',fill='close')
    f=lambda r: ('mean=%+.4f n=%3d k=%3d'%(r['mean'],r['n'],r['k'])) if r else 'n/a'
    L.append('%-10s %-24s %-24s'%('%d-%d'%(a0,a1),f(rt),f(rv)))
L.append('')
L.append('=== reversed split (train on h=2, validate on h=1) for the selected cell ===')
cnd=lambda f,i,d: (30<=f['age'][i]<60) and d['vo'][0]>=5040 and d['pri']==0
for sp in ('train','validate','both'):
    r=backtest(cnd,30,None,-0.25,'all',sp,fill='close')
    if r: L.append('%-9s mean=%+.4f cilo=%+.4f medmint=%+.4f fracpos=%.2f n=%3d k=%3d'%(sp,r['mean'],blo(r['pm']),r['med_mint'],r['frac_pos'],r['n'],r['k']))
L.append('')
L.append('=== v0 threshold profile (age 30-60, pri=0, H=30, SL=-25%, fill=close) ===')
for v0t in (0,50,207,1000,5040,20000,50000):
    cnd=lambda f,i,d,_v=v0t: (30<=f['age'][i]<60) and d['vo'][0]>=_v and d['pri']==0
    rt=backtest(cnd,30,None,-0.25,'all','train',fill='close'); rv=backtest(cnd,30,None,-0.25,'all','validate',fill='close')
    f=lambda r: ('mean=%+.4f n=%3d k=%3d'%(r['mean'],r['n'],r['k'])) if r else 'n/a'
    L.append('v0>=%-7s TRAIN %-24s VALIDATE %-24s'%(v0t,f(rt),f(rv)))
L.append('')
L.append('=== horizon profile (age 30-60, v0>=5040, pri=0, SL=-25%, fill=close) ===')
for H in (5,10,15,30,45,60,120,240):
    cnd=lambda f,i,d: (30<=f['age'][i]<60) and d['vo'][0]>=5040 and d['pri']==0
    rt=backtest(cnd,H,None,-0.25,'all','train',fill='close'); rv=backtest(cnd,H,None,-0.25,'all','validate',fill='close')
    f=lambda r: ('mean=%+.4f n=%3d k=%3d'%(r['mean'],r['n'],r['k'])) if r else 'n/a'
    L.append('H=%-4d TRAIN %-24s VALIDATE %-24s'%(H,f(rt),f(rv)))
open(SP+'/b14.log','w').write('\n'.join(L))
