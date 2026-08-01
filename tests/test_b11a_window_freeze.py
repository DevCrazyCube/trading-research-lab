"""B11a — the fresh evaluation window freeze.

Everything this project has measured so far is burned, so this is the first window on which a model
could honestly be evaluated — and it can be spoiled in exactly five ways: an endpoint that is one
slot off, an overlap with something already burned, a span that quietly drifted from the inherited
geometry, a look at the contents before anything is frozen against them, and an edit to the range
after the chain's position is known. Those five are what this file tests.

The network guard is installed suite-wide, so the preflight is exercised through an injected
transport. No test here touches the network, and the module's own allowlist is tested rather than
trusted.
"""
import hashlib
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b11a_window_freeze", ROOT / "scripts" / "b11a_window_freeze.py")
B11A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B11A)

FROZEN_START = 435_569_150
FROZEN_END = 435_772_750
FROZEN_CUTOFF = 437_211_659


def document():
    return B11A.load_preregistration()


class DerivationTests(unittest.TestCase):
    """The window is arithmetic over already-recorded numbers, and the arithmetic is checked."""

    def test_the_window_re_derives_to_exactly_what_was_frozen(self):
        derived = B11A.assert_matches_preregistration()
        self.assertEqual(derived["launch_window_first_slot_inclusive"], FROZEN_START)
        self.assertEqual(derived["launch_window_last_slot_inclusive"], FROZEN_END)
        self.assertEqual(derived["observation_cutoff_slot_inclusive"], FROZEN_CUTOFF)

    def test_the_start_is_one_slot_after_the_maximum_burned_endpoint(self):
        normalized = B11A.normalized_burned_ranges()
        self.assertEqual(FROZEN_START, max(last for _, _, last in normalized) + 1)

    def test_a_half_open_range_normalises_by_exactly_one_slot(self):
        """`[a, b)` means b is NOT burned. Treating it as inclusive would waste a slot; treating an
        inclusive range as half-open would leave a burned slot inside the evaluation window, which
        is the direction that actually matters."""
        normalized = dict((origin, (first, last))
                          for origin, first, last in B11A.normalized_burned_ranges())
        self.assertEqual(normalized["B7d engineering pilot"], (430_000_000, 430_000_499))
        self.assertEqual(normalized["B7b dead-threshold sample"], (435_566_652, 435_566_690))

    def test_the_conservative_reading_of_b7b_is_the_one_used(self):
        """B7b's code scanned `range(435566652, 435566690)` but its burn statement is inclusive of
        435,566,690. The statement governs, because the reading that keeps a slot out of evaluation
        is the safe one."""
        normalized = dict((origin, last) for origin, _, last in B11A.normalized_burned_ranges())
        self.assertEqual(normalized["B7b dead-threshold sample"], 435_566_690)

    def test_an_off_by_one_in_any_endpoint_is_caught(self):
        for field in ("launch_window_first_slot_inclusive", "launch_window_last_slot_inclusive",
                      "observation_cutoff_slot_inclusive"):
            for delta in (-1, +1):
                with self.subTest(field=field, delta=delta):
                    tampered = document()
                    tampered["frozen_window"][field] += delta
                    with self.assertRaisesRegex(B11A.WindowRefused, "drifted|disagree"):
                        B11A.assert_matches_preregistration(tampered)

    def test_geometry_drift_from_the_inherited_spans_is_caught(self):
        for key in ("launch_window_span_slots", "observation_span_slots"):
            with self.subTest(key=key):
                tampered = document()
                tampered["derivation"][key]["value"] += 1
                with self.assertRaisesRegex(B11A.WindowRefused, "drifted"):
                    B11A.assert_matches_preregistration(tampered)

    def test_the_spans_are_inherited_from_b8b_and_b9d_unchanged(self):
        derived = B11A.derive_window()
        self.assertEqual(derived["launch_window_span_slots"],
                         B11A.B8B_WINDOW_END_SLOT_INCLUSIVE - B11A.B8B_WINDOW_START_SLOT + 1)
        self.assertEqual(derived["observation_span_slots"],
                         B11A.B9D_CUTOFF_SLOT - B11A.B8B_WINDOW_START_SLOT)

    def test_a_range_added_to_or_dropped_from_the_register_is_caught(self):
        tampered = document()
        tampered["burned_range_register"]["count"] = 6
        with self.assertRaisesRegex(B11A.WindowRefused, "burned ranges"):
            B11A.assert_matches_preregistration(tampered)

    def test_a_register_endpoint_that_disagrees_with_the_record_is_caught(self):
        tampered = document()
        tampered["burned_range_register"]["ranges"][0]["inclusive_last"] += 1
        with self.assertRaisesRegex(B11A.WindowRefused, "missing or has a different"):
            B11A.assert_matches_preregistration(tampered)

    def test_a_range_with_an_unstated_convention_is_refused(self):
        with self.assertRaisesRegex(B11A.WindowRefused, "unknown range convention"):
            B11A.normalized_burned_ranges((("X", 1, 2, "probably_inclusive"),))


