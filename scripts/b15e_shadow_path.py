"""B15e — shadow position paths and frozen exits. Offline, read-only, and impact-blind by nature.

Implements `research/B15E_SHADOW_PATH_PREREGISTRATION.json`, committed alone before any later
return was inspected and before any exit was priced.

For each PRICED B15d entry cell it builds the canonical observed path of later TradeEvents on the
same mint, selects an exit at each frozen horizon, and prices it through B10a under the SAME
scenario the entry used.

**SIMULATED_OBSERVED_PATH.** Every later state here comes from a world in which our hypothetical
trade never happened. A real 0.1 SOL buy would have moved the reserves that every one of those
observations reports, so every exit is priced against a curve our entry never touched. Our market
impact is unmeasured, landing probability is unmeasured, and this is not a backtest of a strategy
that traded.

Two rules that are easy to get subtly wrong, so they are stated where they are implemented:

- **The horizon rule is B10b's EXIT rule, not B11b's B10c state-in-force marking.** First canonical
  observation at or AFTER the target, because a sale cannot happen at a price that already passed.
  Figures here are not comparable to B11b's labels.
- **A censored cell is never a loss.** It is excluded from the primary basis and counted, with a
  whole-cohort worst-case published separately.
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

WORK_DIR = ROOT / "research" / "b15e"
DB_PATH = WORK_DIR / "shadow_paths.sqlite"
B15A_RAW = ROOT / "research" / "b15a" / "raw_frames.jsonl"
B15D_DB = ROOT / "research" / "b15d" / "shadow_entries.sqlite"

PREREG_PATH = ROOT / "research" / "B15E_SHADOW_PATH_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "33b94fea408ae36db3bfbfc438b404ed4f8d9d6b983b396a00228b6b1e8a18e5"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

E01_NO_OBSERVATION = "E01_no_observation_at_horizon"
E02_CURVE_COMPLETE = "E02_curve_complete"
E03_MIGRATED = "E03_migrated"
E04_INCOMPLETE_STATE = "E04_incomplete_state"
E05_LIQUIDITY_UNAVAILABLE = "E05_liquidity_unavailable"
E06_ENTRY_NOT_PRICED = "E06_entry_not_priced"
E07_UNKNOWN_EVENT = "E07_unknown_event"
E08_SESSION_GAP = "E08_session_gap"

STATUS_EXITED = "exited"
STATUS_CENSORED = "right_censored"
STATUS_UNAVAILABLE = "unavailable"

LABEL = "SIMULATED_OBSERVED_PATH"

HORIZON_SLOTS = {"h_1000_slots": 1000, "h_10000_slots": 10000}
HORIZON_OBSERVATIONS = {"h_10_observations": 10}
HORIZON_ADMINISTRATIVE = "administrative_window_end"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15D = _load("b15d_shadow_entry", "b15d_shadow_entry.py")
B15B = B15D.B15B
PILOT = B15D.PILOT
B10A = B15D.B10A


class ShadowPathRefused(B15D.ShadowEntryRefused):
    """The materializer will not price this exit, and says why rather than approximating."""


# --------------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------------

def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise ShadowPathRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ShadowPathRefused(
            f"the path preregistration hashes {actual}, pinned {expected}. The horizon rule, the "
            "exit costs and the censoring rule were frozen before any return was inspected, and a "
            "changed document is a different protocol")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    body = path.read_text().split("EXECUTION_SURFACE_TOKENS = (", 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise ShadowPathRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_isolated(work_dir=WORK_DIR):
    resolved = str(pathlib.Path(work_dir).resolve())
    for marker in ("research/b15a", "research/b15b", "research/b15c", "research/b15d",
                   "research/b11a"):
        if marker.replace("/", os.sep) in resolved:
            raise ShadowPathRefused(
                f"{resolved} would write into {marker!r}; those are read-only evidence here")
    if not resolved.endswith(os.sep + "b15e"):
        raise ShadowPathRefused(f"the work directory must be .../b15e, got {resolved}")
    return True


def assert_no_float(node, path="$"):
    try:
        return B15D.assert_no_float(node, path)
    except B15D.ShadowEntryRefused as error:
        raise ShadowPathRefused(str(error)) from error


def assert_scenarios_not_mixed(entry_scenario, exit_scenario):
    """An entry is always paired with its own scenario's exit.

    Pairing an optimistic entry with a stressed exit produces a figure that describes no coherent
    world, and it flatters or damns arbitrarily depending on which way the mismatch happens to run.
    """
    if entry_scenario != exit_scenario:
        raise ShadowPathRefused(
            f"entry scenario {entry_scenario!r} paired with exit scenario {exit_scenario!r}; a "
            "mixed pair describes no coherent world")
    return True


# --------------------------------------------------------------------------------------------
# Horizon selection — B10b EXIT rule, named
# --------------------------------------------------------------------------------------------

def select_exit(path, entry_slot, horizon):
    """The exit observation for one horizon, or None with a reason.

    B10b slot_horizon EXIT semantics: the FIRST canonical observation at or AFTER the target. NOT
    B11b's B10c state-in-force marking, which takes the LAST at or BEFORE it. A sale cannot happen
    at a price that already passed, and the two rules give different numbers.
    """
    if horizon in HORIZON_SLOTS:
        target = entry_slot + HORIZON_SLOTS[horizon]
        for observation in path:
            if observation["slot"] is not None and observation["slot"] >= target:
                return observation, None
        return None, E01_NO_OBSERVATION
    if horizon in HORIZON_OBSERVATIONS:
        needed = HORIZON_OBSERVATIONS[horizon]
        if len(path) < needed:
            return None, E01_NO_OBSERVATION
        return path[needed - 1], None
    if horizon == HORIZON_ADMINISTRATIVE:
        if not path:
            return None, E01_NO_OBSERVATION
        return path[-1], None
    raise ShadowPathRefused(f"{horizon!r} is not a frozen horizon identifier")


def state_from(observation):
    """The curve state an observation publishes, or None if it does not publish all of it."""
    fields = observation["fields"]
    state = {
        "virtual_quote": fields.get("virtual_quote_reserves", fields.get("virtual_sol_reserves")),
        "virtual_token": fields.get("virtual_token_reserves"),
        "real_quote": fields.get("real_quote_reserves", fields.get("real_sol_reserves")),
        "real_token": fields.get("real_token_reserves"),
        "quote_mint": fields.get("quote_mint"),
        "mayhem_mode": bool(fields.get("mayhem_mode")),
        "complete": False,
        "slot": observation["slot"],
    }
    if any(state[key] is None for key in
           ("virtual_quote", "virtual_token", "real_quote", "real_token", "quote_mint")):
        return None
    return state


def maximum_drawdown(path_values):
    """Largest peak-to-trough fall along the path, in lamports, exactly.

    On the PATH, not the endpoints: a position that ended flat after losing four fifths of its
    value is not the same risk as one that never moved.
    """
    if not path_values:
        return None
    peak = path_values[0]
    worst = 0
    for value in path_values:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def evidence_hash(record):
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS position (
  entry_signature TEXT NOT NULL, scenario_id TEXT NOT NULL, delay_slots INTEGER NOT NULL,
  horizon TEXT NOT NULL, mint TEXT, entry_slot INTEGER, entry_status TEXT NOT NULL,
  exit_slot INTEGER, exit_signature TEXT, status TEXT NOT NULL, reason TEXT,
  tokens_held INTEGER, entry_outlay_lamports INTEGER,
  exit_proceeds_lamports INTEGER, exit_execution_cost_lamports INTEGER,
  net_return_lamports INTEGER, max_drawdown_lamports INTEGER,
  path_observations INTEGER NOT NULL, mature INTEGER NOT NULL,
  evidence_sha256 TEXT NOT NULL, materialized_at_wall_unix REAL NOT NULL,
  PRIMARY KEY (entry_signature, scenario_id, delay_slots, horizon));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_database(path=DB_PATH):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def entry_cells(b15d_path=B15D_DB, limit=None):
    """EVERY B15d cell, priced or not. Refused and stale cells stay in the denominator."""
    connection = sqlite3.connect(f"file:{b15d_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT signature, scenario_id, delay_slots, mint, observation_slot, status, "
            "tokens_out, total_outlay_lamports FROM candidate "
            "ORDER BY t0_slot, signature, scenario_id, delay_slots").fetchall()
    finally:
        connection.close()
    return rows[:limit] if limit else rows


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------

def run(limit=None, raw_path=B15A_RAW, b15d_path=B15D_DB, work_dir=WORK_DIR):
    """Materialize every (cell x horizon). Structural counts always; figures only when mature."""
    assert_no_execution_surface()
    assert_isolated(work_dir)
    document = verify_preregistration()
    horizons = document["horizon_rule"]["identifiers"]
    exit_scenarios = {s["scenario_id"]: s for s in document["exit_cost_scenarios"]}

    pathlib.Path(work_dir).mkdir(parents=True, exist_ok=True)
    connection = open_database(pathlib.Path(work_dir) / "shadow_paths.sqlite")
    for key, value in (("schema_version", SCHEMA_VERSION),
                       ("preregistration_id", document["preregistration_id"]),
                       ("preregistration_canonical_sha256", PREREG_CANONICAL_SHA256),
                       ("label", LABEL), ("executable", "0"),
                       ("market_impact", "unmeasured"),
                       ("landing_probability", "unmeasured"),
                       ("horizon_rule", "b10b_exit_first_at_or_after"),
                       ("not_b10c_state_in_force", "1"),
                       ("execution_status", "never_executed"),
                       ("performance_status", "not_evaluated")):
        connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, str(value)))
    connection.commit()

    decoder = B15B.build_decoder()
    idl = json.loads((ROOT / "research" / "pump_idl_9c82f61.json").read_text())
    trade = next(bytes(e["discriminator"]).hex() for e in idl["events"]
                 if e["name"] == "TradeEvent")
    cells = entry_cells(b15d_path, limit)
    # One pass over the raw log for every mint at once, floored at each curve's own entry slot.
    floors = {}
    for _sig, _scenario, _delay, mint, entry_slot, status, _tokens, _outlay in cells:
        if mint and entry_slot is not None:
            floors[mint] = min(floors.get(mint, entry_slot), entry_slot)
    index = B15D.observations_by_mint(raw_path, set(floors), decoder, trade, floors)

    counts = {"cells": 0, "horizons": len(horizons)}
    by_status = {}
    by_reason = {}
    mature_count = 0
    for signature, scenario, delay, mint, entry_slot, entry_status, tokens, outlay in cells:
        path_all = index.get(mint, [])
        # STRICTLY after the entry observation. No observation at or before entry may enter a path.
        path = [o for o in path_all if o["slot"] is not None and entry_slot is not None
                and o["slot"] > entry_slot]
        for horizon in horizons:
            counts["cells"] += 1
            row = _materialize(document, exit_scenarios, signature, scenario, delay, mint,
                               entry_slot, entry_status, tokens, outlay, path, horizon)
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            if row["reason"]:
                by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
            mature_count += row["mature"]
            _insert(connection, row)
        connection.commit()
    connection.close()
    counts["by_status"] = dict(sorted(by_status.items()))
    counts["by_reason"] = dict(sorted(by_reason.items()))
    counts["mature_cells"] = mature_count
    counts["label"] = LABEL
    counts["horizon_rule"] = "b10b_exit_first_at_or_after (NOT b10c state_in_force)"
    counts["market_impact"] = "unmeasured"
    counts["landing_probability"] = "unmeasured"
    counts["no_aggregation_across_scenarios"] = True
    return counts


def _materialize(document, exit_scenarios, signature, scenario, delay, mint, entry_slot,
                 entry_status, tokens, outlay, path, horizon):
    base = {"entry_signature": signature, "scenario_id": scenario, "delay_slots": delay,
            "horizon": horizon, "mint": mint, "entry_slot": entry_slot,
            "entry_status": entry_status, "exit_slot": None, "exit_signature": None,
            "tokens_held": tokens, "entry_outlay_lamports": outlay,
            "exit_proceeds_lamports": None, "exit_execution_cost_lamports": None,
            "net_return_lamports": None, "max_drawdown_lamports": None,
            "path_observations": len(path), "mature": 0}

    if entry_status != B15D.STATUS_PRICED:
        # Kept in the denominator, with its own reason. Dropping it would narrow the cohort to the
        # cells that produced a number.
        return _finish(dict(base, status=STATUS_UNAVAILABLE, reason=E06_ENTRY_NOT_PRICED,
                            mature=1))

    observation, reason = select_exit(path, entry_slot, horizon)
    if observation is None:
        return _finish(dict(base, status=STATUS_CENSORED, reason=reason, mature=0))

    state = state_from(observation)
    if state is None:
        return _finish(dict(base, status=STATUS_UNAVAILABLE, reason=E04_INCOMPLETE_STATE,
                            mature=1))

    exit_scenario = exit_scenarios[scenario]
    assert_scenarios_not_mixed(scenario, exit_scenario["scenario_id"])
    policy = {field: exit_scenario[field] for field in
              ("base_fee_lamports", "priority_fee_lamports", "tip_lamports", "ata_rent_lamports",
               "failed_attempts")}
    try:
        schedule = B15D.fee_schedule_from(observation)
    except B15D.ShadowEntryRefused:
        return _finish(dict(base, status=STATUS_UNAVAILABLE, reason=E04_INCOMPLETE_STATE,
                            mature=1))
    try:
        result = B10A.price_exit(state, tokens, schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        return _finish(dict(base, status=STATUS_UNAVAILABLE,
                            reason=f"{E05_LIQUIDITY_UNAVAILABLE}:{type(error).__name__}",
                            mature=1, exit_slot=observation["slot"],
                            exit_signature=observation["signature"]))
    if result.get("status") == getattr(B10A, "STATUS_EXIT_UNAVAILABLE", "exit_unavailable"):
        liquidity = result.get("liquidity")
        reason = (E02_CURVE_COMPLETE
                  if liquidity == getattr(B10A, "L3_CURVE_COMPLETE", None)
                  else f"{E05_LIQUIDITY_UNAVAILABLE}:{liquidity}")
        return _finish(dict(base, status=STATUS_UNAVAILABLE, reason=reason, mature=1,
                            exit_slot=observation["slot"],
                            exit_signature=observation["signature"]))

    proceeds = result.get("quote_lamports")
    costs = result.get("execution_costs")
    if proceeds is None or not isinstance(costs, dict) or "total" not in costs:
        # A missing cost structure is not a cost of zero. The same idiom that priced 5,352 entry
        # cells as free in B15d is refused here rather than summed.
        raise ShadowPathRefused(
            "the exit pricing result carries no proceeds or no execution_costs.total; a missing "
            "cost structure is not a cost of zero")
    exit_cost = costs["total"]
    net = proceeds - outlay - exit_cost
    # Drawdown along the path in lamports, marked at each observation up to and including the exit.
    marks = []
    for step in path:
        if step["slot"] is not None and step["slot"] > observation["slot"]:
            break
        step_state = state_from(step)
        if step_state is None:
            continue
        try:
            mark = B10A.price_exit(step_state, tokens, B15D.fee_schedule_from(step), policy)
        except Exception:                                                 # noqa: BLE001
            continue
        if mark.get("quote_lamports") is not None:
            marks.append(mark["quote_lamports"])
    return _finish(dict(base, status=STATUS_EXITED, reason=None, mature=1,
                        exit_slot=observation["slot"], exit_signature=observation["signature"],
                        exit_proceeds_lamports=proceeds, exit_execution_cost_lamports=exit_cost,
                        net_return_lamports=net, max_drawdown_lamports=maximum_drawdown(marks)))


def _finish(row):
    row["evidence_sha256"] = evidence_hash(row)
    row["materialized_at_wall_unix"] = time.time()
    assert_no_float({k: v for k, v in row.items() if k != "materialized_at_wall_unix"})
    return row


def _insert(connection, row):
    columns = ("entry_signature", "scenario_id", "delay_slots", "horizon", "mint", "entry_slot",
               "entry_status", "exit_slot", "exit_signature", "status", "reason", "tokens_held",
               "entry_outlay_lamports", "exit_proceeds_lamports", "exit_execution_cost_lamports",
               "net_return_lamports", "max_drawdown_lamports", "path_observations", "mature",
               "evidence_sha256", "materialized_at_wall_unix")
    connection.execute(
        f"INSERT OR REPLACE INTO position({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})", [row.get(name) for name in columns])


def status(db_path=DB_PATH, include_figures=None):
    """Structural counts always. Figures only when the cohort is complete for that cell group."""
    if not pathlib.Path(db_path).exists():
        return {"schema_version": SCHEMA_VERSION, "state": "not_started"}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        meta = dict(connection.execute("SELECT key, value FROM metadata"))
        by_status = dict(connection.execute(
            "SELECT status, COUNT(*) FROM position GROUP BY 1"))
        by_reason = dict(connection.execute(
            "SELECT COALESCE(reason,'none'), COUNT(*) FROM position GROUP BY 1 "
            "ORDER BY 2 DESC LIMIT 10"))
        by_horizon = {}
        for horizon, state, count in connection.execute(
                "SELECT horizon, status, COUNT(*) FROM position GROUP BY 1,2 ORDER BY 1,2"):
            by_horizon.setdefault(horizon, {})[state] = count
        total, mature = connection.execute(
            "SELECT COUNT(*), SUM(mature) FROM position").fetchone()
        exited = connection.execute(
            "SELECT COUNT(*) FROM position WHERE status=?", (STATUS_EXITED,)).fetchone()[0]
        censored = connection.execute(
            "SELECT COUNT(*) FROM position WHERE status=?", (STATUS_CENSORED,)).fetchone()[0]
        figures = None
        cohort_complete = bool(total) and censored == 0
        if include_figures is None:
            include_figures = cohort_complete
        if include_figures and exited:
            figures = {}
            for scenario, horizon, count, total_net, worst in connection.execute(
                    "SELECT scenario_id, horizon, COUNT(*), SUM(net_return_lamports), "
                    "MIN(net_return_lamports) FROM position WHERE status=? "
                    "GROUP BY 1,2 ORDER BY 1,2", (STATUS_EXITED,)):
                figures[f"{scenario}/{horizon}"] = {
                    "exited_cells": count, "net_return_lamports_sum": total_net,
                    "worst_cell_net_return_lamports": worst}
    finally:
        connection.close()
    report = {
        "schema_version": SCHEMA_VERSION,
        "preregistration_id": meta.get("preregistration_id"),
        "label": meta.get("label"),
        "executable": False,
        "horizon_rule": meta.get("horizon_rule"),
        "not_b10c_state_in_force": meta.get("not_b10c_state_in_force") == "1",
        "market_impact": meta.get("market_impact"),
        "landing_probability": meta.get("landing_probability"),
        "execution_status": meta.get("execution_status"),
        "performance_status": meta.get("performance_status"),
        "cells": total,
        "mature_cells": mature or 0,
        "cohort_complete": cohort_complete,
        "by_status": by_status,
        "by_horizon": by_horizon,
        "top_reasons": by_reason,
        "figures_withheld_until_cohort_complete": figures is None,
        "figures": figures,
        "no_aggregation_across_scenarios": True,
        "censored_never_scored_as_loss": True,
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
            "horizons": document["horizon_rule"]["identifiers"],
            "primary": document["horizon_rule"]["primary"],
            "horizon_rule": "b10b_exit_first_at_or_after",
            "not_b10c_state_in_force": True,
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
