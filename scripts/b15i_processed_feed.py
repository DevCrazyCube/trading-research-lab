"""B15i — event-driven processed-commitment pilot. Raw first, RPC never on the feed thread.

Implements `research/B15I_PROCESSED_FEED_PREREGISTRATION.json`, committed alone before connecting.

**Why this exists.** B15h missed 78 of 81 targets. Entry delays of 1/2/4 slots are 0.4 to 1.6
seconds, and a polling scheduler reads the launch table long after they have passed. Triggering
inside B15a would not fix it either: B15a subscribes at CONFIRMED, so the receipt itself can arrive
after t0+1. The commitment is the constraint, not the plumbing.

**The trigger and the state read are different commitments, deliberately.** The trigger is
`processed`, to learn of a launch before t0+1 passes. The state read is `finalized`, because a
finalized account read cannot fork — so the state a cell is priced from is canonical even though
the trigger that scheduled it was provisional. Finalization was measured lagging 31 slots, well
inside the frozen 150-slot tolerance.

**Raw first, and the feed thread never awaits an RPC call.** Frame to disk, launch identity, then
enqueue. A handler that waits on a network round trip stops reading the socket and loses the frames
arriving meanwhile — trading the evidence for the derivative.

The pilot's question is whether 1, 2 and 4 slots are reachable at all. If they are not, the answer
is the measured blocker, not a weakened rule.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import queue
import sqlite3
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15i"
DB_PATH = WORK_DIR / "processed_feed.sqlite"
RAW_PATH = WORK_DIR / "raw_processed_frames.jsonl"
B15A_DB = ROOT / "research" / "b15a" / "shadow.sqlite"
B15B_DB = ROOT / "research" / "b15b" / "backfill.sqlite"

PREREG_PATH = ROOT / "research" / "B15I_PROCESSED_FEED_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "a273a4d916ffe4eb92630d73294be2d9b8bf9151de5d38be484ea4e06e6f2fb1"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

Q_OVERFLOW = "Q_OVERFLOW"
Q_TARGET_ALREADY_PASSED = "Q_TARGET_ALREADY_PASSED"
Q_MISSED_WHILE_DOWN = "Q_MISSED_WHILE_DOWN"
Q_PRE_ACTIVATION = "Q_PRE_ACTIVATION"
Q_LATE = "Q_LATE"
Q_ACCOUNT_MISMATCH = "Q_ACCOUNT_MISMATCH"
Q_ORPHANED = "Q_ORPHANED"
Q_UNRESOLVED = "Q_UNRESOLVED"
Q_RPC_FAILED = "Q_RPC_FAILED"

FORK_UNCONFIRMED = "processed_unconfirmed"
FORK_CONFIRMED = "confirmed"
FORK_ORPHANED = "orphaned"
FORK_UNRESOLVED = "unresolved"

STATE_PENDING = "pending"
STATE_CAPTURED = "captured"
STATE_REFUSED = "refused"

TRIGGER_COMMITMENT = "processed"
STATE_READ_COMMITMENT = "finalized"
MAX_QUEUE_DEPTH = 4096

LABEL = "SIMULATED_PROCESSED_FEED_PILOT"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15H = _load("b15h_prospective_entry", "b15h_prospective_entry.py")
B15F, B15B, PILOT, B10A = B15H.B15F, B15H.B15B, B15H.PILOT, B15H.B10A
WS = PILOT.WS


class ProcessedFeedRefused(B15H.ProspectiveRefused):
    """The pilot will not record this, and says why rather than fabricating a target."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ProcessedFeedRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ProcessedFeedRefused(
            f"the processed-feed preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ProcessedFeedRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("b15a", "b15b", "b15c", "b15d", "b15e", "b15f", "b15g", "b15h", "b11a"):
        if f"research{os.sep}{marker}" in resolved:
            raise ProcessedFeedRefused(
                f"{resolved} would write into research/{marker}; those are read-only here")
    if not resolved.endswith(os.sep + "b15i"):
        raise ProcessedFeedRefused(f"the work directory must be .../b15i, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    try:
        return B15H.assert_no_float(node, path)
    except B15H.ProspectiveRefused as error:
        raise ProcessedFeedRefused(str(error)) from error


def assert_feed_thread_does_not_call_rpc(path=None):
    """The frame handler may not contain an RPC call. Checked against the source.

    A handler that waits on a network round trip stops reading the socket, and the frames arriving
    meanwhile are lost. This is the one performance property that is also a correctness property,
    so it is asserted rather than intended.
    """
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    source = path.read_text()
    start = source.find("\ndef handle_frame(")   # anchored, or this matches its own token list
    if start < 0:
        raise ProcessedFeedRefused("handle_frame is missing; the feed handler cannot be checked")
    end = source.find("\ndef ", start + 1)
    body = source[start:end if end > 0 else len(source)]
    for token in ("urlopen", "fetch_account", "getAccountInfo", "getMultipleAccounts",
                  "_one_attempt", "requests."):
        if token in body:
            raise ProcessedFeedRefused(
                f"the feed handler contains {token!r}. It must not await an RPC call: a handler "
                "that blocks on the network stops reading the socket and the frames that arrive "
                "meanwhile are lost")
    return True


# --------------------------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------------------------

def target_lead_slots(target_slot, observed_slot):
    """How far ahead the target still was when we learned of the launch.

    The pilot's primary measurement. Zero or negative means the target had already passed and the
    delay is unreachable on this transport.
    """
    return target_slot - observed_slot


def assert_target_future(target_slot, observed_slot):
    if target_lead_slots(target_slot, observed_slot) <= 0:
        raise ProcessedFeedRefused(
            f"{Q_TARGET_ALREADY_PASSED}: target {target_slot} is not ahead of the observed slot "
            f"{observed_slot}")
    return True


def assert_lateness_tolerance_unchanged(document, checkpoint_document):
    """This document restates B15F's tolerance; it does not own it and cannot widen it.

    Restating a frozen number in a second document is how a tolerance gets quietly relaxed: the
    later document is edited, the earlier one still says 150, and both look consistent on their
    own. They are compared instead.
    """
    mine = document["checkpoint_geometry"]["max_lateness_slots"]
    theirs = checkpoint_document["context_slot_geometry"]["max_lateness_slots"]
    if mine != theirs:
        raise ProcessedFeedRefused(
            f"this document says the lateness tolerance is {mine} and B15F says {theirs}. It is "
            "B15F's and is not widened here")
    return True


def assert_after_activation(t0_slot, activation_slot):
    if t0_slot is None or t0_slot <= activation_slot:
        raise ProcessedFeedRefused(
            f"{Q_PRE_ACTIVATION}: t0 {t0_slot} is at or before activation {activation_slot}")
    return True


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (
  signature TEXT PRIMARY KEY, t0_slot INTEGER NOT NULL, mint TEXT, bonding_curve TEXT,
  observed_slot INTEGER NOT NULL, received_wall_unix REAL NOT NULL,
  received_monotonic_ns INTEGER NOT NULL, raw_sha256 TEXT NOT NULL,
  fork_state TEXT NOT NULL, reconciled_at_wall_unix REAL);
CREATE TABLE IF NOT EXISTS target (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, bonding_curve TEXT,
  target_slot INTEGER NOT NULL, lead_slots INTEGER NOT NULL,
  enqueued_wall_unix REAL NOT NULL, enqueued_monotonic_ns INTEGER NOT NULL,
  receipt_to_schedule_ns INTEGER NOT NULL,
  state TEXT NOT NULL, reason TEXT,
  queue_delay_ns INTEGER, context_slot INTEGER, lateness_slots INTEGER, rpc_round_trip_ns INTEGER,
  virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, real_token INTEGER,
  quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER,
  evidence_sha256 TEXT NOT NULL,
  PRIMARY KEY (signature, delay_slots));
CREATE INDEX IF NOT EXISTS target_pending ON target(state, target_slot);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


class RawLog:
    """Append-only. Written BEFORE anything is enqueued."""

    def __init__(self, path=RAW_PATH):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")
        if self.path.exists():
            with self.path.open() as existing:
                self.count = sum(1 for _ in existing)
        else:
            self.count = 0

    def append(self, record):
        self.count += 1
        self.handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self.handle.flush()
        return self.count

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# The feed thread — raw first, never an RPC call
# --------------------------------------------------------------------------------------------

def handle_frame(message, decoder, raw, connection, work_queue, document, counts, lock):
    """One processed notification. Writes evidence, then enqueues. Never touches the network.

    The order is mandatory: raw frame, then launch identity, then enqueue. Dying between decode and
    enqueue leaves an observation on disk; enqueuing first would leave a schedule referring to a
    frame nobody can produce.
    """
    received_wall, received_mono = time.time(), time.monotonic_ns()
    payload = json.loads(message)
    params = (payload.get("params") or {}).get("result") or {}
    context = params.get("context") or {}
    value = params.get("value") or {}
    observed_slot = context.get("slot")
    signature = value.get("signature")
    raw_sha256 = hashlib.sha256(message.encode()).hexdigest()
    # 1. RAW FIRST, always, whatever else follows.
    raw.append({"received_wall_unix": received_wall, "received_monotonic_ns": received_mono,
                "commitment": TRIGGER_COMMITMENT, "observed_slot": observed_slot,
                "signature": signature, "raw_notification_json": payload,
                "raw_sha256": raw_sha256})
    counts["frames"] += 1
    if value.get("err") is not None or observed_slot is None or not signature:
        return
    payloads, _skipped = PILOT.program_data_payloads(value.get("logs"))
    for blob in payloads:
        # decode_create strips the event-CPI tag itself when present, and `Program data:` lines
        # carry the discriminator with no tag at all. Both framings reach this transport.
        status, fields, _error = PILOT.decode_create(
            blob, decoder["b7d"], decoder["discriminator"], decoder["create_type"],
            decoder["types"])
        if status != PILOT.DECODE_DECODED:
            continue
        counts["launches"] += 1
        activation = document["activation"]["activation_slot"]
        t0_slot = observed_slot
        curve = fields.get("bonding_curve")
        with lock:
            # 2. LAUNCH IDENTITY, durably, before any target refers to it.
            connection.execute(
                "INSERT OR IGNORE INTO observation(signature,t0_slot,mint,bonding_curve,"
                "observed_slot,received_wall_unix,received_monotonic_ns,raw_sha256,fork_state) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (signature, t0_slot, fields.get("mint"), curve, observed_slot, received_wall,
                 received_mono, raw_sha256, FORK_UNCONFIRMED))
            connection.commit()
        try:
            assert_after_activation(t0_slot, activation)
        except ProcessedFeedRefused:
            counts["pre_activation"] += 1
            continue
        # 3. ENQUEUE, last.
        for delay in document["checkpoint_geometry"]["delays"]:
            target = t0_slot + delay
            lead = target_lead_slots(target, observed_slot)
            enqueued_wall, enqueued_mono = time.time(), time.monotonic_ns()
            record = {"signature": signature, "delay_slots": delay, "bonding_curve": curve,
                      "target_slot": target, "lead_slots": lead,
                      "enqueued_wall_unix": enqueued_wall,
                      "enqueued_monotonic_ns": enqueued_mono,
                      "receipt_to_schedule_ns": enqueued_mono - received_mono}
            if lead <= 0:
                _durable(connection, lock, record, STATE_REFUSED, Q_TARGET_ALREADY_PASSED)
                counts["already_passed"] += 1
                continue
            _durable(connection, lock, record, STATE_PENDING, None)
            try:
                work_queue.put_nowait(record)
            except queue.Full:
                # Never a silent drop. The durable row is rewritten as refused so the census sees
                # it, because a dropped target absent from the count reads as one that never came.
                _durable(connection, lock, record, STATE_REFUSED, Q_OVERFLOW)
                counts["overflow"] += 1


