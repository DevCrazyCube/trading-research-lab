"""End-to-end rehearsal of the frozen post-collection runbook.

The order is the substance: every step exists to make a specific later step recoverable. So the
rehearsal executes the real functions in the frozen order against a synthetic complete artifact,
records what it actually ran, and the tests compare that trace to `RUNBOOK`. Reordering or dropping
a step changes the trace.

Two steps cannot run offline and are simulated with that fact stated at the call site: the
collector's natural exit, and the boundary fetch, which is the only network call.
"""
import contextlib
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

import tests.test_b9d_transaction_bodies as B9DT

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9H = _load("b9h_runbook", "b9h_runbook.py")
B9G = _load("b9g_decode_readiness", "b9g_decode_readiness.py")
SEAL = _load("b9g_seal_collection", "b9g_seal_collection.py")
B9F = _load("b9f_failure_coverage", "b9f_failure_coverage.py")
B9E = _load("b9e_reserve_coverage", "b9e_reserve_coverage.py")

# One b9d instance across every module, so the fixture's patched population constants are the ones
# each gate verifies against. Each module loads b9d by path, which otherwise yields a separate
# object per module -- including a separate FreezeViolation class that `assertRaises` will not match.
B9D = B9DT.B9D
for _module in (B9H, B9G, SEAL, B9F, B9E):
    _module.B9D = B9D
    _module.FreezeViolation = B9D.FreezeViolation

MINT = "So11111111111111111111111111111111111111112"
LAUNCH = {"virtual_quote_reserves": 30_000, "virtual_token_reserves": 1_000_000,
          "real_quote_reserves": 0, "real_token_reserves": 800_000}


