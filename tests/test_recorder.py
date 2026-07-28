import argparse
import http.server
import importlib.util
import json
import os
import re
import tempfile
import threading
import unittest


SPEC = importlib.util.spec_from_file_location("recorder", "scripts/recorder.py")
recorder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recorder)


class RecorderTests(unittest.TestCase):
    def test_schema_version_tracks_log_truncation_extension(self):
        self.assertEqual(recorder.SPEC_VERSION, "0.3")
        with open("docs/schema/RAW_CAPTURE_SPEC.md", encoding="utf-8") as handle:
            self.assertIn("`log_truncated`", handle.read())

    def test_crc32c_standard_vector(self):
        self.assertEqual(recorder.crc32c(b"123456789"), 0xE3069283)

    def test_ulid_shape(self):
        self.assertRegex(recorder.ulid(), re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$"))

    def test_recovery_records_next_missing_sequence(self):
        with tempfile.TemporaryDirectory() as root:
            recorder_id, session_id = recorder.ulid(), recorder.ulid()
            recorder.append_jsonl(os.path.join(root, "meta", "sessions.jsonl"), {
                "event": "open", "recorder_id": recorder_id, "session_id": session_id,
            })
            writer = recorder.SegmentWriter(root, recorder_id, session_id)
            writer.write(0, {"seq_in_session": 0}, b"first")
            writer.write(1, {"seq_in_session": 1}, b"second")
            writer.f.write(b"\xde\xad\xbe\xef")
            writer.f.flush()
            writer.f.close()

            recovered = recorder.recover(root)
            self.assertEqual(recovered[0][1:], (1, 4))
            with open(os.path.join(root, "meta", "gaps.jsonl"), encoding="utf-8") as handle:
                gap = json.loads(handle.readline())
            self.assertEqual(gap["first_missing_hint"], 2)
            self.assertIsNone(gap["last_missing_hint"])


class LoopbackRPC(http.server.BaseHTTPRequestHandler):
    """A minimal JSON-RPC stand-in for `getSlot`/`getBlock`, bound to 127.0.0.1.

    The point of the credential test below is that it is **end-to-end**: it must exercise the real
    segment writer, framing, index and meta paths, because a leak could occur in any of them.
    Stubbing `recorder.rpc` would keep it hermetic but hollow out exactly the coverage that makes it
    worth having. Serving canned responses over loopback keeps the whole write path live while
    contacting nothing outside the machine.
    """

    TIP = 1000

    def log_message(self, *a):
        pass  # keep the suite's output clean

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["method"] == "getSlot":
            result = self.TIP
        else:
            slot = body["params"][0]
            result = {
                "parentSlot": slot - 1,
                "blockhash": f"hash{slot}",
                "blockTime": 1785000000 + slot,
                # One Pump-touching transaction so `touches_pump` keeps it and a real payload is
                # written, and one that must be filtered out.
                "transactions": [
                    {"transaction": {"message": {"instructions": [
                        {"programId": recorder.PUMP, "data": "3Bxs"}]}},
                     "meta": {"err": None, "innerInstructions": []}},
                    {"transaction": {"message": {"instructions": [
                        {"programId": "11111111111111111111111111111111"}]}},
                     "meta": {"err": None, "innerInstructions": []}},
                ],
            }
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class CredentialLeakTests(unittest.TestCase):
    """The RPC URL may carry an API key. Spec v0.2 forbids persisting credentials,
    so no artefact under the capture root may ever contain it. This is an
    end-to-end test: it runs the recorder with a token-bearing URL and greps
    every byte written.

    It runs against a **loopback** server. It previously ran against the public mainnet endpoint,
    which made the suite non-hermetic (a ~6 s live capture on every run, failing with no network)
    and quietly contradicted the read-only/zero-RPC gate every handoff asserts alongside "119 tests
    pass". No credential was ever at risk - the URL was the hardcoded public default with a dummy
    token - but the suite must not reach the network at all.
    """

    def test_no_rpc_url_or_token_reaches_disk(self):
        token = "SECRETTOKEN_DO_NOT_PERSIST_9f3a"
        server = http.server.HTTPServer(("127.0.0.1", 0), LoopbackRPC)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        url = f"http://{host}:{port}/?api-key={token}"

        with tempfile.TemporaryDirectory() as root:
            args = argparse.Namespace(root=root, rpc=url, duration=1.0,
                                      max_lag=20, simulate_crash_after=0)
            recorder.run(args)

            written, hits = 0, []
            for dirpath, _, files in os.walk(root):
                for name in files:
                    p = os.path.join(dirpath, name)
                    with open(p, "rb") as fh:
                        blob = fh.read()
                    written += len(blob)
                    if token.encode() in blob or b"api-key" in blob:
                        hits.append(p)
            self.assertEqual(hits, [], f"credential leaked into: {hits}")
            # A test that greps zero bytes passes vacuously; assert it actually captured something.
            self.assertGreater(written, 0, "recorder wrote nothing - the grep proved nothing")
            self.assertTrue(os.path.exists(os.path.join(root, "index", "frame_index.jsonl")),
                            "no frames written - the end-to-end path did not run")

if __name__ == "__main__":
    unittest.main()
