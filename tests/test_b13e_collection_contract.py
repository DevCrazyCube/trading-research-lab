"""Tests for the B13e collection contract validator.

Synthetic fixtures only. Nothing here queries anything, enumerates B11a, or collects a history.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13E = _load("b13e_collection_contract", "b13e_collection_contract.py")
B13A = B13E.B13A
B11A = B13E.B11A
B10B = B13E.B10B

LOOKBACK = 1_642_509
FRESH_FIRST = 435_569_150          # B11a's first fresh launch slot, from frozen arithmetic
ACTOR_A, ACTOR_B = "ActorAlphaSynthetic", "ActorBetaSynthetic"


def at(slot, index=0, outer=0, inner=0):
    return {"slot": slot, "transaction_index": index, "outer_index": outer, "inner_index": inner}


def params():
    return B13E.read_preregistration()


def unlocked(mature=True, u3=True):
    return {"mature": mature, "criteria": {"U3": u3, "U1": True}}


def accounting(**overrides):
    base = {"transactions_required": 0, "transactions_with_body": 0, "transactions_missing_body": 0,
            "transactions_missing_coordinate": 0, "system_instructions_total": 0,
            "decoded_moving": 0, "decoded_non_moving": 0, "undecodable": 0, "edges_emitted": 0,
            "moving_self_transfer": 0, "moving_without_addresses": 0, "unresolved": []}
    base.update(overrides)
    return base


def pagination(**overrides):
    base = {"method": "getSignaturesForAddress", "pages_fetched": 7, "page_size": 1000,
            "final_cursor": None, "termination_condition": B13E.TERMINATION_EMPTY_PAGE,
            "page_cap": 10_000}
    base.update(overrides)
    return base


def coverage(window, actor=ACTOR_A, **overrides):
    base = {"actor": actor,
            "earliest_slot_reached": window["start_slot_inclusive"],
            "lookback_start_slot": window["start_slot_inclusive"],
            "left_truncated": window["clamped_at_genesis"],
            "pagination": pagination(),
            "decode_accounting": accounting(),
            "source_hashes": ["s" * 64],
            "raw_preserved": True}
    base.update(overrides)
    return base


def window(slot=FRESH_FIRST, **kwargs):
    return B13E.lookback_window(at(slot, **kwargs))


# --------------------------------------------------------------------------------------------

class PreregistrationPinTests(unittest.TestCase):
    """The document is the authority, and the pin is what notices when it moves."""

    def test_the_shipped_document_matches_the_pin(self):
        self.assertTrue(B13E.assert_preregistration())

    def test_an_edited_parameter_stops_matching(self):
        for field, value in (("lookback_slots", 1_642_508),
                             ("cohort_source", "anything_we_find"),
                             ("coverage_averaging_permitted", True),
                             ("burned_members_permitted_as_examples", True)):
            with self.subTest(field=field):
                edited = dict(params(), **{field: value})
                with self.assertRaisesRegex(B13E.PreregistrationMismatch, "hash to"):
                    B13E.assert_preregistration(edited)

    def test_a_replaced_pin_is_itself_the_failure(self):
        """Swapping the expected hash to match an edited document is the attack this guards."""
        edited = dict(params(), lookback_slots=999)
        with self.assertRaisesRegex(B13E.PreregistrationMismatch,
                                    "while the frozen constants give"):
            B13E.assert_preregistration(edited, expected=B13E.preregistration_hash(edited))

    def test_the_document_must_carry_the_expected_id(self):
        edited = dict(params(), preregistration_id="B13E_LOOKBACK_V2")
        with self.assertRaisesRegex(B13E.PreregistrationMismatch, "preregistration id"):
            B13E.assert_preregistration(edited)

    def test_the_documents_own_derivation_must_produce_its_own_lookback(self):
        edited = copy.deepcopy(params())
        edited["lookback_operands"]["b8b_window_start_slot"] = B11A.B8B_WINDOW_START_SLOT
        edited["lookback_operands"]["b9d_cutoff_slot"] = B11A.B9D_CUTOFF_SLOT
        self.assertEqual(
            edited["lookback_operands"]["b9d_cutoff_slot"]
            - edited["lookback_operands"]["b8b_window_start_slot"], edited["lookback_slots"])

    def test_the_cross_module_checks_survive_a_replaced_pin(self):
        """The hash catches any document edit — but only the values the CODE also holds can catch a
        document that was re-pinned after editing. Those are driven here with a matching pin, which
        is the only way to reach past the hash."""
        cases = {
            "while the frozen constants give": {"lookback_slots": 1_642_508},
            "not the frozen constants they claim":
                {"lookback_operands": {"b9d_cutoff_slot": 435_536_742,
                                       "b8b_window_start_slot": 433_894_200}},
        }
        for expected, override in cases.items():
            with self.subTest(expected=expected):
                edited = dict(params(), **override)
                with self.assertRaisesRegex(B13E.PreregistrationMismatch, expected):
                    B13E.assert_preregistration(edited,
                                                expected=B13E.preregistration_hash(edited))

    def test_a_documents_derivation_that_does_not_produce_its_own_lookback_is_refused(self):
        edited = dict(params(), lookback_operands={"b9d_cutoff_slot": B11A.B9D_CUTOFF_SLOT,
                                                   "b8b_window_start_slot": B11A.B9D_CUTOFF_SLOT})
        edited = dict(edited, lookback_slots=0)
        with self.assertRaises(B13E.PreregistrationMismatch):
            B13E.assert_preregistration(edited, expected=B13E.preregistration_hash(edited))

    def test_values_only_the_document_states_are_pinned_by_the_hash_alone(self):
        """Deliberately not re-read in code: a second check on a value the hash already fixes
        could never fire. Every such edit is still caught, by the hash."""
        for field, value in (("cohort_source", "any_actor_we_find"),
                             ("collection_before_unlock_permitted", True),
                             ("coverage_averaging_permitted", True),
                             ("required_unlock_criterion", "U1")):
            with self.subTest(field=field):
                edited = dict(params(), **{field: value})
                with self.assertRaisesRegex(B13E.PreregistrationMismatch, "hash to"):
                    B13E.assert_preregistration(edited)

    def test_a_document_with_no_parameter_block_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write("# a document that is only prose\n\nno parameters here.\n")
            path = handle.name
        try:
            with self.assertRaisesRegex(B13E.PreregistrationMismatch, "prose alone"):
                B13E.read_preregistration(path)
        finally:
            pathlib.Path(path).unlink()

    def test_a_document_whose_block_is_not_valid_json_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write("```json\n{not json at all,}\n```\n")
            path = handle.name
        try:
            with self.assertRaisesRegex(B13E.PreregistrationMismatch, "not valid JSON"):
                B13E.read_preregistration(path)
        finally:
            pathlib.Path(path).unlink()

    def test_a_missing_document_stops_everything(self):
        with self.assertRaisesRegex(B13E.PreregistrationMismatch, "is missing at"):
            B13E.read_preregistration(ROOT / "research" / "does-not-exist.md")


class LookbackTests(unittest.TestCase):
    """1,642,509 slots, derived rather than chosen, and never one slot different."""

    def test_the_lookback_is_the_frozen_difference(self):
        self.assertEqual(B13E.LOOKBACK_SLOTS, LOOKBACK)
        self.assertEqual(B11A.B9D_CUTOFF_SLOT - B11A.B8B_WINDOW_START_SLOT, LOOKBACK)
        self.assertEqual(params()["lookback_slots"], LOOKBACK)

    def test_it_is_the_same_span_b11a_already_inherited(self):
        """Reused geometry, not a new parameter. If these ever differ, one of them was retuned."""
        self.assertEqual(B11A.derive_window()["observation_span_slots"], LOOKBACK)

    def test_the_start_is_exactly_t0_minus_the_lookback(self):
        for slot in (FRESH_FIRST, 435_772_750, 437_211_659, 2_000_000):
            with self.subTest(slot=slot):
                self.assertEqual(window(slot)["start_slot_inclusive"], slot - LOOKBACK)

    def test_a_one_slot_drift_is_visible(self):
        got = window(FRESH_FIRST)["start_slot_inclusive"]
        self.assertNotEqual(got, FRESH_FIRST - LOOKBACK + 1)
        self.assertNotEqual(got, FRESH_FIRST - LOOKBACK - 1)
        self.assertEqual(got, 433_926_641)

    def test_at_the_observation_cutoff_the_window_starts_one_slot_after_the_burned_range(self):
        """A consequence of reusing the observation span, not a design. Stated as a test so that
        anyone who changes either constant sees the relationship break."""
        cutoff = B11A.derive_window()["observation_cutoff_slot_inclusive"]
        self.assertEqual(window(cutoff)["start_slot_inclusive"],
                         B11A.derive_window()["maximum_inclusive_burned_endpoint"] + 1)
        self.assertEqual(window(cutoff)["start_slot_inclusive"], FRESH_FIRST)

    def test_the_window_depends_on_nothing_but_t0_and_the_constant(self):
        """No history, count or coverage figure is an input, so there is nowhere to put an
        adaptive deepening."""
        import inspect
        signature = inspect.signature(B13E.lookback_window)
        self.assertEqual(list(signature.parameters), ["t0", "params"])
        self.assertFalse(params()["adaptive_depth_permitted"])

    def test_a_non_integer_coordinate_is_refused(self):
        for broken in ({"slot": "435569150"}, {"slot": 1.0}, {"slot": True}):
            with self.subTest(broken=broken):
                with self.assertRaisesRegex(B13E.ContractViolation, "must be an integer"):
                    B13E.lookback_window({**at(1), **broken})


class GenesisTests(unittest.TestCase):
    """Safe near slot zero, and honest about what the clamp costs."""

    def test_the_start_never_goes_negative(self):
        for slot in (0, 1, LOOKBACK - 1, LOOKBACK, LOOKBACK + 1):
            with self.subTest(slot=slot):
                self.assertGreaterEqual(window(slot)["start_slot_inclusive"], 0)

    def test_the_clamp_is_reported_rather_than_hidden(self):
        clamped = window(1_000)
        self.assertTrue(clamped["clamped_at_genesis"])
        self.assertEqual(clamped["start_slot_inclusive"], 0)
        self.assertEqual(clamped["unclamped_start_slot"], 1_000 - LOOKBACK)

    def test_exactly_at_the_lookback_the_clamp_does_not_bind(self):
        exact = window(LOOKBACK)
        self.assertFalse(exact["clamped_at_genesis"])
        self.assertEqual(exact["start_slot_inclusive"], 0)

    def test_a_clamped_window_claiming_completeness_is_refused(self):
        """A clamped window is shorter than the lookback; reporting it complete would claim
        knowledge of a period before the chain existed."""
        clamped = window(1_000)
        failures = B13E.actor_coverage_failures(
            coverage(clamped, earliest_slot_reached=0, left_truncated=False), clamped)
        self.assertIn(B13E.AB04_ACTOR_COVERAGE_SHORT,
                      [f["reason_code"] for f in failures])

    def test_a_clamped_window_marked_truncated_is_accepted(self):
        clamped = window(1_000)
        self.assertEqual(B13E.actor_coverage_failures(
            coverage(clamped, earliest_slot_reached=0, left_truncated=True), clamped), [])


class BoundaryTests(unittest.TestCase):
    """Slot-wise at the bottom, coordinate-wise at the top."""

    def setUp(self):
        self.t0 = at(FRESH_FIRST, 5, 3, 2)
        self.window = B13E.lookback_window(self.t0)
        self.start = self.window["start_slot_inclusive"]

    def test_the_whole_start_slot_is_included(self):
        """A coordinate-exact lower bound would make the window's length depend on where inside a
        slot the decision fell, so two decisions one instruction apart would get different
        histories for no defensible reason."""
        for index, outer, inner in ((0, 0, 0), (9_999, 30, 40), (0, -1, -1)):
            with self.subTest(coordinate=(index, outer, inner)):
                self.assertTrue(B13E.in_window(at(self.start, index, outer, inner), self.window))

    def test_one_slot_before_the_start_is_excluded(self):
        self.assertFalse(B13E.in_window(at(self.start - 1, 9_999, 99, 99), self.window))

    def test_the_upper_bound_is_inclusive_at_t0s_exact_coordinate(self):
        self.assertTrue(B13E.in_window(at(FRESH_FIRST, 5, 3, 2), self.window))

    def test_the_upper_bound_is_exclusive_one_coordinate_later(self):
        for later in (at(FRESH_FIRST, 5, 3, 3), at(FRESH_FIRST, 5, 4, 0), at(FRESH_FIRST, 6, 0, 0),
                      at(FRESH_FIRST + 1, 0, 0, 0)):
            with self.subTest(later=later):
                self.assertFalse(B13E.in_window(later, self.window))

    def test_the_two_bounds_use_different_granularities_on_purpose(self):
        self.assertEqual(self.window["lower_bound_granularity"], "slot")
        self.assertEqual(self.window["upper_bound_granularity"], "coordinate")
        self.assertEqual(params()["lower_bound_granularity"], "slot")
        self.assertEqual(params()["upper_bound_granularity"], "coordinate")


class WallClockTests(unittest.TestCase):
    """Defined in slots, applied in slots, never translated."""

    def test_converting_the_lookback_to_hours_is_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "not a frozen parameter"):
            B13E.hours_of_lookback(LOOKBACK)

    def test_the_document_forbids_translation(self):
        self.assertFalse(params()["wall_clock_translation_permitted"])
        self.assertEqual(params()["lookback_units"], "slots")

    def test_the_refusal_explains_why_rather_than_just_saying_no(self):
        try:
            B13E.hours_of_lookback()
        except B13E.ContractViolation as error:
            self.assertIn("Slot production varies", str(error))


class UnlockTests(unittest.TestCase):
    """No query before B11a's maturity and U3, because before that the cohort is unknown."""

    def test_a_matured_and_unlocked_state_is_accepted(self):
        self.assertTrue(B13E.assert_unlocked(unlocked()))

    def test_an_immature_window_refuses_every_query(self):
        with self.assertRaisesRegex(B13E.QueryRefused, "has not matured"):
            B13E.assert_unlocked(unlocked(mature=False))

    def test_a_failed_u3_refuses_every_query(self):
        with self.assertRaisesRegex(B13E.QueryRefused, "U3 criterion has not passed"):
            B13E.assert_unlocked(unlocked(u3=False))

    def test_the_guard_cannot_be_built_before_unlock(self):
        with self.assertRaises(B13E.QueryRefused):
            B13E.QueryGuard(unlocked(mature=False), [ACTOR_A])

    def test_the_guard_holds_no_endpoint_and_cannot_fetch(self):
        """Deliberately not a client: the only thing it can do is refuse."""
        guard = B13E.QueryGuard(unlocked(), [ACTOR_A])
        self.assertEqual(set(vars(guard)), {"params", "enumeration", "calls"})
        for attribute in ("get", "post", "send", "fetch", "request", "session", "endpoint", "url"):
            with self.subTest(attribute=attribute):
                self.assertFalse(hasattr(guard, attribute))

    def test_the_module_imports_nothing_that_could_reach_a_network(self):
        source = (ROOT / "scripts" / "b13e_collection_contract.py").read_text()
        for banned in ("import requests", "import urllib", "import http", "import socket",
                       "aiohttp", "websocket"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)


