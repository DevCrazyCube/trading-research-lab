"""B15h — prospective V2 entry checkpoints whose state does not depend on gapped history.

Implements `research/B15H_PROSPECTIVE_ENTRY_PREREGISTRATION.json`, committed alone before any V2
checkpoint was scheduled.

**What V1 got subtly wrong, and what this changes.** V1 attached `S07_session_degraded` to the
DECISION. That was right for V1, because V1's delayed entry state was reconstructed from TradeEvent
observations between t0 and t0+delay, and a gap there silently removes trades — leaving a state
that looks complete and is wrong. But it was the entry STATE that was poisoned, not the launch
observation. If the CreateEvent frame arrived, that launch was observed; a gap before it does not
make the frame that did arrive less real.

So V2 reads the bonding-curve ACCOUNT at t0+delay instead of reconstructing from a stream of
deltas. A launch observed after a reconnect can yield a valid V2 entry, and its
`observed_after_gap` provenance is carried for its whole life rather than erased.

**It licenses nothing about coverage.** Every result here is conditioned on OBSERVED launches. How
many launches we never saw is not estimable from this feed, and the coverage census is published
beside every result rather than beneath it.

**Nothing pre-activation ever enters.** Every quarantined V1 cell stays quarantined. There is no
code path here that reaches backwards.
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

WORK_DIR = ROOT / "research" / "b15h"
DB_PATH = WORK_DIR / "prospective_entries.sqlite"
B15A_DB = ROOT / "research" / "b15a" / "shadow.sqlite"
B15B_DB = ROOT / "research" / "b15b" / "backfill.sqlite"

PREREG_PATH = ROOT / "research" / "B15H_PROSPECTIVE_ENTRY_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "585435bfb7c8e94660bfcbb4dded76af31c8f8d14ba71858c5942ced007391ac"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

H_PRE_ACTIVATION = "H_PRE_ACTIVATION"
H_NO_CREATE_EVENT = "H_NO_CREATE_EVENT"
H_NO_MATCHING_TRANSACTION = "H_NO_MATCHING_TRANSACTION"
H_INCOMPLETE_T0 = "H_INCOMPLETE_T0"
H_NO_CHECKPOINT = "H_NO_CHECKPOINT"
H_CHECKPOINT_LATE = "H_CHECKPOINT_LATE"
H_TARGET_MISSED = "H_TARGET_MISSED"
H_ACCOUNT_MISMATCH = "H_ACCOUNT_MISMATCH"
H_UNDECIDABLE_COORDINATE = "H_UNDECIDABLE_COORDINATE"
H_FEED_UNREADABLE = "H_FEED_UNREADABLE"
H_CURVE_COMPLETE = "H_CURVE_COMPLETE"
H_V1_MIXING = "H_V1_MIXING"

STATE_PENDING = "pending"
STATE_PRICED = "priced"
STATE_REFUSED = "refused"

PROVENANCE_CONTINUOUS = "observed_continuous"
PROVENANCE_AFTER_GAP = "observed_after_gap"

LABEL = "SIMULATED_PROSPECTIVE_ENTRY_V2"

# Identifiers belonging to the V1 population. Offering one to a V2 computation is a refusal, not a
# merge: V1 cells were priced from a reconstruction a gap can truncate and V2 cells from an account
# read, so a difference between them would measure the evidence bases rather than a strategy.
V1_POPULATION_MARKERS = ("D_feed_degraded_at_t0", "b15d_v1", "b15g_v1", "shadow_entries_v1")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15G = _load("b15g_checkpoint_join", "b15g_checkpoint_join.py")
B15F, B15D, B15B, PILOT, B10A = B15G.B15F, B15G.B15D, B15G.B15B, B15G.PILOT, B15G.B10A


class ProspectiveRefused(B15G.JoinRefused):
    """The V2 cell will not be produced, and says why rather than reaching for weaker evidence."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ProspectiveRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ProspectiveRefused(
            f"the prospective preregistration hashes {actual}, pinned {expected}. The activation "
            "slot was fixed ahead of the present and a changed document is a different boundary")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ProspectiveRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("b15a", "b15b", "b15c", "b15d", "b15e", "b15f", "b15g", "b11a"):
        if f"research{os.sep}{marker}" in resolved:
            raise ProspectiveRefused(
                f"{resolved} would write into research/{marker}; those are read-only here")
    if not resolved.endswith(os.sep + "b15h"):
        raise ProspectiveRefused(f"the work directory must be .../b15h, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    try:
        return B15G.assert_no_float(node, path)
    except B15G.JoinRefused as error:
        raise ProspectiveRefused(str(error)) from error


def assert_not_v1(value):
    """A V1 identifier offered to a V2 computation is refused, never merged."""
    text = json.dumps(value, default=str)
    for marker in V1_POPULATION_MARKERS:
        if marker in text:
            raise ProspectiveRefused(
                f"{H_V1_MIXING}: {marker!r} belongs to the V1 population. V1 cells were priced "
                "from a reconstruction a gap can truncate and V2 cells from an account read; a "
                "difference between them would measure the evidence bases, not a strategy")
    return True


# --------------------------------------------------------------------------------------------
# The activation boundary
# --------------------------------------------------------------------------------------------

def assert_after_activation(t0_slot, activation_slot):
    """STRICTLY after. Nothing that already existed may enter the V2 population."""
    if t0_slot is None:
        raise ProspectiveRefused(f"{H_PRE_ACTIVATION}: the launch has no t0 slot")
    if t0_slot <= activation_slot:
        raise ProspectiveRefused(
            f"{H_PRE_ACTIVATION}: t0 {t0_slot} is at or before the activation slot "
            f"{activation_slot}. This launch belongs to V1 and stays there; there is no path by "
            "which a quarantined cell is recovered")
    return True


def entry_target_slot(t0_slot, delay_slots):
    """t0 + delay. No horizon here — this is the ENTRY, not an outcome."""
    return t0_slot + delay_slots


# --------------------------------------------------------------------------------------------
# Provenance — retained, never rewritten
# --------------------------------------------------------------------------------------------

def launch_provenance(b15a_path=B15A_DB):
    """Per-launch provenance and the session census, read together from B15a.

    The provenance is a FACT about how the launch was seen and it travels with the row for its
    whole life. It is never rewritten as continuous, and `None` means the record was unreadable —
    which is refused rather than assumed clean.
    """
    path = pathlib.Path(b15a_path)
    if not path.exists():
        return None, None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        degraded = {row[0] for row in connection.execute(
            "SELECT l.signature FROM launch l JOIN decision d ON d.launch_seq = l.launch_seq "
            "WHERE d.reason_code LIKE ?", (f"{PILOT.S07_SESSION_DEGRADED}%",))}
        sessions = connection.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        faults = connection.execute(
            "SELECT COUNT(*) FROM connection_event WHERE kind='fault'").fetchone()[0]
        launches = connection.execute("SELECT COUNT(*) FROM launch").fetchone()[0]
        census = {"sessions": sessions, "reconnects": max(0, sessions - 1), "faults": faults,
                  "launches_observed": launches,
                  "launches_observed_after_gap": len(degraded)}
    except sqlite3.Error:
        return None, None
    finally:
        connection.close()
    return degraded, census


def assert_feed_readable(degraded):
    if degraded is None:
        raise ProspectiveRefused(
            f"{H_FEED_UNREADABLE}: the feed-session record could not be read. Unknown is not "
            "clean: without it every launch would be recorded as continuously observed")
    return degraded


def provenance_of(signature, degraded):
    """A launch first seen after a reconnect keeps that label for its whole life."""
    return PROVENANCE_AFTER_GAP if signature in degraded else PROVENANCE_CONTINUOUS


COVERAGE_STATEMENT = ("conditioned on OBSERVED launches; missed-launch incidence is not estimable "
                      "from this feed")


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS entry_schedule (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, mint TEXT, bonding_curve TEXT,
  t0_slot INTEGER NOT NULL, target_slot INTEGER NOT NULL, provenance TEXT NOT NULL,
  state TEXT NOT NULL, reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  context_slot INTEGER, lateness_slots INTEGER,
  virtual_quote INTEGER, virtual_token INTEGER, real_quote INTEGER, real_token INTEGER,
  quote_mint TEXT, mayhem_mode INTEGER, complete INTEGER,
  scheduled_at_wall_unix REAL NOT NULL, scheduled_at_slot INTEGER NOT NULL,
  PRIMARY KEY (signature, delay_slots));
CREATE INDEX IF NOT EXISTS entry_due ON entry_schedule(state, target_slot);
CREATE TABLE IF NOT EXISTS entry_cell (
  signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, scenario_id TEXT NOT NULL,
  provenance TEXT NOT NULL, target_slot INTEGER NOT NULL, context_slot INTEGER,
  state TEXT NOT NULL, reason TEXT,
  tokens_out INTEGER, execution_cost_lamports INTEGER, total_outlay_lamports INTEGER,
  fee_bps INTEGER, creator_fee_bps INTEGER, cashback_fee_bps INTEGER, buyback_fee_bps INTEGER,
  evidence_sha256 TEXT NOT NULL, priced_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (signature, delay_slots, scenario_id));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def eligible_launches(b15a_path=B15A_DB, activation_slot=None, limit=None):
    """Decoded launches STRICTLY after activation. The filter is in the query, not downstream."""
    connection = sqlite3.connect(f"file:{b15a_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT signature, slot, mint, bonding_curve FROM launch "
            "WHERE decode_status=? AND slot > ? AND bonding_curve IS NOT NULL "
            "ORDER BY launch_seq", (PILOT.DECODE_DECODED, activation_slot)).fetchall()
    finally:
        connection.close()
    return rows[:limit] if limit else rows


def schedule_entries(connection, launches, current_slot, degraded, document):
    """One durable row per (launch, delay). Prospective only: a passed target is refused."""
    scheduled = missed = 0
    for signature, t0_slot, mint, curve in launches:
        assert_after_activation(t0_slot, document["activation"]["activation_slot"])
        provenance = provenance_of(signature, degraded)
        for delay in document["entry_checkpoints"]["delays"]:
            target = entry_target_slot(t0_slot, delay)
            if target <= current_slot:
                # Gone before we could schedule it. Refused, never repaired from current state.
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO entry_schedule(signature,delay_slots,mint,"
                    "bonding_curve,t0_slot,target_slot,provenance,state,reason,"
                    "scheduled_at_wall_unix,scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (signature, delay, mint, curve, t0_slot, target, provenance, STATE_REFUSED,
                     H_TARGET_MISSED, time.time(), current_slot))
                missed += cursor.rowcount
                continue
            cursor = connection.execute(
                "INSERT OR IGNORE INTO entry_schedule(signature,delay_slots,mint,bonding_curve,"
                "t0_slot,target_slot,provenance,state,reason,scheduled_at_wall_unix,"
                "scheduled_at_slot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (signature, delay, mint, curve, t0_slot, target, provenance, STATE_PENDING, None,
                 time.time(), current_slot))
            scheduled += cursor.rowcount
    connection.commit()
    return scheduled, missed


