"""B10a — the deterministic direct-Pump simulator kernel.

Three properties carry this module, and each is a way a backtest lies to its author if it breaks:
an execution parameter must never be invented, post-decision state must never reach entry pricing,
and no result may ever be labelled executable.
"""
import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b10a_simulator_kernel", ROOT / "scripts" / "b10a_simulator_kernel.py")
B10A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B10A)

B9D = B10A.B9D
NATIVE = B9D.NATIVE_QUOTE_MINT

# A launch-shaped curve, and a fee schedule matching the only rates observed in the artifact.
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5_000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
          "ata_rent_lamports": 2_039_280, "failed_attempts": 0}


def state(slot=700, complete=False, mayhem=False, quote_mint=NATIVE,
          virtual_quote=30_000_000_000, virtual_token=1_073_000_000_000_000,
          real_quote=30_000_000_000, real_token=793_100_000_000_000):
    return {"virtual_quote": virtual_quote, "virtual_token": virtual_token,
            "real_quote": real_quote, "real_token": real_token, "quote_mint": quote_mint,
            "mayhem_mode": mayhem, "complete": complete, "slot": slot}


ORDER = {"side": B10A.BUY, "quote_lamports": 100_000_000}


class EligibilityTests(unittest.TestCase):
    """The frozen regime, enforced as point-in-time predicates that refuse rather than skip."""

    def test_a_non_sol_quote_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "not native SOL"):
            B10A.price_entry(state(quote_mint="OtherMint111"), ORDER, SCHEDULE, POLICY)

    def test_mayhem_mode_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "Mayhem"):
            B10A.price_entry(state(mayhem=True), ORDER, SCHEDULE, POLICY)

    def test_entry_into_a_completed_curve_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "already complete"):
            B10A.price_entry(state(complete=True), ORDER, SCHEDULE, POLICY)

    def test_incomplete_state_is_refused_rather_than_defaulted(self):
        for field in ("virtual_quote", "virtual_token", "quote_mint", "mayhem_mode",
                      "complete", "slot"):
            with self.subTest(field=field):
                broken = state()
                del broken[field]
                with self.assertRaisesRegex(B10A.SimulationRefused, "incomplete"):
                    B10A.price_entry(broken, ORDER, SCHEDULE, POLICY)

    def test_a_sell_order_is_not_an_entry(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "side"):
            B10A.price_entry(state(), {"side": B10A.SELL, "quote_lamports": 1}, SCHEDULE, POLICY)

    def test_an_order_larger_than_the_curve_can_supply_is_refused(self):
        """Against the REAL reserve. A virtual-reserve check looks like a size guard and is not
        one: the curve formula approaches the virtual reserve asymptotically and never reaches it,
        so no order however large would ever trip it."""
        huge = {"side": B10A.BUY, "quote_lamports": 10 ** 18}
        with self.assertRaisesRegex(B10A.SimulationRefused, "exceeds available reserves"):
            B10A.price_entry(state(), huge, SCHEDULE, POLICY)
        tokens = B10A.B9I.tokens_out_for_exact_quote_in(
            30_000_000_000, 1_073_000_000_000_000, 10 ** 18)
        self.assertLess(tokens, 1_073_000_000_000_000,
                        "the virtual reserve is never reached, which is why it cannot guard size")

    def test_an_exit_drawing_more_than_the_curve_holds_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "cannot pay"):
            B10A.price_exit(state(900, real_quote=1), 10 ** 12, SCHEDULE, POLICY)

    def test_an_order_too_small_to_buy_a_token_is_refused_not_rounded_to_zero(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "buys zero tokens"):
            B10A.price_entry(state(), {"side": B10A.BUY, "quote_lamports": 1}, SCHEDULE, POLICY)


