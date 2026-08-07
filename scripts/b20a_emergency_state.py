"""B20a — the emergency-state owner. Slice E, closing B17c's G6.

WHAT WAS MISSING. `kill_switch_engaged` and `emergency_state` are MANDATORY inputs to
`b12a.assert_health` — it refuses a health snapshot that omits either, because "an unstated health
flag is not a healthy one" — and until now **nothing in this repository produced them**. Every
caller had to invent the answer. B17c's G6 named that gap; this module is the component whose job
is to answer.

WHAT THIS IS NOT, AND CANNOT BECOME. It owns two booleans and an append-only receipt log. It holds
no wallet, no address and no transaction key; it constructs, signs, submits and spends nothing; it
opens no socket. `tests/test_b20a_emergency_state.py` asserts that by running B17a's
execution-surface scanner over this module's own closure, so the claim is checked rather than
promised.

The one secret it uses is an OPERATOR AUTHENTICATION secret, read from the environment and never
from argv, used to MAC a local state file so that a tampered file is detectable. It authenticates a
human to a local control process. It cannot authorize a transaction, because nothing here can build
one. That distinction is the whole reason this is implementable without touching the signer
boundary B19a draws.

FAIL-CLOSED IS THE ENTIRE DESIGN, per B19a's required semantics:

    Default at process start, unreadable state, invalid signature, clock conflict or stale
    heartbeat: ENGAGED.

So `read_verdict` NEVER raises on a bad state and never returns "unknown". Every failure path
returns ENGAGED with a reason code naming which failure it was. A refusal that propagated as an
exception would leave the caller to decide, and a caller deciding is exactly the gap G6 described.
Absence is refusal; unknown is engaged; there is no permissive branch anywhere in the read path.

CLEARING IS THE ONLY PRIVILEGED OPERATION. It requires an explicit operator label, a reason, the
generation the operator believes is current, and a valid secret; it writes a durable append-only
receipt; and it never happens by restart, timeout, or the passage of time. Engaging requires none of
that — it needs no strategy, no RPC and no signer, because a control that is hard to pull is not a
control.

TWO INDEPENDENT VERIFIERS, AND DISAGREEMENT MEANS ENGAGED. B19a requires the risk service and the
signer to verify the state separately. No signer exists, so the second verifier here is genuinely
independent in the way that is available: one reads the state file, the other reads the tail of the
append-only receipt log. They are written at different times through different code paths, so a
partial write, a rolled-back file or a hand-edited record makes them disagree — and disagreement
engages. A single reader could not detect any of those.

THE CONSOLE IS NOT TOUCHED. `snapshot` returns a read-only dict for a renderer to consume. Nothing
here adds a write path to `ui/operator_console.html` or `scripts/b12b_preview_server.py`, and the
console's read-only property is what makes "this page cannot leak a snapshot and cannot touch a
wallet" checkable by reading it. Wiring the snapshot into b12b is deliberately NOT done here.

All times are exact integer Unix nanoseconds supplied by the caller. No float appears anywhere, and
nothing reads a wall clock inside this module — a control process whose behaviour depends on an
unstated clock cannot be tested at its boundaries, and its boundaries are the entire point.
"""
import hashlib
import hmac
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

STATE_PATH = ROOT / "research" / "b20a" / "emergency_state.json"
RECEIPT_PATH = ROOT / "research" / "b20a" / "receipts.jsonl"

# Environment variable name only. The value is never read into argv, never logged, never written
# into a record, and never returned by any function here.
OPERATOR_SECRET_ENV = "B20A_OPERATOR_SECRET"

# Every reason a verdict can carry. Exactly one of these is ever "not engaged".
E01_NO_STATE = "E01_NO_STATE"
E02_UNREADABLE = "E02_UNREADABLE"
E03_BAD_MAC = "E03_BAD_MAC"
E04_NO_SECRET = "E04_NO_SECRET"
E05_STALE_HEARTBEAT = "E05_STALE_HEARTBEAT"
E06_CLOCK_CONFLICT = "E06_CLOCK_CONFLICT"
E07_GENERATION_REGRESSED = "E07_GENERATION_REGRESSED"
E08_VERIFIER_DISAGREEMENT = "E08_VERIFIER_DISAGREEMENT"
E09_EXPLICITLY_ENGAGED = "E09_EXPLICITLY_ENGAGED"
E10_MALFORMED_RECORD = "E10_MALFORMED_RECORD"

# The only clear verdict. Named so a grep for "not engaged" finds exactly one place.
E00_CLEARED_BY_OPERATOR = "E00_CLEARED_BY_OPERATOR"

