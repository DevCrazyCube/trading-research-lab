"""B12a — the deterministic, fail-closed portfolio risk governor.

A risk governor fails in ways that look like success: it approves because a limit was absent rather
than passed, because a clock was stale, because two concurrent orders each fit on their own, or
because an internal error was swallowed into a permissive default. And it fails in one way that
looks like prudence — quietly shrinking an order — which corrupts every evaluated result downstream
by changing the thing that was evaluated.

Each of those has a test here, and each has a mutant.
"""
import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b12a_risk_governor", ROOT / "scripts" / "b12a_risk_governor.py")
B12A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B12A)

B11B = B12A.B11B
B10B = B12A.B10B
B10A = B12A.B10A
NATIVE = B11B.NATIVE_QUOTE_MINT

MINT = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CURVE = "CurveAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CREATOR = "CreatorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
OTHER_CREATOR = "CreatorBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

ORDER_SIZE = 100_000_000


def proposal(**overrides):
    base = {"proposal_id": "p-0001", "mint": MINT, "bonding_curve": CURVE, "creator": CREATOR,
            "side": B10A.BUY, "quote_lamports": ORDER_SIZE}
    base.update(overrides)
    return base


def state(**overrides):
    base = {"virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
            "real_quote": 5_000_000_000, "real_token": 793_100_000_000_000,
            "quote_mint": NATIVE, "mayhem_mode": False, "complete": False, "slot": 435_600_000}
    base.update(overrides)
    return base


def health(**overrides):
    base = {"kill_switch_engaged": False, "emergency_state": False, "evidence_complete": True,
            "evidence_conflicting": False, "program_version_supported": True,
            "curve_regime_consistent": True, "evidence_slot": 435_600_000,
            "current_slot": 435_600_002, "evidence_unix": 1_785_600_000,
            "current_unix": 1_785_600_001, "provenance": {"artifact": "b9d", "sha256": "abc"}}
    base.update(overrides)
    return base


def portfolio(**overrides):
    base = {"open_positions": [], "pending_orders": [], "realised_pnl_today_lamports": 0,
            "peak_realizable_portfolio_lamports": 10_000_000_000,
            "current_realizable_portfolio_lamports": 10_000_000_000}
    base.update(overrides)
    return base


def config(**overrides):
    base = {"config_version": "test-1", "ratification": "operator_unratified",
            "max_order_lamports": ORDER_SIZE, "max_total_exposure_lamports": 1_000_000_000,
            "max_open_positions": 5, "max_creator_exposure_lamports": 300_000_000,
            "max_creator_positions": 2, "max_daily_realised_loss_lamports": 500_000_000,
            "max_portfolio_drawdown_ratio": [1, 4], "max_pending_exposure_lamports": 400_000_000,
            "max_evidence_age_slots": 10, "max_evidence_age_seconds": 5}
    base.update(overrides)
    return base


def position(creator=CREATOR, deployed=ORDER_SIZE, mint=MINT):
    return {"mint": mint, "creator": creator, "deployed_lamports": deployed}


def pending(proposal_id, creator=CREATOR, quote=ORDER_SIZE, mint=MINT):
    return {"proposal_id": proposal_id, "mint": mint, "creator": creator,
            "quote_lamports": quote}


def decide(**overrides):
    arguments = {"proposal": proposal(), "state": state(), "portfolio": portfolio(),
                 "health": health(), "config": config()}
    arguments.update(overrides)
    return B12A.decide(**arguments)


class HappyPathTests(unittest.TestCase):

    def test_a_clean_proposal_is_approved_exactly_as_proposed(self):
        record = decide()
        self.assertEqual(record["decision"], "approved")
        self.assertEqual(record["reasons"], [])
        self.assertIsNone(record["primary_reason"])
        self.assertEqual(record["proposal"]["quote_lamports"], ORDER_SIZE)
        self.assertFalse(record["order_was_resized"])

    def test_an_approval_publishes_the_book_it_would_create(self):
        record = decide()
        self.assertEqual(record["exposure_before"]["total_exposure_lamports"], 0)
        self.assertEqual(record["exposure_after"]["total_exposure_lamports"], ORDER_SIZE)
        self.assertEqual(record["exposure_after"]["position_count"], 1)

    def test_a_rejection_publishes_no_projected_book(self):
        """It would put a number on an operator's screen describing a state that will never
        exist."""
        record = decide(health=health(kill_switch_engaged=True))
        self.assertEqual(record["decision"], "rejected")
        self.assertIsNone(record["exposure_after"])
        self.assertIsNotNone(record["exposure_before"])

    def test_every_record_says_it_authorises_nothing(self):
        record = decide()
        self.assertTrue(record["approval_is_simulation_only"])
        self.assertIn("neither signs nor submits", record["NO_SIGNING_OR_SUBMISSION"])
        self.assertEqual(record["config_ratification"], "operator_unratified")

    def test_the_module_holds_no_wallet_key_transport_or_submission_path(self):
        source = (ROOT / "scripts" / "b12a_risk_governor.py").read_text().lower()
        for forbidden in ("requests", "urllib", "socket", "sendtransaction", "signtransaction",
                          "private_key", "keypair", "secret", "http"):
            self.assertNotIn(forbidden, source)


