"""B10c — the leakage-safe simulated outcome label materializer.

A label table is where leakage becomes invisible: the row that carries the answer sits beside the
row that carries the question, and a single field drifting across t0 contaminates everything
downstream without changing a single number's appearance. So most of what is tested here is the
boundary itself — the field partition, the signature that cannot receive a mark, the decision block
that must not move when the horizon does — rather than the arithmetic on either side of it.

The rest tests the three ways a label lies about absence: scoring a horizon the window never
reached, valuing a curve that stopped trading, and quietly conditioning the table on the curves that
happened to be tradable.
"""
import copy
import importlib.util
import inspect
import json
import math
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One module graph, as in the b10b suite: loading each by path would give two `PathRefused`
# classes and a test failure that is really an artefact of how the test loaded its subject.
CORPUS = _load("b10c_label_corpus", "b10c_label_corpus.py")
B10C = CORPUS.B10C
B10B = B10C.B10B
B10A = B10C.B10A
B10BD = CORPUS.B10BD
NATIVE = B10B.B9D.NATIVE_QUOTE_MINT

MINT = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CURVE = "CurveAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CREATOR = "CreatorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CREATE_USER = "CreatorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
T0_USER = "TraderBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5_000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
          "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
ORDER = {"side": B10A.BUY, "quote_lamports": 100_000_000}

LAUNCH_VQ, LAUNCH_VT = 30_000_000_000, 1_073_000_000_000_000
LAUNCH_RT = 793_100_000_000_000
WINDOW_END = 500_000

IDENTITY = {"bonding_curve": CURVE, "mint": MINT, "creator": CREATOR,
            "create_user": CREATE_USER, "t0_user": T0_USER}


def observation(slot, transaction_index=0, outer_index=0, inner_index=-1, *, mint=MINT,
                virtual_quote=LAUNCH_VQ, virtual_token=LAUNCH_VT, real_quote=5_000_000_000,
                real_token=LAUNCH_RT, complete=False, mayhem_mode=False, quote_mint=NATIVE,
                is_transaction_terminal=True):
    return {"slot": slot, "transaction_index": transaction_index, "outer_index": outer_index,
            "inner_index": inner_index, "mint": mint, "virtual_quote": virtual_quote,
            "virtual_token": virtual_token, "real_quote": real_quote, "real_token": real_token,
            "quote_mint": quote_mint, "mayhem_mode": mayhem_mode, "complete": complete,
            "is_transaction_terminal": is_transaction_terminal}


def t0_state(**overrides):
    base = observation(1_000, real_quote=1_000_000_000)
    base.update(overrides)
    return base


def preregistration(horizons=None, **overrides):
    document = {
        "preregistration_id": "test-fixture",
        "window_status": B10C.WINDOW_BURNED_DEVELOPMENT,
        "purpose": "unit fixture; produces no finding",
        "observation_window_end_slot": WINDOW_END,
        "horizons": horizons if horizons is not None else [
            {"name": "h_500", "kind": B10C.HORIZON_SLOT, "slots": 500}],
    }
    document.update(overrides)
    return document


def path_for(path, t0=None):
    return B10B.evaluate_position_path(
        t0 or t0_state(), path, SCHEDULE, POLICY, mint=MINT, order=ORDER)


def rows_for(path, horizons=None, t0=None, document=None):
    document = document or preregistration(horizons)
    validated, digest = B10C.assert_preregistration(document)
    result = path_for(path, t0)
    return B10C.materialize_decision(
        result, IDENTITY, validated, digest, "corpus-sha", t0 or t0_state(),
        ORDER, SCHEDULE, POLICY), result


