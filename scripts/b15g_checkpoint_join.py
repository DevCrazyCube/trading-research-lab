"""B15g — joins B15f prospective checkpoints to B15d priced entries and prices the exits.

Implements `research/B15G_CHECKPOINT_JOIN_PREREGISTRATION.json`, committed alone before any
checkpoint-derived return was read.

Offline and read-only: every input is already on disk. No credential, no network.

Three things it refuses to do, each of which would produce a plausible number:

- **It never prices an exit whose target precedes its entry.** B15d's actual entry is the first
  observation at or after `t0 + delay`, which can land after the nominal target. Selling then would
  be selling a position that had not been opened.
- **It never assumes a fee schedule.** The bonding-curve account publishes no basis points at all,
  so the schedule comes from the most recent TradeEvent at or before the target, and its absence is
  a refusal rather than a default.
- **It never publishes a sum over an unclosed slice.** A sum over the targets that have resolved so
  far is a sum over the fastest-resolving ones, which are not a random sample.

It also does not touch B15e. That is a separate population with a different target definition, and
a difference between the two would measure the definitions rather than anything about a strategy.
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

WORK_DIR = ROOT / "research" / "b15g"
DB_PATH = WORK_DIR / "checkpoint_join.sqlite"
B15A_RAW = ROOT / "research" / "b15a" / "raw_frames.jsonl"
B15D_DB = ROOT / "research" / "b15d" / "shadow_entries.sqlite"
B15F_DB = ROOT / "research" / "b15f" / "checkpoints.sqlite"

PREREG_PATH = ROOT / "research" / "B15G_CHECKPOINT_JOIN_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "39f93c7d62fef3de38d2f0febdc052bbf1cb3f871c6fcc22d91534008c0a3b67"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

TARGET_SEMANTICS = "nominal_t0_plus_delay_plus_horizon"
FORBIDDEN_TARGET_NAMES = ("b10c_state_in_force", "b15e_exit_semantics", "state_in_force",
                          "first_observation_at_or_after_entry")

J_ENTRY_NOT_BEFORE_TARGET = "J_ENTRY_NOT_BEFORE_TARGET"
J_SCENARIO_MISMATCH = "J_SCENARIO_MISMATCH"
J_IDENTITY_CONFLICT = "J_IDENTITY_CONFLICT"
J_NO_FEE_EVIDENCE = "J_NO_FEE_EVIDENCE"
J_COST_ABSENT = "J_COST_ABSENT"
J_CURVE_COMPLETE = "J_CURVE_COMPLETE"
J_LIQUIDITY_UNAVAILABLE = "J_LIQUIDITY_UNAVAILABLE"
J_CHECKPOINT_REFUSED = "J_CHECKPOINT_REFUSED"
J_DUPLICATE_JOIN = "J_DUPLICATE_JOIN"

STATE_PENDING = "pending"
STATE_PRICED = "priced"
STATE_ENTRY_UNPRICED = "checkpointed_entry_unpriced"
STATE_REFUSED = "refused"
STATE_CHECKPOINT_REFUSED = "checkpoint_refused"

LABEL = "SIMULATED_PROSPECTIVE_CHECKPOINT"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15F = _load("b15f_checkpoint", "b15f_checkpoint.py")
B15E, B15D, B15B, PILOT, B10A = B15F.B15E, B15F.B15D, B15F.B15B, B15F.PILOT, B15F.B10A


class JoinRefused(B15F.CheckpointRefused):
    """The join will not be made, and says why rather than resolving a conflict in someone's favour."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise JoinRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise JoinRefused(
            f"the join preregistration hashes {actual}, pinned {expected}. The population, the "
            "geometry and the maturity gate were frozen before any return was read, and a changed "
            "document is a different contract")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise JoinRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("b15a", "b15b", "b15c", "b15d", "b15e", "b15f", "b11a"):
        if f"research{os.sep}{marker}" in resolved:
            raise JoinRefused(
                f"{resolved} would write into research/{marker}; those are read-only evidence here")
    if not resolved.endswith(os.sep + "b15g"):
        raise JoinRefused(f"the work directory must be .../b15g, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    try:
        return B15F.assert_no_float(node, path)
    except B15F.CheckpointRefused as error:
        raise JoinRefused(str(error)) from error


def assert_target_semantics(label):
    """Every row says WHICH target rule it used. Three now exist in this project."""
    if label != TARGET_SEMANTICS:
        raise JoinRefused(
            f"target semantics {label!r} is not {TARGET_SEMANTICS!r}; a row that does not say "
            "which of this project's three target rules it used is a number waiting to be "
            "misfiled")
    # No second check against FORBIDDEN_TARGET_NAMES here: the comparison above already refuses
    # everything that is not TARGET_SEMANTICS, and TARGET_SEMANTICS is not one of the forbidden
    # names, so the branch could never fire. The list still earns its place as the documented
    # record of which other rules exist, and a test asserts each is refused through the check that
    # does fire.
    return True


# --------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------

def assert_entry_before_target(actual_entry_slot, nominal_target_slot):
    """The entry must be STRICTLY before the target.

    B15d's actual entry is the first observation at or after t0 + delay, which can land arbitrarily
    late — after the nominal target. Pricing an exit at a target that precedes the entry would sell
    a position that had not been opened.
    """
    if actual_entry_slot is None or nominal_target_slot is None:
        raise JoinRefused(f"{J_ENTRY_NOT_BEFORE_TARGET}: a slot is missing on one side")
    if actual_entry_slot >= nominal_target_slot:
        raise JoinRefused(
            f"{J_ENTRY_NOT_BEFORE_TARGET}: entry observed at {actual_entry_slot} is not before "
            f"the nominal target {nominal_target_slot}; that would sell a position never opened")
    return nominal_target_slot - actual_entry_slot


def assert_scenarios_match(entry_scenario, exit_scenario):
    if entry_scenario != exit_scenario:
        raise JoinRefused(f"{J_SCENARIO_MISMATCH}: {entry_scenario!r} vs {exit_scenario!r}")
    return True


# --------------------------------------------------------------------------------------------
# Fee schedule — from evidence at or before the target, never assumed
# --------------------------------------------------------------------------------------------

def fee_schedule_at_or_before(observations, target_slot):
    """The basis points in force at or before the target, from the last TradeEvent that published
    them.

    The bonding-curve ACCOUNT carries no fee fields at all, so a checkpoint alone cannot supply a
    schedule. Nothing after the target is read, and an absent schedule is a refusal — B15c saw
    fee_basis_points take more than one value in a single sample, so there is no safe constant to
    fall back on.
    """
    best = None
    for observation in observations:
        if observation["slot"] is None or observation["slot"] > target_slot:
            continue
        fields = observation["fields"]
        if fields.get("fee_basis_points") is None:
            continue
        best = observation
    if best is None:
        raise JoinRefused(
            f"{J_NO_FEE_EVIDENCE}: no TradeEvent at or before slot {target_slot} publishes a fee "
            "schedule for this curve, and one is not assumed")
    fields = best["fields"]
    schedule = {"fee_bps": fields.get("fee_basis_points"),
                "creator_fee_bps": fields.get("creator_fee_basis_points"),
                "cashback_fee_bps": fields.get("cashback_fee_basis_points"),
                "buyback_fee_bps": fields.get("buyback_fee_basis_points")}
    missing = [name for name, value in schedule.items() if value is None]
    if missing:
        raise JoinRefused(f"{J_NO_FEE_EVIDENCE}: the schedule does not publish {missing}")
    return schedule, best["slot"]


def cost_policy(scenario):
    for field in ("base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                  "ata_rent_lamports", "failed_attempts"):
        if field not in scenario:
            raise JoinRefused(f"{J_COST_ABSENT}: the scenario does not state {field}")
        if isinstance(scenario[field], bool) or not isinstance(scenario[field], int):
            raise JoinRefused(f"{J_COST_ABSENT}: {field} is not an exact integer")
    return {field: scenario[field] for field in
            ("base_fee_lamports", "priority_fee_lamports", "tip_lamports", "ata_rent_lamports",
             "failed_attempts")}


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS joined (
  entry_signature TEXT NOT NULL, delay_slots INTEGER NOT NULL, horizon TEXT NOT NULL,
  scenario_id TEXT NOT NULL, mint TEXT,
  target_semantics TEXT NOT NULL,
  nominal_target_slot INTEGER NOT NULL, actual_entry_observation_slot INTEGER,
  checkpoint_context_slot INTEGER, checkpoint_lateness_slots INTEGER,
  effective_hold_slots INTEGER,
  state TEXT NOT NULL, reason TEXT,
  tokens_held INTEGER, entry_outlay_lamports INTEGER,
  exit_proceeds_lamports INTEGER, exit_execution_cost_lamports INTEGER,
  net_return_lamports INTEGER,
  fee_bps INTEGER, creator_fee_bps INTEGER, cashback_fee_bps INTEGER, buyback_fee_bps INTEGER,
  fee_schedule_slot INTEGER,
  evidence_sha256 TEXT NOT NULL, joined_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (entry_signature, delay_slots, horizon, scenario_id));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def prospective_targets(b15f_path=B15F_DB, limit=None):
    """ONLY prospectively scheduled targets. C_PRE_CHECKPOINT_PROTOCOL rows are excluded here."""
    connection = sqlite3.connect(f"file:{b15f_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT s.entry_signature, s.delay_slots, s.horizon, s.mint, s.t0_slot, "
            "s.target_slot, s.state, s.reason, c.context_slot, c.lateness_slots, "
            "c.virtual_quote, c.virtual_token, c.real_quote, c.real_token, c.quote_mint, "
            "c.mayhem_mode, c.complete "
            "FROM schedule s LEFT JOIN checkpoint c "
            "  ON c.entry_signature = s.entry_signature AND c.delay_slots = s.delay_slots "
            "  AND c.horizon = s.horizon "
            "WHERE s.state != ? ORDER BY s.target_slot",
            (B15F.STATE_NOT_SCHEDULED,)).fetchall()
    finally:
        connection.close()
    return rows[:limit] if limit else rows


def entry_cells(b15d_path=B15D_DB):
    """B15d priced cells, keyed for an exact join. A duplicate key is a refusal, not a pick."""
    connection = sqlite3.connect(f"file:{b15d_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT signature, delay_slots, scenario_id, observation_slot, status, tokens_out, "
            "total_outlay_lamports FROM candidate").fetchall()
    finally:
        connection.close()
    out = {}
    duplicates = set()
    for signature, delay, scenario, slot, status, tokens, outlay in rows:
        key = (signature, delay, scenario)
        if key in out:
            duplicates.add(key)
        out[key] = {"observation_slot": slot, "status": status, "tokens": tokens,
                    "outlay": outlay}
    return out, duplicates


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def run(limit=None, raw_path=B15A_RAW, b15d_path=B15D_DB, b15f_path=B15F_DB, work_dir=WORK_DIR):
    """Join, check the geometry, price what may be priced, and preserve everything else."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    route = json.loads((ROOT / "research" / "B15E_SHADOW_PATH_PREREGISTRATION.json").read_text())
    scenarios = {s["scenario_id"]: s for s in route["exit_cost_scenarios"]}

    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "checkpoint_join.sqlite")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("label", LABEL), ("executable", "0"),
                       ("target_semantics", TARGET_SEMANTICS),
                       ("market_impact", "unmeasured"),
                       ("landing_probability", "unmeasured"),
                       ("never_mixed_with_b15e", "1"),
                       ("execution_status", "never_executed")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    targets = prospective_targets(b15f_path, limit)
    entries, duplicate_keys = entry_cells(b15d_path)
    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    trade = next(bytes(e["discriminator"]).hex() for e in idl["events"]
                 if e["name"] == "TradeEvent")
    mints = {row[3] for row in targets if row[3]}
    floors = {}
    for row in targets:
        if row[3] and row[4] is not None:
            floors[row[3]] = min(floors.get(row[3], row[4]), row[4])
    index = B15D.observations_by_mint(raw_path, mints, decoder, trade, floors) if mints else {}

    counts = {"targets": len(targets), "scenarios": len(scenarios)}
    by_state = {}
    by_reason = {}
    for row in targets:
        (signature, delay, horizon, mint, _t0, target, schedule_state, schedule_reason,
         context_slot, lateness, vq, vt, rq, rt, quote_mint, mayhem, complete) = row
        for scenario_id, scenario in scenarios.items():
            record = _join_one(document, scenario_id, scenario, signature, delay, horizon, mint,
                               target, schedule_state, schedule_reason, context_slot, lateness,
                               (vq, vt, rq, rt, quote_mint, mayhem, complete), entries,
                               duplicate_keys, index.get(mint, []))
            by_state[record["state"]] = by_state.get(record["state"], 0) + 1
            if record["reason"]:
                code = record["reason"].split(":", 1)[0]
                by_reason[code] = by_reason.get(code, 0) + 1
            _insert(connection, record)
        connection.commit()
    connection.close()
    counts["by_state"] = dict(sorted(by_state.items()))
    counts["by_reason"] = dict(sorted(by_reason.items()))
    counts["label"] = LABEL
    counts["target_semantics"] = TARGET_SEMANTICS
    counts["never_mixed_with_b15e"] = True
    counts["market_impact"] = "unmeasured"
    counts["landing_probability"] = "unmeasured"
    return counts


def _join_one(document, scenario_id, scenario, signature, delay, horizon, mint, target,
              schedule_state, schedule_reason, context_slot, lateness, state_tuple, entries,
              duplicate_keys, observations):
    base = {"entry_signature": signature, "delay_slots": delay, "horizon": horizon,
            "scenario_id": scenario_id, "mint": mint, "target_semantics": TARGET_SEMANTICS,
            "nominal_target_slot": target, "actual_entry_observation_slot": None,
            "checkpoint_context_slot": context_slot, "checkpoint_lateness_slots": lateness,
            "effective_hold_slots": None, "tokens_held": None, "entry_outlay_lamports": None,
            "exit_proceeds_lamports": None, "exit_execution_cost_lamports": None,
            "net_return_lamports": None, "fee_bps": None, "creator_fee_bps": None,
            "cashback_fee_bps": None, "buyback_fee_bps": None, "fee_schedule_slot": None}
    assert_target_semantics(base["target_semantics"])

    if schedule_state == B15F.STATE_SCHEDULED:
        return _finish(dict(base, state=STATE_PENDING, reason=None))
    if schedule_state == B15F.STATE_REFUSED:
        # B15f's own code carried through unchanged rather than reclassified.
        return _finish(dict(base, state=STATE_CHECKPOINT_REFUSED,
                            reason=f"{J_CHECKPOINT_REFUSED}:{(schedule_reason or '')[:120]}"))

    key = (signature, delay, scenario_id)
    if key in duplicate_keys:
        return _finish(dict(base, state=STATE_REFUSED, reason=J_DUPLICATE_JOIN))
    entry = entries.get(key)
    if entry is None or entry["status"] != B15D.STATUS_PRICED:
        return _finish(dict(base, state=STATE_ENTRY_UNPRICED, reason=None))

    base["actual_entry_observation_slot"] = entry["observation_slot"]
    base["tokens_held"] = entry["tokens"]
    base["entry_outlay_lamports"] = entry["outlay"]
    try:
        base["effective_hold_slots"] = assert_entry_before_target(entry["observation_slot"],
                                                                  target)
        assert_scenarios_match(scenario_id, scenario["scenario_id"])
        vq, vt, rq, rt, quote_mint, mayhem, complete = state_tuple
        if vq is None:
            raise JoinRefused(f"{J_IDENTITY_CONFLICT}: the checkpoint carries no state")
        if complete:
            raise JoinRefused(f"{J_CURVE_COMPLETE}: the curve is complete at the target")
        schedule, schedule_slot = fee_schedule_at_or_before(observations, target)
        base.update(schedule)
        base["fee_schedule_slot"] = schedule_slot
        policy = cost_policy(scenario)
        state = {"virtual_quote": vq, "virtual_token": vt, "real_quote": rq, "real_token": rt,
                 "quote_mint": quote_mint, "mayhem_mode": bool(mayhem), "complete": False,
                 "slot": target}
        result = B10A.price_exit(state, entry["tokens"], schedule, policy)
        costs = result.get("execution_costs")
        if result.get("quote_lamports") is None or not isinstance(costs, dict) \
                or "total" not in costs:
            raise JoinRefused(f"{J_COST_ABSENT}: the pricing result carries no cost structure")
        proceeds, cost = result["quote_lamports"], costs["total"]
        return _finish(dict(base, state=STATE_PRICED, reason=None,
                            exit_proceeds_lamports=proceeds,
                            exit_execution_cost_lamports=cost,
                            net_return_lamports=proceeds - entry["outlay"] - cost))
    except JoinRefused as error:
        return _finish(dict(base, state=STATE_REFUSED, reason=str(error)[:200]))
    except Exception as error:                                            # noqa: BLE001
        return _finish(dict(base, state=STATE_REFUSED,
                            reason=f"{J_LIQUIDITY_UNAVAILABLE}:{type(error).__name__}"))


def _finish(record):
    record["evidence_sha256"] = evidence_hash(record)
    record["joined_at_wall_unix"] = time.time()
    assert_no_float({k: v for k, v in record.items() if k != "joined_at_wall_unix"})
    return record


def _insert(connection, record):
    columns = ("entry_signature", "delay_slots", "horizon", "scenario_id", "mint",
               "target_semantics", "nominal_target_slot", "actual_entry_observation_slot",
               "checkpoint_context_slot", "checkpoint_lateness_slots", "effective_hold_slots",
               "state", "reason", "tokens_held", "entry_outlay_lamports",
               "exit_proceeds_lamports", "exit_execution_cost_lamports", "net_return_lamports",
               "fee_bps", "creator_fee_bps", "cashback_fee_bps", "buyback_fee_bps",
               "fee_schedule_slot", "evidence_sha256", "joined_at_wall_unix")
    connection.execute(
        f"INSERT OR REPLACE INTO joined({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})", [record.get(name) for name in columns])


def slice_closure(connection):
    """A (scenario, horizon) slice is closed only when nothing in it is still pending."""
    out = {}
    for scenario, horizon, state, count in connection.execute(
            "SELECT scenario_id, horizon, state, COUNT(*) FROM joined GROUP BY 1,2,3"):
        entry = out.setdefault(f"{scenario}/{horizon}", {"states": {}, "closed": None})
        entry["states"][state] = count
    for name, entry in out.items():
        entry["closed"] = entry["states"].get(STATE_PENDING, 0) == 0
        entry["total"] = sum(entry["states"].values())
    return out


def status(db_path=DB_PATH):
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        by_state = dict(connection.execute("SELECT state, COUNT(*) FROM joined GROUP BY 1"))
        reasons = dict(connection.execute(
            "SELECT substr(reason, 1, instr(reason||':',':')-1), COUNT(*) FROM joined "
            "WHERE reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10"))
        slices = slice_closure(connection)
        holds = [r[0] for r in connection.execute(
            "SELECT effective_hold_slots FROM joined WHERE effective_hold_slots IS NOT NULL "
            "ORDER BY effective_hold_slots")]
        lateness = [r[0] for r in connection.execute(
            "SELECT checkpoint_lateness_slots FROM joined "
            "WHERE checkpoint_lateness_slots IS NOT NULL ORDER BY 1")]
        figures = {}
        for name, entry in slices.items():
            if not entry["closed"]:
                continue
            scenario, horizon = name.split("/", 1)
            row = connection.execute(
                "SELECT COUNT(*), SUM(net_return_lamports), MIN(net_return_lamports) FROM joined "
                "WHERE scenario_id=? AND horizon=? AND state=?",
                (scenario, horizon, STATE_PRICED)).fetchone()
            if row[0]:
                figures[name] = {"priced_cells": row[0], "net_return_lamports_sum": row[1],
                                 "worst_cell_net_return_lamports": row[2],
                                 "denominator": entry["total"]}
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "label": meta.get("label"),
        "executable": False,
        "target_semantics": meta.get("target_semantics"),
        "never_mixed_with_b15e": meta.get("never_mixed_with_b15e") == "1",
        "market_impact": meta.get("market_impact"),
        "landing_probability": meta.get("landing_probability"),
        "execution_status": meta.get("execution_status"),
        "by_state": by_state,
        "top_reasons": reasons,
        "slices": slices,
        "closed_slices": sum(1 for entry in slices.values() if entry["closed"]),
        "effective_hold_slots": B15B._summary(holds),
        "checkpoint_lateness_slots": B15B._summary(lateness),
        "figures_for_closed_slices_only": figures or None,
        "interim_sums_never_published": True,
    }
    PILOT.assert_redacted(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", action="store_true")
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
            "target_semantics": TARGET_SEMANTICS,
            "population": "prospectively scheduled B15f targets only",
            "never_mixed_with_b15e": True,
            "label": LABEL, "executable": False,
            "market_impact": "unmeasured", "landing_probability": "unmeasured",
        }, indent=2, sort_keys=True))
        return 0
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return 0
    if args.run:
        print(json.dumps(run(limit=args.limit), indent=2, sort_keys=True))
        return 0
    parser.error("nothing to do; --contract, --status or --run")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PILOT.PilotRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