class CohortTests(unittest.TestCase):
    """Exactly B11a's enumeration. Not wider, not narrower."""

    def test_a_subject_inside_the_enumeration_is_accepted(self):
        self.assertTrue(B13E.assert_cohort([ACTOR_A], [ACTOR_A, ACTOR_B]))

    def test_a_subject_outside_the_enumeration_is_refused(self):
        with self.assertRaisesRegex(B13E.QueryRefused, "wider population"):
            B13E.assert_cohort([ACTOR_A, "SomeoneElse"], [ACTOR_A, ACTOR_B])

    def test_an_empty_enumeration_is_not_permission_to_collect_broadly(self):
        with self.assertRaisesRegex(B13E.QueryRefused, "not permission to collect broadly"):
            B13E.assert_cohort([ACTOR_A], [])

    def test_a_narrower_cohort_is_permitted_only_as_a_subset(self):
        """Collecting fewer is allowed; collecting OTHERS is not. Dropping members whose
        collection is awkward would select on collectability, which correlates with activity."""
        self.assertTrue(B13E.assert_cohort([ACTOR_A], [ACTOR_A, ACTOR_B]))
        self.assertTrue(B13E.assert_cohort([], [ACTOR_A, ACTOR_B]))

    def test_the_guard_refuses_a_query_for_a_subject_outside_the_cohort(self):
        guard = B13E.QueryGuard(unlocked(), [ACTOR_A])
        self.assertTrue(guard.permit("getSignaturesForAddress", ACTOR_A))
        with self.assertRaises(B13E.QueryRefused):
            guard.permit("getSignaturesForAddress", "SomeoneElse")

    def test_a_bare_string_is_not_a_collection_of_identifiers(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "must be collections"):
            B13E.assert_cohort(ACTOR_A, [ACTOR_A])