class PreregistrationTests(unittest.TestCase):
    """No horizon may enter this module without a document naming who chose it and when."""

    def test_the_module_declares_no_default_horizon_anywhere(self):
        """A default horizon is a horizon chosen after seeing outcome counts, with nobody's name
        on it. The absence has to be checked, because adding one back is a one-line edit."""
        source = (ROOT / "scripts" / "b10c_outcome_labels.py").read_text()
        for forbidden in ("DEFAULT_HORIZON", "DEFAULT_HORIZONS", "horizons=("):
            self.assertNotIn(forbidden, source)
        with self.assertRaisesRegex(B10C.LabelRefused, "at least one horizon"):
            B10C.assert_preregistration(preregistration(horizons=[]))

    def test_an_unnamed_preregistration_is_refused(self):
        for identifier in (None, "", "   "):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(B10C.LabelRefused, "preregistration_id"):
                    B10C.assert_preregistration(
                        preregistration(preregistration_id=identifier))

    def test_only_a_burned_window_may_be_declared_today(self):
        for status in ("out_of_sample", "test", "validation", None):
            with self.subTest(status=status):
                with self.assertRaisesRegex(B10C.LabelRefused, "window_status"):
                    B10C.assert_preregistration(preregistration(window_status=status))
        self.assertEqual(B10C.ALLOWED_WINDOW_STATUS, ("burned_development",))

    def test_a_preregistration_without_a_purpose_is_refused(self):
        with self.assertRaisesRegex(B10C.LabelRefused, "purpose"):
            B10C.assert_preregistration(preregistration(purpose=" "))

    def test_censoring_without_a_stated_window_end_is_refused(self):
        """Right-censoring is a claim about window geometry. Made without a window end, it is not
        a claim at all."""
        for value in (None, 0, -1, "435536742"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(B10C.LabelRefused, "observation_window_end_slot"):
                    B10C.assert_preregistration(
                        preregistration(observation_window_end_slot=value))

    def test_a_value_selected_horizon_is_refused_by_name_with_its_reason(self):
        """A stop, a target, or "exit at the first fully executable moment" is an oracle exit: the
        label would embed a decision no strategy could have made at t0."""
        for kind in (B10B.RULE_NET_AT_OR_BELOW, B10B.RULE_NET_AT_OR_ABOVE,
                     B10B.RULE_FIRST_FULL_SIZE_EXIT):
            with self.subTest(kind=kind):
                with self.assertRaises(B10C.LabelRefused) as caught:
                    B10C.assert_horizon({"name": "x", "kind": kind, "lamports": 0})
                self.assertIn(kind, str(caught.exception))
                self.assertIn(B10C.REFUSED_HORIZON_KINDS[kind], str(caught.exception))

    def test_an_unknown_horizon_kind_is_refused(self):
        with self.assertRaisesRegex(B10C.LabelRefused, "is not one of"):
            B10C.assert_horizon({"name": "x", "kind": "when_it_feels_right"})

    def test_a_horizon_missing_its_parameter_is_refused_never_defaulted(self):
        with self.assertRaisesRegex(B10C.LabelRefused, "horizon slots"):
            B10C.assert_horizon({"name": "x", "kind": B10C.HORIZON_SLOT})
        with self.assertRaisesRegex(B10C.LabelRefused, "horizon count"):
            B10C.assert_horizon({"name": "x", "kind": B10C.HORIZON_OBSERVATION})

    def test_duplicate_horizon_names_are_refused(self):
        duplicate = [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 1},
                     {"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 2}]
        with self.assertRaisesRegex(B10C.LabelRefused, "appears twice"):
            B10C.assert_preregistration(preregistration(duplicate))

    def test_the_preregistration_hash_is_stamped_on_every_row_and_moves_with_the_document(self):
        base, _ = rows_for([observation(1_200)])
        other, _ = rows_for([observation(1_200)],
                            document=preregistration(purpose="a different purpose"))
        self.assertEqual({row["preregistration_sha256"] for row in base}, {base[0][
            "preregistration_sha256"]})
        self.assertNotEqual(base[0]["preregistration_sha256"],
                            other[0]["preregistration_sha256"])


class LeakageBoundaryTests(unittest.TestCase):
    """A label may read after t0. A feature may not. Both live in one row, so this is structural."""

    def test_the_field_partition_is_disjoint_and_exhaustive(self):
        self.assertEqual(set(B10C.DECISION_FIELDS) & set(B10C.OUTCOME_FIELDS), set())
        rows, _ = rows_for([observation(1_200)])
        self.assertTrue(B10C.assert_field_partition(rows[0]))
        self.assertEqual(set(rows[0]),
                         set(B10C.DECISION_FIELDS) | set(B10C.OUTCOME_FIELDS))

    def test_an_undeclared_field_is_refused_rather_than_carried(self):
        """Adding a field without saying which side of t0 it comes from is exactly how a label
        table acquires a leak that nobody can see afterwards."""
        rows, _ = rows_for([observation(1_200)])
        with self.assertRaisesRegex(B10C.LabelRefused, "undeclared fields"):
            B10C.assert_field_partition(dict(rows[0], peeked_at_the_future=1))
        missing = dict(rows[0])
        del missing["creator"]
        with self.assertRaisesRegex(B10C.LabelRefused, "missing declared fields"):
            B10C.assert_field_partition(missing)

    def test_build_decision_facts_has_no_parameter_a_mark_could_arrive_through(self):
        parameters = set(inspect.signature(B10C.build_decision_facts).parameters)
        for forbidden in ("path_result", "marks", "path", "horizon", "result", "observations",
                          "future"):
            self.assertNotIn(forbidden, parameters)

    def test_the_decision_block_does_not_move_when_the_horizon_does(self):
        """Horizons are post-t0 geometry. Anything on the decision side that varies with one was
        computed from information after t0, whatever it is called."""
        horizons = [{"name": "a", "kind": B10C.HORIZON_SLOT, "slots": 100},
                    {"name": "b", "kind": B10C.HORIZON_SLOT, "slots": 100_000},
                    {"name": "c", "kind": B10C.HORIZON_OBSERVATION, "count": 1},
                    {"name": "d", "kind": B10C.HORIZON_ADMINISTRATIVE}]
        rows, _ = rows_for([observation(1_200), observation(1_400)], horizons)
        self.assertEqual(len(rows), 4)
        blocks = {B10B.canonical_json(B10C.decision_block(row)) for row in rows}
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len({row["row_sha256"] for row in rows}), 4,
                         "the outcome halves must still differ")

    def test_a_decision_block_that_varies_across_horizons_is_caught(self):
        rows, _ = rows_for([observation(1_200)],
                           [{"name": "a", "kind": B10C.HORIZON_SLOT, "slots": 100},
                            {"name": "b", "kind": B10C.HORIZON_SLOT, "slots": 200}])
        rows[1]["t0_real_quote"] += 1
        with self.assertRaisesRegex(B10C.LabelRefused, "varies across horizons"):
            B10C._assert_decision_block_invariant(rows)

    def test_the_decision_block_is_byte_identical_whether_the_token_moons_or_collapses(self):
        moon, _ = rows_for([observation(1_200, real_quote=80_000_000_000)])
        collapse, _ = rows_for([observation(1_200, real_quote=1)])
        self.assertEqual(B10B.canonical_json(B10C.decision_block(moon[0])),
                         B10B.canonical_json(B10C.decision_block(collapse[0])))
        self.assertNotEqual(moon[0]["row_sha256"], collapse[0]["row_sha256"])

    def test_no_mark_is_reachable_from_the_decision_half_of_a_row(self):
        rows, result = rows_for([observation(1_200), observation(1_400)])
        self.assertTrue(B10B.assert_no_future_reachable(
            B10C.decision_block(rows[0]), result["marks"]))
        leaked = dict(B10C.decision_block(rows[0]))
        leaked["creator"] = result["marks"][0]
        with self.assertRaisesRegex(B10B.PathRefused, "reachable from the entry feature view"):
            B10B.assert_no_future_reachable(leaked, result["marks"])

    def test_the_merge_seam_itself_refuses_a_decision_block_that_reaches_a_mark(self):
        """Not `assert_no_future_reachable` called directly — the real entry point. A check that
        only fires when a test invokes it is a check the production path does not have."""
        document, digest = B10C.assert_preregistration(preregistration())
        result = path_for([observation(1_200), observation(1_400)])
        facts = B10C.build_decision_facts(
            t0_state(), IDENTITY, ORDER, SCHEDULE, POLICY, result["entry"], document, digest,
            "corpus")
        outcome = B10C.build_outcome_facts(
            result, document["horizons"][0], WINDOW_END, result["entry"])
        self.assertTrue(B10C.materialize_row(facts, outcome, result))
        leaked = dict(facts, creator=result["marks"][1])
        with self.assertRaisesRegex(B10B.PathRefused, "reachable from the entry feature view"):
            B10C.materialize_row(leaked, outcome, result)

    def test_the_merge_seam_itself_refuses_an_undeclared_field(self):
        document, digest = B10C.assert_preregistration(preregistration())
        result = path_for([observation(1_200)])
        facts = B10C.build_decision_facts(
            t0_state(), IDENTITY, ORDER, SCHEDULE, POLICY, result["entry"], document, digest,
            "corpus")
        outcome = B10C.build_outcome_facts(
            result, document["horizons"][0], WINDOW_END, result["entry"])
        with self.assertRaisesRegex(B10C.LabelRefused, "undeclared fields"):
            B10C.materialize_row(dict(facts, peeked=1), outcome, result)

    def test_a_decision_states_either_an_entry_or_why_there_was_none(self):
        document, digest = B10C.assert_preregistration(preregistration())
        with self.assertRaisesRegex(B10C.LabelRefused, "exactly one"):
            B10C.build_decision_facts(
                t0_state(), IDENTITY, None, SCHEDULE, POLICY, None, document, digest, "corpus")

    def test_grouping_identities_are_required_because_r5_requires_the_split(self):
        document, digest = B10C.assert_preregistration(preregistration())
        for field in ("creator", "create_user"):
            with self.subTest(field=field):
                identity = dict(IDENTITY, **{field: None})
                with self.assertRaisesRegex(B10C.LabelRefused, field):
                    B10C.build_decision_facts(
                        t0_state(), identity, None, SCHEDULE, POLICY, None, document, digest,
                        "corpus", no_decision_reason="no_later_observation")

    def test_the_split_key_unions_creator_and_users_deterministically(self):
        rows, _ = rows_for([observation(1_200)])
        self.assertEqual(rows[0]["split_key_creator"], CREATOR)
        self.assertEqual(rows[0]["split_key_creator_union_t0_user"],
                         "|".join(sorted({CREATOR, CREATE_USER, T0_USER})))


class HorizonSemanticsTests(unittest.TestCase):
    """R1 fixes the label window at `(t0, t0+H]`. That is a different rule from `the next trade`."""

    def test_a_slot_horizon_labels_the_state_in_force_not_the_next_trade_after_it(self):
        """The last observation at or before the target, never the first one after. Taking the
        first one after would label "the value whenever this token next traded", which moves with
        how quiet the token happened to go rather than with the market."""
        path = [observation(1_100, real_quote=9_000_000_000),
                observation(1_400, real_quote=8_000_000_000),
                observation(9_000, real_quote=7_000_000_000)]
        rows, _ = rows_for(path, [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_MARKED)
        self.assertEqual(rows[0]["mark_slot"], 1_400)
        self.assertEqual(rows[0]["horizon_target_slot"], 1_500)

    def test_a_slot_horizon_beyond_the_recorded_window_is_right_censored(self):
        rows, _ = rows_for([observation(1_200)],
                           [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": WINDOW_END}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_RIGHT_CENSORED)
        self.assertIn("beyond the observation window end", rows[0]["censoring_reason"])

    def test_a_window_with_no_observation_is_not_censoring_and_is_not_valued(self):
        """Distinct from right-censoring on purpose: the window covers the horizon, there is simply
        nothing inside it. The only state available is t0's own, which our entry has already
        changed, so pricing against it would price our own impact away."""
        rows, _ = rows_for([observation(9_000)],
                           [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 100}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_NO_OBSERVED_STATE)
        self.assertNotEqual(rows[0]["outcome_status"], B10C.OUTCOME_RIGHT_CENSORED)
        self.assertIsNone(rows[0]["net_return_numerator"])
        self.assertIn("price our own impact away", rows[0]["censoring_reason"])

    def test_a_curve_completing_before_the_horizon_is_structurally_unavailable(self):
        path = [observation(1_100, real_quote=9_000_000_000),
                observation(1_200, complete=True)]
        rows, _ = rows_for(path, [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 5_000}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_STRUCTURAL_UNAVAILABLE)
        self.assertIn("no exit venue after it", rows[0]["censoring_reason"])
        self.assertIsNone(rows[0]["net_return_numerator"])

    def test_a_curve_completing_after_the_horizon_still_labels_the_earlier_state(self):
        path = [observation(1_100, real_quote=9_000_000_000),
                observation(9_000, complete=True)]
        rows, _ = rows_for(path, [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_MARKED)
        self.assertEqual(rows[0]["mark_slot"], 1_100)

    def test_an_observation_horizon_longer_than_the_path_is_right_censored(self):
        rows, _ = rows_for([observation(1_100), observation(1_200)],
                           [{"name": "h", "kind": B10C.HORIZON_OBSERVATION, "count": 5}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_RIGHT_CENSORED)
        self.assertIn("fewer than the 5", rows[0]["censoring_reason"])

    def test_an_observation_horizon_cut_short_by_completion_is_unavailable_not_censored(self):
        rows, _ = rows_for([observation(1_100), observation(1_200, complete=True)],
                           [{"name": "h", "kind": B10C.HORIZON_OBSERVATION, "count": 5}])
        self.assertEqual(rows[0]["outcome_status"], B10C.OUTCOME_STRUCTURAL_UNAVAILABLE)

    def test_the_administrative_horizon_is_flagged_as_such(self):
        rows, _ = rows_for([observation(1_100), observation(1_200)],
                           [{"name": "end", "kind": B10C.HORIZON_ADMINISTRATIVE}])
        self.assertTrue(rows[0]["horizon_is_administrative"])
        self.assertEqual(rows[0]["mark_slot"], 1_200)
        self.assertFalse(
            rows_for([observation(1_100)],
                     [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500}])[0][0][
                         "horizon_is_administrative"])


class AbsenceIsNeverANumberTests(unittest.TestCase):
    """R4: a member that cannot reach the horizon is censored, never dropped and never negative."""

    def cases(self):
        return {
            B10C.OUTCOME_RIGHT_CENSORED: rows_for(
                [observation(1_200)],
                [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": WINDOW_END}])[0][0],
            B10C.OUTCOME_STRUCTURAL_UNAVAILABLE: rows_for(
                [observation(1_200, complete=True)],
                [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 5_000}])[0][0],
            B10C.OUTCOME_NO_OBSERVED_STATE: rows_for(
                [observation(9_000)],
                [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 100}])[0][0],
        }

    def test_every_absent_outcome_carries_null_and_never_zero_or_minus_one(self):
        for status, row in self.cases().items():
            with self.subTest(status=status):
                self.assertEqual(row["outcome_status"], status)
                for field in ("net_return_numerator", "net_return_denominator",
                              "realizable_net_lamports", "gross_exit_lamports",
                              "capital_denominator_lamports", "liquidity_state",
                              "max_drawdown_lamports"):
                    self.assertIsNone(row[field], field)
                self.assertTrue(row["censoring_reason"])
                self.assertTrue(B10C.assert_row_arithmetic(row))

    def test_a_zero_slipped_into_an_absent_outcome_is_caught(self):
        for status, row in self.cases().items():
            with self.subTest(status=status):
                tampered = dict(row, net_return_numerator=0)
                tampered["row_sha256"] = B10C._sha256_of(
                    {k: v for k, v in tampered.items() if k != "row_sha256"})
                with self.assertRaisesRegex(B10C.LabelRefused, "never zero and never minus one"):
                    B10C.assert_row_arithmetic(tampered)

    def test_an_absent_outcome_without_a_reason_is_caught(self):
        row = dict(self.cases()[B10C.OUTCOME_RIGHT_CENSORED], censoring_reason=None)
        row["row_sha256"] = B10C._sha256_of(
            {k: v for k, v in row.items() if k != "row_sha256"})
        with self.assertRaisesRegex(B10C.LabelRefused, "states no reason"):
            B10C.assert_row_arithmetic(row)


class NoDecisionTests(unittest.TestCase):
    """Every curve produces rows, including the ones we would not have traded."""

    def rows(self, reason="no_later_observation", horizons=None):
        document, digest = B10C.assert_preregistration(preregistration(horizons))
        return B10C.materialize_no_decision(
            IDENTITY, document, digest, "corpus-sha", t0_state(), SCHEDULE, POLICY, reason)

    def test_a_curve_we_would_not_have_entered_still_produces_one_row_per_horizon(self):
        """Conditioning the table on evaluability would select on tradability, and tradability is
        correlated with exactly the outcomes a later model would be asked to predict."""
        horizons = [{"name": "a", "kind": B10C.HORIZON_SLOT, "slots": 100},
                    {"name": "b", "kind": B10C.HORIZON_ADMINISTRATIVE}]
        rows = self.rows(horizons=horizons)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["outcome_status"], B10C.OUTCOME_NO_DECISION)
            self.assertIsNone(row["net_return_numerator"])
            self.assertIsNone(row["entry_outlay_lamports"])
            self.assertEqual(row["no_decision_reason"], "no_later_observation")
            self.assertTrue(B10C.assert_row_arithmetic(row))
            self.assertTrue(B10C.assert_field_partition(row))

    def test_the_reason_must_be_one_of_the_declared_ones(self):
        with self.assertRaisesRegex(B10C.LabelRefused, "no_decision_reason"):
            self.rows(reason="it_looked_unpromising")

    def test_every_declared_reason_is_a_property_of_t0_or_the_corpus(self):
        """None of them may be an outcome — a row that exists because of what later happened is a
        selection, not a coverage category."""
        for reason in B10C.NO_DECISION_REASONS:
            with self.subTest(reason=reason):
                self.assertEqual(self.rows(reason=reason)[0]["no_decision_reason"], reason)

    def test_a_no_decision_row_still_carries_its_grouping_identities(self):
        row = self.rows()[0]
        self.assertEqual(row["creator"], CREATOR)
        self.assertEqual(row["split_key_creator_union_t0_user"],
                         "|".join(sorted({CREATOR, CREATE_USER, T0_USER})))


class ExactArithmeticTests(unittest.TestCase):

    def test_the_return_is_an_exact_reduced_rational_and_never_a_float(self):
        rows, _ = rows_for([observation(1_200, real_quote=10 ** 15)])
        row = rows[0]
        self.assertIsInstance(row["net_return_numerator"], int)
        self.assertIsInstance(row["net_return_denominator"], int)
        self.assertEqual(
            math.gcd(abs(row["net_return_numerator"]), row["net_return_denominator"]), 1)

        def no_float(node, where):
            if isinstance(node, float):
                self.fail(f"a float reached the row at {where}: {node!r}")
            if isinstance(node, dict):
                for key, value in node.items():
                    no_float(value, f"{where}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    no_float(value, f"{where}[{index}]")

        no_float(json.loads(B10B.canonical_json(row)), "row")

    def test_the_return_follows_executable_return_section_1_exactly(self):
        """`R = (Q_out - Q_in - C) / (Q_in + C)` with C every cost, entry and exit."""
        rows, result = rows_for([observation(1_200, real_quote=10 ** 15)])
        row, entry = rows[0], result["entry"]
        cost = (entry["curve_fees"]["charged_total"] + entry["execution_costs"]["total"]
                + row["exit_cost_total_lamports"])
        numerator = row["gross_exit_lamports"] - ORDER["quote_lamports"] - cost
        denominator = ORDER["quote_lamports"] + cost
        self.assertEqual(row["capital_denominator_lamports"], denominator)
        divisor = math.gcd(abs(numerator), denominator)
        self.assertEqual((row["net_return_numerator"], row["net_return_denominator"]),
                         (numerator // divisor, denominator // divisor))

    def test_a_negative_return_is_reported_exactly_and_never_clamped(self):
        rows, _ = rows_for([observation(1_200, real_quote=50_000)])
        row = rows[0]
        self.assertLess(row["net_return_numerator"], 0)
        self.assertGreater(row["net_return_denominator"], 0)
        self.assertTrue(B10C.assert_row_arithmetic(row))

    def test_a_double_counted_cost_is_caught_by_the_second_route(self):
        rows, result = rows_for([observation(1_200, real_quote=10 ** 15)])
        tampered = dict(rows[0])
        tampered["exit_execution_cost_lamports"] += 1
        tampered["exit_cost_total_lamports"] += 1
        tampered["row_sha256"] = B10C._sha256_of(
            {k: v for k, v in tampered.items() if k != "row_sha256"})
        with self.assertRaisesRegex(B10C.LabelRefused, "realizable net is not gross minus"):
            B10C.assert_row_arithmetic(tampered, result)

    def test_a_tampered_row_hash_is_caught(self):
        rows, _ = rows_for([observation(1_200)])
        with self.assertRaisesRegex(B10C.LabelRefused, "row_sha256 does not match"):
            B10C.assert_row_arithmetic(dict(rows[0], gross_exit_lamports=1))

    def test_one_lamport_anywhere_moves_the_row_hash(self):
        base, _ = rows_for([observation(1_200, real_quote=50_000_000)])
        moved, _ = rows_for([observation(1_200, real_quote=50_000_001)])
        self.assertNotEqual(base[0]["row_sha256"], moved[0]["row_sha256"])

    def test_two_runs_of_the_same_inputs_produce_the_same_rows(self):
        first, _ = rows_for([observation(1_200), observation(1_400)])
        second, _ = rows_for([observation(1_200), observation(1_400)])
        self.assertEqual(B10C.rows_hash(first), B10C.rows_hash(second))
        self.assertEqual(B10B.canonical_json(first), B10B.canonical_json(second))


class DrawdownToHorizonTests(unittest.TestCase):
    """R1 applied inside a derived statistic: a label at H must not see the path past H."""

    def test_the_drawdown_stops_at_the_horizon_rather_than_running_to_the_window_end(self):
        path = [observation(1_100, real_quote=10 ** 15),
                observation(1_200, real_quote=60_000_000),
                observation(9_000, real_quote=50_000)]
        rows, result = rows_for(path, [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500},
                                       {"name": "end", "kind": B10C.HORIZON_ADMINISTRATIVE}])
        early, late = rows[0], rows[1]
        self.assertEqual(early["mark_slot"], 1_200)
        self.assertEqual(late["mark_slot"], 9_000)
        self.assertGreater(early["max_drawdown_lamports"], 0)
        self.assertLess(early["max_drawdown_lamports"], late["max_drawdown_lamports"])
        self.assertEqual(late["max_drawdown_lamports"],
                         result["drawdown"]["max_drawdown_lamports"])
        self.assertEqual(early["observations_evaluated_to_horizon"], 2)

    def test_a_drawdown_taken_from_the_whole_path_is_caught_at_an_early_horizon(self):
        path = [observation(1_100, real_quote=10 ** 15),
                observation(1_200, real_quote=60_000_000),
                observation(9_000, real_quote=50_000)]
        rows, result = rows_for(path, [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500}])
        tampered = dict(rows[0],
                        max_drawdown_lamports=result["drawdown"]["max_drawdown_lamports"])
        tampered["row_sha256"] = B10C._sha256_of(
            {k: v for k, v in tampered.items() if k != "row_sha256"})
        with self.assertRaisesRegex(B10C.LabelRefused, "max_drawdown_lamports"):
            B10C.assert_row_arithmetic(tampered, result)

    def test_the_ratio_is_an_exact_pair_and_is_withheld_when_the_peak_was_never_positive(self):
        rising = B10C.drawdown_to(
            path_for([observation(1_100, real_quote=10 ** 15),
                      observation(1_200, real_quote=60_000_000)]), 1)
        self.assertIsInstance(rising["max_drawdown_ratio_numerator"], int)
        self.assertEqual(math.gcd(rising["max_drawdown_ratio_numerator"],
                                  rising["max_drawdown_ratio_denominator"]), 1)
        never = B10C.drawdown_to(
            path_for([observation(1_100, real_quote=50_000),
                      observation(1_200, real_quote=40_000)]), 1)
        self.assertIsNone(never["max_drawdown_ratio_numerator"])
        self.assertIsNone(never["max_drawdown_ratio_denominator"])

    def test_a_label_may_not_cite_a_state_after_its_own_horizon(self):
        rows, result = rows_for([observation(1_100, real_quote=10 ** 15),
                                 observation(9_000, real_quote=900_000_000)],
                                [{"name": "h", "kind": B10C.HORIZON_SLOT, "slots": 500}])
        tampered = dict(rows[0], mark_slot=9_000, mark_index=1)
        tampered["row_sha256"] = B10C._sha256_of(
            {k: v for k, v in tampered.items() if k != "row_sha256"})
        with self.assertRaises(B10C.LabelRefused):
            B10C.assert_row_arithmetic(tampered, result)


class ContractTests(unittest.TestCase):

    def test_the_label_kind_is_distinct_from_the_path_record_label(self):
        rows, _ = rows_for([observation(1_200)])
        self.assertEqual(rows[0]["label_kind"], "SIMULATED_OBSERVED_PATH_LABEL")
        self.assertNotEqual(rows[0]["label_kind"], B10B.OUTCOME_SIMULATED_OBSERVED_PATH)
        self.assertEqual(rows[0]["calibration"], "uncalibrated")

    def test_every_row_carries_the_burned_window_status(self):
        rows, _ = rows_for([observation(1_200)])
        self.assertEqual(rows[0]["window_status"], B10C.WINDOW_BURNED_DEVELOPMENT)

    def test_every_row_carries_the_hashes_that_identify_what_produced_it(self):
        rows, result = rows_for([observation(1_200)])
        row = rows[0]
        self.assertEqual(row["path_record_sha256"], B10B.record_hash(result))
        self.assertEqual(row["dataset_content_sha256"], "corpus-sha")
        self.assertEqual(row["fee_schedule_sha256"], B10C._sha256_of(SCHEDULE))
        self.assertEqual(row["cost_policy_sha256"], B10C._sha256_of(POLICY))
        self.assertEqual(row["decision_sha256"], rows[0]["decision_sha256"])

    def test_the_materializer_does_not_mutate_its_inputs(self):
        document = preregistration()
        identity, t0 = dict(IDENTITY), t0_state()
        order, schedule, policy = dict(ORDER), dict(SCHEDULE), dict(POLICY)
        before = copy.deepcopy((document, identity, t0, order, schedule, policy))
        validated, digest = B10C.assert_preregistration(document)
        B10C.materialize_decision(
            path_for([observation(1_200)], t0), identity, validated, digest, "corpus",
            t0, order, schedule, policy)
        self.assertEqual(before, (document, identity, t0, order, schedule, policy))

    def test_no_profitability_class_or_success_field_exists_in_the_schema(self):
        """The row is allowed to carry a value. It is not allowed to carry a verdict."""
        # Token-wise, not substring-wise: `window_status` contains "win" and would make a
        # substring check pass or fail for reasons that have nothing to do with a verdict.
        tokens = {token for field in B10C.DECISION_FIELDS + B10C.OUTCOME_FIELDS
                  for token in field.split("_")}
        for forbidden in ("success", "successful", "profitable", "profit", "win", "loss",
                          "rug", "dump", "class", "good", "bad", "hit", "verdict"):
            self.assertNotIn(forbidden, tokens)


class CorpusTests(unittest.TestCase):
    """The runner: coverage preserved, every category represented, nothing conditioned away."""

    def derived(self, observations):
        database = sqlite3.connect(":memory:")
        database.executescript(B10BD.SCHEMA)
        database.executemany(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", observations)
        for curve in sorted({row[0] for row in observations}):
            B10BD._insert_curve(database, curve, None)
        return database

    def row(self, curve, slot, transaction_index, outer_index, inner_index, kind, mint=MINT,
            real_quote=5_000_000_000, quote_mint=NATIVE, terminal=1):
        return (curve, slot, transaction_index, outer_index, inner_index, mint, kind,
                LAUNCH_VQ, LAUNCH_VT, real_quote, LAUNCH_RT, quote_mint, 0, 0, terminal)

    def identities(self, curves):
        return {curve: {"bonding_curve": curve, "mint": MINT, "creator": CREATOR,
                        "create_user": CREATE_USER, "t0_user": T0_USER} for curve in curves}

    def test_every_curve_produces_exactly_one_row_per_horizon(self):
        rows = [self.row("A", 1_000, 0, 0, -1, "CreateEvent"),
                self.row("A", 1_100, 0, 0, -1, "TradeEvent"),
                self.row("B", 1_000, 1, 0, -1, "CreateEvent"),
                self.row("C", 1_000, 2, 0, -1, "CreateEvent", quote_mint="OtherMint111"),
                self.row("C", 1_100, 2, 1, -1, "TradeEvent", quote_mint="OtherMint111")]
        horizons = [{"name": "a", "kind": B10C.HORIZON_SLOT, "slots": 500},
                    {"name": "b", "kind": B10C.HORIZON_ADMINISTRATIVE}]
        labels, report = CORPUS.materialize(
            self.derived(rows), self.identities("ABC"), preregistration(horizons), WINDOW_END)
        self.assertEqual(report["rows"]["total"], 6)
        self.assertEqual(report["rows"]["expected"], 6)
        self.assertTrue(report["referential_integrity"]["rows_per_curve_exact"])
        self.assertEqual(report["arithmetic"]["errors"], [])
        self.assertEqual(report["curves"], {"total": 3, "with_decision": 1, "no_decision": 2})

    def test_out_of_regime_and_no_later_observation_survive_as_rows(self):
        rows = [self.row("B", 1_000, 1, 0, -1, "CreateEvent"),
                self.row("C", 1_000, 2, 0, -1, "CreateEvent", quote_mint="OtherMint111")]
        _, report = CORPUS.materialize(
            self.derived(rows), self.identities("BC"), preregistration(), WINDOW_END)
        self.assertEqual(report["rows"]["by_no_decision_reason"],
                         {"no_later_observation": 1, "out_of_regime_non_sol_quote": 1})

    def test_the_runner_reports_that_it_did_not_compute_returns(self):
        rows = [self.row("A", 1_000, 0, 0, -1, "CreateEvent"),
                self.row("A", 1_100, 0, 0, -1, "TradeEvent")]
        _, report = CORPUS.materialize(
            self.derived(rows), self.identities("A"), preregistration(), WINDOW_END)
        self.assertIn("NOT COMPUTED", report["returns"])
        self.assertIn("burned", report["returns"])

    def test_an_identity_row_cannot_be_built_from_a_create_after_t0(self):
        """The check and the row are one function on purpose: a separate assertion beside the row
        construction is a line a later edit can drop while everything still runs."""
        create = observation(1_000, outer_index=2)
        t0 = observation(1_000, outer_index=4)
        fields = {"creator": CREATOR, "user": CREATE_USER}
        row = CORPUS.identity_row("A", dict(create, kind="CreateEvent"),
                                  dict(t0, kind="TradeEvent"), fields, T0_USER)
        self.assertEqual(row[2], CREATOR)
        with self.assertRaisesRegex(B10C.LabelRefused, "CreateEvent is after t0"):
            CORPUS.identity_row("A", dict(t0, kind="CreateEvent"),
                                dict(create, kind="TradeEvent"), fields, T0_USER)

    def test_censoring_against_an_uncollected_window_is_refused_by_the_runner_itself(self):
        rows = [self.row("A", 1_000, 0, 0, -1, "CreateEvent"),
                self.row("A", 1_100, 0, 0, -1, "TradeEvent")]
        with self.assertRaisesRegex(B10C.LabelRefused, "never collected|uncollected window"):
            CORPUS.materialize(self.derived(rows), self.identities("A"), preregistration(),
                               WINDOW_END + 1)

    def test_a_missing_identity_is_refused_rather_than_filled_in(self):
        rows = [self.row("A", 1_000, 0, 0, -1, "CreateEvent"),
                self.row("A", 1_100, 0, 0, -1, "TradeEvent")]
        with self.assertRaisesRegex(B10C.LabelRefused, "no t0 identity"):
            CORPUS.materialize(self.derived(rows), {}, preregistration(), WINDOW_END)

    def test_t0_selection_is_shared_with_b10b_rather_than_reimplemented(self):
        """Two modules choosing t0 by their own rules would silently label a different decision
        than the one the path priced."""
        states = [{"is_transaction_terminal": False}, {"is_transaction_terminal": True}]
        self.assertEqual(B10BD.select_t0(states), 1)
        self.assertIsNone(B10BD.select_t0([{"is_transaction_terminal": False}]))
        source = (ROOT / "scripts" / "b10c_label_corpus.py").read_text()
        self.assertIn("B10BD.select_t0(states)", source)
        self.assertNotIn('if state["is_transaction_terminal"]', source)


class RealCorpusTests(unittest.TestCase):
    """Against the built artifacts when present. Skipped rather than faked when not."""

    CORPUS_PATH = ROOT / "research" / "b10b_observed_paths.sqlite"
    IDENTITY_PATH = ROOT / "research" / "b10c_t0_identity.sqlite"
    PREREGISTRATION = ROOT / "research" / "B10C_PREREGISTRATION_PLUMBING.json"

    def setUp(self):
        if not (self.CORPUS_PATH.exists() and self.IDENTITY_PATH.exists()):
            self.skipTest("derived artifacts not built")
        self.identity = sqlite3.connect(f"file:{self.IDENTITY_PATH}?mode=ro", uri=True)

    def tearDown(self):
        self.identity.close()

    def test_the_identity_table_covers_every_curve_and_hashes_itself(self):
        metadata = CORPUS.identity_metadata(self.identity)
        self.assertEqual(metadata["curves"], "1136")
        self.assertEqual(metadata["content_sha256"], CORPUS.identity_hash(self.identity))
        self.assertEqual(metadata["observation_window_end_slot"], "435536742")

    def test_the_shipped_preregistration_validates_and_declares_a_burned_window(self):
        document = json.loads(self.PREREGISTRATION.read_text())
        validated, digest = B10C.assert_preregistration(document)
        self.assertEqual(validated["window_status"], B10C.WINDOW_BURNED_DEVELOPMENT)
        self.assertEqual(len(digest), 64)
        self.assertEqual(document["observation_window_end_slot"],
                         int(CORPUS.identity_metadata(self.identity)[
                             "observation_window_end_slot"]))
        self.assertIn("NOT A RESEARCH PREREGISTRATION", document["purpose"])

    def test_every_create_event_in_the_corpus_is_inside_the_burned_b8b_window(self):
        """This is why `burned_development` is the only status the module will accept."""
        corpus = sqlite3.connect(f"file:{self.CORPUS_PATH}?mode=ro", uri=True)
        try:
            outside = corpus.execute(
                "SELECT COUNT(*) FROM curve WHERE create_slot < 433894233 "
                "OR create_slot > 434097833").fetchone()[0]
        finally:
            corpus.close()
        self.assertEqual(outside, 0)


if __name__ == "__main__":
    unittest.main()
