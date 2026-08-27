#!/usr/bin/env python3
"""Append-only V2 evidence ledger for the Pump sniper.

The legacy sniper files only retained successful *resolutions*.  An open paper position vanished when
the stream process restarted, and the retained row omitted enough of the entry commitment that its hash
could not be recomputed.  This module writes the entry fill immediately, then one terminal resolution.
Unresolved entries discovered at startup are not silently discarded: they receive an
``INVALID_RESTART_GAP`` terminal record and a conservative full-position-loss stress value.

Paper only.  No wallet, signer, transaction or on-chain write is reachable here.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
TERMINAL_STATUSES = {"RESOLVED", "INVALIDATED"}
NON_EXECUTABLE_REASONS = {"INVALID_RESTART_GAP", "UNPRICED_STALE_TIMEOUT"}
MARK_KIND = "position_mark"   # non-terminal checkpoint of an OPEN position's peak/flow (for restart replay)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_sha256(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _dict(value: Any) -> dict:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return dict(value)


def _with_event_id(event: dict) -> dict:
    out = dict(event)
    out["event_id"] = canonical_sha256(out)
    return out


def append_event(path: str | Path, event: dict) -> None:
    """Durably append one event.  Evidence-write failures raise visibly to stop the paper run."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str) + "\n"
    with p.open("a") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_events(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for lineno, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed V2 ledger {p}:{lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object V2 ledger event {p}:{lineno}")
        out.append(row)
    return out


def executor_assumptions(executor: Any) -> dict:
    return {
        "executor": getattr(executor, "name", "dry-run"),
        "sol_price_usd": float(executor.sol_price_usd),
        "tip_sol_per_side": float(executor.tip_sol),
        "use_live_quote": bool(executor.use_live_quote),
        "default_liq_usd_per_s": float(executor.default_liq_usd_per_s),
    }


def full_loss_stress_r(entry: dict) -> float:
    """Value an unavailable exit at -100% plus the pinned round-trip toll and fixed tips."""
    fill = entry["entry_fill"]
    cfg = entry["strategy_config"]
    price = float(fill["price_usd"])
    size = float(fill["usd_size"])
    catastrophe = float(cfg["catastrophe_frac"])
    if price <= 0 or size <= 0 or catastrophe <= 0:
        raise ValueError("positive entry price, size and catastrophe_frac required")
    units = size / price
    # Apply the same per-side assumptions as a normal round trip.  This is deliberately a bound: a
    # truly unsellable coin may not incur an exit tip, but it also has no executable recovery value.
    toll_cost_per_unit = 2.0 * float(fill["toll_bps"]) / 10_000.0 * price
    tips_per_unit = 2.0 * float(fill.get("tip_usd", 0.0)) / units
    return (-price - toll_cost_per_unit - tips_per_unit) / (price * catastrophe)


def make_entry_event(*, variant: str, preset: str, position: Any, signal: Any,
                     frozen_payload: dict, strategy_config: Any, executor: Any,
                     experiment_sha256: str | None = None) -> dict:
    config = _dict(strategy_config)
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": "entry",
        "status": "OPEN",
        "event_utc": _now_iso(),
        "variant": variant,
        "preset": preset,
        "mint": position.mint,
        "venue": position.venue,
        "frozen_sha256": position.frozen_sha256,
        "frozen_payload": frozen_payload,
        "entry_fill": _dict(position.entry),
        "signal": _dict(signal),
        "strategy_config": config,
        "strategy_config_sha256": canonical_sha256(config),
        "executor_assumptions": executor_assumptions(executor),
        "experiment_preregistration_sha256": experiment_sha256,
        "equity_usd_at_entry": position.meta.get("equity_usd_at_entry"),
        "commitment_recomputable": canonical_sha256(frozen_payload) == position.frozen_sha256,
    }
    event["full_loss_stress_r"] = full_loss_stress_r(event)
    return _with_event_id(event)


def make_resolution_event(*, variant: str, preset: str, position: Any,
                          entry_event: dict) -> dict:
    reason = position.exit_reason or "UNKNOWN"
    executable = reason != "exit:maxhold_timeout"
    stress_r = float(position.realized_r) if executable else float(entry_event["full_loss_stress_r"])
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": "resolution",
        "status": "RESOLVED",
        "event_utc": _now_iso(),
        "variant": variant,
        "preset": preset,
        "mint": position.mint,
        "venue": position.venue,
        "frozen_sha256": position.frozen_sha256,
        "entry_event_id": entry_event["event_id"],
        "exit_fill": _dict(position.exit) if position.exit is not None else None,
        "resolution_reason": reason,
        "realized_r": position.realized_r,
        "stress_realized_r": stress_r,
        "realized_pnl_usd": position.meta.get("realized_pnl_usd"),
        "equity_usd_before_exit": position.meta.get("equity_usd_before_exit"),
        "equity_usd_after_exit": position.meta.get("equity_usd_after_exit"),
        "executable_price_observed": executable,
    }
    if not executable:
        event["stress_note"] = (
            "silent-token timeout used a stale mark; adjudication values it at the frozen full-loss bound"
        )
    return _with_event_id(event)


