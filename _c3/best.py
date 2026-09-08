import json, numpy as np, sys
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
OUT='/home/anont/meme/_c3'
O=open(OUT+'/best.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
F=json.load(open(OUT+'/final.json'))
for r in F:
    d='|'.join(r['desc'])
    if d in ('volaccel=q3|age_min=q0|m_v0=2','age_min=q0|m_px0=1|m_v0=2','rvol10=q1|cumvol_log=q2'):
        p("%-44s %-12s TR %+7.4f (med %+7.4f n%4d k%3d) VA %+7.4f (med %+7.4f n%4d k%3d)"%(
            d,r['combo'],r['tr_mean'],r['tr_med'],r['tr_n'],r['tr_k'],r['va_mean'],r['va_med'],r['va_n'],r['va_k']))
        p("     base %+7.4f edge %+7.4f  boot95 [%+7.4f,%+7.4f]  res %.3f  va_p %s"%(
            r['va_base'],r['va_edge'],r['ci_lo'],r['ci_hi'],r['res'],r['va_p']))
        p("     liq600 %s   liq2000 %s"%(r['liq600'],r['liq2000']))
        p("     uncapped %s  cap100 %s"%(r['uncapped'],r['cap100']))
O.close()
