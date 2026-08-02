"""B13b — point-in-time actor association EVIDENCE LEDGER. Offline library. No clusters.

What this module is
-------------------
A ledger of PAIRWISE EVIDENCE about actors, computed as of exactly t0. Each link says "here is what
was observed about these two addresses, on or before this instant, with the coordinate and source
hash of every observation". It is a record of evidence, not a conclusion drawn from it.

What this module refuses to be
------------------------------
It does not infer clusters, does not emit a `cluster_id`, does not merge, does not take a transitive
closure, does not compute a probability, and never claims two addresses share an owner. Those are a
separate task behind a separate preregistration, and every one of them is a judgement that would
travel downstream wearing the costume of a fact.

Four refusals are structural rather than promised:

1. **A link must be witnessed.** Every evidence item names its own `witness_addresses`, and both
   endpoints of the link must appear in at least one of them. So A—B evidence witnesses {A, B} and
   B—C evidence witnesses {B, C}; neither witnesses {A, C}, and no A—C link can be assembled from
   them. Non-transitivity is a property of the data structure, not a rule somebody remembered.
2. **Identity equality is a different relation type from association.** Exact address equality is
   the only relation that asserts sameness, it requires `address_a == address_b`, and no association
   evidence may appear in it.
3. **Calibration is absent and says so.** Every link and the ledger itself carry
   `confidence_status = "uncalibrated_evidence_only"`, no float may appear anywhere in the record,
   and a scan refuses any field whose name asserts a cluster, a probability or an owner.
4. **The clustering operations fail closed rather than being merely absent.** `cluster_id`,
   `connected_component`, `merge_addresses` and `association_probability` all exist and all raise.
   An operation that is simply missing invites a caller to write their own; one that refuses,
   loudly, tells them why they should not.

Counter-evidence is mandatory, not optional
-------------------------------------------
A shared service wallet is the obvious false link: an exchange hot wallet funds thousands of
unrelated actors, and "shared funder" between two of its customers is evidence of nothing. So every
link carries `counter_evidence`, and an address whose role has not been established is recorded as
`unknown` — which raises the counter-evidence flag rather than lowering it. Absence of a known
service role is not evidence that the address is not a service.

Not chosen here, deliberately: the lookback, the repetition threshold, any probability calibration
and any merge threshold. Each needs its own preregistration written before the actors it will be
applied to are known.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13A = _load("b13a_history", "b13a_history.py")
B10B = B13A.B10B

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B13A.COORDINATE_FIELDS

BOUNDARY_RULE = B13A.BOUNDARY_RULE

CONFIDENCE_STATUS = "uncalibrated_evidence_only"
CONFIDENCE_STATUS_MEANING = (
    "Every item in this ledger is a raw observation with a coordinate and a source hash. Nothing "
    "here has been calibrated against any outcome, no weight has been fitted, and no threshold has "
    "been chosen. A reader may not convert these counts into a probability that two addresses share "
    "an owner, because no such conversion has been validated and this module will not supply one.")

# --------------------------------------------------------------------------------------------
# Relations: exact identity is not association, and the type system says so
# --------------------------------------------------------------------------------------------

RELATION_IDENTITY_EQUALITY = "identity_equality"
RELATION_ASSOCIATION_EVIDENCE = "association_evidence"
RELATION_TYPES = (RELATION_IDENTITY_EQUALITY, RELATION_ASSOCIATION_EVIDENCE)

# --------------------------------------------------------------------------------------------
# Evidence kinds, each carrying what it does NOT mean
# --------------------------------------------------------------------------------------------

E00_EXACT_ADDRESS_EQUALITY = "E00_exact_address_equality"
E01_DIRECT_TRANSFER = "E01_direct_transfer"
E02_SHARED_FUNDER = "E02_shared_funder"
E03_REPEATED_COUNTERPARTY = "E03_repeated_counterparty"
E04_CO_OCCURRENCE_IN_TRANSACTION = "E04_co_occurrence_in_transaction"
E05_CO_SIGNING_LAUNCH_ROLES = "E05_co_signing_launch_roles"

EVIDENCE_KINDS = (E00_EXACT_ADDRESS_EQUALITY, E01_DIRECT_TRANSFER, E02_SHARED_FUNDER,
                  E03_REPEATED_COUNTERPARTY, E04_CO_OCCURRENCE_IN_TRANSACTION,
                  E05_CO_SIGNING_LAUNCH_ROLES)

# The second half of each sentence is the load-bearing half. It travels on the record so a reader
# three phases downstream cannot quietly upgrade the first half into the claim it is not.
EVIDENCE_MEANING = {
    E00_EXACT_ADDRESS_EQUALITY:
        "the same address string occupies two roles. This IS identity, and it is the only relation "
        "here that asserts sameness.",
    E01_DIRECT_TRANSFER:
        "lamports moved from one address to the other. This is evidence of a TRANSFER and of "
        "nothing else. Everyone who has ever paid an exchange has a direct transfer to it.",
    E02_SHARED_FUNDER:
        "one address sent lamports to both endpoints, at or before t0. This is evidence of a shared "
        "COUNTERPARTY, not of common control; a service wallet funds thousands of unrelated actors.",
    E03_REPEATED_COUNTERPARTY:
        "the endpoints transacted with each other more than once. The raw count is published and "
        "NOT compared against any threshold, because no threshold has been preregistered.",
    E04_CO_OCCURRENCE_IN_TRANSACTION:
        "both addresses appear in the same transaction. Co-presence in a transaction one of them "
        "did not sign is evidence of being named, not of acting.",
    E05_CO_SIGNING_LAUNCH_ROLES:
        "the two addresses hold different roles in the same launch. Evidence of a shared ACTION, "
        "which is weaker than shared control and is not the same thing.",
}

DIRECTION_A_TO_B = "a_to_b"
DIRECTION_B_TO_A = "b_to_a"
DIRECTION_BOTH = "both_directions"
DIRECTION_NONE = "not_directional"
DIRECTIONS = (DIRECTION_A_TO_B, DIRECTION_B_TO_A, DIRECTION_BOTH, DIRECTION_NONE)

# Which kinds carry a direction at all. A kind that is directional may never be recorded as
# `not_directional`, because a dropped direction turns "A funded B" into "A and B are connected" —
# and the two support completely different conclusions.
DIRECTIONAL_KINDS = (E01_DIRECT_TRANSFER, E03_REPEATED_COUNTERPARTY)

EVIDENCE_ITEM_FIELDS = ("kind", "direction", "witness_addresses", "coordinates",
                        "source_sha256_list", "facts", "detail")

# --------------------------------------------------------------------------------------------
# Service roles: the obvious false link, named
# --------------------------------------------------------------------------------------------

ROLE_UNKNOWN = "unknown"
ROLE_EXCHANGE = "exchange"
ROLE_ROUTER = "router"
ROLE_FEE_ACCOUNT = "fee_account"
ROLE_PROGRAM_OWNED = "program_owned"
ROLE_NOT_A_SERVICE = "established_not_a_service"
SERVICE_ROLES = (ROLE_UNKNOWN, ROLE_EXCHANGE, ROLE_ROUTER, ROLE_FEE_ACCOUNT, ROLE_PROGRAM_OWNED,
                 ROLE_NOT_A_SERVICE)
ESTABLISHED_SERVICE_ROLES = (ROLE_EXCHANGE, ROLE_ROUTER, ROLE_FEE_ACCOUNT, ROLE_PROGRAM_OWNED)

X01_ENDPOINT_ROLE_UNKNOWN = "X01_endpoint_role_unknown"
X02_ENDPOINT_IS_KNOWN_SERVICE = "X02_endpoint_is_known_service"
X03_INTERMEDIARY_ROLE_UNKNOWN = "X03_intermediary_role_unknown"
X04_INTERMEDIARY_IS_KNOWN_SERVICE = "X04_intermediary_is_known_service"
X05_EVIDENCE_FROM_INCOMPLETE_HISTORY = "X05_evidence_from_incomplete_history"
COUNTER_EVIDENCE_CODES = (X01_ENDPOINT_ROLE_UNKNOWN, X02_ENDPOINT_IS_KNOWN_SERVICE,
                          X03_INTERMEDIARY_ROLE_UNKNOWN, X04_INTERMEDIARY_IS_KNOWN_SERVICE,
                          X05_EVIDENCE_FROM_INCOMPLETE_HISTORY)

# --------------------------------------------------------------------------------------------
# Completeness of the neighbourhood, propagated from B13a
# --------------------------------------------------------------------------------------------

G01_CONTRIBUTING_HISTORY_INCOMPLETE = "G01_contributing_history_incomplete"
G02_LOOKBACK_NOT_CHOSEN = "G02_lookback_not_chosen"
G03_ENDPOINT_HISTORY_ABSENT = "G03_endpoint_history_absent"
G04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0 = "G04_unresolved_evidence_at_or_before_t0"
NEIGHBOURHOOD_REASON_CODES = (G01_CONTRIBUTING_HISTORY_INCOMPLETE, G02_LOOKBACK_NOT_CHOSEN,
                              G03_ENDPOINT_HISTORY_ABSENT,
                              G04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0)

# --------------------------------------------------------------------------------------------
# Record shape
# --------------------------------------------------------------------------------------------

GROUPING_FIELDS = ("address_a", "address_b", "relation_type")

# Numeric and boolean only. Same rule as B13a and B11b, for the same reason: it is checkable
# without anyone having to notice which strings happen to be identities.
LINK_FEATURE_FIELDS = (
    "counts_are_lower_bounds",
    "evidence_item_count_observed",
    "exact_address_equality_count_observed",
    "direct_transfer_count_observed",
    "shared_funder_count_observed",
    "repeated_counterparty_count_observed",
    "co_occurrence_count_observed",
    "co_signing_count_observed",
    "lamports_a_to_b_observed",
    "lamports_b_to_a_observed",
    "distinct_shared_funder_count_observed",
    "counter_evidence_present",
    "neighbourhood_complete",
)

LINK_FIELDS = ("relation_type", "grouping", "features", "evidence", "counter_evidence",
               "completeness", "confidence_status", "link_sha256")

LOOKBACK_FIELDS = ("lookback_slots", "lookback_chosen", "preregistration_reference", "rationale")

ACCOUNTING_FIELDS = ("focus_addresses", "focus_address_list", "pairs_considered", "links_emitted",
                     "links_by_relation", "evidence_items", "evidence_by_kind", "events_supplied",
                     "events_visible", "events_discarded_after_t0")

LEDGER_FIELDS = ("schema_version", "boundary_rule", "confidence_status",
                 "confidence_status_meaning", "as_of", "coverage", "lookback",
                 "role_register_provenance", "links", "accounting",
                 "evidence_hash_chain_sha256", "ledger_sha256")

# Any key whose name asserts a conclusion this module is not entitled to reach. Checked by name
# rather than by value, because the damage is done the moment a downstream reader SEES the name.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "cluster", "probability", "same_owner", "sameowner", "owner_id", "entity_id", "component",
    "likelihood", "posterior", "confidence_score", "merge", "calibrat", "p_same", "score",
)


class AssociationRefused(B13A.HistoryRefused):
    """Raised when an association ledger cannot be built without asserting something untrue."""


class ClusterRefused(AssociationRefused):
    """Raised when a caller asks this module for a cluster, a merge or a probability.

    A separate class because it is a categorically different refusal: the request is not malformed,
    it is out of scope, and the caller needs to know the difference between "fix your input" and
    "this question has not been earned yet".
    """


# --------------------------------------------------------------------------------------------
# The operations that fail closed
# --------------------------------------------------------------------------------------------

_CLUSTER_REFUSAL = (
    "This is an uncalibrated evidence ledger, not a clustering. {what} requires a merge rule, a "
    "threshold and a calibration, none of which has been preregistered, and each of which is a "
    "judgement that would travel downstream indistinguishable from an observation. Funding-cluster "
    "leakage also remains an open gate: a cluster built from evidence at or before t0 can still "
    "encode which actors turned out to matter. Preregister the rule first.")


def cluster_id(*_args, **_kwargs):
    """Never returns. Present so that reaching for a cluster is a refusal, not a blank page."""
    raise ClusterRefused(_CLUSTER_REFUSAL.format(what="A cluster identifier"))


def connected_component(*_args, **_kwargs):
    """Never returns. The transitive closure is exactly the operation this ledger forbids."""
    raise ClusterRefused(_CLUSTER_REFUSAL.format(
        what="A connected component") + " A—B and B—C are two observations, never an A—C link.")


def merge_addresses(*_args, **_kwargs):
    """Never returns."""
    raise ClusterRefused(_CLUSTER_REFUSAL.format(what="Merging two addresses into one entity"))


def association_probability(*_args, **_kwargs):
    """Never returns."""
    raise ClusterRefused(_CLUSTER_REFUSAL.format(
        what="A probability that two addresses share an owner"))


def cluster_adjusted_concentration(*_args, **_kwargs):
    """Never returns. A concentration adjusted by an uncalibrated cluster is a fabricated number."""
    raise ClusterRefused(_CLUSTER_REFUSAL.format(what="A cluster-adjusted concentration"))


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
    """No float anywhere. A calibrated number would arrive as one, and this catches it by type."""
    for path, value in _walk(record):
        if isinstance(value, float):
            raise AssociationRefused(
                f"{path} is the float {value!r}. No float may appear in this ledger: every figure "
                "here is a count of observations, and a non-integer is a number somebody computed")
    return True


def assert_uncalibrated(record):
    """Refuse any field whose NAME asserts a cluster, a probability or an owner.

    By name rather than by value, because the damage is done the moment a downstream reader sees
    the name. A field called `cluster_id` holding the string "none" still teaches the next person
    that clusters are something this record has.
    """
    for path, value in _walk(record):
        if not isinstance(value, dict):
            continue
        for key in value:
            lowered = str(key).lower()
            for banned in FORBIDDEN_FIELD_SUBSTRINGS:
                if banned in lowered:
                    raise AssociationRefused(
                        f"{path}.{key} contains {banned!r}. This ledger may not carry a field whose "
                        "name asserts a cluster, a probability, a score or an owner; the name alone "
                        "would tell a later reader that such a thing had been established here")
    assert_no_float(record)
    return True


def assert_no_identity_in_features(features, label="link"):
    """No string in a feature block, ever. Identities live in grouping and evidence."""
    for field, value in features.items():
        if isinstance(value, str):
            raise AssociationRefused(
                f"{label} feature {field!r} is the string {value!r}. NO STRING MAY APPEAR IN A "
                "FEATURE BLOCK — that is what keeps an address out of a model without anyone "
                "having to notice which strings are addresses")
        if value is not None and not isinstance(value, (int, bool)):
            raise AssociationRefused(
                f"{label} feature {field!r} is a {type(value).__name__}; features are integers, "
                "booleans or null")
    return True


def assert_disjoint_blocks(grouping_fields, feature_fields):
    """No field may be both a grouping key and a feature.

    Takes its field sets as arguments so the check is reachable; with the shipped tuples it can
    never fire, and a guard nobody can make fire is a guard nobody can show works.
    """
    overlap = set(grouping_fields) & set(feature_fields)
    if overlap:
        raise AssociationRefused(
            f"{sorted(overlap)} is both a grouping key and a feature; an identity that is also a "
            "feature is an identity used for prediction")
    return True


# --------------------------------------------------------------------------------------------
# Evidence items
# --------------------------------------------------------------------------------------------

def _non_empty_address(label, value):
    if not isinstance(value, str) or not value:
        raise AssociationRefused(f"{label} must be a non-empty address string, got {value!r}")
    return value


def assert_coordinate(coordinate, label):
    if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
        raise AssociationRefused(
            f"{label} must carry a full canonical coordinate {list(COORDINATE_FIELDS)}")
    for field in COORDINATE_FIELDS:
        value = coordinate[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise AssociationRefused(f"{label} coordinate {field} is not an integer")
    return tuple(coordinate[field] for field in COORDINATE_FIELDS)


def assert_evidence_item(item, endpoints, t0_key):
    """One piece of evidence: typed, witnessed, coordinated, sourced, and at or before t0."""
    if not isinstance(item, dict):
        raise AssociationRefused(f"evidence item must be a mapping, got {type(item).__name__}")
    missing = [field for field in EVIDENCE_ITEM_FIELDS if field not in item]
    if missing:
        raise AssociationRefused(f"evidence item does not state {missing}")
    unknown = [field for field in item if field not in EVIDENCE_ITEM_FIELDS]
    if unknown:
        raise AssociationRefused(f"evidence item carries undeclared fields {sorted(unknown)}")
    if item["kind"] not in EVIDENCE_KINDS:
        raise AssociationRefused(
            f"evidence kind {item['kind']!r} is not one of {list(EVIDENCE_KINDS)}")
    if item["direction"] not in DIRECTIONS:
        raise AssociationRefused(
            f"evidence direction {item['direction']!r} is not one of {list(DIRECTIONS)}")
    if item["kind"] in DIRECTIONAL_KINDS and item["direction"] == DIRECTION_NONE:
        raise AssociationRefused(
            f"{item['kind']} is directional but this item records no direction. A dropped direction "
            "turns 'A funded B' into 'A and B are connected', and those support different "
            "conclusions")
    if item["kind"] not in DIRECTIONAL_KINDS and item["direction"] != DIRECTION_NONE:
        raise AssociationRefused(
            f"{item['kind']} is not directional but this item claims direction "
            f"{item['direction']!r}; an invented direction is worse than none")

    witnesses = item["witness_addresses"]
    if not isinstance(witnesses, list) or not witnesses:
        raise AssociationRefused("evidence item must name the addresses it witnesses")
    for address in witnesses:
        _non_empty_address("witness address", address)
    if list(witnesses) != sorted(witnesses):
        raise AssociationRefused("witness addresses must be sorted, so the same evidence hashes the "
                                 "same way whichever order it was assembled in")
    # THE NON-TRANSITIVITY MECHANISM. Both endpoints must be named by the evidence itself, so no
    # link can exist that some single observation did not witness. A—B and B—C witness {A,B} and
    # {B,C}; neither witnesses {A,C}, and therefore no A—C link can be assembled from them.
    if not set(endpoints).issubset(set(witnesses)):
        raise AssociationRefused(
            f"evidence witnesses {sorted(set(witnesses))} but this link is between "
            f"{sorted(set(endpoints))}. Every link must be witnessed by evidence naming BOTH of its "
            "endpoints; this is what makes A—B plus B—C incapable of manufacturing A—C")

    coordinates = item["coordinates"]
    if not isinstance(coordinates, list) or not coordinates:
        raise AssociationRefused(
            f"{item['kind']} evidence carries no coordinate; an observation that cannot say where "
            "it happened cannot be checked against the boundary")
    keys = [assert_coordinate(c, f"{item['kind']} evidence") for c in coordinates]
    for key in keys:
        if key > tuple(t0_key):
            raise AssociationRefused(
                f"{item['kind']} evidence at {key} is after t0 {tuple(t0_key)}. An association "
                "assembled from the future is the same leak as a feature assembled from it")
    if keys != sorted(keys):
        raise AssociationRefused(f"{item['kind']} evidence coordinates are not canonically ordered")

    sources = item["source_sha256_list"]
    if not isinstance(sources, list) or len(sources) != len(coordinates):
        raise AssociationRefused(
            f"{item['kind']} evidence has {len(coordinates)} coordinates but "
            f"{len(sources) if isinstance(sources, list) else '?'} source hashes; each observation "
            "must name the evidence it came from")
    for source in sources:
        if not isinstance(source, str) or not source:
            raise AssociationRefused(f"{item['kind']} evidence has an empty source hash")
    if not isinstance(item["facts"], dict):
        raise AssociationRefused(f"{item['kind']} evidence facts must be a mapping")
    if not isinstance(item["detail"], str) or not item["detail"]:
        raise AssociationRefused(f"{item['kind']} evidence states no detail")
    return item


def evidence_hash(item):
    return hashlib.sha256(B10B.canonical_json(item).encode("utf-8")).hexdigest()


def ordered_evidence(items):
    """Canonically ordered and duplicate-free. Arrival order is never trusted."""
    decorated, seen = [], set()
    for position, item in enumerate(items):
        digest = evidence_hash(item)
        if digest in seen:
            raise AssociationRefused(
                f"evidence item {position} duplicates an earlier one ({digest[:12]}); the same "
                "observation counted twice looks like two independent ones, which is exactly the "
                "error an uncalibrated ledger must not make on a reader's behalf")
        seen.add(digest)
        first = tuple(item["coordinates"][0][field] for field in COORDINATE_FIELDS)
        decorated.append(((first, item["kind"], digest), item))
    decorated.sort(key=lambda pair: pair[0])
    return [item for _, item in decorated], [key[2] for key, _ in decorated]


# --------------------------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------------------------

def assert_role_register(register):
    """Established roles only. Everything absent is `unknown`, and unknown counts against a link."""
    if register is None:
        return {}
    if not isinstance(register, dict):
        raise AssociationRefused("role register must be a mapping of address to role entry")
    for address, entry in register.items():
        _non_empty_address("role register key", address)
        if not isinstance(entry, dict):
            raise AssociationRefused(f"role register entry for {address} must be a mapping")
        if entry.get("role") not in SERVICE_ROLES:
            raise AssociationRefused(
                f"role {entry.get('role')!r} for {address} is not one of {list(SERVICE_ROLES)}")
        if entry["role"] == ROLE_UNKNOWN:
            raise AssociationRefused(
                f"{address} is registered as {ROLE_UNKNOWN!r}. Unknown is the DEFAULT for every "
                "address not in this register; registering it explicitly implies somebody "
                "established it, and nobody can establish that a role is unknown")
        for field in ("provenance_sha256", "established_by"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise AssociationRefused(
                    f"role register entry for {address} states no {field}; a role asserted without "
                    "provenance is the same unsupported claim as a cluster")
    return register


def role_of(register, address):
    entry = register.get(address)
    return entry["role"] if entry else ROLE_UNKNOWN


def role_register_provenance(register):
    """A stable hash of the roles in force, so two ledgers built under different rosters differ."""
    payload = {address: {"role": entry["role"], "provenance_sha256": entry["provenance_sha256"]}
               for address, entry in sorted(register.items())}
    return {"addresses_registered": len(register),
            "register_sha256": hashlib.sha256(
                B10B.canonical_json(payload).encode("utf-8")).hexdigest()}


def counter_evidence_for(endpoints, evidence, register, incomplete_endpoints):
    """Why this link might be a false one. Never empty while any role is unknown.

    A shared service wallet is the obvious false link, and the honest default is that we do not
    know whether an address is one. So `unknown` RAISES this flag rather than lowering it: absence
    of a known service role is not evidence that the address is not a service.
    """
    found = {}

    def note(code, detail):
        found.setdefault(code, {"reason_code": code, "detail": detail, "addresses": []})

    for address in sorted(set(endpoints)):
        role = role_of(register, address)
        if role == ROLE_UNKNOWN:
            note(X01_ENDPOINT_ROLE_UNKNOWN,
                 "an endpoint's role has not been established, so a service wallet cannot be "
                 "excluded; absence of a known role is not evidence of absence of a service")
            found[X01_ENDPOINT_ROLE_UNKNOWN]["addresses"].append(address)
        elif role in ESTABLISHED_SERVICE_ROLES:
            note(X02_ENDPOINT_IS_KNOWN_SERVICE,
                 "an endpoint is an established service, so a link through it says nothing about "
                 "who controls the other end")
            found[X02_ENDPOINT_IS_KNOWN_SERVICE]["addresses"].append(address)

    intermediaries = sorted({address for item in evidence
                             for address in item["witness_addresses"]} - set(endpoints))
    for address in intermediaries:
        role = role_of(register, address)
        if role == ROLE_UNKNOWN:
            note(X03_INTERMEDIARY_ROLE_UNKNOWN,
                 "an intermediary's role has not been established; a shared funder that turns out "
                 "to be an exchange links every one of its customers to every other")
            found[X03_INTERMEDIARY_ROLE_UNKNOWN]["addresses"].append(address)
        elif role in ESTABLISHED_SERVICE_ROLES:
            note(X04_INTERMEDIARY_IS_KNOWN_SERVICE,
                 "an intermediary is an established service, so evidence routed through it is "
                 "evidence about the service and not about the endpoints")
            found[X04_INTERMEDIARY_IS_KNOWN_SERVICE]["addresses"].append(address)

    incomplete = sorted(set(endpoints) & set(incomplete_endpoints))
    if incomplete:
        note(X05_EVIDENCE_FROM_INCOMPLETE_HISTORY,
             "an endpoint's history is incomplete, so the evidence behind this link is a lower "
             "bound and its absence elsewhere proves nothing")
        found[X05_EVIDENCE_FROM_INCOMPLETE_HISTORY]["addresses"].extend(incomplete)

    for entry in found.values():
        entry["addresses"] = sorted(set(entry["addresses"]))
    return [found[code] for code in COUNTER_EVIDENCE_CODES if code in found]


# --------------------------------------------------------------------------------------------
# Completeness of a neighbourhood
# --------------------------------------------------------------------------------------------

def assert_lookback(lookback):
    """The lookback is declared, and declaring it unchosen is the honest state today."""
    if not isinstance(lookback, dict):
        raise AssociationRefused("lookback must be a mapping")
    missing = [field for field in LOOKBACK_FIELDS if field not in lookback]
    if missing:
        raise AssociationRefused(f"lookback does not state {missing}")
    unknown = [field for field in lookback if field not in LOOKBACK_FIELDS]
    if unknown:
        raise AssociationRefused(f"lookback carries undeclared fields {sorted(unknown)}")
    if not isinstance(lookback["lookback_chosen"], bool):
        raise AssociationRefused("lookback_chosen must be a boolean")
    if lookback["lookback_chosen"]:
        B13A._non_negative_int("lookback_slots", lookback["lookback_slots"])
        if not lookback["preregistration_reference"]:
            raise AssociationRefused(
                "a chosen lookback must name its preregistration. A lookback picked after seeing "
                "how far back the evidence happens to run is a lookback picked for its results")
    else:
        if lookback["lookback_slots"] is not None:
            raise AssociationRefused(
                "lookback_slots is set while lookback_chosen is False; a number nobody chose is a "
                "number somebody will use")
    if not isinstance(lookback["rationale"], str) or not lookback["rationale"]:
        raise AssociationRefused("lookback states no rationale")
    return lookback


def neighbourhood_failures(ledger, address):
    """Stable reason codes for why this address's association neighbourhood is not complete.

    Per address, like B13a's per-subject completeness and for the same reason: a gap that could not
    have touched this address must not be reported as though it had.
    """
    failures = []
    if not ledger["lookback"]["lookback_chosen"]:
        failures.append({
            "reason_code": G02_LOOKBACK_NOT_CHOSEN,
            "detail": "no lookback has been preregistered, so 'no association was found' means "
                      "only 'none inside whatever window this happened to cover'"})
    touching = [link for link in ledger["links"]
                if address in (link["grouping"]["address_a"], link["grouping"]["address_b"])]
    seen_endpoint = any(address in (link["grouping"]["address_a"], link["grouping"]["address_b"])
                        for link in ledger["links"])
    if not seen_endpoint and address not in ledger["accounting"].get("focus_address_list", []):
        failures.append({
            "reason_code": G03_ENDPOINT_HISTORY_ABSENT,
            "detail": "this address is not among the ledger's focus addresses, so its absence from "
                      "every link says nothing about it"})
    if any(not link["features"]["neighbourhood_complete"] for link in touching):
        failures.append({
            "reason_code": G01_CONTRIBUTING_HISTORY_INCOMPLETE,
            "detail": "a history contributing to this address's links is incomplete, so its "
                      "evidence is a lower bound"})
    accounting = ledger["coverage"].get("decode_accounting")
    if accounting:
        boundary = tuple(ledger["as_of"][field] for field in COORDINATE_FIELDS)
        poisoning = B13A.unresolved_before(accounting, boundary)
        if poisoning:
            failures.append({
                "reason_code": G04_UNRESOLVED_EVIDENCE_AT_OR_BEFORE_T0,
                "detail": f"{len(poisoning)} pieces of evidence at or before t0 could not be "
                          "resolved, so a link this ledger should contain may be missing",
                "first_unresolved": poisoning[0]})
    return failures


def require_complete_neighbourhood(ledger, address):
    """Fail closed for any policy that needs the whole neighbourhood rather than the observed part.

    Deliberately a separate call, exactly as in B13a. Building a ledger over a truncated window is
    legitimate; USING one as though the links in it were all the links there are is not.
    """
    failures = neighbourhood_failures(ledger, address)
    if failures:
        raise AssociationRefused(
            f"the association neighbourhood of {address} is not complete, so every count in it is "
            "a lower bound and a policy needing the whole neighbourhood cannot use it: "
            + "; ".join(f"{f['reason_code']} — {f['detail']}" for f in failures))
    return True


# --------------------------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------------------------

def _link_features(evidence, endpoints, counter_evidence, complete, lower_bounds):
    address_a, address_b = endpoints
    by_kind = {kind: 0 for kind in EVIDENCE_KINDS}
    lamports = {DIRECTION_A_TO_B: 0, DIRECTION_B_TO_A: 0}
    funders = set()
    for item in evidence:
        by_kind[item["kind"]] += 1
        if item["kind"] == E01_DIRECT_TRANSFER:
            lamports[item["direction"]] += item["facts"]["lamports"]
        if item["kind"] == E02_SHARED_FUNDER:
            funders.update(set(item["witness_addresses"]) - {address_a, address_b})
    return {
        "counts_are_lower_bounds": lower_bounds,
        "evidence_item_count_observed": len(evidence),
        "exact_address_equality_count_observed": by_kind[E00_EXACT_ADDRESS_EQUALITY],
        "direct_transfer_count_observed": by_kind[E01_DIRECT_TRANSFER],
        "shared_funder_count_observed": by_kind[E02_SHARED_FUNDER],
        "repeated_counterparty_count_observed": by_kind[E03_REPEATED_COUNTERPARTY],
        "co_occurrence_count_observed": by_kind[E04_CO_OCCURRENCE_IN_TRANSACTION],
        "co_signing_count_observed": by_kind[E05_CO_SIGNING_LAUNCH_ROLES],
        # Direction kept separate, never netted. A netted figure would hide a wallet that sent and
        # received a hundred SOL behind one that did nothing.
        "lamports_a_to_b_observed": lamports[DIRECTION_A_TO_B],
        "lamports_b_to_a_observed": lamports[DIRECTION_B_TO_A],
        "distinct_shared_funder_count_observed": len(funders),
        "counter_evidence_present": bool(counter_evidence),
        "neighbourhood_complete": complete,
    }


def build_link(relation_type, address_a, address_b, evidence, t0_key, register=None,
               incomplete_endpoints=(), lower_bounds=True, neighbourhood_complete=False):
    """One pairwise link, fully witnessed and fully uncalibrated."""
    if relation_type not in RELATION_TYPES:
        raise AssociationRefused(
            f"relation type {relation_type!r} is not one of {list(RELATION_TYPES)}")
    _non_empty_address("address_a", address_a)
    _non_empty_address("address_b", address_b)
    if relation_type == RELATION_IDENTITY_EQUALITY:
        if address_a != address_b:
            raise AssociationRefused(
                f"identity equality claims {address_a} and {address_b} are the same address while "
                "they are two different strings. Exact equality is the ONLY relation here that "
                "asserts sameness, and it may not be asserted about two different addresses")
    elif address_a >= address_b:
        raise AssociationRefused(
            f"association endpoints must be distinct and canonically ordered, got "
            f"({address_a}, {address_b})")

    register = assert_role_register(register)
    endpoints = (address_a, address_b)
    ordered, _ = ordered_evidence(evidence)
    for item in ordered:
        assert_evidence_item(item, endpoints, t0_key)
        if relation_type == RELATION_IDENTITY_EQUALITY:
            if item["kind"] != E00_EXACT_ADDRESS_EQUALITY:
                raise AssociationRefused(
                    f"identity equality carries {item['kind']} evidence. Association evidence may "
                    "never appear inside an identity claim; that is how 'they transacted' becomes "
                    "'they are the same'")
        elif item["kind"] == E00_EXACT_ADDRESS_EQUALITY:
            raise AssociationRefused(
                "association evidence carries an exact-equality item; equality is a different "
                "relation type and must be recorded as one")

    counter = counter_evidence_for(endpoints, ordered, register, incomplete_endpoints)
    features = _link_features(ordered, endpoints, counter, neighbourhood_complete, lower_bounds)
    assert_no_identity_in_features(features)
    link = {
        "relation_type": relation_type,
        "grouping": {"address_a": address_a, "address_b": address_b,
                     "relation_type": relation_type},
        "features": features,
        "evidence": ordered,
        "counter_evidence": counter,
        "completeness": {"neighbourhood_complete": neighbourhood_complete,
                         "counts_are_lower_bounds": lower_bounds},
        "confidence_status": CONFIDENCE_STATUS,
        "link_sha256": None,
    }
    assert_link(link, t0_key)
    link["link_sha256"] = link_hash(link)
    return link


def assert_link(link, t0_key):
    """Every gate on one link, in one call."""
    if not isinstance(link, dict):
        raise AssociationRefused(f"link must be a mapping, got {type(link).__name__}")
    missing = [field for field in LINK_FIELDS if field not in link]
    if missing:
        raise AssociationRefused(f"link does not carry {missing}")
    unknown = [field for field in link if field not in LINK_FIELDS]
    if unknown:
        raise AssociationRefused(f"link carries undeclared fields {sorted(unknown)}")
    if link["relation_type"] not in RELATION_TYPES:
        raise AssociationRefused(f"link relation type {link['relation_type']!r} is not declared")
    assert_disjoint_blocks(GROUPING_FIELDS, LINK_FEATURE_FIELDS)
    if set(link["grouping"]) != set(GROUPING_FIELDS):
        raise AssociationRefused(
            f"link grouping is {sorted(link['grouping'])}, contract says {sorted(GROUPING_FIELDS)}")
    if link["grouping"]["relation_type"] != link["relation_type"]:
        raise AssociationRefused("link grouping disagrees with the link about its relation type")
    if set(link["features"]) != set(LINK_FEATURE_FIELDS):
        raise AssociationRefused(
            f"link features are {sorted(link['features'])}, contract says "
            f"{sorted(LINK_FEATURE_FIELDS)}")
    assert_no_identity_in_features(link["features"])
    if link["confidence_status"] != CONFIDENCE_STATUS:
        raise AssociationRefused(
            f"link confidence status is {link['confidence_status']!r}; every link in this ledger is "
            f"{CONFIDENCE_STATUS!r} and nothing here has earned any other")

    endpoints = (link["grouping"]["address_a"], link["grouping"]["address_b"])
    if not link["evidence"]:
        raise AssociationRefused(
            "a link with no evidence is an assertion. Every link must be witnessed by at least one "
            "observation naming both of its endpoints")
    seen = set()
    for item in link["evidence"]:
        assert_evidence_item(item, endpoints, t0_key)
        digest = evidence_hash(item)
        if digest in seen:
            raise AssociationRefused(
                f"link carries the same evidence item twice ({digest[:12]}); duplicated evidence "
                "reads as independent corroboration and is not")
        seen.add(digest)

    for entry in link["counter_evidence"]:
        if entry["reason_code"] not in COUNTER_EVIDENCE_CODES:
            raise AssociationRefused(
                f"counter-evidence {entry['reason_code']!r} is not one of "
                f"{list(COUNTER_EVIDENCE_CODES)}")
    if link["features"]["counter_evidence_present"] != bool(link["counter_evidence"]):
        raise AssociationRefused(
            "link features disagree with its counter-evidence about whether any exists; the one "
            "place a service wallet could be quietly forgotten")
    if link["features"]["neighbourhood_complete"] != link["completeness"]["neighbourhood_complete"]:
        raise AssociationRefused("link features disagree with its completeness block")
    if link["features"]["neighbourhood_complete"] and link["counter_evidence"]:
        for entry in link["counter_evidence"]:
            if entry["reason_code"] == X05_EVIDENCE_FROM_INCOMPLETE_HISTORY:
                raise AssociationRefused(
                    "link claims a complete neighbourhood while carrying evidence from an "
                    "incomplete history; an incomplete history promoted to complete is the "
                    "quietest way for a lower bound to become a total")
    assert_uncalibrated(link)
    return link


def link_hash(link):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in link.items() if k != "link_sha256"}).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------
# Deriving evidence from a B13a event stream
# --------------------------------------------------------------------------------------------

ROLE_CREATOR = "creator"
ROLE_CREATE_USER = "create_user"
ROLE_TRADER = "trader"
ROLE_TRANSFER_FROM = "transfer_from"
ROLE_TRANSFER_TO = "transfer_to"


def _coordinate(event):
    return {field: event[field] for field in COORDINATE_FIELDS}


def _canonically(events):
    """Canonical order with the event's own hash as tiebreak.

    The tiebreak is not decoration: one transaction can carry a launch and a trade at the same
    coordinate, and sorting `(key, event)` tuples would then compare two dicts and raise. It also
    keeps the evidence — and therefore the hash — identical whichever order the events arrived in.
    """
    return sorted(events, key=lambda event: (B10B.canonical_key(event), B13A.event_hash(event)))


def _addresses_in(event):
    """Every address an event names, with the role it holds there."""
    if event["kind"] == B13A.EVENT_LAUNCH:
        return {event["creator"]: ROLE_CREATOR, event["create_user"]: ROLE_CREATE_USER}
    if event["kind"] == B13A.EVENT_TRADE:
        return {event["user"]: ROLE_TRADER}
    if event["kind"] == B13A.EVENT_TRANSFER:
        return {event["from_address"]: ROLE_TRANSFER_FROM, event["to_address"]: ROLE_TRANSFER_TO}
    return {}


def _identity_evidence(visible, address, t0_key):
    """The same address string in two different roles. This IS identity; nothing else here is."""
    occurrences = []
    for event in visible:
        role = _addresses_in(event).get(address)
        if role is None:
            continue
        occurrences.append((role, event))
    roles = sorted({role for role, _ in occurrences})
    if len(roles) < 2:
        return []
    chosen = {}
    for role, event in occurrences:
        chosen.setdefault(role, event)                       # earliest, since `visible` is ordered
    events = _canonically([chosen[role] for role in roles])
    item = {
        "kind": E00_EXACT_ADDRESS_EQUALITY,
        "direction": DIRECTION_NONE,
        "witness_addresses": [address],
        "coordinates": [_coordinate(e) for e in events],
        "source_sha256_list": [e["source_sha256"] for e in events],
        "facts": {"roles_observed": roles, "role_count_observed": len(roles)},
        "detail": f"the same address holds {len(roles)} distinct roles: {', '.join(roles)}",
    }
    assert_evidence_item(item, (address, address), t0_key)
    return [item]


def _pair_evidence(visible, address_a, address_b, t0_key):
    """Every typed observation naming both endpoints. Nothing inferred, nothing joined."""
    items = []
    transfers = [e for e in visible if e["kind"] == B13A.EVENT_TRANSFER]

    # E01 — one item per transfer, direction preserved relative to (a, b).
    between = _canonically([e for e in transfers
                            if {e["from_address"], e["to_address"]} == {address_a, address_b}])
    for edge in between:
        items.append({
            "kind": E01_DIRECT_TRANSFER,
            "direction": (DIRECTION_A_TO_B if edge["from_address"] == address_a
                          else DIRECTION_B_TO_A),
            "witness_addresses": sorted({address_a, address_b}),
            "coordinates": [_coordinate(edge)],
            "source_sha256_list": [edge["source_sha256"]],
            "facts": {"lamports": edge["lamports"]},
            "detail": f"{edge['lamports']} lamports moved directly between the endpoints; this is "
                      "evidence of a transfer and of nothing else",
        })

    # E03 — the raw repetition count. Two is the arithmetic meaning of "repeated", NOT a
    # significance threshold: no threshold has been preregistered and none is applied here.
    if len(between) > 1:
        a_to_b = sum(1 for e in between if e["from_address"] == address_a)
        items.append({
            "kind": E03_REPEATED_COUNTERPARTY,
            "direction": (DIRECTION_BOTH if 0 < a_to_b < len(between)
                          else DIRECTION_A_TO_B if a_to_b else DIRECTION_B_TO_A),
            "witness_addresses": sorted({address_a, address_b}),
            "coordinates": [_coordinate(e) for e in between],
            "source_sha256_list": [e["source_sha256"] for e in between],
            "facts": {"transfer_count_observed": len(between),
                      "a_to_b_count_observed": a_to_b,
                      "b_to_a_count_observed": len(between) - a_to_b,
                      "repetition_threshold_applied": False},
            "detail": f"the endpoints transacted {len(between)} times; the raw count is published "
                      "and compared against no threshold, because none has been preregistered",
        })

    # E02 — one item per funder that paid both endpoints. The classic false link, so the funder is
    # named in the witnesses and lands in counter-evidence when its role is unknown.
    to_a = {e["from_address"]: e for e in reversed(transfers) if e["to_address"] == address_a}
    to_b = {e["from_address"]: e for e in reversed(transfers) if e["to_address"] == address_b}
    for funder in sorted(set(to_a) & set(to_b) - {address_a, address_b}):
        paid = _canonically([to_a[funder], to_b[funder]])
        items.append({
            "kind": E02_SHARED_FUNDER,
            "direction": DIRECTION_NONE,
            "witness_addresses": sorted({address_a, address_b, funder}),
            "coordinates": [_coordinate(e) for e in paid],
            "source_sha256_list": [e["source_sha256"] for e in paid],
            "facts": {"funder_paid_both": True,
                      "lamports_to_a_observed": to_a[funder]["lamports"],
                      "lamports_to_b_observed": to_b[funder]["lamports"]},
            "detail": "one address funded both endpoints; a service wallet funds thousands of "
                      "unrelated actors, so this is evidence of a shared counterparty only",
        })

    # E05 — different roles in one launch. A shared action, which is weaker than shared control.
    for event in visible:
        if event["kind"] != B13A.EVENT_LAUNCH:
            continue
        if {event["creator"], event["create_user"]} != {address_a, address_b}:
            continue
        items.append({
            "kind": E05_CO_SIGNING_LAUNCH_ROLES,
            "direction": DIRECTION_NONE,
            "witness_addresses": sorted({address_a, address_b}),
            "coordinates": [_coordinate(event)],
            "source_sha256_list": [event["source_sha256"]],
            "facts": {"creator_is_a": event["creator"] == address_a},
            "detail": "the endpoints hold different roles in the same launch",
        })

    # E04 — co-presence in one transaction. Deliberately last, and deliberately overlapping the
    # kinds above: an E01 transfer is ALSO a co-occurrence. Overlapping evidence is not independent
    # evidence, which is one more reason these counts may not be added into a score.
    by_transaction = {}
    for event in visible:
        by_transaction.setdefault((event["slot"], event["transaction_index"]), []).append(event)
    for (slot, index), group in sorted(by_transaction.items()):
        named = set()
        for event in group:
            named |= set(_addresses_in(event))
        if not {address_a, address_b}.issubset(named):
            continue
        ordered_group = _canonically(group)
        items.append({
            "kind": E04_CO_OCCURRENCE_IN_TRANSACTION,
            "direction": DIRECTION_NONE,
            "witness_addresses": sorted({address_a, address_b}),
            "coordinates": [_coordinate(e) for e in ordered_group],
            "source_sha256_list": [e["source_sha256"] for e in ordered_group],
            "facts": {"slot": slot, "transaction_index": index,
                      "events_in_transaction_observed": len(group),
                      "overlaps_other_evidence_kinds": True},
            "detail": f"both addresses are named in transaction ({slot}, {index}); co-presence in "
                      "a transaction one of them did not sign is evidence of being named",
        })
    return items


def build_association_ledger(events, focus_addresses, t0, coverage, role_register=None,
                             lookback=None, incomplete_endpoints=None):
    """One point-in-time association evidence ledger, as of exactly t0.

    `events` may arrive in any order; they are canonically sorted and everything after t0 is
    discarded before a single pair is considered, so no code path downstream can see one.
    """
    B13A.assert_coverage(coverage)
    register = assert_role_register(role_register)
    lookback = assert_lookback(lookback if lookback is not None else unchosen_lookback())
    if isinstance(focus_addresses, (str, bytes)):
        raise AssociationRefused("focus_addresses must be a collection of addresses")
    focus = sorted({_non_empty_address("focus address", a) for a in focus_addresses})
    t0_key = B10B.canonical_key(t0)

    ordered, _ = B13A.ordered_events(events)
    visible = B13A.at_or_before(ordered, t0_key)
    discarded = len(ordered) - len(visible)

    lower_bounds = coverage["left_truncated"]
    unresolved_here = bool(B13A.unresolved_before(coverage["decode_accounting"], t0_key))
    incomplete = set(incomplete_endpoints or ())
    if lower_bounds or unresolved_here:
        # Every endpoint's evidence is a lower bound when the window itself is. Marking only some
        # of them would be worse than marking none: it would imply the unmarked ones were checked.
        incomplete |= set(focus)

    links, pairs = [], 0
    for address in focus:
        evidence = _identity_evidence(visible, address, t0_key)
        if evidence:
            links.append(build_link(
                RELATION_IDENTITY_EQUALITY, address, address, evidence, t0_key,
                register=register, incomplete_endpoints=incomplete, lower_bounds=lower_bounds,
                neighbourhood_complete=False))
    for i, address_a in enumerate(focus):
        for address_b in focus[i + 1:]:
            pairs += 1
            evidence = _pair_evidence(visible, address_a, address_b, t0_key)
            if not evidence:
                continue
            links.append(build_link(
                RELATION_ASSOCIATION_EVIDENCE, address_a, address_b, evidence, t0_key,
                register=register, incomplete_endpoints=incomplete, lower_bounds=lower_bounds,
                neighbourhood_complete=False))

    links.sort(key=lambda link: (link["grouping"]["address_a"], link["grouping"]["address_b"],
                                 link["relation_type"], link["link_sha256"]))
    chain = hashlib.sha256()
    for link in links:
        for item in link["evidence"]:
            for source in item["source_sha256_list"]:
                chain.update(source.encode())

    by_kind = {kind: 0 for kind in EVIDENCE_KINDS}
    by_relation = {relation: 0 for relation in RELATION_TYPES}
    for link in links:
        by_relation[link["relation_type"]] += 1
        for item in link["evidence"]:
            by_kind[item["kind"]] += 1

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "boundary_rule": BOUNDARY_RULE,
        "confidence_status": CONFIDENCE_STATUS,
        "confidence_status_meaning": CONFIDENCE_STATUS_MEANING,
        "as_of": {field: t0[field] for field in COORDINATE_FIELDS},
        "coverage": dict(coverage),
        "lookback": dict(lookback),
        "role_register_provenance": role_register_provenance(register),
        "links": links,
        "accounting": {
            "focus_addresses": len(focus),
            "focus_address_list": focus,
            "pairs_considered": pairs,
            "links_emitted": len(links),
            "links_by_relation": by_relation,
            "evidence_items": sum(by_kind.values()),
            "evidence_by_kind": by_kind,
            "events_supplied": len(ordered),
            "events_visible": len(visible),
            "events_discarded_after_t0": discarded,
        },
        "evidence_hash_chain_sha256": chain.hexdigest(),
        "ledger_sha256": None,
    }
    assert_ledger(ledger)
    ledger["ledger_sha256"] = ledger_hash(ledger)
    return ledger


def unchosen_lookback():
    """The honest state today: no lookback, and a record that says so out loud."""
    return {
        "lookback_slots": None,
        "lookback_chosen": False,
        "preregistration_reference": None,
        "rationale": "NOT CHOSEN. A lookback picked after seeing how far back the evidence happens "
                     "to run is a lookback picked for its results. It must be frozen in its own "
                     "preregistration, in slots, before the actors it applies to are known.",
    }


def assert_ledger(ledger):
    """Every gate on the whole ledger, in one call."""
    if not isinstance(ledger, dict):
        raise AssociationRefused(f"ledger must be a mapping, got {type(ledger).__name__}")
    missing = [field for field in LEDGER_FIELDS if field not in ledger]
    if missing:
        raise AssociationRefused(f"ledger does not carry {missing}")
    unknown = [field for field in ledger if field not in LEDGER_FIELDS]
    if unknown:
        raise AssociationRefused(f"ledger carries undeclared fields {sorted(unknown)}")
    if ledger["boundary_rule"] != BOUNDARY_RULE:
        raise AssociationRefused("the boundary rule on this ledger is not the one this module "
                                 "applies")
    if ledger["confidence_status"] != CONFIDENCE_STATUS:
        raise AssociationRefused(
            f"ledger confidence status is {ledger['confidence_status']!r}; nothing in this module "
            f"has earned anything but {CONFIDENCE_STATUS!r}")
    B13A.assert_coverage(ledger["coverage"])
    assert_lookback(ledger["lookback"])
    t0_key = tuple(ledger["as_of"][field] for field in COORDINATE_FIELDS)

    missing_accounting = [field for field in ACCOUNTING_FIELDS if field not in ledger["accounting"]]
    if missing_accounting:
        raise AssociationRefused(f"ledger accounting does not state {missing_accounting}")

    seen_pairs, by_kind = set(), {kind: 0 for kind in EVIDENCE_KINDS}
    by_relation = {relation: 0 for relation in RELATION_TYPES}
    for link in ledger["links"]:
        assert_link(link, t0_key)
        pair = (link["grouping"]["address_a"], link["grouping"]["address_b"],
                link["relation_type"])
        if pair in seen_pairs:
            raise AssociationRefused(
                f"ledger carries two {pair[2]} links for the same pair; the same evidence split "
                "across two links reads as two findings")
        seen_pairs.add(pair)
        by_relation[link["relation_type"]] += 1
        for item in link["evidence"]:
            by_kind[item["kind"]] += 1
        if link["completeness"]["counts_are_lower_bounds"] != ledger["coverage"]["left_truncated"]:
            raise AssociationRefused(
                "a link disagrees with coverage about whether its counts are lower bounds; the one "
                "place a truncated window could be mistaken for a complete one")

    if by_kind != ledger["accounting"]["evidence_by_kind"]:
        raise AssociationRefused(
            f"ledger accounting says {ledger['accounting']['evidence_by_kind']} but the links hold "
            f"{by_kind}; an accounting that does not match the evidence is an accounting of "
            "something else")
    if by_relation != ledger["accounting"]["links_by_relation"]:
        raise AssociationRefused("ledger accounting disagrees with the links about relation types")
    if ledger["accounting"]["links_emitted"] != len(ledger["links"]):
        raise AssociationRefused("ledger accounting disagrees with the links about how many there "
                                 "are")
    if ledger["accounting"]["evidence_items"] != sum(by_kind.values()):
        raise AssociationRefused("ledger accounting disagrees with the links about how much "
                                 "evidence they hold")
    # `assert_no_transitive_link` is deliberately NOT called here. The per-item rule inside
    # `assert_link` is strictly stronger — it requires EVERY item to witness both endpoints, where
    # the ledger-level rule requires only one — so a call here could never fire, and a check that
    # cannot fire is worse than no check. It stays a public entry point so a caller holding a
    # ledger from elsewhere can ask the question directly.
    assert_uncalibrated(ledger)
    return ledger


def assert_no_transitive_link(ledger):
    """No link may exist that no single observation witnessed.

    A public entry point for a caller holding a ledger built elsewhere. `assert_ledger` does not
    call it, because `assert_link`'s per-item rule is strictly stronger and would already have
    refused anything this could catch. A—B and B—C witness {A,B} and {B,C}; an A—C link
    manufactured from them witnesses neither endpoint pair, and there is no way to write one that
    does.
    """
    for link in ledger["links"]:
        endpoints = {link["grouping"]["address_a"], link["grouping"]["address_b"]}
        witnessed = any(endpoints.issubset(set(item["witness_addresses"]))
                        for item in link["evidence"])
        if not witnessed:
            raise AssociationRefused(
                f"link {sorted(endpoints)} is witnessed by no single observation naming both "
                "endpoints. A—B plus B—C is two observations, never an A—C link")
    return True


def ledger_hash(ledger):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in ledger.items() if k != "ledger_sha256"}).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "confidence_status": CONFIDENCE_STATUS,
        "confidence_status_meaning": CONFIDENCE_STATUS_MEANING,
        "relation_types": list(RELATION_TYPES),
        "evidence_kinds": list(EVIDENCE_KINDS),
        "evidence_meaning": EVIDENCE_MEANING,
        "directional_kinds": list(DIRECTIONAL_KINDS),
        "service_roles": list(SERVICE_ROLES),
        "counter_evidence_codes": list(COUNTER_EVIDENCE_CODES),
        "neighbourhood_reason_codes": list(NEIGHBOURHOOD_REASON_CODES),
        "grouping_fields": list(GROUPING_FIELDS),
        "link_feature_fields": list(LINK_FEATURE_FIELDS),
        "lookback": unchosen_lookback(),
        "clusters_inferred": False,
        "transitive_closure_taken": False,
        "probability_emitted": False,
        "refusing_operations": ["cluster_id", "connected_component", "merge_addresses",
                                "association_probability", "cluster_adjusted_concentration"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"AssociationRefused: {error}", file=sys.stderr)
        sys.exit(2)
