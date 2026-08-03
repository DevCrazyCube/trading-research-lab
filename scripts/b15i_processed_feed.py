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
SLOT_SECONDS = 0.4      # the nominal Solana slot; used ONLY to space retries, never as evidence
ORPHAN_MARGIN_SLOTS = 300   # how far a confirmed recorder must be PAST a slot to call it orphaned

LABEL = "SIMULATED_PROCESSED_FEED_PILOT"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15H = _load("b15h_prospective_entry", "b15h_prospective_entry.py")
B15J = _load("b15j_raw_retention", "b15j_raw_retention.py")
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
    # Call forms, not bare words: an earlier version matched the substring "requests." and fired
    # on a comment that ended a sentence with it. A gate that trips on prose gets edited away.
    for token in ("urlopen(", "fetch_account(", "getAccountInfo", "getMultipleAccounts",
                  "_one_attempt(", "requests.get(", "requests.post("):
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
  fork_state TEXT NOT NULL, reconciled_at_wall_unix REAL, orphan_source TEXT,
  chain_verdict TEXT,
  session_id TEXT, observed_after_gap INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS session (
  session_id TEXT PRIMARY KEY, started_wall_unix REAL NOT NULL,
  started_monotonic_ns INTEGER NOT NULL, reconnect_index INTEGER NOT NULL,
  commitment TEXT NOT NULL, ended_wall_unix REAL, end_reason TEXT, frames INTEGER);
CREATE TABLE IF NOT EXISTS target (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, bonding_curve TEXT,
  target_slot INTEGER NOT NULL, lead_slots INTEGER NOT NULL,
  enqueued_wall_unix REAL NOT NULL, enqueued_monotonic_ns INTEGER NOT NULL,
  receipt_to_schedule_ns INTEGER NOT NULL,
  state TEXT NOT NULL, reason TEXT,
  queue_delay_ns INTEGER, context_slot INTEGER, lateness_slots INTEGER, rpc_round_trip_ns INTEGER,
  attempts INTEGER, waited_ns INTEGER,
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
    # A database written before `attempts` existed keeps its rows; the column is added rather than
    # the file recreated, because recreating it would discard the evidence that motivated it.
    existing = {row[1] for row in connection.execute("PRAGMA table_info(target)")}
    for column in ("attempts", "waited_ns"):
        if column not in existing:
            connection.execute(f"ALTER TABLE target ADD COLUMN {column} INTEGER")
    observed = {row[1] for row in connection.execute("PRAGMA table_info(observation)")}
    for column, definition in (("session_id", "TEXT"),
                               ("orphan_source", "TEXT"), ("chain_verdict", "TEXT"),
                               ("observed_after_gap", "INTEGER NOT NULL DEFAULT 0")):
        if column not in observed:
            connection.execute(f"ALTER TABLE observation ADD COLUMN {column} {definition}")
    connection.commit()
    return connection


class RawLog:
    """Append-only, self-rotating, and refusing before the disk becomes someone else's problem.

    Rotation happens HERE rather than in an outside process because this object owns the file
    handle. An external rotator that renamed the path while this handle stayed open would leave the
    writer appending to the same inode under its sealed name, so the "sealed" segment would keep
    growing after it was hashed.
    """

    def __init__(self, path=RAW_PATH, retention=None, max_segment_bytes=None, reserve_bytes=None,
                 check_interval_seconds=60.0, stem=None):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")
        self.retention = retention
        self.stem = stem or self.path.name.removesuffix(".jsonl")
        self.max_segment_bytes = max_segment_bytes
        self.reserve_bytes = reserve_bytes
        self.check_interval_seconds = check_interval_seconds
        self.bytes_written = self.path.stat().st_size if self.path.exists() else 0
        self.rotations = 0
        self._last_space_check = 0.0
        if self.path.exists():
            with self.path.open() as existing:
                self.count = sum(1 for _ in existing)
        else:
            self.count = 0

    def append(self, record):
        self.count += 1
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        self.handle.write(line)
        self.handle.flush()
        self.bytes_written += len(line.encode())
        self._maybe_check_space()
        self._maybe_rotate()
        return self.count

    def _maybe_check_space(self):
        if self.retention is None or self.reserve_bytes is None:
            return
        now = time.monotonic()
        if now - self._last_space_check < self.check_interval_seconds:
            return
        self._last_space_check = now
        # Raises RetentionRefused, which stops capture. It does not degrade, sample or filter:
        # a feed that keeps writing a thinner record past the guard changes its own coverage at
        # an unmarked moment, and no later census can say when.
        self.retention.assert_free_space(self.path.parent, self.reserve_bytes)

    def _maybe_rotate(self):
        if self.retention is None or not self.max_segment_bytes:
            return
        if self.bytes_written < self.max_segment_bytes:
            return
        # Close first: the seal must be taken over a file nobody is appending to.
        self.handle.close()
        try:
            self.retention.rotate(self.path, self.path.parent, self.stem,
                                  self.retention.verify_preregistration())
            self.rotations += 1
            self.bytes_written = 0
        finally:
            self.handle = open(self.path, "a", encoding="utf-8")

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# The feed thread — raw first, never an RPC call
# --------------------------------------------------------------------------------------------

def handle_frame(message, decoder, raw, connection, work_queue, document, counts, lock,
                 session_id=None, after_gap=False, ready_delay_ns=0):
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
                "session_id": session_id, "observed_after_gap": bool(after_gap),
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
                "observed_slot,received_wall_unix,received_monotonic_ns,raw_sha256,fork_state,"
                "session_id,observed_after_gap) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (signature, t0_slot, fields.get("mint"), curve, observed_slot, received_wall,
                 received_mono, raw_sha256, FORK_UNCONFIRMED, session_id, int(bool(after_gap))))
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
                      "receipt_to_schedule_ns": enqueued_mono - received_mono,
                      "ready_monotonic_ns": enqueued_mono + ready_delay_ns}
            if lead <= 0:
                _durable(connection, lock, record, STATE_REFUSED, Q_TARGET_ALREADY_PASSED)
                counts["already_passed"] += 1
                continue
            _durable(connection, lock, record, STATE_PENDING, None)
            try:
                # Priority is the moment the target can plausibly be answered. A worker must never
                # spend that wait itself: at 32 slots of finalization lag and ~210 targets a
                # minute, sleeping workers need about fifty threads just to idle, and with
                # twenty-four the queue backed up until lateness reached 150 — the frozen cliff.
                # The releaser thread holds the wait; a worker only issues its call.
                work_queue.put_nowait((record["ready_monotonic_ns"], record["target_slot"],
                                       record["delay_slots"], record))
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

