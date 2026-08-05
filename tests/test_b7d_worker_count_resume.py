"""Is an interrupted B7d enumeration resumable with a DIFFERENT worker count, bit for bit?

Written for the B11 acceleration audit (handoff 178). Nothing here touches the live run, the live
database or the network: every block comes from a deterministic in-process fixture, and every
database is a throwaway under the test's own temporary directory.

The question is narrow and answerable: if stage 2 were interrupted and restarted with more workers,
would the evidence be identical to an uninterrupted single-configuration run? The architecture says
it must be, for three reasons this file drives rather than asserts:

* resume is a SET DIFFERENCE over `slot_scan`, so a slot already `retrieved` or `skipped` is never
  refetched and a slot missing is always refetched;
* every database write happens on the ONE thread that consumes `executor.map`, so worker count
  changes fetch concurrency and nothing about storage;
* the export is `ORDER BY slot, transaction_index, outer_instruction_index, inner_instruction_index`,
  so its bytes are a function of content, not of insertion order.

What that does NOT establish is whether the SUPERVISOR permits it. That is a separate question with a
different answer, and it is recorded in the audit note rather than here.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest

import tests.test_b7d_create_enumerator as FIXTURE

ROOT = pathlib.Path(__file__).resolve().parents[1]
B7D = FIXTURE.B7D
TYPES = FIXTURE.TYPES
CREATE_IX_DISC = FIXTURE.CREATE_IX_DISC

START = 500_000
COUNT = 40
END = START + COUNT


def block_for(slot):
    """Deterministic block content per slot: a third of them carry a CreateEvent."""
    if slot % 3:
        return {"blockhash": f"hash{slot}", "previousBlockhash": f"prev{slot}",
                "parentSlot": slot - 1, "blockTime": 1_700_000_000 + slot, "transactions": []}
    # The pubkey fields are left as the shared fixture builds them: they are base58-decoded on
    # encode, so a value containing '0' is not a pubkey. Per-slot variation comes from the ledger
    # coordinates and block time, which is what the ordering and coverage claims are about.
    fields = FIXTURE.create_fields()
    payload = FIXTURE.create_payload(fields)
    instruction = B7D.b58encode(B7D.EVENT_TAG + payload)
    return {
        "blockhash": f"hash{slot}", "previousBlockhash": f"prev{slot}", "parentSlot": slot - 1,
        "blockTime": 1_700_000_000 + slot,
        "transactions": [{
            "transaction": {"signatures": [f"sig{slot}"], "message": {"instructions": [
                {"programId": B7D.PUMP, "data": B7D.b58encode(CREATE_IX_DISC)}]}},
            "meta": {"err": None, "innerInstructions": [{
                "index": 3, "instructions": [{"programId": B7D.PUMP, "data": instruction}]}]},
        }],
    }


class WorkerCountResumeTests(unittest.TestCase):
    """Same evidence, whatever the worker count and however many interruptions."""

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="b7d-workers-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.calls = []
        self.original_block = B7D.rpc_block
        self.original_produced = B7D.rpc_produced_slots
        self.addCleanup(lambda: setattr(B7D, "rpc_block", self.original_block))
        self.addCleanup(lambda: setattr(B7D, "rpc_produced_slots", self.original_produced))
        # No skipped slots in the fixture, so the getBlocks verification pass has nothing to do.
        B7D.rpc_produced_slots = lambda url, start, end, retries: (set(range(start, end + 1)), None)
        # Pinned so `endpoint_ref` is stable across runs. The transport is stubbed, so no request is
        # ever made; this only keeps the metadata comparison honest.
        self.saved_url = os.environ.get("SOLANA_RPC_URL")
        os.environ["SOLANA_RPC_URL"] = "https://fixture.invalid/rpc"
        self.addCleanup(self.restore_url)

    def restore_url(self):
        if self.saved_url is None:
            os.environ.pop("SOLANA_RPC_URL", None)
        else:
            os.environ["SOLANA_RPC_URL"] = self.saved_url

    class Interrupted(RuntimeError):
        """An injected kill, distinguishable from anything the enumerator raises itself."""

    def install_transport(self, fail_after=None):
        fetched = []

        def fake(url, slot, retries):
            if fail_after is not None and len(fetched) >= fail_after:
                raise WorkerCountResumeTests.Interrupted(f"killed before slot {slot}")
            fetched.append(slot)
            return slot, "retrieved", block_for(slot), None

        B7D.rpc_block = fake
        return fetched

    def run_enumeration(self, database, export, workers, fail_after=None):
        fetched = self.install_transport(fail_after=fail_after)
        argv = ["b7d_create_enumerator.py", "--start-slot", str(START), "--end-slot", str(END),
                "--database", str(database), "--export-jsonl", str(export),
                "--workers", str(workers)]
        saved = sys.argv
        sys.argv = argv
        try:
            B7D.main()
        except WorkerCountResumeTests.Interrupted:
            pass
        finally:
            sys.argv = saved
        return fetched

    def evidence(self, database):
        """Everything the stage is judged on, as content rather than as file bytes.

        The sqlite FILE is not comparable byte for byte -- page layout depends on write order, which
        is exactly what changing the worker count is allowed to change. What must be identical is the
        CONTENT: every row, in canonical order.
        """
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            scans = connection.execute(
                "SELECT slot, status, blockhash, previous_blockhash, parent_slot, block_time, "
                "transaction_count, pump_transaction_count, create_instruction_count, error "
                "FROM slot_scan ORDER BY slot").fetchall()
            events = connection.execute(
                "SELECT slot, transaction_index, outer_instruction_index, inner_instruction_index, "
                "signature, block_time, mint, bonding_curve, creator, user, is_mayhem_mode, "
                "is_cashback_enabled, quote_mint, fields_json, event_payload_base64 "
                "FROM create_event ORDER BY slot, transaction_index, outer_instruction_index, "
                "inner_instruction_index").fetchall()
            errors = connection.execute(
                "SELECT slot, transaction_index, outer_instruction_index, inner_instruction_index, "
                "signature, error FROM decode_error ORDER BY slot").fetchall()
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        finally:
            connection.close()
        return {"scans": scans, "events": events, "errors": errors, "metadata": metadata}

    def digest(self, payload):
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    # -- the baseline ---------------------------------------------------------------------------

    def test_an_uninterrupted_run_covers_the_whole_window(self):
        database = self.directory / "base.sqlite"
        export = self.directory / "base.jsonl"
        fetched = self.run_enumeration(database, export, workers=4)
        evidence = self.evidence(database)
        self.assertEqual(len(evidence["scans"]), COUNT)
        self.assertEqual(sorted(fetched), list(range(START, END)))
        self.assertEqual(len(fetched), COUNT, "no slot fetched twice")
        self.assertTrue(export.exists())

    # -- the question the audit exists to answer ------------------------------------------------

    def test_resuming_with_more_workers_produces_identical_evidence(self):
        """Interrupt at 4 workers, resume at 16: same rows, same export bytes."""
        reference_db = self.directory / "reference.sqlite"
        reference_export = self.directory / "reference.jsonl"
        self.run_enumeration(reference_db, reference_export, workers=4)
        reference = self.evidence(reference_db)

        resumed_db = self.directory / "resumed.sqlite"
        resumed_export = self.directory / "resumed.jsonl"
        first = self.run_enumeration(resumed_db, resumed_export, workers=4, fail_after=13)
        self.assertEqual(len(first), 13, "the interruption must land mid-window")
        self.assertFalse(resumed_export.exists(),
                         "an incomplete window must not have produced an export")
        second = self.run_enumeration(resumed_db, resumed_export, workers=16)
        resumed = self.evidence(resumed_db)

        self.assertEqual(self.digest(reference["scans"]), self.digest(resumed["scans"]))
        self.assertEqual(self.digest(reference["events"]), self.digest(resumed["events"]))
        self.assertEqual(self.digest(reference["errors"]), self.digest(resumed["errors"]))
        self.assertEqual(reference["metadata"], resumed["metadata"])
        self.assertEqual(reference_export.read_bytes(), resumed_export.read_bytes(),
                         "the export is ordered by ledger coordinate, so its bytes must match")

    def stored_slots(self, database):
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            return {row[0] for row in connection.execute(
                "SELECT slot FROM slot_scan WHERE status IN ('retrieved','skipped')")}
        finally:
            connection.close()

    def test_the_resume_refetches_exactly_the_missing_slots_and_no_others(self):
        """Measured against what was STORED, which is what resume keys on."""
        database = self.directory / "counted.sqlite"
        export = self.directory / "counted.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=13)
        already = self.stored_slots(database)
        second = self.run_enumeration(database, export, workers=16)
        self.assertEqual(set(second), set(range(START, END)) - already,
                         "resume must fetch the missing slots and only those")
        self.assertEqual(len(second), COUNT - len(already), "no duplicate fetches")

    def test_an_interruption_discards_the_blocks_fetched_ahead_of_storage(self):
        """A real cost of acceleration, measured rather than assumed.

        `executor.map` runs the workers ahead of the single consuming thread, so at the moment of a
        kill some blocks have been fetched and not yet stored. Those are lost and refetched. The
        volume lost scales with the worker count, which is the price of interrupting a wider run:
        at 16 workers an interruption can discard roughly 16 blocks of transfer rather than 4.
        """
        database = self.directory / "aheadof.sqlite"
        export = self.directory / "aheadof.jsonl"
        fetched = self.run_enumeration(database, export, workers=4, fail_after=13)
        stored = self.stored_slots(database)
        self.assertEqual(len(fetched), 13, "the fixture stopped the transport after 13 fetches")
        self.assertLess(len(stored), len(fetched),
                        "some fetched blocks were in flight and never reached the database")
        discarded = set(fetched) - stored
        self.assertTrue(discarded, "the discard is real, not hypothetical")
        # Nothing is corrupted by it: the discarded slots are simply absent and get refetched.
        self.run_enumeration(database, export, workers=16)
        self.assertEqual(self.stored_slots(database), set(range(START, END)))

    def test_several_interruptions_at_several_worker_counts_still_agree(self):
        """Three kills, three different worker counts. Coverage and bytes must not care."""
        reference_db = self.directory / "ref2.sqlite"
        reference_export = self.directory / "ref2.jsonl"
        self.run_enumeration(reference_db, reference_export, workers=8)
        reference = self.evidence(reference_db)

        database = self.directory / "chaotic.sqlite"
        export = self.directory / "chaotic.jsonl"
        for workers, fail_after in ((4, 7), (16, 11), (2, 9)):
            self.run_enumeration(database, export, workers=workers, fail_after=fail_after)
        self.run_enumeration(database, export, workers=16)
        chaotic = self.evidence(database)

        self.assertEqual(self.digest(reference["scans"]), self.digest(chaotic["scans"]))
        self.assertEqual(self.digest(reference["events"]), self.digest(chaotic["events"]))
        self.assertEqual(reference_export.read_bytes(), export.read_bytes())

    def test_no_slot_is_missed_or_duplicated_across_a_resume(self):
        database = self.directory / "coverage.sqlite"
        export = self.directory / "coverage.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=17)
        self.run_enumeration(database, export, workers=16)
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            slots = [row[0] for row in connection.execute("SELECT slot FROM slot_scan ORDER BY slot")]
            distinct = connection.execute("SELECT COUNT(DISTINCT slot) FROM slot_scan").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(slots, list(range(START, END)), "every slot exactly once, in order")
        self.assertEqual(distinct, COUNT)

    def test_events_stay_in_canonical_ledger_order_after_a_resume(self):
        database = self.directory / "order.sqlite"
        export = self.directory / "order.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=13)
        self.run_enumeration(database, export, workers=16)
        rows = [json.loads(line) for line in export.read_text().splitlines()]
        coordinates = [(r["slot"], r["transaction_index"], r["outer_instruction_index"],
                        r["inner_instruction_index"]) for r in rows]
        self.assertEqual(coordinates, sorted(coordinates))
        self.assertEqual(len(coordinates), len(set(coordinates)), "no duplicate coordinates")

    # -- what constrains it --------------------------------------------------------------------

    def test_the_worker_count_is_not_pinned_in_the_database_metadata(self):
        """So a resume at a different worker count is not a metadata mismatch.

        The window, program and IDL ARE pinned, which is what stops a resume from silently changing
        the thing being collected.
        """
        database = self.directory / "meta.sqlite"
        export = self.directory / "meta.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=5)
        metadata = self.evidence(database)["metadata"]
        self.assertNotIn("workers", metadata)
        for pinned in ("start_slot", "end_slot_exclusive", "program_id", "idl_sha256"):
            self.assertIn(pinned, metadata)

    def test_a_resume_that_changed_the_window_is_refused(self):
        """The boundary that a worker change must not be confused with."""
        database = self.directory / "window.sqlite"
        export = self.directory / "window.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=5)
        self.install_transport()
        saved = sys.argv
        sys.argv = ["b7d_create_enumerator.py", "--start-slot", str(START),
                    "--end-slot", str(END + 1), "--database", str(database),
                    "--export-jsonl", str(export), "--workers", "16"]
        try:
            with self.assertRaisesRegex(RuntimeError, "metadata mismatch"):
                B7D.main()
        finally:
            sys.argv = saved

    def test_an_incomplete_window_cannot_be_exported(self):
        """So an accelerated resume cannot produce a truncated export that looks finished."""
        database = self.directory / "partial.sqlite"
        export = self.directory / "partial.jsonl"
        self.run_enumeration(database, export, workers=4, fail_after=9)
        self.assertFalse(export.exists())
        connection = B7D.connect_database(database)
        try:
            with self.assertRaisesRegex(RuntimeError, "incomplete window"):
                B7D.export_jsonl(connection, str(export))
        finally:
            connection.close()

    def test_every_database_write_happens_on_one_thread(self):
        """The reason worker count cannot corrupt the store: there is only ever one writer.

        Read from the source rather than inferred: results are consumed from `executor.map` in the
        main thread and `store_result` is called there, so raising the worker count adds fetch
        concurrency and no write concurrency at all.
        """
        source = (ROOT / "scripts" / "b7d_create_enumerator.py").read_text()
        self.assertIn("with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:", source)
        self.assertIn("futures = executor.map(lambda slot: rpc_block(url, slot, args.retries)",
                      source)
        # store_result is called from the consuming loop, not from the worker lambda.
        worker_line = source.split("futures = executor.map(")[1].split("\n")[0]
        self.assertNotIn("store_result", worker_line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
