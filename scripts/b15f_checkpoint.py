"""B15f — prospective point-in-time bonding-curve account checkpoints. Read-only.

Implements `research/B15F_CHECKPOINT_PREREGISTRATION.json`, committed alone before any account
query was made.

The problem it exists for, measured before it was designed: `h_1000_slots` lands 400 seconds after
the entry slot, and the existing chain does not price an entry until up to 900 seconds later. The
target is gone before anything downstream knows the position exists. So **scheduling is decoupled
from pricing**: the moment B15a decodes a launch, `t0_slot` alone determines every slot-addressable
target, and the schedule is written then.

Two rules that make this honest rather than a retrospective repair:

- **A target that has already passed is never scheduled.** It stays censored under
  `C_PRE_CHECKPOINT_PROTOCOL`. Filling it with current reserves would present today's state as the
  state at a moment that has gone.
- **A response that arrives too late is refused, not used.** Reserves 200 slots past the target are
  not the reserves at the target, and `max_lateness_slots` was fixed before any checkpoint existed
  so it cannot be widened to admit one.

It reads B15a's small indexed launch table and never touches the gigabyte raw log.
"""
import argparse
import base64
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

WORK_DIR = ROOT / "research" / "b15f"
DB_PATH = WORK_DIR / "checkpoints.sqlite"
EXCHANGE_PATH = WORK_DIR / "rpc_exchanges.jsonl"
B15A_DB = ROOT / "research" / "b15a" / "shadow.sqlite"

PREREG_PATH = ROOT / "research" / "B15F_CHECKPOINT_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "be9029b9e7c118e43dc330745aacb664f698750949c9d5b3fc07e56217c1f9e8"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BONDING_CURVE_DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")

C_LATE = "C_LATE"
C_EARLY_EXHAUSTED = "C_EARLY_EXHAUSTED"
C_ACCOUNT_MISSING = "C_ACCOUNT_MISSING"
C_ACCOUNT_CLOSED = "C_ACCOUNT_CLOSED"
C_WRONG_OWNER = "C_WRONG_OWNER"
C_SCHEMA = "C_SCHEMA"
C_DECODE = "C_DECODE"
C_COMPLETE = "C_COMPLETE"
C_MIGRATED = "C_MIGRATED"
C_RPC_EXHAUSTED = "C_RPC_EXHAUSTED"
C_PRE_CHECKPOINT_PROTOCOL = "C_PRE_CHECKPOINT_PROTOCOL"

STATE_SCHEDULED = "scheduled"
STATE_CHECKPOINTED = "checkpointed"
STATE_REFUSED = "refused"
STATE_NOT_SCHEDULED = "not_scheduled"

LABEL = "SIMULATED_SHADOW_CHECKPOINT"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15E = _load("b15e_shadow_path", "b15e_shadow_path.py")
B15D = B15E.B15D
B15C = B15D.B15C
B15B = B15D.B15B
PILOT = B15D.PILOT
B10A = B15D.B10A


