import pickle, numpy as np
SP='/home/anont/meme/.fc3'
D=pickle.load(open(SP+'/mm.pkl','rb'))
mints=sorted(D.keys())

HS=[5,15,30,60,120,240]
TPS=[None,0.15,0.40,1.00]
SLS=[None,-0.25,-0.50]
EX=[(h,tp,sl) for h in HS for tp in TPS for sl in SLS]
NE=len(EX)

rows=[]      # (mint_idx, i)
feat=[]      # feature vectors
gross=[]     # NE floats per row
exts=[]      # NE ints per row
res=[]       # NE bool

FN=['age_min','bar_idx','dd','lvl','relvol','vol_i','gap_prev','ret1','pri','prig','v0','entry_ts','h','mi','sig_ts','entry_gap']

for mi,m in enumerate(mints):
    d=D[m]; ts=d['ts']; o=d['o']; hi=d['hi']; lo=d['lo']; cl=d['cl']; vo=d['vo']
    n=len(ts)
    if n<3: continue
    runmax=np.maximum.accumulate(hi)
    cumv=np.cumsum(vo)
    ct=d['create_t']; v0=vo[0]
    # per-horizon exit index
    exidx={}
    for H in HS:
        tgt=ts+H*60
        j=np.searchsorted(ts,tgt,side='left')
        exidx[H]=j
    for i in range(1,n-1):
        e=i+1
        ep=o[e]
        if not np.isfinite(ep) or ep<=0: continue
        meanv=cumv[i]/(i+1)
        f=[(ts[i]-ct)/60.0, float(i), cl[i]/max(runmax[i],1e-300), cl[i]/max(o[0],1e-300),
           vo[i]/max(meanv,1e-300), vo[i], float(ts[i]-ts[i-1]), cl[i]/max(cl[i-1],1e-300)-1.0,
           float(d['pri']), float(d['prig']), v0, float(ts[e]), float(d['h']), float(mi), float(ts[i]),
           float(ts[e]-ts[i])]
        g=np.empty(NE,dtype=np.float32); xt=np.empty(NE,dtype=np.int64); rs=np.zeros(NE,dtype=bool)
        for hidx,H in enumerate(HS):
            jj=exidx[H][e]
            if jj<=e: jj=e+1
            has_exit = jj<n
            base_ret = (o[jj]/ep-1.0) if has_exit else np.nan
            base_ts = ts[jj] if has_exit else ts[-1]
            w_end = jj if has_exit else n     # bars available for touch scan
            if w_end>e:
                cmax=np.maximum.accumulate(hi[e:w_end])
                cmin=np.minimum.accumulate(lo[e:w_end])
            else:
                cmax=np.array([]); cmin=np.array([])
            for tpi,tp in enumerate(TPS):
                for sli,sl in enumerate(SLS):
                    k=hidx*(len(TPS)*len(SLS))+tpi*len(SLS)+sli
                    a=len(cmax); b=len(cmin)
                    if tp is not None and len(cmax):
                        a=int(np.searchsorted(cmax, ep*(1+tp), side='left'))
                    if sl is not None and len(cmin):
                        b=int(np.searchsorted(-cmin, -ep*(1+sl), side='left'))
                    if sl is not None and b<len(cmin) and b<=a:
                        g[k]=sl; xt[k]=ts[e+b]; rs[k]=True
                    elif tp is not None and a<len(cmax) and a<b:
                        g[k]=tp; xt[k]=ts[e+a]; rs[k]=True
                    else:
                        if has_exit:
                            g[k]=base_ret; xt[k]=base_ts; rs[k]=True
                        else:
                            g[k]=np.nan; xt[k]=base_ts; rs[k]=False
        feat.append(f); gross.append(g); exts.append(xt); res.append(rs)

F=np.array(feat,dtype=np.float64)
G=np.array(gross,dtype=np.float32)
X=np.array(exts,dtype=np.int64)
R=np.array(res,dtype=bool)
np.savez_compressed(SP+'/ev.npz',F=F,G=G,X=X,R=R,EX=np.array(EX,dtype=object).astype(str))
lines=['rows=%d NE=%d'%(len(F),NE),'FN='+','.join(FN),'EX=%s'%EX]
lines.append('resolution rate per H (no tp/sl): '+', '.join(
  'H%d=%.3f'%(H, R[:,hidx*12+0].mean()) for hidx,H in enumerate(HS)))
lines.append('mints=%d'%len(set(F[:,13])))
open(SP+'/b2.log','w').write('\n'.join(lines))
