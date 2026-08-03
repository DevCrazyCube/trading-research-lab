"""B15n — exit-horizon account reads scheduled from B15i's own launches.

Implements `research/B15N_NATIVE_EXIT_CHECKPOINT_PREREGISTRATION.json`, committed alone before any
checkpoint was scheduled.

**Why the source matters more than the machinery.** B15M admitted 4,896 cells of 18,846 exit
checkpoints. Those came from B15f, which schedules from B15a, which B15k measured holding 29% of the
launches B15i observes — and B15a has closed at its 5,000-launch stopping rule with extension
forbidden, so that fraction is final. Every study inheriting B15f's schedule inherits it. This worker
reads B15i's own observations instead. B15a and B15f are not read at all.

**Pure instrumentation.** No estimand, no assumption, no strategy figure. It creates evidence.

**Scheduling does not wait for confirmation; admission does.** A 1,000-slot horizon is about 400
seconds away and a launch's confirmation can take longer, so waiting would systematically lose the
shorter horizon on exactly the launches whose confirmation was slowest. Every row instead carries the
launch's fork state and gap provenance, and an unconfirmed, unresolved or orphaned launch's
checkpoint is recorded, counted and withheld from downstream admission.

**A poller, deliberately.** The nearest target is 400 seconds out, so a 20-second poll is 50 slots
inside the 150-slot tolerance. B15i needed an event-driven releaser because its targets are 1, 2 and
4 slots away and no poll can reach them; that reasoning does not transfer three orders of magnitude
further out, and building it anyway would be machinery with nothing to do.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15n"
DB_PATH = WORK_DIR / "exit_checkpoints.sqlite"
B15I_DB = ROOT / "research" / "b15i" / "processed_feed.sqlite"

PREREG_PATH = ROOT / "research" / "B15N_NATIVE_EXIT_CHECKPOINT_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "28a4dc50db2aced38669b8a4fa1e4f346a755262d212fd97927708c40ea1edbd"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

# Artifacts this worker may not consult as a scheduling source. The whole point of the module is
# that its population does not descend from them, so the ban is checked against the source text.
FORBIDDEN_SOURCE_ARTIFACTS = ("b15a/shadow.sqlite", "b15f/checkpoints.sqlite",
                              "B15A_DB", "B15F_DB")

C_PRE_PROTOCOL = "C_PRE_PROTOCOL"
C_LATE = "C_LATE"
N_RPC_FAILED = "N_RPC_FAILED"
N_TARGET_ALREADY_PASSED = "N_TARGET_ALREADY_PASSED"
N_ACCOUNT_MISMATCH = "N_ACCOUNT_MISMATCH"
N_ACCOUNT_ABSENT = "N_ACCOUNT_ABSENT"
N_NOT_CONFIRMED = "N_NOT_CONFIRMED"
N_ORPHANED = "N_ORPHANED"
N_SCHEDULE_CONFLICT = "N_SCHEDULE_CONFLICT"

STATE_SCHEDULED = "scheduled"
STATE_CHECKPOINTED = "checkpointed"
STATE_REFUSED = "refused"
STATE_NOT_SCHEDULED = "not_scheduled"

LABEL = "NATIVE_EXIT_CHECKPOINTS"
SLOT_SECONDS = 0.4


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15F = _load("b15f_checkpoint", "b15f_checkpoint.py")
B15B = _load("b15b_backfill", "b15b_backfill.py")


class ExitCheckpointRefused(RuntimeError):
    """This target is not read, and the reason is recorded rather than worked around."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ExitCheckpointRefused(
            f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ExitCheckpointRefused(
            f"the exit-checkpoint preregistration hashes {actual}, pinned {expected}")
    b15f = B15F.verify_preregistration()
    inherited = document["account_read"]["inherited_verbatim_from_b15f"]
    theirs = b15f["context_slot_geometry"]
    for key in ("max_lateness_slots", "max_attempts", "retry_interval_slots"):
        if inherited[key] != theirs[key]:
            raise ExitCheckpointRefused(
                f"this document says {key} is {inherited[key]} and B15F says {theirs[key]}; a "
                f"restated tolerance is a tolerance that can drift")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "FORBIDDEN_SOURCE_ARTIFACTS = (" if "FORBIDDEN_SOURCE_ARTIFACTS = (" in text \
        else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ExitCheckpointRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_no_b15a_or_b15f_dependency(path=None):
    """The population must not descend from B15a. Checked against the source, not promised.

    This is the entire reason the module exists, so it is the one property most worth asserting
    mechanically: a later edit adding a convenient join to B15f's schedule would silently reinstate
    the 29% censoring the work was done to remove.
    """
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    body = text.split("FORBIDDEN_SOURCE_ARTIFACTS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in FORBIDDEN_SOURCE_ARTIFACTS if token in body})
    if found:
        raise ExitCheckpointRefused(
            f"{path.name} refers to {found}; this worker's population must not descend from B15a "
            f"or B15f, which is the only reason it exists")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("b15a", "b15b", "b15c", "b15d", "b15e", "b15f", "b15g", "b15h", "b15i",
                   "b15j", "b11a"):
        if f"research{os.sep}{marker}" in resolved:
            raise ExitCheckpointRefused(
                f"{resolved} would write into research/{marker}; those are read-only here")
    if not resolved.endswith(os.sep + "b15n"):
        raise ExitCheckpointRefused(f"the work directory must be .../b15n, got {resolved}")
    return True


# --------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------

def target_slot(t0_slot, delay_slots, horizon_slots):
    """t0 + delay + horizon. One expression, so no caller can compose it differently."""
    for label, value in (("t0_slot", t0_slot), ("delay_slots", delay_slots),
                         ("horizon_slots", horizon_slots)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ExitCheckpointRefused(f"{label} must be an integer, got {value!r}")
    return t0_slot + delay_slots + horizon_slots


def assert_after_activation(t0_slot, activation_slot):
    if t0_slot is None or t0_slot <= activation_slot:
        raise ExitCheckpointRefused(
            f"{C_PRE_PROTOCOL}: t0 {t0_slot} is at or before activation {activation_slot}; there "
            f"is no path by which it is scheduled, backfilled or recovered")
    return True


def is_still_schedulable(target, current_slot, tolerance):
    """A target is schedulable while it is future, or late but inside the tolerance.

    Once it is past the tolerance the only honest answer is that it was missed: an account read
    taken now would report reserves from after the target and record them as the state at it.
    """
    return target + tolerance >= current_slot


def cells_for(t0_slot, document):
    """The six (delay, horizon) targets for one launch, in a fixed order."""
    delays = document["target_geometry"]["entry_delays_slots"]
    horizons = document["target_geometry"]["exit_horizons"]
    return [(delay, horizon["name"], target_slot(t0_slot, delay, horizon["slots"]))
            for delay in delays for horizon in horizons]


# --------------------------------------------------------------------------------------------
# Storage — its own namespace, nothing shared
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  mint TEXT, bonding_curve TEXT, t0_slot INTEGER NOT NULL, target_slot INTEGER NOT NULL,
  state TEXT NOT NULL, reason TEXT, attempts INTEGER,
  fork_state_at_schedule TEXT, observed_after_gap INTEGER NOT NULL DEFAULT 0,
  scheduled_at_wall_unix REAL NOT NULL, scheduled_at_slot INTEGER,
  PRIMARY KEY (signature, delay_slots, horizon));
CREATE INDEX IF NOT EXISTS schedule_due ON schedule(state, target_slot);
CREATE TABLE IF NOT EXISTS checkpoint (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  target_slot INTEGER NOT NULL, context_slot INTEGER NOT NULL, lateness_slots INTEGER NOT NULL,
  virtual_quote INTEGER NOT NULL, virtual_token INTEGER NOT NULL,
  real_quote INTEGER NOT NULL, real_token INTEGER NOT NULL,
  quote_mint TEXT NOT NULL, mayhem_mode INTEGER NOT NULL, complete INTEGER NOT NULL,
  fork_state_at_read TEXT, chain_verdict TEXT, observed_after_gap INTEGER NOT NULL DEFAULT 0,
  raw_sha256 TEXT NOT NULL, latency_ns INTEGER NOT NULL, attempts INTEGER NOT NULL,
  read_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (signature, delay_slots, horizon));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


class RawLog:
    """Every JSON-RPC exchange, appended before its answer is judged."""

    def __init__(self, path):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = pathlib.Path(path)
        self.handle = open(self.path, "a", encoding="utf-8")

    def append(self, record):
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        self.handle.write(line + "\n")
        self.handle.flush()
        return hashlib.sha256(line.encode()).hexdigest()

    def close(self):
        self.handle.close()


# --------------------------------------------------------------------------------------------
# Reading B15i's observations — the only source
# --------------------------------------------------------------------------------------------

def observed_launches(path=B15I_DB, after_slot=0, limit=None):
    """Launches B15i has recorded, with their provenance. Read-only, and the only source.

    Provenance is read WITH the launch rather than looked up later: a fork state fetched on a
    separate pass would describe a different moment than the row it lands on.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise ExitCheckpointRefused(
            f"no B15i feed at {path}; this worker has no other scheduling source and will not "
            f"invent one")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(observation)")}
        gap = "observed_after_gap" if "observed_after_gap" in columns else "0"
        verdict = "chain_verdict" if "chain_verdict" in columns else "NULL"
        rows = connection.execute(
            f"SELECT signature, t0_slot, mint, bonding_curve, fork_state, {gap}, {verdict} "
            f"FROM observation WHERE t0_slot > ? ORDER BY t0_slot, signature"
            + (f" LIMIT {int(limit)}" if limit else ""), (after_slot,)).fetchall()
    except sqlite3.Error as error:
        raise ExitCheckpointRefused(f"cannot read B15i's observations: {error}") from error
    finally:
        connection.close()
    fields = ("signature", "t0_slot", "mint", "bonding_curve", "fork_state",
              "observed_after_gap", "chain_verdict")
    return [dict(zip(fields, row)) for row in rows]


def schedule_new(connection, launches, current_slot, document, tolerance):
    """One durable row per (launch, delay, horizon). Written before anything is due.

    Scheduling does NOT wait for confirmation. The launch's fork state is recorded as it stood at
    scheduling and re-read at checkpoint time; confirmation gates ADMISSION, not scheduling, because
    a 1,000-slot horizon is 400 seconds away and a confirmation can take longer than that.
    """
    activation = document["activation"]["activation_slot"]
    scheduled = pre_protocol = passed = conflicts = 0
    for launch in launches:
        try:
            assert_after_activation(launch["t0_slot"], activation)
        except ExitCheckpointRefused:
            pre_protocol += 1
            continue
        for delay, horizon, target in cells_for(launch["t0_slot"], document):
            state, reason = STATE_SCHEDULED, None
            if not is_still_schedulable(target, current_slot, tolerance):
                state, reason = STATE_NOT_SCHEDULED, N_TARGET_ALREADY_PASSED
            existing = connection.execute(
                "SELECT target_slot FROM schedule WHERE signature=? AND delay_slots=? "
                "AND horizon=?", (launch["signature"], delay, horizon)).fetchone()
            if existing is not None:
                # Same slot twice, or a restart re-reading the same launch. Idempotent, unless the
                # geometry itself differs, which would mean two different targets under one key.
                if existing[0] != target:
                    connection.execute(
                        "UPDATE schedule SET state=?, reason=? WHERE signature=? AND "
                        "delay_slots=? AND horizon=?",
                        (STATE_REFUSED, N_SCHEDULE_CONFLICT, launch["signature"], delay, horizon))
                    conflicts += 1
                continue
            connection.execute(
                "INSERT INTO schedule(signature,delay_slots,horizon,mint,bonding_curve,t0_slot,"
                "target_slot,state,reason,attempts,fork_state_at_schedule,observed_after_gap,"
                "scheduled_at_wall_unix,scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (launch["signature"], delay, horizon, launch["mint"], launch["bonding_curve"],
                 launch["t0_slot"], target, state, reason, 0, launch["fork_state"],
                 int(bool(launch["observed_after_gap"])), time.time(), current_slot))
            if state == STATE_SCHEDULED:
                scheduled += 1
            else:
                passed += 1
    connection.commit()
    return {"scheduled": scheduled, C_PRE_PROTOCOL: pre_protocol,
            N_TARGET_ALREADY_PASSED: passed, N_SCHEDULE_CONFLICT: conflicts}


# --------------------------------------------------------------------------------------------
# The account read — B15F's semantics, and B15i's correction to them
# --------------------------------------------------------------------------------------------

def read_checkpoint(row, url, document, decoder, raw, opener=None, sleeper=time.sleep,
                    first_attempt_delay_slots=0):
    """One exit-horizon account read. Raw exchange preserved before the answer is judged.

    `minContextSlot` does NOT make the node wait — B15i measured 147 of 147 requests returning
    -32603 in about 220ms. So the client waits out the measured finalization lag first and B15F's
    bounded retry is the safety net. That correction is carried here rather than rediscovered.
    """
    inherited = document["account_read"]["inherited_verbatim_from_b15f"]
    target = row["target_slot"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [row["bonding_curve"],
                       {"encoding": "base64", "commitment": inherited["commitment"],
                        "minContextSlot": target}]}
    if first_attempt_delay_slots > 0:
        sleeper(first_attempt_delay_slots * SLOT_SECONDS)
    started = time.monotonic_ns()
    outcome = payload = None
    attempts = 0
    for attempt in range(inherited["max_attempts"]):
        attempts = attempt + 1
        attempt_started = time.monotonic_ns()
        outcome, status, payload = B15B._one_attempt(url, body, opener)
        raw_sha256 = raw.append({"method": "getAccountInfo", "signature": row["signature"],
                                 "delay_slots": row["delay_slots"], "horizon": row["horizon"],
                                 "target_slot": target, "attempt": attempts, "outcome": outcome,
                                 "http_status": status, "response": payload,
                                 "network_ns": time.monotonic_ns() - attempt_started,
                                 "at_wall_unix": time.time()})
        if outcome == "retrieved" or "min context slot" not in str(payload).lower():
            break
        if attempts < inherited["max_attempts"]:
            sleeper(inherited["retry_interval_slots"] * SLOT_SECONDS)
    latency = time.monotonic_ns() - started
    if outcome != "retrieved":
        raise ExitCheckpointRefused(
            f"{N_RPC_FAILED}: {outcome} after {attempts} attempts {str(payload)[:120]}")
    try:
        state, context_slot, lateness = B15F.read_account(
            payload, target, B15F.verify_preregistration(), decoder)
    except B15F.CheckpointRefused as error:
        code = str(error).split(":", 1)[0]
        if code == B15F.C_LATE:
            raise ExitCheckpointRefused(f"{C_LATE}: {error}") from error
        if code == B15F.C_ACCOUNT_MISSING:
            raise ExitCheckpointRefused(f"{N_ACCOUNT_ABSENT}: {error}") from error
        raise ExitCheckpointRefused(f"{N_ACCOUNT_MISMATCH}: {error}") from error
    return {"state": state, "context_slot": context_slot, "lateness_slots": lateness,
            "raw_sha256": raw_sha256, "latency_ns": latency, "attempts": attempts}


def current_provenance(signature, b15i_path=B15I_DB):
    """The launch's fork state and chain verdict AT READ TIME, re-read rather than remembered.

    A confirmation that arrived between scheduling and the exit horizon is the common case at a
    10,000-slot horizon, so using the state recorded at scheduling would understate corroboration
    on exactly the rows most likely to have gained it.
    """
    path = pathlib.Path(b15i_path)
    if not path.exists():
        return {"fork_state": None, "chain_verdict": None, "observed_after_gap": None}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(observation)")}
        gap = "observed_after_gap" if "observed_after_gap" in columns else "0"
        verdict = "chain_verdict" if "chain_verdict" in columns else "NULL"
        row = connection.execute(
            f"SELECT fork_state, {verdict}, {gap} FROM observation WHERE signature=?",
            (signature,)).fetchone()
    except sqlite3.Error:
        return {"fork_state": None, "chain_verdict": None, "observed_after_gap": None}
    finally:
        connection.close()
    if row is None:
        return {"fork_state": None, "chain_verdict": None, "observed_after_gap": None}
    return {"fork_state": row[0], "chain_verdict": row[1],
            "observed_after_gap": int(bool(row[2]))}


def admissible_downstream(fork_state, chain_verdict):
    """Only an explicitly chain-confirmed launch. Absence is never treated as confirmation."""
    return fork_state == "confirmed" or chain_verdict == "confirmed"


# --------------------------------------------------------------------------------------------
# The poller
# --------------------------------------------------------------------------------------------

def due_targets(connection, current_slot, tolerance, limit=None):
    """Targets whose slot has arrived and whose deadline has not passed, oldest first.

    A target past the tolerance is NOT returned here; it is retired by `retire_missed` so the
    reason it was missed is recorded rather than inferred from its continued absence.
    """
    rows = connection.execute(
        "SELECT signature, delay_slots, horizon, bonding_curve, t0_slot, target_slot, attempts "
        "FROM schedule WHERE state=? AND target_slot <= ? AND target_slot + ? >= ? "
        "ORDER BY target_slot" + (f" LIMIT {int(limit)}" if limit else ""),
        (STATE_SCHEDULED, current_slot, tolerance, current_slot)).fetchall()
    fields = ("signature", "delay_slots", "horizon", "bonding_curve", "t0_slot", "target_slot",
              "attempts")
    return [dict(zip(fields, row)) for row in rows]


def retire_missed(connection, current_slot, tolerance):
    """A scheduled target whose deadline passed is recorded missed and NEVER fetched.

    Fetching it now would produce an account read from after the target and record it as the state
    at the target. Restarts are the usual cause, so this runs before every drain.
    """
    cursor = connection.execute(
        "UPDATE schedule SET state=?, reason=? WHERE state=? AND target_slot + ? < ?",
        (STATE_REFUSED, N_TARGET_ALREADY_PASSED, STATE_SCHEDULED, tolerance, current_slot))
    connection.commit()
    return cursor.rowcount


def drain(connection, rows, url, document, decoder, raw, counts, opener=None, sleeper=time.sleep,
          first_attempt_delay_slots=0, b15i_path=B15I_DB, rate_per_second=2.0):
    """Read each due target once, at the frozen rate. Every outcome lands in the database."""
    for index, row in enumerate(rows):
        if index:
            sleeper(1.0 / rate_per_second)
        provenance = current_provenance(row["signature"], b15i_path)
        try:
            outcome = read_checkpoint(row, url, document, decoder, raw, opener, sleeper,
                                      first_attempt_delay_slots)
        except ExitCheckpointRefused as error:
            code = str(error).split(":", 1)[0]
            connection.execute(
                "UPDATE schedule SET state=?, reason=?, attempts=attempts+1 WHERE signature=? "
                "AND delay_slots=? AND horizon=?",
                (STATE_REFUSED, f"{code}:{str(error)[:200]}", row["signature"],
                 row["delay_slots"], row["horizon"]))
            connection.commit()
            counts[code] = counts.get(code, 0) + 1
            continue
        state = outcome["state"]
        connection.execute(
            "INSERT OR REPLACE INTO checkpoint(signature,delay_slots,horizon,target_slot,"
            "context_slot,lateness_slots,virtual_quote,virtual_token,real_quote,real_token,"
            "quote_mint,mayhem_mode,complete,fork_state_at_read,chain_verdict,observed_after_gap,"
            "raw_sha256,latency_ns,attempts,read_at_wall_unix) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["signature"], row["delay_slots"], row["horizon"], row["target_slot"],
             outcome["context_slot"], outcome["lateness_slots"], state["virtual_quote"],
             state["virtual_token"], state["real_quote"], state["real_token"],
             state["quote_mint"], int(state["mayhem_mode"]), int(state["complete"]),
             provenance["fork_state"], provenance["chain_verdict"],
             int(bool(provenance["observed_after_gap"])), outcome["raw_sha256"],
             outcome["latency_ns"], outcome["attempts"], time.time()))
        connection.execute(
            "UPDATE schedule SET state=?, reason=NULL, attempts=attempts+1 WHERE signature=? "
            "AND delay_slots=? AND horizon=?",
            (STATE_CHECKPOINTED, row["signature"], row["delay_slots"], row["horizon"]))
        connection.commit()
        counts["checkpointed"] = counts.get("checkpointed", 0) + 1
        if not admissible_downstream(provenance["fork_state"], provenance["chain_verdict"]):
            # Recorded, counted, and withheld. Absence of confirmation is never confirmation.
            key = N_ORPHANED if provenance["fork_state"] == "orphaned" else N_NOT_CONFIRMED
            counts[key] = counts.get(key, 0) + 1
    return counts


def census(connection):
    """Coverage only. No return, no capacity, no strategy figure of any kind."""
    def query(sql, args=()):
        return connection.execute(sql, args).fetchall()

    report = {"schema_version": SCHEMA_VERSION, "label": LABEL, "executable": False,
              "performance_status": "not_evaluated", "execution_status": "never_executed",
              "scheduling_source": "B15i observations; B15a and B15f are not read",
              "schedule_states": dict(query(
                  "SELECT state, COUNT(*) FROM schedule GROUP BY state")),
              "schedule_reasons": dict(query(
                  "SELECT substr(reason,1,instr(reason||':',':')-1), COUNT(*) FROM schedule "
                  "WHERE reason IS NOT NULL GROUP BY 1")),
              "checkpoints": query("SELECT COUNT(*) FROM checkpoint")[0][0],
              "launches_scheduled": query(
                  "SELECT COUNT(DISTINCT signature) FROM schedule")[0][0],
              "launches_with_a_checkpoint": query(
                  "SELECT COUNT(DISTINCT signature) FROM checkpoint")[0][0]}
    report["by_horizon_delay"] = {
        f"{horizon}|{delay}": {"checkpoints": count}
        for horizon, delay, count in query(
            "SELECT horizon, delay_slots, COUNT(*) FROM checkpoint GROUP BY horizon, delay_slots")}
    report["fork_state_at_read"] = dict(query(
        "SELECT fork_state_at_read, COUNT(*) FROM checkpoint GROUP BY fork_state_at_read"))
    report["admissible_downstream"] = query(
        "SELECT COUNT(*) FROM checkpoint WHERE fork_state_at_read='confirmed' "
        "OR chain_verdict='confirmed'")[0][0]
    report["withheld_pending_confirmation"] = report["checkpoints"] - \
        report["admissible_downstream"]
    report["observed_after_gap_checkpoints"] = query(
        "SELECT COUNT(*) FROM checkpoint WHERE observed_after_gap=1")[0][0]
    lateness = query("SELECT MIN(lateness_slots), CAST(AVG(lateness_slots) AS INTEGER), "
                     "MAX(lateness_slots) FROM checkpoint")
    report["lateness_slots"] = ({"min": lateness[0][0], "mean_floor": lateness[0][1],
                                 "max": lateness[0][2]} if lateness[0][0] is not None else None)
    latency = query("SELECT MIN(latency_ns), CAST(AVG(latency_ns) AS INTEGER), MAX(latency_ns) "
                    "FROM checkpoint")
    report["latency_ns"] = ({"min": latency[0][0], "mean_floor": latency[0][1],
                             "max": latency[0][2]} if latency[0][0] is not None else None)
    return report


def replay_checkpoints(raw_path, document, decoder):
    """Rebuild every checkpoint from the preserved raw responses alone.

    The claim that the raw log is sufficient is worth exactly as much as an exercise of it, so this
    reproduces the derived rows from the exchanges and the caller compares.
    """
    path = pathlib.Path(raw_path)
    if not path.exists():
        raise ExitCheckpointRefused(f"no raw exchange log at {path} to replay from")
    rebuilt = {}
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("outcome") != "retrieved" or record.get("method") != "getAccountInfo":
                continue
            key = (record["signature"], record["delay_slots"], record["horizon"])
            try:
                state, context_slot, lateness = B15F.read_account(
                    record["response"], record["target_slot"],
                    B15F.verify_preregistration(), decoder)
            except B15F.CheckpointRefused:
                continue
            rebuilt[key] = {"context_slot": context_slot, "lateness_slots": lateness,
                            "virtual_quote": state["virtual_quote"],
                            "virtual_token": state["virtual_token"],
                            "real_quote": state["real_quote"], "real_token": state["real_token"]}
    return rebuilt


def run(url=None, work_dir=WORK_DIR, b15i_path=B15I_DB, document=None, ticks=1, opener=None,
        sleeper=time.sleep, slot_source=None, poll_seconds=None, limit=None,
        finalization_lag_slots=None):
    """One or more polls: schedule what is new, retire what was missed, read what is due."""
    assert_no_execution_surface()
    assert_no_b15a_or_b15f_dependency()
    assert_isolated(work_dir)
    document = verify_preregistration() if document is None else document
    inherited = document["account_read"]["inherited_verbatim_from_b15f"]
    tolerance = inherited["max_lateness_slots"]
    poll = document["scheduler"]["poll_seconds"] if poll_seconds is None else poll_seconds
    url = url or B15B.rpc_url()
    work_dir = pathlib.Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    connection = open_database(work_dir / "exit_checkpoints.sqlite")
    raw = RawLog(work_dir / "rpc_exchanges.jsonl")
    decoder = B15B.build_decoder()
    lag = (B15F.current_slot(url, opener) if slot_source is None else slot_source())
    if finalization_lag_slots is None:
        finalization_lag_slots = 0
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("activation_slot", str(document["activation"]["activation_slot"])),
                       ("scheduling_source", "b15i_observation"),
                       ("rpc_endpoint_receipt", json.dumps(B15B.endpoint_receipt(url))),
                       ("label", LABEL)):
        connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)", (key, value))
    connection.commit()

    counts = {}
    try:
        for tick in range(ticks):
            if tick:
                sleeper(poll)
            current = B15F.current_slot(url, opener) if slot_source is None else slot_source()
            if current is None:
                counts["slot_unavailable"] = counts.get("slot_unavailable", 0) + 1
                continue
            activation = document["activation"]["activation_slot"]
            highest = connection.execute(
                "SELECT MAX(t0_slot) FROM schedule").fetchone()[0] or activation
            launches = observed_launches(b15i_path, after_slot=max(activation, highest),
                                         limit=limit)
            for key, value in schedule_new(connection, launches, current, document,
                                           tolerance).items():
                counts[key] = counts.get(key, 0) + value
            counts["retired_missed"] = counts.get("retired_missed", 0) + retire_missed(
                connection, current, tolerance)
            rows = due_targets(connection, current, tolerance, limit)
            counts = drain(connection, rows, url, document, decoder, raw, counts, opener, sleeper,
                           finalization_lag_slots, b15i_path,
                           inherited["max_requests_per_second"])
    finally:
        raw.close()
    report = census(connection)
    connection.close()
    return counts, report


def status(work_dir=WORK_DIR):
    path = pathlib.Path(work_dir) / "exit_checkpoints.sqlite"
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started", "label": LABEL}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        return census(connection)
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15n B15i-native exit checkpoints (read-only against the chain)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--ticks", type=int, default=None,
                        help="number of polls; omit to run until stopped")
    parser.add_argument("--limit", type=int, default=None)
    arguments = parser.parse_args(argv)
    if arguments.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    lag = 0
    try:
        # Measured once, not assumed: the client waits out the finalization lag before its first
        # attempt because minContextSlot rejects rather than waits.
        url = B15B.rpc_url()
        processed = B15F.current_slot(url)
        body = {"jsonrpc": "2.0", "id": 1, "method": "getSlot",
                "params": [{"commitment": "processed"}]}
        outcome, _status, payload = B15B._one_attempt(url, body, None)
        if outcome == "retrieved" and payload.get("result") and processed:
            lag = max(0, payload["result"] - processed)
    except Exception:                                                     # noqa: BLE001
        lag = 0
    ticks = arguments.ticks if arguments.ticks is not None else 10 ** 9
    counts, report = run(ticks=ticks, limit=arguments.limit, finalization_lag_slots=lag)
    print(json.dumps({"counts": counts, "census": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