class CheckpointRefused(B15E.ShadowPathRefused):
    """The checkpoint will not be recorded, and says why rather than substituting a value."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CheckpointRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CheckpointRefused(
            f"the checkpoint preregistration hashes {actual}, pinned {expected}. The lateness "
            "tolerance and the prospective-only rule were frozen before any query, and a changed "
            "document is a different protocol")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise CheckpointRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("research/b15a", "research/b15b", "research/b15c", "research/b15d",
                   "research/b15e", "research/b11a"):
        if marker.replace("/", os.sep) in resolved:
            raise CheckpointRefused(
                f"{resolved} would write into {marker!r}; those are read-only evidence here")
    if not resolved.endswith(os.sep + "b15f"):
        raise CheckpointRefused(f"the work directory must be .../b15f, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    try:
        return B15E.assert_no_float(node, path)
    except B15E.ShadowPathRefused as error:
        raise CheckpointRefused(str(error)) from error


# --------------------------------------------------------------------------------------------
# Scheduling — prospective only, from the small indexed launch table
# --------------------------------------------------------------------------------------------

def target_slot(t0_slot, delay_slots, horizon_slots):
    """The NOMINAL target: t0 + delay + horizon.

    Nominal because B15d's actual entry observation slot is not known until the entry is priced,
    and by then the target has passed. Checkpoint targets therefore differ from B15e's, and the
    two populations are never mixed.
    """
    return t0_slot + delay_slots + horizon_slots


def is_schedulable(target, current_slot):
    """A target may be scheduled ONLY if it has not yet passed.

    This is the whole difference between a prospective protocol and a retrospective repair.
    """
    return target > current_slot


def due_targets(connection, current_slot):
    return connection.execute(
        "SELECT entry_signature, delay_slots, horizon, mint, bonding_curve, target_slot "
        "FROM schedule WHERE state=? AND target_slot <= ? ORDER BY target_slot",
        (STATE_SCHEDULED, current_slot)).fetchall()


def schedule_new(connection, launches, current_slot, document):
    """Write a durable schedule row for every future target. Restart-safe by construction."""
    delays = document["scheduling"]["delay_grid"]
    horizons = {"h_1000_slots": 1000, "h_10000_slots": 10000}
    scheduled = skipped = 0
    for signature, t0_slot, mint, curve in launches:
        for delay in delays:
            for horizon, horizon_slots in horizons.items():
                target = target_slot(t0_slot, delay, horizon_slots)
                if not is_schedulable(target, current_slot):
                    # Already gone. Recorded as NOT scheduled with its own reason so this
                    # population can never be confused with one that was observed.
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO schedule(entry_signature,delay_slots,horizon,mint,"
                        "bonding_curve,t0_slot,target_slot,state,reason,scheduled_at_wall_unix,"
                        "scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (signature, delay, horizon, mint, curve, t0_slot, target,
                         STATE_NOT_SCHEDULED, C_PRE_CHECKPOINT_PROTOCOL, time.time(),
                         current_slot))
                    skipped += cursor.rowcount
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO schedule(entry_signature,delay_slots,horizon,mint,"
                    "bonding_curve,t0_slot,target_slot,state,reason,scheduled_at_wall_unix,"
                    "scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, delay, horizon, mint, curve, t0_slot, target, STATE_SCHEDULED,
                     None, time.time(), current_slot))
                scheduled += cursor.rowcount
    connection.commit()
    return scheduled, skipped


# --------------------------------------------------------------------------------------------
# Account decoding — pinned layout only
# --------------------------------------------------------------------------------------------

def decode_bonding_curve(data, decoder):
    """The pinned BondingCurve layout, or a refusal. Never parsed on the assumption it is right."""
    # No separate length check: `data[:8] != DISCRIMINATOR` is already true for anything shorter
    # than eight bytes, so a preceding length guard could never be the branch that fires. It read
    # as an extra safeguard and was one more line to be wrong in.
    if data[:8] != BONDING_CURVE_DISCRIMINATOR:
        raise CheckpointRefused(
            f"{C_SCHEMA}: discriminator {data[:8].hex()} is not the pinned "
            f"{BONDING_CURVE_DISCRIMINATOR.hex()}")
    try:
        return decoder["b7d"].read_struct(
            decoder["b7d"].Cursor(data[8:]), decoder["types"]["BondingCurve"], decoder["types"])
    except Exception as error:                                            # noqa: BLE001
        raise CheckpointRefused(f"{C_DECODE}: {type(error).__name__}: {error}") from error


def state_from_account(fields, slot):
    """B10a's state, from the account. It carries real_quote and complete directly."""
    state = {
        "virtual_quote": fields.get("virtual_quote_reserves"),
        "virtual_token": fields.get("virtual_token_reserves"),
        "real_quote": fields.get("real_quote_reserves"),
        "real_token": fields.get("real_token_reserves"),
        "quote_mint": fields.get("quote_mint"),
        "mayhem_mode": bool(fields.get("is_mayhem_mode")),
        "complete": bool(fields.get("complete")),
        "slot": slot,
    }
    missing = [name for name, value in state.items() if value is None]
    if missing:
        raise CheckpointRefused(f"{C_DECODE}: the account does not publish {missing}")
    return state


def assert_geometry(context_slot, target, document):
    """Context-slot geometry, fixed before any checkpoint existed."""
    geometry = document["context_slot_geometry"]
    if context_slot is None:
        raise CheckpointRefused(f"{C_RPC_EXHAUSTED}: the response carries no context slot")
    if context_slot < target:
        raise CheckpointRefused(
            f"{C_EARLY_EXHAUSTED}: context slot {context_slot} never reached target {target}")
    lateness = context_slot - target
    if lateness > geometry["max_lateness_slots"]:
        raise CheckpointRefused(
            f"{C_LATE}: context slot {context_slot} is {lateness} slots past target {target}, "
            f"beyond the {geometry['max_lateness_slots']} fixed before any checkpoint existed. "
            "Reserves that late are not the reserves at the target")
    return lateness


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule (
  entry_signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  mint TEXT, bonding_curve TEXT, t0_slot INTEGER NOT NULL, target_slot INTEGER NOT NULL,
  state TEXT NOT NULL, reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  scheduled_at_wall_unix REAL NOT NULL, scheduled_at_slot INTEGER NOT NULL,
  PRIMARY KEY (entry_signature, delay_slots, horizon));