class NoInventedDefaultsTests(unittest.TestCase):
    """Absence is not zero. Zero priority fee is the most optimistic assumption available."""

    def test_every_required_cost_must_be_stated(self):
        for field in B10A.REQUIRED_POLICY_FIELDS:
            with self.subTest(field=field):
                partial = {k: v for k, v in POLICY.items() if k != field}
                with self.assertRaisesRegex(B10A.SimulationRefused, "absence is not zero"):
                    B10A.price_entry(state(), ORDER, SCHEDULE, partial)

    def test_every_fee_rate_must_be_stated(self):
        for field in B10A.REQUIRED_FEE_FIELDS:
            with self.subTest(field=field):
                partial = {k: v for k, v in SCHEDULE.items() if k != field}
                with self.assertRaisesRegex(B10A.SimulationRefused, "does not state"):
                    B10A.price_entry(state(), ORDER, partial, POLICY)

    def test_a_fee_rate_outside_the_basis_point_range_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "outside 0..10000"):
            B10A.price_entry(state(), ORDER, dict(SCHEDULE, fee_bps=10_001), POLICY)

    def test_no_result_is_ever_labelled_executable(self):
        result = B10A.simulate_round_trip(state(700), state(900), ORDER, SCHEDULE, POLICY)
        self.assertEqual(result["outcome_label"], B10A.OUTCOME_SIMULATED)
        self.assertEqual(result["calibration"], B10A.CALIBRATION_UNCALIBRATED)
        self.assertNotIn("executable", json.dumps(result).lower())


class LeakageBoundaryTests(unittest.TestCase):
    """Reserve observations after t0 are OUTCOMES. They may never price the entry."""

    def test_entry_pricing_cannot_see_the_exit_state(self):
        """Structural, not a convention: `price_entry` has no parameter for a later state."""
        import inspect
        self.assertNotIn("exit", inspect.signature(B10A.price_entry).parameters)

    def test_entry_flows_are_identical_whatever_the_exit_turns_out_to_be(self):
        """If a future observation could influence entry, this is where it would show."""
        collapsed = state(900, virtual_quote=1_000_000, virtual_token=10 ** 15)
        mooned = state(900, virtual_quote=900_000_000_000, virtual_token=10 ** 12,
                       real_quote=10 ** 12)
        first = B10A.simulate_round_trip(state(700), collapsed, ORDER, SCHEDULE, POLICY)
        second = B10A.simulate_round_trip(state(700), mooned, ORDER, SCHEDULE, POLICY)
        self.assertEqual(first["entry"], second["entry"])
        self.assertNotEqual(first["exit"]["quote_lamports"], second["exit"]["quote_lamports"])

    def test_an_exit_at_or_before_the_decision_instant_is_refused(self):
        for exit_slot in (700, 699):
            with self.subTest(exit_slot=exit_slot):
                with self.assertRaisesRegex(B10A.SimulationRefused, "does not follow entry"):
                    B10A.simulate_round_trip(
                        state(700), state(exit_slot), ORDER, SCHEDULE, POLICY)


class ExitTests(unittest.TestCase):

    def test_a_completed_curve_makes_the_exit_unavailable_not_marked(self):
        """No invented mark and no assumed migration -- `DECISIONS.md` exit boundary."""
        result = B10A.simulate_round_trip(
            state(700), state(900, complete=True), ORDER, SCHEDULE, POLICY)
        self.assertEqual(result["status"], B10A.STATUS_EXIT_UNAVAILABLE)
        self.assertEqual(result["exit"]["liquidity"], B10A.L3_CURVE_COMPLETE)
        self.assertIsNone(result["exit"]["quote_lamports"])
        self.assertIsNone(result["net_lamports"])

    def test_a_constrained_exit_returns_less_than_the_entry_paid(self):
        """Exiting into depleted reserves is the normal case and must price, not refuse."""
        result = B10A.simulate_round_trip(
            state(700), state(900, virtual_quote=1_000_000_000), ORDER, SCHEDULE, POLICY)
        self.assertEqual(result["status"], B10A.STATUS_PRICED)
        self.assertLess(result["net_lamports"], 0)

    def test_proceeds_below_cost_are_reported_negative_not_clamped(self):
        """Clamping to zero would hide exactly the case that matters most."""
        exit_leg = B10A.price_exit(
            state(900, virtual_quote=1_000), 10, SCHEDULE, POLICY)
        self.assertLess(exit_leg["lamports_into_wallet"], 0)