def _durable(connection, lock, record, state, reason):
    with lock:
        connection.execute(
            "INSERT OR REPLACE INTO target(signature,delay_slots,bonding_curve,target_slot,"
            "lead_slots,enqueued_wall_unix,enqueued_monotonic_ns,receipt_to_schedule_ns,state,"
            "reason,evidence_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record["signature"], record["delay_slots"], record["bonding_curve"],
             record["target_slot"], record["lead_slots"], record["enqueued_wall_unix"],
             record["enqueued_monotonic_ns"], record["receipt_to_schedule_ns"], state, reason,
             evidence_hash(record)))
        connection.commit()


# --------------------------------------------------------------------------------------------
# The worker thread — minContextSlot, finalized read
# --------------------------------------------------------------------------------------------

def capture(record, url, connection, lock, decoder, document, counts, opener=None,
            exchanges=None):
    """One checkpoint. `minContextSlot` makes the NODE wait for the target rather than us poll.

    `document` is B15F's frozen checkpoint preregistration, verified once at startup, because the
    lateness geometry is B15F's and is not re-derived here.
    """
    started = time.monotonic_ns()
    target = record["target_slot"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [record["bonding_curve"],
                       {"encoding": "base64", "commitment": STATE_READ_COMMITMENT,
                        "minContextSlot": target}]}
    outcome, status, payload = B15B._one_attempt(url, body, opener)
    round_trip = time.monotonic_ns() - started
    queue_delay = started - record["enqueued_monotonic_ns"]
    if exchanges is not None:
        exchanges.append({"method": "getAccountInfo", "outcome": outcome, "http_status": status,
                          "target_slot": target, "signature": record["signature"],
                          "delay_slots": record["delay_slots"],
                          "round_trip_ns": round_trip, "response": payload})
    try:
        if outcome != "retrieved":
            raise ProcessedFeedRefused(f"{Q_RPC_FAILED}: {outcome} {str(payload)[:120]}")
        state, context_slot, lateness = B15F.read_account(payload, target, document, decoder)
    except (B15F.CheckpointRefused, ProcessedFeedRefused) as error:
        code = str(error).split(":", 1)[0]
        code = Q_LATE if code == B15F.C_LATE else (
            Q_ACCOUNT_MISMATCH if code in (B15F.C_WRONG_OWNER, B15F.C_SCHEMA) else code)
        with lock:
            connection.execute(
                "UPDATE target SET state=?, reason=?, queue_delay_ns=?, rpc_round_trip_ns=? "
                "WHERE signature=? AND delay_slots=?",
                (STATE_REFUSED, f"{code}:{str(error)[:160]}", queue_delay, round_trip,
                 record["signature"], record["delay_slots"]))
            connection.commit()
        counts["refused"] += 1
        return
    with lock:
        connection.execute(
            "UPDATE target SET state=?, queue_delay_ns=?, context_slot=?, lateness_slots=?, "
            "rpc_round_trip_ns=?, virtual_quote=?, virtual_token=?, real_quote=?, real_token=?, "
            "quote_mint=?, mayhem_mode=?, complete=? WHERE signature=? AND delay_slots=?",
            (STATE_CAPTURED, queue_delay, context_slot, lateness, round_trip,
             state["virtual_quote"], state["virtual_token"], state["real_quote"],
             state["real_token"], state["quote_mint"], int(state["mayhem_mode"]),
             int(state["complete"]), record["signature"], record["delay_slots"]))
        connection.commit()
    counts["captured"] += 1