class RunbookRehearsal(unittest.TestCase):
    """A synthetic artifact that genuinely seals, verifies, decodes and passes both gates."""

    # Inside OBSERVATION_RANGE: the decoder resolves the pinned revision at each instruction's own
    # slot, so a fixture outside the covered range is refused -- correctly.
    SLOT_A, SLOT_B = B9D.SLOT_MIN, B9D.SLOT_MIN + 1

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.path = self.dir / "b9d.sqlite"
        saved = (B9D.EXPECTED_SLOTS, B9D.EXPECTED_SIGNATURES)
        B9D.EXPECTED_SLOTS, B9D.EXPECTED_SIGNATURES = 2, 2
        self.addCleanup(lambda: setattr(B9D, "EXPECTED_SLOTS", saved[0]))
        self.addCleanup(lambda: setattr(B9D, "EXPECTED_SIGNATURES", saved[1]))

        self.curve = B9D.base58(bytes(range(32)))
        cohort = B9D.tradable_cohort_identity
        B9D.tradable_cohort_identity = lambda *a, **k: {MINT: self.curve}
        self.addCleanup(lambda: setattr(B9D, "tradable_cohort_identity", cohort))
        # The synthetic artifact has no real B9c/B9a files behind it; source-hash verification is
        # exercised by its own tests elsewhere and is not what this rehearsal is about.
        sources = B9D.verify_source_artifacts
        B9D.verify_source_artifacts = lambda *a, **k: {"b9c": "stubbed", "b9a": "stubbed"}
        self.addCleanup(lambda: setattr(B9D, "verify_source_artifacts", sources))

        self.build_raw_bodies()
        self.trace = []

    # ---------------------------------------------------------------- synthetic artifact

    def pump_body(self, slot, event_payload):
        roles = [a["name"] for a in next(
            i for i in json.loads((ROOT / B9D.PUMP_IDL_PATH).read_bytes())["instructions"]
            if i["name"] == "buy")["accounts"]]
        buy = bytes(next(i for i in json.loads((ROOT / B9D.PUMP_IDL_PATH).read_bytes())
                         ["instructions"] if i["name"] == "buy")["discriminator"])
        keys = [B9D.base58_decode(B9D.PUMP_PROGRAM), bytes(range(32))]
        meta = {"preBalances": [0, 1_000], "postBalances": [0, 1_000],
                "innerInstructions": [{"index": 0, "instructions": [
                    {"programIdIndex": 0, "accounts": [], "data": B9D.base58(event_payload),
                     "stackHeight": 2}]}]}
        raw = B9DT.build_transaction(keys, [(0, [1] * len(roles), buy)])
        return json.dumps({"jsonrpc": "2.0", "id": 1,
                           "result": B9DT.as_result(raw, meta=meta, slot=slot)}).encode()

    def store(self, database, table, key_column, key, raw):
        database.execute(
            f"INSERT INTO {table} ({key_column},method,params_json,received_at_unix,"
            "response_sha256,raw_zlib) VALUES (?,?,?,?,?,?)",
            (key, "m", "[]", 1.0, B9D.hashlib.sha256(raw).hexdigest(), B9D.zlib.compress(raw, 6)))

    def build_raw_bodies(self):
        """Bodies and coordinates only. Boundary evidence arrives at step 4, as it really does."""
        create = B9DT.encode_pump_event(
            "CreateEvent", mint=MINT, bonding_curve=self.curve,
            virtual_quote_reserves=LAUNCH["virtual_quote_reserves"],
            virtual_token_reserves=LAUNCH["virtual_token_reserves"],
            real_token_reserves=LAUNCH["real_token_reserves"])
        # A zero-size trade: the chain must still reconcile exactly, and the curve's lamport delta
        # is 0, so balance reconciliation is `exact` rather than a failure.
        trade = B9DT.encode_trade_event(
            mint=MINT, is_buy=True, quote_amount=0, token_amount=0,
            quote_mint=B9D.NATIVE_QUOTE_MINT, **{k: v for k, v in LAUNCH.items()})
        database = B9D.connect(str(self.path))
        B9D.schema(database)
        with database:
            self.store(database, "raw_block_signatures", "slot", self.SLOT_A,
                       json.dumps({"result": {"signatures": ["sigA"]}}).encode())
            self.store(database, "raw_block_signatures", "slot", self.SLOT_B,
                       json.dumps({"result": {"signatures": ["sigB"]}}).encode())
            database.execute("INSERT INTO transaction_coordinate VALUES ('sigA',?,0)", (self.SLOT_A,))
            database.execute("INSERT INTO transaction_coordinate VALUES ('sigB',?,0)", (self.SLOT_B,))
            self.store(database, "raw_transaction", "signature", "sigA",
                       self.pump_body(self.SLOT_A, create))
            self.store(database, "raw_transaction", "signature", "sigB",
                       self.pump_body(self.SLOT_B, trade))
            database.execute("INSERT INTO metadata VALUES ('b9c_sha256',?)", (B9D.B9C_SHA256,))
            database.execute("INSERT INTO metadata VALUES ('b9a_sha256',?)", (B9D.B9A_SHA256,))
        database.close()

    def open(self):
        database = B9D.connect(str(self.path))
        self.addCleanup(database.close)
        return database

    # ---------------------------------------------------------------- the runbook itself

    def step(self, name):
        self.trace.append(name)

    def run_runbook(self, decode=None, stop_after=None):
        """Execute the frozen order, recording each step as it actually runs."""
        results = {}

        self.step("collector_exits_naturally")          # simulated: the collector is not run here

        self.step("seal_collection")
        results["seal"] = SEAL.seal_collection(str(self.path), now=1000)

        self.step("backup_raw_bodies")
        self.raw_backup = self.dir / "raw-bodies.sqlite"
        results["raw_backup"] = B9H.backup_artifact(self.path, self.raw_backup)

        self.step("collect_boundary")                   # simulated: the only network step
        database = self.open()
        with database:
            B9DT.PublicationGateTests.add_boundary_evidence(None, database)

        self.step("verify_and_readiness")
        results["readiness"] = B9G.assert_decode_ready(self.open(), str(self.path))

        self.step("backup_sealed_raw_and_boundary")
        self.sealed_backup = self.dir / "sealed-raw-boundary.sqlite"
        results["sealed_backup"] = B9H.backup_artifact(self.path, self.sealed_backup)

        if stop_after == "backup_sealed_raw_and_boundary":
            return results

        self.step("atomic_decode")
        results["decode"] = (decode or B9D.decode_artifact)(self.open())

        self.step("verify_decoded")
        results["verify_decoded"] = B9D.verify_decoded_artifact(self.open())

        self.step("b9f_gate")
        results["b9f_measured"] = B9F.failure_coverage(self.open())
        results["b9f"] = B9F.assert_publication_gate(self.open())

        self.step("b9e_gate")
        results["b9e_measured"] = B9E.cohort_reserve_coverage(self.open())
        results["b9e"] = B9E.assert_publication_gate(self.open())
        return results

    # ---------------------------------------------------------------- tests

    def test_the_whole_runbook_executes_in_the_frozen_order_and_both_gates_pass(self):
        results = self.run_runbook()
        self.assertEqual(tuple(self.trace), B9H.STEP_NAMES,
                         "the executed order must be the frozen order")
        self.assertEqual(results["seal"]["sealed_at_unix"], "1000")
        self.assertTrue(results["readiness"]["ready"])
        self.assertEqual(results["b9f"]["counts"], {n: 0 for n in B9F.CATEGORY_NAMES})
        self.assertEqual(results["b9e"]["anchored_complete_fraction"], 1.0)
        self.assertEqual(results["b9e"]["counts"]["anchored_complete"], 1)

    def test_the_raw_backup_is_taken_before_the_boundary_write(self):
        """A failed boundary fetch must have a clean state to return to.

        Backing up after the write would make the pre-boundary state unrecoverable, which is the
        one thing the pre-boundary backup exists for.
        """
        self.run_runbook(stop_after="backup_sealed_raw_and_boundary")
        self.assertLess(self.trace.index("backup_raw_bodies"),
                        self.trace.index("collect_boundary"))
        backup = sqlite3.connect(self.raw_backup)
        self.addCleanup(backup.close)
        self.assertEqual(
            backup.execute("SELECT count(*) FROM raw_boundary_response").fetchone()[0], 0,
            "the pre-boundary backup must predate the boundary evidence")
        self.assertEqual(
            backup.execute("SELECT count(*) FROM metadata WHERE key=?",
                           (B9D.COLLECTION_COMPLETE_KEY,)).fetchone()[0], 1,
            "but it must already be sealed")

    def test_both_backups_restore_byte_for_byte_and_verify_their_digests(self):
        self.run_runbook(stop_after="backup_sealed_raw_and_boundary")
        for backup in (self.raw_backup, self.sealed_backup):
            with self.subTest(backup=backup.name):
                target = self.dir / f"restored-{backup.name}"
                expected = B9H.digest(backup)
                self.assertEqual(B9H.restore_artifact(backup, target, expected), expected)
                self.assertEqual(backup.read_bytes(), target.read_bytes())

    def test_a_corrupted_backup_is_refused_rather_than_restored(self):
        self.run_runbook(stop_after="backup_sealed_raw_and_boundary")
        expected = B9H.digest(self.sealed_backup)
        with self.sealed_backup.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"\x00" * 32)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9H.restore_artifact(self.sealed_backup, self.dir / "target.sqlite", expected)
        self.assertIn("must not be restored", str(ctx.exception))

    def test_a_backup_that_did_not_copy_faithfully_is_refused(self):
        """A backup is only a recovery point if it is verified at the moment it is taken.

        `shutil.copy2` will not truncate on its own, so this simulates the failure it is guarded
        against -- a short write, a full disk, a filesystem that lied about the write.
        """
        def truncating_copy(source, destination):
            pathlib.Path(destination).write_bytes(pathlib.Path(source).read_bytes()[:64])

        saved, B9H.shutil.copy2 = B9H.shutil.copy2, truncating_copy
        self.addCleanup(lambda: setattr(B9H.shutil, "copy2", saved))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9H.backup_artifact(self.path, self.dir / "short.sqlite")
        self.assertIn("hashes", str(ctx.exception))

    def test_a_backup_never_overwrites_an_earlier_recovery_point(self):
        self.run_runbook(stop_after="backup_sealed_raw_and_boundary")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9H.backup_artifact(self.path, self.raw_backup)
        self.assertIn("refusing to overwrite", str(ctx.exception))

    def test_a_failed_decode_rolls_back_and_the_sealed_backup_still_restores_it(self):
        """The decode is one transaction, so a mid-pass failure must leave nothing behind.

        This is what makes step 6 the only state a failed decode restores from: the artifact after
        a rolled-back decode must be indistinguishable from the artifact before it.
        """
        before = None

        def exploding_decode(database, **kwargs):
            nonlocal before
            before = B9H.digest(self.path)
            raise RuntimeError("injected mid-decode failure")

        with self.assertRaises(RuntimeError):
            self.run_runbook(decode=exploding_decode)
        self.assertEqual(self.trace[-1], "atomic_decode", "it failed at the decode, not earlier")

        database = self.open()
        for table in ("instruction", "reserve_observation", "classification_failure"):
            with self.subTest(table=table):
                self.assertEqual(
                    database.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0,
                    "a rolled-back decode must leave no derived rows")
        self.assertEqual(B9H.digest(self.path), before, "the artifact is byte-identical")
        self.assertEqual(B9H.digest(self.sealed_backup), before,
                         "and identical to the sealed backup it would be restored from")

    def test_readiness_refuses_before_the_boundary_step_and_diagnosis_explains_why(self):
        """Running the gate at step 2 rather than step 5 must fail, and say what is missing."""
        SEAL.seal_collection(str(self.path), now=1)
        with self.assertRaises(B9D.FreezeViolation):
            B9G.assert_decode_ready(self.open(), str(self.path))
        report = B9G.diagnose_readiness(self.open(), str(self.path))
        self.assertFalse(report["ready"])
        self.assertFalse(report["checks"]["structural_verification"]["passed"])
        self.assertTrue(report["checks"]["collection_sealed"]["passed"])

    def test_decoding_before_readiness_is_what_the_order_prevents(self):
        """Step 7 before step 5 decodes an artifact with no boundary evidence.

        The decode itself refuses, which is the point: the ordering is not a convention layered on
        top of permissive functions, it is enforced by them.
        """
        SEAL.seal_collection(str(self.path), now=1)
        with self.assertRaises(B9D.FreezeViolation):
            B9D.decode_artifact(self.open())

    def test_the_runbook_declares_which_steps_cannot_be_rehearsed(self):
        offline = {entry["name"] for entry in B9H.RUNBOOK if entry["offline"]}
        self.assertEqual(set(B9H.STEP_NAMES) - offline,
                         {"collector_exits_naturally", "collect_boundary"},
                         "only the collector's exit and the network call are unrehearsable")
        self.assertEqual(len(B9H.RUNBOOK), 10)
        self.assertEqual([entry["step"] for entry in B9H.RUNBOOK], list(range(1, 11)))


if __name__ == "__main__":
    unittest.main()
