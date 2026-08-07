"""B18a — the shadow record layer: B17b-conforming records over the existing recorder.

WHAT THIS IS
------------
`scripts/recorder.py` already captures raw provider frames and must not change. What did not exist
was anything emitting records in the shape frozen by
`research/B17B_EXECUTION_MEASUREMENT_CONTRACT.json`. This is that, and only that: it READS recorder
segments and canonical observations and WRITES conforming records.

THE CONTRACT IS READ, NOT RESTATED
----------------------------------
Every field name, reason code and enum below comes from the frozen JSON at import time, and the
document's canonical hash is pinned. A second copy of a frozen contract drifts from it, and the day
it drifts is the day the records stop meaning what the contract says they mean. If the document is
edited, this module refuses to load rather than emitting records against a contract nobody froze.

THE TWO RULES THE VALIDATOR EXISTS FOR
--------------------------------------
1. **Unknown is null and never zero**, and every null carries a reason code. A record whose missing
   tip reads as `0` is not incomplete, it is WRONG, and it is wrong in the direction that flatters
   the strategy. `assert_conforms` refuses a null without a reason and a reason without a null.
2. **Landing probability is forbidden.** Not absent-by-omission: actively refused, by name and by
   suffix, so it cannot be added later by someone who thinks a landed/sent ratio is a probability.

SHADOW AND LIVE ARE THE SAME SHAPE
----------------------------------
A shadow record has every key a live record has. The send-side fields are `None` with
`U_NOT_APPLICABLE`, because in shadow they cannot exist -- nothing is built, signed or sent. If the
shapes differed, no shadow measurement could ever be compared against a live one, and the whole
exercise would prove nothing.

NO EXECUTION, PROVEN AT RUNTIME
-------------------------------
`emit` runs under B17a's `NoNetwork`, so a socket opened anywhere in the call raises. The module's
closure is scanned for wallet, key, signing and submission surfaces by B17a's scanner. This layer
reads files and writes JSON; that is all it can do.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

CONTRACT_PATH = ROOT / "research" / "B17B_EXECUTION_MEASUREMENT_CONTRACT.json"
# Pinned. A contract that changed is a contract nobody froze, and records written against it would
# claim a conformance that was never agreed.
#
# THIS IS NOT THE FILE'S sha256, AND A RE-CHECK THAT ASSUMES IT IS WILL READ AS TAMPERING.
# `sha256sum` over the raw bytes returns c96f8b56ceb277884751e4adf3af9108586bfd86ed600ae85e9a01b6052
# a11a2. The pin is over CANONICAL serialization -- `json.dumps(sort_keys=True, separators=(",",":"))`
# -- so it survives reindentation and key reordering, which is the point: the contract's MEANING is
# frozen, not its whitespace. An auditor raised exactly this false alarm on 2026-08-07.
#
# The obvious fix -- documenting this inside the contract's own header -- would ADD A KEY and
# therefore change the canonical hash, breaking the pin it was meant to explain. So it is documented
# here, in the module that holds the pin, and in the gap map. The frozen document stays byte-frozen.
CONTRACT_SHA256 = "29f480fcad6dd93cc40ab3ab16ae3368c02280a27a286e7f6458577451ad2ce4"
CONTRACT_FILE_SHA256_FOR_REFERENCE = (
    "c96f8b56ceb277884751e4adf3af9108586bfd86ed600ae85e9a01b6052a11a2")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B17A = _load("b17a_shadow_rehearsal", "b17a_shadow_rehearsal.py")
IDENTITY = _load("rpc_http_identity", "rpc_http_identity.py")
RECORDER = _load("recorder", "recorder.py")


class RecordRefused(RuntimeError):
    """The record cannot be written honestly, so it is not written."""


# ----------------------------------------------------------------------------------------------
# The frozen contract, loaded and pinned
# ----------------------------------------------------------------------------------------------

def canonical_sha256(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_contract(path=CONTRACT_PATH, expected_sha256=CONTRACT_SHA256):
    """Read the frozen contract and refuse if it moved."""
    if not path.exists():
        raise RecordRefused(f"the frozen contract is missing at {path}; nothing defines these fields")
    document = json.loads(path.read_text())
    actual = canonical_sha256(document)
    if actual != expected_sha256:
        raise RecordRefused(
            f"the execution-measurement contract has changed: {actual} is not {expected_sha256}. "
            f"Records written against an edited contract would claim a conformance nobody froze. "
            f"Re-freeze it deliberately and update the pin in the same commit.")
    return document


CONTRACT = load_contract()

_SECTIONS = ("clocks", "economics", "slippage_and_fill", "failure_expiry_and_retry",
             "provider_and_route")


def _fields(section):
    return tuple(entry["name"] for entry in CONTRACT[section]["fields"])


CLOCK_FIELDS = _fields("clocks")
ECONOMIC_FIELDS = _fields("economics")
SLIPPAGE_FIELDS = _fields("slippage_and_fill")
FAILURE_FIELDS = _fields("failure_expiry_and_retry")
PROVIDER_FIELDS = _fields("provider_and_route")
# The clock source is declared by the contract outside the field list, and is as required as any.
CLOCK_SOURCE_FIELD = CONTRACT["clocks"]["clock_source_must_be_declared"]["field"]

MEASURED_FIELDS = (CLOCK_FIELDS + (CLOCK_SOURCE_FIELD,) + ECONOMIC_FIELDS + SLIPPAGE_FIELDS
                   + FAILURE_FIELDS + PROVIDER_FIELDS)

REASON_CODES = tuple(entry["code"] for entry in CONTRACT["unmeasured_reason_codes"])
OUTCOMES = tuple(next(entry for entry in CONTRACT["failure_expiry_and_retry"]["fields"]
                      if entry["name"] == "outcome")["enum"])
NON_NULLABLE = tuple(entry["name"] for section in _SECTIONS
                     for entry in CONTRACT[section]["fields"] if entry.get("nullable") is False)

# The contract's own three stages, plus one this repository adds for fault injection. A rehearsal
# record uses the frozen vocabulary -- same fields, same reason codes, same outcome enum -- so that
# the failure half of the contract can be exercised at all; nothing else in the repository can
# produce `dropped`, `expired`, `rejected_by_provider` or `failed_on_chain`, and an enum nobody can
# reach is an enum nobody has tested. It is a FOURTH stage rather than a shadow record because a
# shadow record may not claim an outcome it could not have had, and because a fault record must be
# impossible to count as evidence: `assert_conforms` requires it to carry `synthetic_fault` and to
# say in the record itself that it is not evidence.
STAGES = ("shadow", "devnet", "mainnet", "rehearsal")
CONTRACT_STAGES = tuple(CONTRACT["applies_to_stages"])
REHEARSAL_STAGE = "rehearsal"

# In shadow nothing is built, signed or sent, so these cannot exist. Not "were not measured":
# CANNOT exist, which is why the reason is U_NOT_APPLICABLE and not U_NOT_INSTRUMENTED.
SHADOW_IMPOSSIBLE = (
    "build_started_unix_nanos", "build_completed_unix_nanos",
    "sign_started_unix_nanos", "sign_completed_unix_nanos",
    "send_unix_nanos", "receipt_unix_nanos",
    "land_unix_nanos", "land_slot", "finalize_unix_nanos", "finalize_slot",
    "priority_fee_microlamports_per_cu", "compute_unit_limit", "compute_units_consumed",
    "base_fee_lamports", "priority_fee_lamports_paid", "jito_tip_lamports", "jito_bundle_id",
    "jito_bundle_landed", "ata_rent_lamports", "total_execution_cost_lamports",
    "executed_state_slot", "actual_tokens_out", "slippage_tokens", "partial_fill",
    "on_chain_error", "blockhash", "blockhash_slot", "expiry_slot", "retry_of_signature",
    "leader_at_send_slot",
)

# The lamport-denominated parts of the total. `jito_bundle_id` is an identifier and
# `compute_unit_limit` a request, so neither is a cost; requiring them would make the total
# permanently null on a direct route and the rule would stop meaning anything.
COST_COMPONENTS = ("base_fee_lamports", "priority_fee_lamports_paid", "jito_tip_lamports",
                   "ata_rent_lamports")

# Refused by name and by shape. A landed/sent ratio describes a sample; attaching it to a future
# order invents a number the evidence cannot support, and the contract forbids the field outright.
FORBIDDEN_FIELD_MARKERS = ("landing_probability", "land_probability", "probability_of_landing",
                           "fill_probability", "p_land", "expected_landing")
FORBIDDEN_FIELD_SUFFIXES = ("_probability", "_odds", "_likelihood")


# ----------------------------------------------------------------------------------------------
# Reading the existing recorder, without changing it
# ----------------------------------------------------------------------------------------------

def read_frames(segment_path):
    """Frame headers from one recorder segment, CRC-checked by the recorder's own reader.

    The framing is `scripts/recorder.py`'s and stays there. This walks it to lift the observation
    clock and slot out; it never writes a segment and never alters one.
    """
    path = pathlib.Path(segment_path)
    valid, valid_bytes, _last = RECORDER.scan_segment(str(path))
    if valid == 0:
        raise RecordRefused(
            f"{path} yielded no CRC-valid frame. An empty read is not an empty capture; it is an "
            f"unreadable one, and treating the two alike is how a gap becomes a zero.")
    data = path.read_bytes()
    header_struct = RECORDER.SegmentWriter.HDR
    frames, offset = [], 0
    while offset < valid_bytes and len(frames) < valid:
        record_len, header_len, seq, _crc = header_struct.unpack_from(data, offset)
        # A zero-length header is not a frame. CRC32C of an empty body is 0, so a run of zero bytes
        # passes the recorder's scanner as a sequence of valid empty records -- true of the framing
        # and worth knowing, but a preallocated or sparse region is not evidence. Refused here
        # rather than repaired: recorder.py is not this layer's to change.
        if header_len == 0:
            raise RecordRefused(
                f"{path} contains a zero-length frame header at offset {offset}. Zero bytes satisfy "
                f"the CRC and would read as empty records; that is absence, not observation.")
        body_at = offset + header_struct.size
        header = json.loads(data[body_at:body_at + header_len])
        payload = data[body_at + header_len:body_at + header_len + record_len]
        frames.append({"seq_in_session": seq, "header": header, "payload": payload})
        offset = body_at + header_len + record_len
    return frames


def observation_from_frame(frame):
    """The canonical observation coordinates a record is anchored to.

    Fail-closed: a frame whose slot cannot be read produces no observation rather than a null one,
    because a record silently anchored to nothing is worse than a missing record.
    """
    header = frame["header"]
    try:
        payload = json.loads(frame["payload"])
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RecordRefused(f"frame {frame['seq_in_session']} payload is not readable JSON: {error}")
    if "slot" not in payload:
        raise RecordRefused(
            f"frame {frame['seq_in_session']} carries no slot, so nothing anchors a record to the "
            f"chain. Refusing rather than writing an unanchored observation.")
    for field in ("received_at_wall_ns", "session_id", "recorder_id"):
        if header.get(field) is None:
            raise RecordRefused(f"frame {frame['seq_in_session']} is missing {field}")
    return {
        "observation_unix_nanos": header["received_at_wall_ns"],
        "observation_slot": payload["slot"],
        "recorder_id": header["recorder_id"],
        "session_id": header["session_id"],
        "seq_in_session": frame["seq_in_session"],
        "payload_schema_version": header.get("payload_schema_version"),
        "provider_kind": header.get("provider_kind"),
    }


# ----------------------------------------------------------------------------------------------
# Building a record
# ----------------------------------------------------------------------------------------------

def _sanitized_endpoint(endpoint):
    """scheme, host and explicit port only.

    b9d once wrote a provider path credential into a collected artifact by keeping `parsed.path`.
    That is why this goes through the shared identity function rather than a local reimplementation.
    """
    identity = IDENTITY.endpoint_identity(endpoint)
    IDENTITY.assert_endpoint_identity_is_safe(endpoint)
    return identity


def assert_stored_endpoint_is_identity(value):
    """A value ALREADY IN a record is scheme, host and explicit port -- checked as a fixed point.

    `IDENTITY.assert_endpoint_identity_is_safe` cannot do this job: it sanitizes its argument and
    then inspects the sanitized result, so handing it a dirty string returns quietly. That is right
    for its own callers, who pass a source URL, and wrong here. My first version called it on the
    stored value and could therefore never fire -- a check that cannot fire is worse than no check,
    because it reads like protection.

    A stored identity must be UNCHANGED by sanitizing it again. Anything carrying a path, query,
    fragment or userinfo is not, so it is refused.
    """
    if not isinstance(value, str) or not value:
        raise RecordRefused(f"endpoint_identity {value!r} is not a string")
    try:
        rebuilt = IDENTITY.endpoint_identity(value)
    except Exception as error:  # noqa: BLE001 - any refusal from the shared parser is a refusal
        raise RecordRefused(f"endpoint_identity {value!r} is not a usable endpoint: {error}")
    if rebuilt != value:
        raise RecordRefused(
            f"endpoint_identity {value!r} is not sanitized; it reduces to {rebuilt!r}. A persisted "
            f"endpoint is scheme, host and explicit port only -- never a path, query or userinfo.")
    return value


def shadow_record(observation, decision, endpoint, *, attempt_index=0, clock_source,
                  expected_tokens_out=None, slippage_limit_tokens=None, quoted_state_slot=None,
                  route=None, provider_region_declared=None):
    """One B17b-conforming SHADOW record.

    Every field the contract names is present. The ones shadow cannot have are `None` with
    `U_NOT_APPLICABLE`, so the record has the same SHAPE as a live one and the two are comparable.
    """
    if attempt_index < 0:
        raise RecordRefused("attempt_index is an index, not a count, and cannot be negative")
    record = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "stage": "shadow",
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "measured": {field: None for field in MEASURED_FIELDS},
        "unmeasured": {},
        "provenance": {
            "recorder_id": observation["recorder_id"],
            "session_id": observation["session_id"],
            "seq_in_session": observation["seq_in_session"],
            "payload_schema_version": observation["payload_schema_version"],
            "provider_kind": observation["provider_kind"],
            "read_only": "this layer reads recorder output and never writes or alters a segment",
        },
        "counterfactual_limitations": list(
            CONTRACT["counterfactual_limitations"]["must_be_carried_with_every_aggregate"]),
    }
    measured = record["measured"]
    measured["observation_unix_nanos"] = observation["observation_unix_nanos"]
    measured["observation_slot"] = observation["observation_slot"]
    measured["decision_unix_nanos"] = decision["decision_unix_nanos"]
    measured[CLOCK_SOURCE_FIELD] = clock_source
    measured["outcome"] = "never_sent"          # true, and in the frozen enum
    measured["attempt_index"] = attempt_index
    measured["endpoint_identity"] = _sanitized_endpoint(endpoint)
    measured["route"] = route
    measured["provider_region_declared"] = provider_region_declared
    measured["quoted_state_slot"] = quoted_state_slot
    measured["expected_tokens_out"] = expected_tokens_out
    measured["slippage_limit_tokens"] = slippage_limit_tokens
    measured["retry_policy_id"] = decision.get("retry_policy_id")

    for field in SHADOW_IMPOSSIBLE:
        record["unmeasured"][field] = "U_NOT_APPLICABLE"
    # Anything still null that shadow COULD have measured was simply not instrumented, and says so
    # rather than borrowing U_NOT_APPLICABLE, which would overstate what is structurally impossible.
    for field in MEASURED_FIELDS:
        if measured[field] is None and field not in record["unmeasured"]:
            record["unmeasured"][field] = "U_NOT_INSTRUMENTED"
    return record


def _proposal_from(observation, curve_state, quote_lamports):
    """A proposal from RECORDER coordinates, not b17a's.

    `B17A.propose` reads `slot` and `transaction_index` from a rehearsal observation; a recorder
    observation has `observation_slot` and `seq_in_session`. Reusing it meant dressing one shape up
    as the other, and `seq_in_session` is a frame counter, not a transaction index -- a name that
    would have been wrong in the identifier of every record.

    Carries no strategy, on the same standard b17a's own `propose` is held to: the size is an
    argument, there is no branch and no numeric constant.
    """
    return {
        "schema_version": B17A.B12A.SCHEMA_VERSION,
        "proposal_id": f"recorded-{observation['observation_slot']}-{observation['seq_in_session']}",
        "mint": curve_state["mint"],
        "bonding_curve": curve_state["bonding_curve"],
        "creator": curve_state["creator"],
        "side": B17A.B10A.BUY,
        "quote_lamports": quote_lamports,
    }


def decide_and_record(observation, curve_state, components, endpoint, *, clock_source,
                      quote_lamports, schedule=None, policy=None, clock=time.time_ns):
    """Run the REAL B12a decision, time it, and record only what that actually measured.

    Until now `decision_unix_nanos` was an argument callers passed, and `main` passed `None`, so
    every record written carried it at `U_NOT_INSTRUMENTED`. B12a's decision object has no clock of
    its own -- correctly, because only the caller can observe when the decision was made -- so the
    clock is taken around the `decide` call and nowhere else.

    THREE FIELDS BECOME MEASURED, AND FOUR DELIBERATELY DO NOT.

    Measured: `decision_unix_nanos`, observed here; `quoted_state_slot`, the curve state the
    decision was actually priced against; and `expected_tokens_out`, but ONLY when the decision
    approved and the entry was therefore priced.

    Still `U_NOT_INSTRUMENTED`: `retry_policy_id` and `slippage_limit_tokens`, because no retry
    policy and no slippage limit exist to name -- writing an identifier for a policy nobody ratified
    would be inventing one; `route` and `provider_region_declared`, because nothing is sent, so the
    route is a plan rather than an observation. Reducing the unmeasured count by filling fields with
    plausible values is the failure this contract exists to prevent, and it would be invisible
    afterwards.

    THE CURVE STATE IS A SEPARATE ARGUMENT, AND THAT IS A FINDING RATHER THAN AN INCONVENIENCE.
    A recorder frame carries a slot, clocks and provenance; it does NOT carry decoded curve
    reserves, because `observation_from_frame` reads the frame envelope and not the Pump account
    layout inside it. So a B17b record anchored to a recorder frame cannot on its own support a
    B12a decision -- b11b's eligibility vetoes need `virtual_quote`, `virtual_token`, `real_quote`,
    `real_token`, `quote_mint`, `mayhem_mode` and `complete`. My first version passed the recorder
    observation straight to `B17A.curve_state` and raised KeyError on `virtual_quote`.

    Passing the curve state in makes the missing decode step visible at every call site instead of
    hiding it behind a default. The decode itself is not built here: it is a real gap, recorded in
    the inventory, and inventing a plausible reserve set to close it would be exactly the failure
    this contract exists to prevent.

    THE REJECTION SEAM IS PRESERVED. B17a's rehearsal proves a rejected proposal is never priced;
    the same must hold here, so a rejected decision leaves `expected_tokens_out` null. A record that
    quoted a price for an order the risk governor refused would describe a decision nobody made.
    """
    schedule = schedule or {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0,
                            "buyback_fee_bps": 5000}
    policy = policy or {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000,
                        "tip_lamports": 0, "ata_rent_lamports": 2_039_280, "failed_attempts": 0}

    state = dict(curve_state)
    proposal = _proposal_from(observation, curve_state, quote_lamports)
    verdict = B17A.B12A.decide(proposal, state, components["portfolio"], components["health"],
                               components["config"])
    decided_at = clock()

    expected_tokens_out = None
    if verdict["decision"] == B17A.B12A.DECISION_APPROVED:
        priced = B17A.B10A.price_entry(state, {"side": B17A.B10A.BUY,
                                               "quote_lamports": quote_lamports},
                                       schedule, policy)
        expected_tokens_out = priced["tokens_out"]

    record = shadow_record(observation,
                           {"decision_unix_nanos": decided_at, "retry_policy_id": None},
                           endpoint, clock_source=clock_source,
                           quoted_state_slot=state["slot"],
                           expected_tokens_out=expected_tokens_out)
    # The verdict itself has no B17b field -- `outcome` describes a transaction, and a risk refusal
    # is not one -- so it goes in provenance rather than being forced into a measured field or lost.
    record["provenance"]["risk_decision"] = {
        "decision": verdict["decision"],
        "primary_reason": verdict["primary_reason"],
        "decision_sha256": verdict["decision_sha256"],
        "approval_is_simulation_only": verdict["approval_is_simulation_only"],
        "priced_only_when_approved": ("expected_tokens_out is null unless this decision approved; "
                                      "a price for a refused order describes a decision nobody made"),
    }
    record["_observation"] = observation
    assert_conforms(record)
    record["record_sha256"] = record_hash(record)
    return record


def retry_record(previous, *, retry_of_signature, decision, endpoint, clock_source, **kwargs):
    """A retry is its OWN record, never an increment on the first.

    Collapsing attempts into a counter hides the distribution of what it took to land, which is one
    of the few things a shadow stage could later say anything honest about.
    """
    if not retry_of_signature:
        raise RecordRefused("a retry must name what it retried, or the chain cannot be reconstructed")
    record = shadow_record(previous["_observation"], decision, endpoint,
                           attempt_index=previous["measured"]["attempt_index"] + 1,
                           clock_source=clock_source, **kwargs)
    record["measured"]["retry_of_signature"] = retry_of_signature
    record["unmeasured"].pop("retry_of_signature", None)
    return record


# ----------------------------------------------------------------------------------------------
# The validator
# ----------------------------------------------------------------------------------------------

def _walk(value, path="record"):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def assert_conforms(record):
    """Refuse anything the frozen contract does not permit. Fail-closed on every branch."""
    problems = []

    if record.get("contract_sha256") != CONTRACT_SHA256:
        problems.append("the record was written against a different contract revision")
    if record.get("stage") not in STAGES:
        problems.append(f"stage {record.get('stage')!r} is not one of {STAGES}")

    measured = record.get("measured")
    unmeasured = record.get("unmeasured")
    if not isinstance(measured, dict) or not isinstance(unmeasured, dict):
        raise RecordRefused("a record must carry `measured` and `unmeasured` maps")

    missing = [field for field in MEASURED_FIELDS if field not in measured]
    if missing:
        problems.append(f"fields the contract names are absent from the record: {missing}")
    unknown = [field for field in measured if field not in MEASURED_FIELDS]
    if unknown:
        problems.append(f"fields the contract does not name: {unknown}")

    # Rule 1, both directions. A null without a reason hides that something is missing; a reason
    # attached to a value that IS known is a lie in the other direction.
    for field in MEASURED_FIELDS:
        if field not in measured:
            continue
        if measured[field] is None and field not in unmeasured:
            problems.append(f"{field} is null with no reason code; unknown must never be silent")
        if measured[field] is not None and field in unmeasured:
            problems.append(f"{field} has a value AND a reason code for being unmeasured")
    for field, reason in unmeasured.items():
        if field not in MEASURED_FIELDS:
            problems.append(f"a reason code is attached to {field}, which the contract does not name")
        if reason not in REASON_CODES:
            problems.append(f"{field} carries reason {reason!r}, which is not a frozen code")

    for field in NON_NULLABLE:
        if measured.get(field) is None:
            problems.append(f"{field} is declared non-nullable by the contract and is null")
    if measured.get("outcome") is not None and measured["outcome"] not in OUTCOMES:
        problems.append(f"outcome {measured['outcome']!r} is not in the frozen enum")

    # Rule 2. Refused by name and by shape, so it cannot arrive under a new spelling.
    for path, _value in _walk(record):
        leaf = path.rsplit(".", 1)[-1].lower()
        if any(marker in leaf for marker in FORBIDDEN_FIELD_MARKERS) \
                or leaf.endswith(FORBIDDEN_FIELD_SUFFIXES):
            problems.append(
                f"{path} is a landing-probability field. A landed/sent ratio describes a sample and "
                f"is never a probability attached to a future order; the contract forbids it.")

    # A partial total is worse than none, so it may exist only when every cost component is known.
    total = measured.get("total_execution_cost_lamports")
    if total is not None:
        unknown_components = [field for field in COST_COMPONENTS if measured.get(field) is None]
        if unknown_components:
            problems.append(
                f"total_execution_cost_lamports is set while {unknown_components} are unknown")
        else:
            # Summed only once every component is known; summing over a None raises before the
            # guard above can report the real problem.
            known = sum(measured[field] for field in COST_COMPONENTS)
            if total != known:
                problems.append(f"the total {total} does not equal its components {known}")

    if measured.get("attempt_index") is not None and measured["attempt_index"] > 0 \
            and measured.get("retry_of_signature") is None:
        problems.append("attempt_index is past the first but nothing says what was retried")

    endpoint = measured.get("endpoint_identity")
    if endpoint is not None:
        try:
            assert_stored_endpoint_is_identity(endpoint)
        except RecordRefused as error:
            problems.append(str(error))

    for path, value in _walk(record):
        if isinstance(value, float):
            problems.append(f"a float reached {path}; every amount and duration is an exact integer")

    if record.get("stage") == REHEARSAL_STAGE:
        # A fault record must be unmistakable. Without these it would be a well-formed record
        # carrying a real-looking failure outcome, which is exactly the thing that must never end up
        # in an aggregate.
        fault = record.get("synthetic_fault")
        if not isinstance(fault, dict) or not fault.get("fault"):
            problems.append(
                "a rehearsal record must name the synthetic fault that produced it; without that it "
                "is indistinguishable from a record of something that actually happened")
        if not record.get("record_is_not_evidence"):
            problems.append("a rehearsal record must say in itself that it is not evidence")
        if record.get("executable") is not False:
            problems.append("a rehearsal record may not be marked executable")

    if record.get("stage") == "shadow":
        for field in ("send_unix_nanos", "sign_completed_unix_nanos", "land_unix_nanos"):
            if measured.get(field) is not None:
                problems.append(
                    f"{field} has a value in a SHADOW record, which means something was actually "
                    f"built, signed or sent. Nothing here may do that.")
        if measured.get("outcome") not in ("never_sent", "unknown"):
            problems.append(f"a shadow record cannot have outcome {measured.get('outcome')!r}")

    if problems:
        raise RecordRefused(f"the record does not conform to {CONTRACT['contract_id']}: {problems}")
    return True


def record_hash(record):
    """Canonical sha256 over the record, ignoring private keys used for chaining."""
    public = {key: value for key, value in record.items() if not key.startswith("_")}
    return canonical_sha256(public)


def live_shape_reference():
    """The key set a LIVE record would have, so shape equality is checkable rather than asserted."""
    return set(MEASURED_FIELDS)


# ----------------------------------------------------------------------------------------------
# Emitting
# ----------------------------------------------------------------------------------------------

def emit(observation, decision, endpoint, *, clock_source, **kwargs):
    """Build, validate and hash one record with the network refused for the duration."""
    with B17A.NoNetwork():
        record = shadow_record(observation, decision, endpoint, clock_source=clock_source, **kwargs)
        record["_observation"] = observation
        assert_conforms(record)
        record["record_sha256"] = record_hash(record)
    return record


def assert_no_execution_surface():
    """This layer's own closure, scanned by B17a's scanner. Scoped to the closure, and says so."""
    return B17A.assert_no_execution_surface(pathlib.Path(__file__).name)


def records_from_segment(segment_path, decision, endpoint, *, clock_source, limit=None):
    """One conforming record per readable frame, in the segment's own order."""
    records = []
    for frame in read_frames(segment_path):
        if limit is not None and len(records) >= limit:
            break
        records.append(emit(observation_from_frame(frame), decision, endpoint,
                            clock_source=clock_source))
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B18a shadow record layer (offline; reads recorder output, writes B17b records)")
    parser.add_argument("--segment", required=True, help="a recorder .seg file to read")
    parser.add_argument("--endpoint", default="https://api.mainnet-beta.solana.com")
    parser.add_argument("--clock-source", default="CLOCK_REALTIME, not monotonic")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--curve-state", default=None,
                        help=("JSON file of decoded curve reserves. WITHOUT it, records are "
                              "frame-only and carry no decision, because a recorder frame has no "
                              "reserves to decide on. WITH it, a real B12a decision is run and "
                              "timed. The difference between the two outputs IS the finding."))
    parser.add_argument("--quote-lamports", type=int, default=100_000_000)
    arguments = parser.parse_args(argv)

    surface = assert_no_execution_surface()
    if arguments.curve_state:
        curve_state = json.loads(pathlib.Path(arguments.curve_state).read_text())
        components = copy.deepcopy(B17A.B12B.demo_components())
        records = []
        with B17A.NoNetwork():
            for frame in read_frames(arguments.segment):
                if arguments.limit is not None and len(records) >= arguments.limit:
                    break
                records.append(decide_and_record(
                    observation_from_frame(frame), curve_state, components, arguments.endpoint,
                    clock_source=arguments.clock_source,
                    quote_lamports=arguments.quote_lamports))
        decision_backed = True
    else:
        records = records_from_segment(arguments.segment,
                                       {"decision_unix_nanos": None, "retry_policy_id": None},
                                       arguments.endpoint, clock_source=arguments.clock_source,
                                       limit=arguments.limit)
        decision_backed = False

    uninstrumented = sorted({field for record in records
                             for field, reason in record["unmeasured"].items()
                             if reason == "U_NOT_INSTRUMENTED"})
    report = {
        "schema_version": SCHEMA_VERSION,
        "layer": "B18A_SHADOW_RECORD",
        "contract_sha256": CONTRACT_SHA256,
        "decision_backed": decision_backed,
        "uninstrumented_fields": uninstrumented,
        "uninstrumented_count": len(uninstrumented),
        "what_the_count_means": (
            "Frame-only records leave seven fields uninstrumented because a recorder frame carries "
            "no curve reserves to decide on. Supplying a decoded curve state runs a real B12a "
            "decision and measures three of them. The remaining four name a retry policy and a "
            "slippage limit that do not exist, and a route and provider region that are plans "
            "rather than observations while nothing is sent."),
        "no_execution_surface": surface,
        "network": "refused at runtime: socket.socket raised while every record was built",
        "records": [{key: value for key, value in record.items() if not key.startswith("_")}
                    for record in records],
        "count": len(records),
    }
    text = json.dumps(report, indent=1, sort_keys=True)
    if arguments.output:
        pathlib.Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(arguments.output).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
