"""B13d — exact point-in-time RAW token concentration. Offline library. No clusters, no thresholds.

What this module is
-------------------
Arithmetic over an as-of-t0 holder-balance snapshot, in exact integers and gcd-reduced rationals.
Holder counts, top-k shares, a Herfindahl index, per-role balances and a creator share — all raw,
all reconciled against the declared supply, and all published under **two denominators at once**.

Why two denominators, always
----------------------------
Concentration is whatever the denominator says it is. Divide by total supply and a token whose curve
holds 90% of it looks broadly distributed; divide by circulating user balances and the same holdings
look extreme. Both figures are true and neither is the answer, so publishing one of them is a
choice made on the reader's behalf — and it is the single easiest place in this whole project to
produce a number that flatters.

So every share is computed under **both** `total_supply` and `circulating_user`, side by side, and a
record carrying only one is refused. The circulating-user denominator is built by SUMMING the
user-role balances rather than by subtracting exclusions from supply, because a sum names what it
included while a subtraction hides what it removed.

Reconciliation is not optional
------------------------------
Every unit is accounted for. Duplicate accounts, negative balances, a second mint, mixed decimals, a
missing role, an owner nobody resolved, an enumeration that claims completeness while not summing to
supply — each one fails closed. **Unknown is never zero**, an unknown role is never a user, and the
supply residual is published rather than absorbed.

Accounts are not owners
-----------------------
One owner can hold many token accounts, so collapsing accounts to owners changes every figure here.
This module refuses to collapse without exact owner evidence for EVERY account, because one
unresolved account could belong to the largest holder and a top-1 share computed without it is a
lower bound wearing the costume of a measurement.

Cluster adjustment is structurally unavailable
----------------------------------------------
`cluster_adjusted_concentration` exists and always raises. No artifact type is accepted in this
pass, no connected component is inferred, and a B13b association ledger passed as a cluster map gets
its own refusal — it is uncalibrated evidence by its own declaration, and treating it as a clustering
would launder an explicit "we do not know" into a merge.

Not chosen here: any concentration threshold, veto, profitability class or rug label.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13C = _load("b13c_observations", "b13c_observations.py")
B13A = B13C.B13A
B10B = B13C.B10B

Absent = B13C.Absent
is_absent = B13C.is_absent

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B13A.COORDINATE_FIELDS

POINT_IN_TIME_RULE = (
    "A holder-balance snapshot may inform a decision at t0 only if its own canonical coordinate is "
    "at or before t0's. A later holder state cannot be backfilled into an earlier decision: the "
    "balances that existed after a decision are not the balances it was made against, and using "
    "them would encode the outcome in the input.")

DENOMINATOR_RULE = (
    "Every share is published under BOTH the total-supply and the circulating-user denominator. "
    "Concentration is whatever the denominator says it is, so publishing one of them would be a "
    "choice made on the reader's behalf. The circulating-user denominator is the SUM of user-role "
    "balances, never supply minus exclusions: a sum names what it included, a subtraction hides "
    "what it removed.")

# --------------------------------------------------------------------------------------------
# Roles — unknown is never a user
# --------------------------------------------------------------------------------------------

ROLE_USER = "user"
ROLE_BONDING_CURVE = "bonding_curve"
ROLE_VAULT = "vault"
ROLE_BURN = "burn"
ROLE_PROGRAM_OWNED = "program_owned"
ROLE_UNKNOWN = "unknown"
ROLES = (ROLE_USER, ROLE_BONDING_CURVE, ROLE_VAULT, ROLE_BURN, ROLE_PROGRAM_OWNED, ROLE_UNKNOWN)

# The only role counted as circulating user supply. An unknown role is NOT a user: treating it as
# one would silently enlarge the denominator and shrink every share, which is the flattering
# direction and therefore the one to refuse by construction.
CIRCULATING_USER_ROLES = (ROLE_USER,)

ROLE_MEANING = {
    ROLE_USER: "a balance held by an ordinary holder; the only role counted as circulating",
    ROLE_BONDING_CURVE: "the bonding curve's own reserve of the token",
    ROLE_VAULT: "a protocol or team vault",
    ROLE_BURN: "an address from which the tokens cannot return",
    ROLE_PROGRAM_OWNED: "held by a program, not by a person deciding anything",
    ROLE_UNKNOWN: "nobody established what this is. NOT a user, and never counted as one",
}

OWNER_EXACT = "exact_owner_evidence"
OWNER_UNRESOLVED = "unresolved"
OWNER_STATUSES = (OWNER_EXACT, OWNER_UNRESOLVED)

# --------------------------------------------------------------------------------------------
# Record shapes
# --------------------------------------------------------------------------------------------

ACCOUNT_FIELDS = ("token_account", "mint", "decimals", "owner", "owner_status", "owner_evidence",
                  "raw_units", "role", "role_evidence")

COMPLETENESS_FIELDS = ("enumeration_complete", "enumeration_method", "accounts_enumerated",
                       "source_hashes", "detail")

CREATOR_BINDING_EXACT = "exact_binding"
CREATOR_BINDING_UNVERIFIED = "unverified"
CREATOR_BINDING_ABSENT = "absent"
CREATOR_BINDING_STATUSES = (CREATOR_BINDING_EXACT, CREATOR_BINDING_UNVERIFIED,
                            CREATOR_BINDING_ABSENT)
CREATOR_BINDING_FIELDS = ("status", "address", "evidence")

SNAPSHOT_FIELDS = ("schema_version", "point_in_time_rule", "mint", "decimals", "as_of",
                   "receipt_provenance", "accounts", "declared_supply_units", "completeness",
                   "creator_binding", "source_sha256", "snapshot_sha256")

DENOMINATOR_TOTAL_SUPPLY = "total_supply"
DENOMINATOR_CIRCULATING_USER = "circulating_user"
DENOMINATORS = (DENOMINATOR_TOTAL_SUPPLY, DENOMINATOR_CIRCULATING_USER)

TOP_K = (1, 5, 10)

GROUPING_ACCOUNT = "account"
GROUPING_OWNER = "owner"
GROUPINGS = (GROUPING_ACCOUNT, GROUPING_OWNER)

ACCOUNTING_FIELDS = ("accounts_enumerated", "accounts_with_positive_balance",
                     "zero_balance_account_count_observed", "unresolved_owner_account_count",
                     "distinct_owners_resolved", "units_held_in_accounts",
                     "declared_supply_units", "supply_residual_units", "enumeration_complete",
                     "owner_grouping_available", "owner_grouping_unavailable_reason")

# No cluster field of any kind, deliberately. B13b's judgement applies here unchanged: a field
# named for a quantity we refuse to compute teaches the next reader that we compute it. The refusal
# lives in `cluster_adjusted_concentration`, which raises, and in the published contract.
CONCENTRATION_FIELDS = ("schema_version", "point_in_time_rule", "denominator_rule", "mint",
                        "as_of", "snapshot_sha256", "accounting", "by_role", "shares",
                        "creator", "concentration_sha256")

# Any key whose name asserts a judgement this module may not make.
FORBIDDEN_FIELD_SUBSTRINGS = ("cluster", "adjusted", "probability", "score", "threshold", "veto",
                              "rug", "profitab", "risk_", "verdict", "label", "predict")


class ConcentrationRefused(B13C.ObservationRefused):
    """Raised when a concentration figure cannot be produced without asserting something untrue."""


class ClusterAdjustmentRefused(ConcentrationRefused):
    """Raised when a caller asks for a cluster-adjusted figure.

    A distinct class because it is a different refusal: the snapshot is fine, the arithmetic is
    fine, and what is missing is an artifact nobody has earned the right to build yet.
    """


# --------------------------------------------------------------------------------------------
# Exact rationals — no float ever reaches a share
# --------------------------------------------------------------------------------------------

def rational(numerator, denominator):
    """A gcd-reduced exact rational. Shares are ratios of integers and stay that way.

    A float here would be a rounded number that later looks like a measurement, and at the scale of
    token supplies the rounding is not small: 10^15 raw units does not survive a double.
    """
    _integer("rational numerator", numerator)
    _integer("rational denominator", denominator)
    if denominator <= 0:
        raise ConcentrationRefused(
            f"a share needs a positive denominator, got {denominator}. A share of nothing is "
            "undefined, not zero")
    divisor = math.gcd(abs(numerator), denominator)
    return {"numerator": numerator // divisor, "denominator": denominator // divisor}


def compare_rationals(first, second):
    """Cross-multiplied comparison. Never converts to a decimal to decide."""
    left = first["numerator"] * second["denominator"]
    right = second["numerator"] * first["denominator"]
    return (left > right) - (left < right)


def assert_rational(value, label):
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise ConcentrationRefused(f"{label} must be a numerator/denominator pair")
    _integer(f"{label} numerator", value["numerator"])
    _integer(f"{label} denominator", value["denominator"])
    if value["denominator"] <= 0:
        raise ConcentrationRefused(f"{label} denominator must be positive")
    if math.gcd(abs(value["numerator"]), value["denominator"]) != 1:
        raise ConcentrationRefused(
            f"{label} is not in lowest terms; two equal shares must have equal representations or "
            "a hash comparison silently says they differ")
    return value


# --------------------------------------------------------------------------------------------
# Cluster adjustment, structurally unavailable
# --------------------------------------------------------------------------------------------

# Deliberately empty. Not "no artifact was supplied" but "no artifact TYPE is acceptable yet".
ACCEPTED_CLUSTER_ARTIFACT_TYPES = ()

CLUSTER_ARTIFACT_REQUIREMENTS = (
    "calibrated against a validation set that is not the one it will be used on",
    "preregistered — the merge rule and its threshold frozen before the cohort was enumerated",
    "complete and point-in-time — every link established from evidence at or before t0, over a "
    "neighbourhood whose completeness is asserted rather than assumed",
    "provenanced — the artifact names its inputs, its rule and its hash",
)


def cluster_adjusted_concentration(_snapshot=None, cluster_artifact=None, **_kwargs):
    """Never returns. Present so that reaching for it is a refusal, not a blank page.

    A cluster-adjusted concentration is the most dangerous number this project could publish: it
    looks like a measurement, it moves in the direction that justifies action, and every input to it
    is a judgement. So the operation is exposed and refuses, rather than being absent and inviting a
    caller to write their own.
    """
    if _looks_like_association_ledger(cluster_artifact):
        raise ClusterAdjustmentRefused(
            "that is a B13b ASSOCIATION EVIDENCE LEDGER, not a cluster map. It declares itself "
            "`uncalibrated_evidence_only`, its links are pairwise observations that explicitly do "
            "not assert common control, and it refuses transitive closure by construction. Passing "
            "it here would launder an explicit 'we do not know' into a merge, and the resulting "
            "number would be indistinguishable from a measured one. "
            + _requirements_sentence())
    raise ClusterAdjustmentRefused(
        "no cluster-adjusted concentration is available. No artifact type is accepted in this pass "
        "and no connected component is inferred from anything. " + _requirements_sentence())


def _requirements_sentence():
    return ("A future artifact must be: "
            + "; ".join(CLUSTER_ARTIFACT_REQUIREMENTS)
            + ". Until one exists and its type is accepted here, this figure does not.")


def _looks_like_association_ledger(artifact):
    """Recognise a B13b ledger by its own declarations rather than by its shape alone."""
    if not isinstance(artifact, dict):
        return False
    if artifact.get("confidence_status") == "uncalibrated_evidence_only":
        return True
    return "links" in artifact and "evidence_hash_chain_sha256" in artifact


def connected_components(*_args, **_kwargs):
    """Never returns. The transitive closure is exactly what would manufacture a cluster."""
    raise ClusterAdjustmentRefused(
        "no connected component is inferred here. A—B and B—C are two observations and never an "
        "A—C link; a component built from them would merge holders on evidence that explicitly "
        "does not support it. " + _requirements_sentence())


# --------------------------------------------------------------------------------------------
# Scans
# --------------------------------------------------------------------------------------------

def _walk(value, path="record"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def assert_no_float(record):
    """No float anywhere. Every figure here is an integer or a ratio of two."""
    for path, value in _walk(record):
        if isinstance(value, float):
            raise ConcentrationRefused(
                f"{path} is the float {value!r}. Shares are exact rationals: a raw supply of 10^15 "
                "units does not survive a double, and a rounded number here later reads as a "
                "measurement")
    return True


def assert_no_judgement(record):
    """Refuse any field whose NAME asserts a threshold, a cluster or a verdict."""
    for path, value in _walk(record):
        if not isinstance(value, dict):
            continue
        for key in value:
            lowered = str(key).lower()
            for banned in FORBIDDEN_FIELD_SUBSTRINGS:
                if banned in lowered:
                    raise ConcentrationRefused(
                        f"{path}.{key} contains {banned!r}. This record may not carry a field whose "
                        "name asserts a cluster, a threshold or a verdict; raw concentration is a "
                        "measurement and everything downstream of it is a decision")
    assert_no_float(record)
    return True


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def _integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConcentrationRefused(f"{label} must be an integer, got {value!r}")
    return value


def _non_negative(label, value):
    _integer(label, value)
    if value < 0:
        raise ConcentrationRefused(f"{label} must not be negative, got {value}")
    return value


def _non_empty(label, value):
    if not isinstance(value, str) or not value:
        raise ConcentrationRefused(f"{label} must be a non-empty string, got {value!r}")
    return value


def assert_account(account, mint, decimals):
    """One token account, fully specified and belonging to this mint."""
    if not isinstance(account, dict):
        raise ConcentrationRefused(f"account must be a mapping, got {type(account).__name__}")
    missing = [field for field in ACCOUNT_FIELDS if field not in account]
    if missing:
        raise ConcentrationRefused(f"account does not state {missing}")
    unknown = [field for field in account if field not in ACCOUNT_FIELDS]
    if unknown:
        raise ConcentrationRefused(f"account carries undeclared fields {sorted(unknown)}")
    _non_empty("token_account", account["token_account"])
    # Each account states its OWN mint and decimals rather than inheriting the snapshot's. An
    # enumeration that pulled in a second mint would otherwise be invisible, and its balances would
    # be summed into a supply they have nothing to do with.
    if account["mint"] != mint:
        raise ConcentrationRefused(
            f"account {account['token_account']} holds mint {account['mint']!r} in a snapshot of "
            f"{mint!r}. Two mints summed into one supply is a concentration figure about neither")
    if account["decimals"] != decimals:
        raise ConcentrationRefused(
            f"account {account['token_account']} states {account['decimals']} decimals against the "
            f"snapshot's {decimals}. Raw units are only comparable at one scale, and mixing them "
            "misstates every share by a power of ten")
    # Negative balances are refused rather than clamped. A negative raw balance means the decode is
    # wrong, and clamping it to zero would turn a broken parse into a plausible holder.
    _non_negative("account raw_units", account["raw_units"])
    if account["role"] not in ROLES:
        raise ConcentrationRefused(
            f"account role {account['role']!r} is not one of {list(ROLES)}. A missing role is not "
            f"{ROLE_USER!r} — it is {ROLE_UNKNOWN!r}, and it must be said out loud")
    if not account["role_evidence"]:
        raise ConcentrationRefused(
            f"account {account['token_account']} states role {account['role']!r} with no evidence; "
            "a role asserted without evidence is a guess that will be read as a fact")
    if account["owner_status"] not in OWNER_STATUSES:
        raise ConcentrationRefused(
            f"owner status {account['owner_status']!r} is not one of {list(OWNER_STATUSES)}")
    if account["owner_status"] == OWNER_EXACT:
        _non_empty("account owner", account["owner"])
        if not account["owner_evidence"]:
            raise ConcentrationRefused(
                f"account {account['token_account']} claims exact owner evidence without stating "
                "any; exact means we looked, not that we are confident")
    else:
        if account["owner"] is not None or account["owner_evidence"]:
            raise ConcentrationRefused(
                f"account {account['token_account']} is unresolved yet names an owner; an "
                "unresolved owner is unknown, and unknown is not a name we happen to have")
    return account


def assert_completeness(completeness):
    if not isinstance(completeness, dict):
        raise ConcentrationRefused("completeness must be a mapping")
    missing = [field for field in COMPLETENESS_FIELDS if field not in completeness]
    if missing:
        raise ConcentrationRefused(f"completeness does not state {missing}")
    unknown = [field for field in completeness if field not in COMPLETENESS_FIELDS]
    if unknown:
        raise ConcentrationRefused(f"completeness carries undeclared fields {sorted(unknown)}")
    if not isinstance(completeness["enumeration_complete"], bool):
        raise ConcentrationRefused("enumeration_complete must be a boolean")
    _non_negative("accounts_enumerated", completeness["accounts_enumerated"])
    _non_empty("enumeration_method", completeness["enumeration_method"])
    if not isinstance(completeness["source_hashes"], list) or not completeness["source_hashes"]:
        raise ConcentrationRefused(
            "completeness must name the sources it was built from; a holder set that cannot name "
            "its source is an assertion")
    for position, digest in enumerate(completeness["source_hashes"]):
        _non_empty(f"source_hashes[{position}]", digest)
    return completeness


def assert_creator_binding(binding):
    if not isinstance(binding, dict):
        raise ConcentrationRefused("creator binding must be a mapping")
    missing = [field for field in CREATOR_BINDING_FIELDS if field not in binding]
    if missing:
        raise ConcentrationRefused(f"creator binding does not state {missing}")
    unknown = [field for field in binding if field not in CREATOR_BINDING_FIELDS]
    if unknown:
        raise ConcentrationRefused(f"creator binding carries undeclared fields {sorted(unknown)}")
    if binding["status"] not in CREATOR_BINDING_STATUSES:
        raise ConcentrationRefused(
            f"creator binding status {binding['status']!r} is not one of "
            f"{list(CREATOR_BINDING_STATUSES)}")
    if binding["status"] == CREATOR_BINDING_EXACT:
        _non_empty("creator binding address", binding["address"])
        if not binding["evidence"]:
            raise ConcentrationRefused(
                "an exact creator binding must show its evidence; without it this is a guess that "
                "will be published as a creator share")
    elif binding["status"] == CREATOR_BINDING_ABSENT:
        if binding["address"] or binding["evidence"]:
            raise ConcentrationRefused(
                "a creator binding declared absent yet names an address; absent means we do not "
                "have one")
    return binding


def assert_snapshot(snapshot):
    """One holder-balance snapshot, fully reconciled. Every unit accounted for or refused."""
    if not isinstance(snapshot, dict):
        raise ConcentrationRefused(f"snapshot must be a mapping, got {type(snapshot).__name__}")
    missing = [field for field in SNAPSHOT_FIELDS if field not in snapshot]
    if missing:
        raise ConcentrationRefused(f"snapshot does not carry {missing}")
    unknown = [field for field in snapshot if field not in SNAPSHOT_FIELDS]
    if unknown:
        raise ConcentrationRefused(
            f"snapshot carries undeclared fields {sorted(unknown)}; a record shape nobody declared "
            "is a record shape nobody reviewed")
    if snapshot["point_in_time_rule"] != POINT_IN_TIME_RULE:
        raise ConcentrationRefused(
            "the point-in-time rule on this snapshot is not the one this module applies")
    _non_empty("mint", snapshot["mint"])
    _non_negative("decimals", snapshot["decimals"])
    _non_negative("declared_supply_units", snapshot["declared_supply_units"])
    _non_empty("receipt_provenance", snapshot["receipt_provenance"])
    _non_empty("source_sha256", snapshot["source_sha256"])

    coordinate = snapshot["as_of"]
    if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
        raise ConcentrationRefused(
            f"snapshot as_of must be a full canonical coordinate {list(COORDINATE_FIELDS)}")
    for field in COORDINATE_FIELDS:
        _integer(f"as_of {field}", coordinate[field])

    accounts = snapshot["accounts"]
    if not isinstance(accounts, list):
        raise ConcentrationRefused("snapshot accounts must be a list")
    seen_accounts = set()
    for account in accounts:
        assert_account(account, snapshot["mint"], snapshot["decimals"])
        if account["token_account"] in seen_accounts:
            raise ConcentrationRefused(
                f"token account {account['token_account']} appears twice. The same account counted "
                "twice inflates its holder's share and the supply at once, and both errors point "
                "the same way")
        seen_accounts.add(account["token_account"])

    completeness = assert_completeness(snapshot["completeness"])
    if completeness["accounts_enumerated"] != len(accounts):
        raise ConcentrationRefused(
            f"completeness says {completeness['accounts_enumerated']} accounts were enumerated but "
            f"{len(accounts)} are present; an enumeration that disagrees with its own output "
            "cannot be reconciled against anything")
    assert_creator_binding(snapshot["creator_binding"])

    held = sum(account["raw_units"] for account in accounts)
    residual = snapshot["declared_supply_units"] - held
    if residual < 0:
        raise ConcentrationRefused(
            f"accounts hold {held} units against a declared supply of "
            f"{snapshot['declared_supply_units']}, a shortfall of {-residual}. Either the supply is "
            "wrong or an account is, and a share computed over either would be wrong by the same "
            "amount")
    if completeness["enumeration_complete"] and residual != 0:
        raise ConcentrationRefused(
            f"the enumeration claims to be complete while {residual} units are unaccounted for. "
            "Complete means every unit is somewhere; a residual is exactly the evidence that it is "
            "not")
    assert_no_judgement(snapshot)
    return snapshot


def snapshot_hash(snapshot):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}).encode("utf-8")).hexdigest()


def build_snapshot(mint, decimals, as_of, receipt_provenance, accounts, declared_supply_units,
                   completeness, creator_binding=None, source_sha256=None):
    """Assemble and validate one snapshot."""
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "point_in_time_rule": POINT_IN_TIME_RULE,
        "mint": mint,
        "decimals": decimals,
        "as_of": {field: as_of[field] for field in COORDINATE_FIELDS},
        "receipt_provenance": receipt_provenance,
        "accounts": [dict(account) for account in accounts],
        "declared_supply_units": declared_supply_units,
        "completeness": dict(completeness),
        "creator_binding": dict(creator_binding or absent_creator_binding()),
        "source_sha256": source_sha256 or "",
        "snapshot_sha256": None,
    }
    assert_snapshot(snapshot)
    snapshot["snapshot_sha256"] = snapshot_hash(snapshot)
    return snapshot


def absent_creator_binding():
    return {"status": CREATOR_BINDING_ABSENT, "address": None, "evidence": None}


# --------------------------------------------------------------------------------------------
# Point in time
# --------------------------------------------------------------------------------------------

def snapshot_key(snapshot):
    return tuple(snapshot["as_of"][field] for field in COORDINATE_FIELDS)


def available_at(snapshot, t0):
    """Whether this snapshot may inform a decision at t0. Inclusive at t0."""
    return snapshot_key(snapshot) <= tuple(B10B.canonical_key(t0))


def require_available_at(snapshot, t0):
    if not available_at(snapshot, t0):
        raise ConcentrationRefused(
            f"this snapshot is as of {snapshot_key(snapshot)}, after the decision at "
            f"{tuple(B10B.canonical_key(t0))}. The balances that existed after a decision are not "
            "the balances it was made against, and using them would encode the outcome in the input")
    return True


def select_snapshot(snapshots, t0):
    """The latest snapshot a decision at t0 could have used, or an Absent saying why not."""
    usable = sorted((s for s in snapshots if available_at(s, t0)),
                    key=lambda s: (snapshot_key(s), s["snapshot_sha256"]))
    if not usable:
        return B13C.absent(B13C.ABSENT_NOT_YET_KNOWN,
                           "no holder snapshot exists at or before this decision, so nothing is "
                           "known about concentration here — which is not the same as it being low")
    return usable[-1]


# --------------------------------------------------------------------------------------------
# Concentration
# --------------------------------------------------------------------------------------------

def _sorted_balances(pairs):
    """Descending by balance, then ascending by key. Deterministic under ties."""
    return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))


def _top_k(balances, k, denominator_units):
    """The top-k share, and how many entries actually went into it.

    The count is published because k may exceed the number of holders. A "top 10" over seven
    accounts is the whole set, and a reader who is not told that will compare it against a genuine
    top 10 somewhere else.
    """
    taken = balances[:k]
    total = sum(units for _, units in taken)
    return {"share": rational(total, denominator_units),
            "units": total,
            "entries_available": len(balances),
            "entries_counted": len(taken)}


def _herfindahl(balances, denominator_units):
    """Σ(bᵢ/D)² as one exact rational: Σbᵢ² over D².

    Computed as a single ratio rather than a sum of ratios, because summing rounded squares is
    where a float implementation loses the small holders entirely.
    """
    return rational(sum(units * units for _, units in balances),
                    denominator_units * denominator_units)


def _grouped_balances(accounts, grouping):
    """Account-level always; owner-level only where every owner is resolved."""
    if grouping == GROUPING_ACCOUNT:
        return [(account["token_account"], account["raw_units"]) for account in accounts]
    totals = {}
    for account in accounts:
        totals[account["owner"]] = totals.get(account["owner"], 0) + account["raw_units"]
    return sorted(totals.items())


def owner_grouping_available(accounts):
    """Whether accounts may be collapsed to owners, and why not when they may not.

    One unresolved account could belong to the largest holder, so a top-1 share computed without it
    is a lower bound rather than a measurement — and a lower bound published as a share is the kind
    of number that gets compared against a threshold.
    """
    unresolved = [a for a in accounts if a["owner_status"] != OWNER_EXACT]
    if unresolved:
        return False, (f"{len(unresolved)} of {len(accounts)} accounts have no exact owner "
                       "evidence; one of them could belong to the largest holder, so collapsing "
                       "would publish a lower bound as a share")
    return True, None


def _share_block(accounts, denominator_units, denominator_name, grouping, scope_roles):
    """One view: which balances were ranked, over which denominator, stated on its face.

    `scope_roles` is published because the two views differ in NUMERATOR as well as denominator.
    Under total supply every account is ranked, including the curve's; under circulating user only
    user balances are. A reader given the ratio without the scope cannot tell which they have.
    """
    balances = _sorted_balances([(key, units) for key, units
                                 in _grouped_balances(accounts, grouping) if units > 0])
    block = {"denominator_units": denominator_units,
             "denominator_name": denominator_name,
             "grouping": grouping,
             "scope_roles": list(scope_roles),
             "holder_count": len(balances)}
    for k in TOP_K:
        block[f"top_{k}"] = _top_k(balances, k, denominator_units)
    block["herfindahl"] = _herfindahl(balances, denominator_units)
    return block


def creator_share(snapshot, scope_accounts, denominator_units):
    """The creator's share, or an Absent saying exactly why there is not one."""
    binding = snapshot["creator_binding"]
    if binding["status"] != CREATOR_BINDING_EXACT:
        return B13C.absent(
            B13C.ABSENT_UNKNOWN,
            f"the creator binding is {binding['status']!r}, so we do not know which address is the "
            "creator's; a share attributed on a guess is worse than no share")
    available, reason = owner_grouping_available(snapshot["accounts"])
    if not available:
        return B13C.absent(
            B13C.ABSENT_UNKNOWN,
            f"the creator's holdings cannot be totalled: {reason}. An unresolved account could be "
            "the creator's, so any figure here would be a lower bound")
    if denominator_units <= 0:
        return B13C.absent(B13C.ABSENT_UNDEFINED,
                           "the denominator is zero, so a share of it does not exist")
    # Scoped exactly like the denominator. A creator holding through an excluded role would
    # otherwise contribute to the numerator but not the denominator, and produce a share above one.
    units = sum(account["raw_units"] for account in scope_accounts
                if account["owner"] == binding["address"])
    return {"units": units, "share": rational(units, denominator_units)}


