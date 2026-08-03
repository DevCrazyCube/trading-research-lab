"""B15a — synthetic frames and the launch-readiness gate. No network, no chain.

Every frame here is manufactured by this file. The gate drives the whole pilot loop against a fake
transport, so the recorder, the decoder, the decision path, the reconnect handling and the stopping
rule are all exercised before anything connects to anything.

`python scripts/b15a_shadow_fixtures.py --gate` exits non-zero on any finding. Launch readiness is
green only when it passes.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PILOT = _load("b15a_shadow_pilot", "b15a_shadow_pilot.py")
WS = PILOT.WS


# --------------------------------------------------------------------------------------------
# Synthetic frames
# --------------------------------------------------------------------------------------------

def create_payload():
    """A real CreateEvent payload, built from the PINNED IDL rather than a hand-written blob.

    Built from the pinned definition so the fixture cannot drift from the decoder it exercises: a
    hand-rolled byte string keeps passing after the IDL changes shape, which is exactly the drift
    the decode path exists to catch.
    """
    b7d, discriminator, create_type, types = PILOT.load_pinned_create_type()
    body = bytearray(discriminator)
    for field in create_type["type"]["fields"]:
        body += _encode(field["type"], types)
    return bytes(PILOT.EVENT_TAG) + bytes(body)


def _encode(type_name, types):
    if isinstance(type_name, dict) and "defined" in type_name:
        name = type_name["defined"]
        name = name.get("name") if isinstance(name, dict) else name
        return b"".join(_encode(f["type"], types) for f in types[name]["type"]["fields"])
    if type_name == "string":
        return (4).to_bytes(4, "little") + b"synt"
    if type_name == "pubkey" or type_name == "publicKey":
        return bytes(range(32))
    if type_name == "bool":
        return b"\x00"
    if type_name == "u8":
        return b"\x01"
    if type_name == "u16":
        return (7).to_bytes(2, "little")
    if type_name == "u32":
        return (7).to_bytes(4, "little")
    if type_name == "u64":
        return (1_000_000).to_bytes(8, "little")
    if type_name == "i64":
        return (1).to_bytes(8, "little", signed=True)
    if type_name == "u128":
        return (1).to_bytes(16, "little")
    raise RuntimeError(f"the fixture does not know how to encode {type_name!r}; refusing to guess")


def notification(logs, slot=1000, signature="SyntheticSig", subscription=42, err=None):
    return json.dumps({
        "jsonrpc": "2.0", "method": "logsNotification",
        "params": {"subscription": subscription,
                   "result": {"context": {"slot": slot},
                              "value": {"signature": signature, "err": err, "logs": logs}}},
    })


def trade_payload():
    """A non-launch Pump event: the right shape, a different discriminator.

    Modelled on what the live feed actually carries — TradeEvent outnumbered CreateEvent 29,110 to
    233 in the first captured window — because a fixture whose only non-create is malformed cannot
    show that a WELL-FORMED foreign event stays out of the launch table.
    """
    return bytes.fromhex("bddb7fd34ee661ee") + b"\x00" * 120


def frames():
    """The stream a session sees: a subscription confirmation, then a deliberate mix."""
    payload = base64.b64encode(create_payload()).decode()
    unknown = base64.b64encode(trade_payload()).decode()
    truncated = base64.b64encode(PILOT.EVENT_TAG + b"\x01" * 4).decode()
    return [
        json.dumps({"jsonrpc": "2.0", "result": 42, "id": 1}),          # subscription confirmed
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}{payload}"], slot=1000, signature="SigA"),
        notification(["Program log: nothing to see"], slot=1001, signature="SigB"),
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}{unknown}"], slot=1002, signature="SigC"),
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}not-base64!!"], slot=1003, signature="SigD"),
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}{payload}"], slot=1004, signature="SigE",
                     err={"InstructionError": [0, "Custom"]}),          # failed tx launched nothing
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}{truncated}"], slot=1005, signature="SigF"),
        notification([f"{PILOT.PROGRAM_DATA_PREFIX}{payload}"], slot=1006, signature="SigG"),
    ]


class FakeSocket:
    """A transport that replays frames and then closes, so reconnect is exercised too."""

    def __init__(self, messages, close_after=None):
        self.messages = list(messages)
        self.sent = []
        self.closed = False
        self.close_reason = "fixture end of stream"
        self.close_after = close_after

    def send_json(self, document):
        self.sent.append(document)

    def send_text(self, text):
        self.sent.append(text)

    def recv(self):
        if self.close_after is not None and len(self.sent) and not self.messages:
            return None
        if not self.messages:
            return None
        return self.messages.pop(0)

    def close(self, code=1000):
        self.closed = True


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------

def _expect(findings, label, exception, thunk):
    try:
        thunk()
    except exception:
        return
    except Exception as error:                                            # noqa: BLE001
        findings.append(f"{label}: raised {type(error).__name__}, not {exception.__name__}")
        return
    findings.append(f"{label}: did NOT refuse")


def check_refusals(directory):
    findings = []
    _expect(findings, "a work dir inside the frozen corpus", PILOT.PilotRefused,
            lambda: PILOT.assert_isolated(ROOT / "research" / "b11a"))
    _expect(findings, "a work dir that is not b15a", PILOT.PilotRefused,
            lambda: PILOT.assert_isolated(directory / "somewhere_else"))
    _expect(findings, "an unpermitted commitment", PILOT.PilotRefused,
            lambda: PILOT.assert_commitment("finalized"))
    _expect(findings, "a drifted preregistration", PILOT.PilotRefused,
            lambda: PILOT.verify_preregistration(expected_sha256="0" * 64))
    _expect(findings, "a missing preregistration", PILOT.PilotRefused,
            lambda: PILOT.verify_preregistration(path=directory / "nope.json"))
    _expect(findings, "an identity in a status line", PILOT.PilotRefused,
            lambda: PILOT.assert_redacted({"mint": "abc"}))
    _expect(findings, "a hypothetical size in a status line", PILOT.PilotRefused,
            lambda: PILOT.assert_redacted({"quote_lamports": 1}))
    _expect(findings, "a non-websocket scheme", WS.WebSocketRefused,
            lambda: WS.WebSocket("https://example.invalid/"))
    _expect(findings, "an endpoint with no host", WS.WebSocketRefused,
            lambda: WS.endpoint_receipt("not-a-url"))
    _expect(findings, "a missing credential", WS.WebSocketRefused,
            lambda: WS.websocket_url_from_env("B15A_DEFINITELY_UNSET"))
    return findings


def check_execution_surface():
    """Neither module may contain the machinery to hold a key, sign, build or submit."""
    findings = []
    for name in ("b15a_shadow_pilot.py", "b15a_websocket.py", "b15a_shadow_fixtures.py"):
        source = (ROOT / "scripts" / name).read_text()
        body = source.split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
        for token in PILOT.EXECUTION_SURFACE_TOKENS:
            if token in body:
                findings.append(f"{name} contains the execution-surface token {token!r}")
    return findings


def run_offline_session(directory, commitment="confirmed"):
    """The whole loop, against fake transport, in a temporary directory named b15a."""
    work = pathlib.Path(directory) / "b15a"
    work.mkdir(parents=True, exist_ok=True)
    stream = frames()
    made = {"count": 0}

    def transport(_url):
        made["count"] += 1
        return FakeSocket(stream if made["count"] == 1 else [])

    # reserve_bytes=0 because a fixture runs in a temp directory whose filesystem is not the one
    # the guard exists to protect. The guard itself is driven by its own tests, not disabled there.
    PILOT.run(commitment=commitment, max_frames=len(stream), transport=transport,
              backfill=lambda _signature: "unavailable", work_dir=work, clock=lambda _s: None,
              max_sessions=2, reserve_bytes=0)
    return work


def gate():
    directory = pathlib.Path(tempfile.mkdtemp(prefix="b15a-gate-"))
    try:
        findings = []
        findings += check_execution_surface()
        findings += check_refusals(directory)

        # Set for the offline session and restored afterwards. `setdefault` without a restore
        # leaves a fake endpoint in the environment of whatever runs next, and when the gate runs
        # inside a test suite that is every later test, including ones that spawn subprocesses.
        previous = os.environ.get("SOLANA_RPC_URL")
        os.environ["SOLANA_RPC_URL"] = "https://fixture.invalid/?api-key=synthetic"
        try:
            work = run_offline_session(directory)
        finally:
            if previous is None:
                os.environ.pop("SOLANA_RPC_URL", None)
            else:
                os.environ["SOLANA_RPC_URL"] = previous

        database = sqlite3.connect(work / "shadow.sqlite")
        launches = database.execute(
            "SELECT decode_status, COUNT(*) FROM launch GROUP BY 1").fetchall()
        decisions = database.execute(
            "SELECT policy_result, reason_code, COUNT(*) FROM decision GROUP BY 1,2").fetchall()
        events = dict(database.execute(
            "SELECT kind, COUNT(*) FROM connection_event GROUP BY 1"))
        non_launch = dict(database.execute(
            "SELECT decode_status, COUNT(*) FROM pump_event GROUP BY 1"))
        sessions = database.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        meta = dict(database.execute("SELECT key, value FROM metadata"))
        database.close()

        raw_lines = (work / "raw_frames.jsonl").read_text().strip().splitlines()
        decode_counts = dict(launches)
        if any(status in PILOT.NON_LAUNCH_STATUSES for status in decode_counts):
            findings.append(
                f"the launch table holds non-launch statuses {sorted(decode_counts)}; a trade "
                "counted as a launch ends a 72-hour pilot in minutes")
        if not non_launch:
            findings.append("no non-launch event was recorded; the separation is not exercised")
        if decode_counts.get(PILOT.DECODE_DECODED, 0) < 2:
            findings.append(f"the fixture decoded {decode_counts.get(PILOT.DECODE_DECODED, 0)} "
                            "CreateEvents; the decode path is not exercised")
        if PILOT.DECODE_UNKNOWN not in non_launch:
            findings.append("no unknown event was recorded; the unknown path is not exercised")
        if not any(result == PILOT.RESULT_NO_ENTRY for result, _reason, _count in decisions):
            findings.append("no refusal was recorded; the no-entry path is not exercised")
        if any(result == PILOT.RESULT_PROPOSED for result, _reason, _count in decisions):
            findings.append("a shadow entry was PROPOSED on feed-only evidence; reserves at the "
                            "decision instant are not knowable and nothing may be proposed on them")
        if "subscribed" not in events:
            findings.append("no subscription confirmation was recorded")
        if sessions < 1:
            findings.append("no session was recorded")
        if len(raw_lines) < 5:
            findings.append(f"{len(raw_lines)} raw frames preserved; the append-only log is not "
                            "capturing the stream")
        if meta.get("geyser_fidelity") != "false":
            findings.append("the artifact does not record that this is not Geyser fidelity")
        if meta.get("execution_status") != "never_executed":
            findings.append("the artifact does not record execution_status=never_executed")

        # Every raw line must be a complete, parseable record carrying both clocks.
        for line in raw_lines:
            record = json.loads(line)
            for field in ("frame_seq", "received_wall_unix", "received_monotonic_ns",
                          "commitment", "raw_notification_json", "raw_sha256"):
                if field not in record:
                    findings.append(f"a raw frame is missing {field}")
                    break

        report = PILOT.status(db_path=work / "shadow.sqlite",
                              raw_path=work / "raw_frames.jsonl")
        PILOT.assert_redacted(report)

        return {
            "schema_version": PILOT.SCHEMA_VERSION,
            "preregistration_canonical_sha256": PILOT.PREREG_CANONICAL_SHA256,
            "sessions": sessions,
            "raw_frames_preserved": len(raw_lines),
            "decode_status_counts": decode_counts,
            "non_launch_event_counts": non_launch,
            "decision_counts": [{"result": r, "reason": c, "count": n} for r, c, n in decisions],
            "connection_events": events,
            "status_sample": report,
            "execution_surface": "absent",
            "geyser_fidelity": False,
            "network_used": False,
            "findings": findings,
            "launch_ready": not findings,
        }
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true", help="exit non-zero on any finding")
    args = parser.parse_args(argv)
    report = gate()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if args.gate and not report["launch_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
