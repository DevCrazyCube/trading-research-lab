#!/usr/bin/env python3
"""AFTERSHOCK V5 — SCALE-OUT 3-arm forward loop. PAPER, read-only.

Entry identical to V3/V4 (reuses the V3 detector); exit is the two-leg scale-out (resolve_v5). Per-arm
ledgers AFTERSHOCK_V5_{A,B,C}. Same idempotent/bounded/flock shape as scan_v2/v3/v4. NO orders/wallet/SOL.
"""
from __future__ import annotations

import datetime as dt
import time

from . import frozen, entry, resolve_v5, tape
from .detector import SLOT_SECONDS
from .detector_v3 import DetectorV3Config, _MintDetectorV3
from .scan import _pass_lock, _entered_keys, RECENT_MIN, SCAN_MARGIN_MIN, MAX_SCAN_MINTS
from scripts.trading_bot.memebot import ledger as _ledger


def arm_spec(base: dict, arm: dict) -> dict:
    prefix = f"AFTERSHOCK_V5_{arm['arm']}"
    s = dict(base)
    s["instrument_id"] = prefix
    s["_paths"] = frozen.paths_for(prefix)
    s["_arm"] = arm
    return s


def scan_entries_v5(aspec: dict) -> dict:
    cfg = DetectorV3Config.from_spec(aspec, veto_strict=False)   # V5 entry == V3 entry
    with _pass_lock(aspec):
        entered = _entered_keys(aspec)
        since = time.time() - (RECENT_MIN + SCAN_MARGIN_MIN) * 60.0
        creates = tape.read_creates(since_ts=since)
        seen, mints = set(), []
        for c in reversed(creates):
            m = c.get("mint")
            if m and m not in seen:
                seen.add(m)
                mints.append(m)
            if len(mints) >= MAX_SCAN_MINTS:
                break

        fired_pass = fired_control = 0

        freeze_ts = frozen.freeze_epoch(aspec)

        def _handle(fire) -> None:
            nonlocal fired_pass, fired_control
            if float(fire.get("t_shock") or 0.0) < freeze_ts:
                return   # no lookahead: the shock predates the freeze (Codex audit 2026-08-27)
            key = (fire["mint"], fire["t_shock"])
            if key in entered:
                return
            entry.freeze_and_append(fire, aspec)
            entered.add(key)
            if fire["control"]:
                fired_control += 1
            else:
                fired_pass += 1

        for mint in mints:
            lines = tape.read_tape(mint)
            if not lines:
                continue
            det = _MintDetectorV3(cfg=cfg)
            for ln in lines:
                fire = det.on_line(ln)
                if fire is not None:
                    _handle(fire)
            flushed = det.flush(time.time())
            if flushed is not None:
                _handle(flushed)

        return {"scanned_mints": len(mints), "new_pass_entries": fired_pass,
                "new_control_entries": fired_control}


def track_open_v5(aspec: dict, arm: dict, base: dict) -> dict:
    resolved = 0
    with _pass_lock(aspec):
        for setup in _ledger.open_positions(aspec):
            mint = setup.get("pool_address")
            t_entry = float(setup.get("t_entry") or 0.0)
            lines = tape.read_tape(mint, since_ts=t_entry)
            if not lines:
                horizon = base["exit"]["max_hold_slots"] * SLOT_SECONDS
                if time.time() >= t_entry + horizon:
                    lines = [{**setup["entry_reserves"], "trader": None, "side": "sell",
                              "sol_amount": 0.0, "token_amount": 0.0, "mint": mint,
                              "ts": t_entry + horizon}]
                else:
                    continue
            res = resolve_v5.resolve_from_tape_v5(setup, lines, base, arm)
            if res is not None:
                _ledger.append_resolution(aspec, res)
                resolved += 1
    return {"resolved": resolved}


def run_cycle_v5() -> dict:
    base = frozen.frozen_spec("AFTERSHOCK_V5")
    per_arm = {}
    for arm in base["arms"]:
        aspec = arm_spec(base, arm)
        e = scan_entries_v5(aspec)
        t = track_open_v5(aspec, arm, base)
        per_arm[arm["arm"]] = {**e, **t, "open_positions": len(_ledger.open_positions(aspec))}
    return {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "arms": per_arm}


def run_loop_v5(interval_s: float = 90.0) -> None:
    while True:
        try:
            rep = run_cycle_v5()
            print(rep, flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"aftershock v5 scan error: {type(e).__name__}: {str(e)[:180]}", flush=True)
        time.sleep(interval_s)
