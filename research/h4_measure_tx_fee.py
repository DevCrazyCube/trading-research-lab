import sqlite3, zlib, json, random, statistics as st
c=sqlite3.connect('file:research/b11a/b11a_bodies.sqlite?mode=ro',uri=True)

def sigs(program, limit=4000):
    q="""select distinct signature from instruction
         where program_id=? and idl_name in ('buy','sell','buy_v2','sell_v2','buy_exact_sol_in','buy_exact_quote_in_v2','buy_exact_quote_in')"""
    rows=[r[0] for r in c.execute(q,(program,))]
    random.seed(7); random.shuffle(rows)
    return rows[:limit]

def fees(sigl):
    out=[]
    CH=400
    for i in range(0,len(sigl),CH):
        chunk=sigl[i:i+CH]
        qm=",".join("?"*len(chunk))
        for sg,blob in c.execute("select signature,raw_zlib from raw_transaction where signature in (%s)"%qm, chunk):
            try:
                j=json.loads(zlib.decompress(blob))
            except Exception: continue
            res=j.get('result') or {}
            meta=res.get('meta') or {}
            fee=meta.get('fee')
            tx=res.get('transaction')
            nsig=None
            if isinstance(tx,list):  # base64
                nsig=None
            if fee is None: continue
            # count writable account balances change to detect ATA rent? skip
            out.append((sg,fee,meta.get('computeUnitsConsumed')))
    return out

for prog,label in [('pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA','PumpSwap AMM'),
                   ('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P','pump.fun curve')]:
    s=sigs(prog)
    f=fees(s)
    v=sorted(x[1] for x in f)
    if not v: print(label,"no fees"); continue
    n=len(v)
    def q(p): return v[min(n-1,int(p*n))]
    print(f"{label}: n_tx={n} fee_lamports p10={q(.10)} p25={q(.25)} median={q(.50)} mean={st.mean(v):.0f} p75={q(.75)} p90={q(.90)} p99={q(.99)} max={v[-1]}")
    cu=[x[2] for x in f if x[2]]
    if cu: print("   CU consumed median", st.median(cu))