def _context_not_reached(payload):
    """The node's way of saying the target is still ahead of its tip. Retryable, and only this."""
    return "min context slot" in str(payload).lower()


def capture(record, url, connection, lock, decoder, document, counts, opener=None,
            exchanges=None, sleeper=time.sleep, first_attempt_delay_slots=0):
    """One checkpoint: wait for finality, ask once, then retry a bounded number of times.

    **`minContextSlot` does not make the node wait.** The frozen document said it would; the first
    live run proved otherwise. Every one of 147 requests came back `-32603 Min context slot not
    reached` in about 220ms rather than blocking until the slot arrived. The parameter is a
    precondition the node checks and rejects, not a barrier it waits on.

    The remedy needs no new rule, because B15F already froze one: `context_before_target` is
    "retry, bounded", six attempts, twenty-five slots apart. That is the safety net.

    **The client waits instead, before asking at all.** Firing immediately and retrying spent about
    three requests per target where one would do, and that load is shared: B15h died on HTTP 429
    within six minutes of this pilot starting with thirty-two workers. Sleeping for the measured
    finalization lag first cuts the request count roughly threefold and costs nothing, because the
    answer does not exist until then either way.

    The wait changes when we ask, never what is admitted. Lateness is still measured from the
    response's own context slot against B15F's tolerance, so a target that finalizes late is
    refused exactly as before.

    `document` is B15F's frozen checkpoint preregistration, verified once at startup, because the
    lateness geometry is B15F's and is not re-derived here.
    """
    started = time.monotonic_ns()
    target = record["target_slot"]
    policy = document["context_slot_geometry"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [record["bonding_curve"],
                       {"encoding": "base64", "commitment": STATE_READ_COMMITMENT,
                        "minContextSlot": target}]}
    if first_attempt_delay_slots > 0:
        sleeper(first_attempt_delay_slots * SLOT_SECONDS)
    # Two clocks, kept apart. `waited_ns` is time deliberately spent not asking; `network_ns` is
    # only the calls themselves. Reporting their sum as "round trip" made a 220ms endpoint look
    # like a 14.7s one, which is a claim about the provider that the measurement never supported.
    waited_ns = time.monotonic_ns() - started
    network_ns = 0
    attempts = 0
    for attempt in range(policy["max_attempts"]):
        attempts = attempt + 1
        attempt_started = time.monotonic_ns()
        outcome, status, payload = B15B._one_attempt(url, body, opener)
        network_ns += time.monotonic_ns() - attempt_started
        if exchanges is not None:
            exchanges.append({"method": "getAccountInfo", "outcome": outcome,
                              "http_status": status, "target_slot": target,
                              "signature": record["signature"], "attempt": attempts,
                              "delay_slots": record["delay_slots"],
                              "network_ns": network_ns, "waited_ns": waited_ns,
                              "response": payload})
        if outcome == "retrieved" or not _context_not_reached(payload):
            break
        if attempts < policy["max_attempts"]:
            retry_started = time.monotonic_ns()
            sleeper(policy["retry_interval_slots"] * SLOT_SECONDS)
            waited_ns += time.monotonic_ns() - retry_started
    round_trip = network_ns
    queue_delay = started - record["enqueued_monotonic_ns"]
    try:
        if outcome != "retrieved":
            raise ProcessedFeedRefused(
                f"{Q_RPC_FAILED}: {outcome} after {attempts} attempts {str(payload)[:120]}")
        state, context_slot, lateness = B15F.read_account(payload, target, document, decoder)
    except (B15F.CheckpointRefused, ProcessedFeedRefused) as error:
        code = str(error).split(":", 1)[0]
        code = Q_LATE if code == B15F.C_LATE else (
            Q_ACCOUNT_MISMATCH if code in (B15F.C_WRONG_OWNER, B15F.C_SCHEMA) else code)
        with lock:
            connection.execute(
                "UPDATE target SET state=?, reason=?, queue_delay_ns=?, rpc_round_trip_ns=?, "
                "attempts=?, waited_ns=? WHERE signature=? AND delay_slots=?",
                (STATE_REFUSED, f"{code}:{str(error)[:160]}", queue_delay, round_trip, attempts,
                 waited_ns, record["signature"], record["delay_slots"]))
            connection.commit()
        counts["refused"] += 1
        return
    with lock:
        connection.execute(
            "UPDATE target SET state=?, queue_delay_ns=?, context_slot=?, lateness_slots=?, "
            "rpc_round_trip_ns=?, attempts=?, waited_ns=?, virtual_quote=?, virtual_token=?, "
            "real_quote=?, real_token=?, quote_mint=?, mayhem_mode=?, complete=? "
            "WHERE signature=? AND delay_slots=?",
            (STATE_CAPTURED, queue_delay, context_slot, lateness, round_trip, attempts, waited_ns,
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

def counterparty_evidence(b15a_path=B15A_DB, b15b_path=B15B_DB):
    """Confirmed signatures, and how far the confirmed recorders have themselves progressed.

    The tip matters as much as the set. Without it, "not in the counterparty" and "the counterparty
    has not got there yet" are the same observation, and the second one silently becomes the first.

    A tip of None means no counterparty could be read at all, and nothing is ever orphaned on that
    basis: unknown is not clean.
    """
    confirmed, tips = set(), []
    sources = ((b15a_path, "SELECT signature FROM launch WHERE decode_status='decoded'",
                ("SELECT MAX(slot) FROM pump_event", "SELECT MAX(slot) FROM launch")),
               (b15b_path, "SELECT signature FROM backfill WHERE status='retrieved'",
                ("SELECT MAX(slot) FROM backfill",)))
    for path, signature_query, tip_queries in sources:
        if not pathlib.Path(path).exists():
            continue
        source = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            confirmed |= {row[0] for row in source.execute(signature_query)}
        except sqlite3.Error:
            pass
        for tip_query in tip_queries:
            try:
                value = source.execute(tip_query).fetchone()[0]
            except sqlite3.Error:
                continue
            if value is not None:
                tips.append(value)
        source.close()
    # The FURTHEST-BEHIND reachable counterparty sets the bar. Taking the max would let a recorder
    # that is current excuse orphaning launches the other one has not reached.
    return confirmed, (min(tips) if tips else None)


def reconcile(connection, lock, b15a_path=B15A_DB, b15b_path=B15B_DB):
    """Promote a processed observation on an independent confirmed record. NEVER orphan it here.

    Promotion is cheap and safe: a signature present in B15a's decoded launches or B15b's retrieved
    transactions did confirm, and that is that.

    Orphaning is neither, and this function no longer does it. The earlier rule orphaned anything
    a confirmed recorder had passed without recording — which assumed the recorder sees everything
    that confirms. B15k tested that assumption: of 200 launches absent from B15a inside an interval
    B15a had demonstrably passed, 200 of 200 were CONFIRMED ON CHAIN by an independent
    getTransaction query. B15a records about 29% of the launches this feed observes, so absence
    from it was measuring our own instrument and reporting the measurement as a fork rate.

    An observation is orphaned only by `confirmation_worker` below, on an explicit not-found from
    the chain. Everything else stays unresolved, which is what it is.
    """
    confirmed, _tip = counterparty_evidence(b15a_path, b15b_path)
    counts = {FORK_CONFIRMED: 0, FORK_ORPHANED: 0, FORK_UNRESOLVED: 0}
    now = time.time()
    with lock:
        rows = connection.execute(
            "SELECT signature, t0_slot, fork_state, chain_verdict FROM observation").fetchall()
        for signature, _t0_slot, previous, verdict in rows:
            if signature in confirmed:
                state = FORK_CONFIRMED
            elif verdict is not None:
                # A verdict the CHAIN gave, in either direction, and this pass does not re-litigate
                # it. Preserving only the orphan half demoted every chain-confirmed observation
                # back to unresolved sixty seconds after the worker promoted it, so the worker
                # made no net progress at all: 8 promotions in five minutes where 600 were due.
                state = FORK_CONFIRMED if verdict == "confirmed" else FORK_ORPHANED
            else:
                state = FORK_UNRESOLVED
            counts[state] += 1
            connection.execute(
                "UPDATE observation SET fork_state=?, reconciled_at_wall_unix=? WHERE signature=?",
                (state, now, signature))
        connection.commit()
    return counts


def withdraw_peer_orphans(connection, lock):
    """Reset every orphan verdict that was NOT reached by asking the chain.

    B15k proved the rule those verdicts came from invalid: 200 of 200 launches absent from B15a
    inside a window B15a had passed were confirmed on chain. A verdict produced by a rule now known
    to be wrong is not evidence, and leaving it in place would let a withdrawn finding go on
    excluding cells from pricing forever.

    The withdrawal is recorded rather than silent, and the observations return to `unresolved` —
    not to `confirmed`. They are re-decided by the chain, one query at a time.
    """
    with lock:
        affected = connection.execute(
            "SELECT COUNT(*) FROM observation WHERE fork_state=? AND chain_verdict IS NULL",
            (FORK_ORPHANED,)).fetchone()[0]
        connection.execute(
            "UPDATE observation SET fork_state=?, reconciled_at_wall_unix=? "
            "WHERE fork_state=? AND chain_verdict IS NULL",
            (FORK_UNRESOLVED, time.time(), FORK_ORPHANED))
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)",
            ("peer_orphan_verdicts_withdrawn",
             json.dumps({"count": affected, "at_wall_unix": time.time(),
                         "reason": "B15K_COVERAGE_AUDIT_V1: 200 of 200 launches absent from B15a "
                                   "inside a window B15a had passed were CONFIRMED ON CHAIN; the "
                                   "peer-absence orphan rule is withdrawn",
                         "returned_to": FORK_UNRESOLVED})))
        connection.commit()
    return affected