class MethodAndCredentialTests(unittest.TestCase):
    """An allowlist, and credentials refused rather than redacted."""

    def test_every_allowlisted_method_is_read_only(self):
        for method in params()["method_allowlist"]:
            with self.subTest(method=method):
                self.assertTrue(method.startswith("get"))
                self.assertTrue(B13E.assert_method_allowlisted(method))

    def test_anything_that_submits_or_signs_is_refused(self):
        for method in ("sendTransaction", "simulateTransaction", "signTransaction",
                       "requestAirdrop", "sendAndConfirmTransaction"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(B13E.QueryRefused, "not in the allowlist"):
                    B13E.assert_method_allowlisted(method)

    def test_an_unknown_method_is_refused_rather_than_assumed_safe(self):
        """An allowlist rather than a denylist, because the next client version adds a method
        nobody thought to forbid."""
        with self.assertRaises(B13E.QueryRefused):
            B13E.assert_method_allowlisted("getSomethingInventedNextYear")

    def test_a_credential_shaped_key_is_refused(self):
        for key in ("api_key", "apiKey", "secret", "Authorization", "private_key", "password"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(B13E.ContractViolation, "credential-shaped"):
                    B13E.assert_no_credential({"request": {key: "value"}})

    def test_a_credential_shaped_url_is_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "credential-shaped string"):
            B13E.assert_no_credential({"endpoint": "https://rpc.invalid/v1?api-key=abc123"})

    def test_a_hashed_endpoint_is_accepted(self):
        self.assertTrue(B13E.assert_no_credential({"endpoint_sha256": "a" * 64}))

    def test_the_guard_refuses_a_request_carrying_a_credential(self):
        guard = B13E.QueryGuard(unlocked(), [ACTOR_A])
        with self.assertRaises(B13E.ContractViolation):
            guard.permit("getSlot", None, {"headers": {"authorization": "Bearer x"}})


class PaginationTests(unittest.TestCase):
    """Exhaustion must be proved, and a page cap is not exhaustion."""

    def test_an_empty_final_page_is_exhaustion(self):
        self.assertTrue(B13E.pagination_exhausted(pagination()))

    def test_an_end_of_stream_is_exhaustion(self):
        self.assertTrue(B13E.pagination_exhausted(
            pagination(termination_condition=B13E.TERMINATION_END_OF_STREAM)))

    def test_a_page_cap_is_not_exhaustion(self):
        """A silent cap is the failure mode that produces a confidently wrong zero."""
        self.assertFalse(B13E.pagination_exhausted(
            pagination(termination_condition=B13E.TERMINATION_PAGE_CAP, final_cursor="cursor-9")))

    def test_an_unconsumed_cursor_is_not_exhaustion_whatever_the_stated_reason(self):
        self.assertFalse(B13E.pagination_exhausted(pagination(final_cursor="cursor-9")))

    def test_a_cap_hit_exactly_at_a_page_boundary_is_still_not_exhaustion(self):
        """The realistic silent cap: the last fetched page was full, the cursor came back empty by
        coincidence, and nobody asked for the next one. The stated termination is what decides."""
        self.assertFalse(B13E.pagination_exhausted(pagination(
            termination_condition=B13E.TERMINATION_PAGE_CAP, final_cursor=None,
            pages_fetched=10, page_cap=10)))

    def test_a_capped_run_marks_the_actor_incomplete(self):
        win = window()
        failures = B13E.actor_coverage_failures(
            coverage(win, pagination=pagination(
                termination_condition=B13E.TERMINATION_PAGE_CAP, final_cursor="c")), win)
        self.assertIn(B13E.AB03_PAGINATION_NOT_EXHAUSTED, [f["reason_code"] for f in failures])

    def test_we_had_enough_is_not_a_termination_condition(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "not a termination condition"):
            B13E.assert_pagination(pagination(termination_condition="we_had_enough"))

    def test_pagination_must_state_every_declared_field(self):
        for field in B13E.PAGINATION_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in pagination().items() if k != field}
                with self.assertRaisesRegex(B13E.ContractViolation, "does not state"):
                    B13E.assert_pagination(broken)


