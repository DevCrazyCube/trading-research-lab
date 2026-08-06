"""B18b — failure rehearsals: drive the B17b vocabulary that nothing else can reach.

WHY THIS EXISTS
---------------
B17b froze an outcome enum containing `dropped`, `expired`, `rejected_by_provider` and
`failed_on_chain`, and two reason codes -- `U_PROVIDER_SILENT` and `U_LOST` -- that only a real
failure produces. Nothing in this repository can produce any of them. A third of the contract's
vocabulary was frozen and unexercised, and a schema whose failure paths have never been written is a
schema whose failure semantics are untested.

This harness writes them, from INJECTED FAULTS, with no network and nothing sent.

WHAT A REHEARSAL RECORD IS, AND IS NOT
--------------------------------------
Records here carry `stage="rehearsal"`, a mandatory `synthetic_fault` block naming the injected
fault, and an explicit `record_is_not_evidence`. `b18a.assert_conforms` refuses a rehearsal record
missing any of those. They use the frozen field names, reason codes and outcome enum -- that is the
whole point -- but they describe a fault this file invented, and they may never be counted, averaged
or aggregated as observations of anything.

THE RETRY POLICY IS THE REAL ONE
--------------------------------
Whether a fault is retried is decided by `rpc_http_identity`, the same module the live watcher uses,
not by a second table written here. So these rehearsals test the actual policy: a 403 is a client
refusal and is terminal, 429 and the 5xx set are retryable, and a transport error is retryable by
TYPE rather than by matching words in its message. That last distinction already killed a live
watcher once, when a transient `URLError` was classified fatal by message-substring matching.

NO NETWORK, NOTHING SENT, NOTHING SIGNED
----------------------------------------
Every fault is a Python object constructed here. The whole sweep runs under B17a's `NoNetwork`, so a
socket opened anywhere raises, and the module's closure is scanned for execution surfaces.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B18A = _load("b18a_shadow_record", "b18a_shadow_record.py")
B17A = B18A.B17A
IDENTITY = B18A.IDENTITY
RecordRefused = B18A.RecordRefused


class RehearsalQuarantined(RecordRefused):
    """The run is invalidated. Nothing further may be recorded against it."""


# ----------------------------------------------------------------------------------------------
# The faults
# ----------------------------------------------------------------------------------------------

def _http(status, message="x"):
    return urllib.error.HTTPError("https://rpc.example.com:8899", status, message, {}, None)


# Each fault says what reached the provider, what came back, and what is therefore KNOWN. The
# reason codes are the interesting part: they are the difference between "we know it did not
# happen" and "we do not know what happened", which a zero would erase.
FAULTS = {
    "provider_403": {
        "error": _http(403, "Forbidden"),
        "reached_provider": True, "response_seen": True,
        "outcome": "rejected_by_provider",
        "note": ("the WAF refused this client. The request arrived and was answered, so the "
                 "provider's silence is not the unknown here -- the refusal is known."),
    },
    "provider_429": {
        "error": _http(429), "reached_provider": True, "response_seen": True,
        "outcome": "rejected_by_provider",
        "note": "rate limited; the provider answered, so nothing about the chain is known yet",
    },
    "provider_500": {
        "error": _http(500), "reached_provider": True, "response_seen": True,
        "outcome": "rejected_by_provider", "note": "provider-side error, retryable",
    },
    "provider_503": {
        "error": _http(503), "reached_provider": True, "response_seen": True,
        "outcome": "rejected_by_provider", "note": "provider unavailable, retryable",
    },
    "dns_failure": {
        "error": urllib.error.URLError("Temporary failure in name resolution"),
        "reached_provider": False, "response_seen": False,
        "outcome": "never_sent",
        "note": ("resolution failed, so nothing left this host. `never_sent` is KNOWN here, which "
                 "is why it is not `unknown`: the absence of a send is itself an observation."),
    },
    "connection_timeout": {
        "error": TimeoutError("timed out"),
        "reached_provider": False, "response_seen": False,
        "outcome": "never_sent", "note": "the connection never completed",
    },
    "provider_silence": {
        "error": TimeoutError("read timed out after the request was written"),
        "reached_provider": True, "response_seen": False,
        "outcome": "unknown",
        "note": ("the request went out and nothing came back. This is the case a zero would "
                 "destroy: it may have landed. `unknown` plus U_PROVIDER_SILENT is the only "
                 "honest record."),
    },
    "lost_response": {
        "error": None, "reached_provider": True, "response_seen": True, "response_captured": False,
        "outcome": "unknown",
        "note": ("the provider answered and we failed to capture it. U_LOST, not "
                 "U_PROVIDER_SILENT: the difference between their fault and ours is worth keeping."),
    },
    "dropped": {
        "error": None, "reached_provider": True, "response_seen": True,
        "outcome": "dropped", "receipt": True,
        "note": "accepted by the provider and never included in a block",
    },
    "expired": {
        "error": None, "reached_provider": True, "response_seen": True,
        "outcome": "expired", "receipt": True, "expiry": True,
        "note": "the blockhash expired before inclusion; the attempt can no longer land",
    },
    "failed_on_chain": {
        "error": None, "reached_provider": True, "response_seen": True,
        "outcome": "failed_on_chain", "receipt": True, "landed": True,
        "on_chain_error": {"InstructionError": [1, {"Custom": 6002}]},
        "note": ("it LANDED and the program rejected it. Fees were paid, so this is the one "
                 "failure with a real cost, and treating it as `dropped` would hide that."),
    },
}


def is_retryable(fault_name):
    """Decided by the shared transport policy, never by a second table written here."""
    fault = FAULTS[fault_name]
    if fault["error"] is None:
        return False        # a chain-side outcome is not a transport retry
    return IDENTITY.is_retryable_error(fault["error"])


# ----------------------------------------------------------------------------------------------
# Building a rehearsal record
# ----------------------------------------------------------------------------------------------

def synthetic_observation(index=0):
    """A canonical observation with no recorder behind it, labelled as such."""
    return {
        "observation_unix_nanos": 1_786_000_000_000_000 + index * 400_000_000,
        "observation_slot": 435_600_001 + index,
        "recorder_id": "SYNTHETIC-NO-RECORDER",
        "session_id": "SYNTHETIC-FAULT-REHEARSAL",
        "seq_in_session": index,
        "payload_schema_version": None,
        "provider_kind": "synthetic",
    }


def fault_record(fault_name, observation, endpoint, *, clock_source, attempt_index=0,
                 retry_of_signature=None):
    """One rehearsal record for one injected fault, conforming to the frozen vocabulary."""
    if fault_name not in FAULTS:
        raise RecordRefused(f"unknown fault {fault_name!r}; the table is frozen in this module")
    fault = FAULTS[fault_name]

    decision = {"decision_unix_nanos": observation["observation_unix_nanos"] + 1_000_000,
                "retry_policy_id": "RP_SHARED_TRANSPORT_V1"}
    record = B18A.shadow_record(observation, decision, endpoint, clock_source=clock_source,
                                attempt_index=attempt_index)
    record["stage"] = B18A.REHEARSAL_STAGE
    record["synthetic_fault"] = {
        "fault": fault_name,
        "error_type": type(fault["error"]).__name__ if fault["error"] is not None else None,
        "reached_provider": fault["reached_provider"],
        "response_seen": fault["response_seen"],
        "retryable_by_shared_policy": is_retryable(fault_name),
        "note": fault["note"],
    }
    record["record_is_not_evidence"] = (
        "INJECTED FAULT. This record describes nothing that happened. It exists to exercise the "
        "frozen failure vocabulary and may never be counted, averaged or aggregated.")

    measured, unmeasured = record["measured"], record["unmeasured"]

    def known(field, value):
        measured[field] = value
        unmeasured.pop(field, None)

    def unknown(field, reason):
        measured[field] = None
        unmeasured[field] = reason

    # A rehearsal attempt got as far as being built and sent, unless the fault says otherwise.
    base = observation["observation_unix_nanos"]
    known("build_started_unix_nanos", base + 2_000_000)
    known("build_completed_unix_nanos", base + 3_000_000)
    known("sign_started_unix_nanos", base + 4_000_000)
    known("sign_completed_unix_nanos", base + 5_000_000)
    known("outcome", fault["outcome"])
    known("route", "direct_rpc")

    if fault["reached_provider"]:
        known("send_unix_nanos", base + 6_000_000)
    else:
        # Nothing left this host, so the send clock CANNOT exist. Not merely unmeasured.
        for field in ("send_unix_nanos", "receipt_unix_nanos"):
            unknown(field, "U_NOT_APPLICABLE")

    if fault.get("response_captured") is False:
        unknown("receipt_unix_nanos", "U_LOST")
    elif fault["reached_provider"] and fault["response_seen"]:
        known("receipt_unix_nanos", base + 7_000_000)
    elif fault["reached_provider"]:
        unknown("receipt_unix_nanos", "U_PROVIDER_SILENT")

    if fault.get("landed"):
        known("land_unix_nanos", base + 9_000_000)
        known("land_slot", observation["observation_slot"] + 2)
        known("finalize_unix_nanos", base + 20_000_000)
        known("finalize_slot", observation["observation_slot"] + 34)
        # It landed, so fees were actually paid and the total is knowable.
        known("base_fee_lamports", 5_000)
        known("priority_fee_lamports_paid", 100_000)
        known("jito_tip_lamports", 0)
        known("ata_rent_lamports", 2_039_280)
        known("total_execution_cost_lamports", 5_000 + 100_000 + 0 + 2_039_280)
        known("compute_units_consumed", 41_233)
        known("on_chain_error", json.dumps(fault["on_chain_error"], sort_keys=True))
    elif fault["outcome"] == "unknown":
        # It MAY have landed. Refusing to say is the entire point of this branch.
        for field in ("land_unix_nanos", "land_slot", "finalize_unix_nanos", "finalize_slot"):
            unknown(field, "U_PROVIDER_SILENT" if fault["response_seen"] is False else "U_LOST")
    else:
        for field in ("land_unix_nanos", "land_slot", "finalize_unix_nanos", "finalize_slot"):
            unknown(field, "U_NOT_APPLICABLE")

    if fault.get("expiry"):
        known("expiry_slot", observation["observation_slot"] + 150)
        known("blockhash", "SyntheticBlockhash1111111111111111111111111")
        known("blockhash_slot", observation["observation_slot"])

    if retry_of_signature is not None:
        known("retry_of_signature", retry_of_signature)

    B18A.assert_conforms(record)
    record["record_sha256"] = B18A.record_hash(record)
    return record


def attempt_chain(fault_name, observation, endpoint, *, clock_source, max_attempts=3):
    """Every attempt is its OWN record. A retry never increments the previous one.

    The chain stops when the shared policy says the fault is terminal, which is why a 403 produces
    exactly one record and a 503 produces several.
    """
    records = [fault_record(fault_name, observation, endpoint, clock_source=clock_source)]
    if not is_retryable(fault_name):
        return records
    while len(records) < max_attempts:
        previous = records[-1]
        records.append(fault_record(
            fault_name, observation, endpoint, clock_source=clock_source,
            attempt_index=previous["measured"]["attempt_index"] + 1,
            retry_of_signature=f"SYNTHETIC-ATTEMPT-{previous['measured']['attempt_index']}"))
    return records


# ----------------------------------------------------------------------------------------------
# Operational failures that are not transport faults
# ----------------------------------------------------------------------------------------------

def assert_clock_coherent(records):
    """A clock that steps backwards produces negative latencies, and must be caught not stored.

    Two separate checks, because they fail differently: within a record the decision cannot precede
    the observation it rests on, and across records a wall clock that moves backwards while slots
    move forwards is a stepped clock, not a reordering.
    """
    problems = []
    previous = None
    for record in records:
        measured = record["measured"]
        observation = measured.get("observation_unix_nanos")
        decision = measured.get("decision_unix_nanos")
        if observation is not None and decision is not None and decision < observation:
            problems.append(
                f"decision {decision} precedes the observation {observation} it rests on")
        for later, earlier in (("receipt_unix_nanos", "send_unix_nanos"),
                               ("land_unix_nanos", "send_unix_nanos"),
                               ("finalize_unix_nanos", "land_unix_nanos")):
            if measured.get(later) is not None and measured.get(earlier) is not None \
                    and measured[later] < measured[earlier]:
                problems.append(f"{later} precedes {earlier} in one attempt")
        if previous is not None:
            slot_forward = (measured.get("observation_slot") or 0) > \
                           (previous["measured"].get("observation_slot") or 0)
            clock_back = (observation or 0) < (previous["measured"].get("observation_unix_nanos") or 0)
            if slot_forward and clock_back:
                problems.append(
                    "the wall clock stepped backwards while slots moved forwards; the clock is "
                    "stepped, not the evidence reordered")
        previous = record
    if problems:
        raise RecordRefused(f"clock incoherence: {problems}")
    return True


def write_records_durably(path, records):
    """Write-then-rename, so a reader never sees a half-written file.

    A record file is evidence. A truncated one that parses is worse than one that does not, because
    the missing attempts look like attempts that never happened.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema_version": SCHEMA_VERSION,
                          "count": len(records),
                          "records_sha256": hashlib.sha256(
                              json.dumps([r["record_sha256"] for r in records],
                                         sort_keys=True).encode()).hexdigest(),
                          "records": records}, sort_keys=True, indent=1)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(payload + "\n")
    temporary.replace(path)
    return path


