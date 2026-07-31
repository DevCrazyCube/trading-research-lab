"""B9e cohort reserve-coverage gate.

The gate exists because a broken chain produces MISSING rows rather than inconsistent ones, so the
survivors pass every structural gate. These tests are therefore mostly about population arithmetic
and about refusing to run unratified, not about row validity.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9e_reserve_coverage", ROOT / "scripts" / "b9e_reserve_coverage.py")
B9E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9E)
B9D = B9E.B9D

RESERVE_FIELDS = ("virtual_quote", "virtual_token", "real_quote", "real_token")


class CoverageFixture(unittest.TestCase):
    """A synthetic artifact whose cohort is patched, so population arithmetic is exact."""

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "coverage.sqlite"
        self.database = B9D.connect(str(self.path))
        B9D.schema(self.database)
        self.addCleanup(self.database.close)
        self.cohort = {}
        saved = B9D.tradable_cohort_identity
        B9D.tradable_cohort_identity = lambda *a, **k: self.cohort
        self.addCleanup(lambda: setattr(B9D, "tradable_cohort_identity", saved))
        self.next_index = 0

    def set_cohort(self, *curves):
        self.cohort = {f"mint-{curve}": curve for curve in curves}

    def coordinates(self):
        self.next_index += 1
        return (700, self.next_index, 0, -1)

    def add_observation(self, curve, anchor=False, before=(1, 2, 3, 4), after=(5, 6, 7, 8)):
        slot, index, outer, inner = self.coordinates()
        before = (None,) * 4 if anchor else before
        self.database.execute(
            "INSERT INTO reserve_observation (slot,transaction_index,outer_index,inner_index,"
            "bonding_curve," + ",".join(f + "_before" for f in RESERVE_FIELDS) + "," +
            ",".join(f + "_after" for f in RESERVE_FIELDS) + ",evidence) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (slot, index, outer, inner, curve) + before + after + ("{}",))

    def add_chain_failure(self, curve, reason, context=None):
        slot, index, outer, inner = self.coordinates()
        context = {"bonding_curve": curve} if context is None else context
        self.database.execute(
            "INSERT INTO classification_failure (signature,slot,transaction_index,outer_index,"
            "inner_index,program_id,discriminator,reason,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"sig-{index}", slot, index, outer, inner, B9D.PUMP_PROGRAM, "00" * 8,
             B9E.RESERVE_CHAIN_PREFIX + reason, json.dumps(context)))

    def counts(self):
        return B9E.cohort_reserve_coverage(self.database)["counts"]


class ReasonVocabularyTests(unittest.TestCase):
    """The constants must track the decoder that produces them.

    B9e reads B9d's own prose out of `classification_failure.reason`. If a rewording there stopped
    matching here, broken curves would silently classify as `anchored_complete` -- the gate would
    keep passing while measuring exactly the wrong population. So every constant is generated
    through the real function rather than copied.
    """

    CREATE = {"virtual_quote_reserves": 30_000, "virtual_token_reserves": 1_000_000,
              "real_token_reserves": 800_000}

    def trade(self, before, quote, token, is_buy=True):
        direction = 1 if is_buy else -1
        return {"virtual_quote_reserves": before["virtual_quote_reserves"] + direction * quote,
                "virtual_token_reserves": before["virtual_token_reserves"] - direction * token,
                "real_quote_reserves": before["real_quote_reserves"] + direction * quote,
                "real_token_reserves": before["real_token_reserves"] - direction * token,
                "quote_amount": quote, "token_amount": token, "is_buy": is_buy}

    def test_the_left_truncation_reason_still_matches(self):
        launch = B9D.curve_state_from_create(self.CREATE)
        _, _, reason = B9D.advance_curve_chain(
            {}, "mint", "TradeEvent", self.trade(launch, 100, 250))
        self.assertTrue(reason.startswith(B9E.LEFT_TRUNCATED_REASON), reason)

    def test_every_break_reason_still_matches(self):
        chains = {}
        B9D.advance_curve_chain(chains, "mint", "CreateEvent", self.CREATE)
        _, _, duplicate = B9D.advance_curve_chain(chains, "mint", "CreateEvent", self.CREATE)

        fresh = {}
        launch = B9D.curve_state_from_create(self.CREATE)
        B9D.advance_curve_chain(fresh, "mint", "CreateEvent", self.CREATE)
        wrong = self.trade(dict(launch, real_token_reserves=launch["real_token_reserves"] - 1),
                           100, 250)
        _, _, mismatch = B9D.advance_curve_chain(fresh, "mint", "TradeEvent", wrong)
        _, _, unrepairable = B9D.advance_curve_chain(fresh, "mint", "TradeEvent", wrong)

        produced = [duplicate, mismatch, unrepairable]
        for reason in produced:
            with self.subTest(reason=reason[:48]):
                self.assertTrue(reason.startswith(B9E.BREAK_REASONS), reason)
        # And every declared constant is actually produced by something, so the tuple cannot
        # accumulate dead entries that quietly stop matching.
        for constant in B9E.BREAK_REASONS:
            with self.subTest(constant=constant[:48]):
                self.assertTrue(any(reason.startswith(constant) for reason in produced), constant)

    def test_a_break_reason_is_never_mistaken_for_the_truncation_notice(self):
        self.assertFalse(B9E.LEFT_TRUNCATED_REASON.startswith(B9E.BREAK_REASONS))
        for constant in B9E.BREAK_REASONS:
            self.assertFalse(constant.startswith(B9E.LEFT_TRUNCATED_REASON))


class ClassificationTests(CoverageFixture):

    def test_each_status_is_assigned_from_its_own_evidence(self):
        self.set_cohort("complete", "truncated", "broken", "absent")
        self.add_observation("complete", anchor=True)
        self.add_observation("complete")
        self.add_observation("truncated")
        self.add_chain_failure("truncated", B9E.LEFT_TRUNCATED_REASON + " in the frozen evidence")
        self.add_observation("broken", anchor=True)
        self.add_chain_failure("broken", B9E.BREAK_REASONS[2] + ": previous={}, derived={}")
        self.assertEqual(self.counts(), {"anchored_complete": 1, "left_truncated": 1,
                                         "broken": 1, "absent": 1})

    def test_a_break_outranks_an_earlier_truncation(self):
        """The strictly worse defect governs usability, so precedence is not cosmetic."""
        self.set_cohort("curve")
        self.add_observation("curve")
        self.add_chain_failure("curve", B9E.LEFT_TRUNCATED_REASON + " in the frozen evidence")
        self.add_chain_failure("curve", B9E.BREAK_REASONS[0])
        self.assertEqual(B9E.cohort_reserve_coverage(self.database)["statuses"]["curve"], "broken")

    def test_observations_without_an_anchor_or_a_truncation_notice_are_unattributable(self):
        """The decoder cannot produce this: a chain starting without an anchor always records the
        notice first. Reaching it means the explaining failure row is gone, so the status is
        unknown -- and an unknown status must not silently count as complete."""
        self.set_cohort("curve")
        self.add_observation("curve")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("unattributable", str(ctx.exception))

    def test_statuses_account_for_every_cohort_curve_including_silent_ones(self):
        """A curve that produced nothing at all is the whole reason the cohort is the denominator:
        it is invisible in the reserve tables and only the cohort reveals it."""
        self.set_cohort(*[f"curve-{n}" for n in range(10)])
        self.add_observation("curve-0", anchor=True)
        coverage = B9E.cohort_reserve_coverage(self.database)
        self.assertEqual(coverage["cohort_curves"], 10)
        self.assertEqual(coverage["counts"]["absent"], 9)
        self.assertEqual(sum(coverage["counts"].values()), 10)

    def test_a_status_outside_the_declared_set_is_refused_rather_than_dropped(self):
        """A curve must land in a named bucket or stop the run.

        The tally is built from `STATUSES`, so an unrecognised status has nowhere to go. Counting
        defensively -- `counts.get(status, 0)` and friends -- would drop the curve from every
        bucket while the totals still looked plausible, which is the silent omission this gate is
        supposed to make impossible.
        """
        self.set_cohort("curve")
        self.add_observation("curve", anchor=True)
        saved = B9E.classify_curve
        B9E.classify_curve = lambda *a, **k: "probably_fine"
        self.addCleanup(lambda: setattr(B9E, "classify_curve", saved))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("unknown coverage status", str(ctx.exception))

    def test_reserve_evidence_outside_the_frozen_cohort_is_refused(self):
        self.set_cohort("known")
        self.add_observation("known", anchor=True)
        self.add_observation("stranger", anchor=True)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("outside the frozen cohort", str(ctx.exception))

    def test_a_discontinuity_that_names_no_curve_is_refused(self):
        """An unattributable break is not a break that can be excluded from a measurement."""
        self.set_cohort("curve")
        self.add_observation("curve", anchor=True)
        self.add_chain_failure("curve", B9E.BREAK_REASONS[0], context={"note": "no curve here"})
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("names no bonding curve", str(ctx.exception))

    def test_an_ambiguous_mint_to_curve_identity_is_refused(self):
        self.cohort = {"mint-a": "shared", "mint-b": "shared"}
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("identity is ambiguous", str(ctx.exception))


    def test_no_curve_is_classified_twice_even_with_evidence_of_several_kinds(self):
        """Statuses partition the cohort; they do not tag it.

        A curve carrying an anchor, observations, a truncation notice AND a break must consume
        exactly one slot in the tally. If classification ever became additive, coverage could
        exceed the cohort size and the fraction could exceed 1.
        """
        self.set_cohort("busy", "quiet")
        self.add_observation("busy", anchor=True)
        self.add_observation("busy")
        self.add_chain_failure("busy", B9E.LEFT_TRUNCATED_REASON + " in the frozen evidence")
        self.add_chain_failure("busy", B9E.BREAK_REASONS[1])
        coverage = B9E.cohort_reserve_coverage(self.database)
        self.assertEqual(sum(coverage["counts"].values()), 2)
        self.assertEqual(len(coverage["statuses"]), 2)
        self.assertEqual(coverage["counts"]["broken"], 1)
        self.assertLessEqual(coverage["counts"]["anchored_complete"], 1)

    def test_incidental_non_cohort_curves_neither_count_nor_dilute(self):
        """Bundled incidental Pump activity is out of scope by construction.

        B9c never enumerated those curve histories, so the decoder skips them and they produce no
        rows. They must also not enter the denominator: an incidental curve is not a cohort curve
        with missing evidence, it is not a member at all. Counting them would understate coverage
        exactly as counting only observed curves would overstate it.
        """
        self.set_cohort("member")
        self.add_observation("member", anchor=True)
        coverage = B9E.cohort_reserve_coverage(self.database)
        self.assertEqual(coverage["cohort_curves"], 1)
        self.assertEqual(coverage["counts"]["anchored_complete"], 1)
        self.assertNotIn("incidental-curve", coverage["statuses"])
        # And if incidental evidence ever DID reach the tables, it is refused rather than absorbed.
        self.add_observation("incidental-curve", anchor=True)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.cohort_reserve_coverage(self.database)
        self.assertIn("outside the frozen cohort", str(ctx.exception))

    def test_discontinuities_are_reported_in_canonical_ledger_order(self):
        """The report names the coordinate of the FIRST break on a curve.

        "First" is only meaningful in canonical ledger order; ordering by rowid would name whichever
        row the decoder happened to write first. Inserted here deliberately out of order.
        """
        self.set_cohort("curve")
        self.add_observation("curve", anchor=True)
        for slot, index in ((900, 5), (700, 2), (700, 1), (800, 9)):
            self.database.execute(
                "INSERT INTO classification_failure (signature,slot,transaction_index,outer_index,"
                "inner_index,program_id,discriminator,reason,context_json) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (f"sig-{slot}-{index}", slot, index, 0, -1, B9D.PUMP_PROGRAM, "00" * 8,
                 B9E.RESERVE_CHAIN_PREFIX + B9E.BREAK_REASONS[1], json.dumps(
                     {"bonding_curve": "curve"})))
        failures = B9E.cohort_reserve_coverage(self.database)["failures"]["curve"]
        self.assertEqual([entry["coordinates"][:2] for entry in failures],
                         [[700, 1], [700, 2], [800, 9], [900, 5]])


class RatificationTests(CoverageFixture):

    def complete_cohort(self, complete, absent):
        self.set_cohort(*([f"ok-{n}" for n in range(complete)] +
                          [f"missing-{n}" for n in range(absent)]))
        for n in range(complete):
            self.add_observation(f"ok-{n}", anchor=True)

    def test_the_gate_refuses_to_run_until_both_thresholds_are_ratified(self):
        """A gate whose threshold defaults to something permissive passes on the day someone
        forgets to set it, which is the day it matters."""
        self.complete_cohort(complete=10, absent=0)
        for kwargs in ({}, {"minimum_anchored_complete_fraction": 0.5},
                       {"eligible_statuses": ["anchored_complete"]}):
            with self.subTest(kwargs=sorted(kwargs)):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9E.assert_reserve_coverage(self.database, **kwargs)
                self.assertIn("not ratified", str(ctx.exception))

    def test_the_denominator_is_the_whole_cohort_not_the_observed_curves(self):
        """The bias this gate exists to catch: one perfect curve out of ten is 10% coverage, and
        would read as 100% if the observed curves were the denominator."""
        self.complete_cohort(complete=1, absent=9)
        measured = B9E.assert_reserve_coverage(
            self.database, 0.1, ["anchored_complete"])["anchored_complete_fraction"]
        self.assertAlmostEqual(measured, 0.1)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.assert_reserve_coverage(self.database, 0.9, ["anchored_complete"])
        self.assertIn("below the preregistered minimum", str(ctx.exception))

    def test_broken_curves_can_never_be_declared_eligible(self):
        self.complete_cohort(complete=1, absent=0)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.assert_reserve_coverage(self.database, 0.5, ["anchored_complete", "broken"])
        self.assertIn("across a discontinuity", str(ctx.exception))

    def test_an_unknown_or_empty_eligible_set_is_refused(self):
        self.complete_cohort(complete=1, absent=0)
        for eligible in ([], ["anchored"], ["anchored_complete", "typo"]):
            with self.subTest(eligible=eligible):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9E.assert_reserve_coverage(self.database, 0.5, eligible)
                self.assertIn("non-empty subset", str(ctx.exception))

    def test_a_nonsensical_minimum_is_refused(self):
        self.complete_cohort(complete=1, absent=0)
        for minimum in (0, -0.1, 1.5):
            with self.subTest(minimum=minimum):
                with self.assertRaises(B9D.FreezeViolation) as ctx:
                    B9E.assert_reserve_coverage(self.database, minimum, ["anchored_complete"])
                self.assertIn("fraction in (0, 1]", str(ctx.exception))

    def test_the_ratified_publication_gate_demands_the_whole_cohort(self):
        """§5 as ratified: 100% anchored_complete, and only anchored_complete is eligible.

        A single curve short of the cohort fails closed. That is the intended severity -- the
        remedy is repairing the missing evidence or preregistering a different estimand over a
        different cohort, never lowering this number to whatever the artifact turned out to be.
        """
        self.assertEqual(B9E.RATIFIED_MINIMUM_ANCHORED_COMPLETE, 1.0)
        self.assertEqual(B9E.RATIFIED_ELIGIBLE_STATUSES, ("anchored_complete",))
        self.complete_cohort(complete=4, absent=0)
        report = B9E.assert_publication_gate(self.database)
        self.assertEqual(report["anchored_complete_fraction"], 1.0)
        self.assertEqual(report["eligible_curves"], 4)

        self.set_cohort(*[f"ok-{n}" for n in range(4)], "one-more")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.assert_publication_gate(self.database)
        self.assertIn("below the preregistered minimum", str(ctx.exception))

    def test_a_left_truncated_curve_alone_cannot_satisfy_the_publication_gate(self):
        """Left-truncated histories are internally continuous but are not launch-anchored, and the
        ratified eligible set excludes them. Admitting them is a decision for a separate
        preregistration, not something a caller can do by passing a different status list here."""
        self.set_cohort("truncated")
        self.add_observation("truncated")
        self.add_chain_failure("truncated", B9E.LEFT_TRUNCATED_REASON + " in the frozen evidence")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9E.assert_publication_gate(self.database)
        self.assertIn("below the preregistered minimum", str(ctx.exception))

    def test_eligible_curves_counts_every_ratified_status(self):
        self.set_cohort("complete", "truncated", "absent")
        self.add_observation("complete", anchor=True)
        self.add_observation("truncated")
        self.add_chain_failure("truncated", B9E.LEFT_TRUNCATED_REASON + " in the frozen evidence")
        report = B9E.assert_reserve_coverage(
            self.database, 0.3, ["anchored_complete", "left_truncated"])
        self.assertEqual(report["eligible_curves"], 2)


class CommandLineTests(CoverageFixture):

    def run_cli(self, *argv):
        self.database.commit()          # the CLI opens its own read-only connection
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = B9E.main([str(self.path), *argv])
        return code, captured.getvalue()

    def test_measuring_without_thresholds_reports_counts_but_does_not_gate(self):
        """Measuring and gating are separate: the distribution has to be readable before anyone
        can ratify a threshold against it."""
        self.set_cohort("complete", "missing")
        self.add_observation("complete", anchor=True)
        code, output = self.run_cli()
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(report["counts"], {"anchored_complete": 1, "left_truncated": 0,
                                            "broken": 0, "absent": 1})
        self.assertNotIn("statuses", report, "per-curve detail is opt-in")

    def test_the_cli_gates_when_thresholds_are_supplied(self):
        self.set_cohort("complete", "missing")
        self.add_observation("complete", anchor=True)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            self.run_cli("--minimum-anchored-complete", "0.9",
                         "--eligible", "anchored_complete")
        self.assertIn("below the preregistered minimum", str(ctx.exception))
        code, output = self.run_cli("--minimum-anchored-complete", "0.5",
                                    "--eligible", "anchored_complete", "--per-curve")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["statuses"]["complete"], "anchored_complete")


class PreregistrationDocumentTests(unittest.TestCase):
    """The document is the artifact the threshold gets ratified in, so its state is testable."""

    PATH = ROOT / "research" / "B9E_RESERVE_COVERAGE_PREREGISTRATION.md"

    def test_the_document_states_the_same_thresholds_the_code_applies(self):
        """The document is where the decision is ratified and the code is where it is enforced.
        If they drift, the preregistration stops describing the gate that actually runs."""
        text = self.PATH.read_text(encoding="utf-8")
        self.assertIn(
            f"minimum_anchored_complete_fraction: {B9E.RATIFIED_MINIMUM_ANCHORED_COMPLETE}", text)
        self.assertIn(f'eligible_statuses:                  {list(B9E.RATIFIED_ELIGIBLE_STATUSES)}'
                      .replace("'", '"'), text)
        for status in B9E.STATUSES:
            self.assertIn(f"`{status}`", text, "every status the code assigns must be defined")

    def test_the_document_records_no_measured_outcome_counts(self):
        """It was written before any decode pass and must stay that way: a preregistration that
        acquires results can be revised to match them without anyone noticing."""
        text = self.PATH.read_text(encoding="utf-8")
        self.assertIn("no measured outcome counts", text)
        self.assertIn("### Verified facts", text)
        self.assertIn("### Open questions", text)

    def test_the_document_names_the_gate_it_preregisters(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertIn("assert_publication_gate", text)
        self.assertIn("assert_reserve_coverage", text)
        self.assertIn("scripts/b9e_reserve_coverage.py", text)


if __name__ == "__main__":
    unittest.main()