def recover_pending(connection, lock, observed_slot):
    """A pending target whose deadline passed while we were down is NEVER fetched.

    Fetching it now would produce an account read from after the target and present it as the state
    at the target. That is the fabrication this whole line of work exists to prevent.
    """
    with lock:
        rows = connection.execute(
            "SELECT signature, delay_slots, target_slot FROM target WHERE state=?",
            (STATE_PENDING,)).fetchall()
        recovered = 0
        for signature, delay, target in rows:
            if target + 150 < observed_slot:
                connection.execute(
                    "UPDATE target SET state=?, reason=? WHERE signature=? AND delay_slots=?",
                    (STATE_REFUSED, Q_MISSED_WHILE_DOWN, signature, delay))
                recovered += 1
        connection.commit()
    return recovered


# --------------------------------------------------------------------------------------------
# Fork reconciliation
# --------------------------------------------------------------------------------------------

def reconcile(connection, lock, b15a_path=B15A_DB, b15b_path=B15B_DB):
    """Promote a processed observation ONLY on an independent confirmed record.

    Never by age, never by absence of contradiction, never by its own repetition. An observation
    with no confirmed counterpart stands as evidence of what processed showed, is marked orphaned,
    and is excluded from pricing.
    """
    confirmed = set()
    for path, query in ((b15a_path, "SELECT signature FROM launch WHERE decode_status='decoded'"),
                        (b15b_path, "SELECT signature FROM backfill WHERE status='retrieved'")):
        if not pathlib.Path(path).exists():
            continue
        source = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            confirmed |= {row[0] for row in source.execute(query)}
        except sqlite3.Error:
            pass
        finally:
            source.close()
    counts = {FORK_CONFIRMED: 0, FORK_ORPHANED: 0, FORK_UNRESOLVED: 0}
    now = time.time()
    with lock:
        rows = connection.execute(
            "SELECT signature, t0_slot, fork_state FROM observation").fetchall()
        newest = connection.execute("SELECT MAX(t0_slot) FROM observation").fetchone()[0] or 0
        for signature, t0_slot, _state in rows:
            if signature in confirmed:
                state = FORK_CONFIRMED
            elif newest - t0_slot > 300:
                # Old enough that a confirmed record would have appeared. Orphaned is a finding,
                # not a default: it says processed showed something confirmed never did.
                state = FORK_ORPHANED
            else:
                state = FORK_UNRESOLVED
            counts[state] += 1
            connection.execute(
                "UPDATE observation SET fork_state=?, reconciled_at_wall_unix=? WHERE signature=?",
                (state, now, signature))
        connection.commit()
    return counts


