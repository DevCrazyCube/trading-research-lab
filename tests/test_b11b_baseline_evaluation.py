"""B11b — the frozen t0 feature contract, veto set, policy set and baseline metrics.

This is the layer where a backtest becomes dishonest without anyone deciding to be dishonest: a
feature that quietly reads one observation too late, an identity that becomes a predictor because
it was convenient, a seed that drifts, a threshold that gets nudged, a horizon whose semantics are
swapped between computing and reporting, or a denominator that shrinks to the rows that happened to
carry a value. Each of those has a test here, and each has a mutant.

Nothing in this file inspects a feature distribution, on any window, for any purpose.
"""
import copy
import hashlib
import importlib.util
import inspect
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One module graph: loading each by path separately would give two `ContractRefused` classes.
METRICS = _load("b11b_baseline_metrics", "b11b_baseline_metrics.py")
B11B = METRICS.B11B
B10C = METRICS.B10C
B10B = B11B.B10B
B10A = B11B.B10A
NATIVE = B11B.NATIVE_QUOTE_MINT

MINT = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CURVE = "CurveAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CREATOR = "CreatorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
STRANGER = "StrangerBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

LAUNCH_VQ, LAUNCH_VT = 30_000_000_000, 1_073_000_000_000_000
LAUNCH_RT = 793_100_000_000_000
SUPPLY = 1_000_000_000_000_000


def create_record(slot=1_000, transaction_index=7):
    return {"slot": slot, "transaction_index": transaction_index, "creator": CREATOR,
            "mint": MINT, "bonding_curve": CURVE, "user": CREATOR, "real_token": LAUNCH_RT,
            "token_total_supply": SUPPLY, "is_cashback_enabled": True}


