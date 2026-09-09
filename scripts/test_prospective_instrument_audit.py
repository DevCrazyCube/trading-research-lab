"""Synthetic reproductions of current defects, plus tests of independent repair helpers.

Loads ONLY named function ASTs from reviewed scripts; never imports their runtime,
opens a real outcome database, sends Telegram, calls RPC, or runs a financial test.
Defect tests assert the observed buggy behavior for audit reproducibility, not fitness.
"""
import ast
import bisect
import collections
from pathlib import Path
import random
import sqlite3
import statistics
import unittest
import json

from scripts.rh_capture_contract import next_range,missing_ranges,ensure_gap_table,record_gap
from scripts.rh_curve_capture import schema,append_response,request_plans
from scripts.rh_curve_probe import source_event,topic,signature,Capture


def functions(name,names,extra=None):
    tree=ast.parse((Path('scripts/trading_bot/memebot')/(name+'.py')).read_text())
    tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if len(tree.body)!=len(names):raise AssertionError('reviewed function missing')
    env=dict(sqlite3=sqlite3,collections=collections,bisect=bisect,random=random,st=statistics)
    env.update(extra or {});exec(compile(tree,'reviewed-function-only','exec'),env)
    return env


class Reproductions(unittest.TestCase):
    def test_coalesce_missing_column_is_not_fallback(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close)
        c.execute('CREATE TABLE ev(avail_ns INTEGER)')
        with self.assertRaisesRegex(sqlite3.OperationalError,'recv_ns'):
            c.execute('SELECT COALESCE(avail_ns,recv_ns) FROM ev LIMIT 0')

    def test_signature_only_drops_second_wallet(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close)
        c.execute('CREATE TABLE notif(sig TEXT PRIMARY KEY,wallet TEXT)')
        c.executemany('INSERT OR IGNORE INTO notif VALUES(?,?)',[('tx','A'),('tx','B')])
        self.assertEqual(c.execute('SELECT COUNT(*) FROM notif').fetchone()[0],1)

    def test_existing_ata_owner_absent_from_transaction_keys(self):
        # A standard transfer needs sender authority and destination token account,
        # not the destination owner as a transaction account.
        account_keys=['payer','sender-ata','recipient-ata','token-program']
        token_balance_owner='recipient-owner'
        self.assertNotIn(token_balance_owner,account_keys)

    def test_coincidence_only_keeps_first_touch(self):
        f=functions('cohort_prospective_eval',{'events','signals'})
        rows=[('A','board','t1',0,1_000_000_000,'mint',1,-2_000_000,0),
              ('A','board','t2',4000,4_000_000_000_000,'mint',1,-2_000_000,0),
              ('B','board','t3',4001,4_001_000_000_000,'mint',1,-2_000_000,0)]
        per=f['events'](rows,{},'board','buy')
        # A and B coincide at 4000/4001s, but first-ever A at1s masks it.
        self.assertEqual(f['signals'](per,{},2,30,None),[])

    def test_unknown_pair_passes_original_age_gate(self):
        f=functions('cohort_prospective_eval',{'signals'})
        self.assertEqual(len(f['signals']({'m':[(1,'a'),(2,'b')]},{},2,None,2)),1)

    def test_failed_firstsight_cannot_retry(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close)
        c.execute('CREATE TABLE firstsight(mint TEXT PRIMARY KEY,zraw BLOB)')
        c.execute('INSERT INTO firstsight VALUES(?,NULL)',('m',))
        self.assertTrue(c.execute('SELECT 1 FROM firstsight WHERE mint=?',('m',)).fetchone())

    def test_upper_middle_is_not_even_sample_median(self):
        f=functions('cohort_prospective_eval',{'evaluate'})
        class NoBars:
            def bars(self,pool,since):
                return [[60,1],[21600,0.1 if pool=='a' else 2.0]]
        out,_=f['evaluate']([('a',0,None),('b',0,None)],{'a':(1,None,'a'),'b':(1,None,'b')},NoBars(),horizons=(6,))
        self.assertNotEqual(out[(6,-1)]['median'],statistics.median([.1*(1-.0114)-1,2*(1-.0114)-1]))