class CoverageTests(unittest.TestCase):
    """Per actor, never averaged, and a short source never shifts the start."""

    def test_a_complete_actor_has_no_failures(self):
        win = window()
        self.assertEqual(B13E.actor_coverage_failures(coverage(win), win), [])

    def test_a_short_source_reports_incomplete(self):
        win = window()
        short = coverage(win, earliest_slot_reached=win["start_slot_inclusive"] + 1)
        failures = B13E.actor_coverage_failures(short, win)
        self.assertEqual([f["reason_code"] for f in failures], [B13E.AB04_ACTOR_COVERAGE_SHORT])
        self.assertIn("NOT shifted", failures[0]["detail"])

    def test_a_shifted_start_is_caught_as_a_formula_mismatch(self):
        """Moving the start up to whatever the source had would silently redefine the parameter per
        actor, so the actors with the least history would get the shortest window."""
        win = window()
        shifted = coverage(win,
                           lookback_start_slot=win["start_slot_inclusive"] + 10_000,
                           earliest_slot_reached=win["start_slot_inclusive"] + 10_000)
        failures = B13E.actor_coverage_failures(shifted, win)
        self.assertIn(B13E.AB10_LOOKBACK_FORMULA_MISMATCH, [f["reason_code"] for f in failures])

    def test_a_one_slot_shift_is_caught(self):
        win = window()
        failures = B13E.actor_coverage_failures(
            coverage(win, lookback_start_slot=win["start_slot_inclusive"] + 1), win)
        self.assertIn(B13E.AB10_LOOKBACK_FORMULA_MISMATCH, [f["reason_code"] for f in failures])

    def test_a_decode_accounting_that_does_not_partition_is_refused(self):
        """B13a's partition is asserted here rather than trusted: an instruction that quietly fell
        out of the walk produces no edge, and no edge is indistinguishable from no funding."""
        win = window()
        with self.assertRaisesRegex(B13A.HistoryRefused, "instruction accounting sums"):
            B13E.actor_coverage_failures(
                coverage(win, decode_accounting=accounting(decoded_non_moving=1)), win)

    def test_missing_decode_accounting_is_a_failure(self):
        win = window()
        failures = B13E.actor_coverage_failures(coverage(win, decode_accounting=None), win)
        self.assertIn(B13E.AB05_DECODE_LOSS_AT_OR_BEFORE_T0, [f["reason_code"] for f in failures])

    def test_unresolved_evidence_at_or_before_t0_is_a_failure(self):
        win = window()
        unresolved = [{"reason_code": B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
                       "coordinate": at(FRESH_FIRST - 1), "detail": "a payload the ABI refuses"}]
        failures = B13E.actor_coverage_failures(
            coverage(win, decode_accounting=accounting(
                system_instructions_total=1, undecodable=1, unresolved=unresolved)), win)
        self.assertIn(B13E.AB05_DECODE_LOSS_AT_OR_BEFORE_T0, [f["reason_code"] for f in failures])

    def test_unresolved_evidence_after_t0_is_not(self):
        win = window()
        unresolved = [{"reason_code": B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
                       "coordinate": at(FRESH_FIRST + 10), "detail": "a payload the ABI refuses"}]
        failures = B13E.actor_coverage_failures(
            coverage(win, decode_accounting=accounting(
                system_instructions_total=1, undecodable=1, unresolved=unresolved)), win)
        self.assertEqual(failures, [])

    def test_missing_source_hashes_and_unpreserved_raw_are_failures(self):
        win = window()
        cases = {B13E.AB07_SOURCE_HASH_DRIFT: {"source_hashes": []},
                 B13E.AB09_RAW_NOT_PRESERVED: {"raw_preserved": False}}
        for expected, override in cases.items():
            with self.subTest(expected=expected):
                failures = B13E.actor_coverage_failures(coverage(win, **override), win)
                self.assertIn(expected, [f["reason_code"] for f in failures])

    def test_coverage_must_state_every_declared_field(self):
        win = window()
        for field in B13E.COVERAGE_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in coverage(win).items() if k != field}
                with self.assertRaisesRegex(B13E.ContractViolation, "does not state"):
                    B13E.actor_coverage_failures(broken, win)