# --------------------------------------------------------------------------------------------
# Census
# --------------------------------------------------------------------------------------------

def census(connection, lock=None):
    """Coverage and refusals. Never a return, never a rate of anything priced."""
    def _query(sql, args=()):
        return connection.execute(sql, args).fetchall()

    report = {"label": LABEL, "schema_version": SCHEMA_VERSION,
              "trigger_commitment": TRIGGER_COMMITMENT,
              "state_read_commitment": STATE_READ_COMMITMENT,
              "coverage_statement": B15H.COVERAGE_STATEMENT,
              "observations": _query("SELECT COUNT(*) FROM observation")[0][0],
              "fork_states": dict(_query(
                  "SELECT fork_state, COUNT(*) FROM observation GROUP BY fork_state")),
              "targets": dict(_query("SELECT state, COUNT(*) FROM target GROUP BY state")),
              "refusals": dict(_query(
                  "SELECT substr(reason,1,instr(reason||':',':')-1), COUNT(*) FROM target "
                  "WHERE state='refused' GROUP BY 1")),
              "lead_slots_by_delay": {}, "latency_ns_by_delay": {}}
    for delay, count, lo, med, hi in _query(
            "SELECT delay_slots, COUNT(*), MIN(lead_slots), "
            "CAST(AVG(lead_slots) AS INTEGER), MAX(lead_slots) FROM target GROUP BY delay_slots"):
        reachable = _query("SELECT COUNT(*) FROM target WHERE delay_slots=? AND lead_slots>0",
                           (delay,))[0][0]
        report["lead_slots_by_delay"][str(delay)] = {
            "targets": count, "min": lo, "mean_floor": med, "max": hi,
            "still_future_at_scheduling": reachable,
            # The pilot's whole question, per delay. A zero here is the measured blocker.
            "reachable": reachable > 0}
    for delay, count, med_sched, med_queue, med_rtt in _query(
            "SELECT delay_slots, COUNT(*), CAST(AVG(receipt_to_schedule_ns) AS INTEGER), "
            "CAST(AVG(queue_delay_ns) AS INTEGER), CAST(AVG(rpc_round_trip_ns) AS INTEGER) "
            "FROM target GROUP BY delay_slots"):
        report["latency_ns_by_delay"][str(delay)] = {
            "targets": count, "receipt_to_schedule_mean_ns": med_sched,
            "queue_delay_mean_ns": med_queue, "rpc_round_trip_mean_ns": med_rtt}
    lateness = _query("SELECT delay_slots, MIN(lateness_slots), CAST(AVG(lateness_slots) AS "
                      "INTEGER), MAX(lateness_slots) FROM target WHERE state='captured' "
                      "GROUP BY delay_slots")
    report["checkpoint_lateness_by_delay"] = {
        str(row[0]): {"min": row[1], "mean_floor": row[2], "max": row[3]} for row in lateness}
    report["priceable_cells"] = _query(
        "SELECT COUNT(*) FROM target t JOIN observation o ON o.signature=t.signature "
        "WHERE t.state='captured' AND o.fork_state='confirmed'")[0][0]
    report["captured_but_not_priceable"] = _query(
        "SELECT COUNT(*) FROM target t JOIN observation o ON o.signature=t.signature "
        "WHERE t.state='captured' AND o.fork_state<>'confirmed'")[0][0]
    report["performance_status"] = "not_evaluated"
    report["execution_status"] = "never_executed"
    return report


