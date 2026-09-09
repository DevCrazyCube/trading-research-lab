import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch
import websocket
from scripts import fomo_probe as F
from scripts.fomo_probe import digest, inspect_frames


class ProbeTests(unittest.TestCase):
    def test_missing_replay_is_unknown(self):
        r = inspect_frames([(10**12, 1, json.dumps({'type':'alert','ts':999000}).encode())])
        self.assertEqual(r['replay_status'], {'UNKNOWN':1})
        self.assertEqual(r['chain_join'], 'NOT_PERFORMED')

    def test_replay_and_delayed_welcome_preserved(self):
        rows = [{'type':'welcome','realtime':False,'delaySeconds':15},
                {'type':'alert','replay':True}, {'type':'alert','replay':False}]
        r = inspect_frames([(10**12+i,i,json.dumps(m).encode()) for i,m in enumerate(rows)])
        self.assertEqual(r['welcome_claims'], [{'realtime':False,'delaySeconds':15}])
        self.assertEqual(r['replay_status'], {'EXPLICIT_REPLAY':1,'EXPLICIT_NOT_REPLAY':1})

    def test_future_timestamp_not_clamped(self):
        r=inspect_frames([(10**12,1,b'{"type":"alert","ts":1001000}')])
        self.assertEqual(r['provider_ts_to_receipt_ms']['min'],-1000)

    def test_payload_values_not_exposed(self):
        r=inspect_frames([(10**12,1,b'{"type":"alert","text":"PRIVATE","trader":"SECRET"}')])
        self.assertNotIn('PRIVATE',json.dumps(r)); self.assertNotIn('SECRET',json.dumps(r))

    def test_unknown_and_malformed_not_discarded(self):
        r=inspect_frames([(1,1,b'no json'),(2,2,b'[]'),(3,3,b'{"type":"novel"}')])
        self.assertEqual(r['malformed_frames'],2)
        self.assertEqual(r['message_types'],{'UNKNOWN':1})

    def test_clock_discontinuity_visible(self):
        r=inspect_frames([(10**12,10,b'{}'),(10**12-1,11,b'{}')])
        self.assertEqual(r['clock_discontinuities'],1)

    def test_hash_binds_receipt_and_bytes(self):
        h=digest('0'*64,1,2,3,b'a')
        self.assertNotEqual(h,digest('0'*64,1,3,3,b'a'))
        self.assertNotEqual(h,digest('0'*64,1,2,3,b'b'))

    def test_non_string_type_is_visible_unknown(self):
        self.assertEqual(inspect_frames([(1,1,b'{"type":[]}')])['message_types'],{'UNKNOWN':1})

    def capture(self, folder, secret_echo=False):
        path=Path(folder)/'probe.sqlite'
        secret='SYNTHETIC_KEY_FOR_TEST_ONLY'
        class Socket:
            calls=0
            def settimeout(self, _): pass
            def recv(self):
                self.calls+=1
                if self.calls==1: return '{"type":"welcome","realtime":true,"delaySeconds":0}'
                with closing(sqlite3.connect(path)) as db:
                    self_count=db.execute('SELECT COUNT(*) FROM raw_frame').fetchone()[0]
                    if self_count!=1: raise AssertionError('first frame not durable before next receive')
                if secret_echo:return secret
                raise websocket.WebSocketConnectionClosedException('sensitive URL '+secret)
            def close(self, **_): pass
        previous_mask=os.umask(0o077)
        try:
            with patch.object(F,'PRIVATE',Path(folder)),patch.object(F,'get_key',return_value=secret),patch.object(websocket,'create_connection',return_value=Socket()) as connect:
                result=F.run(path,1)
                self.assertEqual(connect.call_count,1)
                self.assertEqual(connect.call_args.kwargs['redirect_limit'],0)
        finally:os.umask(previous_mask)
        return path,result,secret

    def test_runtime_single_connection_durable_and_redacted(self):
        with tempfile.TemporaryDirectory() as folder:
            path,result,secret=self.capture(folder)
            self.assertEqual(result['frames'],1)
            self.assertEqual(result['end']['reason'],'FAILED')
            self.assertNotIn(secret,json.dumps(result))
            self.assertNotIn(secret.encode(),path.read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_secret_echo_not_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            path,result,secret=self.capture(folder,secret_echo=True)
            self.assertEqual(result['end']['reason'],'SECRET_ECHO_REFUSED_UNSAVED_FRAME')
            self.assertEqual(result['frames'],1)
            self.assertNotIn(secret.encode(),path.read_bytes())

    def test_closed_tail_deletion_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path,result,secret=self.capture(folder)
            with closing(sqlite3.connect(path)) as db:
                db.execute('DELETE FROM raw_frame')
                db.commit()
            with self.assertRaisesRegex(ValueError,'tail mismatch'):F.report(path)


if __name__ == '__main__':
    unittest.main()
