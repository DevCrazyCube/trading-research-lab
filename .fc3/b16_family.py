import sys; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
exec(open('/home/anont/meme/.fc3/b10_stress.py').read().split("CAND={")[0])
V0HI=5040.0
FAM=[
 ('P1 first-bar, v0=hi, prig=0, H=120 TP+100 SL-25 (first)',
   lambda f,i,d: d['vo'][0]>=V0HI and d['prig']==0, 120,1.00,-0.25,'first'),
 ('P1b same, SL=None (no truncation on the downside)',
   lambda f,i,d: d['vo'][0]>=V0HI and d['prig']==0, 120,1.00,None,'first'),
 ('P1c same, no TP no SL (pure hold)',
   lambda f,i,d: d['vo'][0]>=V0HI and d['prig']==0, 120,None,None,'first'),
 ('P2 age6-10, v0=hi, prig=0, H=60 TP+100 SL-25 (all)',
   lambda f,i,d: 6<=f['age'][i]<10 and d['vo'][0]>=V0HI and d['prig']==0, 60,1.00,-0.25,'all'),
 ('P2c same, pure hold',
   lambda f,i,d: 6<=f['age'][i]<10 and d['vo'][0]>=V0HI and d['prig']==0, 60,None,None,'all'),
 ('P3 age10-20 any coin, H=15 SL-25 (all)',
   lambda f,i,d: 10<=f['age'][i]<20, 15,None,-0.25,'all'),
 ('P3c same, pure hold',
   lambda f,i,d: 10<=f['age'][i]<20, 15,None,None,'all'),
 ('P4 dd>=.9 & lvl>=3 & rv .02-.2, H=30 TP+40 SL-25 (all)',
   lambda f,i,d: f['dd'][i]>=0.9 and f['lvl'][i]>=3 and 0.02<=f['rv'][i]<0.2, 30,0.40,-0.25,'all'),
 ('P4c same, pure hold',
   lambda f,i,d: f['dd'][i]>=0.9 and f['lvl'][i]>=3 and 0.02<=f['rv'][i]<0.2, 30,None,None,'all'),
]
L=[]
for name,cond,H,tp,sl,mode in FAM:
    L.append('=== %s ==='%name)
    fills=['base'] if sl is None else ['base','close','low']
    for split in ('train','validate'):
        for fill in fills:
            r=backtest(cond,H,tp,sl,mode,split,fill=fill)
            if r is None: continue
            L.append('  %-8s fill=%-5s mean=%+.4f cilo=%+.4f medmint=%+.4f fracpos=%.2f ex-top1=%+.4f n=%4d k=%3d res=%.2f'%(
                split,fill,r['mean'],blo(r['pm']),r['med_mint'],r['frac_pos'],r['mean_ex1'],r['n'],r['k'],r['res']))
    r=backtest(cond,H,tp,sl,mode,'validate',fill=('close' if sl else 'base'),cap=1.0)
    if r: L.append('  validate cap=+100%% (pess.fill) mean=%+.4f cilo=%+.4f'%(r['mean'],blo(r['pm'])))
    r=backtest(cond,H,tp,sl,mode,'validate',fill=('close' if sl else 'base'),toll=0.025,charge=-1.0,entry_slip=0.02)
    if r: L.append('  validate WORST(toll2.5%%,drop-100%%,entry+2%%) mean=%+.4f cilo=%+.4f'%(r['mean'],blo(r['pm'])))
open(SP+'/b16.log','w').write('\n'.join(L))
