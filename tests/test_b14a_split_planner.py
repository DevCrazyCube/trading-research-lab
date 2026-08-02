"""Tests for the B14a leakage-safe split planner.

Synthetic rows only. No model is fitted, no window is eligible, no metric is computed and B11a is
never touched.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b14a_split_fixtures", "b14a_split_fixtures.py")
SPLIT = FIXTURES.SPLIT
B10B = SPLIT.B10B

at = FIXTURES.at
row = FIXTURES.row
TRAIN, VALIDATION, TEST = SPLIT.SEGMENT_TRAIN, SPLIT.SEGMENT_VALIDATION, SPLIT.SEGMENT_TEST


def spec(**overrides):
    base = FIXTURES.build_spec()
    folds = overrides.pop("folds", None)
    base.update(overrides)
    if folds is not None:
        base["folds"] = folds
    return base


def one_fold(train=(1_000, 2_000), validation=(2_500, 3_000), test=(4_000, 4_500),
             fold_id="fold-1"):
    return {"fold_id": fold_id,
            "train": {"first_slot_inclusive": train[0], "last_slot_inclusive": train[1]},
            "validation": {"first_slot_inclusive": validation[0],
                           "last_slot_inclusive": validation[1]},
            "test": {"first_slot_inclusive": test[0], "last_slot_inclusive": test[1]}}


def assigned(plan, segment):
    return [row_id for fold in plan["folds"] for row_id in fold["rows"][segment]]


def excluded_for(plan, row_id):
    return [e["reason_code"] for e in plan["exclusions"] if e["row_id"] == row_id]


# --------------------------------------------------------------------------------------------

class PurgeTests(unittest.TestCase):
    """The purge is computed on the label window end, never on t0."""

    def plan_with(self, label_end_slot, purge=50):
        # t0 sits comfortably inside training; only the label window reaches forward.
        subject = row("subject", 1_100, "CreatorSubject", "UserSubject", value=1)
        subject["label_window_end_slot"] = label_end_slot
        return SPLIT.plan_split([subject], spec(purge_slots=purge, folds=[one_fold()]))

    def test_a_label_window_ending_well_before_the_boundary_survives(self):
        plan = self.plan_with(2_000)
        self.assertEqual(assigned(plan, TRAIN), ["subject"])

    def test_the_purge_boundary_is_exact_to_one_slot(self):
        """validation begins at 2,500 and the purge is 50, so the last surviving label window ends
        at 2,449: 2,449 + 50 = 2,499 < 2,500."""
        self.assertEqual(assigned(self.plan_with(2_449), TRAIN), ["subject"])
        self.assertEqual(assigned(self.plan_with(2_450), TRAIN), [])
        self.assertEqual(excluded_for(self.plan_with(2_450), "subject"),
                         [SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP])

    def test_a_one_slot_overlap_is_caught(self):
        """The label window reaches exactly one slot into validation, with no purge at all."""
        plan = SPLIT.plan_split(
            [dict(row("subject", 1_100, "C", "U", value=1), label_window_end_slot=2_500)],
            spec(purge_slots=0, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), [])
        self.assertEqual(excluded_for(plan, "subject"),
                         [SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP])

    def test_one_slot_short_of_the_boundary_survives_with_no_purge(self):
        plan = SPLIT.plan_split(
            [dict(row("subject", 1_100, "C", "U", value=1), label_window_end_slot=2_499)],
            spec(purge_slots=0, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["subject"])

    def test_a_bigger_purge_removes_more(self):
        for purge, survives in ((0, True), (50, True), (100, False), (1_000, False)):
            with self.subTest(purge=purge):
                plan = SPLIT.plan_split(
                    [dict(row("subject", 1_100, "C", "U", value=1),
                          label_window_end_slot=2_420)],
                    spec(purge_slots=purge, folds=[one_fold()]))
                self.assertEqual(bool(assigned(plan, TRAIN)), survives)

    def test_the_binding_boundary_is_the_earliest_evaluation_instant(self):
        """A window reaching test has already reached validation, because chronology is enforced.
        The purge therefore measures against the earliest evaluation instant, and says so."""
        plan = SPLIT.plan_split(
            [dict(row("subject", 1_100, "C", "U", value=1), label_window_end_slot=3_990)],
            spec(purge_slots=50, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), [])
        reason = next(e for e in plan["exclusions"] if e["row_id"] == "subject")
        self.assertEqual(reason["segment"], VALIDATION)
        self.assertIn("first evaluation instant", reason["detail"])

    def test_a_hand_built_plan_with_a_purge_violation_is_refused(self):
        subject = dict(row("subject", 1_100, "C", "U", value=1), label_window_end_slot=1_200)
        rows = SPLIT.ordered_rows([subject])
        plan = SPLIT.plan_split(rows, spec(purge_slots=0, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["subject"])
        # Widen the purge underneath the finished plan, as a hand-edited one would. The ranges are
        # left alone so the chronology check cannot fire first and mask this.
        plan["purge_slots"] = 2_000
        with self.assertRaisesRegex(SPLIT.SplitRefused, "labelled by the period"):
            SPLIT.assert_split_plan(plan, {r["row_id"]: r for r in rows},
                                    SPLIT.identity_groups(rows))

    def test_t0_alone_cannot_see_the_overlap(self):
        """Both rows have the same t0. Only the label window distinguishes them, which is the whole
        argument for computing the purge on the window end."""
        early = dict(row("early", 1_100, "C1", "U1", value=1), label_window_end_slot=1_500)
        late = dict(row("late", 1_100, "C2", "U2", value=1), label_window_end_slot=2_600)
        plan = SPLIT.plan_split([early, late], spec(purge_slots=0, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["early"])
        self.assertEqual(excluded_for(plan, "late"), [SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP])

    def test_a_label_window_ending_before_its_own_decision_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "cannot finish being observed"):
            SPLIT.assert_row(dict(row("subject", 1_100, "C", "U"), label_window_end_slot=1_000))

    def test_the_purge_rule_travels_on_the_plan(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertEqual(plan["purge_rule"], SPLIT.PURGE_RULE)
        plan["purge_rule"] = "roughly before the boundary"
        with self.assertRaisesRegex(SPLIT.SplitRefused, "not the one this module applies"):
            SPLIT.assert_split_plan(plan, {}, {})


class EmbargoTests(unittest.TestCase):
    """Rows just after an evaluation period carry its residue into the next training set."""

    def two_folds(self):
        return [one_fold(fold_id="fold-1"),
                one_fold(fold_id="fold-2", train=(4_400, 6_000), validation=(6_500, 7_000),
                         test=(8_000, 8_500))]

    def test_a_row_inside_the_embargo_is_excluded_from_later_training(self):
        subject = dict(row("after-test", 4_450, "C", "U", value=1),
                       label_window_end_slot=4_500)
        plan = SPLIT.plan_split([subject], spec(embargo_slots=100, folds=self.two_folds()))
        self.assertEqual(excluded_for(plan, "after-test"),
                         [SPLIT.X03_EMBARGOED_AFTER_EVALUATION])

    def test_a_row_past_the_embargo_survives(self):
        subject = dict(row("well-after", 4_601, "C", "U", value=1),
                       label_window_end_slot=4_700)
        plan = SPLIT.plan_split([subject], spec(embargo_slots=100, folds=self.two_folds()))
        self.assertEqual(assigned(plan, TRAIN), ["well-after"])

    def test_the_embargo_boundary_is_exact_to_one_slot(self):
        """fold-1's test ends at 4,500 and the embargo is 100, so 4,600 is the first admissible
        t0."""
        for slot, survives in ((4_599, False), (4_600, True)):
            with self.subTest(slot=slot):
                subject = dict(row("edge", slot, "C", "U", value=1),
                               label_window_end_slot=slot + 10)
                plan = SPLIT.plan_split([subject],
                                        spec(embargo_slots=100, folds=self.two_folds()))
                self.assertEqual(bool(assigned(plan, TRAIN)), survives)

    def test_the_first_fold_has_no_preceding_evaluation_to_embargo_against(self):
        subject = row("first", 1_000, "C", "U", value=1)
        plan = SPLIT.plan_split([subject], spec(embargo_slots=10_000, folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["first"])

    def test_the_embargo_rule_travels_on_the_plan(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertEqual(plan["embargo_rule"], SPLIT.EMBARGO_RULE)


class ChronologyTests(unittest.TestCase):
    """Validation and test never precede training, and walk-forward means forward."""

    def test_a_reversed_train_and_test_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "training on the answer"):
            SPLIT.assert_split_spec(spec(folds=[one_fold(train=(4_000, 4_500),
                                                         validation=(2_500, 3_000),
                                                         test=(1_000, 2_000))]))

    def test_validation_before_training_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "not strictly chronological"):
            SPLIT.assert_split_spec(spec(folds=[one_fold(train=(2_500, 3_000),
                                                         validation=(1_000, 2_000))]))

    def test_test_before_validation_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "not strictly chronological"):
            SPLIT.assert_split_spec(spec(folds=[one_fold(validation=(4_600, 5_000),
                                                         test=(4_000, 4_500))]))

    def test_touching_segments_are_refused(self):
        """Training ending on the slot validation begins is not a boundary, it is an overlap."""
        with self.assertRaisesRegex(SPLIT.SplitRefused, "not strictly chronological"):
            SPLIT.assert_split_spec(spec(folds=[one_fold(train=(1_000, 2_500),
                                                         validation=(2_500, 3_000))]))

    def test_a_later_fold_may_not_evaluate_before_an_earlier_one(self):
        folds = [one_fold(fold_id="fold-1"),
                 one_fold(fold_id="fold-2", train=(1_000, 2_000), validation=(2_500, 3_000),
                          test=(3_500, 3_900))]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "walk-forward means forward"):
            SPLIT.assert_split_spec(spec(folds=folds))

    def test_a_range_that_ends_before_it_begins_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "ends before it begins"):
            SPLIT.assert_split_spec(spec(folds=[one_fold(train=(2_000, 1_000))]))

    def test_a_duplicate_fold_id_is_refused(self):
        folds = [one_fold(fold_id="fold-1"),
                 one_fold(fold_id="fold-1", train=(4_400, 6_000), validation=(6_500, 7_000),
                          test=(8_000, 8_500))]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "appears twice"):
            SPLIT.assert_split_spec(spec(folds=folds))

    def test_a_finished_plan_is_rechecked_for_chronology(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        plan["folds"][0]["ranges"]["validation"]["first_slot_inclusive"] = 500
        with self.assertRaisesRegex(SPLIT.SplitRefused, "not strictly chronological"):
            SPLIT.assert_split_plan(plan, {}, {})


class NoDefaultsTests(unittest.TestCase):
    """Every span is the caller's, and must arrive with a preregistration reference."""

    def test_every_required_field_is_required(self):
        for field in SPLIT.SPLIT_SPEC_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in spec().items() if k != field}
                with self.assertRaisesRegex(SPLIT.SplitRefused, "does not state"):
                    SPLIT.assert_split_spec(broken)

    def test_the_refusal_says_why_there_is_no_default(self):
        broken = {k: v for k, v in spec().items() if k != "purge_slots"}
        try:
            SPLIT.assert_split_spec(broken)
        except SPLIT.SplitRefused as error:
            self.assertIn("chosen after seeing which side scored better", str(error))

    def test_a_spec_without_a_preregistration_reference_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "non-empty string"):
            SPLIT.assert_split_spec(spec(preregistration_reference=""))

    def test_a_spec_without_a_rationale_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "non-empty string"):
            SPLIT.assert_split_spec(spec(rationale=""))

    def test_a_negative_span_is_refused(self):
        for field in ("purge_slots", "embargo_slots"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(SPLIT.SplitRefused, "must not be negative"):
                    SPLIT.assert_split_spec(spec(**{field: -1}))

    def test_the_contract_offers_no_defaults(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            SPLIT.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertEqual(contract["defaults_offered"], [])

    def test_a_spec_with_no_folds_plans_nothing(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "plans nothing"):
            SPLIT.assert_split_spec(spec(folds=[]))


class IdentityUnionTests(unittest.TestCase):
    """R5: the transitive closure of exact identity equality, with creator and user pooled."""

    def test_the_actor_bridge_puts_a_b_and_c_in_one_group(self):
        """A—B share a creator, B—C share a user, and nothing links A to C directly."""
        rows = SPLIT.ordered_rows([
            row("a", 1_000, "SharedCreator", "UserA", value=1),
            row("b", 1_100, "SharedCreator", "SharedUser", value=1),
            row("c", 1_200, "CreatorC", "SharedUser", value=1)])
        groups = SPLIT.identity_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(next(iter(groups.values()))), ["a", "b", "c"])

    def test_the_role_swap_is_caught_because_identities_are_pooled(self):
        """One address creates in one row and trades in another. A separate creator-space and
        user-space would let the same person sit on both sides of a boundary."""
        rows = SPLIT.ordered_rows([
            row("creates", 1_000, "SameAddress", "UserX", value=1),
            row("trades", 1_100, "CreatorY", "SameAddress", value=1)])
        groups = SPLIT.identity_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(next(iter(groups.values()))), ["creates", "trades"])

    def test_unrelated_rows_stay_in_separate_groups(self):
        rows = SPLIT.ordered_rows([row("a", 1_000, "C1", "U1", value=1),
                                   row("b", 1_100, "C2", "U2", value=1)])
        self.assertEqual(len(SPLIT.identity_groups(rows)), 2)

    def test_a_group_spanning_two_segments_is_dropped_whole(self):
        """Splitting it would put an actor's own future in their training set; keeping the larger
        half would select on which side happened to have more rows."""
        rows = [row("train-side", 1_000, "SpanningCreator", "UserA", value=1),
                row("validation-side", 2_600, "SpanningCreator", "UserB", value=1)]
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), [])
        self.assertEqual(assigned(plan, VALIDATION), [])
        for row_id in ("train-side", "validation-side"):
            with self.subTest(row=row_id):
                self.assertEqual(excluded_for(plan, row_id), [SPLIT.X04_GROUP_SPANS_SEGMENTS])

    def test_a_bridged_group_spanning_a_boundary_is_dropped_whole(self):
        """The bridge again, this time across a fold boundary: A in training, C in validation, and
        only B connects them."""
        rows = [row("a", 1_000, "BridgeCreator", "UserA", value=1),
                row("b", 1_200, "BridgeCreator", "BridgeUser", value=1),
                row("c", 2_600, "CreatorC", "BridgeUser", value=1)]
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        self.assertEqual(plan["accounting"]["rows_assigned"], 0)
        self.assertEqual(sorted(e["row_id"] for e in plan["exclusions"]), ["a", "b", "c"])

    def test_a_group_wholly_inside_one_segment_is_kept(self):
        rows = [row("a", 1_000, "SharedCreator", "UserA", value=1),
                row("b", 1_100, "SharedCreator", "UserB", value=1)]
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["a", "b"])
        self.assertEqual(len(plan["folds"][0]["groups"][TRAIN]), 1)

    def test_a_hand_built_plan_with_a_spanning_group_is_refused(self):
        rows = SPLIT.ordered_rows([
            row("train-side", 1_000, "SpanningCreator", "UserA", value=1),
            row("validation-side", 2_600, "SpanningCreator", "UserB", value=1)])
        groups = SPLIT.identity_groups(rows)
        plan = SPLIT.plan_split([rows[0]], spec(folds=[one_fold()]))
        plan["folds"][0]["rows"][VALIDATION] = ["validation-side"]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "an actor's own future"):
            SPLIT.assert_split_plan(plan, {r["row_id"]: r for r in rows}, groups)

    def test_the_group_key_is_a_property_of_the_membership(self):
        """Not of whichever root the union-find happened to pick. A key derived from the root
        changes when the traversal does, and two identical groupings would then look different."""
        groups = SPLIT.identity_groups(SPLIT.ordered_rows([
            row("a", 1_000, "SharedCreator", "UserA", value=1),
            row("b", 1_100, "SharedCreator", "UserB", value=1),
            row("c", 1_200, "OtherCreator", "UserC", value=1)]))
        for key, members in groups.items():
            with self.subTest(key=key):
                self.assertEqual(key, SPLIT.group_key(members))
        forward = SPLIT.identity_groups(SPLIT.ordered_rows([
            row("a", 1_000, "SharedCreator", "UserA", value=1),
            row("b", 1_100, "SharedCreator", "UserB", value=1)]))
        backward = SPLIT.identity_groups(SPLIT.ordered_rows([
            row("b", 1_100, "SharedCreator", "UserB", value=1),
            row("a", 1_000, "SharedCreator", "UserA", value=1)]))
        self.assertEqual(forward, backward)

    def test_the_r5_rule_travels_on_the_plan(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertEqual(plan["r5_rule"], SPLIT.R5_RULE)


class CensoredLabelTests(unittest.TestCase):
    """A right-censored outcome is not a zero."""

    def test_a_censored_row_carrying_a_value_is_refused_at_the_door(self):
        for status in (SPLIT.LABEL_RIGHT_CENSORED, SPLIT.LABEL_UNAVAILABLE):
            for value in (0, False, 1):
                with self.subTest(status=status, value=value):
                    broken = dict(row("subject", 1_000, "C", "U"), label_status=status,
                                  label_value=value)
                    with self.assertRaisesRegex(SPLIT.SplitRefused, "is NOT a zero"):
                        SPLIT.assert_row(broken)

    def test_a_censored_row_is_excluded_rather_than_used(self):
        rows = [row("censored", 1_000, "C", "U", status=SPLIT.LABEL_RIGHT_CENSORED),
                row("observed", 1_100, "C2", "U2", value=1)]
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        self.assertEqual(assigned(plan, TRAIN), ["observed"])
        self.assertEqual(excluded_for(plan, "censored"), [SPLIT.X01_LABEL_NOT_OBSERVED])

    def test_an_unavailable_row_is_excluded_from_evaluation_too(self):
        rows = [row("unavailable", 2_600, "C", "U", status=SPLIT.LABEL_UNAVAILABLE)]
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        self.assertEqual(assigned(plan, VALIDATION), [])
        self.assertEqual(excluded_for(plan, "unavailable"), [SPLIT.X01_LABEL_NOT_OBSERVED])

    def test_a_hand_built_plan_assigning_a_censored_row_is_refused(self):
        censored = row("censored", 1_000, "C", "U", status=SPLIT.LABEL_RIGHT_CENSORED)
        observed = row("observed", 1_100, "C2", "U2", value=1)
        rows = SPLIT.ordered_rows([censored, observed])
        groups = SPLIT.identity_groups(rows)
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        plan["folds"][0]["rows"][TRAIN] = ["censored", "observed"]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "never recoded"):
            SPLIT.assert_split_plan(plan, {r["row_id"]: r for r in rows}, groups)

    def test_the_three_statuses_stay_distinguishable(self):
        self.assertEqual(len(set(SPLIT.LABEL_STATUSES)), 3)
        with self.assertRaisesRegex(SPLIT.SplitRefused, "is not one of"):
            SPLIT.assert_row(dict(row("subject", 1_000, "C", "U"), label_status="probably_zero"))