class NoAveragingTests(unittest.TestCase):
    """An average is exactly the statistic that hides the one actor whose history is missing."""

    def windows(self):
        return {ACTOR_A: window(), ACTOR_B: window()}

    def test_one_short_actor_makes_the_whole_collection_incomplete(self):
        wins = self.windows()
        short = coverage(wins[ACTOR_B], actor=ACTOR_B,
                         earliest_slot_reached=wins[ACTOR_B]["start_slot_inclusive"] + 1)
        result = B13E.cohort_completeness([coverage(wins[ACTOR_A]), short], wins)
        self.assertEqual(result["actors"], 2)
        self.assertEqual(result["actors_complete"], 1)
        self.assertEqual(result["actors_incomplete"], [ACTOR_B])
        self.assertFalse(result["collection_complete"])

    def test_the_aggregate_is_an_and_not_a_mean(self):
        """Ninety-nine complete actors and one short one is an incomplete collection, and there is
        no percentage to pick because picking one would require averaging."""
        wins = {f"actor-{i}": window() for i in range(100)}
        coverages = [coverage(wins[a], actor=a) for a in wins]
        coverages[57] = coverage(wins["actor-57"], actor="actor-57",
                                 earliest_slot_reached=wins["actor-57"]["start_slot_inclusive"] + 1)
        result = B13E.cohort_completeness(coverages, wins)
        self.assertEqual(result["actors_complete"], 99)
        self.assertFalse(result["collection_complete"])
        self.assertEqual(result["actors_incomplete"], ["actor-57"])

    def test_asking_for_the_fraction_is_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "hides the single actor"):
            B13E.coverage_fraction([], {})

    def test_the_result_publishes_no_fraction_of_its_own(self):
        wins = self.windows()
        result = B13E.cohort_completeness(
            [coverage(wins[ACTOR_A]), coverage(wins[ACTOR_B], actor=ACTOR_B)], wins)
        text = json.dumps(result, sort_keys=True).lower()
        for banned in ("fraction", "percent", "mean", "average", "ratio"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)

    def test_every_actor_gets_its_own_verdict(self):
        wins = self.windows()
        result = B13E.cohort_completeness(
            [coverage(wins[ACTOR_A]), coverage(wins[ACTOR_B], actor=ACTOR_B)], wins)
        self.assertEqual(set(result["per_actor"]), {ACTOR_A, ACTOR_B})

    def test_a_duplicate_coverage_record_is_refused(self):
        wins = self.windows()
        with self.assertRaisesRegex(B13E.ContractViolation, "silently replace"):
            B13E.cohort_completeness([coverage(wins[ACTOR_A]), coverage(wins[ACTOR_A])], wins)

    def test_the_document_forbids_averaging(self):
        self.assertFalse(params()["coverage_averaging_permitted"])
        self.assertEqual(params()["coverage_granularity"], "per_actor")
        edited = dict(params(), coverage_averaging_permitted=True)
        with self.assertRaises(B13E.PreregistrationMismatch):
            B13E.cohort_completeness([], {}, edited)