CREATE INDEX IF NOT EXISTS schedule_due ON schedule(state, target_slot);
CREATE TABLE IF NOT EXISTS checkpoint (
  entry_signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  target_slot INTEGER NOT NULL, context_slot INTEGER NOT NULL, lateness_slots INTEGER NOT NULL,
  virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, real_token INTEGER,
  quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER,
  evidence_sha256 TEXT NOT NULL, observed_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (entry_signature, delay_slots, horizon));
CREATE TABLE IF NOT EXISTS checkpoint_exit (
  entry_signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  scenario_id TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
  proceeds_lamports INTEGER, execution_cost_lamports INTEGER, evidence_sha256 TEXT NOT NULL,
  PRIMARY KEY (entry_signature, delay_slots, horizon, scenario_id));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def decoded_launches(b15a_path=B15A_DB, limit=None):
    """B15a's small indexed launch table. The gigabyte raw log is never opened."""
    connection = sqlite3.connect(f"file:{b15a_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT signature, slot, mint, bonding_curve FROM launch "
            "WHERE decode_status=? AND slot IS NOT NULL AND bonding_curve IS NOT NULL "
            "ORDER BY launch_seq", (PILOT.DECODE_DECODED,)).fetchall()
    finally:
        connection.close()
    return rows[:limit] if limit else rows


# --------------------------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------------------------

def current_slot(url, opener=None):
    """One getSlot per scheduler tick. Finalized, because a target must be settled."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "getSlot",
            "params": [{"commitment": "finalized"}]}
    outcome, _status, payload = B15B._one_attempt(url, body, opener)
    if outcome != "retrieved":
        raise CheckpointRefused(f"{C_RPC_EXHAUSTED}: getSlot returned {outcome}: {payload}")
    return payload.get("result")


def fetch_account(curve, url, exchanges, opener=None):
    """One getAccountInfo. The exchange is preserved before the answer is judged."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [curve, {"encoding": "base64", "commitment": "finalized"}]}
    requested_wall, requested_mono = time.time(), time.monotonic_ns()
    outcome, status_code, payload = B15B._one_attempt(url, body, opener)
    received_wall, received_mono = time.time(), time.monotonic_ns()
    exchanges.append({
        "bonding_curve": curve, "endpoint_scheme_host": B15B.endpoint_receipt(url),
        "request_json": body, "requested_wall_unix": requested_wall,
        "requested_monotonic_ns": requested_mono, "received_wall_unix": received_wall,
        "received_monotonic_ns": received_mono, "http_status": status_code,
        "response_json_or_error": payload,
        "raw_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(),
        "outcome": outcome,
    })
    return outcome, payload, received_mono - requested_mono


def read_account(payload, target, document, decoder):
    """The account state at the target, or a visible refusal. Never a substituted value."""
    result = (payload.get("result") or {})
    context_slot = (result.get("context") or {}).get("slot")
    lateness = assert_geometry(context_slot, target, document)
    value = result.get("value")
    if value is None:
        raise CheckpointRefused(f"{C_ACCOUNT_MISSING}: getAccountInfo returned null")
    if value.get("owner") != PUMP_PROGRAM:
        raise CheckpointRefused(f"{C_WRONG_OWNER}: owner {value.get('owner')}")
    if not value.get("lamports"):
        raise CheckpointRefused(f"{C_ACCOUNT_CLOSED}: the account holds no lamports")
    data = value.get("data")
    raw = base64.b64decode(data[0]) if isinstance(data, list) and data else b""
    if not raw:
        raise CheckpointRefused(f"{C_ACCOUNT_CLOSED}: the account carries no data")
    fields = decode_bonding_curve(raw, decoder)
    return state_from_account(fields, target), context_slot, lateness


