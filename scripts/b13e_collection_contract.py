"""B13e — validator and orchestrator for the frozen history-collection contract. Offline. No RPC.

What this module is
-------------------
The machinery that enforces `research/B13E_LOOKBACK_PREREGISTRATION.md`, committed separately and
afterwards so that the parameters could not have been adjusted until the code worked.

It computes lookback windows, checks cohort scope, refuses queries before unlock, validates coverage
per actor, and produces a collection PLAN. **It never collects anything.** There is no network call
in this file and no code path that could make one; the guard it exposes is something a future
collector must ask permission from, not something that fetches.

The three refusals worth naming
-------------------------------
1. **The preregistration is pinned by hash.** Every entry point checks it. A document edited after
   the fact stops matching, and a validator that would accept the edit is the only thing standing
   between a frozen parameter and a retuned one.
2. **Coverage is per actor and averaging is refused outright.** A cohort mean is exactly the
   statistic that hides the one actor whose history is missing, so this module will not compute one
   even when asked.
3. **A burned event may be context; a burned member may never be evidence.** Those are two different
   checks against two different things — the coordinate of an event versus the identity of a
   subject — and collapsing them into one is how "we excluded the burned data" becomes either a
   silent zero or a silent leak.
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


B13A = _load("b13a_history", "b13a_history.py")
B11A = _load("b11a_window_freeze", "b11a_window_freeze.py")
B10B = B13A.B10B

SCHEMA_VERSION = "1.0.0"

COORDINATE_FIELDS = B13A.COORDINATE_FIELDS

PREREGISTRATION_PATH = ROOT / "research" / "B13E_LOOKBACK_PREREGISTRATION.md"
PREREGISTRATION_ID = "B13E_LOOKBACK_V1"

# Pinned against the document committed ALONE in the previous commit. Recomputed on every entry
# point rather than trusted: a parameter is only frozen if something notices when it thaws.
PREREGISTRATION_PARAMS_SHA256 = \
    "ffbc573b89059aabcc5e5cf20a1d9d5e3d9d5b2aedd6f98728c545616ef51428"

# The lookback, restated here so the code can be read on its own — and then asserted against the
# document, which is the authority. Neither is allowed to drift from the other.
LOOKBACK_SLOTS = B11A.B9D_CUTOFF_SLOT - B11A.B8B_WINDOW_START_SLOT

MINIMUM_SLOT = 0

AB01_B11A_NOT_UNLOCKED = "AB01_b11a_not_unlocked"
AB02_COHORT_NOT_FROM_B11A = "AB02_cohort_not_from_b11a"
AB03_PAGINATION_NOT_EXHAUSTED = "AB03_pagination_not_exhausted"
AB04_ACTOR_COVERAGE_SHORT = "AB04_actor_coverage_short"
AB05_DECODE_LOSS_AT_OR_BEFORE_T0 = "AB05_decode_loss_at_or_before_t0"
AB06_SNAPSHOT_NOT_ATOMIC = "AB06_snapshot_not_atomic"
AB07_SOURCE_HASH_DRIFT = "AB07_source_hash_drift"
AB08_METHOD_NOT_ALLOWLISTED = "AB08_method_not_allowlisted"
AB09_RAW_NOT_PRESERVED = "AB09_raw_not_preserved"
AB10_LOOKBACK_FORMULA_MISMATCH = "AB10_lookback_formula_mismatch"
AB11_PREREGISTRATION_HASH_MISMATCH = "AB11_preregistration_hash_mismatch"
ABORT_CODES = (AB01_B11A_NOT_UNLOCKED, AB02_COHORT_NOT_FROM_B11A, AB03_PAGINATION_NOT_EXHAUSTED,
               AB04_ACTOR_COVERAGE_SHORT, AB05_DECODE_LOSS_AT_OR_BEFORE_T0,
               AB06_SNAPSHOT_NOT_ATOMIC, AB07_SOURCE_HASH_DRIFT, AB08_METHOD_NOT_ALLOWLISTED,
               AB09_RAW_NOT_PRESERVED, AB10_LOOKBACK_FORMULA_MISMATCH,
               AB11_PREREGISTRATION_HASH_MISMATCH)

# A burned datum can play two roles, and only one of them is permitted.
ROLE_PRIOR_CONTEXT = "prior_context"
ROLE_EVALUATED_SUBJECT = "evaluated_subject"
ROLE_LABEL_SOURCE = "label_source"
ROLE_TUNING_DATA = "tuning_data"
ROLE_PERFORMANCE_EVIDENCE = "performance_evidence"
BURNED_ROLES = (ROLE_PRIOR_CONTEXT, ROLE_EVALUATED_SUBJECT, ROLE_LABEL_SOURCE, ROLE_TUNING_DATA,
                ROLE_PERFORMANCE_EVIDENCE)
BURNED_ROLE_PERMITTED = {
    ROLE_PRIOR_CONTEXT: True,
    ROLE_EVALUATED_SUBJECT: False,
    ROLE_LABEL_SOURCE: False,
    ROLE_TUNING_DATA: False,
    ROLE_PERFORMANCE_EVIDENCE: False,
}

COVERAGE_FIELDS = ("actor", "earliest_slot_reached", "lookback_start_slot", "left_truncated",
                   "pagination", "decode_accounting", "source_hashes", "raw_preserved")

PAGINATION_FIELDS = ("method", "pages_fetched", "page_size", "final_cursor",
                     "termination_condition", "page_cap")

TERMINATION_EMPTY_PAGE = "empty_page"
TERMINATION_END_OF_STREAM = "end_of_stream"
TERMINATION_PAGE_CAP = "page_cap_reached"
TERMINATION_CONDITIONS = (TERMINATION_EMPTY_PAGE, TERMINATION_END_OF_STREAM, TERMINATION_PAGE_CAP)
EXHAUSTING_TERMINATIONS = (TERMINATION_EMPTY_PAGE, TERMINATION_END_OF_STREAM)

# Credential-shaped things. Refused rather than redacted: a redaction that fails silently looks
# exactly like one that worked.
CREDENTIAL_PATTERNS = (
    re.compile(r"api[_-]?key", re.I),
    re.compile(r"secret", re.I),
    re.compile(r"bearer\s", re.I),
    re.compile(r"authorization", re.I),
    re.compile(r"private[_-]?key", re.I),
    re.compile(r"\bpassword\b", re.I),
    re.compile(r"https?://[^\s]*[?&](?:api[-_]?key|token|access[-_]?token)=", re.I),
)


class ContractViolation(B13A.HistoryRefused):
    """Raised when the collection contract would be broken."""


class PreregistrationMismatch(ContractViolation):
    """Raised when the frozen document is not the one this code was written against.

    A separate class because it is a different problem: nothing about the run is wrong, the
    parameters themselves have moved, and no other check means anything until that is resolved.
    """


class QueryRefused(ContractViolation):
    """Raised when a query would be made that the contract does not permit."""


# --------------------------------------------------------------------------------------------
# The preregistration, pinned
# --------------------------------------------------------------------------------------------

def read_preregistration(path=None):
    """Parse the frozen parameter block out of the committed document."""
    path = pathlib.Path(path or PREREGISTRATION_PATH)
    if not path.exists():
        raise PreregistrationMismatch(
            f"the preregistration is missing at {path}. Nothing here may run without the document "
            "it was written against")
    match = re.search(r"```json\n(.*?)\n```", path.read_text(), re.S)
    if not match:
        raise PreregistrationMismatch(
            "the preregistration carries no frozen parameter block; prose alone is not checkable")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise PreregistrationMismatch(f"the frozen parameter block is not valid JSON: {error}")


def preregistration_hash(params):
    return hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def assert_preregistration(params=None, expected=PREREGISTRATION_PARAMS_SHA256):
    """The document is the authority, and this pin is what notices when it moves.

    Beyond the hash, exactly one class of value is re-checked: anything the CODE holds its own
    independent copy of — the lookback, its two operands, and the burned-role table. Those can
    disagree with the document without the document changing, because the other side can move.

    Values the document alone states (the cohort source, the averaging ban, the unlock requirement)
    are pinned by the hash and are deliberately NOT re-read here. Re-reading them would add a check
    that no input can make fire, and a check that cannot fire is worse than no check.
    """
    params = read_preregistration() if params is None else params
    if params.get("preregistration_id") != PREREGISTRATION_ID:
        raise PreregistrationMismatch(
            f"preregistration id is {params.get('preregistration_id')!r}, expected "
            f"{PREREGISTRATION_ID!r}")
    digest = preregistration_hash(params)
    if digest != expected:
        raise PreregistrationMismatch(
            f"the frozen parameters hash to {digest} but this code was written against {expected}. "
            "Either the document was edited after it was frozen or this code is stale, and a "
            f"validator that accepted the difference would be the only thing standing between a "
            "frozen parameter and a retuned one")
    # The document and the code must agree about the one number that matters, computed
    # independently on both sides.
    if params["lookback_slots"] != LOOKBACK_SLOTS:
        raise PreregistrationMismatch(
            f"the document says {params['lookback_slots']} lookback slots while the frozen "
            f"constants give {LOOKBACK_SLOTS}")
    operands = params["lookback_operands"]
    if (operands["b9d_cutoff_slot"] != B11A.B9D_CUTOFF_SLOT
            or operands["b8b_window_start_slot"] != B11A.B8B_WINDOW_START_SLOT):
        raise PreregistrationMismatch(
            "the document's lookback operands are not the frozen constants they claim to be")
    if operands["b9d_cutoff_slot"] - operands["b8b_window_start_slot"] != params["lookback_slots"]:
        raise PreregistrationMismatch(
            "the document's own derivation does not produce its own lookback")
    return params


# --------------------------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------------------------

def lookback_window(t0, params=None):
    """The window for one decision. Computed from t0 and the frozen constant, from nothing else.

    There is no adaptive deepening here and no place to put one: no history, count or coverage
    figure is an input to this function.
    """
    params = assert_preregistration(params)
    for field in COORDINATE_FIELDS:
        value = t0.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractViolation(f"t0 {field} must be an integer, got {value!r}")
    upper = tuple(t0[field] for field in COORDINATE_FIELDS)
    unclamped = t0["slot"] - params["lookback_slots"]
    start = max(MINIMUM_SLOT, unclamped)
    return {
        "lookback_slots": params["lookback_slots"],
        "start_slot_inclusive": start,
        "unclamped_start_slot": unclamped,
        # A clamped window is SHORTER than the lookback. That is left truncation, and a clamped
        # window reporting itself complete would claim knowledge of a period before the chain
        # existed.
        "clamped_at_genesis": unclamped < MINIMUM_SLOT,
        "end_coordinate_inclusive": {field: t0[field] for field in COORDINATE_FIELDS},
        "end_key": upper,
        "lower_bound_granularity": "slot",
        "upper_bound_granularity": "coordinate",
    }


def in_window(event, window):
    """Slot-wise at the bottom, coordinate-wise at the top. The asymmetry is deliberate.

    The upper bound is a leakage boundary and must be exact to the instruction. The lower bound is a
    coverage boundary: half a slot of lookback is not a meaningful quantity, and a coordinate-exact
    lower bound would make the window's length depend on where inside a slot the decision fell.
    """
    if event["slot"] < window["start_slot_inclusive"]:
        return False
    return tuple(event[field] for field in COORDINATE_FIELDS) <= tuple(window["end_key"])


def hours_of_lookback(*_args, **_kwargs):
    """Never returns. The lookback is defined in slots and applied in slots.

    Slot production varies, so a wall-clock lookback is a different number of slots on every day it
    is applied — and a frozen parameter whose length depends on network conditions is not frozen.
    """
    raise ContractViolation(
        "the lookback is not translated into wall-clock time. Slot production varies, so a "
        "wall-clock lookback is a different number of slots every day it is applied, and a "
        "parameter whose length depends on network conditions is not a frozen parameter. Any "
        "conversion is an estimate outside this contract and must be labelled as one where it is "
        "displayed.")


# --------------------------------------------------------------------------------------------
# Unlock, cohort and access
# --------------------------------------------------------------------------------------------

def assert_unlocked(unlock_state, params=None):
    """No query before B11a's maturity and U3. Before that the cohort is unknown."""
    params = assert_preregistration(params)
    if not isinstance(unlock_state, dict):
        raise ContractViolation("unlock state must be a mapping")
    required = params["required_unlock_criterion"]
    if not unlock_state.get("mature"):
        raise QueryRefused(
            f"{AB01_B11A_NOT_UNLOCKED}: B11a has not matured, so no actor is known. A run that "
            "queried anyway would necessarily have chosen its own population")
    if not unlock_state.get("criteria", {}).get(required):
        raise QueryRefused(
            f"{AB01_B11A_NOT_UNLOCKED}: B11a's {required} criterion has not passed")
    return True


