"""Robinhood Chain (4663) tape v2: chain-wide Uniswap-v3 Swap + PoolCreated logs AND Pons V2 curve events, one shared
public-RPC loop. Integrates Codex's helpers (handoff 476): next_range() catch-up without head-minus-cap skipping,
capture_gap table (no cursor advance on failure), rh_curve_capture request plans with FULL raw-response retention.
Read-only. Streams keep separate cursors: v3 (poll/cursor tables) and curve (curve_cursor via append_response)."""
import json,sqlite3,time,urllib.request,zlib,datetime,os,sys
sys.path.insert(0,'.')
from scripts.rh_capture_contract import next_range,ensure_gap_table,record_gap
from scripts import rh_curve_capture as K
RPC="https://rpc.mainnet.chain.robinhood.com"; DB="research/midcap/rh_tape.sqlite"
SWAP="0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
POOLCREATED="0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
FACTORY="0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"   # Pons V2 current factory (Codex, PONS_V2_DISCOVERY_20260909)
ABIS=[{'name':'TokenLaunched','inputs':[{'type':t} for t in ['address','address','address','address','uint256','uint256']]},
      {'name':'CurveBuy','inputs':[{'type':t} for t in ['address','address','uint256','uint256','uint256','uint256']]},
      {'name':'CurveSell','inputs':[{'type':t} for t in ['address','address','uint256','uint256','uint256','uint256']]},
      {'name':'CurveCompleted','inputs':[{'type':t} for t in ['address','uint256','uint256']]}]
TOPICS={a['name']:K.topic(K.signature(a)).lower() for a in ABIS}
UA={"content-type":"application/json","User-Agent":"Mozilla/5.0"}
_id=[0]
def rpc_raw(m,p):
    """returns (request_id, raw_bytes, sent_ns, received_ns, err)"""
    _id[0]+=1; rid=_id[0]; b=json.dumps({"jsonrpc":"2.0","id":rid,"method":m,"params":p}).encode(); err=None
    for i in range(5):
        sent=time.time_ns()
        try:
            raw=urllib.request.urlopen(urllib.request.Request(RPC,data=b,headers=UA),timeout=40).read(); return rid,raw,sent,time.time_ns(),None
        except Exception as e: err=str(e)[:120]; time.sleep(2*(i+1))
    return rid,None,None,None,err
def rpc(m,p):
    rid,raw,s,r,err=rpc_raw(m,p)
    if raw is None: return None,err
    j=json.loads(raw); return (None,str(j["error"])[:120]) if "error" in j else (j["result"],None)
def s256(h):
    v=int(h,16); return v-(1<<256) if v>=(1<<255) else v
def call(to,data):
    r,_=rpc("eth_call",[{"to":to,"data":data},"latest"]); return r