class RangeRepairTests(unittest.TestCase):
    def test_catchup_never_jumps_to_head_minus_cap(self):
        lo,hi=next_range(100,10000)
        self.assertEqual((lo,hi),(80,2079));self.assertLessEqual(lo,101)
    def test_overlap_and_bootstrap(self):
        self.assertEqual(next_range(None,100),(0,100))
        self.assertEqual(next_range(100,110),(80,110))
    def test_head_regression_refused(self):
        with self.assertRaisesRegex(ValueError,'REGRESSED'):next_range(100,99)
    def test_union_backfill(self):
        self.assertEqual(missing_ranges([(0,10),(20,30)]),[(11,19)])
        self.assertEqual(missing_ranges([(0,10),(20,30),(8,21)]),[])
    def test_invalid_interval_refused(self):
        for v in [(-1,2),(3,2),(1.0,2)]:
            with self.assertRaises(ValueError):missing_ranges([v])
    def test_gap_table_idempotent_explicit_unknown(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close);ensure_gap_table(c)
        for _ in range(2):record_gap(c,'swap',11,19,'cap',100)
        self.assertEqual(c.execute('SELECT lo,hi,status FROM capture_gap').fetchall(),[(11,19,'UNKNOWN_UNREPAIRED')])


class CurveExtensionTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.addCleanup(self.c.close);schema(self.c)
        self.topic='0x'+'1'*64
        self.log={'blockNumber':'0xa','transactionIndex':'0x2','logIndex':'0x3',
            'transactionHash':'0x'+'2'*64,'blockHash':'0x'+'3'*64,'address':'0x'+'4'*40,
            'topics':[self.topic],'data':'0x'+'0'*64,'removed':False}
    def append(self,log=None,lo=10,hi=10,error=None):
        raw=json.dumps({'jsonrpc':'2.0','id':1,'error':error,'result':[log or self.log]}).encode()
        return append_response(self.c,'test',lo,hi,1,raw,1,2,{self.topic})
    def test_raw_first_and_coordinates(self):
        self.append()
        self.assertEqual(self.c.execute('SELECT block,tx_index,log_index,identity_status FROM curve_log').fetchone(),
                         (10,2,3,'UNATTESTED_SOURCE_SHAPE_NOT_CANONICAL'))
        self.assertGreater(self.c.execute('SELECT raw_durable_ns FROM curve_request').fetchone()[0],2)
    def test_error_preserves_raw_and_records_gap_without_cursor(self):
        with self.assertRaises(ValueError):self.append(error={'code':-32000})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM curve_request').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM curve_cursor').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT status FROM capture_gap').fetchone()[0],'UNKNOWN_UNREPAIRED')
    def test_missing_order_and_removed_refused(self):
        for k,v in [('transactionIndex',None),('removed',True),('blockHash','bad')]:
            with self.assertRaises(ValueError):self.append(self.log|{k:v})
    def test_jump_does_not_advance(self):
        self.append()
        with self.assertRaisesRegex(ValueError,'CURSOR_RANGE_HOLE'):
            self.append(self.log|{'blockNumber':'0x14'},lo=20,hi=20)
        self.assertEqual(self.c.execute('SELECT hi FROM curve_cursor').fetchone()[0],10)
    def test_source_event_and_curve_topic_are_separate_from_v3(self):
        src='event CurveBuy(address indexed buyer,uint256 amount);'
        abi=source_event(src,'CurveBuy')
        self.assertEqual(signature(abi),'CurveBuy(address,uint256)')
        self.assertTrue(abi['inputs'][0]['indexed']);self.assertFalse(abi['inputs'][1]['indexed'])
        with self.assertRaises(ValueError):request_plans('0x'+'4'*40,[abi],0,10)
    def test_no_rpc_send(self):
        c=object.__new__(Capture)
        with self.assertRaisesRegex(ValueError,'read-only'):c.rpc('eth_sendRawTransaction',[])
    def test_identical_empty_bodies_keep_distinct_request_bindings(self):
        raw=b'{"id":1,"result":[]}'
        for lo,hi in [(0,10),(11,20)]:append_response(self.c,'test',lo,hi,1,raw,lo+1,hi+2,{self.topic})
        self.assertEqual(self.c.execute('SELECT COUNT(*),COUNT(DISTINCT raw_sha) FROM curve_request').fetchone(),(2,1))


if __name__=='__main__':unittest.main()