def confirmation_worker(connection, lock, stop, counts, url, opener=None, sleeper=time.sleep,
                        interval=30.0, batch=60, rate_per_second=2.0, min_age_slots=None):
    """Ask the CHAIN whether an unresolved launch confirmed. Bounded and rate limited.

    B15a cannot be the sole confirmation oracle — B15k measured it holding 798 of 2,755 launches
    inside an interval it had passed — so corroboration comes from a getTransaction at confirmed
    commitment, one signature at a time, at a rate chosen because B15h was killed by HTTP 429.

    A not-found here is the ONLY thing that orphans an observation, and even then it is recorded as
    what it is: this node has no confirmed transaction for that signature.
    """
    margin = ORPHAN_MARGIN_SLOTS if min_age_slots is None else min_age_slots
    while not stop.wait(interval):
        try:
            with lock:
                tip = connection.execute(
                    "SELECT MAX(t0_slot) FROM observation").fetchone()[0] or 0
                # BOTH not-yet-decided states. A freshly written row is `processed_unconfirmed`
                # and only becomes `unresolved` after a reconcile pass, so a worker watching only
                # the second one would sit idle behind whatever ran first.
                pending = connection.execute(
                    "SELECT signature FROM observation WHERE fork_state IN (?,?) "
                    "AND t0_slot < ? ORDER BY t0_slot LIMIT ?",
                    (FORK_UNRESOLVED, FORK_UNCONFIRMED, tip - margin, batch)).fetchall()
        except sqlite3.Error:
            counts["worker_errors"] += 1
            continue
        for (signature,) in pending:
            if stop.is_set():
                return
            outcome = confirm_on_chain(signature, url, opener)
            if outcome is None:
                counts["confirmation_failed"] = counts.get("confirmation_failed", 0) + 1
                continue
            state = FORK_CONFIRMED if outcome else FORK_ORPHANED
            try:
                with lock:
                    connection.execute(
                        "UPDATE observation SET fork_state=?, reconciled_at_wall_unix=?, "
                        "orphan_source=?, chain_verdict=? WHERE signature=?",
                        (state, time.time(),
                         "chain_not_found" if state == FORK_ORPHANED else None,
                         "confirmed" if outcome else "not_found", signature))
                    connection.commit()
            except sqlite3.Error:
                counts["worker_errors"] += 1
                continue
            counts[f"chain_{state}"] = counts.get(f"chain_{state}", 0) + 1
            sleeper(1.0 / rate_per_second)


