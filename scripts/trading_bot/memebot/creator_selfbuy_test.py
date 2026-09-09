"""Evaluator for CREATOR_SELFBUY_PREREGISTRATION.md. Reuses the exact-fill machinery of handling_test."""
import sqlite3,json,collections,statistics as st,random,sys,time
from scripts.trading_bot.memebot.handling_test import buy,sell,TX_FEE
TAPE="research/midcap/tape_v3.sqlite"; CAP="research/midcap/birth_stream_forward_v3_20260908T1901.sqlite"; SIZE=50_000_000
def load():
    c=sqlite3.connect(f"file:{CAP}?mode=ro",uri=True); t=sqlite3.connect(f"file:{TAPE}?mode=ro",uri=True)
    births={}
    for slot,oj in c.execute("select slot,observation_json from create_observation where succeeded=1"):
        f=json.loads(oj)["fields"]; births.setdefault(f["mint"],(slot,int(f["timestamp"]),f["creator"],f.get("user")))
    done={m:s for m,s in t.execute("select mint,min(slot) from event where name='CompleteEvent' group by mint")}
    tape=collections.defaultdict(list)
    for m,slot,ts,vs,vt,b,sa,u,fee,cf in t.execute("select mint,slot,ts,vsol,vtok,is_buy,sol_amount,user,fee,creator_fee from trade where vsol>0 and vtok>0 order by mint,slot,seq"):
        if m in births: tape[m].append((slot,ts,vs,vt,b,sa,u,int(round(1e4*(fee or 0)/sa)) if sa else 95,int(round(1e4*(cf or 0)/sa)) if sa else 30))
    return births,done,tape
def selfbuy(rows,s0,creators):
    tot=0;last=None
    for slot,ts,vs,vt,b,sa,u,fb,cb in rows:
        if slot>s0+2: break
        if b and u in creators: tot+=sa; last=slot
    return tot/1e9,last
def sim(rows,k,done_slot,exit_rule):
    slot0,ts0,vs,vt,b,sa,u,fb,cb=rows[k]; tok,_,_=buy(vs,vt,SIZE,fb,cb); cost=SIZE+TX_FEE; p0=vs/vt; peak=p0; last=None
    for j in range(k+1,len(rows)):
        slot,ts,vs,vt,b,sa,u,fb,cb=rows[j]
        if done_slot is not None and slot>=done_slot: break
        p=vs/vt; peak=max(peak,p); last=j
        if exit_rule=="15m" and ts-ts0>=900: return sell(vs,vt,tok,fb,cb)-cost-TX_FEE
        if exit_rule=="60m" and ts-ts0>=3600: return sell(vs,vt,tok,fb,cb)-cost-TX_FEE
        if exit_rule=="H4" and peak>=1.5*p0 and p<=0.85*peak: return sell(vs,vt,tok,fb,cb)-cost-TX_FEE
    if last is None: return None
    slot,ts,vs,vt,b,sa,u,fb,cb=rows[last]; return sell(vs,vt,tok,fb,cb)-cost-TX_FEE