def read_records(path):
    """Refuse a file whose contents do not match what it says they are."""
    text = pathlib.Path(path).read_text()
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise RecordRefused(
            f"{path} is not readable JSON ({error}). A partially written record file is absence, "
            f"not a shorter run.")
    records = document.get("records", [])
    if len(records) != document.get("count"):
        raise RecordRefused(
            f"{path} says it holds {document.get('count')} records and holds {len(records)}")
    digest = hashlib.sha256(
        json.dumps([r.get("record_sha256") for r in records], sort_keys=True).encode()).hexdigest()
    if digest != document.get("records_sha256"):
        raise RecordRefused(f"{path} contents do not match their own digest")
    return records


def assert_no_duplicate_attempts(records):
    """A duplicate attempt is a double count, and a double count of a failure understates nothing
    -- it invents an extra event. Keyed on the attempt, not on the record hash, because two
    genuinely distinct attempts can hash differently while describing the same attempt index."""
    seen = {}
    for record in records:
        measured = record["measured"]
        key = (record.get("stage"), measured.get("observation_slot"),
               measured.get("attempt_index"))
        if key in seen:
            raise RecordRefused(
                f"attempt {key} appears twice. Every attempt is its own record, and the same "
                f"attempt is not two attempts.")
        seen[key] = record["record_sha256"]
    return True


