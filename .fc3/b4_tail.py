import sys; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np, pickle
from lib import *
D=pickle.load(open(SP+'/mm.pkl','rb')); mints=sorted(D.keys())
out=[]
ones=np.ones(len(F),dtype=bool)
k=HS.index(15)*12
r=evaluate(ones,k,'all',-0.30,0.0114,'validate',ret_trades=True)
pm=r['pm']
o=np.argsort(pm)[::-1]
out.append('validate H15 per-mint mean top 10: '+', '.join('%.1f'%pm[i] for i in o[:10]))
out.append('sum of top1 contribution to mean: %.4f of %.4f'%(pm[o[0]]/len(pm), pm.mean()))
out.append('mean excl top1=%.4f excl top3=%.4f'%(pm[o[1:]].mean(), pm[o[3:]].mean()))
out.append('trimmed 5%% mean=%.4f'%(np.mean(np.sort(pm)[int(.05*len(pm)):int(.95*len(pm))+1])))
tr=r['trades']; ts=np.sort(tr)[::-1]
out.append('top trades: '+', '.join('%.1f'%x for x in ts[:10]))
# which mints
vm=[m for m in range(NM) if MVAL[m]]
# recompute mapping mint index -> name for those with data
sel=[]
for m in range(NM):
    if not MVAL[m]: continue
    s,e=starts[m],ends[m]
    if e<=s: continue
    sel.append(m)
big=[sel[i] for i in o[:5]]
for m in big:
    d=D[mints[m]]
    out.append('%s bars=%d first_o=%.3g max_hi=%.3g last_c=%.3g age_span_min=%.0f v0=%.3g'%(
        mints[m][:10],len(d['ts']),d['o'][0],d['hi'].max(),d['cl'][-1],(d['ts'][-1]-d['ts'][0])/60,d['vo'][0]))
    # biggest single-bar jump
    rat=d['o'][1:]/np.maximum(d['cl'][:-1],1e-300)
    j=int(np.argmax(rat))
    out.append('   max open/prevclose jump = %.1f at bar %d (vol %.3g -> %.3g)'%(rat[j],j+1,d['vo'][j],d['vo'][j+1]))
    rr=d['cl'][1:]/np.maximum(d['cl'][:-1],1e-300)
    out.append('   max close/close = %.1f ; n bars with >10x bar move = %d'%(rr.max(), int((rr>10).sum())))
open(SP+'/b4.log','w').write('\n'.join(out))