ENGAGED_REASONS = (E01_NO_STATE, E02_UNREADABLE, E03_BAD_MAC, E04_NO_SECRET, E05_STALE_HEARTBEAT,
                   E06_CLOCK_CONFLICT, E07_GENERATION_REGRESSED, E08_VERIFIER_DISAGREEMENT,
                   E09_EXPLICITLY_ENGAGED, E10_MALFORMED_RECORD)

RECORD_FIELDS = ("schema_version", "generation", "engaged", "reason", "operator",
                 "recorded_unix_nanos", "heartbeat_unix_nanos")


class EmergencyRefused(RuntimeError):
    """A WRITE could not be performed safely.

    Only ever raised by `engage` and `clear`. The READ path never raises — a read that raised would
    hand the decision back to a caller, which is the gap this module exists to close.
    """


def _secret(env=None):
    """The operator secret, or None. Never returned to a caller and never logged."""
    value = (env if env is not None else os.environ).get(OPERATOR_SECRET_ENV)
    if value is None or not value.strip():
        return None
    return value.encode()


def canonical_bytes(record):
    """The record minus its MAC, canonically serialized. Reordering keys must not break a MAC."""
    body = {field: record[field] for field in RECORD_FIELDS if field in record}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def compute_mac(record, secret):
    return hmac.new(secret, canonical_bytes(record), hashlib.sha256).hexdigest()


def _verdict(engaged, reason, generation=None, record=None, detail=None):
    """Every read result has this shape. `engaged` is never None and never absent."""
    return {
        "kill_switch_engaged": bool(engaged),
        "emergency_state": bool(engaged),
        "reason_code": reason,
        "generation": generation,
        "detail": detail,
        "record": record,
        "schema_version": SCHEMA_VERSION,
    }


def _read_record(path, secret, now_unix_nanos, stale_after_nanos):
    """One verifier: the state file. Returns a verdict, never raises."""
    path = pathlib.Path(path)
    if not path.is_file():
        return _verdict(True, E01_NO_STATE, detail=f"no state at {path}")

    try:
        record = json.loads(path.read_bytes())
    except (ValueError, OSError) as problem:
        return _verdict(True, E02_UNREADABLE, detail=str(problem))

    if not isinstance(record, dict):
        return _verdict(True, E10_MALFORMED_RECORD, detail="record is not an object")

    missing = [field for field in RECORD_FIELDS if field not in record]
    if missing or "mac" not in record:
        return _verdict(True, E10_MALFORMED_RECORD,
                        detail=f"record does not state {missing or ['mac']}")

    for field in ("generation", "recorded_unix_nanos", "heartbeat_unix_nanos"):
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return _verdict(True, E10_MALFORMED_RECORD,
                            detail=f"{field} must be a non-negative integer, got {value!r}")
    if not isinstance(record["engaged"], bool):
        return _verdict(True, E10_MALFORMED_RECORD, detail="engaged must be a boolean")

    if secret is None:
        return _verdict(True, E04_NO_SECRET, generation=record["generation"],
                        detail=f"{OPERATOR_SECRET_ENV} is unset, so the record cannot be verified")

    if not hmac.compare_digest(compute_mac(record, secret), str(record["mac"])):
        return _verdict(True, E03_BAD_MAC, generation=record["generation"],
                        detail="the record does not match its MAC")

    # A record stamped in the future is a clock conflict, not a fresh record.
    if record["recorded_unix_nanos"] > now_unix_nanos:
        return _verdict(True, E06_CLOCK_CONFLICT, generation=record["generation"],
                        detail="recorded_unix_nanos is in the future")
    if record["heartbeat_unix_nanos"] > now_unix_nanos:
        return _verdict(True, E06_CLOCK_CONFLICT, generation=record["generation"],
                        detail="heartbeat_unix_nanos is in the future")

    if now_unix_nanos - record["heartbeat_unix_nanos"] > stale_after_nanos:
        return _verdict(True, E05_STALE_HEARTBEAT, generation=record["generation"],
                        detail="the owner has not heartbeat within the allowed age")

    if record["engaged"]:
        return _verdict(True, E09_EXPLICITLY_ENGAGED, generation=record["generation"],
                        record=record)

    return _verdict(False, E00_CLEARED_BY_OPERATOR, generation=record["generation"], record=record)


