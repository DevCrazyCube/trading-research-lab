#!/usr/bin/env python3
"""B11b — the t0 feature contract, the hard vetoes, the policy set, and the unlock gate.

Offline, read-only, no network. Pure library: no model fitting, no server, no UI, no signal, no
live RPC, no signing. Freeze: `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`, committed
alone before this module was written.

WHAT THIS IS
============

A baseline/pipeline evaluation has no learned component: `model_family: none`, zero fitted
thresholds. Its job is to establish what the machinery produces with **no selection in it**, so that
a future model has something honest to be measured against. Everything here is therefore a frozen
rule rather than a parameter, and the module's whole design is about making that checkable.

THE ONE RULE THAT DOES MOST OF THE WORK
=======================================

**Every feature value is an integer, a boolean, or None. No string may appear in a feature block.**

That is the structural form of "identities are for grouping, never for prediction". A mint, a
creator, a URI or a symbol cannot enter a model that only accepts numbers, and — the part that
matters — the rule is checkable *without anyone having to notice which strings happen to be
identities*. A rule that requires vigilance is a rule that fails the week nobody is looking.

THREE THINGS THIS MODULE REFUSES TO DO
======================================

1. **It never reads an observation after t0.** `build_t0_features` has no parameter for one, and
   every observation it is given must carry a canonical coordinate at or before t0 and sit inside
   the launch transaction. Both are checked per call, not promised.
2. **It never lets an identity become a predictor.** The feature and grouping blocks are a declared
   disjoint partition, the feature block is scalar-only, and only the frozen random control may read
   an identity at all — as a source of deterministic noise with a seed fixed in advance, never as
   something that could encode history.
3. **It never fits anything.** No threshold, rate, transform or cut point in this file was computed
   from data. The random control's rate is a frozen fraction; the order size is inherited unchanged
   from the earlier plumbing runs; the vetoes are point-in-time predicates from the regime.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREGISTRATION_PATH = ROOT / "research" / "B11B_BASELINE_EVALUATION_PREREGISTRATION.json"

PREREGISTRATION_FILE_SHA256 = (
    "55263060716e99500a097f11260c047d03dbf16c4779a37b3f159d55592cb220")
PREREGISTRATION_CANONICAL_SHA256 = (
    "90b159fb4f7492c98571429855c7939d95654c15543e891aaaee279bdf4c506d")

B11A_PREREGISTRATION_FILE_SHA256 = (
    "5faabb33ad317240824450a9b8a3a4026137a04e4457b4767e95488a5c469ac0")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10B = _load("b10b_position_path", "b10b_position_path.py")
B10A = B10B.B10A
B9I = B10B.B9I
B9D = B10B.B9D
NATIVE_QUOTE_MINT = B9D.NATIVE_QUOTE_MINT

FEATURE_CONTRACT_VERSION = "1.0.0"
MODEL_FAMILY = "none"

# --------------------------------------------------------------------------------------------
# The declared partition. Identities live on one side of it and can never cross.
# --------------------------------------------------------------------------------------------

FEATURE_FIELDS = (
    "t0_is_launch_instruction",
    "launch_transaction_trade_count",
    "creator_initial_buy_present",
    "creator_initial_buy_quote_lamports",
    "creator_initial_buy_token_units",
    "t0_virtual_quote_lamports",
    "t0_virtual_token_units",
    "t0_real_quote_lamports",
    "t0_real_token_units",
    "launch_real_token_units",
    "tokens_left_curve_units",
    "token_total_supply_units",
    "is_cashback_enabled",
    "fee_bps_observed",
    "creator_fee_bps_observed",
    "cashback_fee_bps_observed",
    "buyback_fee_bps_observed",
)

GROUPING_FIELDS = ("mint", "bonding_curve", "creator", "create_user", "t0_user")

# Coordinates are provenance, not features and not identities. Kept separate so a reader can tell
# which decision a record belongs to without either block having to carry it.
COORDINATE_FIELDS = B10B.CANONICAL_ORDER

# --------------------------------------------------------------------------------------------
# Hard vetoes — the frozen regime, restated as codes so a policy cannot quietly widen it
# --------------------------------------------------------------------------------------------

V1_NON_SOL_QUOTE = "V1_non_sol_quote"
V2_MAYHEM_MODE = "V2_mayhem_mode"
V3_CURVE_COMPLETE_AT_T0 = "V3_curve_complete_at_t0"
V4_INCOMPLETE_STATE = "V4_incomplete_state"
V5_MIXED_REGIME_WITHIN_CURVE = "V5_mixed_regime_within_curve"
V6_ORDER_EXCEEDS_REAL_TOKEN_RESERVE = "V6_order_exceeds_real_token_reserve"
V7_ORDER_BUYS_ZERO_TOKENS = "V7_order_buys_zero_tokens"
V8_UNSUPPORTED_PROGRAM_VERSION = "V8_unsupported_program_version"
VETO_CODES = (V1_NON_SOL_QUOTE, V2_MAYHEM_MODE, V3_CURVE_COMPLETE_AT_T0, V4_INCOMPLETE_STATE,
              V5_MIXED_REGIME_WITHIN_CURVE, V6_ORDER_EXCEEDS_REAL_TOKEN_RESERVE,
              V7_ORDER_BUYS_ZERO_TOKENS, V8_UNSUPPORTED_PROGRAM_VERSION)

# --------------------------------------------------------------------------------------------
# Policies — frozen rules, not parameters
# --------------------------------------------------------------------------------------------

ORDER_SIZE_LAMPORTS = 100_000_000
RANDOM_CONTROL_SEED = "b11b-random-control-2026-08-02"
RANDOM_CONTROL_NUMERATOR = 1
RANDOM_CONTROL_DENOMINATOR = 2

P0_DO_NOTHING = "P0_do_nothing"
P1_ALL_ELIGIBLE = "P1_all_eligible_fixed_size"
P2_RANDOM_CONTROL = "P2_mint_hash_random_control"
P3_CREATOR_BUY_PRESENT = "P3_creator_initial_buy_present"
P4_CREATOR_BUY_ABSENT = "P4_creator_initial_buy_absent"
POLICY_IDS = (P0_DO_NOTHING, P1_ALL_ELIGIBLE, P2_RANDOM_CONTROL, P3_CREATOR_BUY_PRESENT,
              P4_CREATOR_BUY_ABSENT)

# `P1` is primary. `P0` is degenerate and excluded from the multiplicity family; the family is the
# four remaining policies crossed with the four horizons, declared BEFORE any result exists.
PRIMARY_POLICY = P1_ALL_ELIGIBLE
PRIMARY_HORIZON = "h_1000_slots"
PRIMARY_METRIC = "capital_weighted_net_return"
MULTIPLICITY_FAMILY_SIZE = 16

# B10c state-in-force, never b10b's first-reachable exit rule. Carried as a constant so an output
# that does not name it is visibly incomplete.
LABEL_SEMANTICS = "b10c_state_in_force_at_or_before_horizon"
FORBIDDEN_LABEL_SEMANTICS = "b10b_first_reachable_exit_at_or_after_horizon"


class ContractRefused(B10B.FreezeViolation):
    """Raised when the frozen feature, veto or policy contract cannot be honoured exactly."""


# --------------------------------------------------------------------------------------------
# Feature materialization
# --------------------------------------------------------------------------------------------

def assert_tokens_out_in_range(tokens_out, virtual_token):
    """A floor under the buy formula, at the one consumer that uses its value without checking it.

    WHY HERE AND NOWHERE ELSE. `tokens_out_for_exact_quote_in` feeds three consumers. b10b and b15m
    both *prove* the property they depend on at runtime — b10b re-checks maximality in both
    directions and b15m refuses a cell whose admissible set is not a prefix. This module is the
    third, and it uses the value to decide VETO CODES: `<= 0` sets V7 and `> real_token` sets V6.
    So a wrong buy formula here would not misprice anything, it would change WHICH CURVES ARE
    ELIGIBLE — a population effect, in the module whose whole job is that the cohort is honestly
    constructed.

    THE INVARIANT. `(quote_in - 1) * virtual_token // (virtual_quote + quote_in - 1)` multiplies
    `virtual_token` by a ratio in `[0, 1)` for any positive `quote_in`, so `0 <= tokens_out <
    virtual_token` holds for every input the formula accepts. One comparison.

    WHAT IT IS NOT. A floor, not a proof. An error that stays inside the bound is invisible to it,
    and only the unit tests on `tokens_out_for_exact_quote_in` itself catch that class. It is worth
    saying plainly rather than letting a cheap check read as a guarantee.

    EXTRACTED RATHER THAN INLINE, deliberately. With a correct formula this can never fire, and a
    check that cannot fire reads as protection while testing nothing — it would survive any mutation
    and nobody could show it works. As a function a test hands it a crafted value. Proposed by the
    claude seat, who also stated the limitation above.
    """
    if not isinstance(tokens_out, int) or isinstance(tokens_out, bool):
        raise ContractRefused(
            f"the buy formula returned {tokens_out!r}, which is not an integer; a veto decided "
            "from it would not be arithmetic")
    if tokens_out < 0 or tokens_out >= virtual_token:
        raise ContractRefused(
            f"the buy formula returned {tokens_out} against a virtual token reserve of "
            f"{virtual_token}; the pinned formula cannot leave this range, so the arithmetic is "
            "wrong and the eligibility vetoes decided from it would be wrong with it")
    return tokens_out


def assert_disjoint_contract(feature_fields=FEATURE_FIELDS, grouping_fields=GROUPING_FIELDS):
    """No field may be declared as both a feature and a grouping identity.

    Takes the field sets as arguments rather than reading the module constants, so the check is
    reachable: with the shipped tuples it can never fire, and a guard that can never fire is one
    nobody can show works. A test hands it overlapping sets.
    """
    overlap = set(feature_fields) & set(grouping_fields)
    if overlap:
        raise ContractRefused(
            f"{sorted(overlap)} are declared as both a feature and a grouping identity; an "
            "identity that is also a feature is an identity used for prediction")
    return True


def assert_feature_partition(record):
    """Features and identities are disjoint, exhaustive, and the feature side holds no string."""
    features, grouping = set(FEATURE_FIELDS), set(GROUPING_FIELDS)
    assert_disjoint_contract(FEATURE_FIELDS, GROUPING_FIELDS)
    if set(record.get("features", {})) != features:
        raise ContractRefused(
            f"feature block is {sorted(set(record.get('features', {})))}, contract says "
            f"{sorted(features)}")
    if set(record.get("grouping", {})) != grouping:
        raise ContractRefused(
            f"grouping block is {sorted(set(record.get('grouping', {})))}, contract says "
            f"{sorted(grouping)}")
    for name, value in record["features"].items():
        if isinstance(value, str):
            raise ContractRefused(
                f"feature {name!r} is the string {value!r}. NO STRING MAY APPEAR IN A FEATURE "
                "BLOCK — that rule is what makes 'identities group, never predict' checkable "
                "without anyone having to notice which strings are identities")
        if value is not None and not isinstance(value, (int, bool)):
            raise ContractRefused(
                f"feature {name!r} is a {type(value).__name__}; features are integers, booleans or "
                "null, and nothing else")
    return True


def _require(mapping, field, where):
    if field not in mapping:
        raise ContractRefused(f"{where} does not publish {field!r}")
    return mapping[field]


def build_t0_features(create, observations, t0_key):
    """Materialize the t0 feature and grouping blocks.

    THIS FUNCTION HAS NO PARAMETER FOR A LATER OBSERVATION — no path, no marks, no horizon, no
    label. Every observation handed to it must sit at or before `t0_key` AND inside the launch
    transaction, and both are checked here rather than assumed by the caller.

    Why the launch-transaction check is not redundant: t0 is the first transaction-terminal state,
    so it is necessarily inside the CreateEvent's transaction (verified on the burned-development
    corpus, 1136 of 1136). An observation from a different transaction therefore cannot be at or
    before t0 without the corpus being malformed — and if the corpus is malformed, the feature is
    a look into the future wearing a valid-looking coordinate.
    """
    if not isinstance(create, dict):
        raise ContractRefused(f"create must be a mapping, got {type(create).__name__}")
    if isinstance(observations, (dict, str, bytes)):
        raise ContractRefused("observations must be a sequence of observation mappings")
    observations = list(observations)
    if not observations:
        raise ContractRefused("no observations at or before t0; a feature vector needs a state")

    launch_transaction = (_require(create, "slot", "create"),
                          _require(create, "transaction_index", "create"))
    creator = _require(create, "creator", "CreateEvent")
    seen_t0 = False
    for position, observation in enumerate(observations):
        key = B10B.canonical_key(observation)
        if key > tuple(t0_key):
            raise ContractRefused(
                f"observation {position} at {key} is after t0 {tuple(t0_key)}; a feature computed "
                "from it would be a look into the future")
        if (observation["slot"], observation["transaction_index"]) != launch_transaction:
            raise ContractRefused(
                f"observation {position} is in transaction "
                f"({observation['slot']}, {observation['transaction_index']}), not the launch "
                f"transaction {launch_transaction}; t0 is always inside the launch transaction, so "
                "anything else is a malformed path rather than an earlier state")
        if key == tuple(t0_key):
            seen_t0 = True
    if not seen_t0:
        raise ContractRefused(
            f"no observation at t0 {tuple(t0_key)}; the decision state itself must be present")

    trades = [o for o in observations if o.get("kind") == "TradeEvent"]
    t0_observation = next(o for o in observations
                          if B10B.canonical_key(o) == tuple(t0_key))
    creator_buys = [o for o in trades if o.get("user") == creator and o.get("is_buy") is True]

    features = {
        "t0_is_launch_instruction": t0_observation.get("kind") == "CreateEvent",
        "launch_transaction_trade_count": len(trades),
        "creator_initial_buy_present": bool(creator_buys),
        "creator_initial_buy_quote_lamports": sum(o["quote_amount"] for o in creator_buys),
        "creator_initial_buy_token_units": sum(o["token_amount"] for o in creator_buys),
        "t0_virtual_quote_lamports": _require(t0_observation, "virtual_quote", "t0"),
        "t0_virtual_token_units": _require(t0_observation, "virtual_token", "t0"),
        "t0_real_quote_lamports": _require(t0_observation, "real_quote", "t0"),
        "t0_real_token_units": _require(t0_observation, "real_token", "t0"),
        "launch_real_token_units": _require(create, "real_token", "CreateEvent"),
        "tokens_left_curve_units": (create["real_token"] - t0_observation["real_token"]),
        "token_total_supply_units": _require(create, "token_total_supply", "CreateEvent"),
        "is_cashback_enabled": bool(_require(create, "is_cashback_enabled", "CreateEvent")),
        # Observed, never assumed. A curve whose launch transaction carried no trade publishes no
        # basis points at t0, and null is the honest value: substituting the regime's usual rates
        # would be asserting a fee schedule the decision instant did not state.
        "fee_bps_observed": trades[-1].get("fee_bps") if trades else None,
        "creator_fee_bps_observed": trades[-1].get("creator_fee_bps") if trades else None,
        "cashback_fee_bps_observed": trades[-1].get("cashback_fee_bps") if trades else None,
        "buyback_fee_bps_observed": trades[-1].get("buyback_fee_bps") if trades else None,
    }
    grouping = {
        "mint": _require(create, "mint", "CreateEvent"),
        "bonding_curve": _require(create, "bonding_curve", "CreateEvent"),
        "creator": creator,
        "create_user": _require(create, "user", "CreateEvent"),
        "t0_user": t0_observation.get("user"),
    }
    record = {
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "model_family": MODEL_FAMILY,
        "coordinate": {field: t0_observation[field] for field in COORDINATE_FIELDS},
        "features": features,
        "grouping": grouping,
    }
    assert_feature_partition(record)
    # The identity check, run at the point of construction rather than left to a caller: nothing
    # reachable from the feature block may be anything but a mapping or a scalar.
    B10B.assert_no_future_reachable(record["features"])
    record["features_sha256"] = _sha256_of(features)
    return record


def _sha256_of(value):
    return hashlib.sha256(B10B.canonical_json(value).encode("utf-8")).hexdigest()


def split_key(grouping):
    """The R5 floor: `creator ∪ user`. A grouping key, and never anything else."""
    members = {grouping["creator"], grouping["create_user"]}
    if grouping.get("t0_user"):
        members.add(grouping["t0_user"])
    return "|".join(sorted(members))


# --------------------------------------------------------------------------------------------
# Hard vetoes
# --------------------------------------------------------------------------------------------

def evaluate_vetoes(state, order_quote_lamports, *, regime_in_regime, version_supported):
    """Every veto that fires at t0, as codes. Point-in-time predicates, no fitted thresholds.

    Returns a sorted tuple so the result is order-stable, and an empty tuple means eligible.
    """
    if version_supported is None:
        raise ContractRefused(
            "version_supported must be stated true or false; an unstated program-version check is "
            "not a passed one")
    codes = set()
    if not version_supported:
        codes.add(V8_UNSUPPORTED_PROGRAM_VERSION)
    if not regime_in_regime:
        codes.add(V5_MIXED_REGIME_WITHIN_CURVE)
    missing = [f for f in B10B.STATE_FIELDS if f not in state]
    if missing:
        codes.add(V4_INCOMPLETE_STATE)
        return tuple(sorted(codes))
    if state["quote_mint"] != NATIVE_QUOTE_MINT:
        codes.add(V1_NON_SOL_QUOTE)
    if state["mayhem_mode"]:
        codes.add(V2_MAYHEM_MODE)
    if state["complete"]:
        codes.add(V3_CURVE_COMPLETE_AT_T0)
    if not codes or codes <= {V5_MIXED_REGIME_WITHIN_CURVE, V8_UNSUPPORTED_PROGRAM_VERSION}:
        # Size checks need well-formed reserves, so they run only once the state predicates pass.
        tokens_out = assert_tokens_out_in_range(
            B9I.tokens_out_for_exact_quote_in(
                state["virtual_quote"], state["virtual_token"], order_quote_lamports),
            state["virtual_token"])
        if tokens_out <= 0:
            codes.add(V7_ORDER_BUYS_ZERO_TOKENS)
        elif tokens_out > state["real_token"]:
            codes.add(V6_ORDER_EXCEEDS_REAL_TOKEN_RESERVE)
    return tuple(sorted(codes))


# --------------------------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------------------------

def mint_hash_selected(mint, seed=RANDOM_CONTROL_SEED,
                       numerator=RANDOM_CONTROL_NUMERATOR,
                       denominator=RANDOM_CONTROL_DENOMINATOR):
    """Deterministic pseudo-random selection from a frozen seed.

    The mint is used here as a source of NOISE, not as a predictor: the seed is fixed in advance,
    the hash carries no information about the token, and nothing about the mapping can encode
    history. That is the only use of an identity anywhere outside grouping.
    """
    if not isinstance(mint, str) or not mint:
        raise ContractRefused("mint must be a non-empty string")
    digest = hashlib.sha256((seed + mint).encode("utf-8")).hexdigest()
    return int(digest, 16) % denominator < numerator


def decide(policy_id, features, vetoes, grouping):
    """One policy's decision at t0: an order size in lamports, or None.

    Every policy is a frozen rule. None of them consults an observation after t0, another curve, or
    a threshold computed from anything.
    """
    if policy_id not in POLICY_IDS:
        raise ContractRefused(f"unknown policy {policy_id!r}; the set is {list(POLICY_IDS)}")
    if policy_id == P0_DO_NOTHING:
        return None
    if vetoes:
        return None
    if policy_id == P1_ALL_ELIGIBLE:
        return ORDER_SIZE_LAMPORTS
    if policy_id == P2_RANDOM_CONTROL:
        return ORDER_SIZE_LAMPORTS if mint_hash_selected(grouping["mint"]) else None
    if policy_id == P3_CREATOR_BUY_PRESENT:
        return ORDER_SIZE_LAMPORTS if features["creator_initial_buy_present"] else None
    return None if features["creator_initial_buy_present"] else ORDER_SIZE_LAMPORTS


def assert_policy_invariants(entries_by_policy):
    """The relations the policy set must satisfy, asserted rather than assumed.

    `entries_by_policy` maps a policy id to the SET of mints it entered.
    """
    missing = [p for p in POLICY_IDS if p not in entries_by_policy]
    if missing:
        raise ContractRefused(f"no entry set for {missing}")
    if entries_by_policy[P0_DO_NOTHING]:
        raise ContractRefused(
            "the do-nothing policy entered something; the degenerate reference is the one result "
            "that is known in advance, so a non-empty book here means the accounting is wrong")
    present = entries_by_policy[P3_CREATOR_BUY_PRESENT]
    absent = entries_by_policy[P4_CREATOR_BUY_ABSENT]
    everything = entries_by_policy[P1_ALL_ELIGIBLE]
    if present & absent:
        raise ContractRefused(
            f"{len(present & absent)} curves are in both arms of a partition of the same boolean")
    if present | absent != everything:
        raise ContractRefused(
            "the creator-initial-buy arms do not partition the all-eligible set; either a veto was "
            "applied inconsistently or the feature is not the boolean it claims to be")
    if not entries_by_policy[P2_RANDOM_CONTROL] <= everything:
        raise ContractRefused(
            "the random control entered a curve the all-eligible policy did not; a control that "
            "can enter an ineligible curve is not controlling for anything")
    return True


# --------------------------------------------------------------------------------------------
# The unlock gate
# --------------------------------------------------------------------------------------------

UNLOCK_REQUIREMENTS = ("U1", "U2", "U3", "U4", "U5")


def evaluate_unlock_evidence(evidence, preregistration_path=PREREGISTRATION_PATH):
    """Which of U1..U5 hold, and why each failure fails. Never raises; `assert_` does that.

    Kept as a report rather than a boolean because "results are locked" is a claim someone will
    eventually want to argue with, and an unexplained False is not arguable.
    """
    if not isinstance(evidence, dict):
        raise ContractRefused(f"unlock evidence must be a mapping, got {type(evidence).__name__}")
    raw = pathlib.Path(preregistration_path).read_bytes()
    on_disk_file = hashlib.sha256(raw).hexdigest()
    on_disk_canonical = hashlib.sha256(
        B10B.canonical_json(json.loads(raw)).encode("utf-8")).hexdigest()

    results = {}
    results["U1"] = {
        "satisfied": (evidence.get("b11b_prereg_file_sha256") == PREREGISTRATION_FILE_SHA256
                      and evidence.get("b11b_prereg_canonical_sha256")
                      == PREREGISTRATION_CANONICAL_SHA256
                      and bool(evidence.get("recorded_in_decisions"))),
        "requirement": "this preregistration is committed and both hashes are recorded in "
                       "DECISIONS.md",
    }
    results["U2"] = {
        "satisfied": (evidence.get("model_family") == MODEL_FAMILY
                      or bool(evidence.get("model_artifact_sha256"))),
        "requirement": "model_family is none, or a model artifact hash was frozen before unlock",
    }
    results["U3"] = {
        "satisfied": bool(evidence.get("collection_complete")) and bool(evidence.get("gates_passed")),
        "requirement": "B11a collection is complete and the E6 gates have passed",
    }
    results["U4"] = {
        "satisfied": (evidence.get("b11a_prereg_file_sha256") == B11A_PREREGISTRATION_FILE_SHA256
                      and bool(evidence.get("decisions_unlock_entry"))),
        "requirement": "a DECISIONS.md entry names both window and evaluation hashes and declares "
                       "the unlock",
    }
    results["U5"] = {
        "satisfied": (on_disk_file == PREREGISTRATION_FILE_SHA256
                      and on_disk_canonical == PREREGISTRATION_CANONICAL_SHA256),
        "requirement": "nothing in the contract changed since U1; the on-disk hashes still match",
    }
    unmet = [key for key in UNLOCK_REQUIREMENTS if not results[key]["satisfied"]]
    return {"unlocked": not unmet, "unmet": unmet, "requirements": results,
            "evaluation_only_rule": "B11a is evaluation data. Once labels are revealed no feature, "
                                    "veto, policy, horizon, metric or primary designation may "
                                    "change in response; that requires a new preregistration AND a "
                                    "new window, and B11a would then be burned."}


def assert_unlock_evidence(evidence, preregistration_path=PREREGISTRATION_PATH):
    report = evaluate_unlock_evidence(evidence, preregistration_path)
    if not report["unlocked"]:
        raise ContractRefused(
            f"results remain locked: {report['unmet']} unmet. "
            + "; ".join(f"{key}: {report['requirements'][key]['requirement']}"
                        for key in report["unmet"]))
    return True


def load_preregistration(path=PREREGISTRATION_PATH, verify_hashes=True):
    raw = pathlib.Path(path).read_bytes()
    document = json.loads(raw)
    if verify_hashes:
        digest = hashlib.sha256(raw).hexdigest()
        canonical = hashlib.sha256(
            B10B.canonical_json(document).encode("utf-8")).hexdigest()
        if digest != PREREGISTRATION_FILE_SHA256:
            raise ContractRefused(
                f"preregistration file hash is {digest}, pinned {PREREGISTRATION_FILE_SHA256}")
        if canonical != PREREGISTRATION_CANONICAL_SHA256:
            raise ContractRefused(
                f"preregistration canonical hash is {canonical}, pinned "
                f"{PREREGISTRATION_CANONICAL_SHA256}")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    load_preregistration()
    print(json.dumps({
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "model_family": MODEL_FAMILY,
        "preregistration_file_sha256": PREREGISTRATION_FILE_SHA256,
        "preregistration_canonical_sha256": PREREGISTRATION_CANONICAL_SHA256,
        "features": list(FEATURE_FIELDS),
        "grouping_identities": list(GROUPING_FIELDS),
        "vetoes": list(VETO_CODES),
        "policies": list(POLICY_IDS),
        "primary": {"policy": PRIMARY_POLICY, "horizon": PRIMARY_HORIZON,
                    "metric": PRIMARY_METRIC},
        "multiplicity_family_size": MULTIPLICITY_FAMILY_SIZE,
        "label_semantics": LABEL_SEMANTICS,
        "unlock_requirements": list(UNLOCK_REQUIREMENTS),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ContractRefused: {error}", file=sys.stderr)
        sys.exit(2)
