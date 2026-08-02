"""B13f — materializer for the frozen prospective feature contract. Offline. No model, no fitting.

What this module is
-------------------
The machinery that assembles the 99-field vector frozen in
`research/B13F_FEATURE_CONTRACT_PREREGISTRATION.md`, committed separately and afterwards so the
field list could not have been trimmed until the numbers came out well.

It copies no arithmetic. Every value is read out of an already-validated B11b, B13a or B13d record,
through those modules' own validators — so if one of them changes, this vector's claim about what it
contains fails rather than quietly diverging.

Three things it will not do
---------------------------
1. **It will not produce a vector for B11a.** `eligible_windows` is empty and every entry point
   checks it. B11a's evaluation was frozen as a no-model baseline over 17 declared fields; putting a
   99-field vector into that window would evaluate something nobody preregistered.
2. **It will not impute.** A missing input makes the vector *unavailable with reasons*. A zero would
   claim the thing did not happen; a median would claim the subject was typical, computed from a
   distribution fitted outside any fold; a missingness flag chosen because it improved a score is
   the outcome leaking in through the door marked "handling missing data".
3. **It will not fit anything.** There is no scaler, no encoder, no rank, no quantile and nowhere to
   put one. Transforms belong inside a training fold, and this module has no concept of a fold.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13D = _load("b13d_concentration", "b13d_concentration.py")
B13A = B13D.B13A
B10B = B13D.B10B
B11B = _load("b11b_t0_features", "b11b_t0_features.py")
B13E = _load("b13e_collection_contract", "b13e_collection_contract.py")

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B13A.COORDINATE_FIELDS

PREREGISTRATION_PATH = ROOT / "research" / "B13F_FEATURE_CONTRACT_PREREGISTRATION.md"
PREREGISTRATION_ID = "B13F_FEATURE_CONTRACT_V1"

# Pinned against the document committed ALONE in the previous commit.
PREREGISTRATION_PARAMS_SHA256 = \
    "2573f3aa2a80b6800fd861f158cbfbc6797e13dfc4716e414b5a95d0e6056359"

V01_HISTORY_INCOMPLETE = "V01_history_incomplete"
V02_UNRESOLVED_DECODE_EVIDENCE = "V02_unresolved_decode_evidence"
V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE = "V03_concentration_not_atomic_or_incomplete"
V04_REQUIRED_DENOMINATOR_UNDEFINED = "V04_required_denominator_undefined"
V05_EVIDENCE_AFTER_T0 = "V05_evidence_after_t0"
V06_SOURCE_HASH_DRIFT = "V06_source_hash_drift"
V07_CONTRACT_HASH_MISMATCH = "V07_contract_hash_mismatch"
UNAVAILABILITY_CODES = (V01_HISTORY_INCOMPLETE, V02_UNRESOLVED_DECODE_EVIDENCE,
                        V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE,
                        V04_REQUIRED_DENOMINATOR_UNDEFINED, V05_EVIDENCE_AFTER_T0,
                        V06_SOURCE_HASH_DRIFT, V07_CONTRACT_HASH_MISMATCH)

VECTOR_FIELDS = ("schema_version", "feature_contract_version", "preregistration_id",
                 "preregistration_sha256", "feature_order_sha256", "window_id", "as_of",
                 "grouping", "features", "availability", "evidence", "vector_sha256")

# Every source of a field, so the materializer can be read as a map rather than a pile of lookups.
SOURCE_T0 = "b11b_t0_features"
SOURCE_HISTORY = "b13a_history"
SOURCE_CONCENTRATION = "b13d_concentration"

# Names whose presence anywhere in a feature block would mean this contract had been widened past
# what was frozen. Checked by substring because the damage is done by the concept, not the spelling.
FORBIDDEN_FEATURE_SUBSTRINGS = (
    "cluster", "association", "sentiment", "embedding", "engagement", "popularity", "credibility",
    "market_cap", "price_change", "rank", "quantile", "percentile", "zscore", "z_score", "log_",
    "normali", "standardi", "scaled", "imputed", "median", "mean_", "label", "outcome", "pnl",
    "return_", "probability", "score", "url", "handle", "text", "headline",
)


class VectorRefused(B13D.ConcentrationRefused):
    """Raised when a feature vector cannot be produced without asserting something untrue."""


class ContractIneligible(VectorRefused):
    """Raised when this contract is applied to a window it was never eligible for.

    A separate class because it is not a data problem: the inputs may be perfect and the answer is
    still that nobody preregistered this evaluation.
    """


# --------------------------------------------------------------------------------------------
# The preregistration, pinned
# --------------------------------------------------------------------------------------------

def read_preregistration(path=None):
    path = pathlib.Path(path or PREREGISTRATION_PATH)
    if not path.exists():
        raise VectorRefused(f"the feature contract is missing at {path}")
    match = re.search(r"```json\n(.*?)\n```", path.read_text(), re.S)
    if not match:
        raise VectorRefused("the feature contract carries no frozen parameter block")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise VectorRefused(f"the frozen parameter block is not valid JSON: {error}")


def preregistration_hash(params):
    return hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def feature_order_hash(order):
    """A hash of the ORDER, not just the set. Order drift is the failure this catches.

    Two vectors with the same fields in different positions are the same set and a different
    matrix, and a model trained on one and scored on the other is silently wrong in every row.
    """
    return hashlib.sha256(json.dumps(list(order), separators=(",", ":")).encode()).hexdigest()


def assert_preregistration(params=None, expected=PREREGISTRATION_PARAMS_SHA256):
    """The document is the authority. Beyond the hash, only cross-source facts are re-checked.

    Same rule as B13e: a value the code holds its own copy of is checked against that copy, because
    the other side can move without the document changing. A value only the document states is
    pinned by the hash alone, and re-reading it would add a check no input can make fire.
    """
    params = read_preregistration() if params is None else params
    if params.get("preregistration_id") != PREREGISTRATION_ID:
        raise VectorRefused(
            f"{V07_CONTRACT_HASH_MISMATCH}: preregistration id is "
            f"{params.get('preregistration_id')!r}, expected {PREREGISTRATION_ID!r}")
    digest = preregistration_hash(params)
    if digest != expected:
        raise VectorRefused(
            f"{V07_CONTRACT_HASH_MISMATCH}: the frozen parameters hash to {digest} but this code "
            f"was written against {expected}. A feature list that moved after it was frozen is a "
            "feature list somebody trimmed")
    order = params["feature_order"]
    if len(order) != params["feature_count"]:
        raise VectorRefused("the contract's own field count does not match its own field list")
    if len(set(order)) != len(order):
        raise VectorRefused("the contract lists a field twice; two names for one fact is how a "
                            "later reader ends up with both")
    # Cross-source: B11b's 17 fields must still be exactly the first block, under their own names.
    if list(order[:len(B11B.FEATURE_FIELDS)]) != list(B11B.FEATURE_FIELDS):
        raise VectorRefused(
            "the contract's first block is not B11b's frozen field list in B11b's own order; "
            "renaming or reordering a frozen contract forks it")
    for name in order:
        lowered = name.lower()
        for banned in FORBIDDEN_FEATURE_SUBSTRINGS:
            if banned in lowered:
                raise VectorRefused(
                    f"the contract lists {name!r}, which contains {banned!r}. This vector carries "
                    "raw point-in-time facts only; a transform, a judgement or an identity in the "
                    "field list is one a model would weight")
    return params


def assert_eligible(window_id, params=None, expected=PREREGISTRATION_PARAMS_SHA256):
    """Fail closed on any window. `eligible_windows` is empty, and B11a is named explicitly.

    The B11a refusal below is UNCONDITIONAL — it does not consult `eligible_for_b11a`. That flag is
    a value only the document states, so the hash already pins it, and re-reading it would add a
    check no input can make fire. The code's own refusal is independent of the document and
    strictly stronger: a document re-pinned with `eligible_for_b11a: true` still cannot get a B11a
    vector out of this function. `expected` is exposed so a test can supply a re-pinned document
    and demonstrate exactly that.
    """
    params = assert_preregistration(params, expected)
    if str(window_id).lower().startswith("b11a"):
        raise ContractIneligible(
            f"{window_id!r} is B11a. Its evaluation was frozen as a NO-MODEL baseline over B11b's "
            "17 declared fields, and its unlock evidence was written against that; a 99-field "
            "vector there would evaluate something nobody preregistered, on a window whose "
            "maturity conditions were set for something else")
    if window_id not in params["eligible_windows"]:
        raise ContractIneligible(
            f"{window_id!r} is not an eligible window, and none is: `eligible_windows` is empty. "
            "A new training/evaluation design must first name a fresh window, state its split, and "
            "fit every transform on training folds only")
    return True


# --------------------------------------------------------------------------------------------
# Scans
# --------------------------------------------------------------------------------------------

def assert_feature_types(features):
    """Integers, booleans and null. Nothing else, and a float least of all."""
    for name, value in features.items():
        if isinstance(value, str):
            raise VectorRefused(
                f"feature {name!r} is the string {value!r}. NO STRING MAY APPEAR IN A FEATURE "
                "BLOCK — raw text, URLs and handles live in evidence, and that rule is checkable "
                "without anyone having to notice which strings are identities")
        if isinstance(value, float):
            raise VectorRefused(
                f"feature {name!r} is the float {value!r}. Rationals travel as named integer "
                "numerator/denominator pairs precisely so a later model adapter cannot silently "
                "round them")
        if value is not None and not isinstance(value, (int, bool)):
            raise VectorRefused(
                f"feature {name!r} is a {type(value).__name__}; features are integers, booleans "
                "or null")
    return True


def assert_no_association_evidence(record):
    """A B13b ledger admitted here would turn an explicit 'we do not know' into a weighted number."""
    def looks_like_ledger(value):
        if not isinstance(value, dict):
            return False
        if value.get("confidence_status") == "uncalibrated_evidence_only":
            return True
        return "links" in value and "evidence_hash_chain_sha256" in value

    def walk(value, path="record"):
        if looks_like_ledger(value):
            raise VectorRefused(
                f"{path} is a B13b ASSOCIATION EVIDENCE LEDGER. It declares itself "
                "`uncalibrated_evidence_only` and its links explicitly do not assert common "
                "control; admitting it here would turn 'we do not know' into a number a model "
                "weights")
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
    walk(record)
    return True


# --------------------------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------------------------

def unavailability(t0_record, history, concentration, t0_key, source_hashes=None):
    """Why no vector exists for this subject. Reason codes, never a silent zero."""
    reasons = []

    for failure in B13A.completeness_failures(history):
        code = (V02_UNRESOLVED_DECODE_EVIDENCE
                if failure["reason_code"] == B13A.C04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0
                else V01_HISTORY_INCOMPLETE)
        reasons.append({"reason_code": code, "detail": failure["detail"],
                        "source": SOURCE_HISTORY, "source_reason": failure["reason_code"]})

    accounting = concentration["accounting"]
    if not accounting["enumeration_complete"]:
        reasons.append({
            "reason_code": V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE,
            "detail": f"the holder enumeration is incomplete, leaving "
                      f"{accounting['supply_residual_units']} units unaccounted for, so every "
                      "share computed from it is a lower bound. (B13d already refuses a complete "
                      "enumeration with a residual, so the flag alone decides here.)",
            "source": SOURCE_CONCENTRATION})
    if tuple(concentration["as_of"][field] for field in COORDINATE_FIELDS) != tuple(t0_key):
        reasons.append({
            "reason_code": V03_CONCENTRATION_NOT_ATOMIC_OR_INCOMPLETE,
            "detail": "the holder snapshot is not as of this decision's coordinate; balances from "
                      "another instant are not the balances the decision was made against",
            "source": SOURCE_CONCENTRATION})

    # Both denominators are REQUIRED by the contract, so an undefined one is not a missing field —
    # it makes the whole vector unavailable.
    for name in B13D.DENOMINATORS:
        block = concentration["shares"]["by_account"][name]
        if not block.get("defined"):
            reasons.append({
                "reason_code": V04_REQUIRED_DENOMINATOR_UNDEFINED,
                "detail": f"the {name} denominator is undefined: {block.get('undefined_reason')}. "
                          "Both denominators are required, because publishing one of them is a "
                          "choice made on the reader's behalf",
                "source": SOURCE_CONCENTRATION})

    for label, record in (("t0 features", t0_record), ("history", history),
                          ("concentration", concentration)):
        coordinate = record.get("as_of") or record.get("t0") or {}
        if coordinate and tuple(coordinate.get(f, 0) for f in COORDINATE_FIELDS) > tuple(t0_key):
            reasons.append({
                "reason_code": V05_EVIDENCE_AFTER_T0,
                "detail": f"the {label} record is as of a coordinate after t0",
                "source": label})

    for entry in source_hashes or ():
        if entry["recorded"] != entry["recomputed"]:
            reasons.append({
                "reason_code": V06_SOURCE_HASH_DRIFT,
                "detail": f"{entry['name']} hashes to {entry['recomputed'][:12]} but claims "
                          f"{entry['recorded'][:12]}",
                "source": entry["name"]})
    return reasons


def require_available(reasons):
    if reasons:
        raise VectorRefused(
            "no feature vector exists for this subject: "
            + "; ".join(f"{r['reason_code']} — {r['detail']}" for r in reasons))
    return True


# --------------------------------------------------------------------------------------------
# Materialization
# --------------------------------------------------------------------------------------------

def _share_fields(block, prefix, features):
    features[f"{prefix}_denominator_units"] = block["denominator_units"]
    features[f"{prefix}_holder_count"] = block["holder_count"]
    for k in B13D.TOP_K:
        entry = block[f"top_{k}"]
        features[f"{prefix}_top_{k}_units"] = entry["units"]
        features[f"{prefix}_top_{k}_share_numerator"] = entry["share"]["numerator"]
        features[f"{prefix}_top_{k}_share_denominator"] = entry["share"]["denominator"]
    features[f"{prefix}_herfindahl_numerator"] = block["herfindahl"]["numerator"]
    features[f"{prefix}_herfindahl_denominator"] = block["herfindahl"]["denominator"]


def materialize(t0_record, history, concentration, window_id, source_hashes=None, params=None,
                enforce_eligibility=True):
    """One vector, or a refusal naming why there is none.

    Inputs are validated by the modules that produced them, never re-derived here, and are only
    ever read — a test asserts that this function leaves every one of them byte-identical, which is
    what catches a future edit that starts writing to them.
    """
    params = assert_preregistration(params)
    if enforce_eligibility:
        assert_eligible(window_id, params)

    for record in (t0_record, history, concentration):
        assert_no_association_evidence(record)
    B11B.assert_feature_partition(t0_record)
    B13A.assert_history(history)
    B13D.assert_concentration(concentration)

    t0_key = tuple(history["as_of"][field] for field in COORDINATE_FIELDS)
    reasons = unavailability(t0_record, history, concentration, t0_key, source_hashes)
    require_available(reasons)

    sections = history["sections"]
    features = {}

    # Block A — B11b, names unchanged.
    for name in B11B.FEATURE_FIELDS:
        features[name] = t0_record["features"][name]

    # Block B — history over the fixed lookback, renamed to name the window it was computed over.
    creator, user, token, funding = (sections["creator"]["features"], sections["user"]["features"],
                                     sections["token"]["features"],
                                     sections["funding"]["features"])
    features["creator_prior_launch_count_in_lookback"] = creator["prior_launch_count_observed"]
    features["creator_prior_completion_count_in_lookback"] = \
        creator["prior_completion_count_observed"]
    features["creator_prior_launch_with_buy_count_in_lookback"] = \
        creator["prior_launch_with_creator_buy_count_observed"]
    features["creator_prior_buy_quote_lamports_in_lookback"] = \
        creator["prior_creator_buy_quote_lamports_observed"]
    features["creator_slots_since_previous_launch_in_lookback"] = \
        creator["slots_since_previous_observed_launch"]
    for source, target in (("prior_trade_count_observed", "user_prior_trade_count_in_lookback"),
                           ("prior_buy_count_observed", "user_prior_buy_count_in_lookback"),
                           ("prior_sell_count_observed", "user_prior_sell_count_in_lookback"),
                           ("prior_quote_in_lamports_observed",
                            "user_prior_quote_in_lamports_in_lookback"),
                           ("prior_quote_out_lamports_observed",
                            "user_prior_quote_out_lamports_in_lookback"),
                           ("prior_token_in_units_observed",
                            "user_prior_token_in_units_in_lookback"),
                           ("prior_token_out_units_observed",
                            "user_prior_token_out_units_in_lookback"),
                           ("prior_distinct_mint_count_observed",
                            "user_prior_distinct_mint_count_in_lookback")):
        features[target] = user[source]
    for source, target in (("slots_since_launch", "token_slots_since_launch"),
                           ("prior_trade_count_observed", "token_prior_trade_count_in_lookback"),
                           ("prior_buy_count_observed", "token_prior_buy_count_in_lookback"),
                           ("prior_sell_count_observed", "token_prior_sell_count_in_lookback"),
                           ("prior_quote_in_lamports_observed",
                            "token_prior_quote_in_lamports_in_lookback"),
                           ("prior_quote_out_lamports_observed",
                            "token_prior_quote_out_lamports_in_lookback"),
                           ("prior_distinct_user_count_observed",
                            "token_prior_distinct_user_count_in_lookback"),
                           ("completed_before_t0", "token_completed_before_t0")):
        features[target] = token[source]
    for source, target in (("inbound_edge_count_observed",
                            "creator_funding_inbound_edge_count_in_lookback"),
                           ("outbound_edge_count_observed",
                            "creator_funding_outbound_edge_count_in_lookback"),
                           ("inbound_lamports_observed",
                            "creator_funding_inbound_lamports_in_lookback"),
                           ("outbound_lamports_observed",
                            "creator_funding_outbound_lamports_in_lookback"),
                           ("distinct_counterparty_count_observed",
                            "creator_funding_distinct_counterparty_count_in_lookback")):
        features[target] = funding[source]

    # Block C — concentration, both denominators, rationals flattened into named integer pairs.
    for name in B13D.DENOMINATORS:
        _share_fields(concentration["shares"]["by_account"][name], f"concentration_{name}",
                      features)

    owner_available = bool(concentration["accounting"]["owner_grouping_available"])
    features["concentration_owner_grouping_available"] = owner_available
    for name in B13D.DENOMINATORS:
        prefix = f"concentration_owner_{name}"
        block = concentration["shares"]["by_owner"][name]
        if owner_available and block.get("defined"):
            features[f"{prefix}_holder_count"] = block["holder_count"]
            features[f"{prefix}_top_1_units"] = block["top_1"]["units"]
            features[f"{prefix}_top_1_share_numerator"] = block["top_1"]["share"]["numerator"]
            features[f"{prefix}_top_1_share_denominator"] = block["top_1"]["share"]["denominator"]
        else:
            # NULL, never zero. A top-1 of zero says the largest owner holds nothing; null says we
            # cannot collapse accounts to owners, and those are different facts.
            for suffix in ("holder_count", "top_1_units", "top_1_share_numerator",
                           "top_1_share_denominator"):
                features[f"{prefix}_{suffix}"] = None

    for role in B13D.ROLES:
        features[f"concentration_role_{role}_units"] = concentration["by_role"][role]["units"]
    accounting = concentration["accounting"]
    features["concentration_accounts_enumerated"] = accounting["accounts_enumerated"]
    features["concentration_accounts_with_positive_balance"] = \
        accounting["accounts_with_positive_balance"]
    features["concentration_zero_balance_account_count"] = \
        accounting["zero_balance_account_count_observed"]
    features["concentration_unresolved_owner_account_count"] = \
        accounting["unresolved_owner_account_count"]
    features["concentration_distinct_owners_resolved"] = accounting["distinct_owners_resolved"]
    features["concentration_units_held_in_accounts"] = accounting["units_held_in_accounts"]
    features["concentration_declared_supply_units"] = accounting["declared_supply_units"]
    # Carried, not dropped. A residual left out of the vector is supply the model believes is
    # distributed among the holders it can see.
    features["concentration_supply_residual_units"] = accounting["supply_residual_units"]

    creator_blocks = concentration["creator"]
    creator_available = all(creator_blocks[name].get("defined") for name in B13D.DENOMINATORS)
    features["concentration_creator_share_available"] = creator_available
    for name in B13D.DENOMINATORS:
        prefix = f"concentration_creator_{name}"
        block = creator_blocks[name]
        if creator_available:
            features[f"{prefix}_units"] = block["units"]
            features[f"{prefix}_share_numerator"] = block["share"]["numerator"]
            features[f"{prefix}_share_denominator"] = block["share"]["denominator"]
        else:
            for suffix in ("units", "share_numerator", "share_denominator"):
                features[f"{prefix}_{suffix}"] = None

    vector = {
        "schema_version": SCHEMA_VERSION,
        "feature_contract_version": params["feature_contract_version"],
        "preregistration_id": PREREGISTRATION_ID,
        "preregistration_sha256": preregistration_hash(params),
        "feature_order_sha256": feature_order_hash(params["feature_order"]),
        "window_id": window_id,
        "as_of": {field: history["as_of"][field] for field in COORDINATE_FIELDS},
        # Identities group. They never predict.
        "grouping": {field: history["subject"].get(field) if field in history["subject"]
                     else t0_record["grouping"].get(field) for field in params["grouping_fields"]},
        "features": features,
        "availability": {
            "available": True,
            "reasons": [],
            "owner_grouping_available": owner_available,
            "creator_share_available": creator_available,
        },
        "evidence": {
            "history_sha256": history["history_sha256"],
            "concentration_sha256": concentration["concentration_sha256"],
            "source_hash_chain_sha256": history["source_hash_chain_sha256"],
        },
        "vector_sha256": None,
    }
    assert_vector(vector, params)
    vector["vector_sha256"] = vector_hash(vector)
    return vector


def unavailable_vector(window_id, as_of, reasons, params=None, enforce_eligibility=True):
    """An explicit absence, with its reasons, rather than a vector of substituted values."""
    params = assert_preregistration(params)
    if enforce_eligibility:
        assert_eligible(window_id, params)
    for reason in reasons:
        if reason["reason_code"] not in UNAVAILABILITY_CODES:
            raise VectorRefused(
                f"unavailability reason {reason['reason_code']!r} is not one of "
                f"{list(UNAVAILABILITY_CODES)}")
    if not reasons:
        raise VectorRefused("an unavailable vector must say why; 'unavailable' alone tells an "
                            "operator nothing about what to fix")
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_contract_version": params["feature_contract_version"],
        "preregistration_id": PREREGISTRATION_ID,
        "preregistration_sha256": preregistration_hash(params),
        "feature_order_sha256": feature_order_hash(params["feature_order"]),
        "window_id": window_id,
        "as_of": {field: as_of[field] for field in COORDINATE_FIELDS},
        "grouping": {},
        # No feature block at all. An empty one would invite a caller to fill it in.
        "features": None,
        "availability": {"available": False, "reasons": list(reasons),
                         "owner_grouping_available": None, "creator_share_available": None},
        "evidence": {},
        "vector_sha256": None,
    }


def assert_vector(vector, params=None, expected=PREREGISTRATION_PARAMS_SHA256):
    """Every gate on one vector, in one call.

    `expected` is exposed so a test can supply a re-pinned contract and reach the checks that sit
    behind the hash — the identity-in-features rule chief among them.
    """
    params = assert_preregistration(params, expected)
    if not isinstance(vector, dict):
        raise VectorRefused(f"vector must be a mapping, got {type(vector).__name__}")
    missing = [field for field in VECTOR_FIELDS if field not in vector]
    if missing:
        raise VectorRefused(f"vector does not carry {missing}")
    unknown = [field for field in vector if field not in VECTOR_FIELDS]
    if unknown:
        raise VectorRefused(f"vector carries undeclared fields {sorted(unknown)}")
    if vector["preregistration_sha256"] != preregistration_hash(params):
        raise VectorRefused(f"{V07_CONTRACT_HASH_MISMATCH}: the vector was built under a different "
                            "contract than the one in force")
    if vector["feature_order_sha256"] != feature_order_hash(params["feature_order"]):
        raise VectorRefused(
            "the vector's feature order does not match the contract's. Two vectors with the same "
            "fields in different positions are the same set and a different matrix, and a model "
            "trained on one and scored on the other is wrong in every row")

    features = vector["features"]
    if not vector["availability"]["available"]:
        if features is not None:
            raise VectorRefused("an unavailable vector carries features; absence is not a row")
        if not vector["availability"]["reasons"]:
            raise VectorRefused("an unavailable vector states no reason")
        return vector

    order = list(params["feature_order"])
    if list(features) != order:
        present, expected = set(features), set(order)
        if present != expected:
            raise VectorRefused(
                f"feature block has {len(present - expected)} extra and "
                f"{len(expected - present)} missing fields against the frozen contract")
        raise VectorRefused(
            "the feature block is in a different ORDER from the frozen contract; the set matches "
            "and the matrix does not")
    assert_feature_types(features)
    for name in params["grouping_fields"]:
        if name in features:
            raise VectorRefused(
                f"{name!r} is a grouping identity and appears in the feature block; an identity "
                "that is also a feature is an identity used for prediction")
    assert_no_association_evidence(vector)

    for flag, governed in params["optional_fields"].items():
        available = features[flag]
        for name in governed:
            if available and features[name] is None:
                raise VectorRefused(
                    f"{flag} is true but {name!r} is null; the availability rule and the value "
                    "disagree")
            if not available and features[name] is not None:
                raise VectorRefused(
                    f"{flag} is false but {name!r} carries {features[name]!r}. An unavailable "
                    "optional field is NULL, never zero: a share of zero says the holder holds "
                    "nothing, null says we cannot say, and a model that cannot tell them apart "
                    "will learn from the difference anyway")
    return vector


def vector_hash(vector):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in vector.items() if k != "vector_sha256"}).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    params = assert_preregistration()
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "feature_contract_version": params["feature_contract_version"],
        "preregistration_id": PREREGISTRATION_ID,
        "preregistration_sha256": preregistration_hash(params),
        "feature_order_sha256": feature_order_hash(params["feature_order"]),
        "feature_count": params["feature_count"],
        "eligible_for_b11a": False,
        "eligible_windows": list(params["eligible_windows"]),
        "transforms_fitted": [],
        "floats_permitted": False,
        "imputation_permitted": False,
        "unavailability_codes": list(UNAVAILABILITY_CODES),
        "excluded_sources": list(params["excluded_sources"]),
        "model_fitted": False,
        "corpus_read": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"VectorRefused: {error}", file=sys.stderr)
        sys.exit(2)