def resume_after_kill(written, all_intended):
    """What a resumed run may say about the attempts it never wrote.

    It may say they are missing. It may not renumber the survivors to look contiguous, and it may
    not write them now from memory -- a fabricated attempt is indistinguishable from a real one and
    that is precisely why it must not exist.
    """
    written_indexes = {r["measured"]["attempt_index"] for r in written}
    missing = sorted(set(range(all_intended)) - written_indexes)
    return {
        "attempts_intended": all_intended,
        "attempts_durably_written": sorted(written_indexes),
        "attempts_lost_to_the_kill": missing,
        "reason_code": "U_LOST" if missing else None,
        "not_reconstructed": ("the lost attempts are reported as lost. Rewriting them from memory "
                              "after a kill would produce records indistinguishable from real ones."),
        "renumbering_refused": "the surviving attempt indexes keep their original values",
    }


def quarantine(reason, records_so_far):
    """An invalidated run yields a marker, not a partial result presented as a whole one."""
    return {
        "quarantined": True,
        "reason": reason,
        "records_before_quarantine": len(records_so_far),
        "not_for_use": ("this run is INVALIDATED. Records written before the quarantine may not be "
                        "reused, resumed from, or smoothed into a later run."),
    }


# ----------------------------------------------------------------------------------------------
# The documented recorder observation
# ----------------------------------------------------------------------------------------------