def assert_cohort(subjects, enumeration, params=None):
    """Exactly B11a's enumeration. Not wider, not narrower.

    Wider selects on whatever the broader population happened to contain; narrower selects on
    collectability, which correlates with activity.
    """
    params = assert_preregistration(params)
    if isinstance(subjects, (str, bytes)) or isinstance(enumeration, (str, bytes)):
        raise ContractViolation("subjects and enumeration must be collections of identifiers")
    subjects, enumeration = set(subjects), set(enumeration)
    if not enumeration:
        raise QueryRefused(
            f"{AB02_COHORT_NOT_FROM_B11A}: the enumeration is empty, so no subject can be in it. "
            "Before unlock the cohort is unknown, and an empty enumeration is not permission to "
            "collect broadly")
    outside = sorted(subjects - enumeration)
    if outside:
        raise QueryRefused(
            f"{AB02_COHORT_NOT_FROM_B11A}: {len(outside)} subjects are not in B11a's enumeration "
            f"(first: {outside[0]}). Collecting a wider population and filtering afterwards selects "
            "on whatever the wider population happened to contain")
    return True


def assert_method_allowlisted(method, params=None):
    """An allowlist, because the next client version adds a method nobody thought to forbid."""
    params = assert_preregistration(params)
    if method not in params["method_allowlist"]:
        raise QueryRefused(
            f"{AB08_METHOD_NOT_ALLOWLISTED}: {method!r} is not in the allowlist. This contract "
            "permits read-only methods only, and anything that submits, signs or mutates is "
            "permanently forbidden")
    return True