class BurnedDataTests(unittest.TestCase):
    """Context yes, evidence no — two checks against two different things."""

    def burned_slot(self):
        return B11A.normalized_burned_ranges()[0][1]

    def unburned_slot_inside_lookback(self):
        """A slot the earliest fresh decision can see that is NOT burned. Note that FRESH_FIRST - 1
        is itself the last burned slot — the fresh window starts one slot after the maximum burned
        endpoint — so "just before t0" is the wrong place to look for one."""
        win = window(FRESH_FIRST)
        for candidate in range(win["start_slot_inclusive"], FRESH_FIRST, 1_000):
            if not B13E.slot_is_burned(candidate):
                return candidate
        raise AssertionError("no unburned slot lies inside the earliest fresh lookback")

    def burned_slot_inside_lookback(self):
        """A burned slot the earliest fresh decision can actually see. The B8b range straddles the
        lookback start, which is precisely why the context rule matters."""
        win = window(FRESH_FIRST)
        for _, first, last in B11A.normalized_burned_ranges():
            candidate = max(first, win["start_slot_inclusive"])
            if candidate <= last:
                return candidate
        raise AssertionError("no burned slot lies inside the earliest fresh lookback")

    def test_the_burned_ranges_are_recognised(self):
        self.assertTrue(B13E.slot_is_burned(self.burned_slot()))
        self.assertFalse(B13E.slot_is_burned(FRESH_FIRST))

    def test_a_burned_event_may_be_prior_context(self):
        self.assertTrue(B13E.assert_burned_role(self.burned_slot(), B13E.ROLE_PRIOR_CONTEXT))

    def test_a_burned_member_may_never_be_evidence(self):
        for role in (B13E.ROLE_EVALUATED_SUBJECT, B13E.ROLE_LABEL_SOURCE, B13E.ROLE_TUNING_DATA,
                     B13E.ROLE_PERFORMANCE_EVIDENCE):
            with self.subTest(role=role):
                with self.assertRaisesRegex(B13E.ContractViolation, "never appear in a METRIC"):
                    B13E.assert_burned_role(self.burned_slot(), role)

    def test_a_fresh_slot_is_unrestricted_in_every_role(self):
        for role in B13E.BURNED_ROLES:
            with self.subTest(role=role):
                self.assertTrue(B13E.assert_burned_role(FRESH_FIRST, role))

    def test_the_document_and_the_code_must_agree_about_each_role(self):
        """The burned-role table exists in BOTH places, so it is cross-checked past the hash. A
        document re-pinned after loosening one of these is exactly the case the second copy is for,
        and it is reached here by supplying the matching pin."""
        fields = {"burned_members_permitted_as_examples": B13E.ROLE_EVALUATED_SUBJECT,
                  "burned_members_permitted_as_labels": B13E.ROLE_LABEL_SOURCE,
                  "burned_members_permitted_as_tuning_data": B13E.ROLE_TUNING_DATA,
                  "burned_members_permitted_as_performance_evidence":
                      B13E.ROLE_PERFORMANCE_EVIDENCE,
                  "burned_events_permitted_as_context": B13E.ROLE_PRIOR_CONTEXT}
        for field, role in fields.items():
            with self.subTest(field=field):
                edited = dict(params(), **{field: not params()[field]})
                # The hash catches it first when the pin is untouched...
                with self.assertRaisesRegex(B13E.PreregistrationMismatch, "hash to"):
                    B13E.assert_burned_role(self.burned_slot(), role, edited)
                # ...and the code's own table catches it when the pin has been replaced.
                with self.assertRaisesRegex(B13E.PreregistrationMismatch, "disagree about whether"):
                    B13E.assert_burned_role(self.burned_slot(), role, edited,
                                            expected=B13E.preregistration_hash(edited))

    def test_burned_context_may_not_be_excluded_entirely(self):
        """A creator who demonstrably launched during a burned range must not be reported as
        having none. That zero would be a collection artefact presented as a fact."""
        burned = self.burned_slot_inside_lookback()
        events = [at(burned), at(burned + 1), at(self.unburned_slot_inside_lookback())]
        win = window()
        self.assertTrue(B13E.assert_context_not_excluded(win, events, events))

    def test_dropping_burned_events_from_the_window_is_caught(self):
        burned = self.burned_slot_inside_lookback()
        win = window()
        events = [at(burned), at(self.unburned_slot_inside_lookback())]
        retained = [e for e in events if not B13E.slot_is_burned(e["slot"])]
        self.assertEqual(len(retained), 1)
        with self.assertRaisesRegex(B13E.ContractViolation, "collection artefact"):
            B13E.assert_context_not_excluded(win, events, retained)

    def test_dropping_a_non_burned_event_is_also_caught(self):
        win = window()
        unburned = self.unburned_slot_inside_lookback()
        events = [at(unburned), at(unburned + 1)]
        with self.assertRaisesRegex(B13E.ContractViolation, "silently shortened"):
            B13E.assert_context_not_excluded(win, events, events[:1])

    def test_retaining_something_past_t0_is_caught(self):
        win = window()
        events = [at(self.unburned_slot_inside_lookback())]
        with self.assertRaisesRegex(B13E.ContractViolation, "the leak this whole contract"):
            B13E.assert_context_not_excluded(win, events, events + [at(FRESH_FIRST + 1)])

    def test_the_slot_before_the_fresh_window_is_itself_burned(self):
        """A consequence of B11a starting one slot after the maximum burned endpoint, worth
        pinning: anyone reaching for "just before t0" as an unburned fixture gets a burned one."""
        self.assertTrue(B13E.slot_is_burned(FRESH_FIRST - 1))
        self.assertFalse(B13E.slot_is_burned(FRESH_FIRST))

    def test_the_lookback_genuinely_reaches_burned_territory(self):
        """If it ever stopped doing so, the context rule would be untested by construction."""
        win = window(FRESH_FIRST)
        burned = self.burned_slot_inside_lookback()
        self.assertTrue(B13E.slot_is_burned(burned))
        self.assertTrue(B13E.in_window(at(burned), win))
        self.assertGreaterEqual(burned, win["start_slot_inclusive"])

    def test_a_role_outside_the_declared_set_is_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "is not one of"):
            B13E.assert_burned_role(self.burned_slot(), "sort_of_context")