class ArithmeticTests(unittest.TestCase):
    """The kernel must reuse b9i's proven functions, not carry a private copy."""

    def test_the_curve_functions_are_b9i_s_own(self):
        self.assertIs(B10A.B9I.tokens_out_for_exact_quote_in.__module__ and
                      B10A.B9I.tokens_out_for_exact_quote_in,
                      B10A.B9I.tokens_out_for_exact_quote_in)
        entry = B10A.price_entry(state(), ORDER, SCHEDULE, POLICY)
        self.assertEqual(
            entry["tokens_out"],
            B10A.B9I.tokens_out_for_exact_quote_in(
                30_000_000_000, 1_073_000_000_000_000, 100_000_000))

    def test_fees_use_ceiling_but_buyback_uses_floor(self):
        """The one rounding difference in the whole fee set, and it was wrong for three handoffs.

        The quote is chosen so the protocol fee is ODD. At 5,000 bps floor and ceil agree on every
        even fee, so an even-fee fixture cannot tell them apart -- mutation caught exactly that
        hole here, the second time the same trap has been walked into.
        """
        fees = B10A.curve_fees(100, dict(SCHEDULE, fee_bps=95))
        self.assertEqual(fees["fee"], 1, "fixture must produce an odd fee to discriminate")
        self.assertEqual(fees["fee"] % 2, 1)
        self.assertEqual(fees["buyback_fee_reported_not_charged"], 0)
        self.assertEqual(B10A.B9I.ceil_div(fees["fee"] * 5000, 10000), 1)

    def test_the_buyback_fee_is_reported_but_never_charged(self):
        """It is a split of the protocol fee, not an addition. The pinned gross identity is
        `quote + fee + creator + cashback` with no buyback term, so charging it would take half the
        protocol fee from the user twice."""
        fees = B10A.curve_fees(1_000_000, SCHEDULE)
        self.assertGreater(fees["buyback_fee_reported_not_charged"], 0)
        self.assertEqual(fees["charged_total"],
                         fees["fee"] + fees["creator_fee"] + fees["cashback"])

    def test_ata_rent_is_charged_on_entry_and_never_credited_back(self):
        entry = B10A.price_entry(state(), ORDER, SCHEDULE, POLICY)
        self.assertEqual(entry["execution_costs"]["ata_rent_charged_never_refunded"], 2_039_280)
        exit_leg = B10A.price_exit(state(900), entry["tokens_out"], SCHEDULE, POLICY)
        self.assertNotIn("ata_rent", json.dumps(exit_leg))

    def test_failed_attempts_cost_base_plus_priority_each(self):
        policy = dict(POLICY, failed_attempts=3)
        entry = B10A.price_entry(state(), ORDER, SCHEDULE, policy)
        self.assertEqual(entry["execution_costs"]["failed_attempt_cost"], 3 * (5_000 + 100_000))

    def test_one_lamport_changes_the_result(self):
        """A kernel insensitive to a lamport is not doing integer arithmetic."""
        base = B10A.price_entry(state(), ORDER, SCHEDULE, POLICY)
        moved = B10A.price_entry(
            state(), dict(ORDER, quote_lamports=ORDER["quote_lamports"] + 1), SCHEDULE, POLICY)
        self.assertNotEqual(base["lamports_out_of_wallet"], moved["lamports_out_of_wallet"])
        self.assertNotEqual(base["tokens_out"], moved["tokens_out"])


