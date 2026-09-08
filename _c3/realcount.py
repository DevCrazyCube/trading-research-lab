import json, numpy as np
OUT='/home/anont/meme/_c3'
V=json.load(open(OUT+'/validate.json'))
O=open(OUT+'/realcount.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
for ph in ('A','B','C',None):
    S=[x for x in V if ph is None or x['phase']==ph]
    if not S: continue
    # BH within this phase alone, to match the placebo (which BH's within its own arm)
    pv=np.array([x['va_p'] if x['va_p']==x['va_p'] else 1.0 for x in S])
    o=np.argsort(pv); m=len(pv); k=0
    for r,i in enumerate(o,1):
        if pv[i]<=0.10*r/m: k=r
    bh=set(o[:k].tolist())
    for i,x in enumerate(S): x['bh_ph']= i in bh
    p("phase %s: validated %d | BH %d | BH&va>0 %d | BH&va>0&tr>0 %d | +both medians>0 %d"%(
        ph or 'ALL',len(S),k,
        sum(1 for x in S if x['bh_ph'] and x['va_mean']>0),
        sum(1 for x in S if x['bh_ph'] and x['va_mean']>0 and x['tr_mean']>0),
        sum(1 for x in S if x['bh_ph'] and x['va_mean']>0 and x['tr_mean']>0 and x['va_med']>0 and x['tr_med']>0)))
O.close()