def recorder_zero_frame_finding():
    """The CRC32C-zero observation, demonstrated rather than asserted. recorder.py is NOT changed."""
    RECORDER = _load("recorder_for_finding", "recorder.py")
    zeros = b"\x00" * 64
    empty_body_crc = RECORDER.crc32c(b"")
    scratch = pathlib.Path(ROOT / "scripts").parent / ".b18b_zero_probe.seg"
    try:
        scratch.write_bytes(zeros)
        counted, valid_bytes, last_seq = RECORDER.scan_segment(str(scratch))
        try:
            B18A.read_frames(str(scratch))
            b18a_refused = False
        except RecordRefused:
            b18a_refused = True
    finally:
        scratch.unlink(missing_ok=True)
    return {
        "finding": "CRC32C of an empty body is 0, so a zero-filled region satisfies the recorder's "
                   "own scanner as a run of valid empty records",
        "crc32c_of_empty_body": empty_body_crc,
        "zero_bytes_probed": len(zeros),
        "records_the_recorder_counts_as_valid": counted,
        "valid_bytes_the_recorder_reports": valid_bytes,
        "last_seq_reported": last_seq,
        "b18a_refuses_them": b18a_refused,
        "why_it_matters": ("a preallocated, sparse or zero-filled region would read as observations "
                           "rather than as absence, and absence read as observation is the same "
                           "class of error as a zero standing in for an unknown"),
        "recorder_not_changed": ("scripts/recorder.py is untouched. B18a refuses a zero-length "
                                 "frame header instead. Changing the recorder's framing while a "
                                 "collection run reads it needs its own authorization and its own "
                                 "evidence."),
        "what_a_fix_would_need": ("a framing change is not obviously safe: existing sealed segments "
                                  "and their .sha256 sidecars were written under the current rule, "
                                  "so a reader that starts rejecting zero-length headers must be "
                                  "shown not to reject any real historical frame first"),
    }


