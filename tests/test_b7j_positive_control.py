"""Focused tests for the B7j positive control.

These pin the properties the preregistration froze: the derived envelope, derived discriminators,
ordinal assignment, out-of-scope skipping, decode-error visibility, canonical key shape,
pagination boundary proof, and the no-provider-fallback rule.
"""
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "b7j", ROOT / "scripts" / "b7j_positive_control.py")
B7J = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B7J)
IDL = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
TYPES = {item["name"]: item for item in IDL["types"]}


class EnvelopeTests(unittest.TestCase):
    def test_envelope_matches_preregistered_derivation(self):
        # Any contiguous 220-slot window containing S starts in [S-219, S]; union is [S-219, S+220).
        s, w = 435565104, 220
        self.assertEqual((B7J.WINDOW_START, B7J.WINDOW_END), (s - (w - 1), s + w))
        self.assertEqual(B7J.WINDOW_END - B7J.WINDOW_START, 439)
        self.assertTrue(B7J.WINDOW_START <= s < B7J.WINDOW_END)

    def test_envelope_covers_every_admissible_scan_window(self):
        s, w = 435565104, 220
        for start in range(s - (w - 1), s + 1):
            self.assertGreaterEqual(start, B7J.WINDOW_START)
            self.assertLessEqual(start + w, B7J.WINDOW_END)


class DiscriminatorTests(unittest.TestCase):
    def test_discriminators_are_derived_and_match_the_pinned_idl(self):
        import hashlib
        discs = B7J.event_discriminators()
        self.assertEqual(len(discs), 2)
        for name in B7J.EVENT_NAMES:
            expected = hashlib.sha256(f"event:{name}".encode()).digest()[:8]
            self.assertIn(expected, discs)
            self.assertEqual(discs[expected], name)
            self.assertIn(name, TYPES, "frozen event must exist in the pinned IDL")

    def test_frozen_events_carry_mint_and_bonding_curve(self):
        # The candidate path depends on both fields being present on both event types.
        for name in B7J.EVENT_NAMES:
            fields = {f["name"] for f in TYPES[name]["type"]["fields"]}
            self.assertIn("mint", fields, name)
            self.assertIn("bonding_curve", fields, name)


def _tx(inner_instructions, signature="SIG", err=None):
    return {"transaction": {"signatures": [signature]},
            "meta": {"err": err, "innerInstructions": inner_instructions}}


def _cpi(disc_bytes, body=b""):
    raw = B7J.b7d.EVENT_TAG + disc_bytes + body
    return {"programId": B7J.b7d.PUMP, "data": B7J.b7d.b58encode(raw)}


class DecodeScopeTests(unittest.TestCase):
    def setUp(self):
        self.discs = B7J.event_discriminators()

    def test_unrelated_discriminator_is_skipped_silently(self):
        import hashlib
        trade = hashlib.sha256(b"event:TradeEvent").digest()[:8]
        rows, errors = B7J.decode_events(
            _tx([{"index": 0, "instructions": [_cpi(trade, b"\x00" * 32)]}]),
            self.discs, TYPES, 1, 0)
        self.assertEqual(rows, [])
        self.assertEqual(errors, [], "out-of-scope discriminators are not decode errors")

    def test_frozen_discriminator_with_bad_payload_is_a_visible_decode_error(self):
        disc = next(d for d, n in self.discs.items() if n == "CompleteEvent")
        rows, errors = B7J.decode_events(
            _tx([{"index": 0, "instructions": [_cpi(disc, b"\x01\x02")]}]),
            self.discs, TYPES, 1, 0)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1, "in-scope payload failure must be visible")

    def test_failed_transaction_contributes_nothing(self):
        disc = next(iter(self.discs))
        rows, errors = B7J.decode_events(
            _tx([{"index": 0, "instructions": [_cpi(disc, b"\x00" * 200)]}], err={"x": 1}),
            self.discs, TYPES, 1, 0)
        self.assertEqual((rows, errors), ([], []))