def due_entries(connection, current_slot):
    return connection.execute(
        "SELECT signature, delay_slots, bonding_curve, target_slot, provenance "
        "FROM entry_schedule WHERE state=? AND target_slot <= ? ORDER BY target_slot",
        (STATE_PENDING, current_slot)).fetchall()


def matched_transaction(signature, b15b_path=B15B_DB):
    """B15b's exactly matching successful launch transaction, or None."""
    path = pathlib.Path(b15b_path)
    if not path.exists():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        row = connection.execute(
            "SELECT t.signature, t.missing_fields FROM t0_state t JOIN backfill b "
            "ON b.signature = t.signature WHERE t.signature=? AND b.status='retrieved'",
            (signature,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return row


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def run(limit=None, b15a_path=B15A_DB, b15b_path=B15B_DB, work_dir=WORK_DIR, opener=None,
        sleeper=time.sleep, url=None, slot_source=None, ticks=1):
    """Schedule from t0, checkpoint at the target, price three scenarios from one shared state."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    v1f = B15F.verify_preregistration()
    v2f = B15F.verify_preregistration_v2()
    activation = document["activation"]["activation_slot"]
    url = url or B15B.rpc_url()
    receipt = B15B.endpoint_receipt(url)
    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "prospective_entries.sqlite")
    exchanges = B15B.ExchangeLog(pathlib.Path(work_dir) / "rpc_exchanges.jsonl")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("activation_slot", activation), ("label", LABEL), ("executable", "0"),
                       ("endpoint_scheme_host", receipt),
                       ("coverage_statement", COVERAGE_STATEMENT),
                       ("execution_status", "never_executed"),
                       ("never_mixed_with_v1", "1")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = B15B.build_decoder()
    route = json.loads((ROOT / "research" / "B15D_SHADOW_ROUTE_PREREGISTRATION.json").read_text())
    scenarios = {s["scenario_id"]: s for s in route["cost_scenarios"]}
    order = route["materialization_rules"]["order"]
    counts = {"ticks": 0, "scheduled": 0, "missed_at_schedule": 0, "due": 0, "checkpointed": 0,
              "refused": 0, "cells_priced": 0, "activation_slot": activation}
    refusals = {}
    census = None
    try:
        for _tick in range(ticks):
            counts["ticks"] += 1
            degraded, census = launch_provenance(b15a_path)
            assert_feed_readable(degraded)
            slot = slot_source() if slot_source else B15F.current_slot(url, opener)
            launches = eligible_launches(b15a_path, activation, limit)
            scheduled, missed = schedule_entries(connection, launches, slot, degraded, document)
            counts["scheduled"] += scheduled
            counts["missed_at_schedule"] += missed
            due = due_entries(connection, slot)
            counts["due"] += len(due)
            if not due:
                continue
            batch, context, error = _fetch_batch(due, url, exchanges, opener, v2f)
            # Built once per tick from PRESERVED launch-transaction evidence, never from feed
            # history that a gap can truncate.
            schedules = fee_schedules_from_launch_transactions(
                {row[0] for row in due}, decoder)
            for signature, delay, curve, target, provenance in due:
                connection.execute(
                    "UPDATE entry_schedule SET attempts = attempts + 1 WHERE signature=? AND "
                    "delay_slots=?", (signature, delay))
                try:
                    if curve not in batch:
                        raise ProspectiveRefused(f"{H_NO_CHECKPOINT}: {error or 'no entry'}")
                    state, context_slot, lateness = B15F.read_account_from_batch(
                        batch[curve], curve, context, target, v1f, decoder)
                    match = matched_transaction(signature, b15b_path)
                    if match is None:
                        raise ProspectiveRefused(
                            f"{H_NO_MATCHING_TRANSACTION}: B15b has no retrieved launch "
                            "transaction for this signature")
                    if match[1] != "[]":
                        raise ProspectiveRefused(f"{H_INCOMPLETE_T0}: {match[1]}")
                    if state["complete"]:
                        raise ProspectiveRefused(f"{H_CURVE_COMPLETE}: complete at the entry target")
                except B15F.CheckpointRefused as error_:
                    code = str(error_).split(":", 1)[0]
                    code = H_CHECKPOINT_LATE if code == B15F.C_LATE else (
                        H_ACCOUNT_MISMATCH if code in (B15F.C_WRONG_OWNER, B15F.C_SCHEMA)
                        else code)
                    _refuse(connection, signature, delay, code, str(error_)[:200])
                    counts["refused"] += 1
                    refusals[code] = refusals.get(code, 0) + 1
                    continue
                connection.execute(
                    "UPDATE entry_schedule SET state=?, context_slot=?, lateness_slots=?, "
                    "virtual_quote=?, virtual_token=?, real_quote=?, real_token=?, quote_mint=?, "
                    "mayhem_mode=?, complete=? WHERE signature=? AND delay_slots=?",
                    (STATE_PRICED, context_slot, lateness, state["virtual_quote"],
                     state["virtual_token"], state["real_quote"], state["real_token"],
                     state["quote_mint"], int(state["mayhem_mode"]), int(state["complete"]),
                     signature, delay))
                counts["checkpointed"] += 1
                counts["cells_priced"] += _price_cells(
                    connection, signature, delay, provenance, target, context_slot, state,
                    scenarios, order, schedules.get(signature))
                connection.commit()
    finally:
        exchanges.close()
        connection.close()
    counts["refusals_by_code"] = dict(sorted(refusals.items()))
    counts["label"] = LABEL
    counts["coverage_census"] = census
    counts["coverage_statement"] = COVERAGE_STATEMENT
    counts["never_mixed_with_v1"] = True
    return counts


def _fetch_batch(due, url, exchanges, opener, v2f):
    curves = [row[2] for row in due if row[2]]
    batch, context, error = {}, None, None
    size = v2f["transport_v2"]["max_accounts_per_request"]
    for start in range(0, len(curves), size):
        outcome, payload, requested, _hash = B15F.fetch_accounts_batch(
            curves[start:start + size], url, exchanges, opener)
        if outcome != "retrieved":
            error = f"{B15F.C_RPC_EXHAUSTED}: {outcome}"
            continue
        try:
            mapped, context = B15F.map_batch(payload, requested)
        except B15F.CheckpointRefused as refusal:
            error = str(refusal)
            continue
        batch.update(mapped)
    return batch, context, error


def _price_cells(connection, signature, delay, provenance, target, context_slot, state,
                 scenarios, order, schedule):
    """Three scenarios from ONE shared account state. The chain knows nothing of our scenarios."""
    priced = 0
    for scenario_id, scenario in scenarios.items():
        cell_state, reason = STATE_REFUSED, None
        tokens = cost = outlay = None
        if schedule is None:
            reason = H_INCOMPLETE_T0
        else:
            policy = B15D.cost_policy(scenario)
            try:
                result = B10A.price_entry(state, {"side": "buy",
                                                  "quote_lamports": order["quote_lamports"]},
                                          schedule, policy)
                costs = result.get("execution_costs")
                if not isinstance(costs, dict) or "total" not in costs \
                        or "lamports_out_of_wallet" not in result:
                    reason = H_INCOMPLETE_T0
                else:
                    cell_state = STATE_PRICED
                    tokens = result["tokens_out"]
                    cost = costs["total"]
                    outlay = result["lamports_out_of_wallet"]
                    priced += 1
            except Exception as error:                                    # noqa: BLE001
                reason = f"{type(error).__name__}"
        record = {"signature": signature, "delay_slots": delay, "scenario_id": scenario_id,
                  "provenance": provenance, "target_slot": target, "context_slot": context_slot,
                  "state": cell_state, "reason": reason, "tokens_out": tokens,
                  "execution_cost_lamports": cost, "total_outlay_lamports": outlay}
        record.update(schedule or {"fee_bps": None, "creator_fee_bps": None,
                                   "cashback_fee_bps": None, "buyback_fee_bps": None})
        assert_no_float(record)
        assert_not_v1(record)
        connection.execute(
            "INSERT OR REPLACE INTO entry_cell(signature,delay_slots,scenario_id,provenance,"
            "target_slot,context_slot,state,reason,tokens_out,execution_cost_lamports,"
            "total_outlay_lamports,fee_bps,creator_fee_bps,cashback_fee_bps,buyback_fee_bps,"
            "evidence_sha256,priced_at_wall_unix) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (signature, delay, scenario_id, provenance, target, context_slot, cell_state, reason,
             tokens, cost, outlay, record["fee_bps"], record["creator_fee_bps"],
             record["cashback_fee_bps"], record["buyback_fee_bps"], evidence_hash(record),
             time.time()))
    return priced


def fee_schedules_from_launch_transactions(signatures, decoder,
                                           exchange_path=None):
    """Fee basis points per launch, from B15b's PRESERVED launch-transaction responses.

    Self-contained launch-transaction evidence, which is the whole point: the schedule comes from
    the transaction B15b proved, not from feed history a gap can truncate. One pass over the
    preserved exchange log builds the index; a signature absent from it has no schedule and its
    cells are refused rather than priced on an assumed one — B15c observed fee_basis_points taking
    more than one value in a single sample, so there is no safe constant.
    """
    path = (ROOT / "research" / "b15b" / "rpc_exchanges.jsonl") if exchange_path is None \
        else pathlib.Path(exchange_path)
    wanted = set(signatures)
    out = {}
    if not path.exists() or not wanted:
        return out
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    trade = next(bytes(e["discriminator"]).hex() for e in idl["events"]
                 if e["name"] == "TradeEvent")
    with path.open() as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            signature = record.get("signature")
            if signature not in wanted or signature in out:
                continue
            payload = record.get("response_json_or_error")
            if not isinstance(payload, dict):
                continue
            meta = ((payload.get("result") or {}).get("meta") or {})
            payloads, _skipped = PILOT.program_data_payloads(meta.get("logMessages") or [])
            for blob in payloads:
                body = blob[len(PILOT.EVENT_TAG):] \
                    if blob.startswith(PILOT.EVENT_TAG) else blob
                if len(body) < 8 or body[:8].hex() != trade:
                    continue
                try:
                    fields = decoder["b7d"].read_struct(
                        decoder["b7d"].Cursor(body[8:]), decoder["types"]["TradeEvent"],
                        decoder["types"])
                except Exception:                                         # noqa: BLE001
                    continue
                schedule = {"fee_bps": fields.get("fee_basis_points"),
                            "creator_fee_bps": fields.get("creator_fee_basis_points"),
                            "cashback_fee_bps": fields.get("cashback_fee_basis_points"),
                            "buyback_fee_bps": fields.get("buyback_fee_basis_points")}
                if any(value is None for value in schedule.values()):
                    continue
                out[signature] = schedule
                break
    return out


def _refuse(connection, signature, delay, code, detail):
    connection.execute(
        "UPDATE entry_schedule SET state=?, reason=? WHERE signature=? AND delay_slots=?",
        (STATE_REFUSED, f"{code}:{detail}"[:240], signature, delay))
    connection.commit()


def status(db_path=DB_PATH, b15a_path=B15A_DB):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        by_state = dict(connection.execute(
            "SELECT state, COUNT(*) FROM entry_schedule GROUP BY 1"))
        by_provenance = dict(connection.execute(
            "SELECT provenance, COUNT(*) FROM entry_schedule GROUP BY 1"))
        reasons = dict(connection.execute(
            "SELECT substr(reason,1,instr(reason||':',':')-1), COUNT(*) FROM entry_schedule "
            "WHERE reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8"))
        cells = dict(connection.execute("SELECT state, COUNT(*) FROM entry_cell GROUP BY 1"))
        lateness = [r[0] for r in connection.execute(
            "SELECT lateness_slots FROM entry_schedule WHERE lateness_slots IS NOT NULL "
            "ORDER BY 1")]
    finally:
        connection.close()
    _degraded, census = launch_provenance(b15a_path)
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "label": meta.get("label"),
        "executable": False,
        "activation_slot": int(meta.get("activation_slot", 0)),
        "schedule_by_state": by_state,
        "schedule_by_provenance": by_provenance,
        "entry_cells_by_state": cells,
        "top_reasons": reasons,
        "lateness_slots": B15B._summary(lateness),
        # Published BESIDE the counts, never beneath them: under a return it is a footnote, beside
        # it, it is a condition on reading the return at all.
        "coverage_census": census,
        "coverage_statement": COVERAGE_STATEMENT,
        "missed_launch_incidence": "not estimable from this feed",
        "never_mixed_with_v1": meta.get("never_mixed_with_v1") == "1",
        "no_retroactive_recovery": True,
        "figures_withheld_until_v2_slices_close": True,
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
            "activation_slot": document["activation"]["activation_slot"],
            "delays": document["entry_checkpoints"]["delays"],
            "no_retroactive_recovery": True,
            "coverage_statement": COVERAGE_STATEMENT,
            "label": LABEL, "executable": False,
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