class SnapshotTests(unittest.TestCase):
    """One slot, or it is not a snapshot of anything."""

    def test_a_single_slot_is_atomic(self):
        self.assertEqual(B13E.assert_snapshot_atomic([430_000_000] * 5), 430_000_000)

    def test_balances_read_across_slots_are_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "appear twice or vanish"):
            B13E.assert_snapshot_atomic([430_000_000, 430_000_001])

    def test_a_snapshot_observed_at_no_slot_is_refused(self):
        with self.assertRaisesRegex(B13E.ContractViolation, "observed at no slot"):
            B13E.assert_snapshot_atomic([])

    def test_the_document_requires_atomicity(self):
        self.assertTrue(params()["snapshot_must_be_atomic_at_one_slot"])


class PlanTests(unittest.TestCase):
    """A plan, not a collection."""

    def test_a_plan_states_that_it_collected_nothing(self):
        plan = B13E.plan_collection({ACTOR_A: at(FRESH_FIRST)}, [ACTOR_A, ACTOR_B])
        self.assertFalse(plan["collection_performed"])
        self.assertEqual(plan["cohort_size"], 1)
        self.assertEqual(plan["lookback_slots"], LOOKBACK)

    def test_a_plan_pins_the_preregistration_it_was_built_under(self):
        plan = B13E.plan_collection({ACTOR_A: at(FRESH_FIRST)}, [ACTOR_A])
        self.assertEqual(plan["preregistration_sha256"], B13E.PREREGISTRATION_PARAMS_SHA256)
        self.assertEqual(plan["preregistration_id"], B13E.PREREGISTRATION_ID)

    def test_a_plan_for_a_subject_outside_the_cohort_is_refused(self):
        with self.assertRaises(B13E.QueryRefused):
            B13E.plan_collection({"SomeoneElse": at(FRESH_FIRST)}, [ACTOR_A])

    def test_every_window_in_a_plan_follows_the_formula(self):
        decisions = {ACTOR_A: at(FRESH_FIRST), ACTOR_B: at(FRESH_FIRST + 500, 3, 2, 1)}
        plan = B13E.plan_collection(decisions, [ACTOR_A, ACTOR_B])
        for actor, t0 in decisions.items():
            with self.subTest(actor=actor):
                self.assertEqual(plan["windows"][actor]["start_slot_inclusive"],
                                 t0["slot"] - LOOKBACK)

    def test_a_plan_is_deterministic(self):
        decisions = {ACTOR_B: at(FRESH_FIRST + 9), ACTOR_A: at(FRESH_FIRST)}
        first = B13E.plan_collection(decisions, [ACTOR_A, ACTOR_B])
        second = B13E.plan_collection(dict(reversed(list(decisions.items()))),
                                      [ACTOR_B, ACTOR_A])
        self.assertEqual(first["plan_sha256"], second["plan_sha256"])

    def test_a_plan_carrying_a_credential_is_refused(self):
        with self.assertRaises(B13E.ContractViolation):
            B13E.plan_collection({"actor?api_key=secret": at(FRESH_FIRST)},
                                 ["actor?api_key=secret"])