class CanonicalKeyTests(unittest.TestCase):
    def test_key_shape_matches_the_freeze(self):
        row = {"slot": 1, "transaction_index": 2, "signature": "S",
               "outer_instruction_index": 3, "inner_instruction_index": 4,
               "event_ordinal": 5, "mint": "M", "event_payload_base64": "P"}
        self.assertEqual(B7J.canonical_key(row), (1, 2, "S", 3, 4, 5, "M", "P"))

    def test_ordinal_increments_within_a_coordinate_group(self):
        ordinals, key = {}, ("SIG", 0, 0)
        seen = []
        for _ in range(3):
            value = ordinals.get(key, 0)
            ordinals[key] = value + 1
            seen.append(value)
        self.assertEqual(seen, [0, 1, 2], "ordinals must not be defaulted to a constant")


class PaginationTests(unittest.TestCase):
    """The freeze forbids treating a cap as 'history exhausted'."""

    class _DB:
        def execute(self, *a, **k): return None
        def commit(self): return None

    def test_cap_without_boundary_proof_fails_visibly(self):
        pages = [[{"signature": f"s{i}", "slot": B7J.WINDOW_END + 10} for i in range(1000)]
                 for _ in range(10)]
        calls = {"n": 0}

        def fake_rpc(url, method, params, retries=4, timeout=90):
            calls["n"] += 1
            return pages[min(calls["n"] - 1, len(pages) - 1)], None

        original, B7J.rpc = B7J.rpc, fake_rpc
        try:
            with self.assertRaises(RuntimeError) as ctx:
                B7J.paginate_curve("u", "CURVE", B7J.WINDOW_START, self._DB(), max_pages=3)
            self.assertIn("without proving", str(ctx.exception))
        finally:
            B7J.rpc = original

    def test_page_crossing_window_start_proves_the_boundary(self):
        def fake_rpc(url, method, params, retries=4, timeout=90):
            return [{"signature": "a", "slot": B7J.WINDOW_START - 1}], None

        original, B7J.rpc = B7J.rpc, fake_rpc
        try:
            out = B7J.paginate_curve("u", "CURVE", B7J.WINDOW_START, self._DB(), max_pages=3)
            self.assertEqual(len(out), 1)
        finally:
            B7J.rpc = original


class NoFallbackTests(unittest.TestCase):
    """Throttling a pinned path must raise, never silently switch providers."""

    def test_throttle_raises_path_unavailable(self):
        import urllib.error

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError("http://redacted", 429, "throttled", None, None)

        original, B7J.urllib.request.urlopen = B7J.urllib.request.urlopen, fake_urlopen
        try:
            for code_case in (429,):
                with self.assertRaises(B7J.PathUnavailable):
                    B7J.rpc("http://redacted", "getBlock", [1], retries=3)
        finally:
            B7J.urllib.request.urlopen = original


class ThrottleClassificationTests(unittest.TestCase):
    """Codex finding (4): throttling can arrive as a JSON-RPC error body, not only an HTTP status."""

    def _rpc_returning(self, payload):
        import io

        class R:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
            def read(self_inner): return json.dumps(payload).encode()

        original = B7J.urllib.request.urlopen
        B7J.urllib.request.urlopen = lambda req, timeout=None: R()
        try:
            return B7J.rpc("http://redacted", "getBlock", [1], retries=2)
        finally:
            B7J.urllib.request.urlopen = original

    def test_jsonrpc_throttle_codes_classify_as_path_unavailable(self):
        for code in (429, -32429, -32005):
            with self.assertRaises(B7J.PathUnavailable, msg=f"code {code}"):
                self._rpc_returning({"error": {"code": code, "message": "slow down"}})

    def test_jsonrpc_rate_limit_message_classifies_as_path_unavailable(self):
        with self.assertRaises(B7J.PathUnavailable):
            self._rpc_returning({"error": {"code": -1, "message": "Rate limit exceeded"}})

    def test_ordinary_jsonrpc_error_is_not_a_throttle(self):
        result, error = self._rpc_returning({"error": {"code": -32007, "message": "skipped"}})
        self.assertIsNone(result)
        self.assertIn("-32007", error)