def observation(outer_index, kind, *, slot=1_000, transaction_index=7, inner_index=-1,
                user=None, is_buy=None, quote_amount=0, token_amount=0,
                virtual_quote=LAUNCH_VQ, virtual_token=LAUNCH_VT, real_quote=0,
                real_token=LAUNCH_RT, fee_bps=95):
    record = {"slot": slot, "transaction_index": transaction_index,
              "outer_index": outer_index, "inner_index": inner_index, "kind": kind,
              "virtual_quote": virtual_quote, "virtual_token": virtual_token,
              "real_quote": real_quote, "real_token": real_token}
    if kind == "TradeEvent":
        record.update({"user": user, "is_buy": is_buy, "quote_amount": quote_amount,
                       "token_amount": token_amount, "fee_bps": fee_bps,
                       "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000})
    return record


def launch_without_dev_buy():
    create = observation(2, "CreateEvent")
    return create_record(), [create], B10B.canonical_key(create)


def launch_with_dev_buy(buyer=CREATOR):
    create = observation(2, "CreateEvent")
    trade = observation(4, "TradeEvent", user=buyer, is_buy=True,
                        quote_amount=50_000_000, token_amount=1_700_000_000_000,
                        real_quote=50_000_000, real_token=LAUNCH_RT - 1_700_000_000_000)
    return create_record(), [create, trade], B10B.canonical_key(trade)


def state(**overrides):
    base = {"virtual_quote": LAUNCH_VQ, "virtual_token": LAUNCH_VT, "real_quote": 5_000_000_000,
            "real_token": LAUNCH_RT, "quote_mint": NATIVE, "mayhem_mode": False,
            "complete": False, "slot": 1_000}
    base.update(overrides)
    return base


class FeatureContractTests(unittest.TestCase):

    def test_the_feature_list_is_pinned_exactly(self):
        """Pinned as a tuple, not merely checked for absence of strings. A `creator_hash` feature
        would pass the no-string rule while being an identity used for prediction; the only defence
        against that is that adding any field at all fails here."""
        self.assertEqual(B11B.FEATURE_FIELDS, (
            "t0_is_launch_instruction", "launch_transaction_trade_count",
            "creator_initial_buy_present", "creator_initial_buy_quote_lamports",
            "creator_initial_buy_token_units", "t0_virtual_quote_lamports",
            "t0_virtual_token_units", "t0_real_quote_lamports", "t0_real_token_units",
            "launch_real_token_units", "tokens_left_curve_units", "token_total_supply_units",
            "is_cashback_enabled", "fee_bps_observed", "creator_fee_bps_observed",
            "cashback_fee_bps_observed", "buyback_fee_bps_observed"))
        self.assertEqual(B11B.GROUPING_FIELDS,
                         ("mint", "bonding_curve", "creator", "create_user", "t0_user"))

    def test_features_and_identities_are_disjoint(self):
        self.assertEqual(set(B11B.FEATURE_FIELDS) & set(B11B.GROUPING_FIELDS), set())
        self.assertTrue(B11B.assert_disjoint_contract())

    def test_a_field_declared_as_both_a_feature_and_an_identity_is_refused(self):
        """With the shipped tuples this can never fire, so the check takes its field sets as
        arguments — a guard nobody can make fire is a guard nobody can show works."""
        with self.assertRaisesRegex(B11B.ContractRefused, "both a feature and a grouping"):
            B11B.assert_disjoint_contract(("creator", "t0_real_quote_lamports"), ("creator",))

    def test_no_string_may_appear_in_a_feature_block(self):
        record = B11B.build_t0_features(*launch_with_dev_buy())
        for name, value in record["features"].items():
            with self.subTest(name=name):
                self.assertNotIsInstance(value, str)
                self.assertTrue(value is None or isinstance(value, (int, bool)))
        leaked = copy.deepcopy(record)
        leaked["features"]["t0_is_launch_instruction"] = CREATOR
        with self.assertRaisesRegex(B11B.ContractRefused, "NO STRING MAY APPEAR"):
            B11B.assert_feature_partition(leaked)

    def test_a_non_scalar_feature_is_refused(self):
        record = B11B.build_t0_features(*launch_with_dev_buy())
        record["features"]["launch_transaction_trade_count"] = [1]
        with self.assertRaisesRegex(B11B.ContractRefused, "integers, booleans or null"):
            B11B.assert_feature_partition(record)

    def test_an_added_or_missing_feature_is_refused(self):
        record = B11B.build_t0_features(*launch_with_dev_buy())
        with self.assertRaisesRegex(B11B.ContractRefused, "feature block is"):
            B11B.assert_feature_partition(
                {**record, "features": {**record["features"], "sneaky": 1}})
        trimmed = dict(record["features"])
        trimmed.pop("is_cashback_enabled")
        with self.assertRaisesRegex(B11B.ContractRefused, "feature block is"):
            B11B.assert_feature_partition({**record, "features": trimmed})

    def test_identities_live_only_in_the_grouping_block(self):
        record = B11B.build_t0_features(*launch_with_dev_buy())
        self.assertEqual(record["grouping"]["creator"], CREATOR)
        self.assertEqual(record["grouping"]["mint"], MINT)
        blob = json.dumps(record["features"])
        for identity in (MINT, CURVE, CREATOR):
            self.assertNotIn(identity, blob)

    def test_the_split_key_is_the_r5_floor_and_is_order_stable(self):
        record = B11B.build_t0_features(*launch_with_dev_buy(buyer=STRANGER))
        self.assertEqual(B11B.split_key(record["grouping"]),
                         "|".join(sorted({CREATOR, STRANGER})))


class FeatureLeakageTests(unittest.TestCase):
    """A feature that reads one observation too late is the whole failure, in one line."""

    def test_the_materializer_has_no_parameter_a_later_observation_could_arrive_through(self):
        parameters = set(inspect.signature(B11B.build_t0_features).parameters)
        self.assertEqual(parameters, {"create", "observations", "t0_key"})
        for forbidden in ("later", "path", "marks", "horizon", "label", "outcome", "result"):
            self.assertNotIn(forbidden, parameters)

    def test_an_observation_after_t0_is_refused(self):
        create, observations, t0_key = launch_with_dev_buy()
        future = observation(6, "TradeEvent", user=STRANGER, is_buy=True,
                             quote_amount=9_000_000_000, token_amount=1)
        with self.assertRaisesRegex(B11B.ContractRefused, "is after t0"):
            B11B.build_t0_features(create, observations + [future], t0_key)

    def test_an_observation_from_another_transaction_is_refused(self):
        """t0 is always inside the launch transaction, so an earlier-looking observation from a
        different one means the path is malformed — and a malformed path is how a future state
        arrives wearing a valid coordinate."""
        create, observations, t0_key = launch_with_dev_buy()
        elsewhere = observation(0, "TradeEvent", slot=999, transaction_index=1, user=STRANGER,
                                is_buy=True)
        with self.assertRaisesRegex(B11B.ContractRefused, "not the launch transaction"):
            B11B.build_t0_features(create, observations + [elsewhere], t0_key)

    def test_the_decision_state_itself_must_be_present(self):
        create, observations, t0_key = launch_with_dev_buy()
        with self.assertRaisesRegex(B11B.ContractRefused, "no observation at t0"):
            B11B.build_t0_features(create, observations[:1], t0_key)

    def test_features_are_byte_identical_whatever_happens_afterwards(self):
        """The end-to-end statement: the materializer cannot see the future because it is never
        given it, and the record is the same object either way."""
        create, observations, t0_key = launch_with_dev_buy()
        first = B11B.build_t0_features(create, observations, t0_key)
        second = B11B.build_t0_features(create, list(observations), t0_key)
        self.assertEqual(B10B.canonical_json(first), B10B.canonical_json(second))
        self.assertEqual(first["features_sha256"], second["features_sha256"])

    def test_one_lamport_at_t0_moves_the_feature_hash(self):
        create, observations, t0_key = launch_with_dev_buy()
        base = B11B.build_t0_features(create, observations, t0_key)
        moved = copy.deepcopy(observations)
        moved[-1]["real_quote"] += 1
        self.assertNotEqual(base["features_sha256"],
                            B11B.build_t0_features(create, moved, t0_key)["features_sha256"])

    def test_the_creator_buy_feature_is_attribution_not_an_identity_predictor(self):
        """It is true when the launch buyer IS the creator and false when a stranger buys the same
        amount. That is an equality test between two t0 identities, not an identity entering the
        model: the identities themselves never reach the feature block."""
        with_creator = B11B.build_t0_features(*launch_with_dev_buy(buyer=CREATOR))
        with_stranger = B11B.build_t0_features(*launch_with_dev_buy(buyer=STRANGER))
        self.assertTrue(with_creator["features"]["creator_initial_buy_present"])
        self.assertFalse(with_stranger["features"]["creator_initial_buy_present"])
        self.assertEqual(with_creator["features"]["creator_initial_buy_quote_lamports"], 50_000_000)
        self.assertEqual(with_stranger["features"]["creator_initial_buy_quote_lamports"], 0)

    def test_a_launch_with_no_trade_publishes_null_fee_rates_rather_than_the_usual_ones(self):
        """Substituting the regime's usual basis points would assert a fee schedule the decision
        instant did not state."""
        record = B11B.build_t0_features(*launch_without_dev_buy())
        self.assertTrue(record["features"]["t0_is_launch_instruction"])
        self.assertEqual(record["features"]["launch_transaction_trade_count"], 0)
        for name in ("fee_bps_observed", "creator_fee_bps_observed",
                     "cashback_fee_bps_observed", "buyback_fee_bps_observed"):
            self.assertIsNone(record["features"][name])

    def test_tokens_left_curve_is_an_identity_not_a_chosen_transform(self):
        record = B11B.build_t0_features(*launch_with_dev_buy())
        self.assertEqual(record["features"]["tokens_left_curve_units"],
                         record["features"]["launch_real_token_units"]
                         - record["features"]["t0_real_token_units"])


class VetoTests(unittest.TestCase):

    def vetoes(self, curve_state, size=B11B.ORDER_SIZE_LAMPORTS, **kwargs):
        kwargs.setdefault("regime_in_regime", True)
        kwargs.setdefault("version_supported", True)
        return B11B.evaluate_vetoes(curve_state, size, **kwargs)

    def test_an_eligible_state_triggers_nothing(self):
        self.assertEqual(self.vetoes(state()), ())

    def test_each_veto_fires_for_its_own_condition(self):
        cases = {
            B11B.V1_NON_SOL_QUOTE: (state(quote_mint="OtherMint111"), {}),
            B11B.V2_MAYHEM_MODE: (state(mayhem_mode=True), {}),
            B11B.V3_CURVE_COMPLETE_AT_T0: (state(complete=True), {}),
            B11B.V5_MIXED_REGIME_WITHIN_CURVE: (state(), {"regime_in_regime": False}),
            B11B.V6_ORDER_EXCEEDS_REAL_TOKEN_RESERVE: (state(real_token=1_000), {}),
            B11B.V8_UNSUPPORTED_PROGRAM_VERSION: (state(), {"version_supported": False}),
        }
        for code, (curve_state, kwargs) in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, self.vetoes(curve_state, **kwargs))

    def test_an_incomplete_state_short_circuits_to_one_veto(self):
        broken = state()
        del broken["complete"]
        self.assertIn(B11B.V4_INCOMPLETE_STATE, self.vetoes(broken))

    def test_an_order_below_the_curve_resolution_is_vetoed_not_rounded(self):
        self.assertIn(B11B.V7_ORDER_BUYS_ZERO_TOKENS, self.vetoes(state(), size=1))

    def test_the_veto_codes_agree_with_what_b10a_actually_refuses(self):
        """Otherwise the veto list is documentation rather than the regime."""
        for curve_state in (state(quote_mint="OtherMint111"), state(mayhem_mode=True),
                            state(complete=True), state(real_token=1_000)):
            with self.subTest(state=curve_state["quote_mint"]):
                self.assertTrue(self.vetoes(curve_state))
                with self.assertRaises(B10A.SimulationRefused):
                    B10A.price_entry(
                        curve_state,
                        {"side": B10A.BUY, "quote_lamports": B11B.ORDER_SIZE_LAMPORTS},
                        {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                         "buyback_fee_bps": 5000},
                        {"base_fee_lamports": 5_000, "priority_fee_lamports": 100_000,
                         "tip_lamports": 0, "ata_rent_lamports": 2_039_280, "failed_attempts": 0})

    def test_an_unstated_version_check_is_refused_rather_than_assumed_passed(self):
        with self.assertRaisesRegex(B11B.ContractRefused, "version_supported"):
            B11B.evaluate_vetoes(state(), B11B.ORDER_SIZE_LAMPORTS,
                                 regime_in_regime=True, version_supported=None)

    def test_the_veto_result_is_order_stable(self):
        self.assertEqual(self.vetoes(state(quote_mint="X", mayhem_mode=True)),
                         tuple(sorted(self.vetoes(state(quote_mint="X", mayhem_mode=True)))))


class PolicyTests(unittest.TestCase):

    def features(self, present):
        record = B11B.build_t0_features(
            *(launch_with_dev_buy(CREATOR) if present else launch_with_dev_buy(STRANGER)))
        return record["features"], record["grouping"]

    def test_the_policy_set_and_the_order_size_are_pinned(self):
        self.assertEqual(B11B.POLICY_IDS,
                         ("P0_do_nothing", "P1_all_eligible_fixed_size",
                          "P2_mint_hash_random_control", "P3_creator_initial_buy_present",
                          "P4_creator_initial_buy_absent"))
        self.assertEqual(B11B.ORDER_SIZE_LAMPORTS, 100_000_000)
        self.assertEqual(B11B.PRIMARY_POLICY, "P1_all_eligible_fixed_size")
        self.assertEqual(B11B.PRIMARY_HORIZON, "h_1000_slots")
        self.assertEqual(B11B.MULTIPLICITY_FAMILY_SIZE, 16)

    def test_do_nothing_never_enters_even_with_no_vetoes(self):
        features, grouping = self.features(True)
        self.assertIsNone(B11B.decide(B11B.P0_DO_NOTHING, features, (), grouping))

    def test_every_policy_declines_a_vetoed_curve(self):
        features, grouping = self.features(True)
        for policy in B11B.POLICY_IDS:
            with self.subTest(policy=policy):
                self.assertIsNone(
                    B11B.decide(policy, features, (B11B.V2_MAYHEM_MODE,), grouping))

    def test_the_creator_buy_arms_partition_the_all_eligible_set(self):
        for present in (True, False):
            with self.subTest(present=present):
                features, grouping = self.features(present)
                arms = [B11B.decide(B11B.P3_CREATOR_BUY_PRESENT, features, (), grouping),
                        B11B.decide(B11B.P4_CREATOR_BUY_ABSENT, features, (), grouping)]
                self.assertEqual(sum(1 for a in arms if a is not None), 1)
                self.assertIsNotNone(B11B.decide(B11B.P1_ALL_ELIGIBLE, features, (), grouping))

    def test_only_the_random_control_reads_an_identity(self):
        """Every other policy must be invariant to the mint. A policy that quietly consults an
        identity is an identity used for prediction, whatever the field is called."""
        features, grouping = self.features(True)
        for policy in (B11B.P0_DO_NOTHING, B11B.P1_ALL_ELIGIBLE, B11B.P3_CREATOR_BUY_PRESENT,
                       B11B.P4_CREATOR_BUY_ABSENT):
            decisions = {B11B.decide(policy, features, (), dict(grouping, mint=f"Mint{i}"))
                         for i in range(40)}
            with self.subTest(policy=policy):
                self.assertEqual(len(decisions), 1)
        control = {B11B.decide(B11B.P2_RANDOM_CONTROL, features, (), dict(grouping, mint=f"M{i}"))
                   for i in range(40)}
        self.assertEqual(len(control), 2, "the control must actually vary with the mint")

    def test_the_random_control_seed_and_rate_are_pinned_against_drift(self):
        """A seed that drifts silently reproduces a different control, and the old numbers stop
        meaning anything. These expectations are computed from the frozen seed."""
        self.assertEqual(B11B.RANDOM_CONTROL_SEED, "b11b-random-control-2026-08-02")
        self.assertEqual((B11B.RANDOM_CONTROL_NUMERATOR, B11B.RANDOM_CONTROL_DENOMINATOR), (1, 2))
        pinned = {mint: B11B.mint_hash_selected(mint)
                  for mint in ("MintA", "MintB", "MintC", "MintD", "MintE")}
        expected = {}
        for mint in pinned:
            digest = hashlib.sha256(
                ("b11b-random-control-2026-08-02" + mint).encode()).hexdigest()
            expected[mint] = int(digest, 16) % 2 < 1
        self.assertEqual(pinned, expected)
        drifted = {mint: B11B.mint_hash_selected(mint, seed="other-seed") for mint in pinned}
        self.assertNotEqual(pinned, drifted)

    def test_the_control_is_deterministic_across_calls(self):
        self.assertEqual([B11B.mint_hash_selected(MINT) for _ in range(5)],
                         [B11B.mint_hash_selected(MINT)] * 5)

    def test_an_unknown_policy_is_refused(self):
        features, grouping = self.features(True)
        with self.assertRaisesRegex(B11B.ContractRefused, "unknown policy"):
            B11B.decide("P9_have_a_hunch", features, (), grouping)

    def test_the_policy_invariants_are_enforced(self):
        entries = {B11B.P0_DO_NOTHING: set(), B11B.P1_ALL_ELIGIBLE: {"a", "b", "c"},
                   B11B.P2_RANDOM_CONTROL: {"a"}, B11B.P3_CREATOR_BUY_PRESENT: {"a", "b"},
                   B11B.P4_CREATOR_BUY_ABSENT: {"c"}}
        self.assertTrue(B11B.assert_policy_invariants(entries))
        with self.assertRaisesRegex(B11B.ContractRefused, "do-nothing policy entered"):
            B11B.assert_policy_invariants({**entries, B11B.P0_DO_NOTHING: {"a"}})
        with self.assertRaisesRegex(B11B.ContractRefused, "do not partition"):
            B11B.assert_policy_invariants({**entries, B11B.P4_CREATOR_BUY_ABSENT: set()})
        with self.assertRaisesRegex(B11B.ContractRefused, "both arms"):
            B11B.assert_policy_invariants(
                {**entries, B11B.P3_CREATOR_BUY_PRESENT: {"a", "b", "c"}})
        with self.assertRaisesRegex(B11B.ContractRefused, "random control entered"):
            B11B.assert_policy_invariants({**entries, B11B.P2_RANDOM_CONTROL: {"a", "z"}})

    def test_no_adaptive_machinery_appears_in_the_module(self):
        """No fitted threshold, no ranking, no quantile. A baseline with a tuned parameter is not
        a baseline."""
        source = (ROOT / "scripts" / "b11b_t0_features.py").read_text().lower()
        for forbidden in ("quantile", "percentile", "top_k", "topk", "argsort", "\n    fit(",
                          "def fit", "sklearn", "numpy", "np."):
            self.assertNotIn(forbidden, source)


class HorizonSemanticsTests(unittest.TestCase):

    def test_the_two_semantics_are_named_and_different(self):
        self.assertEqual(B11B.LABEL_SEMANTICS, "b10c_state_in_force_at_or_before_horizon")
        self.assertEqual(B11B.FORBIDDEN_LABEL_SEMANTICS,
                         "b10b_first_reachable_exit_at_or_after_horizon")
        self.assertNotEqual(B11B.LABEL_SEMANTICS, B11B.FORBIDDEN_LABEL_SEMANTICS)

    def test_evaluating_under_the_wrong_semantics_is_refused(self):
        with self.assertRaisesRegex(METRICS.ContractRefused, "label semantics"):
            METRICS.evaluate([], policy_id=B11B.P1_ALL_ELIGIBLE, horizon_name="h_1000_slots",
                             entered_mints=set(), split_keys={}, cohort_curves=0,
                             label_semantics=B11B.FORBIDDEN_LABEL_SEMANTICS)

    def test_every_metric_record_names_the_semantics_it_used(self):
        metrics = METRICS.evaluate([], policy_id=B11B.P1_ALL_ELIGIBLE,
                                   horizon_name="h_1000_slots", entered_mints=set(),
                                   split_keys={}, cohort_curves=0)
        self.assertEqual(metrics["label_semantics"], B11B.LABEL_SEMANTICS)

    def test_a_row_from_another_horizon_is_refused(self):
        row = label_row("m1", B10C.OUTCOME_MARKED, horizon="h_10000_slots")
        with self.assertRaisesRegex(METRICS.ContractRefused, "passed to a"):
            METRICS.evaluate([row], policy_id=B11B.P1_ALL_ELIGIBLE,
                             horizon_name="h_1000_slots", entered_mints={"m1"},
                             split_keys={"m1": "g1"}, cohort_curves=1)


def label_row(mint, status, *, horizon="h_1000_slots", net=0, outlay=103_394_280,
              capital=None, drawdown=None, liquidity=B10B.L0_FULL):
    capital = outlay if capital is None else capital
    row = {field: None for field in B10C.DECISION_FIELDS + B10C.OUTCOME_FIELDS}
    row.update({"mint": mint, "horizon_name": horizon, "outcome_status": status,
                "entry_outlay_lamports": None, "capital_denominator_lamports": None,
                "realizable_net_lamports": None, "net_return_numerator": None,
                "net_return_denominator": None, "liquidity_state": None,
                "max_drawdown_ratio_numerator": None, "max_drawdown_ratio_denominator": None})
    if status != B10C.OUTCOME_NO_DECISION:
        row["entry_outlay_lamports"] = outlay
    if status == B10C.OUTCOME_MARKED:
        row.update({"capital_denominator_lamports": capital,
                    "realizable_net_lamports": outlay + net,
                    "net_return_numerator": net, "net_return_denominator": capital,
                    "liquidity_state": liquidity})
        if drawdown is not None:
            row["max_drawdown_ratio_numerator"] = drawdown[0]
            row["max_drawdown_ratio_denominator"] = drawdown[1]
    return row


class RationalTests(unittest.TestCase):

    def test_reduction_and_sign_are_canonical(self):
        self.assertEqual(METRICS.reduce_rational(4, 8), (1, 2))
        self.assertEqual(METRICS.reduce_rational(-4, 8), (-1, 2))
        self.assertEqual(METRICS.reduce_rational(4, -8), (-1, 2))
        self.assertEqual(METRICS.reduce_rational(0, 5), (0, 1))
        with self.assertRaisesRegex(METRICS.ContractRefused, "zero denominator"):
            METRICS.reduce_rational(1, 0)

    def test_ordering_is_cross_multiplication_and_never_a_float(self):
        self.assertTrue(METRICS.rational_less((1, 3), (1, 2)))
        self.assertFalse(METRICS.rational_less((1, 2), (1, 3)))
        huge = (10 ** 40 + 1, 10 ** 40)
        self.assertTrue(METRICS.rational_less((1, 1), huge),
                        "a float comparison would call these equal")

    def test_the_median_is_exact_for_odd_and_even_sets(self):
        self.assertEqual(METRICS.rational_median([(1, 2), (1, 3), (1, 4)]), (1, 3))
        self.assertEqual(METRICS.rational_median([(1, 2), (1, 4)]), (3, 8))
        self.assertIsNone(METRICS.rational_median([]))


class MetricTests(unittest.TestCase):

    def rows(self):
        return [
            label_row("m1", B10C.OUTCOME_MARKED, net=10_000_000, drawdown=(1, 4)),
            label_row("m2", B10C.OUTCOME_MARKED, net=-20_000_000, drawdown=(1, 2),
                      liquidity=B10B.L2_SIZE_CONSTRAINED),
            label_row("m3", B10C.OUTCOME_RIGHT_CENSORED),
            label_row("m4", B10C.OUTCOME_STRUCTURAL_UNAVAILABLE),
            label_row("m5", B10C.OUTCOME_NO_OBSERVED_STATE),
            label_row("m6", B10C.OUTCOME_NO_DECISION),
            label_row("m7", B10C.OUTCOME_MARKED, net=5_000_000),
        ]

    def evaluate(self, entered=None, rows=None):
        rows = self.rows() if rows is None else rows
        entered = {"m1", "m2", "m3", "m4", "m5", "m7"} if entered is None else entered
        return METRICS.evaluate(
            rows, policy_id=B11B.P1_ALL_ELIGIBLE, horizon_name="h_1000_slots",
            entered_mints=entered,
            split_keys={m: ("g1" if m in {"m1", "m2"} else f"g_{m}") for m in
                        {"m1", "m2", "m3", "m4", "m5", "m6", "m7"}},
            cohort_curves=len(rows))

    def test_the_census_accounts_for_every_curve(self):
        metrics = self.evaluate()
        self.assertEqual(sum(metrics["disposition_census"].values()), 7)
        self.assertEqual(metrics["disposition_census"], {
            METRICS.BUCKET_MARKED: 3, METRICS.BUCKET_RIGHT_CENSORED: 1,
            METRICS.BUCKET_STRUCTURAL: 1, METRICS.BUCKET_NO_OBSERVED: 1,
            METRICS.BUCKET_NO_DECISION: 1, METRICS.BUCKET_NOT_ENTERED: 0})
        self.assertTrue(METRICS.assert_denominator_preserved(metrics))

    def test_a_curve_the_policy_declined_is_counted_not_dropped(self):
        """`not_entered_by_policy` is separate from the pipeline's own `no_decision`: merging them
        would hide which of the two a result depends on."""
        metrics = self.evaluate(entered={"m1", "m7"})
        self.assertEqual(metrics["disposition_census"][METRICS.BUCKET_NOT_ENTERED], 4)
        self.assertEqual(sum(metrics["disposition_census"].values()), 7)
        self.assertEqual(metrics["cohort_curves"], 7)

    def test_a_filtered_cohort_is_refused(self):
        metrics = self.evaluate()
        metrics["disposition_census"][METRICS.BUCKET_NO_DECISION] = 0
        with self.assertRaisesRegex(METRICS.ContractRefused, "flatters itself"):
            METRICS.assert_denominator_preserved(metrics)

    def test_the_headline_return_is_computed_over_marked_rows_only(self):
        metrics = self.evaluate()
        net = 10_000_000 - 20_000_000 + 5_000_000
        capital = 103_394_280 * 3
        self.assertEqual(metrics["total_net_lamports"], net)
        self.assertEqual(tuple(metrics["capital_weighted_net_return"]),
                         METRICS.reduce_rational(net, capital))

    def test_the_worst_case_bound_is_strictly_worse_and_is_labelled_a_bound(self):
        metrics = self.evaluate()
        self.assertTrue(METRICS.rational_less(
            tuple(metrics["worst_case_lower_bound_return"]),
            tuple(metrics["capital_weighted_net_return"])))
        self.assertIn("BOUND", metrics["worst_case_lower_bound_note"])
        self.assertIn("No upper bound", metrics["worst_case_lower_bound_note"])

    def test_censored_rows_never_enter_the_headline_as_losses(self):
        metrics = self.evaluate()
        self.assertTrue(METRICS.assert_no_censored_as_loss(metrics, self.rows()))
        cheated = copy.deepcopy(metrics)
        cheated["capital_weighted_net_return"] = cheated["worst_case_lower_bound_return"]
        with self.assertRaisesRegex(METRICS.ContractRefused, "leaked into the headline"):
            METRICS.assert_no_censored_as_loss(cheated, self.rows())

    def test_deployed_capital_counts_every_entered_position_not_only_the_observed_ones(self):
        metrics = self.evaluate()
        self.assertEqual(metrics["deployed_capital_lamports"], 103_394_280 * 6)
        self.assertEqual(metrics["entered_positions"], 6)

    def test_robust_summaries_and_capacity_are_reported(self):
        metrics = self.evaluate()
        self.assertEqual(tuple(metrics["median_position_return"]),
                         METRICS.reduce_rational(5_000_000, 103_394_280))
        self.assertEqual(tuple(metrics["median_position_max_drawdown"]), (3, 8))
        self.assertEqual(tuple(metrics["worst_position_max_drawdown"]), (1, 2))
        self.assertEqual(metrics["capacity_positions_fully_executable"], 2)
        self.assertEqual(metrics["capacity_positions_size_constrained"], 1)

    def test_grouped_uncertainty_is_a_jackknife_over_creator_union_user(self):
        grouped = self.evaluate()["grouped_uncertainty"]
        self.assertEqual(grouped["group_count"], 2)
        self.assertEqual(tuple(grouped["largest_group_position_share"]), (2, 3))
        self.assertTrue(METRICS.rational_less(
            tuple(grouped["leave_one_group_out_min_return"]),
            tuple(grouped["leave_one_group_out_max_return"])))

    def test_a_position_without_a_split_key_is_refused_rather_than_dropped(self):
        with self.assertRaisesRegex(METRICS.ContractRefused, "split key"):
            METRICS.evaluate(self.rows(), policy_id=B11B.P1_ALL_ELIGIBLE,
                             horizon_name="h_1000_slots", entered_mints={"m1"},
                             split_keys={}, cohort_curves=7)

    def test_an_empty_book_produces_nulls_rather_than_zeros(self):
        metrics = self.evaluate(entered=set())
        self.assertIsNone(metrics["capital_weighted_net_return"])
        self.assertIsNone(metrics["median_position_return"])
        self.assertEqual(metrics["deployed_capital_lamports"], 0)
        self.assertEqual(metrics["disposition_census"][METRICS.BUCKET_NOT_ENTERED], 6)

    def test_no_float_appears_anywhere_in_a_metric_record(self):
        blob = B10B.canonical_json(self.evaluate())

        def walk(node, where):
            if isinstance(node, float):
                self.fail(f"a float reached the metrics at {where}: {node!r}")
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{where}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{where}[{index}]")

        walk(json.loads(blob), "metrics")

    def test_the_record_is_deterministic(self):
        self.assertEqual(self.evaluate()["metrics_sha256"], self.evaluate()["metrics_sha256"])

    def test_exactly_one_cell_may_be_primary(self):
        primary = self.evaluate()
        secondary = METRICS.evaluate(
            [], policy_id=B11B.P2_RANDOM_CONTROL, horizon_name="h_1000_slots",
            entered_mints=set(), split_keys={}, cohort_curves=0)
        table = METRICS.family_table([primary, secondary])
        self.assertEqual(table["family_size_declared"], 16)
        self.assertEqual(table["primary"]["policy_id"], B11B.PRIMARY_POLICY)
        self.assertTrue(table["secondary_may_not_be_promoted"])
        self.assertTrue(table["no_test_performed"])
        with self.assertRaisesRegex(METRICS.ContractRefused, "claim to be primary"):
            METRICS.family_table([primary, dict(secondary, is_primary=True)])


class PreregistrationTests(unittest.TestCase):

    def test_both_hashes_match_the_committed_document(self):
        raw = B11B.PREREGISTRATION_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), B11B.PREREGISTRATION_FILE_SHA256)
        canonical = B10B.canonical_json(json.loads(raw)).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         B11B.PREREGISTRATION_CANONICAL_SHA256)

    def test_a_reformatted_document_fails_the_file_hash(self):
        import tempfile
        document = json.loads(B11B.PREREGISTRATION_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "reformatted.json"
            path.write_text(json.dumps(document, indent=4) + "\n")
            with self.assertRaisesRegex(B11B.ContractRefused, "file hash"):
                B11B.load_preregistration(path)

    def test_the_document_declares_no_model_and_no_fitted_threshold(self):
        document = B11B.load_preregistration()
        self.assertEqual(document["model"]["model_family"], "none")
        self.assertEqual(document["model"]["learned_parameters"], 0)
        self.assertEqual(document["model"]["fitted_thresholds"], 0)
        self.assertTrue(document["committed_before_any_feature_materialization"])
        self.assertFalse(document["b11a_composition_inspected"])

    def test_the_code_and_the_document_agree_on_every_frozen_choice(self):
        """A preregistration the implementation quietly diverges from is not a preregistration."""
        document = B11B.load_preregistration()
        self.assertEqual([f["name"] for f in document["feature_contract"]["features"]],
                         list(B11B.FEATURE_FIELDS))
        self.assertEqual(
            document["feature_contract"]["grouping_identities_never_features"]["fields"],
            list(B11B.GROUPING_FIELDS))
        self.assertEqual([v["code"] for v in document["hard_vetoes"]["vetoes"]],
                         list(B11B.VETO_CODES))
        self.assertEqual([p["id"] for p in document["policies"]["set"]], list(B11B.POLICY_IDS))
        self.assertEqual(document["policies"]["order_size_lamports"], B11B.ORDER_SIZE_LAMPORTS)
        control = next(p for p in document["policies"]["set"] if p["id"] == B11B.P2_RANDOM_CONTROL)
        self.assertEqual(control["seed"], B11B.RANDOM_CONTROL_SEED)
        self.assertEqual((control["rate_numerator"], control["rate_denominator"]),
                         (B11B.RANDOM_CONTROL_NUMERATOR, B11B.RANDOM_CONTROL_DENOMINATOR))
        self.assertEqual(document["primary_result"]["policy"], B11B.PRIMARY_POLICY)
        self.assertEqual(document["primary_result"]["horizon"], B11B.PRIMARY_HORIZON)
        self.assertEqual(document["primary_result"]["metric"], B11B.PRIMARY_METRIC)
        self.assertEqual(document["multiplicity"]["family_size"], B11B.MULTIPLICITY_FAMILY_SIZE)
        self.assertEqual([h["name"] for h in document["horizons"]["set"]],
                         ["h_1000_slots", "h_10000_slots", "h_10_observations",
                          "administrative_window_end"])

    def test_the_horizons_are_the_b10c_ones_unchanged(self):
        plumbing = json.loads(
            (ROOT / "research" / "B10C_PREREGISTRATION_PLUMBING.json").read_text())
        frozen = B11B.load_preregistration()["horizons"]["set"]
        self.assertEqual([{k: v for k, v in h.items()} for h in frozen], plumbing["horizons"])

    def test_it_points_at_the_b11a_window_and_claims_no_inspection_of_it(self):
        document = B11B.load_preregistration()
        window = document["applies_to_window"]
        self.assertEqual(window["file_sha256"], B11B.B11A_PREREGISTRATION_FILE_SHA256)
        self.assertEqual(window["launch_window_first_slot_inclusive"], 435_569_150)
        self.assertEqual(window["observation_cutoff_slot_inclusive"], 437_211_659)


class UnlockGateTests(unittest.TestCase):

    def evidence(self, **overrides):
        base = {
            "b11b_prereg_file_sha256": B11B.PREREGISTRATION_FILE_SHA256,
            "b11b_prereg_canonical_sha256": B11B.PREREGISTRATION_CANONICAL_SHA256,
            "recorded_in_decisions": True,
            "model_family": "none",
            "collection_complete": True,
            "gates_passed": True,
            "b11a_prereg_file_sha256": B11B.B11A_PREREGISTRATION_FILE_SHA256,
            "decisions_unlock_entry": "2026-XX-XX unlock",
        }
        base.update(overrides)
        return base

    def test_complete_evidence_unlocks(self):
        self.assertTrue(B11B.assert_unlock_evidence(self.evidence()))

    def test_each_requirement_can_independently_keep_results_locked(self):
        cases = {
            "U1": {"recorded_in_decisions": False},
            "U2": {"model_family": "logistic_regression"},
            "U3": {"gates_passed": False},
            "U4": {"decisions_unlock_entry": ""},
        }
        for identifier, override in cases.items():
            with self.subTest(requirement=identifier):
                report = B11B.evaluate_unlock_evidence(self.evidence(**override))
                self.assertFalse(report["unlocked"])
                self.assertIn(identifier, report["unmet"])
                with self.assertRaisesRegex(B11B.ContractRefused, identifier):
                    B11B.assert_unlock_evidence(self.evidence(**override))

    def test_u5_notices_an_edited_contract(self):
        import tempfile
        document = json.loads(B11B.PREREGISTRATION_PATH.read_text())
        document["policies"]["order_size_lamports"] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "edited.json"
            path.write_text(json.dumps(document))
            report = B11B.evaluate_unlock_evidence(self.evidence(), path)
            self.assertIn("U5", report["unmet"])

    def test_a_model_unlocks_only_with_its_artifact_hash_frozen(self):
        locked = B11B.evaluate_unlock_evidence(self.evidence(model_family="gbm"))
        self.assertIn("U2", locked["unmet"])
        unlocked = B11B.evaluate_unlock_evidence(
            self.evidence(model_family="gbm", model_artifact_sha256="a" * 64))
        self.assertNotIn("U2", unlocked["unmet"])

    def test_the_evaluation_only_rule_travels_with_the_report(self):
        rule = B11B.evaluate_unlock_evidence(self.evidence())["evaluation_only_rule"]
        self.assertIn("evaluation data", rule)
        self.assertIn("may change in response", rule)
        self.assertIn("new preregistration AND a new window", rule)
        self.assertIn("burned", rule)

    def test_b11a_results_are_still_locked_today(self):
        """Nothing has been collected, so the gate must refuse on U3 whatever else is true."""
        report = B11B.evaluate_unlock_evidence(
            self.evidence(collection_complete=False, gates_passed=False))
        self.assertFalse(report["unlocked"])
        self.assertIn("U3", report["unmet"])

    def test_b10c_enum_is_still_locked(self):
        self.assertEqual(B10C.ALLOWED_WINDOW_STATUS, ("burned_development",))


class RealCorpusTests(unittest.TestCase):
    """Against the burned-development corpus when present. No distribution is ever inspected."""

    CORPUS = ROOT / "research" / "b10b_observed_paths.sqlite"
    ARTIFACT = ROOT / "research" / "b9d_transaction_bodies.sqlite"

    def test_t0_is_inside_the_launch_transaction_for_every_curve(self):
        """The proof that makes the creator-initial-buy feature a t0 fact rather than a peek."""
        if not self.CORPUS.exists():
            self.skipTest("corpus not built")
        import sqlite3
        B10BD = _load("b10b_path_dataset", "b10b_path_dataset.py")
        database = sqlite3.connect(f"file:{self.CORPUS}?mode=ro", uri=True)
        try:
            for (curve,) in database.execute(
                    "SELECT bonding_curve FROM curve ORDER BY bonding_curve LIMIT 300"):
                states = B10BD.load_states(database, curve)
                create = next(s for s in states if s["kind"] == B10BD.KIND_CREATE)
                t0 = states[B10BD.select_t0(states)]
                self.assertEqual((t0["slot"], t0["transaction_index"]),
                                 (create["slot"], create["transaction_index"]), curve)
        finally:
            database.close()


class InputValidationFoundUntestedByMutationTests(unittest.TestCase):
    """Five guards a mutation sweep could neuter without any existing test noticing.

    Worth stating what the sweep did NOT find, because it is the more important half: every
    LEAKAGE guard was killed. The after-t0 refusal, the launch-transaction rule, the requirement
    that t0 itself be present, the no-strings rule and the disjoint feature/identity contract are
    all covered. What was uncovered is the input validation around them — and a validator nobody
    tests is how a malformed input reaches a guard that assumed it was well-formed.
    """

    def test_an_empty_observation_list_is_refused_BY_ITS_OWN_GUARD(self):
        """Asserts the MESSAGE, because asserting only the refusal tests a different guard.

        With no observations the loop body never runs, so `seen_t0` stays False and the
        decision-state check refuses anyway. A test asserting merely "it raises" therefore passes
        with the empty-list guard deleted — a mutation sweep showed exactly that, and it is section
        7's "a test killed by a different guard than the one it names" appearing in a test written
        the same day the lesson was recorded.

        The two refusals are not interchangeable. "no observations at all" and "observations exist
        but none is at t0" are different faults with different fixes, and the message is the whole
        difference between them.
        """
        with self.assertRaises(B11B.ContractRefused) as caught:
            B11B.build_t0_features(create_record(), [], (1_000, 7, 0, -1))
        self.assertIn("no observations at or before t0", str(caught.exception))
        self.assertNotIn("no observation at t0", str(caught.exception))

    def test_create_must_be_a_mapping(self):
        for bad in ("a string", ["a", "list"], 7, None):
            with self.subTest(create=type(bad).__name__):
                with self.assertRaises(B11B.ContractRefused):
                    B11B.build_t0_features(bad, [observation(0, "CreateEvent")], (1_000, 7, 0, -1))

    def test_observations_must_be_a_sequence_not_a_string_or_mapping(self):
        """A string is iterable, so without this it would be walked CHARACTER BY CHARACTER and
        each character asked for its canonical key — a failure far from its cause."""
        for bad in ("CreateEvent", {"kind": "CreateEvent"}, b"bytes"):
            with self.subTest(observations=type(bad).__name__):
                with self.assertRaises(B11B.ContractRefused):
                    B11B.build_t0_features(create_record(), bad, (1_000, 7, 0, -1))

    def test_a_missing_required_field_is_refused_by_name(self):
        for field in ("slot", "transaction_index", "creator", "real_token", "token_total_supply"):
            with self.subTest(missing=field):
                create = {k: v for k, v in create_record().items() if k != field}
                with self.assertRaises(B11B.ContractRefused) as caught:
                    B11B.build_t0_features(create, [observation(0, "CreateEvent")],
                                           (1_000, 7, 0, -1))
                self.assertIn(field, str(caught.exception),
                              "the refusal must name the absent field, or it cannot be fixed")

    def test_the_grouping_block_must_match_the_contract(self):
        """The feature side was covered and the identity side was not, which is the asymmetry
        that matters: a grouping block quietly gaining or losing a field changes what is treated
        as an identity rather than a predictor."""
        record = B11B.build_t0_features(create_record(), [observation(0, "CreateEvent")],
                                        (1_000, 7, 0, -1))
        B11B.assert_feature_partition(record)

        extra = dict(record, grouping=dict(record["grouping"], invented_identity="x"))
        with self.assertRaises(B11B.ContractRefused):
            B11B.assert_feature_partition(extra)

        short = dict(record, grouping={k: v for k, v in record["grouping"].items() if k != "mint"})
        with self.assertRaises(B11B.ContractRefused):
            B11B.assert_feature_partition(short)


class FloatSafeMagnitudeTests(unittest.TestCase):
    """Guard a conclusion that currently rests on a regime, not on the code.

    `b14c_model_engine` computes decision-tree split thresholds as `(low + high) / 2` in FLOAT.
    That was checked on 2026-08-07 and is not a defect **today**: the dangerous failure — a midpoint
    rounding up to `high`, emptying one side of a split that the sample counts said was non-empty —
    never occurs, and the only divergence is the midpoint landing exactly on `low`, which still
    separates the two training points and differs only for unseen values strictly between them.

    That divergence needs a feature value above **2**52 = 4,503,599,627,370,496**, where float64's
    53-bit mantissa stops representing consecutive integers.

    THE MARGIN IS 4.5x AND IT IS NOT GUARANTEED BY ANYTHING IN THIS REPOSITORY. Six of the
    seventeen frozen FEATURE_FIELDS are token-unit denominated, and they sit at ~1e15 = 2**49.8
    ONLY because Pump's standard supply is 1e9 at 6 decimals. A token with ten times the standard
    supply crosses the line. Nothing in the contract, the builder or the model bounds it.

    So this exists rather than a note. An answered-no is a stopping claim and nobody re-tests a
    stopping claim; a test fails. Raised by the claude seat, who was right that the close needed a
    guard rather than a memory.
    """

    FLOAT_EXACT_INTEGER_LIMIT = 2 ** 52

    def features_for(self, supply):
        """The FEATURE BLOCK, not the whole record. The first version of this returned the record,
        whose top-level values are dicts and strings, so the magnitude check below skipped every
        one and passed while asserting nothing — a check that cannot fire, inside the guard written
        against that very failure. The non-vacuity assertion is there so it cannot recur."""
        create = dict(create_record(), token_total_supply=supply)
        observations = [observation(0, "CreateEvent")]
        record = B11B.build_t0_features(create, observations, (1_000, 7, 0, -1))
        return record["features"]

    def test_every_standard_regime_feature_stays_below_the_float_exact_limit(self):
        features = self.features_for(SUPPLY)
        checked = []
        for name, value in sorted(features.items()):
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            checked.append(name)
            with self.subTest(field=name):
                self.assertLess(abs(value), self.FLOAT_EXACT_INTEGER_LIMIT,
                                f"{name} = {value:,} has crossed 2**52; b14c's float split "
                                "thresholds are no longer safe by magnitude and that close "
                                "must be re-opened")
        self.assertGreaterEqual(len(checked), 6,
                                "this must actually inspect the integer features, not skip them")

    def test_the_margin_is_a_regime_property_and_a_larger_supply_crosses_the_line(self):
        """Pins WHERE the line is, so the guard above is not merely 'stay small'.

        If this ever stops crossing, either the arithmetic changed or the boundary moved, and
        either way the conclusion above needs re-deriving rather than inheriting.
        """
        standard = self.features_for(SUPPLY)["token_total_supply_units"]
        self.assertLess(standard, self.FLOAT_EXACT_INTEGER_LIMIT)
        self.assertGreater(standard * 10, self.FLOAT_EXACT_INTEGER_LIMIT,
                           "a ten-times-standard supply must cross 2**52, or the margin is "
                           "wider than the finding assumed and the docstring is stale")

    def test_the_token_denominated_fields_are_the_ones_at_risk(self):
        """Named explicitly, because the count was reported as four and is six."""
        token_fields = [f for f in B11B.FEATURE_FIELDS if "token" in f and "units" in f]
        self.assertEqual(len(token_fields), 6)
        features = self.features_for(SUPPLY)
        for name in token_fields:
            with self.subTest(field=name):
                self.assertIn(name, features)


if __name__ == "__main__":
    unittest.main()
