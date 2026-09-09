"""Evaluator for LATE_MOMENTUM_REPLICATION_PREREGISTRATION.md. Event-driven over the v3 tape. Paper only."""
import sqlite3, json, collections, statistics as st, random, sys, time
from scripts.trading_bot.memebot.handling_test import buy, sell, TX_FEE
TAPE="research/midcap/tape_v3.sqlite"; CAP="research/midcap/birth_stream_forward_v3_20260908T1901.sqlite"
SIZE=200_000_000
def load():
    c=sqlite3.connect(f"file:{CAP}?mode=ro",uri=True); t=sqlite3.connect(f"file:{TAPE}?mode=ro",uri=True)
    births={}
    for slot,oj in c.execute("select slot,observation_json from create_observation where succeeded=1"):
        f=json.loads(oj)["fields"]; births.setdefault(f["mint"],(slot,int(f["timestamp"]),f["creator"]))
    done={m:s for m,s in t.execute("select mint,min(slot) from event where name='CompleteEvent' group by mint")}
    tape=collections.defaultdict(list)
    q="select mint,slot,ts,recv_ns,vsol,vtok,rsol,is_buy,sol_amount,user,fee,creator_fee from trade where vsol>0 and vtok>0 order by mint,slot,seq"
    for m,slot,ts,recv,vs,vt,rs,b,sa,u,fee,cf in t.execute(q):
        if m not in births: continue
        fb=int(round(1e4*(fee or 0)/sa)) if sa else 95; cb=int(round(1e4*(cf or 0)/sa)) if sa else 30
        tape[m].append((slot,recv/1e9,vs,vt,rs or 0,b,sa,u,fb,cb,ts))
    return births,done,tape
def run_mint(rows,s0,ts0,done_slot,L,placebo,rng):
    """returns list of net lamports per position"""
    out=[]; pos=None; entries=0; w60=collections.deque(); w10=collections.deque(); trig_t=None; exit_t=None
    p60=collections.deque()   # (t,price)
    n=len(rows); i=0
    for i,(slot,t,vs,vt,rs,b,sa,u,fb,cb,ts) in enumerate(rows):
        price=vs/vt
        while w60 and w60[0][0]<t-60: w60.popleft()
        while w10 and w10[0][0]<t-10: w10.popleft()
        p60.append((t,price))
        while len(p60)>1 and p60[1][0]<=t-60: p60.popleft()
        price60=p60[0][1]
        # ---- exits first
        if pos is not None:
            pos['peak']=max(pos['peak'],price)
            if exit_t is None:
                el=t-pos['t']; sin=sum(x[2] for x in w10 if x[1]); sout=sum(x[2] for x in w10 if not x[1])
                if (el>=37 and sout>sin) or price<=0.85*pos['peak'] or el>=200 or (done_slot and slot>=done_slot): exit_t=t
            if exit_t is not None and t>=exit_t+L and not (done_slot and slot>=done_slot):
                got=sell(vs,vt,pos['tok'],fb,cb); out.append(got-pos['cost']-TX_FEE); pos=None; exit_t=None
        # ---- entry
        if pos is None and entries<3 and trig_t is None:
            age=ts-ts0; prog=rs/85e9
            if 40<=age<=600 and 0.12<=prog<=0.45:
                if placebo: ok = rng.random()<0.02
                else:
                    buyers=len({x[3] for x in w60 if x[1]}); sin=sum(x[2] for x in w10 if x[1])
                    ok = buyers>=15 and sin>=1e9 and price/price60>=0.95
                if ok: trig_t=t
        if pos is None and trig_t is not None and t>=trig_t+L:
            if not (done_slot and slot>=done_slot):
                tok,_,_=buy(vs,vt,SIZE,fb,cb); pos={'tok':tok,'cost':SIZE+TX_FEE,'t':t,'peak':price}; entries+=1
            trig_t=None
        w60.append((t,b,sa,u)); w10.append((t,b,sa))
    if pos is not None:            # never exited
        out.append(-pos['cost'] if exit_t is None or True else 0)   # charged -100% (dropout)
    return out
def evaluate(mints,births,done,tape,L,placebo=False,seed=0,drop=-1.0):
    rng=random.Random(seed); per_mint=[]; groups_c=[]; groups_s=[]; npos=0; tot=0
    for m in mints:
        rows=tape.get(m); 
        if not rows: continue
        s0,ts0,cr=births[m]; res=run_mint(rows,s0,ts0,done.get(m),L,placebo,rng)
        if not res: continue
        r=[(x/SIZE if x>-SIZE else drop) for x in res]; per_mint.append(st.fmean(r)); npos+=len(r); tot+=sum(res)/1e9
        groups_c.append(cr); groups_s.append(ts0//1800)
    if not per_mint: return None
    def boot(g,n=1500):
        by=collections.defaultdict(list)
        for v,k in zip(per_mint,g): by[k].append(v)
        keys=list(by); ms=[]; rr=random.Random(1)
        for _ in range(n):
            sm=[x for k in (rr.choice(keys) for _ in keys) for x in by[k]]; ms.append(sum(sm)/len(sm))
        ms.sort(); return ms[int(.025*n)],ms[int(.975*n)]
    l1,h1=boot(groups_c); l2,h2=boot(groups_s)
    v=sorted(per_mint)
    return dict(mints=len(per_mint),positions=npos,mean=st.fmean(per_mint),median=v[len(v)//2],win=sum(x>0 for x in per_mint)/len(v),sol=tot,ci=(min(l1,l2),max(h1,h2)))
def main():
    births,done,tape=load(); mints=sorted(births,key=lambda m:births[m][0]); cut=int(len(mints)*.6); ex,ho=mints[:cut],mints[cut:]
    print(f"mints {len(mints)} explore {len(ex)} holdout {len(ho)}",flush=True)
    def show(lab,r):
        if r is None: print(f"  {lab}: no positions"); return
        print(f"  {lab:28} mints {r['mints']:5d} pos {r['positions']:5d} mean {r['mean']*100:+6.2f}% median {r['median']*100:+6.2f}% win {r['win']*100:3.0f}%  bot P&L {r['sol']:+8.2f} SOL  ci [{r['ci'][0]*100:+.2f}%,{r['ci'][1]*100:+.2f}%]",flush=True)
    print("EXPLORATION (60%):")
    res={}
    for L in (0,2,5,13):
        res[L]=evaluate(ex,births,done,tape,L); show(f"rule  L={L}s",res[L])
    for L in (0,2):
        show(f"PLACEBO L={L}s (no flow cond.)",evaluate(ex,births,done,tape,L,placebo=True))
    show("rule L=2s, dropout -50%",evaluate(ex,births,done,tape,2,drop=-0.5))
    print("HOLDOUT (40%) — single read, pre-declared primary L=2s:")
    r=evaluate(ho,births,done,tape,2); show("HOLDOUT rule L=2s",r)
    p=evaluate(ho,births,done,tape,2,placebo=True); show("HOLDOUT placebo L=2s",p)
    json.dump({'explore':{str(k):v for k,v in res.items()},'holdout':r,'holdout_placebo':p},open("research/midcap/late_momentum_result.json","w"),default=str)
if __name__=="__main__": main()