class DisjointnessTests(unittest.TestCase):

    def test_both_the_launch_window_and_the_whole_observation_span_are_disjoint(self):
        self.assertTrue(B11A.assert_disjoint(FROZEN_START, FROZEN_END))
        self.assertTrue(B11A.assert_disjoint(FROZEN_START, FROZEN_CUTOFF))

    def test_every_burned_range_is_actually_detected_as_an_overlap(self):
        """Otherwise the disjointness check is a check that always passes."""
        for origin, first, last in B11A.normalized_burned_ranges():
            with self.subTest(origin=origin):
                for span in ((first, first), (last, last), (first, last),
                             (first - 5, first + 5), (last - 5, last + 5)):
                    with self.assertRaisesRegex(B11A.WindowRefused, "intersects burned range"):
                        B11A.assert_disjoint(*span)

    def test_the_slot_immediately_before_the_start_is_burned_and_the_start_is_not(self):
        """The tightest possible off-by-one: the window begins exactly where the burn ends."""
        with self.assertRaisesRegex(B11A.WindowRefused, "intersects burned range"):
            B11A.assert_disjoint(FROZEN_START - 1, FROZEN_START - 1)
        self.assertTrue(B11A.assert_disjoint(FROZEN_START, FROZEN_START))

    def test_observation_span_disjointness_is_redundant_under_the_start_rule(self):
        """A proof, not a safeguard. Because the start is `max(burned last) + 1`, every burned
        range ends strictly before the window begins, so nothing can intersect [start, cutoff].
        The module keeps the check anyway — it is free, and it is what would catch a future change
        to the start rule — but a mutation deleting it SURVIVES this suite by construction, and
        that is recorded rather than hidden behind a test that cannot really fail."""
        normalized = B11A.normalized_burned_ranges()
        start = B11A.derive_window()["launch_window_first_slot_inclusive"]
        self.assertTrue(all(last < start for _, _, last in normalized))
        self.assertEqual(start, max(last for _, _, last in normalized) + 1)

    def test_an_overlap_aborts_and_the_module_offers_no_way_to_shift_the_window(self):
        with self.assertRaises(B11A.WindowRefused) as caught:
            B11A.assert_disjoint(433_894_233, 434_097_833)
        self.assertIn("never shifted", str(caught.exception))
        source = (ROOT / "scripts" / "b11a_window_freeze.py").read_text()
        for forbidden in ("shift_window", "next_free_slot", "find_window", "search_window"):
            self.assertNotIn(forbidden, source)


