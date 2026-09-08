from h66 import *
import json
meme=json.load(open('meme.json'))
FEE=0.001   # 10 bp round trip taker on Binance perps
for side,pc in (('short',95),('long',5)):
    tr=run(meme,side,pc,0.0003,[3,7,14],'x',min_hist=90)
    print('=== %s p%d  signals=%d syms=%d'%(side,pc,len(tr),len(set(t['sym'] for t in tr))))
    for H in (3,7,14):
        for dc,lab in ((None,'resolved-only'),(-0.30,'drop@-30%'),(-0.50,'drop@-50%'),(-1.00,'drop@-100%')):
            s=summarize(tr,H,FEE,dc,lab)
            if s: print('  H=%2d %-13s n=%4d cl=%2d mean=%+7.2f%% med=%+7.2f%% ci=[%+7.2f,%+7.2f] res=%5.1f%% win=%4.1f%%'%(
                s['H'],s['tag'],s['n'],s['clusters'],s['mean'],s['median'],s['ci_lo'],s['ci_hi'],s['resolution'],s['winrate']))