def confirm_on_chain(signature, url, opener=None):
    """True if confirmed, False if the node has no confirmed transaction, None if undecided.

    None is not False. A failed query decides nothing and must never orphan anything.
    """
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"commitment": "confirmed",
                                   "maxSupportedTransactionVersion": 0, "encoding": "json"}]}
    outcome, _status, _payload = B15B._one_attempt(url, body, opener)
    if outcome == "retrieved":
        return True
    if outcome == "not_found":
        return False
    return None


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
    # Waiting and network are reported separately and never summed into one figure. Their sum
    # once made a 220ms endpoint read as a 14.7s one, which is a claim about the provider that the
    # measurement never supported.
    for delay, count, med_sched, med_queue, med_net, med_wait in _query(
            "SELECT delay_slots, COUNT(*), CAST(AVG(receipt_to_schedule_ns) AS INTEGER), "
            "CAST(AVG(queue_delay_ns) AS INTEGER), CAST(AVG(rpc_round_trip_ns) AS INTEGER), "
            "CAST(AVG(waited_ns) AS INTEGER) FROM target GROUP BY delay_slots"):
        report["latency_ns_by_delay"][str(delay)] = {
            "targets": count, "receipt_to_schedule_mean_ns": med_sched,
            "queue_delay_mean_ns": med_queue, "rpc_network_mean_ns": med_net,
            "deliberate_wait_mean_ns": med_wait}
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
    report["sessions"] = _query("SELECT COUNT(*) FROM session")[0][0]
    report["reconnects"] = max(0, report["sessions"] - 1)
    report["faults"] = _query(
        "SELECT COUNT(*) FROM session WHERE end_reason IS NOT NULL AND end_reason<>'stopping' "
        "AND end_reason<>'peer closed'")[0][0]
    report["observed_after_gap"] = _query(
        "SELECT COUNT(*) FROM observation WHERE observed_after_gap=1")[0][0]
    report["performance_status"] = "not_evaluated"
    report["execution_status"] = "never_executed"
    return report


