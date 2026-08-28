#!/usr/bin/env python3
"""Read-only, fail-closed PAC performance adapter for the local dashboard.

This module never runs the strategy and never repairs/mutates its files.  It only publishes a
performance curve when the scenario ledger contains a fully costed, internally reconciled schema.
Legacy/gross-only rows are surfaced as an integrity refusal instead of being charted as profit.
"""
from __future__ import annotations

from fractions import Fraction
import copy
import hashlib
import json
import pathlib
import threading
import time

from . import pac_policy, pac_runner, pac_status, solusd_recorder
from .execution import RefusedExecution


ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE_PATH = RESEARCH / "AFTERSHOCK_PAC_V1_RUNNER_STATE.json"
LEDGER_PATH = RESEARCH / "AFTERSHOCK_PAC_V1_SCENARIO_LEDGER.jsonl"
LEDGER_SCHEMA = 2
STATE_SCHEMA = 3
_STATUS_TTL_SECONDS = 60.0
_STATUS_CACHE: dict = {"at": 0.0, "value": None}
_STATUS_LOCK = threading.Lock()


def _exact_int(label: str, value, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise RefusedExecution(f"{label} must be an exact integer"
                               + (f" >= {minimum}" if minimum is not None else ""))
    return value


def _text(label: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RefusedExecution(f"{label} must be a non-empty string")
    return value


def _decimal(value: Fraction, places: int = 6) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    scale = 10 ** places
    scaled = (value.numerator * scale) // value.denominator
    whole, frac = divmod(scaled, scale)
    return f"{sign}{whole}.{frac:0{places}d}"


def _read_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return pac_runner._new_state()
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC runner state is unreadable: {type(exc).__name__}") from exc
    pac_runner._validate_state(state)
    if state["pending_ledger_rows"]:
        raise RefusedExecution("PAC runner has an unreconciled pending ledger transaction")
    return state


def _read_ledger(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise RefusedExecution(f"PAC ledger is unreadable: {type(exc).__name__}") from exc
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RefusedExecution(f"PAC ledger line {lineno} is invalid JSON") from exc
        if not isinstance(row, dict) or row.get("schema_version") != LEDGER_SCHEMA:
            raise RefusedExecution(f"PAC ledger line {lineno} is not fully-costed schema 2")
        pac_runner._validate_row(row)
        rows.append(row)
    return rows


def _latest_solusd_status() -> dict:
    """Dashboard-only O(last-record) freshness check. Sizing still uses the sealed recorder consumer."""
    path = solusd_recorder.OUTPUT
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if size <= 0:
                raise RefusedExecution("SOL/USD recorder is empty")
            window = min(size, 65_536)
            handle.seek(size - window)
            lines = [line for line in handle.read().splitlines() if line.strip()]
        if not lines:
            raise RefusedExecution("SOL/USD recorder has no complete row")
        row = json.loads(lines[-1])
        raw = row.get("raw_response_utf8")
        if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != row.get("raw_response_sha256"):
            raise RefusedExecution("latest SOL/USD raw response hash does not reconcile")
        payload = json.loads(raw)
        received = _exact_int("SOL/USD received_unix_nanos", row.get("received_unix_nanos"), minimum=0)
        now = time.time_ns()
        if received > now or now - received > solusd_recorder.MAX_LOCAL_AGE_NANOS:
            raise RefusedExecution("latest SOL/USD dashboard record is stale or future")
        price = solusd_recorder._price_string(row.get("price"))
        if (row.get("source") != solusd_recorder.SOURCE or row.get("quote_currency") != "USD"
                or not isinstance(payload, dict) or payload.get("price") != price
                or payload.get("time") != row.get("provider_trade_time")):
            raise RefusedExecution("latest SOL/USD dashboard row does not reconcile to source/raw fields")
        return {"status": "FRESH", "price": price, "received_unix_nanos": received,
                "source": solusd_recorder.SOURCE}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, RefusedExecution) as exc:
        return {"status": "REFUSED", "reason": str(exc)[:180]}


def _validate_open(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise RefusedExecution("PAC open position must be an object")
    out = {
        "mint": _text("open.mint", raw.get("mint")),
        "token_atoms": _exact_int("open.token_atoms", raw.get("token_atoms"), minimum=1),
        "quote_input_lamports": _exact_int(
            "open.quote_input_lamports", raw.get("quote_input_lamports"), minimum=1),
        "entry_all_in_lamports": _exact_int(
            "open.entry_all_in_lamports", raw.get("entry_all_in_lamports"), minimum=1),
        "entry_curve_fee_lamports": _exact_int(
            "open.entry_curve_fee_lamports", raw.get("entry_curve_fee_lamports"), minimum=0),
        "entry_attempt_cost_lamports": _exact_int(
            "open.entry_attempt_cost_lamports", raw.get("entry_attempt_cost_lamports"), minimum=0),
        "ata_rent_lamports": _exact_int(
            "open.ata_rent_lamports", raw.get("ata_rent_lamports"), minimum=0),
        "entry_observation_unix_nanos": _exact_int(
            "open.entry_observation_unix_nanos", raw.get("entry_observation_unix_nanos"), minimum=0),
        "peak_full_exit_quote_lamports": _exact_int(
            "open.peak_full_exit_quote_lamports", raw.get("peak_full_exit_quote_lamports"), minimum=0),
        "entry_decision_id": _text("open.entry_decision_id", raw.get("entry_decision_id")),
        "entry_attempt_id": _text("open.entry_attempt_id", raw.get("entry_attempt_id")),
        "last_processed_observation_unix_nanos": _exact_int(
            "open.last_processed_observation_unix_nanos",
            raw.get("last_processed_observation_unix_nanos"), minimum=0),
    }
    if out["last_processed_observation_unix_nanos"] < out["entry_observation_unix_nanos"]:
        raise RefusedExecution("PAC open position resume clock precedes its entry")
    if out["entry_all_in_lamports"] != (out["quote_input_lamports"]
            + out["entry_curve_fee_lamports"] + out["entry_attempt_cost_lamports"]
            + out["ata_rent_lamports"]):
        raise RefusedExecution("PAC open position entry costs do not reconcile")
    return out


def _validate_rows(rows: list[dict], opens: list[dict], state: dict) -> tuple[list[dict], list[dict], list[dict]]:
    event_ids: set[str] = set()
    opened: dict[str, dict] = {}
    closed_attempts: set[str] = set()
    resolved: list[dict] = []
    performance_events: list[dict] = []
    activity: list[dict] = []
    for index, row in enumerate(rows):
        event_id = _text(f"ledger[{index}].event_id", row.get("event_id"))
        if event_id in event_ids:
            raise RefusedExecution("PAC ledger contains a duplicate event_id")
        event_ids.add(event_id)
        kind = row.get("kind")
        mint = _text(f"ledger[{index}].mint", row.get("mint"))
        if state["session_event_sha256"] is not None and (
                row.get("session_event_sha256") != state["session_event_sha256"]
                or row.get("activation_root_sha256") != state["activation_root_sha256"]):
            raise RefusedExecution("PAC ledger row belongs to another runner session")
        if kind == "opened":
            attempt_id = _text("opened.entry_attempt_id", row.get("entry_attempt_id"))
            if attempt_id in opened:
                raise RefusedExecution("PAC ledger contains a duplicate opened entry attempt")
            entry_all_in = _exact_int(
                "opened.entry_all_in_lamports", row.get("entry_all_in_lamports"), minimum=1)
            quote_input = _exact_int(
                "opened.quote_input_lamports", row.get("quote_input_lamports"), minimum=1)
            entry_curve = _exact_int("opened.entry_curve_fee_lamports",
                                     row.get("entry_curve_fee_lamports"), minimum=0)
            entry_attempt = _exact_int("opened.entry_attempt_cost_lamports",
                                       row.get("entry_attempt_cost_lamports"), minimum=0)
            rent = _exact_int("opened.ata_rent_lamports", row.get("ata_rent_lamports"), minimum=0)
            if entry_all_in != quote_input + entry_curve + entry_attempt + rent:
                raise RefusedExecution("PAC opened entry costs do not reconcile")
            opened[attempt_id] = row
            activity.append({"kind": kind, "mint": mint, "status": "OPENED",
                             "entry_attempt_id": attempt_id})
            continue
        if kind == "attempt_cost":
            attempt_id = _text("attempt_cost.attempt_id", row.get("attempt_id"))
            if attempt_id in closed_attempts:
                raise RefusedExecution("PAC ledger contains a duplicate attempt id")
            closed_attempts.add(attempt_id)
            cost = _exact_int("attempt_cost.attempt_cost_lamports",
                              row.get("attempt_cost_lamports"), minimum=0)
            denominator = _exact_int("attempt_cost.denominator_lamports",
                                     row.get("denominator_lamports"), minimum=1)
            observed = row.get("cost_observed")
            if type(observed) is not bool or (not observed and cost != 0):
                raise RefusedExecution("PAC failed-attempt cost observability does not reconcile")
            ret = Fraction(-cost, denominator)
            performance_events.append({"kind": kind, "return": ret,
                                       "unexitable_full_loss": False})
            activity.append({"kind": kind, "mint": mint,
                             "status": _text("attempt_cost.outcome", row.get("outcome")),
                             "attempt_cost_lamports": cost,
                             "return_r": _decimal(ret)})
            continue
        if kind != "resolved":
            raise RefusedExecution(f"PAC ledger contains unknown kind {kind!r}")

        entry_attempt = _text("resolved.entry_attempt_id", row.get("entry_attempt_id"))
        exit_attempt = row.get("exit_attempt_id")
        if exit_attempt is not None:
            exit_attempt = _text("resolved.exit_attempt_id", exit_attempt)
            if exit_attempt in closed_attempts:
                raise RefusedExecution("PAC ledger contains a duplicate exit attempt")
            closed_attempts.add(exit_attempt)
        if entry_attempt not in opened:
            raise RefusedExecution("PAC resolution does not reference an earlier opened entry")
        if any(r["entry_attempt_id"] == entry_attempt for r in resolved):
            raise RefusedExecution("PAC entry resolves more than once")

        entry_cost = _exact_int(
            "resolved.entry_all_in_lamports", row.get("entry_all_in_lamports"), minimum=1)
        exit_net = _exact_int(
            "resolved.exit_net_proceeds_lamports", row.get("exit_net_proceeds_lamports"))
        num = _exact_int("resolved.net_return_num", row.get("net_return_num"))
        den = _exact_int("resolved.net_return_den", row.get("net_return_den"), minimum=1)
        if den != entry_cost or num != exit_net - entry_cost:
            raise RefusedExecution("PAC resolved return does not reconcile to all-in entry and net exit")
        opened_row = opened[entry_attempt]
        if entry_cost != opened_row["entry_all_in_lamports"]:
            raise RefusedExecution("PAC resolved entry cost differs from its opened row")
        gross = _exact_int("resolved.exit_gross_quote_lamports",
                           row.get("exit_gross_quote_lamports"), minimum=0)
        curve = _exact_int("resolved.exit_curve_fee_lamports",
                           row.get("exit_curve_fee_lamports"), minimum=0)
        attempt_cost = _exact_int("resolved.exit_attempt_cost_lamports",
                                  row.get("exit_attempt_cost_lamports"), minimum=0)
        if exit_net != gross - curve - attempt_cost:
            raise RefusedExecution("PAC exit net does not reconcile to gross quote, curve fee and attempt cost")
        if Fraction(num, den) < -1:
            raise RefusedExecution("PAC scenario return is below the full-loss floor")
        entry_obs = _exact_int(
            "resolved.entry_observation_unix_nanos", row.get("entry_observation_unix_nanos"), minimum=0)
        exit_obs = row.get("exit_boundary_observation_unix_nanos")
        if exit_obs is not None and _exact_int(
                "resolved.exit_boundary_observation_unix_nanos", exit_obs, minimum=0) <= entry_obs:
            raise RefusedExecution("PAC exit boundary is not strictly after entry")
        if row.get("unexitable_full_loss") is True and (num != -den or exit_net != 0):
            raise RefusedExecution("PAC unexitable row is not an exact full loss")
        resolved_row = {
            "kind": kind, "mint": mint,
            "action": _text("resolved.action", row.get("action")),
            "entry_attempt_id": entry_attempt, "exit_attempt_id": exit_attempt,
            "entry_observation_unix_nanos": entry_obs,
            "exit_boundary_observation_unix_nanos": exit_obs,
            "return": Fraction(num, den),
            "return_r": _decimal(Fraction(num, den)),
            "entry_all_in_lamports": entry_cost,
            "exit_net_proceeds_lamports": exit_net,
            "unexitable_full_loss": row.get("unexitable_full_loss") is True,
        }
        resolved.append(resolved_row)
        performance_events.append(resolved_row)
        activity.append({k: v for k, v in resolved_row.items() if k != "return"})

    open_attempts = {_text("open.entry_attempt_id", p["entry_attempt_id"]) for p in opens}
    unresolved_attempts = set(opened) - {row["entry_attempt_id"] for row in resolved}
    if open_attempts != unresolved_attempts:
        raise RefusedExecution("PAC state and ledger do not reconcile to the same open entries")
    if len(opens) > 1:
        raise RefusedExecution("PAC state violates the one-position discovery policy")
    return resolved, performance_events, activity


def _performance(resolved: list[dict], performance_events: list[dict] | None = None) -> dict:
    baseline = Fraction(100, 1)
    probe_index = Fraction(10, 1)
    equity = baseline
    peak = baseline
    max_dd = Fraction(0, 1)
    curve = [_decimal(equity, 4)]
    wins = losses = full_losses = 0
    total = Fraction(0, 1)
    performance_events = resolved if performance_events is None else performance_events
    for row in resolved:
        ret = row["return"]
        total += ret
        wins += ret > 0
        losses += ret < 0
        full_losses += row["unexitable_full_loss"]
    attempt_cost_events = sum(row["kind"] == "attempt_cost" for row in performance_events)
    total = sum((row["return"] for row in performance_events), Fraction(0, 1))
    for row in performance_events:
        ret = row["return"]
        equity += probe_index * ret
        curve.append(_decimal(equity, 4))
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    n = len(resolved)
    return {
        "resolved": n,
        "wins": wins,
        "losses": losses,
        "full_losses": full_losses,
        "failed_attempt_cost_events": attempt_cost_events,
        "win_rate": _decimal(Fraction(wins, n), 6) if n else None,
        "unexitable_rate": _decimal(Fraction(full_losses, n), 6) if n else None,
        "mean_return_r": _decimal(total / n, 6) if n else None,
        "sum_return_r": _decimal(total, 6),
        "normalized_capital_index": _decimal(equity, 4),
        "normalized_capital_change_pct": (_decimal((equity - baseline) / baseline, 6)
                                           if performance_events else None),
        "max_drawdown": _decimal(max_dd, 6) if performance_events else None,
        "equity_curve": curve,
        "minimum_discovery": 100,
        "discovery_progress": _decimal(Fraction(min(n, 100), 100), 4),
        "numeraire_note": (
            "Normalized 100-index: each fully-costed trade contributes 10 × return. "
            "It is not executable USD P&L and never includes unanchored/gross-only rows."),
    }


def snapshot(*, ledger_path: pathlib.Path = LEDGER_PATH, state_path: pathlib.Path = STATE_PATH,
             status_snapshot: dict | None = None) -> dict:
    if status_snapshot is not None:
        status = status_snapshot
    else:
        now = time.monotonic()
        with _STATUS_LOCK:
            if (_STATUS_CACHE["value"] is None
                    or now - _STATUS_CACHE["at"] >= _STATUS_TTL_SECONDS):
                _STATUS_CACHE["value"] = pac_status.status()
                _STATUS_CACHE["at"] = time.monotonic()
            status = copy.deepcopy(_STATUS_CACHE["value"])
        status["solusd"] = _latest_solusd_status()
        status["slow_inventory_refresh_seconds"] = _STATUS_TTL_SECONDS
    errors: list[str] = []
    state = pac_runner._new_state()
    rows: list[dict] = []
    opens: list[dict] = []
    resolved: list[dict] = []
    performance_events: list[dict] = []
    activity: list[dict] = []
    try:
        state = _read_state(state_path)
        rows = _read_ledger(ledger_path)
        opens = [_validate_open(raw) for raw in state["open_positions"]]
        resolved, performance_events, activity = _validate_rows(rows, opens, state)
    except RefusedExecution as exc:
        errors.append(str(exc))

    anchored = status.get("seal") == "ANCHORED" and status.get("activation") == "ANCHORED"
    if errors:
        evidence_status = "REFUSED_LEDGER_INTEGRITY"
        performance = _performance([])
    elif rows and not anchored:
        evidence_status = "REFUSED_UNANCHORED_EVIDENCE"
        errors.append("ledger rows exist while the current PAC seal/session is not anchored")
        performance = _performance([])
    elif rows:
        evidence_status = ("VALID_PAPER_SCENARIO"
                           if status.get("latency_calibration") == "CALIBRATED_FORWARD_CLOCKS"
                           else "VALID_UNCALIBRATED_PAPER_SCENARIO")
        performance = _performance(resolved, performance_events)
    else:
        evidence_status = "NO_FORWARD_EVIDENCE"
        performance = _performance([])

    scenario_resolved = performance["resolved"]
    calibrated = status.get("latency_calibration") == "CALIBRATED_FORWARD_CLOCKS"
    promotion_resolved = scenario_resolved if calibrated else 0
    performance["scenario_resolved"] = scenario_resolved
    performance["promotion_discovery_resolved"] = promotion_resolved
    performance["discovery_progress"] = _decimal(Fraction(min(promotion_resolved, 100), 100), 4)
    performance["calibration_note"] = (
        "Scenario outcomes do not count toward the 100-position promotion gate until build/sign/send/land "
        "and failure clocks are measured and separately frozen."
        if not calibrated else "Measured forward-clock outcomes count toward promotion discovery.")

    return {
        "instrument_id": "AFTERSHOCK_PAC_V1",
        "title": "Payable Absorption Compression",
        "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS · NOT A PROFIT CLAIM",
        "evidence_status": evidence_status,
        "integrity_errors": errors,
        "operational": status,
        "formula": "W2≥W1 · D2≤D1 · B2≥B1 · E2≥E1",
        "formula_note": "second sell/recovery is no weaker, no slower, and does not erode reserve capacity",
        "policy": {
            "bankroll_index_start": pac_policy.DISCOVERY_BANKROLL_USD,
            "probe_index_points": pac_policy.DISCOVERY_PROBE_USD,
            "trail_percent": 12,
            "coverage_multiple": 6,
            "max_hold_minutes": 12,
            "max_concurrent_positions": 1,
        },
        "performance": performance,
        "open_positions": opens,
        "pending_orders": state.get("pending_orders", []),
        "last_measurement_refusal": state.get("last_measurement_refusal"),
        "activity": list(reversed(activity[-100:])),
        "ledger_rows": len(rows),
        "generated_at": time.time(),
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2, default=str))
