import pickle, numpy as np
OUT='/home/anont/meme/_r0'
D=pickle.load(open(OUT+'/cache.pkl','rb')); mints=D['mints']; REG=D['REG']; RN=D['REGNAMES']; grid=D['grid']
o=open(OUT+'/diag4.log','w')
def L(*a): o.write(' '.join(str(x) for x in a)+'\n')
ts=np.concatenate([m['ts'] for m in mints])
gi=np.concatenate([m['gi'] for m in mints])
R=REG[gi]
L('bar ts min/max',int(ts.min()),int(ts.max()),'span_h %.1f'%((ts.max()-ts.min())/3600))
CUT=1785254235
L('bars after creates-table cutoff %d: %.3f'%(CUT,float((ts>CUT).mean())))
for k,nm in enumerate(RN):
    c=R[:,k]; ok=~np.isnan(c)
    L('%-16s corr(with ts) %+.3f  | mean-ts-of-BOT20 %s  TOP20 %s'%(
        nm, float(np.corrcoef(c[ok],ts[ok])[0,1]),
        '%.1fh'%((np.mean(ts[ok][c[ok]<=np.percentile(c[ok],20)])-ts.min())/3600),
        '%.1fh'%((np.mean(ts[ok][c[ok]>=np.percentile(c[ok],80)])-ts.min())/3600)))
# how much of VOL1H_BOT20 is the tail of the sample
c=R[:,1]; ok=~np.isnan(c)
lo=c<=np.percentile(c[ok],20)
L('VOL1H_BOT20 bars: frac in last 25%% of calendar span: %.3f (base 0.25)'%(
    float((ts[lo]>ts.min()+0.75*(ts.max()-ts.min())).mean())))
c0=R[:,0]
lo0=c0<=577
L('LAUNCH1H_BOT20 bars: frac after creates cutoff: %.3f'%float((ts[lo0]>CUT).mean()))
o.close()
