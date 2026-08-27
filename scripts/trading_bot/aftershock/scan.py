#!/usr/bin/env python3
"""AFTERSHOCK scan/track — the tape-driven detached loop. PAPER, read-only.

Each pass:
  1. ENTRIES — for each recently-created mint not already entered, replay its trade tape through a fresh
     detector; on a FIRE (PASS or CONTROL) whose (mint, t_shock) is new, freeze + append the entry.
  2. TRACK   — for each OPEN position, resolve against its tape since entry; append any resolution.

Idempotent: fires are de-duplicated by (mint, t_shock) read back from the ledger, so replaying the same
tape never double-enters (the record's decided_utc changes per pass, so the hash is not a stable key).
Bounded: only mints created within RECENT_MIN are scanned for entries (AFTERSHOCK's shock+absorption
window is in a coin's first minutes), so a pass stays cheap.
"""
from __future__ import annotations

import contextlib
import fcntl
import time

from . import frozen, entry, resolve, tape
from .detector import DetectorConfig, SLOT_SECONDS, _MintDetector
from scripts.trading_bot.memebot import ledger as _ledger

RECENT_MIN = 20.0          # a mint's shock+absorption opportunity is in its first minutes
SCAN_MARGIN_MIN = 5.0      # read creates a little older too (review #9: a late shock fires after its
#                            absorption window + loop latency, by when the create would have aged out;
#                            the (mint, t_shock) dedup makes re-scanning older creates safe)
MAX_SCAN_MINTS = 500       # safety cap on entry-scan work per pass


@contextlib.contextmanager
def _pass_lock(spec: dict):
    """Inter-process flock so two scan/track passes never double-enter the same shock (review #8)."""
    lock_path = spec["_paths"]["state"].with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _entered_keys(spec: dict) -> set:
    """(mint, t_shock) pairs already frozen as entries — the idempotency key."""
    return {(e.get("pool_address"), e.get("t_shock"))
            for e in _ledger.read_entries(spec) if e.get("kind") == "entry"}


def scan_entries(spec: dict) -> dict:
    cfg = DetectorConfig.from_spec(spec["detector"])
    with _pass_lock(spec):
        entered = _entered_keys(spec)   # re-read under the lock so concurrent passes can't both add
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

        def _handle(fire) -> None:
            nonlocal fired_pass, fired_control
            key = (fire["mint"], fire["t_shock"])
            if key in entered:
                return
            entry.freeze_and_append(fire, spec)
            entered.add(key)
            if fire["control"]:
                fired_control += 1
            else:
                fired_pass += 1

        for mint in mints:
            lines = tape.read_tape(mint)
            if not lines:
                continue
            det = _MintDetector(cfg=cfg)
            for ln in lines:
                fire = det.on_line(ln)
                if fire is not None:
                    _handle(fire)
            # wall-clock flush: an ARMED window that has objectively elapsed but whose closing tape line
            # never arrived (dead/rugged mint) is force-closed as the honest CONTROL null (review #2).
            flushed = det.flush(time.time())
            if flushed is not None:
                _handle(flushed)

        return {"scanned_mints": len(mints), "new_pass_entries": fired_pass,
                "new_control_entries": fired_control}


def track_open(spec: dict) -> dict:
    resolved = 0
    with _pass_lock(spec):
        for setup in _ledger.open_positions(spec):
            mint = setup.get("pool_address")
            t_entry = float(setup.get("t_entry") or 0.0)
            lines = tape.read_tape(mint, since_ts=t_entry)
            if not lines:
                # tape reaped/empty but the wall-clock horizon may still have elapsed: fall back to the
                # frozen entry reserves so a silent coin still resolves (small-fee exit or UNEXITABLE).
                if time.time() >= t_entry + spec["exit"]["max_hold_slots"] * SLOT_SECONDS:
                    lines = [{**setup["entry_reserves"], "trader": None, "side": "sell",
                              "sol_amount": 0.0, "token_amount": 0.0, "mint": mint,
                              "ts": t_entry + spec["exit"]["max_hold_slots"] * SLOT_SECONDS}]
                else:
                    continue
            res = resolve.resolve_from_tape(setup, lines, spec)
            if res is not None:
                _ledger.append_resolution(spec, res)
                resolved += 1
    return {"resolved": resolved}


def run_cycle() -> dict:
    spec = frozen.frozen_spec("AFTERSHOCK")
    e = scan_entries(spec)
    t = track_open(spec)
    return {"utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            **e, **t, "open_positions": len(_ledger.open_positions(spec))}


def run_loop(interval_s: float = 90.0) -> None:
    while True:
        try:
            rep = run_cycle()
            print(rep, flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"aftershock scan error: {type(e).__name__}: {str(e)[:160]}", flush=True)
        time.sleep(interval_s)
