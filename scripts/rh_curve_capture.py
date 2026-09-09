"""Integration-only raw curve-event extension for the owner of rh_tape.py.

No network loop, keys, orders or financial evaluator. Keep v3 and curve cursors
separate. Caller supplies original HTTP-decoded JSON-RPC bytes, not reserialized
logs. Unknown emitters remain unverified even when their event topic matches.
"""
import hashlib
import json
import re
import sqlite3
import time

from scripts.rh_curve_probe import ADDRESS,signature,topic
from scripts.rh_capture_contract import ensure_gap_table,record_gap

HASH=re.compile(r'0x[0-9a-fA-F]{64}')
HEX=re.compile(r'0x(?:[0-9a-fA-F]{2})*')


def request_plans(factory,abis,lo,hi):
    if not ADDRESS.fullmatch(factory) or type(lo) is not int or type(hi) is not int or not 0<=lo<=hi:
        raise ValueError('request coordinates')
    by={a['name']:a for a in abis}
    required=['TokenLaunched','CurveBuy','CurveSell','CurveCompleted']
    if any(n not in by for n in required):raise ValueError('missing pinned ABI shapes')
    common={'fromBlock':hex(lo),'toBlock':hex(hi)}
    return {'pons_launch':common|{'address':factory,'topics':[topic(signature(by['TokenLaunched']))]},
            'pons_curve_shape':common|{'topics':[[topic(signature(by[n])) for n in required[1:]]]}}


def schema(db):
    ensure_gap_table(db)
    db.executescript('''CREATE TABLE IF NOT EXISTS curve_request(
        sha TEXT PRIMARY KEY,raw_sha TEXT,stream TEXT,lo INTEGER,hi INTEGER,sent_ns INTEGER,received_ns INTEGER,
        raw BLOB NOT NULL,raw_durable_ns INTEGER);
        CREATE TABLE IF NOT EXISTS curve_log(
        response_sha TEXT,ordinal INTEGER,block INTEGER,block_hash TEXT,tx_index INTEGER,log_index INTEGER,
        tx_hash TEXT,emitter TEXT,topic0 TEXT,identity_status TEXT,PRIMARY KEY(response_sha,ordinal));
        CREATE TABLE IF NOT EXISTS curve_issue(response_sha TEXT,reason TEXT);
        CREATE TABLE IF NOT EXISTS curve_cursor(stream TEXT PRIMARY KEY,hi INTEGER);''')


def validate_log(g,lo,hi,allowed_topics):
    # Preserve canonical order and reorg identity; never infer them from row order.
    for k in ['blockHash','transactionHash']:
        if not isinstance(g.get(k),str) or not HASH.fullmatch(g[k]):raise ValueError('missing canonical hash')
    if not isinstance(g.get('address'),str) or not ADDRESS.fullmatch(g['address']):raise ValueError('emitter shape')
    if g.get('removed') is not False:raise ValueError('removed or unknown canonical status')
    coords=[]
    for k in ['blockNumber','transactionIndex','logIndex']:
        v=g.get(k)
        if not isinstance(v,str) or not re.fullmatch('0x[0-9a-fA-F]+',v):raise ValueError('canonical coordinate absent')
        coords.append(int(v,16))
    if not lo<=coords[0]<=hi:raise ValueError('out of request range')
    if not isinstance(g.get('topics'),list) or not g['topics'] or any(not isinstance(t,str) or not HASH.fullmatch(t) for t in g['topics']):
        raise ValueError('topic shape')
    if g['topics'][0].lower() not in allowed_topics:raise ValueError('unexpected topic')
    if not isinstance(g.get('data'),str) or not HEX.fullmatch(g['data']) or (len(g['data'])-2)%64:
        raise ValueError('ABI word shape')
    return coords


def append_response(db,stream,lo,hi,request_id,raw,sent_ns,received_ns,allowed_topics):
    """FULL raw commit precedes derived rows. Error/gap records prevent cursor advance.

    This checks the envelope, coordinates and topic/data shape only. It does NOT
    attest provider completeness, event ABI, deployed code, token identity or finality.
    Caller must separately reconcile block hashes before treating a prefix canonical.
    """
    if type(raw) is not bytes or type(sent_ns) is not int or type(received_ns) is not int or not 0<sent_ns<=received_ns:
        raise ValueError('raw/clock evidence required')
    if len(raw)>8*1024**2 or type(lo) is not int or type(hi) is not int or not 0<=lo<=hi:raise ValueError('bounds')
    db.execute('PRAGMA synchronous=FULL');raw_sha=hashlib.sha256(raw).hexdigest()
    # Equal empty responses from different requests are distinct observations.
    binding=json.dumps([stream,lo,hi,request_id,sent_ns,received_ns,raw_sha],separators=(',',':')).encode()
    sha=hashlib.sha256(binding).hexdigest()
    db.execute('INSERT OR IGNORE INTO curve_request VALUES(?,?,?,?,?,?,?,?,NULL)',(sha,raw_sha,stream,lo,hi,sent_ns,received_ns,raw));db.commit()
    db.execute('UPDATE curve_request SET raw_durable_ns=COALESCE(raw_durable_ns,?) WHERE sha=?',(time.time_ns(),sha));db.commit()
    try:
        j=json.loads(raw)
        if j.get('id')!=request_id or j.get('error') or not isinstance(j.get('result'),list):raise ValueError('RPC envelope refused')
        parsed=[];seen=set()
        for i,g in enumerate(j['result']):
            b,tx,log=validate_log(g,lo,hi,allowed_topics)
            identity=(g['blockHash'],tx,log)
            if identity in seen:raise ValueError('duplicate canonical log in response')
            seen.add(identity)
            parsed.append((sha,i,b,g['blockHash'],tx,log,g['transactionHash'],g['address'],g['topics'][0],
                           'UNATTESTED_SOURCE_SHAPE_NOT_CANONICAL'))
        old=db.execute('SELECT hi FROM curve_cursor WHERE stream=?',(stream,)).fetchone()
        if old and lo>old[0]+1:raise ValueError('CURSOR_RANGE_HOLE')
        db.executemany('INSERT OR IGNORE INTO curve_log VALUES(?,?,?,?,?,?,?,?,?,?)',parsed)
        db.execute('INSERT INTO curve_cursor VALUES(?,?) ON CONFLICT(stream) DO UPDATE SET hi=MAX(hi,excluded.hi)',(stream,hi))
        db.commit();return sha,len(parsed)
    except Exception as e:
        db.rollback();reason=str(e) if isinstance(e,ValueError) else type(e).__name__
        db.execute('INSERT INTO curve_issue VALUES(?,?)',(sha,reason))
        record_gap(db,stream,lo,hi,reason,time.time_ns());db.commit();raise
