"""Tests for the B13f prospective feature vector materializer.

Synthetic fixtures only. No corpus is read, no model is fitted, no window is eligible, and no
feature value or distribution is reported anywhere.

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


B13F = _load("b13f_feature_vector", "b13f_feature_vector.py")
B13D = B13F.B13D
B13A = B13F.B13A
B11B = B13F.B11B
B10B = B13F.B10B

MINT = "MintSyntheticNothingRealHere1111111111111"
CURVE = "CurveSyntheticNothingRealHere111111111111"
CREATOR = "CreatorSyntheticNothingReal11111111111111"
CREATE_USER = "CreateUserSyntheticNothingReal1111111111"
T0_USER = "TraderSyntheticNothingReal11111111111111"
WINDOW = "b13g-future-window-not-yet-named"


def at(slot, index=0, outer=0, inner=0):
    return {"slot": slot, "transaction_index": index, "outer_index": outer, "inner_index": inner}


T0 = at(500, 2, 1, 0)


def params():
    return B13F.read_preregistration()


# --------------------------------------------------------------------------------------------
# Synthetic inputs, each built through its own module's validator
# --------------------------------------------------------------------------------------------

def t0_record(**overrides):
    features = {name: index for index, name in enumerate(B11B.FEATURE_FIELDS, 1)}
    features["t0_is_launch_instruction"] = True
    features["creator_initial_buy_present"] = True
    features["is_cashback_enabled"] = False
    record = {"features": features,
              "grouping": {"mint": MINT, "bonding_curve": CURVE, "creator": CREATOR,
                           "create_user": CREATE_USER, "t0_user": T0_USER}}
    record.update(overrides)
    B11B.assert_feature_partition(record)
    return record


def accounting(**overrides):
    base = {"transactions_required": 0, "transactions_with_body": 0, "transactions_missing_body": 0,
            "transactions_missing_coordinate": 0, "system_instructions_total": 0,
            "decoded_moving": 0, "decoded_non_moving": 0, "undecodable": 0, "edges_emitted": 0,
            "moving_self_transfer": 0, "moving_without_addresses": 0, "unresolved": []}
    base.update(overrides)
    return base


def coverage(**overrides):
    base = {"first_slot": 100, "last_slot": 500, "source_population": "synthetic fixture",
            "left_truncated": False, "right_truncated": False, "complete": True,
            "provenance_sha256": "cov" * 10, "decode_accounting": accounting()}
    base.update(overrides)
    return base


def events():
    return [
        {**at(200), "kind": B13A.EVENT_LAUNCH, "mint": MINT, "bonding_curve": CURVE,
         "creator": CREATOR, "create_user": CREATE_USER, "source_sha256": "launch-200"},
        {**at(150), "kind": B13A.EVENT_LAUNCH, "mint": "OtherMint", "bonding_curve": "OtherCurve",
         "creator": CREATOR, "create_user": CREATOR, "source_sha256": "launch-150"},
        {**at(300), "kind": B13A.EVENT_TRADE, "mint": MINT, "user": CREATOR, "is_buy": True,
         "quote_lamports": 7_000, "token_units": 900, "source_sha256": "trade-300"},
        # A second buy, so buys != sells. With one of each, a swap between the two counts would be
        # invisible and the direction test would pass while measuring nothing.
        {**at(320), "kind": B13A.EVENT_TRADE, "mint": MINT, "user": CREATOR, "is_buy": True,
         "quote_lamports": 5_000, "token_units": 600, "source_sha256": "trade-320"},
        {**at(350), "kind": B13A.EVENT_TRADE, "mint": MINT, "user": CREATOR, "is_buy": False,
         "quote_lamports": 3_000, "token_units": 400, "source_sha256": "trade-350"},
        {**at(400), "kind": B13A.EVENT_TRANSFER, "from_address": "FunderSynthetic1111",
         "to_address": CREATOR, "lamports": 50_000, "source_sha256": "transfer-400"},
        {**at(420), "kind": B13A.EVENT_TRANSFER, "from_address": CREATOR,
         "to_address": "PayeeSynthetic1111", "lamports": 20_000, "source_sha256": "transfer-420"},
    ]


def history(cover=None, extra_events=()):
    subject = {"mint": MINT, "creator": CREATOR, "bonding_curve": CURVE, "user": CREATOR,
               "funding_subject_address": CREATOR}
    return B13A.build_as_of_history(list(events()) + list(extra_events), subject, T0,
                                    cover or coverage())


def token_account(name, units, role=B13D.ROLE_USER, owner=None, resolved=True):
    if resolved:
        return {"token_account": name, "mint": MINT, "decimals": 6,
                "owner": owner or f"Owner-of-{name}", "owner_status": B13D.OWNER_EXACT,
                "owner_evidence": "synthetic account record names its owner",
                "raw_units": units, "role": role, "role_evidence": f"synthetic role for {name}"}
    return {"token_account": name, "mint": MINT, "decimals": 6, "owner": None,
            "owner_status": B13D.OWNER_UNRESOLVED, "owner_evidence": None,
            "raw_units": units, "role": role, "role_evidence": f"synthetic role for {name}"}


def snapshot(accounts=None, supply=1_000_000_000, complete=True, creator_bound=True, as_of=None):
    accounts = accounts if accounts is not None else [
        token_account("curve", 400_000_000, role=B13D.ROLE_BONDING_CURVE),
        token_account("holder-creator", 300_000_000, owner=CREATOR),
        token_account("holder-2", 200_000_000),
        token_account("holder-3", 100_000_000),
    ]
    binding = ({"status": B13D.CREATOR_BINDING_EXACT, "address": CREATOR,
                "evidence": "the synthetic launch record names this creator"}
               if creator_bound else B13D.absent_creator_binding())
    return B13D.build_snapshot(
        MINT, 6, as_of or T0, "synthetic receipt provenance", accounts, supply,
        {"enumeration_complete": complete,
         "enumeration_method": "synthetic full enumeration",
         "accounts_enumerated": len(accounts),
         "source_hashes": ["s" * 64], "detail": "synthetic"},
        creator_binding=binding, source_sha256="src" * 10)


def concentration(**kwargs):
    return B13D.compute_concentration(snapshot(**kwargs))


def build(**kwargs):
    return B13F.materialize(t0_record(), kwargs.pop("history", None) or history(),
                            kwargs.pop("concentration", None) or concentration(),
                            kwargs.pop("window_id", WINDOW), enforce_eligibility=False, **kwargs)


# --------------------------------------------------------------------------------------------

class ContractPinTests(unittest.TestCase):
    """The frozen field list, and what notices when it moves."""

    def test_the_shipped_contract_matches_the_pin(self):
        self.assertTrue(B13F.assert_preregistration())

    def test_the_contract_holds_ninety_nine_unique_fields(self):
        order = params()["feature_order"]
        self.assertEqual(len(order), 99)
        self.assertEqual(len(set(order)), 99)
        self.assertEqual(params()["feature_count"], 99)

    def test_an_edited_field_list_stops_matching(self):
        edited = copy.deepcopy(params())
        edited["feature_order"] = edited["feature_order"] + ["something_new"]
        with self.assertRaisesRegex(B13F.VectorRefused, "somebody trimmed"):
            B13F.assert_preregistration(edited)

    def test_a_reordered_field_list_is_a_different_contract(self):
        """Same set, different matrix. A model trained on one and scored on the other is wrong in
        every row, and the set-equality check would not notice."""
        edited = copy.deepcopy(params())
        order = edited["feature_order"]
        edited["feature_order"] = order[:20] + [order[21], order[20]] + order[22:]
        self.assertEqual(set(edited["feature_order"]), set(order))
        self.assertNotEqual(B13F.feature_order_hash(edited["feature_order"]),
                            B13F.feature_order_hash(order))

    def test_the_first_block_must_still_be_b11bs_own_list_in_its_own_order(self):
        edited = copy.deepcopy(params())
        order = edited["feature_order"]
        edited["feature_order"] = [order[1], order[0]] + order[2:]
        with self.assertRaisesRegex(B13F.VectorRefused, "renaming or reordering a frozen contract"):
            B13F.assert_preregistration(edited, expected=B13F.preregistration_hash(edited))

    def test_a_duplicate_field_is_refused(self):
        edited = copy.deepcopy(params())
        edited["feature_order"] = edited["feature_order"] + [edited["feature_order"][0]]
        edited["feature_count"] = len(edited["feature_order"])
        with self.assertRaisesRegex(B13F.VectorRefused, "lists a field twice"):
            B13F.assert_preregistration(edited, expected=B13F.preregistration_hash(edited))

    def test_a_count_that_disagrees_with_the_list_is_refused(self):
        edited = dict(params(), feature_count=98)
        with self.assertRaisesRegex(B13F.VectorRefused, "own field count"):
            B13F.assert_preregistration(edited, expected=B13F.preregistration_hash(edited))

    def test_a_forbidden_concept_in_the_field_list_is_refused(self):
        for name in ("cluster_size", "creator_sentiment", "holder_rank", "log_supply",
                     "normalised_share", "market_cap_usd", "author_handle", "outcome_pnl",
                     "top_1_percentile", "imputed_count"):
            with self.subTest(field=name):
                edited = copy.deepcopy(params())
                edited["feature_order"] = edited["feature_order"] + [name]
                edited["feature_count"] = len(edited["feature_order"])
                with self.assertRaisesRegex(B13F.VectorRefused, "a model would weight"):
                    B13F.assert_preregistration(edited,
                                                expected=B13F.preregistration_hash(edited))

    def test_the_preregistration_was_committed_before_this_module(self):
        import subprocess

        def first_commit(path):
            found = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%H", "--", path],
                cwd=ROOT, capture_output=True, text=True).stdout.split()
            return found[-1] if found else None

        prereg = first_commit("research/B13F_FEATURE_CONTRACT_PREREGISTRATION.md")
        module = first_commit("scripts/b13f_feature_vector.py")
        self.assertTrue(prereg, "the contract must already be committed")
        if module:
            order = subprocess.run(["git", "rev-list", "--topo-order", "HEAD"],
                                   cwd=ROOT, capture_output=True, text=True).stdout.split()
            self.assertGreater(order.index(prereg), order.index(module),
                               "the contract must be an ANCESTOR of this module")


class EligibilityTests(unittest.TestCase):
    """No window is eligible, and B11a is named so the refusal explains itself."""

    def test_no_window_is_eligible(self):
        self.assertEqual(params()["eligible_windows"], [])
        with self.assertRaisesRegex(B13F.ContractIneligible, "`eligible_windows` is empty"):
            B13F.assert_eligible(WINDOW)

    def test_b11a_gets_its_own_refusal(self):
        for name in ("b11a", "B11A", "b11a-fresh-window", "B11a evaluation window"):
            with self.subTest(window=name):
                with self.assertRaisesRegex(B13F.ContractIneligible, "NO-MODEL baseline"):
                    B13F.assert_eligible(name)

    def test_the_contract_declares_itself_ineligible_for_b11a(self):
        self.assertFalse(params()["eligible_for_b11a"])
        edited = dict(params(), eligible_for_b11a=True)
        with self.assertRaisesRegex(B13F.VectorRefused, "somebody trimmed"):
            B13F.assert_eligible(WINDOW, edited)

    def test_the_b11a_refusal_does_not_consult_the_document(self):
        """A document re-pinned with `eligible_for_b11a: true` and B11a in `eligible_windows` must
        still not get a vector. The code's own refusal is independent and strictly stronger, which
        is why the document flag is not re-read at all."""
        edited = dict(params(), eligible_for_b11a=True, eligible_windows=["b11a-fresh-window"])
        with self.assertRaisesRegex(B13F.ContractIneligible, "NO-MODEL baseline"):
            B13F.assert_eligible("b11a-fresh-window", edited,
                                 expected=B13F.preregistration_hash(edited))

    def test_materializing_for_b11a_is_refused_before_anything_is_read(self):
        with self.assertRaises(B13F.ContractIneligible):
            B13F.materialize(t0_record(), history(), concentration(), "b11a")

    def test_an_ineligibility_is_distinguishable_from_a_data_problem(self):
        self.assertTrue(issubclass(B13F.ContractIneligible, B13F.VectorRefused))

    def test_the_contract_requires_a_new_training_evaluation_design(self):
        self.assertTrue(params()["requires_new_training_evaluation_design"])
        self.assertEqual(params()["transforms_fitted"], [])


class ShapeTests(unittest.TestCase):
    """The vector is exactly the frozen tuple, in the frozen order."""

    def setUp(self):
        self.vector = build()

    def test_the_feature_block_is_the_contract_in_order(self):
        self.assertEqual(list(self.vector["features"]), list(params()["feature_order"]))

    def test_a_reordered_feature_block_is_refused(self):
        vector = copy.deepcopy(self.vector)
        items = list(vector["features"].items())
        vector["features"] = dict(items[:5] + [items[6], items[5]] + items[7:])
        with self.assertRaisesRegex(B13F.VectorRefused, "the set matches and the matrix does not"):
            B13F.assert_vector(vector)

    def test_an_extra_feature_is_refused(self):
        vector = copy.deepcopy(self.vector)
        vector["features"]["smuggled_in"] = 1
        with self.assertRaisesRegex(B13F.VectorRefused, "extra and"):
            B13F.assert_vector(vector)

    def test_a_missing_feature_is_refused(self):
        vector = copy.deepcopy(self.vector)
        del vector["features"][list(vector["features"])[3]]
        with self.assertRaisesRegex(B13F.VectorRefused, "missing fields"):
            B13F.assert_vector(vector)

    def test_a_vector_built_under_a_different_order_hash_is_refused(self):
        vector = copy.deepcopy(self.vector)
        vector["feature_order_sha256"] = "0" * 64
        with self.assertRaisesRegex(B13F.VectorRefused, "wrong in every row"):
            B13F.assert_vector(vector)

    def test_a_vector_built_under_a_different_contract_hash_is_refused(self):
        vector = copy.deepcopy(self.vector)
        vector["preregistration_sha256"] = "0" * 64
        with self.assertRaisesRegex(B13F.VectorRefused, "different contract than the one in force"):
            B13F.assert_vector(vector)

    def test_an_undeclared_top_level_field_is_refused(self):
        vector = copy.deepcopy(self.vector)
        vector["notes"] = "a note"
        with self.assertRaisesRegex(B13F.VectorRefused, "undeclared fields"):
            B13F.assert_vector(vector)

    def test_the_b11b_block_keeps_b11bs_own_names_and_values(self):
        source = t0_record()
        for name in B11B.FEATURE_FIELDS:
            with self.subTest(field=name):
                self.assertEqual(self.vector["features"][name], source["features"][name])


class TypeTests(unittest.TestCase):
    """Integers, booleans and null. A float would be a number somebody rounded."""

    def test_every_shipped_value_is_an_integer_boolean_or_null(self):
        for name, value in build()["features"].items():
            with self.subTest(field=name):
                self.assertTrue(value is None or isinstance(value, (int, bool)),
                                f"{name} is {type(value).__name__}")

    def test_a_float_is_refused(self):
        with self.assertRaisesRegex(B13F.VectorRefused, "cannot silently round them"):
            B13F.assert_feature_types({"concentration_total_supply_top_1_share_numerator": 0.4})

    def test_a_value_that_is_neither_integer_boolean_nor_null_is_refused(self):
        for value in ([1, 2], {"a": 1}, (1,), {1, 2}, b"bytes"):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(B13F.VectorRefused,
                                            "integers, booleans|NO STRING MAY APPEAR"):
                    B13F.assert_feature_types({"creator_prior_launch_count_in_lookback": value})

    def test_a_string_is_refused(self):
        with self.assertRaisesRegex(B13F.VectorRefused, "NO STRING MAY APPEAR"):
            B13F.assert_feature_types({"creator_prior_launch_count_in_lookback": CREATOR})

    def test_every_share_travels_as_two_named_integers(self):
        """Never one number. A single 'share' field is what a later adapter float-rounds."""
        features = build()["features"]
        for name in params()["feature_order"]:
            if name.endswith("_share_numerator"):
                with self.subTest(field=name):
                    partner = name[: -len("_numerator")] + "_denominator"
                    self.assertIn(partner, features)
                    if features[name] is not None:
                        self.assertIsInstance(features[name], int)
                        self.assertIsInstance(features[partner], int)
                        self.assertGreater(features[partner], 0)
        self.assertFalse(any(n == "concentration_total_supply_top_1_share"
                             for n in params()["feature_order"]))


class IdentityTests(unittest.TestCase):
    """Identities group. They never predict."""

    def test_no_grouping_identity_appears_in_the_feature_block(self):
        vector = build()
        for name in params()["grouping_fields"]:
            with self.subTest(field=name):
                self.assertNotIn(name, vector["features"])

    def test_an_identity_smuggled_into_the_features_is_refused(self):
        vector = build()
        vector["features"]["mint"] = 1
        with self.assertRaisesRegex(B13F.VectorRefused, "extra and"):
            B13F.assert_vector(vector)

    def test_an_identity_hash_bucket_is_still_an_identity(self):
        """The classic dodge: hash the address to an integer and call it a feature. It passes the
        no-strings rule and is the same identity used for prediction."""
        edited = copy.deepcopy(params())
        edited["feature_order"] = edited["feature_order"] + ["creator_hash_bucket"]
        edited["feature_count"] = len(edited["feature_order"])
        vector = build()
        vector["features"]["creator_hash_bucket"] = 17
        with self.assertRaisesRegex(B13F.VectorRefused, "extra and"):
            B13F.assert_vector(vector)
        # And it would not survive the contract either, because a bucket count is chosen from a
        # distribution of identities.
        self.assertNotIn("creator_hash_bucket", params()["feature_order"])

    def test_an_identity_listed_as_a_feature_by_the_contract_is_still_refused(self):
        """Reached past the set-equality check by editing the contract and re-pinning it — the one
        way a grouping identity could arrive in a feature block that otherwise matches."""
        edited = copy.deepcopy(params())
        edited["feature_order"] = edited["feature_order"] + ["mint"]
        edited["feature_count"] = len(edited["feature_order"])
        vector = build()
        vector["features"]["mint"] = 1
        vector["feature_order_sha256"] = B13F.feature_order_hash(edited["feature_order"])
        vector["preregistration_sha256"] = B13F.preregistration_hash(edited)
        with self.assertRaisesRegex(B13F.VectorRefused, "identity used for prediction"):
            B13F.assert_vector(vector, edited, expected=B13F.preregistration_hash(edited))

    def test_the_grouping_block_carries_the_identities(self):
        vector = build()
        self.assertEqual(set(vector["grouping"]), set(params()["grouping_fields"]))
        self.assertEqual(vector["grouping"]["mint"], MINT)
        self.assertEqual(vector["grouping"]["creator"], CREATOR)


class DirectionTests(unittest.TestCase):
    """Directions are carried separately. A net figure hides the wallet that cycled."""

    def test_buys_and_sells_are_separate_fields(self):
        features = build()["features"]
        for prefix in ("user_prior", "token_prior"):
            with self.subTest(prefix=prefix):
                self.assertIn(f"{prefix}_buy_count_in_lookback", features)
                self.assertIn(f"{prefix}_sell_count_in_lookback", features)
                self.assertIn(f"{prefix}_quote_in_lamports_in_lookback", features)
                self.assertIn(f"{prefix}_quote_out_lamports_in_lookback", features)

    def test_funding_directions_are_separate_fields(self):
        features = build()["features"]
        for name in ("creator_funding_inbound_edge_count_in_lookback",
                     "creator_funding_outbound_edge_count_in_lookback",
                     "creator_funding_inbound_lamports_in_lookback",
                     "creator_funding_outbound_lamports_in_lookback"):
            with self.subTest(field=name):
                self.assertIn(name, features)

    def test_no_netted_field_exists_in_the_contract(self):
        for name in params()["feature_order"]:
            lowered = name.lower()
            with self.subTest(field=name):
                self.assertNotIn("_net_", lowered)
                self.assertFalse(lowered.endswith("_net"))

    def test_the_directional_values_come_through_unnetted(self):
        features = build()["features"]
        record = history()["sections"]
        self.assertEqual(features["user_prior_buy_count_in_lookback"],
                         record["user"]["features"]["prior_buy_count_observed"])
        self.assertEqual(features["user_prior_sell_count_in_lookback"],
                         record["user"]["features"]["prior_sell_count_observed"])
        self.assertEqual(features["creator_funding_inbound_lamports_in_lookback"],
                         record["funding"]["features"]["inbound_lamports_observed"])
        self.assertEqual(features["creator_funding_outbound_lamports_in_lookback"],
                         record["funding"]["features"]["outbound_lamports_observed"])
        self.assertNotEqual(features["creator_funding_inbound_lamports_in_lookback"],
                            features["creator_funding_outbound_lamports_in_lookback"])
        # The fixture must make every paired direction distinguishable, or a swap between two
        # equal values would pass a test that appears to check it.
        self.assertNotEqual(features["user_prior_buy_count_in_lookback"],
                            features["user_prior_sell_count_in_lookback"])
        self.assertEqual(features["user_prior_quote_in_lamports_in_lookback"],
                         record["user"]["features"]["prior_quote_in_lamports_observed"])
        self.assertEqual(features["user_prior_quote_out_lamports_in_lookback"],
                         record["user"]["features"]["prior_quote_out_lamports_observed"])
        self.assertNotEqual(features["user_prior_quote_in_lamports_in_lookback"],
                            features["user_prior_quote_out_lamports_in_lookback"])
        self.assertEqual(features["user_prior_token_in_units_in_lookback"],
                         record["user"]["features"]["prior_token_in_units_observed"])
        self.assertEqual(features["user_prior_token_out_units_in_lookback"],
                         record["user"]["features"]["prior_token_out_units_observed"])


class DenominatorTests(unittest.TestCase):
    """Both denominators, and the pairs must not be crossed."""

    def test_both_denominators_appear_for_every_share(self):
        features = build()["features"]
        for name in B13D.DENOMINATORS:
            with self.subTest(denominator=name):
                for k in B13D.TOP_K:
                    self.assertIn(f"concentration_{name}_top_{k}_share_numerator", features)
                self.assertIn(f"concentration_{name}_herfindahl_numerator", features)

    def test_each_denominator_carries_its_own_source_value(self):
        record = concentration()
        features = build()["features"]
        for name in B13D.DENOMINATORS:
            with self.subTest(denominator=name):
                block = record["shares"]["by_account"][name]
                self.assertEqual(features[f"concentration_{name}_denominator_units"],
                                 block["denominator_units"])
                self.assertEqual(features[f"concentration_{name}_top_1_share_numerator"],
                                 block["top_1"]["share"]["numerator"])

    def test_the_two_denominators_carry_different_values(self):
        """If they ever stopped differing, a swap would be invisible."""
        features = build()["features"]
        self.assertNotEqual(features["concentration_total_supply_denominator_units"],
                            features["concentration_circulating_user_denominator_units"])
        self.assertNotEqual(features["concentration_total_supply_top_1_share_numerator"],
                            features["concentration_circulating_user_top_1_share_numerator"])

    def test_a_numerator_and_denominator_are_not_interchangeable(self):
        features = build()["features"]
        for name in B13D.DENOMINATORS:
            for k in B13D.TOP_K:
                with self.subTest(denominator=name, k=k):
                    numerator = features[f"concentration_{name}_top_{k}_share_numerator"]
                    denominator = features[f"concentration_{name}_top_{k}_share_denominator"]
                    self.assertLessEqual(numerator, denominator,
                                         "a share above one means the pair is crossed")

    def test_every_concentration_value_matches_its_source_field_by_field(self):
        """Read against B13d's own record rather than recomputed, so a wrong field or a crossed
        pair shows up as a mismatch rather than as a plausible number."""
        record = concentration()
        features = build()["features"]
        for name in B13D.DENOMINATORS:
            block = record["shares"]["by_account"][name]
            with self.subTest(denominator=name):
                self.assertEqual(features[f"concentration_{name}_holder_count"],
                                 block["holder_count"])
                self.assertEqual(features[f"concentration_{name}_herfindahl_numerator"],
                                 block["herfindahl"]["numerator"])
                self.assertEqual(features[f"concentration_{name}_herfindahl_denominator"],
                                 block["herfindahl"]["denominator"])
                self.assertNotEqual(block["herfindahl"]["numerator"],
                                    block["herfindahl"]["denominator"])
                for k in B13D.TOP_K:
                    entry = block[f"top_{k}"]
                    self.assertEqual(features[f"concentration_{name}_top_{k}_units"],
                                     entry["units"])
                    if k == 1:
                        # Only the top-1 can differ from the whole denominator here: the fixture
                        # holds four accounts, so top-5 and top-10 are the entire set by
                        # construction. Distinctness is asserted where it is actually available.
                        self.assertNotEqual(entry["units"], block["denominator_units"],
                                            "the fixture must keep units and denominator distinct")
                    self.assertEqual(features[f"concentration_{name}_top_{k}_share_numerator"],
                                     entry["share"]["numerator"])
                    self.assertEqual(features[f"concentration_{name}_top_{k}_share_denominator"],
                                     entry["share"]["denominator"])

    def test_the_role_balances_and_residual_are_carried(self):
        record = concentration()
        features = build()["features"]
        for role in B13D.ROLES:
            with self.subTest(role=role):
                self.assertEqual(features[f"concentration_role_{role}_units"],
                                 record["by_role"][role]["units"])
        self.assertIn("concentration_supply_residual_units", features)
        self.assertEqual(features["concentration_supply_residual_units"],
                         record["accounting"]["supply_residual_units"])


class AvailabilityTests(unittest.TestCase):
    """Unavailable is not zero, and it says why."""

    def test_an_incomplete_history_makes_the_vector_unavailable(self):
        cover = coverage(left_truncated=True, complete=False)
        reasons = B13F.unavailability(t0_record(), history(cover), concentration(),
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V01_HISTORY_INCOMPLETE, [r["reason_code"] for r in reasons])
        with self.assertRaises(B13F.VectorRefused):
            build(history=history(cover))

    def test_unresolved_decode_evidence_gets_its_own_code(self):
        unresolved = [{"reason_code": B13A.D01_UNDECODABLE_SYSTEM_PAYLOAD,
                       "coordinate": at(300), "detail": "a payload the pinned ABI refuses"}]
        cover = coverage(complete=False, decode_accounting=accounting(
            system_instructions_total=1, undecodable=1, unresolved=unresolved))
        reasons = B13F.unavailability(t0_record(), history(cover), concentration(),
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V02_UNRESOLVED_DECODE_EVIDENCE, [r["reason_code"] for r in reasons])

    def test_an_incomplete_enumeration_makes_the_vector_unavailable(self):
        record = concentration(accounts=[token_account("only", 400_000_000)], complete=False)
        reasons = B13F.unavailability(t0_record(), history(), record,
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE,
                      [r["reason_code"] for r in reasons])

    def test_a_snapshot_from_another_instant_makes_the_vector_unavailable(self):
        record = concentration(as_of=at(499))
        reasons = B13F.unavailability(t0_record(), history(), record,
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE,
                      [r["reason_code"] for r in reasons])

    def test_an_undefined_required_denominator_makes_the_vector_unavailable(self):
        """Both denominators are required, so an undefined one is not a missing field."""
        record = concentration(accounts=[
            token_account("curve", 1_000_000_000, role=B13D.ROLE_BONDING_CURVE)])
        reasons = B13F.unavailability(t0_record(), history(), record,
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V04_REQUIRED_DENOMINATOR_UNDEFINED,
                      [r["reason_code"] for r in reasons])
        with self.assertRaises(B13F.VectorRefused):
            build(concentration=record)

    def test_evidence_after_t0_makes_the_vector_unavailable(self):
        record = concentration(as_of=at(9_999))
        reasons = B13F.unavailability(t0_record(), history(), record,
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS))
        self.assertIn(B13F.V05_EVIDENCE_AFTER_T0, [r["reason_code"] for r in reasons])

    def test_source_hash_drift_makes_the_vector_unavailable(self):
        drift = [{"name": "history", "recorded": "a" * 64, "recomputed": "b" * 64}]
        reasons = B13F.unavailability(t0_record(), history(), concentration(),
                                      tuple(T0[f] for f in B13F.COORDINATE_FIELDS), drift)
        self.assertIn(B13F.V06_SOURCE_HASH_DRIFT, [r["reason_code"] for r in reasons])

    def test_a_matching_source_hash_is_not_drift(self):
        same = [{"name": "history", "recorded": "a" * 64, "recomputed": "a" * 64}]
        self.assertEqual(B13F.unavailability(t0_record(), history(), concentration(),
                                             tuple(T0[f] for f in B13F.COORDINATE_FIELDS), same),
                         [])

    def test_an_unavailable_vector_carries_no_features_at_all(self):
        """An empty feature block would invite a caller to fill it in."""
        vector = B13F.unavailable_vector(
            WINDOW, T0, [{"reason_code": B13F.V01_HISTORY_INCOMPLETE, "detail": "short"}],
            enforce_eligibility=False)
        self.assertIsNone(vector["features"])
        self.assertFalse(vector["availability"]["available"])
        self.assertTrue(B13F.assert_vector(vector))

    def test_an_unavailable_vector_must_say_why(self):
        with self.assertRaisesRegex(B13F.VectorRefused, "tells an operator nothing"):
            B13F.unavailable_vector(WINDOW, T0, [], enforce_eligibility=False)

    def test_an_undeclared_unavailability_reason_is_refused(self):
        with self.assertRaisesRegex(B13F.VectorRefused, "is not one of"):
            B13F.unavailable_vector(WINDOW, T0, [{"reason_code": "V99_felt_wrong", "detail": "x"}],
                                    enforce_eligibility=False)

    def test_an_unavailable_vector_carrying_features_is_refused(self):
        vector = B13F.unavailable_vector(
            WINDOW, T0, [{"reason_code": B13F.V01_HISTORY_INCOMPLETE, "detail": "short"}],
            enforce_eligibility=False)
        vector["features"] = {name: 0 for name in params()["feature_order"]}
        with self.assertRaisesRegex(B13F.VectorRefused, "absence is not a row"):
            B13F.assert_vector(vector)


class NoImputationTests(unittest.TestCase):
    """A zero claims the thing did not happen. Null says we cannot say."""

    def test_an_unavailable_owner_grouping_is_null_not_zero(self):
        record = concentration(accounts=[
            token_account("curve", 400_000_000, role=B13D.ROLE_BONDING_CURVE),
            token_account("holder-creator", 300_000_000, owner=CREATOR),
            token_account("mystery", 300_000_000, resolved=False)])
        features = build(concentration=record)["features"]
        self.assertFalse(features["concentration_owner_grouping_available"])
        for name in B13D.DENOMINATORS:
            for suffix in ("holder_count", "top_1_units", "top_1_share_numerator",
                           "top_1_share_denominator"):
                with self.subTest(field=f"concentration_owner_{name}_{suffix}"):
                    self.assertIsNone(features[f"concentration_owner_{name}_{suffix}"])

    def test_an_unavailable_creator_share_is_null_not_zero(self):
        features = build(concentration=concentration(creator_bound=False))["features"]
        self.assertFalse(features["concentration_creator_share_available"])
        for name in B13D.DENOMINATORS:
            for suffix in ("units", "share_numerator", "share_denominator"):
                with self.subTest(field=f"concentration_creator_{name}_{suffix}"):
                    self.assertIsNone(features[f"concentration_creator_{name}_{suffix}"])

    def test_a_zero_substituted_for_an_unavailable_optional_field_is_refused(self):
        vector = build(concentration=concentration(creator_bound=False))
        vector["features"]["concentration_creator_total_supply_units"] = 0
        with self.assertRaisesRegex(B13F.VectorRefused, "null says we cannot say"):
            B13F.assert_vector(vector)

    def test_an_availability_flag_that_disagrees_with_its_values_is_refused(self):
        vector = build()
        self.assertTrue(vector["features"]["concentration_creator_share_available"])
        vector["features"]["concentration_creator_total_supply_units"] = None
        with self.assertRaisesRegex(B13F.VectorRefused, "availability rule and the value disagree"):
            B13F.assert_vector(vector)

    def test_an_available_optional_field_carries_its_real_value(self):
        record = concentration()
        features = build()["features"]
        self.assertTrue(features["concentration_creator_share_available"])
        self.assertEqual(features["concentration_creator_total_supply_units"],
                         record["creator"]["total_supply"]["units"])

    def test_the_contract_forbids_imputation_and_names_no_fitted_transform(self):
        self.assertFalse(params()["imputation_permitted"])
        self.assertFalse(params()["missingness_indicator_selected_from_outcomes"])
        self.assertEqual(params()["transforms_fitted"], [])


class ExclusionTests(unittest.TestCase):
    """What may never enter, checked against the thing itself rather than its name."""

    def association_ledger(self):
        return {"confidence_status": "uncalibrated_evidence_only", "links": [],
                "evidence_hash_chain_sha256": "0" * 64}

    def test_the_materializer_itself_refuses_an_input_carrying_a_ledger(self):
        """Not just the scanner in isolation: a ledger riding along on an input must stop the
        materialization, because it would never appear in the output to be caught later."""
        for label in ("t0", "history", "concentration"):
            with self.subTest(where=label):
                inputs = {"t0": t0_record(), "history": history(),
                          "concentration": concentration()}
                inputs[label] = copy.deepcopy(inputs[label])
                inputs[label]["smuggled"] = self.association_ledger()
                with self.assertRaisesRegex(B13F.VectorRefused, "ASSOCIATION EVIDENCE LEDGER"):
                    B13F.materialize(inputs["t0"], inputs["history"], inputs["concentration"],
                                     WINDOW, enforce_eligibility=False)

    def test_a_b13b_ledger_anywhere_in_an_input_is_refused(self):
        for label in ("t0", "history", "concentration"):
            with self.subTest(where=label):
                record = {"t0": t0_record(), "history": history(),
                          "concentration": concentration()}[label]
                record = copy.deepcopy(record)
                record["smuggled"] = self.association_ledger()
                with self.assertRaisesRegex(B13F.VectorRefused, "ASSOCIATION EVIDENCE LEDGER"):
                    B13F.assert_no_association_evidence(record)

    def test_a_ledger_is_recognised_by_declaration_or_by_shape(self):
        for artifact in ({"confidence_status": "uncalibrated_evidence_only"},
                         {"links": [], "evidence_hash_chain_sha256": "0" * 64}):
            with self.subTest(artifact=sorted(artifact)):
                with self.assertRaises(B13F.VectorRefused):
                    B13F.assert_no_association_evidence({"nested": {"deep": artifact}})

    def test_a_real_b13b_ledger_is_recognised(self):
        b13b = _load("b13b_association", "b13b_association.py")
        events_in = [{"slot": 100, "transaction_index": 0, "outer_index": 0, "inner_index": 0,
                      "kind": B13A.EVENT_TRANSFER, "from_address": "AAAa", "to_address": "BBBb",
                      "lamports": 5, "source_sha256": "src-1"}]
        ledger = b13b.build_association_ledger(events_in, ["AAAa", "BBBb"], at(200), coverage())
        with self.assertRaisesRegex(B13F.VectorRefused, "do not assert common control"):
            B13F.assert_no_association_evidence({"extra": ledger})

    def test_a_raw_social_string_in_a_feature_is_refused(self):
        for text in ("just aped in, this one is going to run", "https://example.invalid/post/1",
                     "@somehandle"):
            with self.subTest(text=text[:20]):
                with self.assertRaisesRegex(B13F.VectorRefused, "raw text, URLs and handles"):
                    B13F.assert_feature_types({"token_prior_trade_count_in_lookback": text})

    def test_the_contract_lists_every_excluded_source(self):
        excluded = set(params()["excluded_sources"])
        for name in ("b13b_association_evidence", "cluster_fields", "b13c_raw_text", "b13c_urls",
                     "b13c_author_identities", "sentiment", "engagement", "market_cap_transforms",
                     "ranks", "quantiles", "logarithms", "normalisation",
                     "any_value_selected_from_a_distribution"):
            with self.subTest(excluded=name):
                self.assertIn(name, excluded)

    def test_no_absolute_slot_number_is_a_feature(self):
        """A calendar index lets a model learn "later is better", which is not a property of a
        token and does not survive a different window."""
        for name in params()["feature_order"]:
            with self.subTest(field=name):
                self.assertFalse(name.endswith("_slot"), f"{name} is an absolute slot")
        self.assertIn("token_slots_since_launch", params()["feature_order"])
        self.assertIn("creator_slots_since_previous_launch_in_lookback",
                      params()["feature_order"])

    def test_no_lower_bound_bookkeeping_field_is_a_feature(self):
        """Under this contract the window must be complete, so those are constants."""
        for name in ("counts_are_lower_bounds", "actor_seen_in_window",
                     "launch_observed_in_window"):
            with self.subTest(field=name):
                self.assertNotIn(name, params()["feature_order"])


class DeterminismTests(unittest.TestCase):
    """Same inputs, same bytes, whatever order they arrived in."""

    def test_rebuilding_is_byte_identical(self):
        self.assertEqual(B10B.canonical_json(build()), B10B.canonical_json(build()))

    def test_the_vector_hash_covers_everything_but_itself(self):
        vector = build()
        self.assertEqual(vector["vector_sha256"], B13F.vector_hash(vector))

    def test_event_order_does_not_change_the_vector(self):
        forward = build()
        subject = {"mint": MINT, "creator": CREATOR, "bonding_curve": CURVE, "user": CREATOR,
                   "funding_subject_address": CREATOR}
        reversed_history = B13A.build_as_of_history(list(reversed(events())), subject, T0,
                                                    coverage())
        self.assertEqual(forward["vector_sha256"],
                         build(history=reversed_history)["vector_sha256"])

    def test_account_order_does_not_change_a_single_feature(self):
        """The substantive claim. The evidence block legitimately DIFFERS — it records the hash of
        the input actually consumed, and two differently-ordered snapshots are two different byte
        sequences. Provenance that ignored that would be provenance of something else."""
        accounts = [token_account("curve", 400_000_000, role=B13D.ROLE_BONDING_CURVE),
                    token_account("holder-creator", 300_000_000, owner=CREATOR),
                    token_account("holder-2", 200_000_000),
                    token_account("holder-3", 100_000_000)]
        forward = build(concentration=concentration(accounts=accounts))
        backward = build(concentration=concentration(accounts=list(reversed(accounts))))
        self.assertEqual(forward["features"], backward["features"])
        self.assertEqual(list(forward["features"]), list(backward["features"]))
        self.assertNotEqual(forward["evidence"]["concentration_sha256"],
                            backward["evidence"]["concentration_sha256"])

    def test_the_materializer_does_not_mutate_its_inputs(self):
        t0, hist, conc = t0_record(), history(), concentration()
        before = (B10B.canonical_json(t0), B10B.canonical_json(hist),
                  B10B.canonical_json(conc))
        B13F.materialize(t0, hist, conc, WINDOW, enforce_eligibility=False)
        self.assertEqual(before, (B10B.canonical_json(t0), B10B.canonical_json(hist),
                                  B10B.canonical_json(conc)))

    def test_changing_one_input_value_changes_the_vector_hash(self):
        base = build()
        other = concentration(accounts=[
            token_account("curve", 400_000_000, role=B13D.ROLE_BONDING_CURVE),
            token_account("holder-creator", 299_999_999, owner=CREATOR),
            token_account("holder-2", 200_000_001),
            token_account("holder-3", 100_000_000)])
        self.assertNotEqual(base["vector_sha256"], build(concentration=other)["vector_sha256"])


class ScopeTests(unittest.TestCase):
    """What this pass did not do."""

    def test_the_contract_reports_no_model_and_no_corpus(self):
        import io, contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B13F.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertFalse(contract["model_fitted"])
        self.assertFalse(contract["corpus_read"])
        self.assertFalse(contract["eligible_for_b11a"])
        self.assertEqual(contract["eligible_windows"], [])
        self.assertEqual(contract["transforms_fitted"], [])
        self.assertFalse(contract["floats_permitted"])
        self.assertFalse(contract["imputation_permitted"])

    def test_every_unavailability_code_is_declared_in_both_places(self):
        self.assertEqual(list(B13F.UNAVAILABILITY_CODES), params()["unavailability_codes"])

    def test_the_lookback_matches_b13es_frozen_value(self):
        self.assertEqual(params()["lookback_slots"], B13F.B13E.LOOKBACK_SLOTS)


if __name__ == "__main__":
    unittest.main()