def assert_no_credential(record):
    """Refused rather than redacted; a redaction that fails silently looks like one that worked."""
    def walk(value, path="record"):
        if isinstance(value, dict):
            for key, child in value.items():
                for pattern in CREDENTIAL_PATTERNS:
                    if pattern.search(str(key)):
                        raise ContractViolation(
                            f"{path}.{key} is credential-shaped. Credentials are environment-only "
                            "and never persisted — not in a record, a query spec, a log or a report")
                walk(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            for pattern in CREDENTIAL_PATTERNS:
                if pattern.search(value):
                    raise ContractViolation(
                        f"{path} contains a credential-shaped string. Store the endpoint identity "
                        "as a hash; a query specification is hashed precisely so one containing a "
                        "key cannot sit in the clear")
    walk(record)
    return True


class QueryGuard:
    """Permission to query, which a future collector must ask for and this module never uses.

    Deliberately not a client. It holds no endpoint, opens no socket and imports nothing that
    could; the only thing it can do is refuse.
    """

    def __init__(self, unlock_state, enumeration, params=None):
        self.params = assert_preregistration(params)
        assert_unlocked(unlock_state, self.params)
        self.enumeration = set(enumeration)
        if not self.enumeration:
            raise QueryRefused(f"{AB02_COHORT_NOT_FROM_B11A}: no enumeration, no cohort, no query")
        self.calls = []

    def permit(self, method, subject=None, request=None):
        assert_method_allowlisted(method, self.params)
        if subject is not None:
            assert_cohort([subject], self.enumeration, self.params)
        if request is not None:
            assert_no_credential(request)
        self.calls.append({"method": method, "subject": subject})
        return True


# --------------------------------------------------------------------------------------------
# Coverage, per actor and never averaged
# --------------------------------------------------------------------------------------------

def assert_pagination(pagination):
    """Exhaustion must be proved, and a page cap is not exhaustion."""
    if not isinstance(pagination, dict):
        raise ContractViolation("pagination must be a mapping")
    missing = [field for field in PAGINATION_FIELDS if field not in pagination]
    if missing:
        raise ContractViolation(f"pagination does not state {missing}")
    unknown = [field for field in pagination if field not in PAGINATION_FIELDS]
    if unknown:
        raise ContractViolation(f"pagination carries undeclared fields {sorted(unknown)}")
    if pagination["termination_condition"] not in TERMINATION_CONDITIONS:
        raise ContractViolation(
            f"termination condition {pagination['termination_condition']!r} is not one of "
            f"{list(TERMINATION_CONDITIONS)}. 'We had enough' is not a termination condition")
    for field in ("pages_fetched", "page_size"):
        value = pagination[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractViolation(f"pagination {field} must be a non-negative integer")
    return pagination


def pagination_exhausted(pagination):
    """Whether the source was actually read to its end."""
    assert_pagination(pagination)
    if pagination["termination_condition"] not in EXHAUSTING_TERMINATIONS:
        return False
    # An unconsumed cursor means there was more and nobody fetched it, whatever the stated reason.
    return not pagination["final_cursor"]


def actor_coverage_failures(coverage, window, params=None):
    """Why THIS actor's history is short. Per actor, and the reasons are codes.

    Per actor rather than per cohort because an average is exactly the statistic that hides the one
    actor whose history is missing.
    """
    params = assert_preregistration(params)
    if not isinstance(coverage, dict):
        raise ContractViolation("coverage must be a mapping")
    missing = [field for field in COVERAGE_FIELDS if field not in coverage]
    if missing:
        raise ContractViolation(f"coverage does not state {missing}")
    failures = []

    if coverage["lookback_start_slot"] != window["start_slot_inclusive"]:
        failures.append({
            "reason_code": AB10_LOOKBACK_FORMULA_MISMATCH,
            "detail": f"coverage claims a start of {coverage['lookback_start_slot']} but the "
                      f"formula gives {window['start_slot_inclusive']}; a start moved to match what "
                      "a source happened to have would redefine the parameter per actor"})
    if coverage["earliest_slot_reached"] > coverage["lookback_start_slot"]:
        failures.append({
            "reason_code": AB04_ACTOR_COVERAGE_SHORT,
            "detail": f"the source reached back only to {coverage['earliest_slot_reached']}, short "
                      f"of {coverage['lookback_start_slot']}. This actor's counts are lower bounds "
                      "and the start is NOT shifted to meet the source"})
    if window["clamped_at_genesis"] and not coverage["left_truncated"]:
        failures.append({
            "reason_code": AB04_ACTOR_COVERAGE_SHORT,
            "detail": "the window was clamped at genesis, so it is shorter than the lookback; a "
                      "clamped window reporting itself complete claims knowledge of a period "
                      "before the chain existed"})

    if not pagination_exhausted(coverage["pagination"]):
        failures.append({
            "reason_code": AB03_PAGINATION_NOT_EXHAUSTED,
            "detail": f"pagination terminated on "
                      f"{coverage['pagination']['termination_condition']!r} with cursor "
                      f"{coverage['pagination']['final_cursor']!r}; a run that stops at a cap has "
                      "not read the source, and a silent cap produces a confidently wrong zero"})

    accounting = coverage["decode_accounting"]
    if not accounting:
        failures.append({
            "reason_code": AB05_DECODE_LOSS_AT_OR_BEFORE_T0,
            "detail": "no decode accounting, so silent evidence loss cannot be ruled out: an "
                      "instruction that would not decode produces no edge, and no edge is "
                      "indistinguishable from no funding"})
    else:
        B13A.assert_decode_accounting(accounting)
        poisoning = B13A.unresolved_before(accounting, window["end_key"])
        if poisoning:
            failures.append({
                "reason_code": AB05_DECODE_LOSS_AT_OR_BEFORE_T0,
                "detail": f"{len(poisoning)} pieces of evidence at or before this actor's t0 could "
                          "not be resolved",
                "first_unresolved": poisoning[0]})

    if not coverage["source_hashes"]:
        failures.append({
            "reason_code": AB07_SOURCE_HASH_DRIFT,
            "detail": "no source hashes, so nothing can be compared against anything later"})
    if params["raw_preservation_required"] and not coverage["raw_preserved"]:
        failures.append({
            "reason_code": AB09_RAW_NOT_PRESERVED,
            "detail": "the raw response was neither retained nor hashed, so a parse cannot be told "
                      "from a refetch"})
    return failures


def cohort_completeness(coverages, windows, params=None):
    """Per-actor verdicts and one overall boolean. Never a fraction.

    The overall value is the AND of every actor, which is the only aggregate that cannot hide one.
    """
    params = assert_preregistration(params)
    per_actor = {}
    for coverage in coverages:
        actor = coverage["actor"]
        if actor in per_actor:
            raise ContractViolation(
                f"two coverage records for {actor}; the second would silently replace the first")
        per_actor[actor] = actor_coverage_failures(coverage, windows[actor], params)
    return {
        "per_actor": per_actor,
        "actors": len(per_actor),
        "actors_complete": sum(1 for f in per_actor.values() if not f),
        "actors_incomplete": sorted(a for a, f in per_actor.items() if f),
        # AND, not a mean. Any single short actor makes the collection incomplete, and there is no
        # percentage to pick because picking one would require averaging.
        "collection_complete": all(not f for f in per_actor.values()),
    }


def coverage_fraction(*_args, **_kwargs):
    """Never returns. Exists so that asking for the average is a refusal, not a blank page."""
    raise ContractViolation(
        "coverage is published per actor and never averaged. A cohort mean, median or fraction is "
        "exactly the statistic that hides the single actor whose history is missing, and one "
        "actor's complete history does not make another's complete.")


# --------------------------------------------------------------------------------------------
# Burned data: context yes, evidence no
# --------------------------------------------------------------------------------------------

def slot_is_burned(slot, ranges=B11A.BURNED_RANGES):
    return any(first <= slot <= last
               for _, first, last in B11A.normalized_burned_ranges(ranges))


def assert_burned_role(slot, role, params=None, expected=PREREGISTRATION_PARAMS_SHA256):
    """Two different checks against two different things, kept apart on purpose.

    An EVENT at a burned coordinate may be prior context for a fresh decision — it genuinely
    happened before, and excluding it would report a zero that is a collection artefact. A burned
    MEMBER may never be an evaluated subject, a label, tuning data or performance evidence, because
    its outcome has already been measured.

    `expected` is exposed so the code's own copy of the role table can be reached past the hash. A
    document re-pinned after loosening one of these is precisely the case the second copy is for.
    """
    params = assert_preregistration(params, expected)
    if role not in BURNED_ROLES:
        raise ContractViolation(f"role {role!r} is not one of {list(BURNED_ROLES)}")
    if not slot_is_burned(slot):
        return True
    permitted_by_document = {
        ROLE_PRIOR_CONTEXT: params["burned_events_permitted_as_context"],
        ROLE_EVALUATED_SUBJECT: params["burned_members_permitted_as_examples"],
        ROLE_LABEL_SOURCE: params["burned_members_permitted_as_labels"],
        ROLE_TUNING_DATA: params["burned_members_permitted_as_tuning_data"],
        ROLE_PERFORMANCE_EVIDENCE: params["burned_members_permitted_as_performance_evidence"],
    }
    if permitted_by_document[role] != BURNED_ROLE_PERMITTED[role]:
        raise PreregistrationMismatch(
            f"the document and this code disagree about whether a burned datum may be {role!r}")
    if not BURNED_ROLE_PERMITTED[role]:
        raise ContractViolation(
            f"slot {slot} is inside a burned range and may not be used as {role!r}. A burned curve "
            "may appear in a FEATURE and may never appear in a METRIC: its outcome has already "
            "been measured, so anything computed from it is measured on data already used")
    return True


def assert_context_not_excluded(window, events, retained):
    """What the window admits must be what the collector kept. Excluding burned context is an error.

    Takes the retained set as an argument rather than recomputing it, so the check is against what a
    caller ACTUALLY kept rather than against this module's own opinion twice over.

    A creator who demonstrably launched during a burned range must not be reported as having no
    prior launches. That zero would be a collection artefact presented as a fact about the creator,
    which is the exact failure `_observed` naming exists to prevent.
    """
    def keys(items):
        return {tuple(item[field] for field in COORDINATE_FIELDS) for item in items}

    admitted = keys(e for e in events if in_window(e, window))
    dropped = admitted - keys(retained)
    burned_dropped = sorted(k for k in dropped if slot_is_burned(k[0]))
    if burned_dropped:
        raise ContractViolation(
            f"{len(burned_dropped)} events inside the lookback were dropped for being in a burned "
            f"range (first at slot {burned_dropped[0][0]}). Burned events that genuinely precede a "
            "fresh decision are prior CONTEXT and must be counted; dropping them reports a zero "
            "that is a collection artefact presented as a fact about the actor")
    if dropped:
        raise ContractViolation(
            f"{len(dropped)} events inside the lookback were not retained; the window defines what "
            "the history contains, and a collector that keeps less has silently shortened it")
    surplus = keys(retained) - admitted
    if surplus:
        raise ContractViolation(
            f"{len(surplus)} retained events are outside the lookback window; anything past t0 is "
            "the leak this whole contract exists to prevent")
    return True


# --------------------------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------------------------

def assert_snapshot_atomic(observed_slots):
    """One slot, or it is not a snapshot of anything.

    Balances read across a range can double-count a transfer or lose it, and neither shows up as an
    error anywhere.
    """
    distinct = sorted(set(observed_slots))
    if not distinct:
        raise ContractViolation(f"{AB06_SNAPSHOT_NOT_ATOMIC}: a snapshot observed at no slot")
    if len(distinct) > 1:
        raise ContractViolation(
            f"{AB06_SNAPSHOT_NOT_ATOMIC}: balances were read across slots {distinct[0]}–"
            f"{distinct[-1]}. A transfer between two reads can appear twice or vanish, and neither "
            "shows up as an error")
    return distinct[0]


# --------------------------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------------------------

# A plan is never a result, and the constant says so in one place so the claim cannot drift.
PLAN_COLLECTION_PERFORMED = False

PLAN_FIELDS = ("schema_version", "preregistration_id", "preregistration_sha256", "lookback_slots",
               "cohort_size", "windows", "unlock_required", "method_allowlist", "abort_codes",
               "collection_performed", "plan_sha256")


def plan_collection(decisions, enumeration, params=None):
    """A plan, not a collection. Nothing here queries anything.

    `decisions` maps an actor identifier to that actor's t0 coordinate. Every window is computed
    from t0 and the frozen constant alone.
    """
    params = assert_preregistration(params)
    assert_cohort(decisions.keys(), enumeration, params)
    windows = {actor: lookback_window(t0, params) for actor, t0 in decisions.items()}
    plan = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": PREREGISTRATION_ID,
        "preregistration_sha256": preregistration_hash(params),
        "lookback_slots": params["lookback_slots"],
        "cohort_size": len(windows),
        "windows": windows,
        "unlock_required": params["required_unlock_criterion"],
        "method_allowlist": list(params["method_allowlist"]),
        "abort_codes": list(ABORT_CODES),
        # Stated on the artifact itself, so a plan can never be mistaken for a result.
        "collection_performed": PLAN_COLLECTION_PERFORMED,
        "plan_sha256": None,
    }
    assert_no_credential(plan)
    plan["plan_sha256"] = hashlib.sha256(
        B10B.canonical_json({k: v for k, v in plan.items()
                             if k != "plan_sha256"}).encode("utf-8")).hexdigest()
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    params = assert_preregistration()
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": PREREGISTRATION_ID,
        "preregistration_sha256": preregistration_hash(params),
        "lookback_slots": LOOKBACK_SLOTS,
        "lookback_derivation": f"{B11A.B9D_CUTOFF_SLOT} - {B11A.B8B_WINDOW_START_SLOT}",
        "wall_clock_translation_permitted": False,
        "lower_bound_granularity": "slot",
        "upper_bound_granularity": "coordinate",
        "minimum_slot": MINIMUM_SLOT,
        "burned_role_permitted": BURNED_ROLE_PERMITTED,
        "abort_codes": list(ABORT_CODES),
        "method_allowlist": list(params["method_allowlist"]),
        "coverage_averaging_permitted": False,
        "collection_performed": False,
        "queries_made": 0,
        "b11a_enumerated": False,
        "refusing_operations": ["hours_of_lookback", "coverage_fraction"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ContractViolation: {error}", file=sys.stderr)
        sys.exit(2)