class SlotReconciliationTests(unittest.TestCase):
    """Codex finding (2): a getBlock-skipped slot that getBlocks says was produced is an ERROR."""

    def _db(self):
        import sqlite3, tempfile, os
        path = os.path.join(tempfile.mkdtemp(), "t.sqlite")
        db = B7J.connect(path)
        return db

    def test_skipped_but_produced_becomes_error(self):
        db = self._db()
        db.execute("INSERT INTO slot_scan VALUES (?,?,?,?)", (100, "skipped", "-32007", 0.0))
        db.execute("INSERT INTO slot_scan VALUES (?,?,?,?)", (101, "skipped", "-32007", 0.0))
        db.commit()
        produced = {100}                      # 100 really existed; 101 genuinely absent
        for slot, _ in db.execute("SELECT slot,status FROM slot_scan WHERE status='skipped'").fetchall():
            if slot in produced:
                db.execute("UPDATE slot_scan SET status='error',error=? WHERE slot=?",
                           ("skipped by getBlock but present in getBlocks", slot))
            else:
                db.execute("UPDATE slot_scan SET status='verified_skipped' WHERE slot=?", (slot,))
        db.commit()
        got = dict(db.execute("SELECT slot,status FROM slot_scan"))
        self.assertEqual(got[100], "error", "produced-but-skipped must not pass silently")
        self.assertEqual(got[101], "verified_skipped")

    def test_only_retrieved_and_verified_skipped_are_acceptable(self):
        db = self._db()
        for slot, status in ((1, "retrieved"), (2, "verified_skipped"), (3, "skipped"),
                             (4, "error"), (5, "pending")):
            db.execute("INSERT INTO slot_scan VALUES (?,?,?,?)", (slot, status, None, 0.0))
        db.commit()
        bad = dict(db.execute("SELECT status,COUNT(*) FROM slot_scan WHERE status NOT IN "
                              "('retrieved','verified_skipped') GROUP BY status"))
        self.assertEqual(set(bad), {"skipped", "error", "pending"},
                         "raw 'skipped' must count as unresolved")


class MetadataReuseTests(unittest.TestCase):
    """Codex finding (3): a database built under different parameters must not be silently reused."""

    def test_mismatched_metadata_is_detected(self):
        import tempfile, os
        db = B7J.connect(os.path.join(tempfile.mkdtemp(), "t.sqlite"))
        db.executemany("INSERT INTO metadata VALUES (?,?)",
                       [("window_start", "1"), ("window_end", "2")])
        db.commit()
        present = {k: v for k, v in db.execute("SELECT key,value FROM metadata") if k != "summary"}
        expected = {"window_start": str(B7J.WINDOW_START), "window_end": str(B7J.WINDOW_END)}
        self.assertNotEqual(present, expected)

    def test_summary_key_is_excluded_from_the_comparison(self):
        import tempfile, os
        db = B7J.connect(os.path.join(tempfile.mkdtemp(), "t.sqlite"))
        db.executemany("INSERT INTO metadata VALUES (?,?)",
                       [("window_start", str(B7J.WINDOW_START)), ("summary", "{}")])
        db.commit()
        present = {k: v for k, v in db.execute("SELECT key,value FROM metadata") if k != "summary"}
        self.assertNotIn("summary", present)


class PersistenceTests(unittest.TestCase):
    """Auditability addendum: counts cannot reproduce discovery."""

    def test_schema_persists_blocks_history_pages_and_transactions(self):
        import tempfile, os
        db = B7J.connect(os.path.join(tempfile.mkdtemp(), "t.sqlite"))
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("raw_block", "raw_history_page", "raw_payload", "curve_history",
                         "run_error", "event_row", "slot_scan", "metadata"):
            self.assertIn(required, tables, required)

    def test_raw_tables_accept_zero_event_records(self):
        import tempfile, os, zlib
        db = B7J.connect(os.path.join(tempfile.mkdtemp(), "t.sqlite"))
        blob = zlib.compress(b'{"transactions":[]}')
        db.execute("INSERT INTO raw_block VALUES (?,?)", (1, blob))
        db.execute("INSERT INTO raw_history_page VALUES (?,?,?)", ("CURVE", 0, blob))
        db.execute("INSERT INTO raw_payload VALUES ('candidate',?,?,?)", ("SIG", 1, blob))
        db.commit()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_block").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_history_page").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_payload").fetchone()[0], 1)


