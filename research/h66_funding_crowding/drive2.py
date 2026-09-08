from h66 import *
allsyms=sorted(set(px)&set(fund))
# dedupe: one contract per base ticker, prefer USDT
best={}
for s in allsyms:
    b=base_of(s)
    if b not in MEME_BASES: continue
    rank = 0 if s.endswith('USDT') else (1 if s.endswith('USDC') else 2)
    n=len(set(fund[s])&set(px[s]))
    key=(rank,-n)
    if b not in best or key<best[b][0]: best[b]=(key,s)
meme=sorted(v[1] for v in best.values())
print('deduped meme symbols:',len(meme))
import json;json.dump(meme,open('meme.json','w'))
for mh in (90,60):
  for pc,side,am in ((95,'short',0.0003),(5,'long',0.0003)):
    tr=run(meme,side,pc,am,[3,7,14],'x',min_hist=mh)
    print('min_hist',mh,side,'pct',pc,'signals',len(tr),'syms',len(set(t['sym'] for t in tr)))
