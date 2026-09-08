#!/usr/bin/env python3
"""AFTERSHOCK V2 scan/track — the 3-arm tape-driven detached loop. PAPER, read-only.

Runs arms A/B/C off the SAME frozen AFTERSHOCK_V2 spec, each into its OWN ledger
(AFTERSHOCK_V2_A / _B / _C) so their forward records are isolated and scored separately. Arms differ
only by the frozen `arms` block: A = net-reserve entry + V1 exit; B = + strict entry-flow-veto;
C = B + capacity/quote-trail exit. The per-arm spec is synthesised from the one frozen spec (same
prereg hash, same thresholds) with its own on-disk paths — no duplicate frozen files.

Mirrors scan.py (idempotent by (mint, t_shock), bounded to recent creates, flock-guarded). NO orders,
no wallet, no real SOL, no on-chain writes: reads the free tape + curve-exact ECR math only.
"""
from __future__ import annotations

import datetime as dt
import time

from . import frozen, entry, resolve_v2, tape
from .detector import SLOT_SECONDS
from .detector_v2 import DetectorV2Config, _MintDetectorV2
from .scan import _pass_lock, _entered_keys, RECENT_MIN, SCAN_MARGIN_MIN, MAX_SCAN_MINTS
from scripts.trading_bot.memebot import ledger as _ledger


def arm_spec(base: dict, arm: dict) -> dict:
    """Per-arm spec: the shared frozen spec re-pointed at this arm's own ledger paths."""
    prefix = f"AFTERSHOCK_V2_{arm['arm']}"
    s = dict(base)
    s["instrument_id"] = prefix
    s["_paths"] = frozen.paths_for(prefix)
    s["_arm"] = arm
    return s


def scan_entries_v2(aspec: dict, arm: dict) -> dict:
    cfg = DetectorV2Config.from_spec(aspec, veto_strict=bool(arm.get("veto_strict")))
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
            det = _MintDetectorV2(cfg=cfg)
            for ln in lines:
                fire = det.on_line(ln)
                if fire is not None:
                    _handle(fire)
            flushed = det.flush(time.time())
            if flushed is not None:
                _handle(flushed)

        return {"scanned_mints": len(mints), "new_pass_entries": fired_pass,
                "new_control_entries": fired_control}


def track_open_v2(aspec: dict, arm: dict, base: dict) -> dict:
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
            res = resolve_v2.resolve_from_tape_v2(setup, lines, base, arm)
            if res is not None:
                _ledger.append_resolution(aspec, res)
                resolved += 1
    return {"resolved": resolved}


def run_cycle_v2() -> dict:
    base = frozen.frozen_spec("AFTERSHOCK_V2")
    per_arm = {}
    for arm in base["arms"]:
        aspec = arm_spec(base, arm)
        e = scan_entries_v2(aspec, arm)
        t = track_open_v2(aspec, arm, base)
        per_arm[arm["arm"]] = {**e, **t, "open_positions": len(_ledger.open_positions(aspec))}
    return {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "arms": per_arm}


def run_loop_v2(interval_s: float = 90.0) -> None:
    while True:
        try:
            rep = run_cycle_v2()
            print(rep, flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"aftershock v2 scan error: {type(e).__name__}: {str(e)[:180]}", flush=True)
        time.sleep(interval_s)
