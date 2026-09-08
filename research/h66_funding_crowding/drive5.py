from h66 import *
import json,datetime
meme=json.load(open('meme.json'))
FEE=0.001
def with_funding(tr,H):
    # add realized funding received by the short over the hold (sum of daily funding, capped horizon)
    out=[]
    for t in tr:
        r=t['r%d'%H]
        if r is None: out.append(None); continue
        s=0.0; d=t['entry_day']
        for k in range(H):
            s+=fund[t['sym']].get(d+k*DAY,0.0)
        out.append(max(r,-1.0)+s)
    return out

def blk(tr,H,label,mask=None):
    vals=[];cl=[]
    fr=with_funding(tr,H)
    for t,v in zip(tr,fr):
        if mask and not mask(t): continue
        if v is None: v=-1.0
        vals.append(v-FEE); cl.append(t['sym'])
    if len(vals)<20: print('  %-28s n=%d (too few)'%(label,len(vals))); return
    lo,hi=boot(vals,cl)
    print('  %-28s n=%4d cl=%2d mean=%+7.2f%% med=%+7.2f%% ci=[%+7.2f,%+7.2f]'%(
        label,len(vals),len(set(cl)),100*np.mean(vals),100*np.median(vals),100*lo,100*hi))

def ms(y,m): return int(datetime.datetime(y,m,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
CUT=ms(2025,1)

tr=run(meme,'short',95,0.0003,[3,7,14],'x',min_hist=90)
trg=run(meme,'short',95,0.0003,[3,7,14],'x',min_hist=90,gap=14)  # non-overlapping-ish
print('=== SHORT p95, WITH funding accrued to short, drop@-100%, fee 10bp')
for H in (3,7,14):
    blk(tr,H,'all H=%d'%H)
blk(tr,7,'H=7 pre-2025', lambda t: t['entry_day']<CUT)
blk(tr,7,'H=7 2025-2026', lambda t: t['entry_day']>=CUT)
blk(trg,7,'H=7 non-overlap(gap14)')
print('  signals non-overlap:',len(trg),'syms',len(set(t['sym'] for t in trg)))
print()
print('=== sensitivity: harder cut (trailing 30d mean funding >= 0.10%/8h, still >=p95)')
tr2=run(meme,'short',95,0.0010,[3,7,14],'x',min_hist=90)
print('  signals',len(tr2),'syms',len(set(t['sym'] for t in tr2)))
for H in (3,7,14): blk(tr2,H,'hard H=%d'%H)
print()
print('=== FULL 919-symbol universe (non-meme control), SHORT p95')
allm=sorted(set(px)&set(fund))
tr3=run(allm,'short',95,0.0003,[7],'x',min_hist=90)
print('  signals',len(tr3),'syms',len(set(t['sym'] for t in tr3)))
blk(tr3,7,'full-universe H=7')