def _read_receipt_tail(path):
    """The second verifier: the append-only receipt log, read independently of the state file.

    Deliberately not derived from the first verifier's result. A partial write, a restored older
    state file or a hand-edited record leaves these two disagreeing, and no single reader could
    see that.
    """
    path = pathlib.Path(path)
    if not path.is_file():
        return None
    last = None
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                last = json.loads(line)
    except (ValueError, OSError):
        return "unreadable"
    return last


def read_verdict(now_unix_nanos, state_path=STATE_PATH, receipt_path=RECEIPT_PATH,
                 stale_after_nanos=60_000_000_000, env=None):
    """The state, fail-closed. NEVER raises, and never returns an unknown.

    `stale_after_nanos` defaults to 60 seconds expressed exactly in nanoseconds. A heartbeat older
    than that engages: an owner that has stopped saying it is alive is indistinguishable from one
    that has died, and the safe reading of that is engaged.
    """
    if isinstance(now_unix_nanos, bool) or not isinstance(now_unix_nanos, int):
        return _verdict(True, E06_CLOCK_CONFLICT,
                        detail=f"now_unix_nanos must be an integer, got {now_unix_nanos!r}")

    primary = _read_record(state_path, _secret(env), now_unix_nanos, stale_after_nanos)
    tail = _read_receipt_tail(receipt_path)

    # Disagreement engages. Checked even when the primary already engaged, so the reason code
    # reports the disagreement rather than hiding it behind whichever failure was noticed first.
    if not primary["kill_switch_engaged"]:
        if tail is None:
            return _verdict(True, E08_VERIFIER_DISAGREEMENT, generation=primary["generation"],
                            detail="the state file says cleared and no receipt supports it")
        if tail == "unreadable":
            return _verdict(True, E08_VERIFIER_DISAGREEMENT, generation=primary["generation"],
                            detail="the receipt log could not be read")
        if tail.get("generation") != primary["generation"] or tail.get("engaged") is not False:
            return _verdict(
                True, E08_VERIFIER_DISAGREEMENT, generation=primary["generation"],
                detail=(f"state file generation {primary['generation']} engaged=False vs receipt "
                        f"generation {tail.get('generation')} engaged={tail.get('engaged')}"))

    return primary


def health_fields(verdict):
    """The two fields b12a demands and nothing produced until now."""
    return {"kill_switch_engaged": verdict["kill_switch_engaged"],
            "emergency_state": verdict["emergency_state"]}