# --------------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------------

def reconciler_loop(connection, lock, stop, counts, interval=60.0,
                    b15a_path=B15A_DB, b15b_path=B15B_DB):
    """Reconcile on a timer, not only at shutdown.

    A session meant to run for days that reconciles once at exit would leave every observation
    reading `processed_unconfirmed` for its whole life, and an operator glancing at the census
    would see a fork state that means "not yet checked" and read it as "not corroborated".
    """
    while not stop.wait(interval):
        try:
            counts.update(reconcile(connection, lock, b15a_path, b15b_path))
        except sqlite3.Error as error:
            counts["worker_errors"] += 1
            counts["last_reconcile_error"] = f"{type(error).__name__}: {error}"


def releaser_loop(pending_queue, work_queue, stop, connection, lock, counts):
    """Hold the wait for finality here, so a worker is never blocked doing nothing.

    `pending_queue` is a priority queue keyed on the moment a target can plausibly be answered, so
    the earliest item is always at the head and sleeping on it cannot make a later one overdue.
    Every enqueue is at `t + lag` for the same lag, so arrivals are already in that order.
    """
    while not stop.is_set():
        try:
            item = pending_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        ready, record = item[0], item[-1]
        remaining = (ready - time.monotonic_ns()) / 1e9
        if remaining > 0 and stop.wait(remaining):
            pending_queue.task_done()
            break
        try:
            work_queue.put_nowait(record)
        except queue.Full:
            _durable(connection, lock, record, STATE_REFUSED, Q_OVERFLOW)
            counts["overflow"] += 1
        finally:
            pending_queue.task_done()


