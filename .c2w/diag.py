import numpy as np
OUT=open('/home/anont/meme/.c2w/diag.txt','w')
def p(*a): print(*a,file=OUT)
d=np.load('/home/anont/meme/.c2w/mat.npz',allow_pickle=True)
g=d['ret_g']; ok=d['ok'].astype(bool); mid=d['mint_id']; hs=d['hs']; X=d['X']
FN=[str(x) for x in d['featnames']]
r=g[ok]
p("resolved trades:",ok.sum(),"of",len(g))
p("gross 15m return pooled: mean=%+.4f median=%+.4f" % (r.mean(), np.median(r)))
p("gross pct: ", np.round(np.percentile(r,[1,5,10,25,50,75,90,95,99]),4).tolist())
p("frac gross>0:", round(float((r>0).mean()),4))
# mint-equal gross
u,inv=np.unique(mid[ok],return_inverse=True)
cnt=np.bincount(inv); tot=np.bincount(inv,weights=r)
mm=tot/cnt
p("mint-equal gross: mean=%+.4f median=%+.4f  (k=%d)"%(mm.mean(),np.median(mm),len(mm)))
p("mint-mean pct:", np.round(np.percentile(mm,[1,5,25,50,75,95,99]),4).tolist())
p("worst 5 mint means:", np.round(np.sort(mm)[:5],4).tolist())
p("best 5 mint means:", np.round(np.sort(mm)[-5:],4).tolist())
p("frac mints positive:", round(float((mm>0).mean()),4))
# per-mint number of trades
p("trades per mint pct:", np.percentile(cnt,[5,25,50,75,95]).tolist())
# dropout rate per mint
u2,inv2=np.unique(mid,return_inverse=True)
c2=np.bincount(inv2); d2=np.bincount(inv2,weights=(~ok).astype(float))
p("per-mint dropout frac pct:", np.round(np.percentile(d2/c2,[5,25,50,75,95]),3).tolist())
# life span in minutes
p("life: bars per mint pct:", np.percentile(c2,[5,25,50,75,95]).tolist())
# check price decay: r_since_first quantiles at last bar of each mint
k=FN.index('r_since_first')
p("r_since_first p:", np.round(np.percentile(X[:,k],[1,25,50,75,99]),3).tolist())
k=FN.index('dd_from_ath')
p("dd_from_ath p:", np.round(np.percentile(X[:,k],[1,25,50,75,99]),3).tolist())
OUT.close()