# --------------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------------

def worker_loop(work_queue, url, connection, lock, decoder, document, counts, stop,
                opener=None, exchanges=None):
    while not stop.is_set():
        try:
            record = work_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            capture(record, url, connection, lock, decoder, document, counts, opener, exchanges)
        except Exception as error:                                        # noqa: BLE001
            # A worker that dies takes the drain with it and every later target silently pends.
            # The failure is recorded against the target and the loop continues.
            with lock:
                connection.execute(
                    "UPDATE target SET state=?, reason=? WHERE signature=? AND delay_slots=?",
                    (STATE_REFUSED, f"{Q_RPC_FAILED}:{type(error).__name__}: {error}"[:200],
                     record["signature"], record["delay_slots"]))
                connection.commit()
            counts["worker_errors"] += 1
        finally:
            work_queue.task_done()


def run(url=None, ws_url=None, work_dir=WORK_DIR, seconds=None, workers=4, opener=None,
        websocket=None, max_frames=None):
    """Subscribe at processed, write raw, enqueue, drain. Read-only against the chain throughout."""
    assert_no_execution_surface()
    assert_feed_thread_does_not_call_rpc()
    assert_isolated(work_dir)
    document = verify_preregistration()
    checkpoint_document = B15F.verify_preregistration()
    assert_lateness_tolerance_unchanged(document, checkpoint_document)
    url = url or B15B.rpc_url()
    ws_url = ws_url or WS.websocket_url_from_env()
    work_dir = pathlib.Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    connection = open_database(work_dir / "processed_feed.sqlite")
    raw = RawLog(work_dir / "raw_processed_frames.jsonl")
    exchanges = B15B.ExchangeLog(work_dir / "rpc_exchanges.jsonl")
    b7d, discriminator, create_type, types = PILOT.load_pinned_create_type()
    create_decoder = {"b7d": b7d, "discriminator": discriminator, "create_type": create_type,
                      "types": types}
    curve_decoder = B15B.build_decoder()
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("activation_slot", str(document["activation"]["activation_slot"])),
                       ("trigger_commitment", TRIGGER_COMMITMENT),
                       ("state_read_commitment", STATE_READ_COMMITMENT),
                       ("rpc_endpoint_receipt", json.dumps(B15B.endpoint_receipt(url))),
                       ("label", LABEL)):
        connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)", (key, value))
    connection.commit()

    lock = threading.Lock()
    counts = {"frames": 0, "launches": 0, "already_passed": 0, "overflow": 0, "captured": 0,
              "refused": 0, "pre_activation": 0, "worker_errors": 0, "missed_while_down": 0}
    work_queue = queue.Queue(maxsize=MAX_QUEUE_DEPTH)
    stop = threading.Event()
    threads = [threading.Thread(target=worker_loop,
                                args=(work_queue, url, connection, lock, curve_decoder,
                                      checkpoint_document, counts, stop, opener, exchanges),
                                daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()

    socket = websocket or WS.WebSocket(ws_url)
    deadline = None if seconds is None else time.monotonic() + seconds
    try:
        socket = socket.connect() or socket
        socket.send_json({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                          "params": [{"mentions": [PILOT.PUMP_PROGRAM]},
                                     {"commitment": TRIGGER_COMMITMENT}]})
        while deadline is None or time.monotonic() < deadline:
            if max_frames is not None and counts["frames"] >= max_frames:
                break
            try:
                message = socket.recv()
            except WS.WebSocketRefused:
                break
            if message is None:
                break
            try:
                handle_frame(message, create_decoder, raw, connection, work_queue, document,
                             counts, lock)
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
                counts["worker_errors"] += 1
                raw.append({"handler_error": f"{type(error).__name__}: {error}",
                            "received_wall_unix": time.time()})
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)
        try:
            socket.close()
        except Exception:                                                 # noqa: BLE001
            pass
        raw.close()
    counts.update(reconcile(connection, lock))
    return counts, census(connection)


def main(argv=None):
    parser = argparse.ArgumentParser(description="B15i processed-commitment pilot (read-only)")
    parser.add_argument("--seconds", type=int, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--census-only", action="store_true")
    parser.add_argument("--recover", action="store_true",
                        help="mark pending targets whose deadline passed while down")
    arguments = parser.parse_args(argv)
    if arguments.census_only:
        connection = open_database()
        print(json.dumps(census(connection), indent=2, sort_keys=True))
        return 0
    if arguments.recover:
        connection = open_database()
        lock = threading.Lock()
        slot = B15F.current_slot(B15B.rpc_url())
        print(json.dumps({"missed_while_down": recover_pending(connection, lock, slot)}))
        return 0
    counts, report = run(seconds=arguments.seconds, workers=arguments.workers)
    print(json.dumps({"counts": counts, "census": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