class SchemaTests(unittest.TestCase):

    def result(self):
        return B10A.simulate_round_trip(
            state(700), state(900), ORDER, SCHEDULE, POLICY,
            evidence={"source": "test-fixture"})

    def test_the_result_carries_its_schema_version_and_provenance(self):
        result = self.result()
        self.assertEqual(result["schema_version"], B10A.SCHEMA_VERSION)
        self.assertEqual(result["evidence"], {"source": "test-fixture"})
        for field in ("entry_slot", "exit_slot", "status", "fee_schedule", "cost_policy",
                      "net_lamports", "entry", "exit"):
            self.assertIn(field, result)

    def test_serialisation_is_stable_and_round_trips(self):
        result = self.result()
        first = json.dumps(result, sort_keys=True)
        self.assertEqual(first, json.dumps(json.loads(first), sort_keys=True))
        self.assertEqual(json.loads(first), result)

    def test_the_kernel_does_not_mutate_its_inputs(self):
        entry_state, exit_state = state(700), state(900)
        order, schedule, policy = dict(ORDER), dict(SCHEDULE), dict(POLICY)
        before = copy.deepcopy((entry_state, exit_state, order, schedule, policy))
        B10A.simulate_round_trip(entry_state, exit_state, order, schedule, policy)
        self.assertEqual(before, (entry_state, exit_state, order, schedule, policy))

    def test_canonical_order_is_declared_and_is_not_insertion_order(self):
        self.assertEqual(B10A.CANONICAL_ORDER,
                         ("slot", "transaction_index", "outer_index", "inner_index"))
        source = (ROOT / "scripts" / "b10a_simulator_kernel.py").read_text()
        self.assertIn("ORDER BY r.slot, r.transaction_index, r.outer_index, r.inner_index", source)
        self.assertNotIn("ORDER BY rowid", source)

    def test_every_status_is_declared(self):
        self.assertIn(self.result()["status"], B10A.STATUSES)


