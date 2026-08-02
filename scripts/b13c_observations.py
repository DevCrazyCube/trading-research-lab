"""B13c — leakage-safe EXTERNAL OBSERVATION LEDGER. Offline library. No network, no vendors.

What this module is
-------------------
An immutable record of things observed OUTSIDE the chain — token metadata, social posts, news
articles, timestamped financial facts and configuration facts — each carrying enough provenance to
answer one question exactly: **could we actually have known this, at that instant?**

The leak this module exists to prevent
--------------------------------------
On-chain leakage is easy to see: a coordinate is either at or before t0 or it is not. External data
has a second clock, and the second clock is where the leak hides. An article published last Tuesday
but *fetched* today is not evidence a decision last Tuesday could have used, and nothing about the
article says so. Backfilling it is the single most natural mistake in this whole area, and it
produces a backtest that is right for a reason that will never repeat.

So the availability rule is deliberately strict and needs BOTH clocks:

    An observation is feature-eligible at t0 only if we actually RECEIVED it at or before t0
    AND its claimed publication/effective time is at or before t0.

Neither half implies the other. Receipt without publication admits a provider's future-dated post;
publication without receipt admits the backfill. Missing or ambiguous clocks yield UNAVAILABLE and
never a guess — an unbounded time claim cannot be shown to precede anything.

History is never rewritten
--------------------------
A correction, an edit and a deletion are each a NEW observation in a revision chain. As-of replay
returns the latest revision actually known by t0 and preserves every prior one, so a decision made
before a correction arrived is replayed against what it actually saw. A deletion received after t0
does not reach back and remove the text a decision was made on; that would be leakage wearing the
costume of data hygiene.

Four times, kept apart
----------------------
`event_time` (when the thing happened), `publication_time` (when the provider says it was
published), `receipt_time` (when we got it, on both a wall and a monotonic clock) and
`effective_coordinate` (the on-chain instant, where one applies). Collapsing any two of these is how
a leak becomes invisible.

What this module refuses to compute
-----------------------------------
No sentiment, no embedding, no engagement or popularity score, no source-credibility probability, no
price or market-cap transform, no feature distribution. **No LLM is in the live decision path.**
Those are judgements, and a judgement stored beside an observation becomes indistinguishable from
one. A raw quoted value is representable; a transform of it is not.

A ticker is not a token
-----------------------
`mapping_status` separates an exact mint/account binding from a name or ticker match and from a
provider's bare claim. A ticker collision is the cheapest possible way to attach a stranger's news
to a token, so an exact binding requires evidence and everything else is labelled as what it is.

Nothing here collects. No adapter, no credential, no vendor, no purchase. Synthetic fixtures only.
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

AVAILABILITY_RULE = (
    "An external observation is feature-eligible at t0 if and only if it was RECEIVED by us at a "
    "wall-clock instant at or before t0's, AND its claimed publication/effective instant is at or "
    "before t0's. Both halves are required and neither implies the other: receipt alone admits a "
    "provider's future-dated item, publication alone admits an article fetched later and backfilled "
    "into an earlier decision. A time claim that is unavailable, or whose latest possible instant "
    "cannot be bounded, is never eligible — an unbounded claim cannot be shown to precede anything.")

# --------------------------------------------------------------------------------------------
# Absence, which is not zero and not false
# --------------------------------------------------------------------------------------------


class Absent:
    """A value we do not have. Deliberately not falsy, and deliberately not a number.

    `unknown`, `unavailable` and `deleted` are three different facts and none of them is zero. A
    sentinel that quietly evaluates to False is how "we never received a price" becomes "the price
    was nothing", so `bool()` on this raises instead of answering.
    """

    __slots__ = ("reason", "detail")

    def __init__(self, reason, detail):
        self.reason = reason
        self.detail = detail

    def __bool__(self):
        raise ObservationRefused(
            f"an absent value ({self.reason}) was used as a truth value. Absence is not falsity: "
            f"{self.detail}. Test for it explicitly with is_absent()")

    def __eq__(self, other):
        return isinstance(other, Absent) and other.reason == self.reason

    def __hash__(self):
        return hash(("Absent", self.reason))

    def __repr__(self):
        return f"Absent({self.reason!r})"


ABSENT_UNKNOWN = "unknown"
ABSENT_UNAVAILABLE = "unavailable"
ABSENT_DELETED = "deleted"
ABSENT_NOT_YET_KNOWN = "not_yet_known"
# Not merely missing: a value that cannot exist. A share of an empty denominator is undefined, and
# reporting it as zero would be the most confident possible way to be wrong.
ABSENT_UNDEFINED = "undefined"
ABSENT_REASONS = (ABSENT_UNKNOWN, ABSENT_UNAVAILABLE, ABSENT_DELETED, ABSENT_NOT_YET_KNOWN,
                  ABSENT_UNDEFINED)


def absent(reason, detail):
    if reason not in ABSENT_REASONS:
        raise ObservationRefused(f"absence reason {reason!r} is not one of {list(ABSENT_REASONS)}")
    return Absent(reason, detail)


def is_absent(value):
    return isinstance(value, Absent)


# --------------------------------------------------------------------------------------------
# Taxonomy — provider-neutral by construction
# --------------------------------------------------------------------------------------------

KIND_TOKEN_METADATA = "token_metadata"
KIND_SOCIAL_POST = "social_post"
KIND_NEWS_ARTICLE = "news_article"
KIND_FINANCIAL_QUOTE = "financial_quote"
KIND_CONFIG_FACT = "config_fact"
OBSERVATION_KINDS = (KIND_TOKEN_METADATA, KIND_SOCIAL_POST, KIND_NEWS_ARTICLE,
                     KIND_FINANCIAL_QUOTE, KIND_CONFIG_FACT)

# The taxonomy names what a thing IS, never who supplied it. A kind called `tweet` would bake one
# vendor's product into the schema and quietly stop describing the next one.
KIND_MEANING = {
    KIND_TOKEN_METADATA: "a claim about a token's name, symbol, links or supply, made off-chain",
    KIND_SOCIAL_POST: "a short public post attributed to an account on some platform; covers "
                      "tweet-like sources without naming any",
    KIND_NEWS_ARTICLE: "an article or release published by an outlet",
    KIND_FINANCIAL_QUOTE: "a timestamped market or financial fact, always with its unit and quote "
                          "asset",
    KIND_CONFIG_FACT: "a timestamped configuration or reference fact, such as a fee schedule",
}

# --------------------------------------------------------------------------------------------
# Time claims — four clocks, kept apart, never guessed
# --------------------------------------------------------------------------------------------

TIME_STATED = "stated"
TIME_UNAVAILABLE = "unavailable"
TIME_AMBIGUOUS = "ambiguous"
TIME_STATUSES = (TIME_STATED, TIME_UNAVAILABLE, TIME_AMBIGUOUS)

TIME_CLAIM_FIELDS = ("status", "value_ns", "precision_ns", "source")

CLOCKS = ("event_time", "publication_time", "receipt_time")

CLOCK_MEANING = {
    "event_time": "when the thing described actually happened",
    "publication_time": "when the provider says the item was published or last made effective",
    "receipt_time": "when WE received it — the only clock we can vouch for",
}


def time_claim(value_ns, precision_ns=0, source="", status=TIME_STATED):
    """One clock reading, with the width of its own uncertainty attached.

    `precision_ns` is not decoration. A provider that publishes a date without a time has given a
    claim covering a whole day, and the only safe reading of it is the LATEST instant it could mean.
    Recording the width lets that reading be computed instead of assumed.
    """
    return {"status": status, "value_ns": value_ns, "precision_ns": precision_ns, "source": source}


def unavailable_time(detail):
    return {"status": TIME_UNAVAILABLE, "value_ns": None, "precision_ns": None, "source": detail}


def ambiguous_time(value_ns, detail):
    """A value we have but cannot bound. Distinct from unavailable, and equally unusable."""
    return {"status": TIME_AMBIGUOUS, "value_ns": value_ns, "precision_ns": None, "source": detail}


def assert_time_claim(claim, label):
    if not isinstance(claim, dict):
        raise ObservationRefused(f"{label} must be a mapping, got {type(claim).__name__}")
    missing = [field for field in TIME_CLAIM_FIELDS if field not in claim]
    if missing:
        raise ObservationRefused(f"{label} does not state {missing}")
    unknown = [field for field in claim if field not in TIME_CLAIM_FIELDS]
    if unknown:
        raise ObservationRefused(f"{label} carries undeclared fields {sorted(unknown)}")
    if claim["status"] not in TIME_STATUSES:
        raise ObservationRefused(f"{label} status {claim['status']!r} is not one of "
                                 f"{list(TIME_STATUSES)}")
    if claim["status"] == TIME_STATED:
        _integer(f"{label} value_ns", claim["value_ns"])
        _non_negative(f"{label} precision_ns", claim["precision_ns"])
    elif claim["status"] == TIME_AMBIGUOUS:
        if claim["precision_ns"] is not None:
            raise ObservationRefused(
                f"{label} is ambiguous yet states a precision. A claim whose width is known is not "
                "ambiguous — state it and let the boundary arithmetic use it")
    else:
        if claim["value_ns"] is not None or claim["precision_ns"] is not None:
            raise ObservationRefused(
                f"{label} is unavailable yet carries a value; an unavailable clock has no reading")
    if not isinstance(claim["source"], str):
        raise ObservationRefused(f"{label} source must be a string")
    return claim


def latest_possible(claim):
    """The latest instant a claim could mean, or an Absent if it cannot be bounded.

    Conservative on purpose. For eligibility we must show the item existed BY t0, so the question is
    always "could it still have been later?" — and only the upper end of the interval answers that.
    """
    if claim["status"] == TIME_UNAVAILABLE:
        return absent(ABSENT_UNAVAILABLE, "the clock reading was never supplied")
    if claim["status"] == TIME_AMBIGUOUS:
        return absent(ABSENT_UNAVAILABLE,
                      "the claim has a value but no bound on its width, so its latest possible "
                      "instant is unknown and it cannot be shown to precede anything")
    return claim["value_ns"] + claim["precision_ns"]


# --------------------------------------------------------------------------------------------
# Mapping — a ticker is not a token
# --------------------------------------------------------------------------------------------

MAPPING_EXACT_BINDING = "exact_binding"
MAPPING_UNVERIFIED = "unverified_mapping"
MAPPING_SOURCE_CLAIM = "source_claim"
MAPPING_UNMAPPED = "unmapped"
MAPPING_STATUSES = (MAPPING_EXACT_BINDING, MAPPING_UNVERIFIED, MAPPING_SOURCE_CLAIM,
                    MAPPING_UNMAPPED)

MAPPING_MEANING = {
    MAPPING_EXACT_BINDING: "the payload itself contains the mint or account address, and the "
                           "binding evidence names where",
    MAPPING_UNVERIFIED: "a name or ticker matched. This is NOT token identity: tickers collide, "
                        "and attaching a stranger's news to a token is the cheapest error here",
    MAPPING_SOURCE_CLAIM: "the provider asserts the mapping and we have not checked it. A claim "
                          "about identity is still a claim",
    MAPPING_UNMAPPED: "no mapping was attempted or none was found",
}

MAPPING_FIELDS = ("status", "mint", "account", "matched_text", "binding_evidence", "detail")

# --------------------------------------------------------------------------------------------
# Licence and retention — what we are allowed to keep, and what we actually kept
# --------------------------------------------------------------------------------------------

LICENSE_UNKNOWN = "unknown"
LICENSE_PERMITS_STORAGE = "permits_storage"
LICENSE_REFERENCE_ONLY = "reference_only"
LICENSE_PROHIBITED = "prohibited"
LICENSE_STATUSES = (LICENSE_UNKNOWN, LICENSE_PERMITS_STORAGE, LICENSE_REFERENCE_ONLY,
                    LICENSE_PROHIBITED)

RETENTION_RAW_RETAINED = "raw_retained"
RETENTION_HASH_ONLY = "hash_only"
RETENTION_PURGED = "purged"
RETENTION_STATUSES = (RETENTION_RAW_RETAINED, RETENTION_HASH_ONLY, RETENTION_PURGED)

# Which retentions each licence permits. Enforced rather than documented, because a licence recorded
# beside a payload it forbids is a licence nobody is honouring.
LICENSE_PERMITS = {
    LICENSE_PERMITS_STORAGE: (RETENTION_RAW_RETAINED, RETENTION_HASH_ONLY, RETENTION_PURGED),
    LICENSE_REFERENCE_ONLY: (RETENTION_HASH_ONLY, RETENTION_PURGED),
    LICENSE_PROHIBITED: (RETENTION_HASH_ONLY, RETENTION_PURGED),
    # Unknown is the fail-closed case: we may keep a hash so the item can be recognised later, and
    # nothing else. Storing raw text under an unknown licence is a decision nobody made.
    LICENSE_UNKNOWN: (RETENTION_HASH_ONLY, RETENTION_PURGED),
}

# --------------------------------------------------------------------------------------------
# Revisions — corrections never rewrite
# --------------------------------------------------------------------------------------------

REVISION_CREATE = "create"
REVISION_EDIT = "edit"
REVISION_DELETE = "delete"
REVISION_RESTORE = "restore"
REVISION_KINDS = (REVISION_CREATE, REVISION_EDIT, REVISION_DELETE, REVISION_RESTORE)

# --------------------------------------------------------------------------------------------
# Record shape
# --------------------------------------------------------------------------------------------

IDENTITY_FIELDS = ("provider", "provider_observation_id", "observation_kind")

PROVENANCE_FIELDS = ("query_spec_sha256", "fetch_session_id", "fetch_provenance_sha256",
                     "decoder_name", "decoder_version")

PAYLOAD_FIELDS = ("payload_sha256", "payload_byte_length", "payload_reference", "raw_payload")

TIMES_FIELDS = ("event_time", "publication_time", "receipt_time", "receipt_monotonic_ns",
                "effective_coordinate")

REVISION_FIELDS = ("revision_kind", "revision_index", "supersedes_observation_sha256")

# Numeric and boolean only. Same rule as B13a/B13b, for the same reason: it is checkable without
# anyone having to notice which strings happen to be text, URLs or handles.
FEATURE_FIELDS = ("payload_byte_length", "revision_index", "is_deletion",
                  "publication_time_available", "receipt_time_available",
                  "event_time_available", "mapping_is_exact_binding", "raw_payload_retained")

# A measured value NEVER travels without its unit. Putting the number in the feature block and the
# unit somewhere else would guarantee that one day they are read apart, so financial values live
# here — together — and not among the features at all.
MEASUREMENT_FIELDS = ("value_numerator", "value_denominator", "unit", "quote_asset",
                      "effective_time", "measurement_basis")

OBSERVATION_FIELDS = ("schema_version", "availability_rule", "identity", "provenance", "payload",
                      "times", "revision", "mapping", "license_status", "retention_status",
                      "features", "measurement", "evidence", "observation_sha256")

# Any key whose name asserts a quantity this module is not entitled to compute. Checked by name,
# because the damage is done the moment a downstream reader sees it.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "sentiment", "embedding", "engagement", "popularity", "credibility", "virality", "influence",
    "score", "probability", "market_cap", "marketcap", "price_change", "pct_change", "return_",
    "momentum", "zscore", "z_score", "normali", "llm", "prompt", "completion_", "confidence",
    "bullish", "bearish", "hype", "trending",
)

A01_RECEIVED_AFTER_T0 = "A01_received_after_t0"
A02_PUBLISHED_AFTER_T0 = "A02_published_after_t0"
A03_RECEIPT_TIME_UNAVAILABLE = "A03_receipt_time_unavailable"
A04_PUBLICATION_TIME_UNAVAILABLE = "A04_publication_time_unavailable"
A05_MAPPING_NOT_EXACT = "A05_mapping_not_exact"
A06_LICENSE_PROHIBITS_USE = "A06_license_prohibits_use"
A07_PAYLOAD_PURGED = "A07_payload_purged"
A08_DECODER_UNPINNED = "A08_decoder_unpinned"
INELIGIBILITY_CODES = (A01_RECEIVED_AFTER_T0, A02_PUBLISHED_AFTER_T0, A03_RECEIPT_TIME_UNAVAILABLE,
                       A04_PUBLICATION_TIME_UNAVAILABLE, A05_MAPPING_NOT_EXACT,
                       A06_LICENSE_PROHIBITS_USE, A07_PAYLOAD_PURGED, A08_DECODER_UNPINNED)

DECISION_INSTANT_FIELDS = ("wall_ns", "coordinate", "wall_clock_provenance")


class ObservationRefused(B13A.HistoryRefused):
    """Raised when an external observation cannot be used without asserting something untrue."""


class DerivedQuantityRefused(ObservationRefused):
    """Raised when a caller asks this module to compute a judgement rather than record a fact.

    A separate class because it is a different refusal: the input is fine, the question is out of
    scope, and the caller needs to know which.
    """


# --------------------------------------------------------------------------------------------
# The computations that fail closed
# --------------------------------------------------------------------------------------------

_DERIVED_REFUSAL = (
    "{what} is a JUDGEMENT, not an observation. Stored beside a raw item it becomes "
    "indistinguishable from one, and three phases later nobody remembers which was inferred. This "
    "ledger records what a provider said and when we learned it; deriving a quantity from that "
    "needs its own preregistration, its own validation set and its own leakage argument.")


def sentiment(*_args, **_kwargs):
    """Never returns."""
    raise DerivedQuantityRefused(_DERIVED_REFUSAL.format(what="A sentiment"))


def embedding(*_args, **_kwargs):
    """Never returns."""
    raise DerivedQuantityRefused(_DERIVED_REFUSAL.format(what="An embedding"))


def engagement_score(*_args, **_kwargs):
    """Never returns."""
    raise DerivedQuantityRefused(_DERIVED_REFUSAL.format(what="An engagement or popularity score"))


def source_credibility(*_args, **_kwargs):
    """Never returns."""
    raise DerivedQuantityRefused(_DERIVED_REFUSAL.format(what="A source-credibility probability"))


def market_cap(*_args, **_kwargs):
    """Never returns."""
    raise DerivedQuantityRefused(_DERIVED_REFUSAL.format(
        what="A market capitalisation or price transform"))


def call_language_model(*_args, **_kwargs):
    """Never returns. NO LANGUAGE MODEL IS IN THE LIVE DECISION PATH."""
    raise DerivedQuantityRefused(
        "No language model is in the live decision path, and this function exists so that reaching "
        "for one is a refusal rather than a blank page. A model in the path would make every "
        "decision unreproducible, unauditable at the instant it mattered, and dependent on a remote "
        "service whose behaviour changes without notice.")


LLM_IN_DECISION_PATH = False


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
    """No float anywhere. A derived quantity arrives as one, and this catches it by type."""
    for path, value in _walk(record):
        if isinstance(value, float):
            raise ObservationRefused(
                f"{path} is the float {value!r}. No float may appear in this ledger: an observation "
                "is a recorded fact, and a non-integer is a number somebody computed. Exact values "
                "travel as a numerator and denominator")
    return True


def assert_no_derived_quantity(record):
    """Refuse any field whose NAME asserts a judgement this module may not make."""
    for path, value in _walk(record):
        if not isinstance(value, dict):
            continue
        for key in value:
            lowered = str(key).lower()
            for banned in FORBIDDEN_FIELD_SUBSTRINGS:
                if banned in lowered:
                    raise DerivedQuantityRefused(
                        f"{path}.{key} contains {banned!r}. This ledger may not carry a field whose "
                        "name asserts a sentiment, a score, a probability or a price transform; the "
                        "name alone would tell a later reader that such a thing was established "
                        "here")
    assert_no_float(record)
    return True


def assert_no_string_in_features(features, label="observation"):
    for field, value in features.items():
        if isinstance(value, str):
            raise ObservationRefused(
                f"{label} feature {field!r} is the string {value!r}. NO STRING MAY APPEAR IN A "
                "FEATURE BLOCK — raw text, URLs and handles live in the evidence block, and that is "
                "what keeps them out of a model without anyone having to notice which strings are "
                "which")
        if value is not None and not isinstance(value, (int, bool)):
            raise ObservationRefused(
                f"{label} feature {field!r} is a {type(value).__name__}; features are integers, "
                "booleans or null")
    return True


def assert_disjoint_blocks(evidence_fields, feature_fields):
    """No field may be both evidence and a feature.

    Takes its field sets as arguments so the check is reachable; with the shipped tuples it can
    never fire, and a guard nobody can make fire is a guard nobody can show works.
    """
    overlap = set(evidence_fields) & set(feature_fields)
    if overlap:
        raise ObservationRefused(
            f"{sorted(overlap)} is both evidence and a feature; raw text that is also a feature is "
            "raw text used for prediction")
    return True


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def _integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationRefused(f"{label} must be an integer, got {value!r}")
    return value


def _non_negative(label, value):
    _integer(label, value)
    if value < 0:
        raise ObservationRefused(f"{label} must not be negative, got {value}")
    return value


def _non_empty(label, value):
    if not isinstance(value, str) or not value:
        raise ObservationRefused(f"{label} must be a non-empty string, got {value!r}")
    return value


def assert_mapping(mapping):
    """A ticker match is labelled a ticker match, and an exact binding must show its evidence."""
    if not isinstance(mapping, dict):
        raise ObservationRefused("mapping must be a mapping")
    missing = [field for field in MAPPING_FIELDS if field not in mapping]
    if missing:
        raise ObservationRefused(f"mapping does not state {missing}")
    unknown = [field for field in mapping if field not in MAPPING_FIELDS]
    if unknown:
        raise ObservationRefused(f"mapping carries undeclared fields {sorted(unknown)}")
    if mapping["status"] not in MAPPING_STATUSES:
        raise ObservationRefused(
            f"mapping status {mapping['status']!r} is not one of {list(MAPPING_STATUSES)}")
    if mapping["status"] == MAPPING_EXACT_BINDING:
        if not (mapping["mint"] or mapping["account"]):
            raise ObservationRefused(
                "an exact binding names neither a mint nor an account. Exact means the address is "
                "there, not that we are confident")
        if not mapping["binding_evidence"]:
            raise ObservationRefused(
                "an exact binding must show where the address was found; 'exact' means the address "
                "is there, and the evidence is what says where")
    else:
        if mapping["binding_evidence"]:
            raise ObservationRefused(
                f"mapping status is {mapping['status']!r} yet it carries binding evidence; binding "
                "evidence is what makes a mapping exact, so carrying it while claiming less is a "
                "record that disagrees with itself")
    if mapping["status"] == MAPPING_UNVERIFIED and not mapping["matched_text"]:
        raise ObservationRefused(
            "an unverified mapping must say what text matched, so a reader can see the collision "
            "risk they are being asked to accept")
    return mapping


def require_exact_binding(observation):
    """Fail closed for any policy that needs to know WHICH token an item is about.

    A ticker match may be perfectly good context for a human and is never token identity: symbols
    collide constantly, and attaching a stranger's news to a token is the cheapest available error.
    """
    status = observation["mapping"]["status"]
    if status != MAPPING_EXACT_BINDING:
        raise ObservationRefused(
            f"this observation's mapping is {status!r}, not an exact binding: "
            f"{MAPPING_MEANING[status]}. A policy that needs to know which token this is about "
            "cannot use it")
    return True


def assert_measurement(measurement, kind):
    """A number and its unit, together, or nothing.

    Financial values are kept out of the feature block entirely. A value that CAN be separated from
    its unit eventually will be, and lamports read as SOL is off by a factor of a billion.
    """
    if kind != KIND_FINANCIAL_QUOTE:
        if measurement is not None:
            raise ObservationRefused(
                f"a {kind} observation carries a measurement; only {KIND_FINANCIAL_QUOTE} "
                "observations state measured values")
        return None
    if not isinstance(measurement, dict):
        raise ObservationRefused(
            f"a {KIND_FINANCIAL_QUOTE} observation must carry a measurement")
    missing = [field for field in MEASUREMENT_FIELDS if field not in measurement]
    if missing:
        raise ObservationRefused(f"measurement does not state {missing}")
    unknown = [field for field in measurement if field not in MEASUREMENT_FIELDS]
    if unknown:
        raise ObservationRefused(f"measurement carries undeclared fields {sorted(unknown)}")
    _integer("measurement value_numerator", measurement["value_numerator"])
    denominator = _integer("measurement value_denominator", measurement["value_denominator"])
    if denominator <= 0:
        raise ObservationRefused(
            "measurement value_denominator must be positive; an exact value is a rational, and a "
            "float would be a number somebody rounded")
    _non_empty("measurement unit", measurement["unit"])
    _non_empty("measurement quote_asset", measurement["quote_asset"])
    _non_empty("measurement measurement_basis", measurement["measurement_basis"])
    assert_time_claim(measurement["effective_time"], "measurement effective_time")
    if measurement["effective_time"]["status"] != TIME_STATED:
        raise ObservationRefused(
            "a measurement whose effective time is not stated cannot be placed on any timeline, so "
            "it cannot be shown to precede a decision or to be fresh at one")
    return measurement


def assert_comparable(first, second):
    """Two measurements may only be compared or combined in identical units.

    Fails closed rather than converting. A conversion needs a rate, a rate is itself a timestamped
    observation, and silently supplying one here would invent data.
    """
    for label, field in (("unit", "unit"), ("quote asset", "quote_asset"),
                         ("basis", "measurement_basis")):
        if first[field] != second[field]:
            raise ObservationRefused(
                f"measurements differ in {label}: {first[field]!r} versus {second[field]!r}. They "
                "are not comparable, and converting would require a rate that is itself an "
                "observation nobody supplied")
    return True


def staleness_ns(measurement, instant):
    """How old this measurement is at `instant`, or an Absent when that cannot be said."""
    effective = latest_possible(measurement["effective_time"])
    if is_absent(effective):
        return effective
    return instant["wall_ns"] - effective


def require_fresh(measurement, instant, max_staleness_ns, rationale):
    """Fail closed on a stale value. The bound is the CALLER's and must arrive with a reason.

    No default is offered on purpose. A freshness bound is a threshold, thresholds in this project
    are preregistered, and a module that supplied one silently would have chosen it for everybody.
    """
    _non_negative("max_staleness_ns", max_staleness_ns)
    if not isinstance(rationale, str) or not rationale:
        raise ObservationRefused(
            "a freshness bound must arrive with the reason it was chosen; an unexplained threshold "
            "is one nobody can review")
    age = staleness_ns(measurement, instant)
    if is_absent(age):
        raise ObservationRefused(
            "this measurement's age cannot be computed, so it cannot be shown to be fresh: "
            f"{age.detail}")
    if age < 0:
        raise ObservationRefused(
            f"this measurement is effective {-age} ns AFTER the instant it is being used at; a "
            "value from the future is the leak this ledger exists to prevent")
    if age > max_staleness_ns:
        raise ObservationRefused(
            f"this measurement is {age} ns old at the decision instant, beyond the caller's bound "
            f"of {max_staleness_ns} ns ({rationale})")
    return True


def assert_decision_instant(instant):
    """The instant a decision was made, on BOTH clocks, with the mapping between them declared.

    A chain coordinate does not carry a wall time, and the mapping between them is itself an
    observation with error. This module refuses to derive one: the caller supplies the wall instant
    and says where it came from, so a later reader can audit the join rather than discover it.
    """
    if not isinstance(instant, dict):
        raise ObservationRefused("decision instant must be a mapping")
    missing = [field for field in DECISION_INSTANT_FIELDS if field not in instant]
    if missing:
        raise ObservationRefused(f"decision instant does not state {missing}")
    unknown = [field for field in instant if field not in DECISION_INSTANT_FIELDS]
    if unknown:
        raise ObservationRefused(f"decision instant carries undeclared fields {sorted(unknown)}")
    _integer("decision instant wall_ns", instant["wall_ns"])
    coordinate = instant["coordinate"]
    if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
        raise ObservationRefused(
            f"decision instant must carry a full canonical coordinate {list(COORDINATE_FIELDS)}")
    for field in COORDINATE_FIELDS:
        _integer(f"decision instant coordinate {field}", coordinate[field])
    if not instant["wall_clock_provenance"]:
        raise ObservationRefused(
            "decision instant must say where its wall time came from. A chain coordinate carries no "
            "wall time, and the mapping between them is itself an observation with error; deriving "
            "one here would hide a join a later reader needs to audit")
    return instant


def assert_observation(observation):
    """One observation, fully specified. Absence is refusal, never a default."""
    if not isinstance(observation, dict):
        raise ObservationRefused(
            f"observation must be a mapping, got {type(observation).__name__}")
    missing = [field for field in OBSERVATION_FIELDS if field not in observation]
    if missing:
        raise ObservationRefused(f"observation does not carry {missing}")
    unknown = [field for field in observation if field not in OBSERVATION_FIELDS]
    if unknown:
        raise ObservationRefused(
            f"observation carries undeclared fields {sorted(unknown)}; a record shape nobody "
            "declared is a record shape nobody reviewed")
    if observation["availability_rule"] != AVAILABILITY_RULE:
        raise ObservationRefused(
            "the availability rule on this observation is not the one this module applies")

    identity = observation["identity"]
    if set(identity) != set(IDENTITY_FIELDS):
        raise ObservationRefused(
            f"identity block is {sorted(identity)}, contract says {sorted(IDENTITY_FIELDS)}")
    kind = identity["observation_kind"]
    if kind not in OBSERVATION_KINDS:
        raise ObservationRefused(f"observation kind {kind!r} is not one of "
                                 f"{list(OBSERVATION_KINDS)}")
    _non_empty("provider", identity["provider"])
    _non_empty("provider_observation_id", identity["provider_observation_id"])

    provenance = observation["provenance"]
    if set(provenance) != set(PROVENANCE_FIELDS):
        raise ObservationRefused(
            f"provenance block is {sorted(provenance)}, contract says {sorted(PROVENANCE_FIELDS)}")
    for field in PROVENANCE_FIELDS:
        _non_empty(f"provenance {field}", provenance[field])

    payload = observation["payload"]
    if set(payload) != set(PAYLOAD_FIELDS):
        raise ObservationRefused(
            f"payload block is {sorted(payload)}, contract says {sorted(PAYLOAD_FIELDS)}")
    _non_empty("payload_sha256", payload["payload_sha256"])
    _non_negative("payload_byte_length", payload["payload_byte_length"])

    times = observation["times"]
    if set(times) != set(TIMES_FIELDS):
        raise ObservationRefused(
            f"times block is {sorted(times)}, contract says {sorted(TIMES_FIELDS)}")
    for clock in CLOCKS:
        assert_time_claim(times[clock], clock)
    _integer("receipt_monotonic_ns", times["receipt_monotonic_ns"])
    if times["effective_coordinate"] is not None:
        coordinate = times["effective_coordinate"]
        if not isinstance(coordinate, dict) or set(coordinate) != set(COORDINATE_FIELDS):
            raise ObservationRefused(
                "effective_coordinate must be a full canonical coordinate or null")
        for field in COORDINATE_FIELDS:
            _integer(f"effective_coordinate {field}", coordinate[field])

    revision = observation["revision"]
    if set(revision) != set(REVISION_FIELDS):
        raise ObservationRefused(
            f"revision block is {sorted(revision)}, contract says {sorted(REVISION_FIELDS)}")
    if revision["revision_kind"] not in REVISION_KINDS:
        raise ObservationRefused(
            f"revision kind {revision['revision_kind']!r} is not one of {list(REVISION_KINDS)}")
    _non_negative("revision_index", revision["revision_index"])
    if revision["revision_kind"] == REVISION_CREATE:
        if revision["revision_index"] != 0 or revision["supersedes_observation_sha256"]:
            raise ObservationRefused(
                "a create is revision 0 and supersedes nothing; anything else is an edit wearing "
                "the wrong label")
    else:
        if revision["revision_index"] == 0 or not revision["supersedes_observation_sha256"]:
            raise ObservationRefused(
                f"a {revision['revision_kind']} must name the observation it supersedes. A "
                "correction that cannot point at what it corrects rewrites history instead of "
                "recording it")

    assert_mapping(observation["mapping"])
    if observation["license_status"] not in LICENSE_STATUSES:
        raise ObservationRefused(
            f"license status {observation['license_status']!r} is not one of "
            f"{list(LICENSE_STATUSES)}")
    if observation["retention_status"] not in RETENTION_STATUSES:
        raise ObservationRefused(
            f"retention status {observation['retention_status']!r} is not one of "
            f"{list(RETENTION_STATUSES)}")
    permitted = LICENSE_PERMITS[observation["license_status"]]
    if observation["retention_status"] not in permitted:
        raise ObservationRefused(
            f"licence {observation['license_status']!r} permits {list(permitted)} but this record "
            f"is {observation['retention_status']!r}. A licence recorded beside a payload it "
            "forbids is a licence nobody is honouring")
    if observation["retention_status"] == RETENTION_RAW_RETAINED:
        if payload["raw_payload"] is None:
            raise ObservationRefused("retention says the raw payload was kept but none is present")
        if hashlib.sha256(payload["raw_payload"].encode("utf-8")).hexdigest() \
                != payload["payload_sha256"]:
            raise ObservationRefused(
                "the retained payload does not hash to the recorded digest. Either the bytes "
                "drifted or the digest did, and there is no way to tell which from here")
        if len(payload["raw_payload"].encode("utf-8")) != payload["payload_byte_length"]:
            raise ObservationRefused("the retained payload's length disagrees with the record")
    elif payload["raw_payload"] is not None:
        raise ObservationRefused(
            f"retention is {observation['retention_status']!r} yet a raw payload is present; the "
            "record and the storage disagree about what we kept")

    if set(observation["features"]) != set(FEATURE_FIELDS):
        raise ObservationRefused(
            f"feature block is {sorted(observation['features'])}, contract says "
            f"{sorted(FEATURE_FIELDS)}")
    assert_no_string_in_features(observation["features"])
    assert_disjoint_blocks(tuple(observation["evidence"]), FEATURE_FIELDS)
    _assert_features_agree(observation)
    assert_measurement(observation["measurement"], kind)
    assert_no_derived_quantity(observation)
    return observation


def _assert_features_agree(observation):
    """The numeric view must describe the record it ships with, not something else."""
    features, times = observation["features"], observation["times"]
    expected = {
        "payload_byte_length": observation["payload"]["payload_byte_length"],
        "revision_index": observation["revision"]["revision_index"],
        "is_deletion": observation["revision"]["revision_kind"] == REVISION_DELETE,
        "publication_time_available": times["publication_time"]["status"] == TIME_STATED,
        "receipt_time_available": times["receipt_time"]["status"] == TIME_STATED,
        "event_time_available": times["event_time"]["status"] == TIME_STATED,
        "mapping_is_exact_binding":
            observation["mapping"]["status"] == MAPPING_EXACT_BINDING,
        "raw_payload_retained": observation["retention_status"] == RETENTION_RAW_RETAINED,
    }
    for field, value in expected.items():
        if features[field] != value:
            raise ObservationRefused(
                f"feature {field!r} says {features[field]!r} while the record says {value!r}; the "
                "one place a numeric view could quietly disagree with the evidence under it")
    return True


def observation_hash(observation):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in observation.items()
         if k != "observation_sha256"}).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------------------------

def exact_binding(mint=None, account=None, binding_evidence="", detail=""):
    """The only mapping that asserts identity, and it must show where the address was found."""
    return {"status": MAPPING_EXACT_BINDING, "mint": mint, "account": account,
            "matched_text": None, "binding_evidence": binding_evidence, "detail": detail}


def ticker_mapping(matched_text, mint=None, detail=""):
    """A name or ticker matched. NOT identity — this is where collisions live."""
    return {"status": MAPPING_UNVERIFIED, "mint": mint, "account": None,
            "matched_text": matched_text, "binding_evidence": None, "detail": detail}


def claimed_mapping(mint=None, account=None, detail=""):
    """The provider says so and we have not checked. A claim about identity is still a claim."""
    return {"status": MAPPING_SOURCE_CLAIM, "mint": mint, "account": account,
            "matched_text": None, "binding_evidence": None, "detail": detail}


def unmapped(detail=""):
    return {"status": MAPPING_UNMAPPED, "mint": None, "account": None, "matched_text": None,
            "binding_evidence": None, "detail": detail}


def build_observation(provider, provider_observation_id, kind, query_spec_sha256,
                      fetch_session_id, fetch_provenance_sha256, decoder_name, decoder_version,
                      receipt_time, publication_time, receipt_monotonic_ns,
                      event_time=None, raw_payload=None, payload_sha256=None,
                      payload_byte_length=None, payload_reference=None,
                      effective_coordinate=None, revision_kind=REVISION_CREATE, revision_index=0,
                      supersedes=None, mapping=None, license_status=LICENSE_UNKNOWN,
                      retention_status=RETENTION_HASH_ONLY, measurement=None, evidence=None):
    """Assemble one observation, deriving the numeric view from the record rather than beside it.

    The feature block is COMPUTED here, never passed in. A caller who hand-wrote it could state that
    a publication time was available when it was not, and that single boolean is the whole
    availability rule.
    """
    if raw_payload is not None:
        encoded = raw_payload.encode("utf-8")
        payload_sha256 = payload_sha256 or hashlib.sha256(encoded).hexdigest()
        payload_byte_length = len(encoded) if payload_byte_length is None else payload_byte_length
    if payload_sha256 is None:
        raise ObservationRefused(
            "an observation must carry a payload digest even when the bytes were not kept; without "
            "one there is no way to recognise the same item again")
    times = {
        "event_time": event_time or unavailable_time("the provider stated no event time"),
        "publication_time": publication_time,
        "receipt_time": receipt_time,
        "receipt_monotonic_ns": receipt_monotonic_ns,
        "effective_coordinate": effective_coordinate,
    }
    mapping = mapping if mapping is not None else unmapped("no mapping was attempted")
    observation = {
        "schema_version": SCHEMA_VERSION,
        "availability_rule": AVAILABILITY_RULE,
        "identity": {"provider": provider, "provider_observation_id": provider_observation_id,
                     "observation_kind": kind},
        "provenance": {"query_spec_sha256": query_spec_sha256,
                       "fetch_session_id": fetch_session_id,
                       "fetch_provenance_sha256": fetch_provenance_sha256,
                       "decoder_name": decoder_name, "decoder_version": decoder_version},
        "payload": {"payload_sha256": payload_sha256,
                    "payload_byte_length": payload_byte_length or 0,
                    "payload_reference": payload_reference, "raw_payload": raw_payload},
        "times": times,
        "revision": {"revision_kind": revision_kind, "revision_index": revision_index,
                     "supersedes_observation_sha256": supersedes},
        "mapping": mapping,
        "license_status": license_status,
        "retention_status": retention_status,
        "features": {},
        "measurement": measurement,
        "evidence": dict(evidence or {}),
        "observation_sha256": None,
    }
    observation["features"] = {
        "payload_byte_length": observation["payload"]["payload_byte_length"],
        "revision_index": revision_index,
        "is_deletion": revision_kind == REVISION_DELETE,
        "publication_time_available": times["publication_time"]["status"] == TIME_STATED,
        "receipt_time_available": times["receipt_time"]["status"] == TIME_STATED,
        "event_time_available": times["event_time"]["status"] == TIME_STATED,
        "mapping_is_exact_binding": mapping["status"] == MAPPING_EXACT_BINDING,
        "raw_payload_retained": retention_status == RETENTION_RAW_RETAINED,
    }
    assert_observation(observation)
    observation["observation_sha256"] = observation_hash(observation)
    return observation


# --------------------------------------------------------------------------------------------
# The availability rule
# --------------------------------------------------------------------------------------------

def ineligibility(observation, instant, require_binding=True):
    """Why this observation may not feed a decision at `instant`. Empty means it may.

    Reason codes rather than a bare False: "not eligible" tells an operator nothing about whether
    the item is unusable forever, unusable yet, or unusable for this token.
    """
    assert_decision_instant(instant)
    reasons = []
    receipt = latest_possible(observation["times"]["receipt_time"])
    if is_absent(receipt):
        reasons.append({"reason_code": A03_RECEIPT_TIME_UNAVAILABLE,
                        "detail": "we cannot say when we received this, so we cannot say we had it"})
    elif receipt > instant["wall_ns"]:
        reasons.append({
            "reason_code": A01_RECEIVED_AFTER_T0,
            "detail": f"received at {receipt} ns, after the decision at {instant['wall_ns']} ns. An "
                      "item fetched later cannot be backfilled into an earlier decision"})

    published = latest_possible(observation["times"]["publication_time"])
    if is_absent(published):
        reasons.append({"reason_code": A04_PUBLICATION_TIME_UNAVAILABLE,
                        "detail": f"the publication claim cannot be bounded: {published.detail}"})
    elif published > instant["wall_ns"]:
        reasons.append({
            "reason_code": A02_PUBLISHED_AFTER_T0,
            "detail": f"published at {published} ns, after the decision at {instant['wall_ns']} ns"})

    if require_binding and observation["mapping"]["status"] != MAPPING_EXACT_BINDING:
        reasons.append({
            "reason_code": A05_MAPPING_NOT_EXACT,
            "detail": f"mapping is {observation['mapping']['status']!r}: "
                      f"{MAPPING_MEANING[observation['mapping']['status']]}"})
    if observation["license_status"] == LICENSE_PROHIBITED:
        reasons.append({"reason_code": A06_LICENSE_PROHIBITS_USE,
                        "detail": "the licence prohibits use of this content"})
    if observation["retention_status"] == RETENTION_PURGED:
        reasons.append({"reason_code": A07_PAYLOAD_PURGED,
                        "detail": "the payload was purged, so nothing remains to read"})
    if not observation["provenance"]["decoder_version"]:
        reasons.append({"reason_code": A08_DECODER_UNPINNED,
                        "detail": "the decoder version is unpinned, so the parse cannot be "
                                  "reproduced"})
    return reasons


def feature_eligible(observation, instant, require_binding=True):
    return not ineligibility(observation, instant, require_binding=require_binding)


def require_eligible(observation, instant, require_binding=True):
    """Fail closed. Building a ledger of ineligible items is fine; USING one is not."""
    reasons = ineligibility(observation, instant, require_binding=require_binding)
    if reasons:
        raise ObservationRefused(
            "this observation was not available to a decision at that instant: "
            + "; ".join(f"{r['reason_code']} — {r['detail']}" for r in reasons))
    return True


# --------------------------------------------------------------------------------------------
# Revision chains — as-of replay that preserves every prior version
# --------------------------------------------------------------------------------------------

def chain_key(observation):
    return (observation["identity"]["provider"],
            observation["identity"]["provider_observation_id"])


def ordered_observations(observations):
    """Canonically ordered and duplicate-free. Arrival order is never trusted.

    Sorting here rather than requiring sorted input is deliberate: a caller who happened to read
    rows in insertion order would otherwise get a different as-of answer from the same evidence, and
    the difference would be invisible.
    """
    if isinstance(observations, (dict, str, bytes)):
        raise ObservationRefused("observations must be a sequence of observation mappings")
    decorated, seen = [], set()
    for position, observation in enumerate(observations):
        assert_observation(observation)
        digest = observation_hash(observation)
        if digest in seen:
            raise ObservationRefused(
                f"observation {position} duplicates an earlier one ({digest[:12]}); the same item "
                "counted twice inflates every total derived from it")
        seen.add(digest)
        decorated.append(((chain_key(observation),
                           observation["revision"]["revision_index"], digest), observation))
    decorated.sort(key=lambda pair: pair[0])
    return [observation for _, observation in decorated]


def revision_chain(observations, provider, provider_observation_id):
    return [observation for observation in ordered_observations(observations)
            if chain_key(observation) == (provider, provider_observation_id)]


def assert_revision_chain(chain):
    """One create, contiguous indices, each revision pointing at the one before it.

    And the monotonic receipt clock must not run backwards within a fetch session. That is exactly
    why both clocks are recorded: a wall clock can legitimately jump — NTP, a suspend, a timezone
    mistake — so it cannot detect reordering, and a monotonic clock can.
    """
    if not chain:
        raise ObservationRefused("a revision chain with no observations describes nothing")
    keys = {chain_key(observation) for observation in chain}
    if len(keys) != 1:
        raise ObservationRefused(
            f"a revision chain must be about one provider item, got {sorted(keys)}")
    if chain[0]["revision"]["revision_kind"] != REVISION_CREATE:
        raise ObservationRefused("a revision chain must begin with a create")
    creates = [o for o in chain if o["revision"]["revision_kind"] == REVISION_CREATE]
    if len(creates) != 1:
        raise ObservationRefused(
            f"{len(creates)} creates in one chain; a second create is a different item reusing an "
            "identifier, and treating them as one silently merges two histories")
    for position, observation in enumerate(chain):
        if observation["revision"]["revision_index"] != position:
            raise ObservationRefused(
                f"revision index {observation['revision']['revision_index']} at position "
                f"{position}; a gap means a version nobody kept, and the chain would replay to the "
                "wrong text")
        if position:
            expected = chain[position - 1]["observation_sha256"]
            if observation["revision"]["supersedes_observation_sha256"] != expected:
                raise ObservationRefused(
                    f"revision {position} supersedes "
                    f"{observation['revision']['supersedes_observation_sha256']!r} but the previous "
                    f"version hashes to {expected!r}; a chain that does not link is a chain that "
                    "rewrote something")
    sessions = {}
    for observation in chain:
        session = observation["provenance"]["fetch_session_id"]
        monotonic = observation["times"]["receipt_monotonic_ns"]
        if session in sessions and monotonic < sessions[session]:
            raise ObservationRefused(
                f"the monotonic receipt clock ran backwards within fetch session {session!r} "
                f"({monotonic} after {sessions[session]}). A monotonic clock cannot go back, so "
                "either these arrived out of order or they are not from the same session — and "
                "both mean the receipt order cannot be trusted")
        sessions[session] = monotonic
    return chain


def assert_no_identifier_collision(observations):
    """Two observations sharing a provider identifier must be revisions of each other.

    The same identifier carrying different content with no revision relationship is two different
    items, and folding them together would attribute one source's words to another.
    """
    by_key = {}
    for observation in ordered_observations(observations):
        by_key.setdefault(chain_key(observation), []).append(observation)
    for key, group in sorted(by_key.items()):
        payloads = {o["payload"]["payload_sha256"] for o in group}
        indices = {o["revision"]["revision_index"] for o in group}
        if len(payloads) > 1 and len(indices) != len(group):
            raise ObservationRefused(
                f"provider item {key} appears {len(group)} times with {len(payloads)} distinct "
                "payloads but reuses a revision index; the same identifier holding different "
                "content is two items, not one, and merging them attributes one source's words to "
                "another")
    return True


def as_of(chain, instant, require_binding=False):
    """The version of this item a decision at `instant` actually knew, or an Absent saying why.

    Every prior version is preserved; this only chooses which one was current. A revision we had not
    received yet is invisible here — including a DELETION, which is the subtle case: a deletion that
    arrived after the decision must not reach back and remove the text the decision was made on.
    Doing so would be leakage wearing the costume of data hygiene.
    """
    assert_revision_chain(chain)
    assert_decision_instant(instant)
    known = [observation for observation in chain
             if not ineligibility(observation, instant, require_binding=require_binding)]
    if not known:
        return absent(ABSENT_NOT_YET_KNOWN,
                      "no version of this item had been received, with a publication claim at or "
                      "before this instant")
    current = known[-1]
    if current["revision"]["revision_kind"] == REVISION_DELETE:
        return absent(ABSENT_DELETED,
                      f"the item was deleted at revision {current['revision']['revision_index']}, "
                      "and the deletion had been received by this instant")
    return current


def version_history_as_of(chain, instant, require_binding=False):
    """Every version known by `instant`, oldest first. Nothing is ever dropped."""
    assert_revision_chain(chain)
    return [observation for observation in chain
            if not ineligibility(observation, instant, require_binding=require_binding)]


# --------------------------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "availability_rule": AVAILABILITY_RULE,
        "observation_kinds": list(OBSERVATION_KINDS),
        "kind_meaning": KIND_MEANING,
        "clocks": list(CLOCKS),
        "clock_meaning": CLOCK_MEANING,
        "time_statuses": list(TIME_STATUSES),
        "mapping_statuses": list(MAPPING_STATUSES),
        "mapping_meaning": MAPPING_MEANING,
        "license_statuses": list(LICENSE_STATUSES),
        "retention_statuses": list(RETENTION_STATUSES),
        "license_permits": {k: list(v) for k, v in LICENSE_PERMITS.items()},
        "revision_kinds": list(REVISION_KINDS),
        "ineligibility_codes": list(INELIGIBILITY_CODES),
        "absence_reasons": list(ABSENT_REASONS),
        "feature_fields": list(FEATURE_FIELDS),
        "measurement_fields": list(MEASUREMENT_FIELDS),
        "llm_in_decision_path": LLM_IN_DECISION_PATH,
        "network_collection_performed": False,
        "vendors_selected": [],
        "refusing_computations": ["sentiment", "embedding", "engagement_score",
                                  "source_credibility", "market_cap", "call_language_model"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ObservationRefused: {error}", file=sys.stderr)
        sys.exit(2)