def run(limit=None, b15a_path=B15A_DB, work_dir=WORK_DIR, opener=None, sleeper=time.sleep,
        url=None, slot_source=None, ticks=1):
    """One or more scheduler ticks: schedule future targets, then check the due ones."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    rate = document["rate_policy"]
    url = url or B15B.rpc_url()
    receipt = B15B.endpoint_receipt(url)
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "checkpoints.sqlite")
    exchanges = B15B.ExchangeLog(pathlib.Path(work_dir) / "rpc_exchanges.jsonl")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("endpoint_scheme_host", receipt), ("label", LABEL),
                       ("executable", "0"), ("execution_status", "never_executed"),
                       ("market_impact", "unmeasured"),
                       ("landing_probability", "unmeasured")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = B15B.build_decoder()
    route = json.loads((ROOT / "research" / "B15E_SHADOW_PATH_PREREGISTRATION.json").read_text())
    exit_scenarios = {s["scenario_id"]: s for s in route["exit_cost_scenarios"]}
    counts = {"ticks": 0, "scheduled": 0, "not_scheduled_already_passed": 0, "due": 0,
              "checkpointed": 0, "refused": 0, "exits_priced": 0}
    refusals = {}
    try:
        for _tick in range(ticks):
            counts["ticks"] += 1
            slot = slot_source() if slot_source else current_slot(url, opener)
            launches = decoded_launches(b15a_path, limit)
            scheduled, skipped = schedule_new(connection, launches, slot, document)
            counts["scheduled"] += scheduled
            counts["not_scheduled_already_passed"] += skipped
            due = due_targets(connection, slot)
            counts["due"] += len(due)
            for signature, delay, horizon, mint, curve, target in due:
                if rate["min_interval_ms"]:
                    sleeper(rate["min_interval_ms"] / 1000.0)
                connection.execute(
                    "UPDATE schedule SET attempts = attempts + 1 WHERE entry_signature=? AND "
                    "delay_slots=? AND horizon=?", (signature, delay, horizon))
                outcome, payload, _latency = fetch_account(curve, url, exchanges, opener)
                try:
                    if outcome != "retrieved":
                        raise CheckpointRefused(f"{C_RPC_EXHAUSTED}: {outcome}")
                    state, context_slot, lateness = read_account(payload, target, document,
                                                                 decoder)
                except CheckpointRefused as error:
                    code = str(error).split(":", 1)[0]
                    if code == C_EARLY_EXHAUSTED:
                        attempts = connection.execute(
                            "SELECT attempts FROM schedule WHERE entry_signature=? AND "
                            "delay_slots=? AND horizon=?",
                            (signature, delay, horizon)).fetchone()[0]
                        if attempts < document["context_slot_geometry"]["max_attempts"]:
                            # Still short of the target. Left SCHEDULED so the next tick retries;
                            # a bounded retry is not a refusal.
                            connection.commit()
                            continue
                    _refuse(connection, signature, delay, horizon, code, str(error)[:200])
                    counts["refused"] += 1
                    refusals[code] = refusals.get(code, 0) + 1
                    continue
                _record(connection, signature, delay, horizon, target, context_slot, lateness,
                        state)
                counts["checkpointed"] += 1
                counts["exits_priced"] += _price_exits(connection, signature, delay, horizon,
                                                       state, exit_scenarios, b15a_path)
                connection.commit()
    finally:
        exchanges.close()
        connection.close()
    counts["refusals_by_code"] = dict(sorted(refusals.items()))
    counts["label"] = LABEL
    counts["endpoint_scheme_host"] = receipt
    counts["market_impact"] = "unmeasured"
    counts["landing_probability"] = "unmeasured"
    counts["no_retrospective_mix_with_b15e"] = True
    return counts


def _refuse(connection, signature, delay, horizon, code, detail):
    connection.execute(
        "UPDATE schedule SET state=?, reason=? WHERE entry_signature=? AND delay_slots=? "
        "AND horizon=?", (STATE_REFUSED, f"{code}:{detail}"[:240], signature, delay, horizon))
    connection.commit()


def _record(connection, signature, delay, horizon, target, context_slot, lateness, state):
    record = {"entry_signature": signature, "delay_slots": delay, "horizon": horizon,
              "target_slot": target, "context_slot": context_slot,
              "lateness_slots": lateness, "state": state}
    assert_no_float(record)
    connection.execute(
        "INSERT OR REPLACE INTO checkpoint(entry_signature,delay_slots,horizon,target_slot,"
        "context_slot,lateness_slots,virtual_quote,virtual_token,real_quote,real_token,"
        "quote_mint,mayhem_mode,complete,evidence_sha256,observed_at_wall_unix) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (signature, delay, horizon, target, context_slot, lateness, state["virtual_quote"],
         state["virtual_token"], state["real_quote"], state["real_token"], state["quote_mint"],
         int(state["mayhem_mode"]), int(state["complete"]), evidence_hash(record), time.time()))
    connection.execute(
        "UPDATE schedule SET state=? WHERE entry_signature=? AND delay_slots=? AND horizon=?",
        (STATE_CHECKPOINTED, signature, delay, horizon))


def _price_exits(connection, signature, delay, horizon, state, exit_scenarios, b15a_path):
    """Three scenarios from ONE shared on-chain state. The chain knows nothing of our scenarios."""
    tokens = _tokens_held(signature, delay, b15a_path)
    priced = 0
    for scenario_id, scenario in exit_scenarios.items():
        status, reason, proceeds, cost = STATE_REFUSED, None, None, None
        if tokens is None:
            reason = "entry_not_priced"
        elif state["complete"]:
            reason = C_COMPLETE
        else:
            policy = {field: scenario[field] for field in
                      ("base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                       "ata_rent_lamports", "failed_attempts")}
            schedule = {"fee_bps": 95, "creator_fee_bps": 5, "cashback_fee_bps": 0,
                        "buyback_fee_bps": 0}
            try:
                result = B10A.price_exit(state, tokens, schedule, policy)
                costs = result.get("execution_costs")
                if result.get("quote_lamports") is None or not isinstance(costs, dict) \
                        or "total" not in costs:
                    reason = "no_cost_structure"
                else:
                    status, proceeds, cost = "priced", result["quote_lamports"], costs["total"]
                    priced += 1
            except Exception as error:                                    # noqa: BLE001
                reason = f"{C_COMPLETE if state['complete'] else 'liquidity'}:" \
                         f"{type(error).__name__}"
        connection.execute(
            "INSERT OR REPLACE INTO checkpoint_exit(entry_signature,delay_slots,horizon,"
            "scenario_id,status,reason,proceeds_lamports,execution_cost_lamports,evidence_sha256) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (signature, delay, horizon, scenario_id, status, reason, proceeds, cost,
             evidence_hash({"s": signature, "d": delay, "h": horizon, "c": scenario_id,
                            "st": status})))
    return priced


def _tokens_held(signature, delay, b15a_path):
    """The position size from B15d, if the entry has been priced. None is not zero."""
    path = ROOT / "research" / "b15d" / "shadow_entries.sqlite"
    if not path.exists():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        row = connection.execute(
            "SELECT tokens_out FROM candidate WHERE signature=? AND delay_slots=? AND status=? "
            "LIMIT 1", (signature, delay, B15D.STATUS_PRICED)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return row[0] if row else None


def status(db_path=DB_PATH):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        by_state = dict(connection.execute("SELECT state, COUNT(*) FROM schedule GROUP BY 1"))
        reasons = dict(connection.execute(
            "SELECT COALESCE(substr(reason,1,40),'none'), COUNT(*) FROM schedule "
            "WHERE reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8"))
        checkpoints = connection.execute("SELECT COUNT(*) FROM checkpoint").fetchone()[0]
        lateness = [r[0] for r in connection.execute(
            "SELECT lateness_slots FROM checkpoint ORDER BY lateness_slots")]
        exits = dict(connection.execute(
            "SELECT status, COUNT(*) FROM checkpoint_exit GROUP BY 1"))
        pending = connection.execute(
            "SELECT COUNT(*) FROM schedule WHERE state=?", (STATE_SCHEDULED,)).fetchone()[0]
        next_target = connection.execute(
            "SELECT MIN(target_slot) FROM schedule WHERE state=?",
            (STATE_SCHEDULED,)).fetchone()[0]
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "label": meta.get("label"),
        "executable": False,
        "endpoint_scheme_host": meta.get("endpoint_scheme_host"),
        "execution_status": meta.get("execution_status"),
        "market_impact": meta.get("market_impact"),
        "landing_probability": meta.get("landing_probability"),
        "schedule_by_state": by_state,
        "pending_future_targets": pending,
        "next_target_slot": next_target,
        "checkpoints_taken": checkpoints,
        "lateness_slots": B15B._summary(lateness),
        "checkpoint_exits_by_status": exits,
        "top_reasons": reasons,
        "no_retrospective_mix_with_b15e": True,
        "already_passed_targets_stay_censored": True,
    }
    PILOT.assert_redacted(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    if args.contract:
        document = verify_preregistration()
        assert_no_execution_surface()
        assert_isolated()
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "preregistration_id": document["preregistration_id"],
            "preregistration_canonical_sha256": PREREG_CANONICAL_SHA256,
            "schedulable_horizons": document["scheduling"]["schedulable_horizons"],
            "max_lateness_slots": document["context_slot_geometry"]["max_lateness_slots"],
            "scheduler_poll_seconds": document["rate_policy"]["scheduler_poll_seconds"],
            "prospective_only": True, "label": LABEL, "executable": False,
        }, indent=2, sort_keys=True))
        return 0
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if args.run:
        print(json.dumps(run(limit=args.limit, ticks=args.ticks), indent=2, sort_keys=True))
        return 0
    parser.error("nothing to do; --contract, --status or --run")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PILOT.PilotRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
