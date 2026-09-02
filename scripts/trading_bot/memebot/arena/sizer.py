#!/usr/bin/env python3
"""MEME ARENA — the shared position sizer + global risk limits. One place, all arms, so risk is bounded
ACROSS arms, not per-arm. Frozen rules from the owner's spec:
  - bankroll $100, fixed clip $10 (NO martingale — the clip never grows to chase a loss);
  - at most TWO concurrent PRIMARY positions across ALL arms (flock-guarded global slot file);
  - a position's clip must be <= 5% of its stress-tested exit capacity at entry, else reduce-or-VOID;
  - scale up ONLY after a real forward PASS, via conservative fractional Kelly, capped at 10% of bankroll.
Pure stdlib + a flock'd json slot file; hermetically testable (the slot file path is injectable).
"""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import time

BANKROLL_USD = 100.0
CLIP_USD = 10.0
MAX_CONCURRENT_PRIMARY = 2
MAX_EXIT_CAPACITY_FRAC = 0.05      # clip <= 5% of stress-tested exit capacity
MAX_KELLY_FRAC = 0.10             # post-PASS scale-up ceiling: 10% of bankroll
KELLY_FRACTION = 0.25            # conservative quarter-Kelly


def clip_sol(sol_usd: float) -> float:
    """The fixed $10 clip expressed in SOL at the activation's frozen SOL/USD."""
    if not sol_usd or sol_usd <= 0:
        raise ValueError("sol_usd must be positive")
    return CLIP_USD / sol_usd


def exit_capacity_ok(clip_usd: float, exit_capacity_usd: float | None) -> tuple[bool, str]:
    """A clip is tradeable only if it is <= 5% of the stress-tested exit capacity. If capacity is unknown,
    it is NOT ok (VOID rather than trade blind)."""
    if exit_capacity_usd is None or exit_capacity_usd <= 0:
        return False, "exit capacity unknown/zero — VOID (never trade blind liquidity)"
    frac = clip_usd / exit_capacity_usd
    if frac <= MAX_EXIT_CAPACITY_FRAC:
        return True, f"clip is {frac:.1%} of exit capacity (<= {MAX_EXIT_CAPACITY_FRAC:.0%})"
    return False, f"clip is {frac:.1%} of exit capacity (> {MAX_EXIT_CAPACITY_FRAC:.0%}) — reduce or VOID"


def _slot_path(portfolio_path) -> pathlib.Path:
    return pathlib.Path(portfolio_path)


def try_acquire_primary(instrument: str, mint: str, portfolio_path, now=None) -> bool:
    """Atomically claim one of the <=2 global PRIMARY slots. Returns True on success. flock-guarded so two
    arm runtimes cannot both take the last slot."""
    now = now if now is not None else time.time()
    p = _slot_path(portfolio_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = os.read(fd, 1_000_000).decode() or "{}"
        try:
            slots = json.loads(raw)
        except ValueError:
            slots = {}
        key = f"{instrument}:{mint}"
        if key in slots:
            return True                                  # idempotent re-claim of our own slot
        if len(slots) >= MAX_CONCURRENT_PRIMARY:
            return False
        slots[key] = now
        os.lseek(fd, 0, 0); os.ftruncate(fd, 0)
        os.write(fd, json.dumps(slots).encode()); os.fsync(fd)
        return True
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def release_primary(instrument: str, mint: str, portfolio_path) -> None:
    p = _slot_path(portfolio_path)
    if not p.exists():
        return
    fd = os.open(p, os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            slots = json.loads(os.read(fd, 1_000_000).decode() or "{}")
        except ValueError:
            slots = {}
        slots.pop(f"{instrument}:{mint}", None)
        os.lseek(fd, 0, 0); os.ftruncate(fd, 0)
        os.write(fd, json.dumps(slots).encode()); os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def kelly_clip_usd(win_prob: float, win_loss_ratio: float, bankroll_usd: float = BANKROLL_USD) -> float:
    """Conservative fractional-Kelly clip, capped at MAX_KELLY_FRAC of bankroll. USE ONLY after a real
    forward PASS — never on an unvalidated arm (where the honest clip stays the fixed $10)."""
    if win_loss_ratio <= 0:
        return 0.0
    edge = win_prob - (1 - win_prob) / win_loss_ratio        # full-Kelly fraction
    frac = max(0.0, min(edge * KELLY_FRACTION, MAX_KELLY_FRAC))
    return frac * bankroll_usd


if __name__ == "__main__":
    import tempfile
    assert abs(clip_sol(200.0) - 0.05) < 1e-9                # $10 at $200/SOL = 0.05 SOL
    ok, _ = exit_capacity_ok(10.0, 500.0); assert ok         # $10 of $500 capacity = 2% <= 5%
    bad, _ = exit_capacity_ok(10.0, 100.0); assert not bad   # $10 of $100 = 10% > 5%
    blind, _ = exit_capacity_ok(10.0, None); assert not blind
    with tempfile.TemporaryDirectory() as d:
        pf = pathlib.Path(d) / "portfolio.json"
        assert try_acquire_primary("A", "m1", pf)            # slot 1
        assert try_acquire_primary("B", "m2", pf)            # slot 2
        assert not try_acquire_primary("A", "m3", pf)        # 3rd refused (global max 2)
        assert try_acquire_primary("A", "m1", pf)            # idempotent re-claim ok
        release_primary("A", "m1", pf)
        assert try_acquire_primary("A", "m3", pf)            # freed a slot -> now ok
    assert kelly_clip_usd(0.6, 2.0) <= MAX_KELLY_FRAC * BANKROLL_USD
    assert kelly_clip_usd(0.3, 1.0) == 0.0                   # no edge -> no size
    print("sizer.py self-check OK: $10 clip, 5% exit-cap gate, global max-2 flock slots, capped Kelly")