def compute_concentration(snapshot):
    """Every raw figure, under both denominators, with nothing collapsed that cannot be."""
    assert_snapshot(snapshot)
    accounts = snapshot["accounts"]
    positive = [a for a in accounts if a["raw_units"] > 0]
    held = sum(a["raw_units"] for a in accounts)
    residual = snapshot["declared_supply_units"] - held

    by_role = {}
    for role in ROLES:
        in_role = [a for a in accounts if a["role"] == role]
        by_role[role] = {"account_count": len(in_role),
                         "units": sum(a["raw_units"] for a in in_role)}

    # Built by SUMMING what is included, never by subtracting exclusions from supply.
    circulating = sum(by_role[role]["units"] for role in CIRCULATING_USER_ROLES)
    denominator_units = {DENOMINATOR_TOTAL_SUPPLY: snapshot["declared_supply_units"],
                         DENOMINATOR_CIRCULATING_USER: circulating}

    owner_ok, owner_reason = owner_grouping_available(accounts)
    user_accounts = [a for a in accounts if a["role"] in CIRCULATING_USER_ROLES]

    shares, owner_shares, creator = {}, {}, {}
    for name in DENOMINATORS:
        units = denominator_units[name]
        scope = accounts if name == DENOMINATOR_TOTAL_SUPPLY else user_accounts
        if units <= 0:
            # Undefined, not zero. Every downstream field says so rather than showing a 0/1.
            shares[name] = {"denominator_units": units, "denominator_name": name,
                            "defined": False,
                            "undefined_reason": "the denominator is zero, so no share of it exists"}
            owner_shares[name] = dict(shares[name])
            creator[name] = {"defined": False,
                             "undefined_reason": "the denominator is zero, so no share of it "
                                                 "exists"}
            continue
        scope_roles = ROLES if name == DENOMINATOR_TOTAL_SUPPLY else CIRCULATING_USER_ROLES
        shares[name] = dict(_share_block(scope, units, name, GROUPING_ACCOUNT, scope_roles),
                            defined=True)
        if owner_ok:
            owner_shares[name] = dict(
                _share_block(scope, units, name, GROUPING_OWNER, scope_roles), defined=True)
        else:
            owner_shares[name] = {"denominator_units": units, "denominator_name": name,
                                  "defined": False, "undefined_reason": owner_reason}
        value = creator_share(snapshot, scope, units)
        creator[name] = ({"defined": False, "undefined_reason": value.detail}
                         if is_absent(value) else dict(value, defined=True))

    distinct_owners = len({a["owner"] for a in accounts if a["owner_status"] == OWNER_EXACT})
    record = {
        "schema_version": SCHEMA_VERSION,
        "point_in_time_rule": POINT_IN_TIME_RULE,
        "denominator_rule": DENOMINATOR_RULE,
        "mint": snapshot["mint"],
        "as_of": dict(snapshot["as_of"]),
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "accounting": {
            "accounts_enumerated": len(accounts),
            "accounts_with_positive_balance": len(positive),
            # Kept, not dropped. A closed account that still exists is evidence about the holder
            # set, and silently removing it changes the holder count nobody was told about.
            "zero_balance_account_count_observed": len(accounts) - len(positive),
            "unresolved_owner_account_count":
                len([a for a in accounts if a["owner_status"] != OWNER_EXACT]),
            "distinct_owners_resolved": distinct_owners,
            "units_held_in_accounts": held,
            "declared_supply_units": snapshot["declared_supply_units"],
            "supply_residual_units": residual,
            "enumeration_complete": snapshot["completeness"]["enumeration_complete"],
            "owner_grouping_available": owner_ok,
            "owner_grouping_unavailable_reason": owner_reason,
        },
        "by_role": by_role,
        "shares": {"by_account": shares, "by_owner": owner_shares},
        "creator": creator,
        "concentration_sha256": None,
    }
    assert_concentration(record)
    record["concentration_sha256"] = concentration_hash(record)
    return record