def measure_finalization_lag(url, opener=None):
    """How far finalized trails processed, right now. One pair of getSlot calls, at startup.

    Measured rather than assumed: the freeze recorded 31 slots at one moment, and a number written
    down once is a number that will be wrong later. Returns 0 if either call fails, which simply
    means the first attempt fires immediately and the bounded retry does the waiting.
    """
    tips = {}
    for commitment in (TRIGGER_COMMITMENT, STATE_READ_COMMITMENT):
        outcome, _status, payload = B15B._one_attempt(
            url, {"jsonrpc": "2.0", "id": 1, "method": "getSlot",
                  "params": [{"commitment": commitment}]}, opener)
        if outcome != "retrieved" or payload.get("result") is None:
            return 0
        tips[commitment] = payload["result"]
    return max(0, tips[TRIGGER_COMMITMENT] - tips[STATE_READ_COMMITMENT])


def worker_loop(work_queue, url, connection, lock, decoder, document, counts, stop,
                opener=None, exchanges=None, sleeper=time.sleep, first_attempt_delay_slots=0):
    while not stop.is_set():
        try:
            record = work_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            capture(record, url, connection, lock, decoder, document, counts, opener, exchanges,
                    sleeper, first_attempt_delay_slots)
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
        websocket=None, max_frames=None, reconcile_interval=60.0, max_sessions=10**9,
        reconnect_pause=1.0, reserve_bytes=None, max_segment_bytes=None):
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
    retention_document = B15J.verify_preregistration()
    reserve = retention_document["free_space_guard"]["reserve_bytes"] if reserve_bytes is None \
        else reserve_bytes
    segment_limit = retention_document["segment_format"]["max_segment_bytes"] \
        if max_segment_bytes is None else max_segment_bytes
    # Refuse at startup rather than after an hour of writing: if the reserve is already breached
    # there is nothing this pilot should be adding to the disk.
    B15J.assert_free_space(work_dir, reserve)
    B15J.discard_partial_archives(work_dir)
    raw = RawLog(work_dir / "raw_processed_frames.jsonl", retention=B15J,
                 max_segment_bytes=segment_limit, reserve_bytes=reserve,
                 check_interval_seconds=retention_document["free_space_guard"][
                     "check_interval_seconds"])
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

    # One pair of getSlot calls, before any worker starts. Workers then wait out the lag instead
    # of discovering it three requests at a time, each.
    finalization_lag = measure_finalization_lag(url, opener)
    ready_delay_ns = int(finalization_lag * SLOT_SECONDS * 1e9)
    connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)",
                       ("finalization_lag_slots_at_startup", str(finalization_lag)))
    connection.commit()
    lock = threading.Lock()
    counts = {"finalization_lag_slots": finalization_lag, "frames": 0, "launches": 0,
              "already_passed": 0, "overflow": 0, "captured": 0, "refused": 0,
              "pre_activation": 0, "worker_errors": 0, "missed_while_down": 0}
    pending_queue = queue.PriorityQueue(maxsize=MAX_QUEUE_DEPTH)
    work_queue = queue.Queue(maxsize=MAX_QUEUE_DEPTH)
    stop = threading.Event()
    threads = [threading.Thread(target=worker_loop,
                                args=(work_queue, url, connection, lock, curve_decoder,
                                      checkpoint_document, counts, stop, opener, exchanges,
                                      time.sleep, 0),
                                daemon=True) for _ in range(workers)]
    threads.append(threading.Thread(
        target=reconciler_loop, args=(connection, lock, stop, counts, reconcile_interval),
        daemon=True))
    threads.append(threading.Thread(
        target=releaser_loop,
        args=(pending_queue, work_queue, stop, connection, lock, counts), daemon=True))
    threads.append(threading.Thread(
        target=confirmation_worker,
        args=(connection, lock, stop, counts, url, opener), daemon=True))
    for thread in threads:
        thread.start()

    socket = None
    deadline = None if seconds is None else time.monotonic() + seconds
    try:
        # Sessions, not one connection. A single 30-second read timeout used to end the pilot for
        # good: the raw TimeoutError from the socket escaped past `except WebSocketRefused` and
        # unwound out of run(). A durable recorder that dies on the first quiet half-minute records
        # a few good minutes and then a silence indistinguishable from a chain with no launches.
        reconnect_index = 0
        while deadline is None or time.monotonic() < deadline:
            if max_frames is not None and counts["frames"] >= max_frames:
                break
            if reconnect_index >= max_sessions:
                counts["end_reason"] = "max_sessions"
                break
            session_id = hashlib.sha256(
                f"{time.time()}:{os.getpid()}:{reconnect_index}".encode()).hexdigest()[:32]
            # The gap is recorded BEFORE the frames that follow it, so a launch first seen after a
            # reconnect carries `observed_after_gap` for its whole life. Provenance that is only
            # attached afterwards is provenance that a later pass can quietly drop.
            with lock:
                connection.execute(
                    "INSERT INTO session(session_id,started_wall_unix,started_monotonic_ns,"
                    "reconnect_index,commitment) VALUES (?,?,?,?,?)",
                    (session_id, time.time(), time.monotonic_ns(), reconnect_index,
                     TRIGGER_COMMITMENT))
                connection.commit()
            counts["sessions"] = reconnect_index + 1
            counts["reconnects"] = reconnect_index
            frames_here, end_reason = 0, "stopping"
            try:
                socket = (websocket if websocket is not None else WS.WebSocket(ws_url))
                socket = socket.connect() or socket
                socket.send_json({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                                  "params": [{"mentions": [PILOT.PUMP_PROGRAM]},
                                             {"commitment": TRIGGER_COMMITMENT}]})
                while deadline is None or time.monotonic() < deadline:
                    if max_frames is not None and counts["frames"] >= max_frames:
                        break
                    message = socket.recv()
                    if message is None:
                        end_reason = "peer closed"
                        break
                    frames_here += 1
                    try:
                        handle_frame(message, create_decoder, raw, connection, pending_queue,
                                     document, counts, lock, session_id, reconnect_index > 0,
                                     ready_delay_ns)
                    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
                        counts["worker_errors"] += 1
                        raw.append({"handler_error": f"{type(error).__name__}: {error}",
                                    "received_wall_unix": time.time()})
            except (WS.WebSocketRefused, OSError) as error:
                # OSError covers TimeoutError and every ssl/socket failure beneath it. The fault is
                # recorded as a fault; it is never smoothed over into a quiet stretch.
                end_reason = f"{type(error).__name__}: {error}"
                counts["faults"] = counts.get("faults", 0) + 1
            finally:
                try:
                    socket.close()
                except Exception:                                         # noqa: BLE001
                    pass
                with lock:
                    connection.execute(
                        "UPDATE session SET ended_wall_unix=?, end_reason=?, frames=? "
                        "WHERE session_id=?", (time.time(), end_reason, frames_here, session_id))
                    connection.commit()
            if websocket is not None:
                break                       # a fixture transport is not reconnected to
            reconnect_index += 1
            if deadline is None or time.monotonic() < deadline:
                time.sleep(reconnect_pause)
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
    parser.add_argument("--withdraw-peer-orphans", action="store_true",
                        help="reset orphan verdicts not reached by asking the chain")
    parser.add_argument("--recover", action="store_true",
                        help="mark pending targets whose deadline passed while down")
    arguments = parser.parse_args(argv)
    if arguments.census_only:
        connection = open_database()
        print(json.dumps(census(connection), indent=2, sort_keys=True))
        return 0
    if arguments.withdraw_peer_orphans:
        connection = open_database()
        print(json.dumps({"withdrawn": withdraw_peer_orphans(connection, threading.Lock())}))
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
