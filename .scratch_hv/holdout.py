import sys, statistics, random
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load, signals, run_trades, aggregate, boot_ci, net_ret, simulate
O=open('/home/anont/meme/.scratch_hv/holdout.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n'); O.flush()

W=20; HOLD=45
data=load({0})          # RESERVED HOLDOUT ONLY
p('=== RESERVED HOLDOUT (md5(mint)%%3==0) ===')
p('mints with >=25 bars:',len(data),' total bars:',sum(len(b) for m,b in data))

# ---- rule ----
per={}; sigcount=0
for m,b in data:
    sg=signals(b,0.05,300.0,W)
    sigcount+=len(sg)
    tr=run_trades(b,sg,hold_min=HOLD)
    if tr: per[m]=tr
p('raw signal bars:',sigcount)

def report(per,label,toll,dc):
    mm,at,rn,tn=aggregate(per,toll,dc)
    if not mm: p(label,'NO TRADES'); return None
    lo,hi,pval=boot_ci(mm,20000,777,2.5,97.5)
    blo,bhi,_=boot_ci(mm,20000,777,0.41667,99.58333)
    p(f'{label}: n={tn} k={len(mm)} res={rn/tn*100:.2f}% mean={statistics.mean(mm)*100:.4f}% '
      f'mintMed={statistics.median(mm)*100:.4f}% tradeMed={statistics.median(at)*100:.4f}% '
      f'CI95=[{lo*100:.3f}%,{hi*100:.3f}%] CI99.17=[{blo*100:.3f}%,{bhi*100:.3f}%] bootP(mean<=0)={pval:.4f}')
    return dict(n=tn,k=len(mm),res=rn/tn,mean=statistics.mean(mm),med=statistics.median(mm),
                tmed=statistics.median(at),lo=lo,hi=hi,blo=blo,bhi=bhi,p=pval)

p('')
p('--- RULE #3 on reserved holdout ---')
main=None
for toll,tl in ((0.0114,'toll1.14'),(0.025,'toll2.50')):
    for dc,dl in ((-0.30,'drop-30'),(-0.50,'drop-50'),(-1.00,'drop-100')):
        r=report(per,f'RULE {tl} {dl}',toll,dc)
        if toll==0.0114 and dc==-0.30: main=r

# ---- matched random control: same mints, same trade counts, same structure ----
p('')
p('--- MATCHED RANDOM-ENTRY CONTROL (same reserved mints, same structure, same #trades/mint) ---')
bars_by={m:b for m,b in data}
counts={m:len(v) for m,v in per.items()}
R=400
def rand_run(seed,toll,dc):
    rnd=random.Random(seed)
    cper={}
    for m,k in counts.items():
        b=bars_by[m]
        elig=list(range(W,len(b)-1))
        if not elig: continue
        pick=sorted(rnd.sample(elig,min(k*3,len(elig))))  # oversample, no-overlap will thin
        tr=run_trades(b,pick,hold_min=HOLD)
        tr=tr[:k] if len(tr)>k else tr
        if tr: cper[m]=tr
    mm,at,rn,tn=aggregate(cper,toll,dc)
    return mm,at,rn,tn

for toll,tl in ((0.0114,'toll1.14'),(0.025,'toll2.50')):
    for dc,dl in ((-0.30,'drop-30'),(-1.00,'drop-100')):
        ms=[];meds=[];ns=[];rs=[]
        for s in range(R):
            mm,at,rn,tn=rand_run(1000+s,toll,dc)
            if not mm: continue
            ms.append(statistics.mean(mm)); meds.append(statistics.median(mm)); ns.append(tn); rs.append(rn/tn)
        ms_s=sorted(ms)
        p(f'CONTROL {tl} {dl}: reps={len(ms)} avg_n={statistics.mean(ns):.0f} avg_res={statistics.mean(rs)*100:.2f}% '
          f'mean={statistics.mean(ms)*100:.4f}% [p5={ms_s[int(.05*len(ms_s))]*100:.3f}%, p95={ms_s[int(.95*len(ms_s))]*100:.3f}%] '
          f'mintMed={statistics.mean(meds)*100:.4f}%')
        if toll==0.0114 and dc==-0.30 and main:
            diff=main['mean']-statistics.mean(ms)
            frac=sum(1 for x in ms if x>=main['mean'])/len(ms)
            p(f'   -> RULE minus CONTROL = {diff*100:.4f} pp ; P(control >= rule) = {frac:.4f}')

# ---- true unconditional random-bar control over ALL reserved mints, same structure ----
p('')
p('--- UNCONDITIONAL: same structure on EVERY bar, all reserved mints ---')
uper={}
for m,b in data:
    tr=run_trades(b,list(range(W,len(b)-1)),hold_min=HOLD)
    if tr: uper[m]=tr
report(uper,'UNCOND-ALLBARS toll1.14 drop-30',0.0114,-0.30)

# ---- robustness: other readings of the feature definition ----
p('')
p('--- robustness: alternative readings of rvol20/notional20 (holdout) ---')
def sig_C(b):
    v=[x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        s=sum(v[i-W:i])
        if s>0 and v[i]/s<=0.05 and s>=300: out.append(i)
    return out
def sig_D(b):
    v=[x[5] for x in b]; out=[]
    for i in range(W,len(b)-1):
        w=v[i-W:i]; s=sum(w); md=statistics.median(w)
        if md>0 and s>0 and v[i]/md<=0.05 and s>=300: out.append(i)
    return out
def sig_B(b):
    v=[x[5] for x in b]; out=[]
    for i in range(W-1,len(b)-1):
        s=sum(v[i-W+1:i+1])
        if s>0 and v[i]/(s/W)<=0.05 and s>=300: out.append(i)
    return out
for nm,fn in (('B incl-i',sig_B),('C v/sum20',sig_C),('D v/median20',sig_D)):
    pp={}
    for m,b in data:
        tr=run_trades(b,fn(b),hold_min=HOLD)
        if tr: pp[m]=tr
    report(pp,'ALT '+nm+' toll1.14 drop-30',0.0114,-0.30)
O.close()