class MissingInputTests(unittest.TestCase):
    """Absence is refusal. No financial limit defaults to zero or to infinity."""

    def test_every_config_field_is_required(self):
        for field in B12A.CONFIG_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in config().items() if k != field}
                with self.assertRaisesRegex(B12A.RiskRefused, "does not state"):
                    decide(config=broken)

    def test_every_health_field_is_required(self):
        for field in B12A.HEALTH_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in health().items() if k != field}
                with self.assertRaisesRegex(B12A.RiskRefused, "does not state"):
                    decide(health=broken)

    def test_every_portfolio_field_is_required(self):
        for field in B12A.PORTFOLIO_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in portfolio().items() if k != field}
                with self.assertRaisesRegex(B12A.RiskRefused, "does not state"):
                    decide(portfolio=broken)

    def test_every_proposal_field_is_required(self):
        for field in B12A.PROPOSAL_FIELDS:
            with self.subTest(field=field):
                broken = {k: v for k, v in proposal().items() if k != field}
                with self.assertRaisesRegex(B12A.RiskRefused, "does not state"):
                    decide(proposal=broken)

    def test_a_misspelled_limit_is_refused_rather_than_ignored(self):
        """An unknown key means somebody believes they set a limit they did not."""
        broken = dict(config())
        broken["max_orderr_lamports"] = broken.pop("max_order_lamports")
        with self.assertRaisesRegex(B12A.RiskRefused, "does not state|unknown fields"):
            decide(config=broken)

    def test_an_extra_key_alongside_a_complete_config_is_still_refused(self):
        """The case the misspelling test cannot reach: every required limit IS present, so only
        the unknown-key check can notice that somebody also set a limit that does not exist."""
        with self.assertRaisesRegex(B12A.RiskRefused, "unknown fields"):
            decide(config=dict(config(), max_slippage_bps=50))

    def test_a_limit_of_none_is_refused_and_never_read_as_unlimited(self):
        for field in B12A.CONFIG_INTEGER_LIMITS:
            with self.subTest(field=field):
                with self.assertRaisesRegex(B12A.RiskRefused, "non-negative integer"):
                    decide(config=config(**{field: None}))

    def test_a_negative_limit_is_refused(self):
        with self.assertRaisesRegex(B12A.RiskRefused, "non-negative integer"):
            decide(config=config(max_order_lamports=-1))

    def test_a_drawdown_limit_must_be_an_exact_pair_not_a_percentage(self):
        for bad in (0.25, "25%", [1], [1, 0], [1, -2], None):
            with self.subTest(bad=bad):
                with self.assertRaises(B12A.RiskRefused):
                    decide(config=config(max_portfolio_drawdown_ratio=bad))

    def test_an_unratified_config_is_the_only_thing_that_can_be_declared_today(self):
        self.assertEqual(B12A.ALLOWED_RATIFICATION, ("operator_unratified",))
        for value in ("operator_ratified", "treasury_approved", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(B12A.RiskRefused, "ratification"):
                    decide(config=config(ratification=value))

    def test_a_zero_order_is_not_an_order(self):
        with self.assertRaisesRegex(B12A.RiskRefused, "not an order"):
            decide(proposal=proposal(quote_lamports=0))

    def test_a_sell_proposal_is_refused_in_this_regime(self):
        with self.assertRaisesRegex(B12A.RiskRefused, "side must be"):
            decide(proposal=proposal(side="sell"))


class CapBoundaryTests(unittest.TestCase):
    """A limit is the largest permitted value; strictly exceeding it rejects. One rule, everywhere."""

    def assert_boundary(self, reason, at_cap, over_cap):
        self.assertNotIn(reason, at_cap["reasons"], "at the cap must be permitted")
        self.assertIn(reason, over_cap["reasons"], "one lamport over must reject")

    def test_max_order_lamports_at_and_one_over(self):
        self.assert_boundary(
            B12A.R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS,
            decide(config=config(max_order_lamports=ORDER_SIZE)),
            decide(config=config(max_order_lamports=ORDER_SIZE - 1)))

    def test_total_exposure_at_and_one_over(self):
        self.assert_boundary(
            B12A.R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED,
            decide(config=config(max_total_exposure_lamports=ORDER_SIZE)),
            decide(config=config(max_total_exposure_lamports=ORDER_SIZE - 1)))

    def test_pending_exposure_at_and_one_over(self):
        self.assert_boundary(
            B12A.R23_PENDING_EXPOSURE_LIMIT_EXCEEDED,
            decide(config=config(max_pending_exposure_lamports=ORDER_SIZE)),
            decide(config=config(max_pending_exposure_lamports=ORDER_SIZE - 1)))

    def test_open_position_count_at_and_one_over(self):
        book = portfolio(open_positions=[position(), position(OTHER_CREATOR)])
        self.assert_boundary(
            B12A.R17_OPEN_POSITION_LIMIT_EXCEEDED,
            decide(portfolio=book, config=config(max_open_positions=3)),
            decide(portfolio=book, config=config(max_open_positions=2)))

    def test_creator_exposure_at_and_one_over(self):
        book = portfolio(open_positions=[position(CREATOR, 100_000_000)])
        self.assert_boundary(
            B12A.R18_CREATOR_EXPOSURE_LIMIT_EXCEEDED,
            decide(portfolio=book, config=config(max_creator_exposure_lamports=200_000_000)),
            decide(portfolio=book, config=config(max_creator_exposure_lamports=199_999_999)))

    def test_creator_position_count_at_and_one_over(self):
        book = portfolio(open_positions=[position(CREATOR), position(CREATOR)])
        self.assert_boundary(
            B12A.R19_CREATOR_POSITION_LIMIT_EXCEEDED,
            decide(portfolio=book, config=config(max_creator_positions=3)),
            decide(portfolio=book, config=config(max_creator_positions=2)))

    def test_daily_realised_loss_at_and_one_over(self):
        losing = portfolio(realised_pnl_today_lamports=-500_000_000)
        self.assert_boundary(
            B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED,
            decide(portfolio=losing, config=config(max_daily_realised_loss_lamports=500_000_000)),
            decide(portfolio=losing, config=config(max_daily_realised_loss_lamports=499_999_999)))

    def test_a_realised_profit_never_trips_the_loss_limit(self):
        winning = portfolio(realised_pnl_today_lamports=10_000_000_000)
        self.assertNotIn(B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED,
                         decide(portfolio=winning)["reasons"])


class DrawdownTests(unittest.TestCase):

    def test_the_drawdown_limit_is_an_exact_rational_comparison(self):
        """A quarter is exactly a quarter. 2,500,000,001 of 10,000,000,000 is over it by one
        lamport, and a float comparison at this magnitude cannot be relied on to say so."""
        at_limit = portfolio(peak_realizable_portfolio_lamports=10_000_000_000,
                             current_realizable_portfolio_lamports=7_500_000_000)
        over = portfolio(peak_realizable_portfolio_lamports=10_000_000_000,
                         current_realizable_portfolio_lamports=7_499_999_999)
        self.assertNotIn(B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED,
                         decide(portfolio=at_limit)["reasons"])
        self.assertIn(B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED,
                      decide(portfolio=over)["reasons"])

    def test_an_unverifiable_drawdown_rejects_rather_than_passing(self):
        """A peak of zero is not evidence of no decline, and a limit that cannot be checked has
        not been passed."""
        for book in (portfolio(peak_realizable_portfolio_lamports=0),
                     portfolio(peak_realizable_portfolio_lamports=-1),
                     portfolio(peak_realizable_portfolio_lamports=1_000,
                               current_realizable_portfolio_lamports=2_000)):
            with self.subTest(peak=book["peak_realizable_portfolio_lamports"]):
                record = decide(portfolio=book)
                self.assertIn(B12A.R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE, record["reasons"])
                self.assertEqual(record["decision"], "rejected")

    def test_a_zero_drawdown_allowance_still_permits_an_undrawn_book(self):
        record = decide(config=config(max_portfolio_drawdown_ratio=[0, 1]))
        self.assertNotIn(B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED, record["reasons"])
        drawn = portfolio(peak_realizable_portfolio_lamports=10_000_000_000,
                          current_realizable_portfolio_lamports=9_999_999_999)
        self.assertIn(B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED,
                      decide(portfolio=drawn,
                             config=config(max_portfolio_drawdown_ratio=[0, 1]))["reasons"])


class StalenessTests(unittest.TestCase):

    def test_slot_staleness_at_and_one_over(self):
        fresh = health(evidence_slot=435_600_000, current_slot=435_600_010)
        stale = health(evidence_slot=435_600_000, current_slot=435_600_011)
        self.assertNotIn(B12A.R06_EVIDENCE_STALE_SLOTS, decide(health=fresh)["reasons"])
        self.assertIn(B12A.R06_EVIDENCE_STALE_SLOTS, decide(health=stale)["reasons"])

    def test_wall_clock_staleness_at_and_one_over(self):
        fresh = health(evidence_unix=1_785_600_000, current_unix=1_785_600_005)
        stale = health(evidence_unix=1_785_600_000, current_unix=1_785_600_006)
        self.assertNotIn(B12A.R07_EVIDENCE_STALE_SECONDS, decide(health=fresh)["reasons"])
        self.assertIn(B12A.R07_EVIDENCE_STALE_SECONDS, decide(health=stale)["reasons"])

    def test_both_clocks_are_checked_because_either_can_stop_alone(self):
        """Slots stop advancing during an outage while the wall clock keeps running, and a stalled
        provider can replay an old slot under a fresh timestamp. Checking one is checking neither."""
        record = decide(health=health(evidence_slot=1, current_slot=435_600_000,
                                      evidence_unix=1, current_unix=1_785_600_000))
        self.assertIn(B12A.R06_EVIDENCE_STALE_SLOTS, record["reasons"])
        self.assertIn(B12A.R07_EVIDENCE_STALE_SECONDS, record["reasons"])

    def test_evidence_from_the_future_is_conflicting_not_fresh(self):
        for override in ({"evidence_slot": 435_600_003, "current_slot": 435_600_002},
                         {"evidence_unix": 1_785_600_009, "current_unix": 1_785_600_001}):
            with self.subTest(**override):
                self.assertIn(B12A.R04_EVIDENCE_CONFLICTING,
                              decide(health=health(**override))["reasons"])

    def test_incomplete_and_conflicting_evidence_each_reject(self):
        self.assertIn(B12A.R03_EVIDENCE_INCOMPLETE,
                      decide(health=health(evidence_complete=False))["reasons"])
        self.assertIn(B12A.R04_EVIDENCE_CONFLICTING,
                      decide(health=health(evidence_conflicting=True))["reasons"])

    def test_an_unsupported_program_version_rejects(self):
        self.assertIn(B12A.R05_PROGRAM_VERSION_UNSUPPORTED,
                      decide(health=health(program_version_supported=False))["reasons"])


class EligibilityReuseTests(unittest.TestCase):
    """The governor and the evaluator must admit exactly the same curves."""

    def test_curve_eligibility_is_delegated_to_b11b_rather_than_reimplemented(self):
        source = (ROOT / "scripts" / "b12a_risk_governor.py").read_text()
        self.assertIn("B11B.evaluate_vetoes(", source)
        for formula in ("virtual_token //", "* virtual_token", "tokens_out_for_exact_quote_in"):
            self.assertNotIn(formula, source)

    def test_every_b11b_veto_maps_to_a_declared_reason(self):
        self.assertEqual(set(B12A.VETO_TO_REASON), set(B11B.VETO_CODES))
        for reason in B12A.VETO_TO_REASON.values():
            self.assertIn(reason, B12A.REASON_PRECEDENCE)

    def test_the_regime_vetoes_reject(self):
        cases = {
            B12A.R08_NON_SOL_QUOTE: {"state": state(quote_mint="OtherMint111")},
            B12A.R09_MAYHEM_MODE: {"state": state(mayhem_mode=True)},
            B12A.R10_CURVE_COMPLETE: {"state": state(complete=True)},
            B12A.R12_MIXED_REGIME_WITHIN_CURVE: {
                "health": health(curve_regime_consistent=False)},
            B12A.R13_ORDER_EXCEEDS_RESERVE_CAPACITY: {"state": state(real_token=1_000)},
        }
        for reason, override in cases.items():
            with self.subTest(reason=reason):
                self.assertIn(reason, decide(**override)["reasons"])

    def test_an_incomplete_curve_state_rejects(self):
        broken = state()
        del broken["complete"]
        self.assertIn(B12A.R11_CURVE_STATE_INCOMPLETE, decide(state=broken)["reasons"])

    def test_an_order_below_the_curve_resolution_rejects(self):
        record = decide(proposal=proposal(quote_lamports=1),
                        config=config(max_order_lamports=1))
        self.assertIn(B12A.R14_ORDER_BUYS_ZERO_TOKENS, record["reasons"])


class KillSwitchAndEmergencyTests(unittest.TestCase):

    def test_the_kill_switch_rejects_an_otherwise_clean_proposal(self):
        self.assertEqual(decide()["decision"], "approved")
        record = decide(health=health(kill_switch_engaged=True))
        self.assertEqual(record["decision"], "rejected")
        self.assertEqual(record["primary_reason"], B12A.R02_KILL_SWITCH_ENGAGED)

    def test_emergency_state_rejects_a_previously_acceptable_proposal(self):
        """Same proposal, same state, same book, same config — only the flag differs."""
        arguments = {"proposal": proposal(), "state": state(), "portfolio": portfolio(),
                     "config": config()}
        self.assertEqual(B12A.decide(health=health(), **arguments)["decision"], "approved")
        emergency = B12A.decide(health=health(emergency_state=True), **arguments)
        self.assertEqual(emergency["decision"], "rejected")
        self.assertEqual(emergency["primary_reason"], B12A.R01_EMERGENCY_STATE)

    def test_emergency_state_outranks_every_other_reason(self):
        record = decide(health=health(emergency_state=True, kill_switch_engaged=True,
                                      evidence_complete=False))
        self.assertEqual(record["reasons"][0], B12A.R01_EMERGENCY_STATE)
        self.assertIn(B12A.R02_KILL_SWITCH_ENGAGED, record["reasons"])
        self.assertIn(B12A.R03_EVIDENCE_INCOMPLETE, record["reasons"])

    def test_emergency_state_rejects_even_an_empty_book_and_perfect_evidence(self):
        self.assertEqual(
            decide(health=health(emergency_state=True), portfolio=portfolio())["decision"],
            "rejected")


class PendingExposureTests(unittest.TestCase):
    """Two orders that each fit and together do not is the concurrency failure to prevent."""

    def test_pending_orders_count_toward_every_exposure_limit(self):
        book = portfolio(pending_orders=[pending("p-existing")])
        before = decide(portfolio=book)["exposure_before"]
        self.assertEqual(before["pending_exposure_lamports"], ORDER_SIZE)
        self.assertEqual(before["total_exposure_lamports"], ORDER_SIZE)
        self.assertEqual(before["position_count"], 1)
        self.assertEqual(before["creator_position_count"], 1)

    def test_a_second_concurrent_proposal_is_rejected_once_the_first_is_pending(self):
        """No mutable global: the caller threads the snapshot, and `apply_approved` returns a NEW
        one. That is what makes the second call see the first."""
        tight = config(max_total_exposure_lamports=ORDER_SIZE)
        first = decide(config=tight)
        self.assertEqual(first["decision"], "approved")
        book = B12A.apply_approved(portfolio(), first)
        second = decide(proposal=proposal(proposal_id="p-0002"), portfolio=book, config=tight)
        self.assertEqual(second["decision"], "rejected")
        self.assertIn(B12A.R16_TOTAL_EXPOSURE_LIMIT_EXCEEDED, second["reasons"])

    def test_apply_approved_never_mutates_the_snapshot_it_was_given(self):
        book = portfolio()
        before = copy.deepcopy(book)
        updated = B12A.apply_approved(book, decide())
        self.assertEqual(book, before)
        self.assertEqual(len(updated["pending_orders"]), 1)
        self.assertEqual(len(book["pending_orders"]), 0)

    def test_only_an_approved_decision_may_be_applied(self):
        with self.assertRaisesRegex(B12A.RiskRefused, "only an approved decision"):
            B12A.apply_approved(portfolio(), decide(health=health(kill_switch_engaged=True)))

    def test_the_same_proposal_twice_is_rejected_as_a_duplicate(self):
        """Otherwise a retry double-counts, and the book grows by an order nobody placed twice."""
        book = B12A.apply_approved(portfolio(), decide())
        again = decide(portfolio=book)
        self.assertIn(B12A.R24_DUPLICATE_PENDING_PROPOSAL, again["reasons"])

    def test_the_governor_holds_no_state_between_calls(self):
        first = decide()
        second = decide()
        self.assertEqual(first["decision_sha256"], second["decision_sha256"])
        self.assertEqual(first["exposure_before"], second["exposure_before"])

    def test_creator_exposure_counts_open_and_pending_together(self):
        book = portfolio(open_positions=[position(CREATOR, 100_000_000)],
                         pending_orders=[pending("p-x", CREATOR, 100_000_000)])
        before = decide(portfolio=book)["exposure_before"]
        self.assertEqual(before["creator_exposure_lamports"], 200_000_000)
        self.assertEqual(before["creator_position_count"], 2)

    def test_another_creators_exposure_does_not_count_against_this_one(self):
        """Concentration is per creator. Counting every position against every creator would make
        the concentration limit a second, tighter copy of the global one."""
        book = portfolio(open_positions=[position(OTHER_CREATOR, 900_000_000)],
                         pending_orders=[pending("p-other", OTHER_CREATOR, 50_000_000)])
        before = decide(portfolio=book)["exposure_before"]
        self.assertEqual(before["creator_exposure_lamports"], 0)
        self.assertEqual(before["creator_position_count"], 0)
        self.assertEqual(before["position_count"], 2)
        self.assertEqual(before["total_exposure_lamports"], 950_000_000)


class ReasonOrderTests(unittest.TestCase):

    def test_reasons_come_back_in_the_declared_precedence(self):
        record = decide(health=health(kill_switch_engaged=True, evidence_complete=False),
                        state=state(mayhem_mode=True),
                        config=config(max_order_lamports=1))
        index = B12A.REASON_PRECEDENCE.index
        self.assertEqual(record["reasons"], sorted(record["reasons"], key=index))
        self.assertEqual(record["primary_reason"], record["reasons"][0])

    def test_the_order_is_by_the_declared_tuple_not_by_insertion_or_alphabet(self):
        """Handed a permuted precedence, the output must follow it. A sort nobody can distinguish
        from an accident is not a specified sort."""
        permuted = tuple(reversed(B12A.REASON_PRECEDENCE))
        codes = [B12A.R02_KILL_SWITCH_ENGAGED, B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED,
                 B12A.R09_MAYHEM_MODE]
        self.assertEqual(B12A.order_reasons(codes),
                         (B12A.R02_KILL_SWITCH_ENGAGED, B12A.R09_MAYHEM_MODE,
                          B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED))
        self.assertEqual(B12A.order_reasons(codes, permuted),
                         (B12A.R20_DAILY_REALISED_LOSS_LIMIT_EXCEEDED, B12A.R09_MAYHEM_MODE,
                          B12A.R02_KILL_SWITCH_ENGAGED))

    def test_the_result_does_not_depend_on_the_order_the_codes_arrive_in(self):
        codes = [B12A.R09_MAYHEM_MODE, B12A.R02_KILL_SWITCH_ENGAGED, B12A.R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS]
        self.assertEqual(B12A.order_reasons(codes),
                         B12A.order_reasons(list(reversed(codes))))

    def test_duplicates_collapse(self):
        self.assertEqual(
            B12A.order_reasons([B12A.R09_MAYHEM_MODE, B12A.R09_MAYHEM_MODE]),
            (B12A.R09_MAYHEM_MODE,))

    def test_an_undeclared_reason_is_refused_rather_than_appended(self):
        with self.assertRaisesRegex(B12A.RiskRefused, "not in the declared precedence"):
            B12A.order_reasons(["R99_SEEMED_RISKY"])

    def test_the_precedence_covers_every_declared_reason_exactly_once(self):
        self.assertEqual(len(B12A.REASON_PRECEDENCE), len(set(B12A.REASON_PRECEDENCE)))
        declared = {name for name in dir(B12A) if name.startswith("R") and name[1:3].isdigit()}
        self.assertEqual({getattr(B12A, name) for name in declared},
                         set(B12A.REASON_PRECEDENCE))

    def test_all_applicable_reasons_are_reported_not_only_the_first(self):
        record = decide(health=health(kill_switch_engaged=True),
                        config=config(max_order_lamports=1))
        self.assertIn(B12A.R02_KILL_SWITCH_ENGAGED, record["reasons"])
        self.assertIn(B12A.R15_ORDER_EXCEEDS_MAX_ORDER_LAMPORTS, record["reasons"])


class NoResizeAndImmutabilityTests(unittest.TestCase):

    def test_the_governor_never_offers_a_smaller_order(self):
        """The failure that looks like prudence. A shrunk order changes the thing being evaluated,
        and every downstream return then describes a strategy nobody wrote."""
        record = decide(config=config(max_order_lamports=ORDER_SIZE - 1))
        self.assertEqual(record["decision"], "rejected")
        self.assertEqual(record["proposal"]["quote_lamports"], ORDER_SIZE)
        blob = json.dumps(record)
        for forbidden in ("suggested_size", "adjusted_quote", "max_allowed_size",
                          "permitted_quote_lamports", "reduced_to"):
            self.assertNotIn(forbidden, blob)
        self.assertFalse(record["order_was_resized"])
        self.assertIn("rejects it", record["resizing_is_not_available"])

    def test_no_input_is_mutated(self):
        inputs = (proposal(), state(), portfolio(open_positions=[position()]), health(), config())
        before = copy.deepcopy(inputs)
        B12A.decide(*inputs)
        self.assertEqual(before, inputs)

    def test_the_echoed_proposal_is_a_copy_not_the_callers_object(self):
        original = proposal()
        record = B12A.decide(original, state(), portfolio(), health(), config())
        record["proposal"]["quote_lamports"] = 1
        self.assertEqual(original["quote_lamports"], ORDER_SIZE)


class FailClosedTests(unittest.TestCase):

    def test_an_unexpected_internal_failure_refuses_rather_than_approving(self):
        """A bug must be able to stop this system and must never be able to open it.

        Injected rather than provoked through bad input: bad input is already caught by validation
        and raises a RiskRefused, which is a DIFFERENT path from the one that handles a genuine
        internal fault. Only a real exception exercises the fail-closed handler."""
        original = B12A._projected

        def explode(*args, **kwargs):
            raise ValueError("arithmetic went wrong somewhere nobody anticipated")

        B12A._projected = explode
        try:
            with self.assertRaisesRegex(B12A.RiskRefused, "could not complete a decision"):
                decide()
        finally:
            B12A._projected = original
        self.assertEqual(decide()["decision"], "approved", "the seam must be restored")

    def test_malformed_input_refuses_rather_than_approving(self):
        broken = portfolio(open_positions=[{"mint": MINT, "creator": CREATOR,
                                            "deployed_lamports": "lots"}])
        with self.assertRaises(B12A.RiskRefused):
            decide(portfolio=broken)

    def test_a_malformed_pending_entry_refuses(self):
        for entry in ({"mint": MINT, "creator": CREATOR, "quote_lamports": 1},
                      {"proposal_id": "p", "creator": CREATOR, "quote_lamports": 1},
                      "not a mapping"):
            with self.subTest(entry=entry):
                with self.assertRaises(B12A.RiskRefused):
                    decide(portfolio=portfolio(pending_orders=[entry]))

    def test_an_approved_record_can_never_carry_reasons(self):
        record = decide()
        record["reasons"] = [B12A.R09_MAYHEM_MODE]
        with self.assertRaisesRegex(B12A.RiskRefused, "approved while holding"):
            B12A._assert_record_consistent(record)

    def test_a_rejected_record_can_never_be_unexplained(self):
        record = decide(health=health(kill_switch_engaged=True))
        record["reasons"] = []
        with self.assertRaisesRegex(B12A.RiskRefused, "unexplained refusal"):
            B12A._assert_record_consistent(record)

    def test_a_rejected_record_can_never_publish_a_projected_book(self):
        record = decide(health=health(kill_switch_engaged=True))
        record["exposure_after"] = {"total_exposure_lamports": 1}
        with self.assertRaisesRegex(B12A.RiskRefused, "will never exist"):
            B12A._assert_record_consistent(record)

    def test_the_record_shows_what_the_loss_and_drawdown_controls_were_checked_against(self):
        """Otherwise an operator can see THAT they passed but not against what, and two different
        books could produce a byte-identical decision."""
        book = portfolio(realised_pnl_today_lamports=-7,
                         peak_realizable_portfolio_lamports=10_000_000_000,
                         current_realizable_portfolio_lamports=9_000_000_000)
        risk = decide(portfolio=book)["portfolio_risk"]
        self.assertEqual(risk["realised_pnl_today_lamports"], -7)
        self.assertEqual(risk["current_drawdown_ratio"], [1, 10])
        self.assertEqual(risk["max_portfolio_drawdown_ratio"], [1, 4])
        self.assertEqual(risk["max_daily_realised_loss_lamports"], 500_000_000)
        unverifiable = decide(portfolio=portfolio(peak_realizable_portfolio_lamports=0))
        self.assertIsNone(unverifiable["portfolio_risk"]["current_drawdown_ratio"])

    def test_the_exposure_block_holds_no_identity(self):
        record = decide()
        for value in record["exposure_before"].values():
            self.assertIsInstance(value, int)
            self.assertNotIsInstance(value, bool)
        self.assertEqual(set(record["grouping"]), set(B12A.GROUPING_FIELDS))
        self.assertEqual(record["grouping"]["creator"], CREATOR)


class HashStabilityTests(unittest.TestCase):

    def test_the_same_inputs_produce_the_same_record_and_hash(self):
        self.assertEqual(B10B.canonical_json(decide()), B10B.canonical_json(decide()))
        self.assertEqual(decide()["decision_sha256"], decide()["decision_sha256"])

    def test_one_lamport_anywhere_moves_the_hash(self):
        base = decide()["decision_sha256"]
        for override in ({"proposal": proposal(quote_lamports=ORDER_SIZE - 1)},
                         {"portfolio": portfolio(realised_pnl_today_lamports=-1)},
                         {"health": health(current_slot=435_600_003)},
                         {"config": config(max_order_lamports=ORDER_SIZE + 1)}):
            with self.subTest(**override):
                self.assertNotEqual(base, decide(**override)["decision_sha256"])

    def test_the_config_hash_is_stable_across_key_order(self):
        shuffled = dict(reversed(list(config().items())))
        self.assertEqual(B12A.config_hash(config()), B12A.config_hash(shuffled))
        self.assertNotEqual(B12A.config_hash(config()),
                            B12A.config_hash(config(max_open_positions=6)))

    def test_the_record_round_trips_through_json_unchanged(self):
        record = decide()
        blob = B10B.canonical_json(record)
        self.assertEqual(blob, B10B.canonical_json(json.loads(blob)))

    def test_no_float_appears_anywhere_in_a_decision(self):
        def walk(node, where):
            if isinstance(node, float):
                self.fail(f"a float reached the decision at {where}: {node!r}")
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{where}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{where}[{index}]")

        walk(json.loads(B10B.canonical_json(decide())), "decision")
        walk(json.loads(B10B.canonical_json(
            decide(health=health(emergency_state=True)))), "decision")


class ScopeTests(unittest.TestCase):
    """This handoff must not alter B11b or unlock B11a."""

    def test_b11b_still_declares_no_model_and_its_hashes_are_unchanged(self):
        self.assertEqual(B11B.MODEL_FAMILY, "none")
        self.assertEqual(B11B.PREREGISTRATION_FILE_SHA256,
                         "55263060716e99500a097f11260c047d03dbf16c4779a37b3f159d55592cb220")
        B11B.load_preregistration()

    def test_b11a_results_remain_locked(self):
        report = B11B.evaluate_unlock_evidence({
            "b11b_prereg_file_sha256": B11B.PREREGISTRATION_FILE_SHA256,
            "b11b_prereg_canonical_sha256": B11B.PREREGISTRATION_CANONICAL_SHA256,
            "recorded_in_decisions": True, "model_family": "none",
            "collection_complete": False, "gates_passed": False,
            "b11a_prereg_file_sha256": B11B.B11A_PREREGISTRATION_FILE_SHA256,
            "decisions_unlock_entry": "none"})
        self.assertFalse(report["unlocked"])
        self.assertIn("U3", report["unmet"])


class GuardsFoundUntestedByMutationTests(unittest.TestCase):
    """Three guards a mutation sweep could neuter without any existing test noticing.

    PLAN.md has claimed 36/36 for this module since before sweeps were reproducible. Making that
    claim re-runnable (`research/mutation/b12a.sweep.json`) surfaced these three. This module is
    the last thing standing between a model and an order, so a guard here that no test can
    distinguish from its absence is not a guard.
    """

    def test_the_drawdown_comparison_is_exact_and_a_float_would_approve_what_it_rejects(self):
        """The no-float rule, at the one place a float changes a decision rather than a report.

        `drawdown_reason` cross-multiplies instead of dividing. Replacing that with float division
        survived every existing test, because no test used values where float64 loses integer
        precision — above ~9e15, its 53-bit mantissa cannot represent consecutive integers.

        The divergence is not symmetric. At these values exact arithmetic says the drawdown limit
        is EXCEEDED and float says it is not, so the float version approves an order the exact one
        refuses. That is the direction that costs money, and it is why the rule is "no float
        anywhere" rather than "no float where it matters" — nobody should have to work out where
        the boundary bites.
        """
        peak, current = 10**17, 66666666666666666
        numerator, denominator = 1, 3

        exact_exceeded = (peak - current) * denominator > numerator * peak
        float_exceeded = (peak - current) / peak > numerator / denominator
        self.assertTrue(exact_exceeded, "the fixture must be over the limit exactly")
        self.assertFalse(float_exceeded, "and under it in float, or this proves nothing")

        book = portfolio()
        book["peak_realizable_portfolio_lamports"] = peak
        book["current_realizable_portfolio_lamports"] = current
        limits = dict(config(), max_portfolio_drawdown_ratio=[numerator, denominator])

        self.assertEqual(B12A.drawdown_reason(book, limits),
                         B12A.R21_PORTFOLIO_DRAWDOWN_LIMIT_EXCEEDED)

    def test_a_health_flag_that_is_not_a_boolean_is_refused(self):
        """`1` and `"yes"` are truthy, and a truthy kill switch that is not `True` is a flag whose
        producer and consumer disagree about the type. The governor refuses rather than coercing."""
        for field in ("kill_switch_engaged", "emergency_state", "evidence_complete",
                      "evidence_conflicting", "program_version_supported",
                      "curve_regime_consistent"):
            for value in (1, 0, "true", None):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(B12A.RiskRefused):
                        B12A.assert_health(dict(health(), **{field: value}))

    def test_a_record_claiming_a_resized_order_is_refused(self):
        """The governor approves the exact order or rejects it; it never shrinks one.

        That property is load-bearing — a governor that silently resizes changes the thing being
        evaluated — and `_assert_record_consistent` enforces it, but nothing exercised the branch,
        so neutering it changed nothing observable.
        """
        record = decide()
        self.assertIs(record["order_was_resized"], False)

        with self.assertRaisesRegex(B12A.RiskRefused, "does not resize"):
            B12A._assert_record_consistent(dict(record, order_was_resized=True))


if __name__ == "__main__":
    unittest.main()