class HorizonTests(unittest.TestCase):
    """One purge span cannot be correct for two different label windows."""

    def test_a_row_from_another_horizon_is_refused(self):
        rows = [row("ours", 1_000, "C", "U", value=1),
                row("theirs", 1_100, "C2", "U2", value=1, horizon="synthetic_horizon_60_slots")]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "planned separately"):
            SPLIT.plan_split(rows, spec(folds=[one_fold()]))

    def test_a_row_from_another_target_is_refused(self):
        rows = [row("ours", 1_000, "C", "U", value=1),
                row("theirs", 1_100, "C2", "U2", value=1, target="synthetic_target_b")]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "planned separately"):
            SPLIT.plan_split(rows, spec(folds=[one_fold()]))

    def test_a_plan_carries_the_single_target_and_horizon_it_covers(self):
        plan = SPLIT.plan_split([row("ours", 1_000, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertEqual(plan["target_id"], FIXTURES.TARGET)
        self.assertEqual(plan["horizon_id"], FIXTURES.HORIZON)


class AssociationGateTests(unittest.TestCase):
    """The exact-identity union is permitted. Association evidence is not."""

    def ledger(self):
        return {"confidence_status": "uncalibrated_evidence_only", "links": [],
                "evidence_hash_chain_sha256": "0" * 64}

    def test_a_ledger_passed_alongside_the_rows_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "ASSOCIATION EVIDENCE LEDGER"):
            SPLIT.plan_split([dict(row("subject", 1_000, "C", "U", value=1))],
                             spec(folds=[one_fold()]), cluster_artifact=self.ledger())

    def test_a_ledger_used_to_close_the_gate_gets_its_own_refusal(self):
        with self.assertRaisesRegex(SPLIT.StatusGated, "ASSOCIATION EVIDENCE LEDGER"):
            SPLIT.require_status(SPLIT.STATUS_MODEL_ELIGIBLE, self.ledger())

    def test_a_ledger_is_recognised_by_declaration_or_by_shape(self):
        for artifact in ({"confidence_status": "uncalibrated_evidence_only"},
                         {"links": [], "evidence_hash_chain_sha256": "0" * 64}):
            with self.subTest(artifact=sorted(artifact)):
                self.assertTrue(SPLIT._looks_like_association_ledger(artifact))
                with self.assertRaises(SPLIT.SplitRefused):
                    SPLIT.assert_no_association_evidence({"nested": artifact})

    def test_a_real_b13b_ledger_is_recognised(self):
        b13b = _load("b13b_association", "b13b_association.py")
        coverage = {"first_slot": 1, "last_slot": 200, "source_population": "synthetic",
                    "left_truncated": False, "right_truncated": False, "complete": True,
                    "provenance_sha256": "p" * 10,
                    "decode_accounting": {
                        "transactions_required": 0, "transactions_with_body": 0,
                        "transactions_missing_body": 0, "transactions_missing_coordinate": 0,
                        "system_instructions_total": 0, "decoded_moving": 0,
                        "decoded_non_moving": 0, "undecodable": 0, "edges_emitted": 0,
                        "moving_self_transfer": 0, "moving_without_addresses": 0,
                        "unresolved": []}}
        ledger = b13b.build_association_ledger([], ["AAAa", "BBBb"], at(200), coverage)
        with self.assertRaisesRegex(SPLIT.SplitRefused, "do not assert common control"):
            SPLIT.assert_no_association_evidence({"grouping": ledger})

    def test_exact_identity_grouping_is_still_permitted(self):
        """The point of the gate is association evidence, not identity. Exact equality stays."""
        rows = SPLIT.ordered_rows([row("a", 1_000, "Shared", "U1", value=1),
                                   row("b", 1_100, "Shared", "U2", value=1)])
        self.assertEqual(len(SPLIT.identity_groups(rows)), 1)


class StatusGateTests(unittest.TestCase):
    """Funding-cluster leakage is an open gate, and only plumbing is attainable."""

    def test_only_research_plumbing_is_attainable(self):
        self.assertEqual(SPLIT.ATTAINABLE_STATUSES, (SPLIT.STATUS_RESEARCH_PLUMBING_ONLY,))
        self.assertTrue(SPLIT.require_status(SPLIT.STATUS_RESEARCH_PLUMBING_ONLY))

    def test_the_higher_statuses_are_refused(self):
        for status in (SPLIT.STATUS_PUBLICATION_GRADE, SPLIT.STATUS_MODEL_ELIGIBLE):
            with self.subTest(status=status):
                with self.assertRaisesRegex(SPLIT.StatusGated, "not attainable"):
                    SPLIT.require_status(status)

    def test_no_cluster_artifact_type_is_accepted(self):
        self.assertEqual(SPLIT.ACCEPTED_CLUSTER_ARTIFACT_TYPES, ())
        for artifact in ({}, {"type": "anything"}, {"clusters": [["a", "b"]]}):
            with self.subTest(artifact=artifact):
                with self.assertRaises(SPLIT.StatusGated):
                    SPLIT.require_status(SPLIT.STATUS_MODEL_ELIGIBLE, artifact)

    def test_the_refusal_names_what_the_gate_is_about(self):
        try:
            SPLIT.require_status(SPLIT.STATUS_MODEL_ELIGIBLE)
        except SPLIT.StatusGated as error:
            self.assertIn("without sharing an address", str(error))
            for requirement in ("calibrated", "preregistered", "point-in-time", "provenanced"):
                with self.subTest(requirement=requirement):
                    self.assertIn(requirement, str(error))

    def test_a_plan_may_not_ship_with_a_gated_status(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        plan["status"] = SPLIT.STATUS_MODEL_ELIGIBLE
        with self.assertRaises(SPLIT.StatusGated):
            SPLIT.assert_split_plan(plan, {}, {})

    def test_an_undeclared_status_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "is not one of"):
            SPLIT.require_status("nearly_ready")

    def test_a_gated_status_is_distinguishable_from_a_broken_plan(self):
        self.assertTrue(issubclass(SPLIT.StatusGated, SPLIT.SplitRefused))


class DeterminismTests(unittest.TestCase):
    """Insertion order is irrelevant, and the plan hash proves it."""

    def test_row_order_does_not_change_the_plan(self):
        rows = FIXTURES.build_fixture_corpus()
        forward = SPLIT.plan_split(rows, FIXTURES.build_spec())
        backward = SPLIT.plan_split(list(reversed(rows)), FIXTURES.build_spec())
        self.assertEqual(forward["plan_sha256"], backward["plan_sha256"])
        self.assertEqual(B10B.canonical_json(forward), B10B.canonical_json(backward))

    def test_a_duplicate_row_id_is_refused(self):
        subject = row("subject", 1_000, "C", "U", value=1)
        with self.assertRaisesRegex(SPLIT.SplitRefused, "two folds at once"):
            SPLIT.ordered_rows([subject, copy.deepcopy(subject)])

    def test_rows_must_be_a_sequence(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "must be a sequence"):
            SPLIT.ordered_rows(row("subject", 1_000, "C", "U", value=1))

    def test_changing_one_row_changes_the_plan_hash(self):
        base = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        other = SPLIT.plan_split([row("subject", 1_101, "C", "U", value=1)],
                                 spec(folds=[one_fold()]))
        self.assertNotEqual(base["plan_sha256"], other["plan_sha256"])

    def test_the_plan_hash_covers_everything_but_itself(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertEqual(plan["plan_sha256"], SPLIT.plan_hash(plan))

    def test_no_float_may_appear_in_a_plan(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        self.assertTrue(SPLIT.assert_no_float(plan))
        plan["purge_slots"] = 50.0
        with self.assertRaisesRegex(SPLIT.SplitRefused, "somebody computed"):
            SPLIT.assert_no_float(plan)

    def test_an_undeclared_plan_field_is_refused(self):
        plan = SPLIT.plan_split([row("subject", 1_100, "C", "U", value=1)],
                                spec(folds=[one_fold()]))
        plan["notes"] = "a note"
        with self.assertRaisesRegex(SPLIT.SplitRefused, "undeclared fields"):
            SPLIT.assert_split_plan(plan, {}, {})

    def test_an_undeclared_row_field_is_refused(self):
        with self.assertRaisesRegex(SPLIT.SplitRefused, "undeclared fields"):
            SPLIT.assert_row(dict(row("subject", 1_000, "C", "U", value=1), extra=1))

    def test_a_row_assigned_outside_its_segments_range_is_refused(self):
        subject = row("subject", 1_100, "C", "U", value=1)
        rows = SPLIT.ordered_rows([subject])
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        plan["folds"][0]["rows"][TRAIN] = []
        plan["folds"][0]["rows"][TEST] = ["subject"]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "outside that range"):
            SPLIT.assert_split_plan(plan, {r["row_id"]: r for r in rows},
                                    SPLIT.identity_groups(rows))

    def test_a_row_in_two_segments_of_one_fold_is_refused(self):
        subject = row("subject", 1_100, "C", "U", value=1)
        rows = SPLIT.ordered_rows([subject])
        plan = SPLIT.plan_split(rows, spec(folds=[one_fold()]))
        plan["folds"][0]["rows"][VALIDATION] = ["subject"]
        with self.assertRaisesRegex(SPLIT.SplitRefused, "two segments at once"):
            SPLIT.assert_split_plan(plan, {r["row_id"]: r for r in rows},
                                    SPLIT.identity_groups(rows))


class GateTests(unittest.TestCase):
    """The fixture report's own conditions, and the report's silence about performance."""

    def clean_report(self):
        return {"errors": [], "order_independent": True, "groups_never_span_segments": True,
                "purge_holds_for_every_training_row": True, "censored_rows_excluded": True,
                "artifact_sealed": True, "artifact_compatible_with_its_own_request": True,
                "association_ledger_refused_as_cluster_artifact": True,
                "gated_statuses_refused": {"publication_grade": True, "model_eligible": True},
                "status": SPLIT.STATUS_RESEARCH_PLUMBING_ONLY,
                "metrics_reported": False, "model_fitted": False, "b11a_touched": False,
                "exclusions_by_reason": {SPLIT.X01_LABEL_NOT_OBSERVED: 2,
                                         SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP: 1,
                                         SPLIT.X04_GROUP_SPANS_SEGMENTS: 2}}

    def test_a_clean_report_passes(self):
        self.assertEqual(FIXTURES.gate_failures(self.clean_report()), [])

    def test_every_gate_condition_can_fail(self):
        cases = {
            "integrity errors": {"errors": [{"error": "x"}]},
            "order_independent": {"order_independent": False},
            "groups_never_span_segments": {"groups_never_span_segments": False},
            "purge_holds_for_every_training_row": {"purge_holds_for_every_training_row": False},
            "censored_rows_excluded": {"censored_rows_excluded": False},
            "artifact_sealed": {"artifact_sealed": False},
            "artifact_compatible_with_its_own_request":
                {"artifact_compatible_with_its_own_request": False},
            "association_ledger_refused_as_cluster_artifact":
                {"association_ledger_refused_as_cluster_artifact": False},
            "gated status was granted": {"gated_statuses_refused": {"model_eligible": False}},
            "unattainable status": {"status": SPLIT.STATUS_MODEL_ELIGIBLE},
            "reports no metric": {"metrics_reported": True},
            "exercised the purge": {"exclusions_by_reason": {SPLIT.X01_LABEL_NOT_OBSERVED: 1,
                                                             SPLIT.X04_GROUP_SPANS_SEGMENTS: 1}},
            "spanning segments": {"exclusions_by_reason": {
                SPLIT.X01_LABEL_NOT_OBSERVED: 1, SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP: 1}},
            "censored label": {"exclusions_by_reason": {
                SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP: 1, SPLIT.X04_GROUP_SPANS_SEGMENTS: 1}},
        }
        for expected, override in cases.items():
            with self.subTest(condition=expected):
                report = self.clean_report()
                report.update(override)
                failures = FIXTURES.gate_failures(report)
                self.assertTrue(any(expected in failure for failure in failures),
                                f"{expected!r} not in {failures}")

    def test_the_shipped_corpus_passes_its_own_gate(self):
        report = FIXTURES.assert_clean()
        self.assertEqual(report["errors"], [])
        self.assertFalse(report["metrics_reported"])
        self.assertFalse(report["model_fitted"])
        self.assertFalse(report["b11a_touched"])

    def test_the_report_publishes_no_metric(self):
        """Nothing has been fitted, so any number here would be read as a performance figure for a
        model that does not exist.

        Scanned over FIELD NAMES rather than the raw JSON: the report carries hex digests, and a
        substring search over those matches "f1" and "auc" by coincidence — a check that fires on
        a hash is a check nobody will keep.
        """
        def names(value, found=None):
            found = [] if found is None else found
            if isinstance(value, dict):
                for key, child in value.items():
                    found.append(str(key).lower())
                    names(child, found)
            elif isinstance(value, list):
                for child in value:
                    names(child, found)
            return found

        report = FIXTURES.check()
        keys = names(report)
        for banned in ("accuracy", "precision", "recall", "auc", "f1", "sharpe", "pnl",
                       "profit", "return", "score", "metric_value", "performance"):
            with self.subTest(banned=banned):
                self.assertFalse([k for k in keys if banned in k],
                                 f"{banned!r} appears in a report field name")
        self.assertFalse(report["metrics_reported"])

    def test_the_corpus_exercises_every_seam_it_claims_to(self):
        report = FIXTURES.check()
        self.assertGreaterEqual(report["largest_group_size"], 3)
        for code in (SPLIT.X01_LABEL_NOT_OBSERVED, SPLIT.X02_PURGED_LABEL_WINDOW_OVERLAP,
                     SPLIT.X04_GROUP_SPANS_SEGMENTS):
            with self.subTest(code=code):
                self.assertGreater(report["exclusions_by_reason"][code], 0)


if __name__ == "__main__":
    unittest.main()