def assert_concentration(record):
    """Every gate on the output, in one call."""
    if not isinstance(record, dict):
        raise ConcentrationRefused(f"concentration must be a mapping, got {type(record).__name__}")
    missing = [field for field in CONCENTRATION_FIELDS if field not in record]
    if missing:
        raise ConcentrationRefused(f"concentration does not carry {missing}")
    unknown = [field for field in record if field not in CONCENTRATION_FIELDS]
    if unknown:
        raise ConcentrationRefused(f"concentration carries undeclared fields {sorted(unknown)}")
    if record["point_in_time_rule"] != POINT_IN_TIME_RULE:
        raise ConcentrationRefused("the point-in-time rule on this record is not this module's")
    if record["denominator_rule"] != DENOMINATOR_RULE:
        raise ConcentrationRefused("the denominator rule on this record is not this module's")
    if set(record["by_role"]) != set(ROLES):
        raise ConcentrationRefused(
            f"by_role covers {sorted(record['by_role'])}, contract says {sorted(ROLES)}; a role "
            "left out of the accounting is a balance nobody has to explain")
    for grouping in ("by_account", "by_owner"):
        published = set(record["shares"][grouping])
        if published != set(DENOMINATORS):
            raise ConcentrationRefused(
                f"shares.{grouping} publishes {sorted(published)} but both of "
                f"{list(DENOMINATORS)} are required. Concentration is whatever the denominator says "
                "it is, so one of them alone is a choice made on the reader's behalf")
    if set(record["creator"]) != set(DENOMINATORS):
        raise ConcentrationRefused("the creator share must be published under both denominators")

    accounting = record["accounting"]
    missing_accounting = [field for field in ACCOUNTING_FIELDS if field not in accounting]
    if missing_accounting:
        raise ConcentrationRefused(f"accounting does not state {missing_accounting}")
    if (accounting["accounts_with_positive_balance"]
            + accounting["zero_balance_account_count_observed"]
            != accounting["accounts_enumerated"]):
        raise ConcentrationRefused(
            "the positive and zero-balance account counts do not sum to the enumeration; an "
            "account in neither bucket is one that quietly left the holder set")
    if accounting["units_held_in_accounts"] + accounting["supply_residual_units"] \
            != accounting["declared_supply_units"]:
        raise ConcentrationRefused(
            "held units plus the residual do not equal the declared supply; the residual exists "
            "precisely so that every unit is somewhere")
    if accounting["enumeration_complete"] and accounting["supply_residual_units"] != 0:
        raise ConcentrationRefused(
            "a complete enumeration with a non-zero residual; complete means every unit is "
            "accounted for")
    role_units = sum(block["units"] for block in record["by_role"].values())
    role_accounts = sum(block["account_count"] for block in record["by_role"].values())
    if role_units != accounting["units_held_in_accounts"]:
        raise ConcentrationRefused(
            f"the roles account for {role_units} units but {accounting['units_held_in_accounts']} "
            "are held; a balance that belongs to no role is one an exclusion could hide")
    if role_accounts != accounting["accounts_enumerated"]:
        raise ConcentrationRefused("the roles do not account for every enumerated account")

    circulating = sum(record["by_role"][role]["units"] for role in CIRCULATING_USER_ROLES)
    published = record["shares"]["by_account"][DENOMINATOR_CIRCULATING_USER]["denominator_units"]
    if published != circulating:
        raise ConcentrationRefused(
            f"the circulating-user denominator is published as {published} but the user-role "
            f"balances sum to {circulating}. The denominator is the SUM of what was included, and "
            "a mismatch is exactly how an exclusion hides")
    total = record["shares"]["by_account"][DENOMINATOR_TOTAL_SUPPLY]["denominator_units"]
    if total != accounting["declared_supply_units"]:
        raise ConcentrationRefused("the total-supply denominator is not the declared supply")

    for grouping in ("by_account", "by_owner"):
        for name, block in record["shares"][grouping].items():
            if not block.get("defined"):
                continue
            _assert_share_block(f"shares.{grouping}.{name}", block)
    assert_no_judgement(record)
    return record