def evaluate(mints,births,done,tape,T,L,exit_rule,sizes,drop=-1.0,nboot=800):
    vals=[];cre=[];ses=[];n_sig=n_ent=n_noent=0
    for m in mints:
        if sizes[m]<T: continue
        n_sig+=1; rows=tape[m]; s0=births[m][0]; sig_slot=sizes_slot[m] if sizes_slot.get(m) is not None else s0
        k=next((i for i,r in enumerate(rows) if r[0]>=sig_slot+L),None)
        if k is None or (done.get(m) is not None and rows[k][0]>=done[m]): n_noent+=1; continue
        n_ent+=1; net=sim(rows,k,done.get(m),exit_rule); vals.append(drop if net is None else net/SIZE); cre.append(births[m][2]); ses.append(births[m][1]//1800)
    if not vals: return dict(n_sig=n_sig,n_ent=0,n_noent=n_noent)
    def boot(g):
        by=collections.defaultdict(list)
        for v,k in zip(vals,g): by[k].append(v)
        keys=list(by); rng=random.Random(2); ms=[]
        for _ in range(nboot):
            sm=[x for k in (rng.choice(keys) for _ in keys) for x in by[k]]; ms.append(sum(sm)/len(sm))
        ms.sort(); return ms[int(.025*nboot)],ms[int(.975*nboot)]
    l1,h1=boot(cre); l2,h2=boot(ses); v=sorted(vals)
    return dict(n_sig=n_sig,n_ent=n_ent,n_noent=n_noent,mean=st.fmean(vals),median=v[len(v)//2],win=sum(x>0 for x in vals)/len(vals),ci=(min(l1,l2),max(h1,h2)))
if __name__=="__main__":
    births,done,tape=load(); mints=sorted([m for m in births if tape.get(m)],key=lambda m:births[m][0])
    sizes={};sizes_slot={}
    for m in mints:
        s,l=selfbuy(tape[m],births[m][0],{births[m][2],births[m][3]}); sizes[m]=s; sizes_slot[m]=l
    cut=int(len(mints)*.6); ex,ho=mints[:cut],mints[cut:]
    print(f"launches with trades {len(mints)} | explore {len(ex)} holdout {len(ho)}")
    print("\nGRADUATION LIFT by creator self-buy (create slot + 2), whole population:")
    bins=[(0,0),(1e-9,0.2),(0.2,1),(1,5),(5,1e9)]
    for lo,hi in bins:
        sel=[m for m in mints if lo<=sizes[m]<hi] if lo>0 else [m for m in mints if sizes[m]==0]
        if not sel: continue
        g=sum(1 for m in sel if m in done); org=sum(1 for m in sel if m in done and (done[m]-births[m][0])*0.4>300)
        inst=sum(1 for m in sel if m in done and (done[m]-births[m][0])*0.4<=10)
        print(f"  self-buy {lo:>4}-{hi if hi<1e9 else 'inf':<4} SOL: n={len(sel):5d}  any-grad {g/len(sel)*100:5.2f}%  organic(>5m) {org/len(sel)*100:5.2f}%  instant(<=10s) {inst/len(sel)*100:5.2f}%")
    print("\nEXPLORATION (60%) — net return per position, dropouts -100%:")
    print(f"{'T':>4} {'L':>4} {'exit':>4} {'sig':>5} {'ent':>5} {'noent':>5} {'mean':>8} {'median':>8} {'win':>4} {'ci':>18}")
    res={}
    for T in (0.2,1,5):
        for L in (5,32,450):
            for ex_r in ("15m","60m","end"):
                r=evaluate(ex,births,done,tape,T,L,ex_r,sizes); res[(T,L,ex_r)]=r
                if r.get('n_ent'): print(f"{T:4} {L:4} {ex_r:>4} {r['n_sig']:5d} {r['n_ent']:5d} {r['n_noent']:5d} {r['mean']*100:+7.1f}% {r['median']*100:+7.1f}% {r['win']*100:3.0f}% [{r['ci'][0]*100:+.1f},{r['ci'][1]*100:+.1f}]")
                else: print(f"{T:4} {L:4} {ex_r:>4} {r['n_sig']:5d} {0:5d} {r['n_noent']:5d}   (no enterable launches)")
    # shuffled-size placebo for the primary cell on exploration
    rng=random.Random(7); sh=dict(zip(ex,rng.sample([sizes[m] for m in ex],len(ex)))); sizes_bak=dict(sizes); sizes.update(sh)
    p=evaluate(ex,births,done,tape,1,32,"60m",sizes); sizes.update(sizes_bak)
    print(f"\nPLACEBO (shuffled self-buy sizes) T=1 L=32 60m: ent {p.get('n_ent',0)} mean {p.get('mean',0)*100:+.1f}% median {p.get('median',0)*100:+.1f}%")
    r=evaluate(ho,births,done,tape,1,32,"60m",sizes,nboot=5000)
    print(f"\nHOLDOUT (single read) T=1 SOL, L=32 slots, exit 60m: sig {r['n_sig']} entered {r.get('n_ent',0)} not-enterable {r['n_noent']} mean {r.get('mean',0)*100:+.2f}% median {r.get('median',0)*100:+.2f}% win {r.get('win',0)*100:.0f}% ci [{r.get('ci',(0,0))[0]*100:+.2f},{r.get('ci',(0,0))[1]*100:+.2f}]")
    r50=evaluate(ho,births,done,tape,1,32,"60m",sizes,drop=-0.5,nboot=200); print(f"  at -50% dropout: mean {r50.get('mean',0)*100:+.2f}%")
    json.dump({str(k):v for k,v in res.items()}|{'holdout':r},open("research/midcap/creator_selfbuy_result.json","w"),default=str)
