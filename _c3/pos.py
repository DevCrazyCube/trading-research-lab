import json, numpy as np
OUT='/home/anont/meme/_c3'
O=open(OUT+'/pos.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
tot=0
for f,key in (('phaseA.json',None),('phaseB.json',None),('phaseC.json','cells')):
    try:
        d=json.load(open(OUT+'/'+f))
        if key: d=d[key]
    except Exception as e:
        p("missing",f,e); continue
    tot+=len(d)
    pos=[r for r in d if r['tr_mean']>0]
    p("%s: kept=%d  with POSITIVE train mean=%d"%(f,len(d),len(pos)))
    pos.sort(key=lambda r:-r['tr_mean'])
    for r in pos[:25]:
        p("   %-56s %-14s tr_mean %+7.4f med %+7.4f n %5d k %3d p %.4f"%(
            '|'.join(str(x) for x in r['desc']),r['combo'],r['tr_mean'],r['tr_med'],r['tr_n'],r['tr_k'],r['p']))
p("total kept cells",tot)
O.close()