def _assert_share_block(label, block):
    for k in TOP_K:
        entry = block[f"top_{k}"]
        assert_rational(entry["share"], f"{label}.top_{k}.share")
        _non_negative(f"{label}.top_{k}.units", entry["units"])
        if entry["entries_counted"] > k:
            raise ConcentrationRefused(
                f"{label}.top_{k} counted {entry['entries_counted']} entries; a top-{k} that "
                "counts more than k is not a top-k")
        if entry["entries_counted"] != min(k, entry["entries_available"]):
            raise ConcentrationRefused(
                f"{label}.top_{k} counted {entry['entries_counted']} of "
                f"{entry['entries_available']} available; it must take exactly "
                f"min({k}, available), and a short count silently understates concentration")
    for smaller, larger in zip(TOP_K, TOP_K[1:]):
        if compare_rationals(block[f"top_{smaller}"]["share"],
                             block[f"top_{larger}"]["share"]) > 0:
            raise ConcentrationRefused(
                f"{label}: top-{smaller} exceeds top-{larger}, which is arithmetically impossible "
                "and means the ordering or the summation is wrong")
    assert_rational(block["herfindahl"], f"{label}.herfindahl")
    if block["holder_count"] != block["top_1"]["entries_available"]:
        raise ConcentrationRefused(
            f"{label}: the holder count disagrees with the number of ranked balances")
    return True


def concentration_hash(record):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in record.items()
         if k != "concentration_sha256"}).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "point_in_time_rule": POINT_IN_TIME_RULE,
        "denominator_rule": DENOMINATOR_RULE,
        "roles": list(ROLES),
        "role_meaning": ROLE_MEANING,
        "circulating_user_roles": list(CIRCULATING_USER_ROLES),
        "owner_statuses": list(OWNER_STATUSES),
        "denominators": list(DENOMINATORS),
        "groupings": list(GROUPINGS),
        "top_k": list(TOP_K),
        "creator_binding_statuses": list(CREATOR_BINDING_STATUSES),
        "accepted_cluster_artifact_types": list(ACCEPTED_CLUSTER_ARTIFACT_TYPES),
        "future_cluster_artifact_requirements": list(CLUSTER_ARTIFACT_REQUIREMENTS),
        "cluster_adjustment_available": False,
        "connected_components_inferred": False,
        "thresholds_chosen": [],
        "floats_used": False,
        "refusing_operations": ["cluster_adjusted_concentration", "connected_components"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ConcentrationRefused: {error}", file=sys.stderr)
        sys.exit(2)