db=sqlite3.connect(DB,timeout=60); db.execute("PRAGMA journal_mode=WAL")
db.executescript("""CREATE TABLE IF NOT EXISTS swap(block INT, tx TEXT, logidx INT, pool TEXT, sender TEXT, recipient TEXT, amount0 TEXT, amount1 TEXT, sqrtp TEXT, liq TEXT, tick INT, PRIMARY KEY(tx,logidx));
CREATE TABLE IF NOT EXISTS pool(pool TEXT PRIMARY KEY, token0 TEXT, token1 TEXT, fee INT, first_block INT, created_block INT);
CREATE TABLE IF NOT EXISTS blocktime(block INT PRIMARY KEY, ts INT);
CREATE TABLE IF NOT EXISTS rawlog(block_lo INT, block_hi INT, recv_ns INT, zjson BLOB);
CREATE TABLE IF NOT EXISTS rawpc(block_lo INT, block_hi INT, recv_ns INT, zjson BLOB, err TEXT);
CREATE TABLE IF NOT EXISTS poll(at INT, lo INT, hi INT, swaps INT, new_pools INT, err TEXT);
CREATE TABLE IF NOT EXISTS cursor(k TEXT PRIMARY KEY, v INT);""")
ensure_gap_table(db); K.schema(db); db.commit()
def ingest_swaps(logs):
    newp=0
    for g in logs:
        d=g["data"][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
        if len(w)<5: continue
        pool=g["address"].lower(); blk=int(g["blockNumber"],16)
        db.execute("INSERT OR IGNORE INTO swap VALUES(?,?,?,?,?,?,?,?,?,?,?)",(blk,g["transactionHash"],int(g["logIndex"],16),pool,"0x"+g["topics"][1][-40:],"0x"+g["topics"][2][-40:],str(s256(w[0])),str(s256(w[1])),str(int(w[2],16)),str(int(w[3],16)),s256(w[4])))
        if not db.execute("SELECT 1 FROM pool WHERE pool=?",(pool,)).fetchone():
            t0a=call(pool,"0x0dfe1681"); t1a=call(pool,"0xd21220a7"); fee=call(pool,"0xddca3f43"); time.sleep(0.2)
            db.execute("INSERT OR IGNORE INTO pool VALUES(?,?,?,?,?,?)",(pool,("0x"+t0a[-40:]) if t0a else None,("0x"+t1a[-40:]) if t1a else None,int(fee,16) if fee else None,blk,None)); newp+=1
    return newp
def v3_range(lo,hi):
    """one v3 Swap + PoolCreated query over [lo,hi]; returns (nswaps,newpools) or None on failure (gap recorded, no advance)"""
    logs,err=rpc("eth_getLogs",[{"fromBlock":hex(lo),"toBlock":hex(hi),"topics":[SWAP]}])
    if logs is None:
        record_gap(db,"v3_swap",lo,hi,"RPC:"+(err or "?"),time.time_ns()); db.execute("INSERT INTO poll VALUES(?,?,?,?,?,?)",(int(time.time()),lo,hi,0,0,err)); db.commit(); return None
    db.execute("INSERT INTO rawlog VALUES(?,?,?,?)",(lo,hi,time.time_ns(),zlib.compress(json.dumps(logs).encode())))
    newp=ingest_swaps(logs)
    pc,err2=rpc("eth_getLogs",[{"fromBlock":hex(lo),"toBlock":hex(hi),"topics":[POOLCREATED]}])
    db.execute("INSERT INTO rawpc VALUES(?,?,?,?,?)",(lo,hi,time.time_ns(),zlib.compress(json.dumps(pc).encode()) if pc is not None else None,err2))
    if pc is None: record_gap(db,"v3_poolcreated",lo,hi,"RPC:"+(err2 or "?"),time.time_ns())
    for g in (pc or []):
        d=g["data"][2:]; w=[d[i:i+64] for i in range(0,len(d),64)]
        if len(w)>=2:
            pool="0x"+w[1][-40:].lower(); db.execute("INSERT OR IGNORE INTO pool VALUES(?,?,?,?,?,?)",(pool,"0x"+g["topics"][1][-40:],"0x"+g["topics"][2][-40:],int(g["topics"][3],16),None,int(g["blockNumber"],16)))
            db.execute("UPDATE pool SET created_block=? WHERE pool=? AND created_block IS NULL",(int(g["blockNumber"],16),pool))
    for b in range(lo - lo%50, hi+1, 50):
        if not db.execute("SELECT 1 FROM blocktime WHERE block=?",(b,)).fetchone():
            r,_=rpc("eth_getBlockByNumber",[hex(b),False]); time.sleep(0.15)
            if r: db.execute("INSERT OR IGNORE INTO blocktime VALUES(?,?)",(b,int(r["timestamp"],16)))
    db.execute("INSERT INTO poll VALUES(?,?,?,?,?,?)",(int(time.time()),lo,hi,len(logs),newp,None)); db.execute("INSERT OR REPLACE INTO cursor VALUES('hi',?)",(hi,)); db.commit()
    return len(logs),newp
def curve_range(lo,hi):
    """Pons V2 streams with FULL raw retention via Codex's append_response; failures record gaps and do not advance."""
    out={}
    for stream,plan in K.request_plans(FACTORY,ABIS,lo,hi).items():
        allowed={TOPICS['TokenLaunched']} if stream=='pons_launch' else {TOPICS['CurveBuy'],TOPICS['CurveSell'],TOPICS['CurveCompleted']}
        rid,raw,sent,recv,err=rpc_raw("eth_getLogs",[plan])
        if raw is None: record_gap(db,stream,lo,hi,"RPC:"+(err or "?"),time.time_ns()); db.commit(); out[stream]=None; continue
        try: out[stream]=K.append_response(db,stream,lo,hi,rid,raw,sent,recv,allowed)[1]
        except Exception as e: out[stream]=None   # append_response already recorded the issue/gap
    return out
# ---- one-time backfill of the three v3 holes Codex found (marked REPAIRED, not hidden) ----
_cur0=(db.execute("SELECT v FROM cursor WHERE k='hi'").fetchone() or (None,))[0]
for lo,hi in ((58711396,58711800),(58713802,58714891),(58781845,58783268)):
    if db.execute("SELECT 1 FROM capture_gap WHERE stream='v3_swap' AND lo=? AND hi=? AND status='REPAIRED'",(lo,hi)).fetchone(): continue
    r=v3_range(lo,hi)
    if r is not None:
        record_gap(db,"v3_swap",lo,hi,"HEAD_MINUS_CAP_SKIP_v1",time.time_ns()); db.execute("UPDATE capture_gap SET status='REPAIRED' WHERE stream='v3_swap' AND lo=? AND hi=?",(lo,hi)); db.commit()
        print(f"backfilled v3 hole {lo}-{hi}: {r[0]} swaps",flush=True)
if _cur0 is not None: db.execute("INSERT OR REPLACE INTO cursor VALUES('hi',?)",(_cur0,)); db.commit()   # backfill must not rewind the live cursor
last=(db.execute("SELECT v FROM cursor WHERE k='hi'").fetchone() or (None,))[0]
ccur={s:(db.execute("SELECT hi FROM curve_cursor WHERE stream=?",(s,)).fetchone() or (None,))[0] for s in ('pons_launch','pons_curve_shape')}
print(f"rh_tape v2 start {datetime.datetime.now(datetime.UTC).isoformat()} v3 cursor {last} curve cursors {ccur}",flush=True)
while True:
    t0=time.time(); head,err=rpc("eth_blockNumber",[])
    if head is None: db.execute("INSERT INTO poll VALUES(?,?,?,?,?,?)",(int(time.time()),None,None,0,0,err)); db.commit(); time.sleep(20); continue
    head=int(head,16); done_v3=0
    # v3: walk forward in <=2000-block chunks until caught up (no skipping)
    while True:
        lo,hi=next_range(last,head); r=v3_range(lo,hi)
        if r is None: break
        last=hi; done_v3+=r[0]
        if hi>=head: break
    # curve streams: same catch-up discipline, own cursors
    cstats={}
    while True:
        c0=min(ccur[s] if ccur[s] is not None else head-400 for s in ccur); lo,hi=next_range(c0 if any(v is not None for v in ccur.values()) else None,head)
        res=curve_range(lo,hi)
        for s,v in res.items():
            if v is not None: ccur[s]=hi; cstats[s]=cstats.get(s,0)+v
        if any(v is None for v in res.values()) or hi>=head: break
    print(json.dumps({"utc":datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S'),"head":head,"v3_swaps":done_v3,"curve":cstats,"v3_cursor":last,"secs":round(time.time()-t0)}),flush=True)
    time.sleep(max(5,20-(time.time()-t0)))