# ----------------------------------------------------------------------------------------------
# The sweep
# ----------------------------------------------------------------------------------------------

def rehearse_all(endpoint="https://api.mainnet-beta.solana.com",
                 clock_source="CLOCK_REALTIME via time.time_ns(); NOT monotonic"):
    """Every fault, under a runtime network refusal."""
    surface = B17A.assert_no_execution_surface(pathlib.Path(__file__).name)
    with B17A.NoNetwork():
        chains = {}
        for index, fault_name in enumerate(sorted(FAULTS)):
            observation = synthetic_observation(index)
            records = attempt_chain(fault_name, observation, endpoint, clock_source=clock_source)
            assert_clock_coherent(records)
            assert_no_duplicate_attempts(records)
            chains[fault_name] = records
    outcomes = {name: records[0]["measured"]["outcome"] for name, records in chains.items()}
    reasons = sorted({reason for records in chains.values() for record in records
                      for reason in record["unmeasured"].values()})
    return {
        "schema_version": SCHEMA_VERSION,
        "harness": "B18B_FAILURE_REHEARSAL",
        "stage": B18A.REHEARSAL_STAGE,
        "record_is_not_evidence": ("every record here describes an INJECTED FAULT and nothing that "
                                   "happened. None may be counted, averaged or aggregated."),
        "executable": False,
        "performance_status": "not_evaluated",
        "execution_status": "never_executed",
        "no_execution_surface": surface,
        "network": "refused at runtime: socket.socket raised for the whole sweep",
        "contract_sha256": B18A.CONTRACT_SHA256,
        "faults": sorted(FAULTS),
        "outcomes_exercised": outcomes,
        "outcome_enum_coverage": {
            "frozen": list(B18A.OUTCOMES),
            "reached": sorted({o for o in outcomes.values()}),
            "unreachable_without_a_real_send": sorted(set(B18A.OUTCOMES) - set(outcomes.values())),
        },
        "reason_codes_exercised": reasons,
        "retry_policy_source": "scripts/rpc_http_identity.py, the module the live watcher uses",
        "attempt_counts": {name: len(records) for name, records in chains.items()},
        "terminal_faults": sorted(name for name in FAULTS if not is_retryable(name)),
        "recorder_zero_frame_finding": recorder_zero_frame_finding(),
        "chains": chains,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B18b failure rehearsals (offline; injected faults, nothing sent)")
    parser.add_argument("--output", default=None)
    arguments = parser.parse_args(argv)
    report = rehearse_all()
    text = json.dumps(report, indent=1, sort_keys=True)
    if arguments.output:
        pathlib.Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(arguments.output).write_text(text + "\n")
    summary = {key: report[key] for key in
               ("outcome_enum_coverage", "reason_codes_exercised", "attempt_counts",
                "terminal_faults")}
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
