"""Pure range-planning and separate query-coverage audit. No price/outcome access.

Integration helper for the owner of rh_tape.py; does not modify or restart it.
Coverage of requested block ranges is not proof of complete RPC log responses.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import time


def next_range(cursor,head,*,max_blocks=2000,overlap=20,warmup=400):
    if type(head) is not int or head<0 or (cursor is not None and (type(cursor) is not int or cursor<0)):
        raise ValueError('invalid block height')
    if not 0<=overlap<max_blocks-1 or warmup<0:raise ValueError('invalid range budget')
    if cursor is not None and head<cursor:raise ValueError('HEAD_REGRESSED_RECONCILE_BEFORE_ADVANCE')
    lo=max(0,head-warmup) if cursor is None else max(0,cursor-overlap)
    return lo,min(head,lo+max_blocks-1)


def missing_ranges(ranges):
    """Union inclusive intervals, so subsequent backfills really can repair holes."""
    merged=[]
    for lo,hi in sorted(ranges):
        if type(lo) is not int or type(hi) is not int or lo<0 or hi<lo:raise ValueError('invalid interval')
        if merged and lo<=merged[-1][1]+1:merged[-1][1]=max(merged[-1][1],hi)
        else:merged.append([lo,hi])
    return [(a[1]+1,b[0]-1) for a,b in zip(merged,merged[1:])]


def ensure_gap_table(db):
    db.execute('''CREATE TABLE IF NOT EXISTS capture_gap(
        id INTEGER PRIMARY KEY, stream TEXT NOT NULL, lo INTEGER NOT NULL, hi INTEGER NOT NULL,
        detected_ns INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
        CHECK(lo>=0 AND hi>=lo), UNIQUE(stream,lo,hi,reason))''')


def record_gap(db,stream,lo,hi,reason,detected_ns):
    if not stream or not reason or type(detected_ns) is not int or detected_ns<=0:raise ValueError('gap identity')
    missing_ranges([(lo,hi)])
    db.execute('INSERT OR IGNORE INTO capture_gap(stream,lo,hi,detected_ns,reason,status) VALUES(?,?,?,?,?,?)',
               (stream,lo,hi,detected_ns,reason,'UNKNOWN_UNREPAIRED'))


def audit(source,out):
    if not source.exists() or out.exists() or source.resolve()==out.resolve():raise ValueError('existing source / fresh output required')
    # No token, swap, price, bar or return table is read.
    with sqlite3.connect('file:'+str(source.resolve())+'?mode=ro',uri=True,timeout=5) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        rows=c.execute('SELECT lo,hi FROM poll WHERE err IS NULL AND lo IS NOT NULL AND hi IS NOT NULL').fetchall()
        counts=c.execute('SELECT COUNT(*),MAX(at),SUM(err IS NOT NULL) FROM poll').fetchone()
    gaps=missing_ranges(rows);now=time.time_ns()
    with sqlite3.connect(out) as d:
        ensure_gap_table(d)
        d.execute('CREATE TABLE manifest(source TEXT, observed_ns INTEGER, source_poll_rows INTEGER, last_poll INTEGER, reported_errors INTEGER, limitation TEXT)')
        d.execute('INSERT INTO manifest VALUES(?,?,?,?,?,?)',(str(source),now,*counts,
            'Only successful v3 Swap query ranges. Not a chain census, reorg audit, or PoolCreated coverage.'))
        for lo,hi in gaps:record_gap(d,'v3_swap',lo,hi,'SUCCESSFUL_QUERY_RANGE_HOLE',now)
    return {'status':'QUERY_COVERAGE_ONLY_NO_TRADE','poll_rows':counts[0],
            'gaps':[{'lo':lo,'hi':hi,'blocks':hi-lo+1} for lo,hi in gaps],
            'unqueried_blocks':sum(hi-lo+1 for lo,hi in gaps)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();print(json.dumps(audit(a.source,a.out),sort_keys=True))