class HashPinTests(unittest.TestCase):
    """The freeze is only a freeze if editing it is detectable."""

    def test_the_committed_document_matches_both_pinned_hashes(self):
        raw = B11A.PREREGISTRATION_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), B11A.PREREGISTRATION_FILE_SHA256)
        canonical = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         B11A.PREREGISTRATION_CANONICAL_SHA256)

    def test_an_edited_document_fails_the_hash_check(self):
        with self.assertRaisesRegex(B11A.WindowRefused, "hash"):
            B11A.load_preregistration(ROOT / "research" / "B10C_PREREGISTRATION_PLUMBING.json")

    def test_a_reformatted_document_fails_the_FILE_hash_even_though_it_means_the_same(self):
        """The two hashes are not redundant. Reformatting preserves the canonical hash, so only the
        file hash can tell that the committed bytes changed — and a diff nobody can see is exactly
        the kind of edit a freeze exists to catch."""
        import tempfile
        reformatted = json.dumps(document(), indent=4) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "reformatted.json"
            path.write_text(reformatted)
            self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                B11A.PREREGISTRATION_FILE_SHA256)
            canonical = hashlib.sha256(json.dumps(
                json.loads(reformatted), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(canonical, B11A.PREREGISTRATION_CANONICAL_SHA256,
                             "reformatting must preserve the canonical hash, or this proves nothing")
            with self.assertRaisesRegex(B11A.WindowRefused, "file hash"):
                B11A.load_preregistration(path)

    def test_the_document_declares_it_was_committed_before_any_chain_query(self):
        self.assertTrue(document()["committed_before_any_chain_query"])
        self.assertEqual(document()["window_status"], "fresh_preregistered")


class PreflightTests(unittest.TestCase):
    """One method. The allowlist is the mechanism, not the discipline."""

    def transport(self, tip):
        def call(url, method, params, timeout=30):
            self.assertEqual(method, "getSlot")
            self.assertEqual(params, [{"commitment": "finalized"}])
            return tip
        return call

    def test_only_getslot_may_be_called(self):
        self.assertEqual(B11A.PREFLIGHT_ALLOWED_METHODS, ("getSlot",))
        for method in ("getSignaturesForAddress", "getBlock", "getProgramAccounts",
                       "getTransaction", "getBlocks"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(B11A.WindowRefused, "not in the preflight allowlist"):
                    B11A.preflight_call("http://x", method, [], self.transport(1))

    def test_the_allowlist_is_an_allowlist_and_not_a_denylist(self):
        """A denylist would have to anticipate every method that leaks composition. This one has to
        anticipate nothing."""
        with self.assertRaises(B11A.WindowRefused):
            B11A.preflight_call("http://x", "someMethodInventedNextYear", [], self.transport(1))

    def test_the_receipt_records_that_no_composition_was_queried(self):
        receipt = B11A.preflight("https://user:key@example.org/path?api-key=SECRET",
                                 self.transport(FROZEN_CUTOFF - 100), document())
        self.assertEqual(receipt["methods_called"], ["getSlot"])
        self.assertFalse(receipt["composition_queried"])
        self.assertEqual(receipt["endpoint_reference"], "https://example.org/")

    def test_no_credential_survives_into_the_receipt(self):
        receipt = B11A.preflight("https://mainnet.example.org/?api-key=SUPERSECRET",
                                 self.transport(1), document())
        blob = json.dumps(receipt)
        for secret in ("SUPERSECRET", "api-key"):
            self.assertNotIn(secret, blob)

    def test_a_missing_rpc_url_refuses_rather_than_guessing_an_endpoint(self):
        import os
        saved = os.environ.pop("SOLANA_RPC_URL", None)
        try:
            with self.assertRaisesRegex(B11A.WindowRefused, "SOLANA_RPC_URL is not set"):
                B11A.rpc_url_from_environment()
        finally:
            if saved is not None:
                os.environ["SOLANA_RPC_URL"] = saved


class MaturityTests(unittest.TestCase):

    def test_an_unreached_cutoff_reports_the_exact_wait_and_refuses_to_move(self):
        state = B11A.maturity(FROZEN_CUTOFF - 1_000_000, document())
        self.assertFalse(state["mature"])
        self.assertEqual(state["slots_remaining"], 1_000_000)
        self.assertIn("not moved", state["action"])
        self.assertIn("not shortened", state["action"])
        self.assertIn("estimate", state["estimate_basis"])

    def test_the_boundary_slot_itself_counts_as_mature(self):
        self.assertTrue(B11A.maturity(FROZEN_CUTOFF, document())["mature"])
        self.assertFalse(B11A.maturity(FROZEN_CUTOFF - 1, document())["mature"])

    def test_the_wait_is_reported_in_slots_first_because_slots_do_not_drift(self):
        """A wall-clock figure moves with network speed; the slot count does not. The estimate is
        offered, but it is labelled an estimate and the exact quantity is the slot count."""
        state = B11A.maturity(FROZEN_CUTOFF - 2_393_400, document())
        self.assertEqual(state["slots_remaining"], 2_393_400)
        self.assertAlmostEqual(state["estimated_wait_seconds"], 1_000_000, delta=1)

    def test_a_nonsense_tip_is_refused(self):
        for tip in (-1, "435000000", None, True):
            with self.subTest(tip=tip):
                with self.assertRaisesRegex(B11A.WindowRefused, "tip slot"):
                    B11A.maturity(tip, document())


class ResultLockTests(unittest.TestCase):
    """Premature result access is the failure that cannot be undone."""

    def test_nothing_runs_before_maturity(self):
        for stage in B11A.plan_pipeline(mature=False):
            with self.subTest(stage=stage["stage"]):
                self.assertFalse(stage["runnable"])
                self.assertIn("not mature", stage["blocked_reason"])

    def test_collection_runs_at_maturity_but_results_stay_locked(self):
        plan = {stage["stage"]: stage for stage in B11A.plan_pipeline(mature=True)}
        self.assertTrue(plan["enumerate_creates"]["runnable"])
        self.assertTrue(plan["transaction_bodies"]["runnable"])
        self.assertFalse(plan["position_paths"]["runnable"])
        self.assertFalse(plan["outcome_labels"]["runnable"])
        self.assertIn("burn the window", plan["outcome_labels"]["blocked_reason"])

    def test_every_label_and_path_stage_is_classified_as_a_result(self):
        """If a stage that emits outcomes were classified as collection, the lock would be
        decorative."""
        for stage in B11A.PIPELINE:
            with self.subTest(stage=stage["stage"]):
                if stage["script"].startswith(("b10b", "b10c")):
                    self.assertEqual(stage["kind"], B11A.STAGE_RESULTS)
                    self.assertFalse(stage["permitted_before_unlock"])

    def test_gates_may_run_but_their_counts_are_withheld(self):
        """A gate must be able to fail before unlock — data that has not been gated cannot be
        shipped — but a count is a description of the window's composition."""
        plan = {stage["stage"]: stage for stage in B11A.plan_pipeline(mature=True)}
        for name in ("reserve_coverage_gate", "failure_coverage_gate", "simulator_replay_gate"):
            with self.subTest(name=name):
                self.assertTrue(plan[name]["runnable"])
                self.assertTrue(plan[name]["numbers_withheld"])

    def test_collection_counts_are_withheld_too_because_a_membership_count_is_composition(self):
        """Enumerating the cohort has to happen — you cannot collect a cohort without knowing who
        is in it — but "there are N launches" describes the window. Only the program-boundary probe
        is composition-free, because an upgrade slot is a property of the program."""
        plan = {stage["stage"]: stage for stage in B11A.plan_pipeline(mature=True)}
        for name in ("enumerate_creates", "signature_inventory", "transaction_bodies",
                     "decode_and_reserves"):
            with self.subTest(name=name):
                self.assertTrue(plan[name]["runnable"])
                self.assertTrue(plan[name]["numbers_withheld"])
        self.assertFalse(plan["program_boundary"]["numbers_withheld"])
        self.assertEqual(
            [s["stage"] for s in B11A.PIPELINE if not s["emits_composition"]],
            ["program_boundary"])

    def test_a_withheld_report_keeps_the_verdict_and_drops_the_numbers(self):
        report = {"passed": True, "curves": 1234, "anchored_complete": 1200}
        redacted = B11A.redact_composition(report)
        self.assertTrue(redacted["passed"])
        self.assertNotIn("curves", redacted)
        self.assertNotIn("1234", json.dumps(redacted))
        self.assertEqual(B11A.redact_composition(report, results_unlocked=True), report)

    def test_asking_for_a_locked_stage_refuses_by_name_with_the_branch(self):
        with self.assertRaisesRegex(B11A.WindowRefused, "abort branch A7"):
            B11A.assert_stage_permitted("outcome_labels", mature=True)
        with self.assertRaisesRegex(B11A.WindowRefused, "abort branch A3"):
            B11A.assert_stage_permitted("enumerate_creates", mature=False)
        self.assertTrue(B11A.assert_stage_permitted("enumerate_creates", mature=True))

    def test_an_unknown_stage_is_refused_rather_than_allowed(self):
        with self.assertRaisesRegex(B11A.WindowRefused, "unknown pipeline stage"):
            B11A.assert_stage_permitted("just_have_a_quick_look", mature=True)

    def test_b10c_still_refuses_this_window_status(self):
        """Deliberate: extending B10c's enum now would open a path to revealing this window's
        labels before anything is frozen against them."""
        spec = importlib.util.spec_from_file_location(
            "b10c_outcome_labels", ROOT / "scripts" / "b10c_outcome_labels.py")
        b10c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b10c)
        self.assertEqual(b10c.ALLOWED_WINDOW_STATUS, ("burned_development",))
        with self.assertRaisesRegex(b10c.LabelRefused, "window_status"):
            b10c.assert_preregistration(dict(document(), horizons=[
                {"name": "h", "kind": "slot_horizon", "slots": 1}]))


class PostPreflightImmutabilityTests(unittest.TestCase):
    """Once the chain's position is known, editing the window is choosing it."""

    def receipt(self):
        def transport(url, method, params, timeout=30):
            return FROZEN_CUTOFF - 500
        return B11A.preflight("https://example.org/", transport, document())

    def test_an_unchanged_window_passes(self):
        self.assertTrue(B11A.assert_preregistration_unchanged(self.receipt(), document()))

    def test_moving_any_endpoint_after_the_preflight_is_refused(self):
        for field in ("launch_window_first_slot_inclusive", "launch_window_last_slot_inclusive",
                      "observation_cutoff_slot_inclusive"):
            with self.subTest(field=field):
                receipt = self.receipt()
                edited = document()
                edited["frozen_window"][field] -= 1
                with self.assertRaisesRegex(B11A.WindowRefused, "A5"):
                    B11A.assert_preregistration_unchanged(receipt, edited)

    def test_replacing_the_preregistration_after_the_preflight_is_refused(self):
        receipt = self.receipt()
        receipt["preregistration_file_sha256"] = "0" * 64
        with self.assertRaisesRegex(B11A.WindowRefused, "A5"):
            B11A.assert_preregistration_unchanged(receipt, document())


class FreezeContentTests(unittest.TestCase):
    """The document must actually say the things the process depends on it saying."""

    def test_all_seven_abort_branches_are_recorded(self):
        branches = {branch["id"] for branch in document()["abort_branches"]}
        self.assertEqual(branches, {"A1", "A2", "A3", "A4", "A5", "A6", "A7"})

    def test_the_regime_and_the_split_floor_are_frozen(self):
        doc = document()
        self.assertEqual(doc["regime"]["quote"], "SOL-paired only")
        self.assertIn("excluded", doc["regime"]["mayhem"])
        self.assertEqual(doc["identity_group_split_floor"]["minimum"], "creator union user")
        self.assertIn("OPEN GATE", doc["identity_group_split_floor"]["open_gate"])

    def test_the_b10c_horizons_are_carried_over_unchanged(self):
        plumbing = json.loads(
            (ROOT / "research" / "B10C_PREREGISTRATION_PLUMBING.json").read_text())
        self.assertEqual(document()["label_horizons"]["horizons"], plumbing["horizons"])

    def test_both_programs_are_covered_by_the_boundary_policy(self):
        policy = document()["program_version_boundary_policy"]
        self.assertEqual(len(policy["programs"]), 2)
        self.assertIn("ABORT", policy["on_violation"])
        self.assertIn("NOT moved", policy["on_violation"])

    def test_geometry_adjustment_is_forbidden_for_every_tempting_reason(self):
        inheritance = document()["geometry_inheritance"]
        self.assertFalse(inheritance["adjustment_permitted"])
        for reason in ("yield", "market regime", "current activity", "outcomes"):
            self.assertIn(reason, inheritance["adjustment_forbidden_reasons"])


if __name__ == "__main__":
    unittest.main()
