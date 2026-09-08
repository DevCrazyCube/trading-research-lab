import sqlite3, json, random, statistics as st, numpy as np
HOR=900; GAPMAX=120; TOLL_RT=0.0114; SEED=20260903; SOL_USD=105.0
c=sqlite3.connect('file:research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
mints={}
for mint,bj,fa in c.execute("select mint,bars_json,fetched_at from ohlcv where status='ok'"):
    b=sorted(json.loads(bj)); b=[x for x in b if x[1]>0 and x[4]>0]
    if len(b)>=4: mints[mint]=(b,fa)
O,H,L,C=1,2,3,4
def prior5(b,i):
    t=b[i][0]-300
    for j in range(i-1,-1,-1):
        if abs(b[j][0]-t)<=60: return b[i][C]/b[j][C]-1
        if b[j][0]<t-60: return None
    return None
random.seed(SEED); ENTRIES={'random':[], 'survivor_cell':[]}
for mint,(b,fa) in mints.items():
    adm=[(i,i+1) for i in range(len(b)-1) if b[i+1][0]-b[i][0]<=GAPMAX and b[i+1][0]+HOR+300<=fa]
    if not adm: continue
    for s,e in (adm if len(adm)<=5 else random.sample(adm,5)): ENTRIES['random'].append((mint,s,e))
    for s,e in adm:
        r=prior5(b,s)
        if r is not None and 0.048<=r<=0.095: ENTRIES['survivor_cell'].append((mint,s,e))

def exit_leg(b,ei,ets,conv='A'):
    after=[k for k in range(ei+1,len(b)) if b[k][0]>=ets+HOR]
    if not after: return None
    if conv=='A':
        last=max([k for k in range(ei,len(b)) if b[k][0]<=ets+HOR], default=ei); return b[last][C]
    if conv=='B':
        k=after[0]; return b[k][O] if b[k][0]<=ets+HOR+600 else None
    return b[after[0]][O]

def evaluate(mint,si,ei,frac,tp,conv='A',fill='nextopen'):
    b,fa=mints[mint]; ent=b[ei][O]; ets=b[ei][0]
    tp_hit=False; tp_px=None
    if frac>0:
        tgt=ent*(1+tp)
        for k in range(ei+1,len(b)):
            if b[k][0]>ets+HOR: break
            if b[k][H]>=tgt:
                if fill=='limit': tp_px=max(tgt,b[k][O]); tp_hit=True
                elif fill=='close': tp_px=b[k][C]; tp_hit=True
                else:  # nextopen: strict no-lookahead, sell at the NEXT real bar's open
                    if k+1<len(b) and b[k+1][0]-b[k][0]<=GAPMAX and b[k+1][0]<=ets+HOR+GAPMAX:
                        tp_px=b[k+1][O]; tp_hit=True
                    else: tp_hit=False   # no real next bar to sell into -> ladder never executes
                break
    ex=exit_leg(b,ei,ets,conv)
    f=frac if tp_hit else 0.0
    return dict(resolved=ex is not None, tp_hit=tp_hit, f=f,
                realized=f*(tp_px/ent-1.0) if tp_hit else 0.0,
                resid_w=1.0-f, resid_ret=(ex/ent-1.0) if ex is not None else None,
                tp_mult=(tp_px/ent) if tp_hit else None)

def netvals(res,dropout,g,S,toll=TOLL_RT):
    out=[]
    for r in res:
        rr=r['resid_ret'] if r['resolved'] else dropout
        n_tx=1+(1 if r['tp_hit'] else 0)+(1 if r['resolved'] else 0)
        out.append(r['realized']+r['resid_w']*rr - toll - n_tx*g/S)
    return out
def boot_ci(v,cl,B=4000,seed=SEED):
    rng=np.random.default_rng(seed); d={}
    for a,k in zip(v,cl): d.setdefault(k,[]).append(a)
    arr=[np.array(x) for x in d.values()]; n=len(arr)
    ms=np.array([np.concatenate([arr[j] for j in rng.integers(0,n,n)]).mean() for _ in range(B)])
    return float(np.percentile(ms,2.5)),float(np.percentile(ms,97.5))

FRACS=[0.25,0.5,0.75]; TPS=[0.05,0.10,0.15,0.20,0.30,0.50]
print("### TP-FILL SENSITIVITY: ladder-minus-single delta (pp), conv A, dropout -50%, no fixed cost")
for setname in ['random','survivor_cell']:
    E=ENTRIES[setname]; cl=[x[0] for x in E]
    print(f"\n{setname}: n={len(E)} k={len(set(cl))}")
    for fill in ['limit','close','nextopen']:
        base=netvals([evaluate(m,s,e,0,0,'A',fill) for m,s,e in E],-0.50,0.0,1e12)
        rows=[]
        for fr in FRACS:
            for tp in TPS:
                r=[evaluate(m,s,e,fr,tp,'A',fill) for m,s,e in E]
                v=netvals(r,-0.50,0.0,1e12); d=[a-b for a,b in zip(v,base)]
                rows.append((fr,tp,st.mean(v),st.median(v),st.mean(d),sum(x['tp_hit'] for x in r)/len(r)))
        rows.sort(key=lambda x:-x[2]); b=rows[0]
        r=[evaluate(m,s,e,b[0],b[1],'A',fill) for m,s,e in E]
        v=netvals(r,-0.50,0.0,1e12); d=[a-bb for a,bb in zip(v,base)]
        lo,hi=boot_ci(d,cl); vlo,vhi=boot_ci(v,cl)
        npos=sum(1 for x in rows if x[4]>0)
        print(f"  fill={fill:9s} SINGLE mean {st.mean(base)*100:7.2f}% | best f={b[0]} tp={b[1]:.2f} "
              f"mean {b[2]*100:7.2f}% med {b[3]*100:6.2f}% CI[{vlo*100:.2f},{vhi*100:.2f}] "
              f"| delta {b[4]*100:+6.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}] tp_hit {b[5]*100:.0f}% | cells with delta>0: {npos}/18")

print("\n\n"+"="*100)
print("### THE HYPOTHESIS: fixed cost per transaction, and B*")
G={'base_only(5,000 lam)':5000e-9*SOL_USD,'MEASURED MEDIAN(80,001)':80001e-9*SOL_USD,
   'p75(566,105)':566105e-9*SOL_USD,'p90(1,005,000)':1055000e-9*SOL_USD*0+1005000e-9*SOL_USD,
   'p99(5,871,000)':5871000e-9*SOL_USD, 'hypothesis-assumed $0.10':0.10, 'hypothesis-assumed $0.50':0.50}
E=ENTRIES['survivor_cell']; cl=[x[0] for x in E]
BEST=(0.75,0.10)
for dl,dv in [('-30%',-0.30),('-50%',-0.50),('-100%',-1.00)]:
    single=[evaluate(m,s,e,0,0,'A','nextopen') for m,s,e in E]
    lad=[evaluate(m,s,e,BEST[0],BEST[1],'A','nextopen') for m,s,e in E]
    bg=st.mean(netvals(single,dv,0.0,1e12)); lg=st.mean(netvals(lad,dv,0.0,1e12))
    dgross=lg-bg; ptp=sum(r['tp_hit'] for r in lad)/len(lad)
    print(f"\ndropout {dl}: SINGLE gross-of-fixed mean {bg*100:.2f}%  LADDER(f=.75,tp=.10) {lg*100:.2f}%  "
          f"delta_gross={dgross*100:+.3f}pp  P(extra sell)={ptp:.3f}")
    print(f"   B* = P(tp)*g*N/delta_gross  (bankroll above which the ladder's extra sell pays for itself)")
    print(f"   {'g per tx':>28} | {'B*(N=5)':>10} {'B*(N=12)':>10} | {'ladder net@$60,N=12':>20} {'single net@$60,N=12':>20}")
    for k,g in G.items():
        Bs=ptp*g*5/dgross; B12=ptp*g*12/dgross
        ln=st.mean(netvals(lad,dv,g,60/12)); sn=st.mean(netvals(single,dv,g,60/12))
        print(f"   {k:>28} | ${Bs:9.2f} ${B12:9.2f} | {ln*100:19.2f}% {sn*100:19.2f}%")
    print(f"   BREAK-EVEN FEE g* at B=$60: N=5 (S=$12) g*=${dgross*12/ptp:.4f}/tx ; N=12 (S=$5) g*=${dgross*5/ptp:.4f}/tx")

print("\n"+"="*100)
print("### RESIDUAL DUST (f=0.75, tp=0.10, survivor_cell, dropout -50%)")
lad=[evaluate(m,s,e,0.75,0.10,'A','nextopen') for m,s,e in E]
hit=[r for r in lad if r['tp_hit']]
for N,S in [(5,60/5),(12,60/12),(20,60/20)]:
    at_so=[r['resid_w']*S*r['tp_mult'] for r in hit]
    at_ex=[r['resid_w']*S*(1+(r['resid_ret'] if r['resolved'] else -0.50)) for r in hit]
    at_ex=[max(x,0.0) for x in at_ex]
    def frac_lt(v,t): return sum(1 for x in v if x<t)/len(v)
    print(f" N={N:2d} S=${S:5.2f}: residual at scale-out median ${st.median(at_so):.2f}; "
          f"<$1: {frac_lt(at_so,1)*100:.1f}% | at 15m exit median ${st.median(at_ex):.2f}; "
          f"<$1: {frac_lt(at_ex,1)*100:.1f}%  <$0.11(p90 gas): {frac_lt(at_ex,0.1055)*100:.1f}%  "
          f"<$0.0084(median gas): {frac_lt(at_ex,0.0084)*100:.1f}%")
print(f" (n scale-outs = {len(hit)} of {len(lad)} entries, {len(set(m for (m,s,e),r in zip(E,lad) if r['tp_hit']))} clusters)")

print("\n"+"="*100)
print("### TOTAL fixed-cost drag (not the increment): n_tx * g / S, vs the 114bp toll")
ntx=st.mean([1+(1 if r['tp_hit'] else 0)+(1 if r['resolved'] else 0) for r in lad])
print(f" mean n_tx for the ladder = {ntx:.2f}")
for k,g in G.items():
    print(f"   {k:>28}: N=5 (S=$12) {ntx*g/12*100:6.2f}% of position | N=12 (S=$5) {ntx*g/5*100:6.2f}% | "
          f"N=20 (S=$3) {ntx*g/3*100:6.2f}%")

print("\n"+"="*100)
print("### HEADLINE ARM: best laddered cell (f=0.75, tp=+10%), 15m, survivor_cell entries,")
print("### conv A (mark), fill=nextopen(strict), toll 1.14% RT, B=$60, MEASURED MEDIAN gas $0.0084/tx")
g=80001e-9*SOL_USD
lad=[evaluate(m,s,e,0.75,0.10,'A','nextopen') for m,s,e in E]
sng=[evaluate(m,s,e,0,0,'A','nextopen') for m,s,e in E]
resol=sum(r['resolved'] for r in sng)/len(sng)
for N in [5,12]:
    for dl,dv in [('-30%',-0.30),('-50%',-0.50),('-100%',-1.00)]:
        v=netvals(lad,dv,g,60/N); s=netvals(sng,dv,g,60/N)
        lo,hi=boot_ci(v,cl); slo,shi=boot_ci(s,cl)
        print(f" N={N:2d} drop{dl:>5}: LADDER mean {st.mean(v)*100:6.2f}% med {st.median(v)*100:6.2f}% CI[{lo*100:+.2f},{hi*100:+.2f}] "
              f"|| SINGLE mean {st.mean(s)*100:6.2f}% med {st.median(s)*100:6.2f}% CI[{slo*100:+.2f},{shi*100:+.2f}]")
print(f" n={len(E)} clusters={len(set(cl))} resolution={resol*100:.1f}%")
# 3% toll sensitivity
for N in [12]:
    v=netvals(lad,-0.50,g,60/N,toll=0.030); print(f" 3.0% toll sensitivity, N=12, drop-50%: LADDER mean {st.mean(v)*100:.2f}% med {st.median(v)*100:.2f}%")
# same-universe random-bar control under identical machinery
Er=ENTRIES['random']; clr=[x[0] for x in Er]
rs=netvals([evaluate(m,s,e,0,0,'A','nextopen') for m,s,e in Er],-0.50,g,5.0)
rlo,rhi=boot_ci(rs,clr)
print(f" same-universe RANDOM-BAR control (single exit, N=12, drop-50%): mean {st.mean(rs)*100:.2f}% med {st.median(rs)*100:.2f}% "
      f"CI[{rlo*100:+.2f},{rhi*100:+.2f}] n={len(Er)} k={len(set(clr))}")