class GuardsFoundUntestedByMutationTests(unittest.TestCase):
    """Seven guards a mutation sweep could neuter without any existing test noticing.

    This kernel is the arithmetic every cost figure in the project rests on: B15L, B15M, B16D and
    the B19 preregistrations all call `price_entry`, `price_exit` and `curve_fees` directly rather
    than reimplementing them. A silent change to rounding or solvency here moves every priced cell
    in the same direction at once, which is the kind of error a spot-check never finds.

    The pattern in what survived is worth naming: the PROTOCOL fee's rounding was tested and the
    creator fee's and cashback's were not. Coverage followed the field somebody happened to care
    about rather than the rule they all share.
    """

    def test_every_fee_component_rounds_UP_not_just_the_protocol_fee(self):
        """`ceil_div` on each component, checked where ceil and floor actually differ.

        1 lamport at 30 bps is 0.003 lamports of fee: ceil gives 1, floor gives 0. Rounding a fee
        down is the direction that flatters every result, because it understates cost on every
        trade at once.
        """
        schedule = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 17,
                    "buyback_fee_bps": 5000}
        fees = B10A.curve_fees(1, schedule)
        self.assertEqual(fees["fee"], 1, "protocol fee must round up")
        self.assertEqual(fees["creator_fee"], 1, "creator fee must round up")
        self.assertEqual(fees["cashback"], 1, "cashback must round up")
        self.assertEqual(fees["charged_total"], 3)

    def test_the_buyback_rounds_DOWN_because_it_is_a_split_not_a_charge(self):
        """The opposite direction from the others, deliberately: it is reported, not charged."""
        schedule = {"fee_bps": 10000, "creator_fee_bps": 0, "cashback_fee_bps": 0,
                    "buyback_fee_bps": 1}
        fees = B10A.curve_fees(1, schedule)
        self.assertEqual(fees["buyback_fee_reported_not_charged"], 0,
                         "a 1-bps split of a 1-lamport fee rounds DOWN to nothing")
        # And the identity that matters: the charged total is the three CHARGED components and
        # never includes the buyback, whatever the buyback happens to be.
        big = {"fee_bps": 9000, "creator_fee_bps": 30, "cashback_fee_bps": 10,
               "buyback_fee_bps": 5000}
        charged = B10A.curve_fees(1_000_000, big)
        self.assertGreater(charged["buyback_fee_reported_not_charged"], 0,
                           "the fixture must produce a non-zero buyback or this proves nothing")
        self.assertEqual(charged["charged_total"],
                         charged["fee"] + charged["creator_fee"] + charged["cashback"])

    def test_an_exit_drawing_EXACTLY_the_reserve_is_allowed_and_one_more_is_not(self):
        """Pins the boundary, not just the direction. `>` and `>=` differ by one lamport, and an
        off-by-one here silently refuses or permits a whole class of exits."""
        entry = state()
        tokens = B10A.price_entry(entry, ORDER, SCHEDULE, POLICY)["tokens_out"]
        exact = B10A.B9I.quote_out_for_tokens_in(
            entry["virtual_quote"], entry["virtual_token"], tokens)

        allowed = B10A.price_exit(state(slot=800, real_quote=exact), tokens, SCHEDULE, POLICY)
        self.assertEqual(allowed["status"], B10A.STATUS_PRICED,
                         "an exit the reserves can exactly pay must be priced")

        with self.assertRaises(B10A.SimulationRefused):
            B10A.price_exit(state(slot=800, real_quote=exact - 1), tokens, SCHEDULE, POLICY)

    def test_non_positive_virtual_reserves_are_refused_BY_THE_ELIGIBILITY_GUARD(self):
        """Asserts the MESSAGE, because zero and minus one are refused by different guards.

        A mutation sweep showed that asserting merely "it raises" leaves the eligibility check
        mutable: minus one is caught earlier by the non-negative-integer check, and with the
        eligibility guard removed zero falls through to the curve arithmetic and fails there
        anyway. Two guards, one assertion, and the wrong one was being credited.

        A zero virtual reserve is not a small curve, it is an undefined one, and it must be named
        as such rather than surfacing as whatever the arithmetic happens to do with it.
        """
        for field in ("virtual_quote", "virtual_token"):
            with self.subTest(field=field, value=0):
                with self.assertRaises(B10A.SimulationRefused) as caught:
                    B10A.price_entry(state(**{field: 0}), ORDER, SCHEDULE, POLICY)
                self.assertIn("virtual reserves are non-positive", str(caught.exception))
                self.assertIn("curve is undefined", str(caught.exception))

            with self.subTest(field=field, value=-1):
                with self.assertRaises(B10A.SimulationRefused) as caught:
                    B10A.price_entry(state(**{field: -1}), ORDER, SCHEDULE, POLICY)
                self.assertIn("non-negative integer", str(caught.exception),
                              "a negative reserve is a type failure, caught before eligibility")

    def test_an_entry_spending_nothing_is_refused(self):
        for amount in (0, -1):
            with self.subTest(quote_lamports=amount):
                with self.assertRaises(B10A.SimulationRefused):
                    B10A.price_entry(state(), {"side": B10A.BUY, "quote_lamports": amount},
                                     SCHEDULE, POLICY)

    def test_quantities_must_be_non_negative_integers_not_floats_or_booleans(self):
        """`_positive_int` is the module's no-float rule and nothing exercised it.

        A float lamport amount is the failure this project bans everywhere else; accepting one
        here would put it at the bottom of every cost figure.
        """
        for value in (1.0, -1, True, "100", None):
            with self.subTest(value=value):
                with self.assertRaises(B10A.SimulationRefused):
                    B10A._positive_int("probe", value)

    def test_failed_attempts_are_charged_and_are_not_free(self):
        """The term B21a's external reading found named as what killed a real memecoin bot:
        "the transaction fees from retrying transactions killed it". It was untested here.

        A failed attempt pays base + priority and lands nothing, so its cost must appear in the
        execution total. Zeroing that term understates cost on exactly the trades that went worst.
        """
        base = dict(POLICY, failed_attempts=0)
        retried = dict(POLICY, failed_attempts=2)

        clean = B10A.price_entry(state(), ORDER, SCHEDULE, base)
        costly = B10A.price_entry(state(), ORDER, SCHEDULE, retried)

        expected_extra = 2 * (POLICY["base_fee_lamports"] + POLICY["priority_fee_lamports"])
        self.assertEqual(costly["lamports_out_of_wallet"]
                         - clean["lamports_out_of_wallet"], expected_extra)
        self.assertGreater(expected_extra, 0, "the fixture must actually charge something")


if __name__ == "__main__":
    unittest.main()