class ScopeTests(unittest.TestCase):
    """What this pass did not do, asserted rather than promised."""

    def test_the_contract_reports_no_queries_and_no_enumeration(self):
        import io, contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B13E.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertEqual(contract["queries_made"], 0)
        self.assertFalse(contract["b11a_enumerated"])
        self.assertFalse(contract["collection_performed"])
        self.assertFalse(contract["coverage_averaging_permitted"])
        self.assertFalse(contract["wall_clock_translation_permitted"])

    def test_no_cluster_probability_or_threshold_is_authorised(self):
        self.assertFalse(params()["clusters_permitted"])
        self.assertFalse(params()["probabilities_permitted"])
        self.assertEqual(params()["thresholds_chosen"], [])

    def test_b11bs_baseline_is_not_altered(self):
        self.assertFalse(params()["alters_b11b_baseline"])

    def test_every_abort_code_is_declared_in_both_places(self):
        self.assertEqual(list(B13E.ABORT_CODES), params()["abort_codes"])

    def test_the_preregistration_was_committed_before_this_module(self):
        """Not a file-system fact but a repository one, so it is checked against git rather than
        asserted in prose."""
        import subprocess
        def first_commit(path):
            found = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%H", "--", path],
                cwd=ROOT, capture_output=True, text=True).stdout.split()
            return found[-1] if found else None
        prereg = first_commit("research/B13E_LOOKBACK_PREREGISTRATION.md")
        order = subprocess.run(["git", "rev-list", "--topo-order", "HEAD"],
                               cwd=ROOT, capture_output=True, text=True).stdout.split()
        module = first_commit("scripts/b13e_collection_contract.py")
        if module:                       # unset until this file is itself committed
            self.assertGreater(order.index(prereg), order.index(module),
                               "the preregistration must be an ANCESTOR of this module")
        else:
            self.assertTrue(prereg, "the preregistration must already be committed")


if __name__ == "__main__":
    unittest.main()