def make_mark_event(*, variant: str, preset: str, position: Any) -> dict:
    """A non-terminal CHECKPOINT of an OPEN position's mutable exit state (peak, flow streak, last mark),
    so a process restart can REOPEN the position honestly instead of charging it a full-loss gap. Append-
    only; last-write-wins per frozen_sha256 on replay. Ignored by ledger_summary (unknown kind)."""
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": MARK_KIND,
        "status": "OPEN",
        "event_utc": _now_iso(),
        "variant": variant,
        "preset": preset,
        "mint": position.mint,
        "frozen_sha256": position.frozen_sha256,
        "peak_price": float(position.peak_price),
        "flow_below_streak": int(position.meta.get("flow_below_streak", 0)),
        "last_price": position.meta.get("last_price"),
        "last_bar_ts": position.meta.get("last_bar_ts"),
    }
    return _with_event_id(event)


def reload_open_entries(path: str | Path) -> list[dict]:
    """Entries with NO terminal event yet, each paired with its latest position_mark (or None). This is
    the restart-replay source: reconstruct each into an open Position so nothing is dropped/censored."""
    events = read_events(path)
    entries = {str(e.get("frozen_sha256")): e for e in events if e.get("kind") == "entry"}
    terminal = {str(e.get("frozen_sha256")) for e in events
                if e.get("kind") == "resolution" and e.get("status") in TERMINAL_STATUSES}
    marks: dict[str, dict] = {}
    for e in events:                                   # file is time-ordered -> last write wins
        if e.get("kind") == MARK_KIND:
            marks[str(e.get("frozen_sha256"))] = e
    return [{"entry": entry, "mark": marks.get(sha)}
            for sha, entry in entries.items() if sha not in terminal]


def invalidate_unresolved(path: str | Path, only: set[str] | None = None) -> list[dict]:
    """Append one terminal invalidation for every persisted entry lacking a terminal event. When ``only``
    is given, invalidate ONLY those frozen_sha256s (used as the narrowed fallback for entries that failed
    honest reconstruction on restart -- everything reconstructable is reopened, not invalidated)."""
    events = read_events(path)
    entries = {str(e.get("frozen_sha256")): e for e in events if e.get("kind") == "entry"}
    terminal = {str(e.get("frozen_sha256")) for e in events
                if e.get("kind") == "resolution" and e.get("status") in TERMINAL_STATUSES}
    added: list[dict] = []
    for frozen_sha, entry in entries.items():
        if frozen_sha in terminal:
            continue
        if only is not None and frozen_sha not in only:
            continue
        event = _with_event_id({
            "schema_version": SCHEMA_VERSION,
            "kind": "resolution",
            "status": "INVALIDATED",
            "event_utc": _now_iso(),
            "variant": entry.get("variant"),
            "preset": entry.get("preset"),
            "mint": entry.get("mint"),
            "venue": entry.get("venue"),
            "frozen_sha256": frozen_sha,
            "entry_event_id": entry.get("event_id"),
            "exit_fill": None,
            "resolution_reason": "INVALID_RESTART_GAP",
            "realized_r": None,
            "stress_realized_r": float(entry["full_loss_stress_r"]),
            "realized_pnl_usd": None,
            "executable_price_observed": False,
            "stress_note": (
                "process restarted without checkpointed peak/flow state; position cannot be honestly "
                "resumed and is charged at the frozen full-loss bound"
            ),
        })
        append_event(path, event)
        added.append(event)
    return added


def ledger_summary(path: str | Path) -> dict:
    events = read_events(path)
    entries = {str(e.get("frozen_sha256")): e for e in events if e.get("kind") == "entry"}
    terminal: dict[str, dict] = {}
    duplicate_terminal = 0
    for event in events:
        if event.get("kind") != "resolution" or event.get("status") not in TERMINAL_STATUSES:
            continue
        key = str(event.get("frozen_sha256"))
        if key in terminal:
            duplicate_terminal += 1
            continue
        terminal[key] = event
    outcomes = list(terminal.values())
    stress_pnl_usd = 0.0
    for event in outcomes:
        entry = entries.get(str(event.get("frozen_sha256")))
        if not entry or event.get("stress_realized_r") is None:
            continue
        cfg = entry["strategy_config"]
        size = float(entry["entry_fill"]["usd_size"])
        risk_notional_usd = size * float(cfg["catastrophe_frac"])
        stress_pnl_usd += float(event["stress_realized_r"]) * risk_notional_usd
    initial_equities = {float(e["strategy_config"]["initial_bankroll_usd"])
                        for e in entries.values()}
    initial_equity = next(iter(initial_equities)) if len(initial_equities) == 1 else None
    return {
        "entries": len(entries),
        "terminal": len(outcomes),
        "open": len(set(entries) - set(terminal)),
        "duplicate_terminal": duplicate_terminal,
        "reported_r": [float(e["realized_r"]) for e in outcomes if e.get("realized_r") is not None],
        "stress_r": [float(e["stress_realized_r"]) for e in outcomes
                     if e.get("stress_realized_r") is not None],
        "restart_invalidations": sum(e.get("resolution_reason") == "INVALID_RESTART_GAP"
                                     for e in outcomes),
        "stale_mark_stressed": sum(e.get("resolution_reason") == "exit:maxhold_timeout"
                                   for e in outcomes),
        "commitment_failures": sum(not e.get("commitment_recomputable", False)
                                   for e in entries.values()),
        "stress_realized_pnl_usd": stress_pnl_usd,
        "initial_equity_usd": initial_equity,
        "adjudication_equity_usd": (
            max(0.0, initial_equity + stress_pnl_usd) if initial_equity is not None else None),
    }
