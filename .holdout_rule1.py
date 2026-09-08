import sqlite3, json, hashlib, statistics, random, math
import numpy as np

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
OUT=open('/home/anont/meme/.holdout_rule1_out.txt','w')
def P(*a): print(*a,file=OUT)

def hsplit(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

con=sqlite3.connect(DB)
mints={}
for mint,bj,st in con.execute("select mint,bars_json,status from ohlcv where status='ok' and bars_json is not null"):
    b=json.loads(bj)
    if not b: continue
    b=sorted(b,key=lambda x:x[0])
    T=np.array([x[0] for x in b],dtype=np.int64)
    O=np.array([x[1] for x in b],dtype=float)
    H=np.array([x[2] for x in b],dtype=float)
    L=np.array([x[3] for x in b],dtype=float)
    C=np.array([x[4] for x in b],dtype=float)
    V=np.array([x[5] for x in b],dtype=float)
    if len(T)<12: continue
    if not (np.all(np.isfinite(O)) and np.all(np.isfinite(C)) and np.all(O>0)): continue
    mints[mint]=(T,O,H,L,C,V)

P('loaded mints',len(mints))
by_h={0:[],1:[],2:[]}
for m in mints: by_h[hsplit(m)].append(m)
P('mints by h',{k:len(v) for k,v in by_h.items()})
P('bars by h',{k:sum(len(mints[m][0]) for m in v) for k,v in by_h.items()})

MINI=9  # need i-9..i

def features(d):
    T,O,H,L,C,V=d
    n=len(T)
    tp=(H+L+C)/3.0
    cs_v=np.concatenate(([0.0],np.cumsum(V)))
    cs_pv=np.concatenate(([0.0],np.cumsum(tp*V)))
    idx=np.arange(MINI,n)
    # vacc
    num=(cs_v[idx+1]-cs_v[idx-2])/3.0            # V[i-2..i]
    den=(cs_v[idx-2]-cs_v[idx-7])/5.0            # V[i-7..i-3]
    with np.errstate(divide='ignore',invalid='ignore'):
        vacc=np.where(den>0,num/den,np.nan)
    # vwap10 over i-9..i
    sv=cs_v[idx+1]-cs_v[idx-9]
    spv=cs_pv[idx+1]-cs_pv[idx-9]
    with np.errstate(divide='ignore',invalid='ignore'):
        vwap=np.where(sv>0,spv/sv,np.nan)
        vwapdev=np.where((sv>0)&(vwap>0),C[idx]/vwap-1.0,np.nan)
    # vrel5 median V[i-4..i]
    win=np.lib.stride_tricks.sliding_window_view(V,5)   # rows start at 0..n-5
    med=np.median(win,axis=1)[idx-4]
    with np.errstate(divide='ignore',invalid='ignore'):
        vrel5=np.where(med>0,V[idx]/med,np.nan)
    ok=np.isfinite(vacc)&np.isfinite(vwapdev)&np.isfinite(vrel5)&(idx<len(T)-1)
    return idx,vacc,vwapdev,vrel5,ok

FEAT={m:features(mints[m]) for m in mints}

def pool(hs):
    a=[];b=[];c=[]
    for m in mints:
        if hsplit(m) not in hs: continue
        idx,va,vw,vr,ok=FEAT[m]
        a.append(va[ok]); b.append(vw[ok]); c.append(vr[ok])
    return np.concatenate(a),np.concatenate(b),np.concatenate(c)

def thresholds(hs):
    va,vw,vr=pool(hs)
    return dict(n=len(va),
        vacc_lo=float(np.quantile(va,0.90)), vacc_hi=float(np.quantile(va,0.99)),
        vwap_q90=float(np.quantile(vw,0.90)), vrel_q90=float(np.quantile(vr,0.90)))

TH_TRAIN=thresholds({1,2})
TH_H1=thresholds({1}); TH_H2=thresholds({2}); TH_H0=thresholds({0})
P('thresholds train(h1+h2)',TH_TRAIN)
P('thresholds h1 only',TH_H1)
P('thresholds h2 only',TH_H2)
P('thresholds h0 (in-sample sensitivity only)',TH_H0)

CAP=300; TPMULT=1.60

def sim_trades(m, signal_idx_set, tp_include_exit_bar=False):
    """signal bars given as set of bar indices i. returns list of dicts."""
    T,O,H,L,C,V=mints[m]
    n=len(T)
    trades=[]
    next_free=0
    for i in sorted(signal_idx_set):
        if i<next_free: continue
        e=i+1
        if e>=n: continue
        ep=O[e]
        if not (ep>0): continue
        # time-cap exit bar
        j=None
        lim=T[e]+CAP
        k=e+1
        while k<n:
            if T[k]>=lim: j=k; break
            k+=1
        hi_end = (j if (j is not None and tp_include_exit_bar) else (j if j is not None else n))
        # bars scanned for TP: e .. hi_end-1  (exclusive of exit bar by default)
        end = (j if j is not None else n)
        if tp_include_exit_bar and j is not None: end=j+1
        hit = bool(np.any(H[e:end] >= TPMULT*ep)) if end>e else False
        if hit:
            gross=TPMULT-1.0; res=True; kind='tp'
        elif j is not None:
            gross=O[j]/ep-1.0; res=True; kind='cap'
        else:
            gross=None; res=False; kind='drop'
        exit_idx = j if j is not None else n-1
        trades.append(dict(mint=m,i=i,e=e,gross=gross,res=res,kind=kind))
        next_free = (exit_idx if res else 10**9)
    return trades

def netret(gross, toll, drop_charge):
    g = gross if gross is not None else drop_charge
    return (1.0+g)*(1.0-toll)-1.0

def aggregate(trades, toll, drop_charge):
    per={}
    for t in trades:
        per.setdefault(t['mint'],[]).append(netret(t['gross'],toll,drop_charge))
    mm=[float(np.mean(v)) for v in per.values()]
    return per, mm

def rule_signals(TH):
    sigs={}
    for m in mints:
        idx,va,vw,vr,ok=FEAT[m]
        sel=ok & (va>=TH['vacc_lo']) & (va<=TH['vacc_hi']) & (vw>TH['vwap_q90']) & (vr>TH['vrel_q90'])
        if sel.any(): sigs[m]=set(idx[sel].tolist())
    return sigs

def legal_bars(m):
    idx,va,vw,vr,ok=FEAT[m]
    return idx[ok]

def report(tag, trades, hset_desc):
    P('')
    P('=== %s ==='%tag)
    n=len(trades); cl=len(set(t['mint'] for t in trades))
    res=sum(1 for t in trades if t['res'])
    P('n_trades %d  clusters %d  resolution %.4f  (tp %d, cap %d, drop %d)'%(
        n,cl,res/n if n else float('nan'),
        sum(1 for t in trades if t['kind']=='tp'),
        sum(1 for t in trades if t['kind']=='cap'),
        sum(1 for t in trades if t['kind']=='drop')))
    for toll in (0.0114,0.025):
        for dc in (-0.30,-0.50,-1.00):
            per,mm=aggregate(trades,toll,dc)
            P('  toll %.4f drop %.2f : mint-eq mean %+.4f%%  median %+.4f%%  (trade-pooled mean %+.4f%%)'%(
                toll,dc,100*np.mean(mm),100*np.median(mm),
                100*np.mean([x for v in per.values() for x in v])))
    return

rng=np.random.default_rng(20260904)

def boot_ci(mintvals, reps=20000, levels=(2.5,97.5)):
    a=np.array(mintvals,dtype=float)
    if len(a)==0: return (float('nan'),)*len(levels)
    idx=rng.integers(0,len(a),size=(reps,len(a)))
    bs=a[idx].mean(axis=1)
    return [float(np.percentile(bs,l)) for l in levels], bs

# ---------------- MAIN: reserved holdout ----------------
sigs=rule_signals(TH_TRAIN)
res_sigs={m:s for m,s in sigs.items() if hsplit(m)==0}
tr_sigs={m:s for m,s in sigs.items() if hsplit(m) in (1,2)}
tot_legal_h0=sum(len(legal_bars(m)) for m in by_h[0])
tot_legal_tr=sum(len(legal_bars(m)) for m in by_h[1]+by_h[2])
P('')
P('signal bars: reserved %d / %d legal (%.3f%%) across %d mints'%(
    sum(len(v) for v in res_sigs.values()),tot_legal_h0,
    100*sum(len(v) for v in res_sigs.values())/max(tot_legal_h0,1),len(res_sigs)))
P('signal bars: train    %d / %d legal (%.3f%%) across %d mints'%(
    sum(len(v) for v in tr_sigs.values()),tot_legal_tr,
    100*sum(len(v) for v in tr_sigs.values())/max(tot_legal_tr,1),len(tr_sigs)))

hold_trades=[]
for m,s in res_sigs.items(): hold_trades+=sim_trades(m,s)
report('HOLDOUT (h==0) RULE #1, train-fixed thresholds',hold_trades,'h0')

# sanity: same rule on train mints (should roughly reproduce reported)
tr_trades=[]
for m,s in tr_sigs.items(): tr_trades+=sim_trades(m,s)
report('TRAIN/VALIDATE (h in 1,2) RULE #1  [reproduction check]',tr_trades,'h12')

# ---- matched random control on the same reserved mints ----
per_mint_k={}
for t in hold_trades: per_mint_k[t['mint']]=per_mint_k.get(t['mint'],0)+1

def random_matched(reps=1000, toll=0.0114, dc=-0.30):
    means=[]; medians=[]; allmm=[]
    for r in range(reps):
        tt=[]
        for m,k in per_mint_k.items():
            lb=legal_bars(m)
            if len(lb)==0: continue
            pick=set(rng.choice(lb,size=min(k*4,len(lb)),replace=False).tolist())
            t2=sim_trades(m,pick)
            tt+=t2[:k] if len(t2)>=k else t2
        per,mm=aggregate(tt,toll,dc)
        means.append(np.mean(mm)); medians.append(np.median(mm)); allmm.append(mm)
    return np.array(means),np.array(medians),allmm

P('')
P('=== MATCHED RANDOM CONTROL (same reserved mints, same k per mint, same +60%TP/5min structure) ===')
for toll in (0.0114,0.025):
    for dc in (-0.30,-1.00):
        mn,md,_=random_matched(600,toll,dc)
        per,mm=aggregate(hold_trades,toll,dc)
        rule_mean=float(np.mean(mm)); rule_med=float(np.median(mm))
        P('  toll %.4f drop %.2f : random mint-eq mean %+.4f%% (sd %.4f%%) median %+.4f%% | RULE %+.4f%% | diff %+.4f%% | pct-of-random-draws-above-rule %.3f'%(
            toll,dc,100*mn.mean(),100*mn.std(),100*md.mean(),100*rule_mean,
            100*(rule_mean-mn.mean()), float((mn>=rule_mean).mean())))

# ---- universe random control: every reserved mint, random entries ----
P('')
P('=== UNIVERSE RANDOM CONTROL (all reserved mints, 1 random legal entry each, same structure) ===')
for toll in (0.0114,0.025):
    for dc in (-0.30,-1.00):
        ms=[]
        for r in range(400):
            tt=[]
            for m in by_h[0]:
                lb=legal_bars(m)
                if len(lb)==0: continue
                pick={int(rng.choice(lb))}
                tt+=sim_trades(m,pick)
            per,mm=aggregate(tt,toll,dc)
            ms.append(np.mean(mm))
        P('  toll %.4f drop %.2f : mean %+.4f%%'%(toll,dc,100*np.mean(ms)))

# ---- cluster bootstrap CIs on the holdout rule ----
P('')
P('=== CLUSTER BOOTSTRAP BY MINT (holdout rule) ===')
for toll in (0.0114,0.025):
    for dc in (-0.30,-0.50,-1.00):
        per,mm=aggregate(hold_trades,toll,dc)
        (lo,hi),bs=boot_ci(mm,20000,(2.5,97.5))
        alpha=0.05/6
        (blo,bhi),_=boot_ci(mm,20000,(100*alpha/2,100*(1-alpha/2)))
        p_two=2*min((bs<=0).mean(),(bs>=0).mean())
        P('  toll %.4f drop %.2f : mean %+.4f%%  95%%CI [%+.4f%%, %+.4f%%]  Bonf(6) %.4f%%CI [%+.4f%%, %+.4f%%]  boot p=%.4f'%(
            toll,dc,100*np.mean(mm),100*lo,100*hi,100*(1-alpha),100*blo,100*bhi,p_two))

# ---- bootstrap of rule-minus-random paired by mint ----
P('')
P('=== RULE MINUS MATCHED-RANDOM, cluster bootstrap by mint (toll 1.14%, drop -30%) ===')
toll,dc=0.0114,-0.30
per,mm=aggregate(hold_trades,toll,dc)
mints_list=sorted(per.keys())
# per-mint expected random value
rand_per_mint={}
for m in mints_list:
    k=per_mint_k[m]; lb=legal_bars(m); vals=[]
    for r in range(400):
        pick=set(rng.choice(lb,size=min(k*4,len(lb)),replace=False).tolist())
        t2=sim_trades(m,pick)[:k]
        if t2: vals.append(np.mean([netret(t['gross'],toll,dc) for t in t2]))
    rand_per_mint[m]=float(np.mean(vals)) if vals else 0.0
diff=[float(np.mean(per[m]))-rand_per_mint[m] for m in mints_list]
(lo,hi),bs=boot_ci(diff,20000,(2.5,97.5))
P('  mean diff %+.4f%%  95%%CI [%+.4f%%, %+.4f%%]  boot p=%.4f'%(
    100*np.mean(diff),100*lo,100*hi,2*min((bs<=0).mean(),(bs>=0).mean())))

# ---- sensitivity: thresholds from h1 only / h2 only; TP including exit bar ----
P('')
P('=== SENSITIVITY ===')
for nm,TH in (('h1-only thresholds',TH_H1),('h2-only thresholds',TH_H2)):
    s2={m:v for m,v in rule_signals(TH).items() if hsplit(m)==0}
    tt=[]
    for m,v in s2.items(): tt+=sim_trades(m,v)
    per,mm=aggregate(tt,0.0114,-0.30)
    P('  %s : n=%d clusters=%d mean %+.4f%% median %+.4f%%'%(nm,len(tt),len(mm),100*np.mean(mm),100*np.median(mm)))
tt=[]
for m,v in res_sigs.items(): tt+=sim_trades(m,v,tp_include_exit_bar=True)
per,mm=aggregate(tt,0.0114,-0.30)
P('  TP window includes exit bar : n=%d clusters=%d mean %+.4f%% median %+.4f%%'%(len(tt),len(mm),100*np.mean(mm),100*np.median(mm)))

# per-mint dump
P('')
P('=== PER-MINT (holdout, toll 1.14%, drop -30%) ===')
per,mm=aggregate(hold_trades,0.0114,-0.30)
for m in sorted(per,key=lambda x:-np.mean(per[x])):
    P('  %s k=%d mean %+.4f%%'%(m,len(per[m]),100*np.mean(per[m])))
OUT.close()