class CanonicalKeyAmendmentTests(unittest.TestCase):
    """Codex finding (1): tx_index exclusion must be an explicit rule, not a silent drop."""

    def test_equality_projection_excludes_transaction_index(self):
        base = {"slot": 1, "signature": "S", "outer_instruction_index": 0,
                "inner_instruction_index": 0, "event_ordinal": 0, "mint": "M",
                "event_payload_base64": "P"}
        ref = dict(base, transaction_index=7)
        cand = dict(base, transaction_index=None)

        def projection(row):
            return (row["slot"], row["signature"], row["outer_instruction_index"],
                    row["inner_instruction_index"], row["event_ordinal"], row["mint"],
                    row["event_payload_base64"])

        self.assertEqual(projection(ref), projection(cand))
        self.assertNotEqual(B7J.canonical_key(ref), B7J.canonical_key(cand),
                            "full canonical key still distinguishes them; only the equality "
                            "projection drops tx_index, and that is an explicit frozen rule")


def _seeded_db(summary=None, partial=True):
    """A database carrying evidence from an earlier run, built through `connect()`."""
    import tempfile, os, zlib
    path = os.path.join(tempfile.mkdtemp(), "t.sqlite")
    db = B7J.connect(path)
    blob = zlib.compress(b"{}")
    if partial:
        db.execute("INSERT INTO event_row VALUES "
                   "('reference',1,0,'S',0,0,0,'CompleteEvent','M','C','P')")
        db.execute("INSERT INTO run_error VALUES ('x','y',0.0)")
        db.execute("INSERT INTO raw_payload VALUES ('candidate','S',1,?)", (blob,))
        db.execute("INSERT INTO raw_block VALUES (1,?)", (blob,))
        db.execute("INSERT INTO raw_history_page VALUES ('C',0,?)", (blob,))
        db.execute("INSERT INTO curve_history VALUES ('C',1,1,1)")
        db.execute("INSERT INTO slot_scan VALUES (?,?,?,?)",
                   (B7J.WINDOW_START, "retrieved", None, 0.0))
    if summary is not None:
        db.execute("INSERT INTO metadata VALUES ('summary',?)", (summary,))
    db.commit()
    return path, db


class ResumeCleanupTests(unittest.TestCase):
    """Every run rescans all slots, so no prior partial state may survive a rerun.

    These call `reset_for_rerun` itself. The previous versions re-implemented the DELETE
    statements inside the test, so they asserted only that SQLite deletes rows - production
    could have stopped clearing a table entirely and they would still have passed.
    """

    def test_reset_clears_every_derived_raw_and_history_table(self):
        _, db = _seeded_db(summary='{"stale":true}')
        B7J.reset_for_rerun(db)
        for table in B7J.RESETTABLE_TABLES:
            self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
        self.assertIsNone(B7J.completed_summary(db))
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM slot_scan WHERE status!='pending'").fetchone()[0], 0,
            "all slot rows must be reset to pending because every run rescans all slots")

    def test_resettable_tables_covers_every_evidence_table(self):
        _, db = _seeded_db()
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables - set(B7J.RESETTABLE_TABLES), {"metadata", "slot_scan"},
                         "a new evidence table must be added to RESETTABLE_TABLES or explicitly "
                         "handled; silently surviving a reset would contaminate the next verdict")