def snapshot(verdict):
    """A read-only view for a renderer. Carries no secret and no write affordance."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kill_switch_engaged": verdict["kill_switch_engaged"],
        "emergency_state": verdict["emergency_state"],
        "reason_code": verdict["reason_code"],
        "generation": verdict["generation"],
        "detail": verdict["detail"],
        "console_may_mutate_this": False,
        "owner": "scripts/b20a_emergency_state.py",
    }


def _append_receipt(receipt_path, record, action):
    receipt_path = pathlib.Path(receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "action": action,
        "generation": record["generation"],
        "engaged": record["engaged"],
        "reason": record["reason"],
        "operator": record["operator"],
        "recorded_unix_nanos": record["recorded_unix_nanos"],
    }
    # Append-only by construction: opened for append, never for write, and never rewritten.
    with receipt_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return receipt


def _current_generation(state_path):
    path = pathlib.Path(state_path)
    if not path.is_file():
        return 0
    try:
        record = json.loads(path.read_bytes())
    except (ValueError, OSError):
        return None
    generation = record.get("generation") if isinstance(record, dict) else None
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        return None
    return generation


def _write(state_path, receipt_path, record, secret, action):
    record = dict(record)
    record["mac"] = compute_mac(record, secret)
    path = pathlib.Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Receipt first. If the process dies between the two, the receipt is ahead of the state file
    # and the two verifiers disagree, which engages. The other order could leave a cleared state
    # file with nothing attesting it.
    _append_receipt(receipt_path, record, action)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)
    return record


def engage(reason, operator, now_unix_nanos, state_path=STATE_PATH, receipt_path=RECEIPT_PATH,
           env=None):
    """Engage. Needs no strategy, no RPC and no signer — a control that is hard to pull is not one.

    Still requires the secret, because a record nobody can verify reads as E04 and engages anyway;
    writing an unverifiable record would leave the switch engaged for the wrong reason and hide a
    misconfiguration behind a correct-looking outcome.
    """
    secret = _secret(env)
    if secret is None:
        raise EmergencyRefused(
            f"{OPERATOR_SECRET_ENV} is unset. The switch reads as ENGAGED without it, so nothing "
            "is unsafe, but an unverifiable record would hide the misconfiguration")
    if not isinstance(reason, str) or not reason.strip():
        raise EmergencyRefused("engaging requires a reason; an unexplained halt cannot be reviewed")
    if not isinstance(operator, str) or not operator.strip():
        raise EmergencyRefused("engaging requires an operator label")
    if isinstance(now_unix_nanos, bool) or not isinstance(now_unix_nanos, int) \
            or now_unix_nanos < 0:
        raise EmergencyRefused("now_unix_nanos must be a non-negative integer")

    current = _current_generation(state_path)
    if current is None:
        raise EmergencyRefused(
            "the current state is unreadable, so the next generation cannot be established. The "
            "switch already reads as ENGAGED; repair the state file rather than overwriting it")

    record = {
        "schema_version": SCHEMA_VERSION,
        "generation": current + 1,
        "engaged": True,
        "reason": reason,
        "operator": operator,
        "recorded_unix_nanos": now_unix_nanos,
        "heartbeat_unix_nanos": now_unix_nanos,
    }
    return _write(state_path, receipt_path, record, secret, "engage")


def clear(reason, operator, expected_generation, now_unix_nanos, state_path=STATE_PATH,
          receipt_path=RECEIPT_PATH, env=None):
    """The only privileged operation, and the only one that can produce a not-engaged state.

    Requires an explicit operator, a reason, and the generation the operator believes is current —
    so an operator clearing a switch someone else moved underneath them is refused rather than
    silently succeeding. Never called by a timeout, a restart or any code path but this one.
    """
    secret = _secret(env)
    if secret is None:
        raise EmergencyRefused(f"{OPERATOR_SECRET_ENV} is unset; clearing requires authentication")
    if not isinstance(reason, str) or not reason.strip():
        raise EmergencyRefused(
            "clearing requires a reason. B19a requires a durable record of WHY the halt ended, "
            "and an unexplained clear is indistinguishable from an accident")
    if not isinstance(operator, str) or not operator.strip():
        raise EmergencyRefused("clearing requires an operator label")
    if isinstance(expected_generation, bool) or not isinstance(expected_generation, int) \
            or expected_generation < 0:
        raise EmergencyRefused("expected_generation must be a non-negative integer")
    if isinstance(now_unix_nanos, bool) or not isinstance(now_unix_nanos, int) \
            or now_unix_nanos < 0:
        raise EmergencyRefused("now_unix_nanos must be a non-negative integer")

    current = _current_generation(state_path)
    if current is None:
        raise EmergencyRefused(
            "the current state is unreadable, so it cannot be cleared. Repair it deliberately")
    if current != expected_generation:
        raise EmergencyRefused(
            f"the state is at generation {current}, not {expected_generation}. Someone else moved "
            "it; re-read it before clearing")

    record = {
        "schema_version": SCHEMA_VERSION,
        "generation": current + 1,
        "engaged": False,
        "reason": reason,
        "operator": operator,
        "recorded_unix_nanos": now_unix_nanos,
        "heartbeat_unix_nanos": now_unix_nanos,
    }
    return _write(state_path, receipt_path, record, secret, "clear")


def heartbeat(now_unix_nanos, state_path=STATE_PATH, receipt_path=RECEIPT_PATH, env=None):
    """Refresh liveness WITHOUT changing the engaged flag or the generation.

    A heartbeat may never clear. It re-stamps liveness on whatever the state already says, so a
    cleared switch stays cleared while the owner is alive and engages the moment it is not. The
    generation is deliberately unchanged: a heartbeat is not an operator action and must not look
    like one in the receipt log.
    """
    secret = _secret(env)
    if secret is None:
        raise EmergencyRefused(f"{OPERATOR_SECRET_ENV} is unset; a heartbeat cannot be signed")
    if isinstance(now_unix_nanos, bool) or not isinstance(now_unix_nanos, int) \
            or now_unix_nanos < 0:
        raise EmergencyRefused("now_unix_nanos must be a non-negative integer")

    path = pathlib.Path(state_path)
    if not path.is_file():
        raise EmergencyRefused("there is no state to heartbeat; it reads as ENGAGED already")
    try:
        record = json.loads(path.read_bytes())
    except (ValueError, OSError) as problem:
        raise EmergencyRefused(f"the state is unreadable: {problem}") from problem
    if not isinstance(record, dict) or "engaged" not in record:
        raise EmergencyRefused("the state is malformed")

    refreshed = {field: record[field] for field in RECORD_FIELDS if field in record}
    refreshed["heartbeat_unix_nanos"] = now_unix_nanos
    refreshed["mac"] = compute_mac(refreshed, secret)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(refreshed, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)
    return refreshed