class RerunGuardTests(unittest.TestCase):
    """A rerun must never destroy irreplaceable raw evidence implicitly.

    The defect: re-invoking the same command line deleted every raw block, transaction and
    history page in the database. Those cannot be re-derived, and the B7j PASS verdict rests
    on them.
    """

    def test_fresh_database_passes_the_guard_untouched(self):
        _, db = _seeded_db(partial=False)
        B7J.guard_rerun(db, "t.sqlite", reset=False)      # must not raise
        self.assertFalse(B7J.has_prior_data(db))

    def test_partial_database_refuses_without_reset_and_keeps_its_data(self):
        _, db = _seeded_db()
        with self.assertRaises(SystemExit) as ctx:
            B7J.guard_rerun(db, "t.sqlite", reset=False)
        self.assertIn("--reset", str(ctx.exception))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_block").fetchone()[0], 1,
                         "a refused rerun must leave the evidence intact")

    def test_partial_database_with_reset_is_cleared(self):
        _, db = _seeded_db()
        B7J.guard_rerun(db, "t.sqlite", reset=True)
        self.assertFalse(B7J.has_prior_data(db))

    def test_completed_database_refuses_even_with_reset(self):
        for reset in (False, True):
            _, db = _seeded_db(summary='{"result":"PASS"}')
            with self.assertRaises(SystemExit) as ctx:
                B7J.guard_rerun(db, "t.sqlite", reset=reset)
            self.assertIn("COMPLETED", str(ctx.exception))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_block").fetchone()[0], 1,
                             f"finished artifact destroyed with reset={reset}")
            self.assertIsNotNone(B7J.completed_summary(db))

    def test_a_completed_run_with_no_other_rows_is_still_protected(self):
        # summary present but every table empty: still a finished artifact, not a work area.
        _, db = _seeded_db(summary='{"result":"PASS"}', partial=False)
        self.assertTrue(B7J.has_prior_data(db))
        with self.assertRaises(SystemExit):
            B7J.guard_rerun(db, "t.sqlite", reset=True)

    def test_reset_flag_defaults_to_false(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--reset", action="store_true")
        self.assertFalse(parser.parse_args([]).reset,
                         "destruction must never be the default")


class CandidateDurabilityTests(unittest.TestCase):
    """Candidate rows must be durable per transaction, like the reference path is per slot."""

    def _row(self, mint="M", signature="S", ordinal=0):
        return {"slot": B7J.WINDOW_START, "transaction_index": 7, "signature": signature,
                "outer_instruction_index": 0, "inner_instruction_index": 1,
                "event_ordinal": ordinal, "event_name": "CompleteEvent", "mint": mint,
                "bonding_curve": "C", "event_payload_base64": "P"}

    def test_row_survives_a_crash_after_its_own_commit(self):
        import sqlite3
        path, db = _seeded_db(partial=False)
        candidate = {}
        B7J.record_candidate_rows(db, [self._row()], {"M"}, candidate)
        db.commit()
        db.close()                                   # nothing else runs: the process died here
        reopened = sqlite3.connect(path)
        rows = reopened.execute(
            "SELECT side,mint,signature FROM event_row").fetchall()
        self.assertEqual(rows, [("candidate", "M", "S")],
                         "a candidate row must reach disk before the loop that produced it ends")

    def test_transaction_index_is_nulled_and_mints_outside_the_reference_are_dropped(self):
        _, db = _seeded_db(partial=False)
        candidate = {}
        B7J.record_candidate_rows(
            db, [self._row(mint="M"), self._row(mint="OTHER", signature="S2")], {"M"}, candidate)
        db.commit()
        stored = db.execute("SELECT mint,transaction_index FROM event_row").fetchall()
        self.assertEqual(stored, [("M", None)])
        self.assertEqual(len(candidate), 1)
        self.assertIsNone(next(iter(candidate.values()))["transaction_index"])

    def test_repeated_rows_dedupe_rather_than_accumulate(self):
        _, db = _seeded_db(partial=False)
        candidate = {}
        for _ in range(3):
            B7J.record_candidate_rows(db, [self._row()], {"M"}, candidate)
        db.commit()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM event_row").fetchone()[0], 1)
        self.assertEqual(len(candidate), 1)

    def test_both_paths_share_one_column_order(self):
        row = self._row()
        reference = B7J.event_row_values("reference", row)
        cand = B7J.event_row_values("candidate", row)
        self.assertEqual(reference[0], "reference")
        self.assertEqual(cand[0], "candidate")
        self.assertEqual(reference[1:], cand[1:])
        self.assertEqual(len(reference), B7J.EVENT_ROW_INSERT.count("?"),
                         "placeholder count must match the tuple width")


if __name__ == "__main__":
    unittest.main()
