#!/usr/bin/env python3
"""Synthetic self-test for the momentum-surge detector (signals.py).

Deterministic, offline, read-only. Proves, on hand-built Bar sequences:
  A. a genuine surge (rising price + buy-dominated + enough trades + liquid) FIRES exactly once,
  B. a flat / chop tape does NOT fire,
  C. a sell-dominated pump does NOT fire (buy_frac gate),
  D. a thin (illiquid) surge is REJECTED by the liquidity gate,
  E. debounce: one surge fires once, a fresh (re-armed) surge later fires again,
  F. the position_open hook suppresses a would-be signal.

Run (from repo root):  python3 -m scripts.trading_bot.sniper.signals_selftest
(Run as a module, not a bare path: the package's local `types.py` shadows stdlib `types` when its own
directory is placed on sys.path[0], which breaks a plain-script launch. `-m` avoids that.)
Exit code 0 = all pass, 1 = a failure.
"""
from __future__ import annotations

import sys
from typing import List, Optional

try:
    from .types import Bar, EntrySignal
    from .signals import SurgeConfig, SurgeDetector, params_grid
except ImportError:  # run as a plain script
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from types import Bar, EntrySignal  # type: ignore
    from signals import SurgeConfig, SurgeDetector, params_grid  # type: ignore


# --------------------------------------------------------------------------- bar factory
def bar(t: int, price: float, *, buy_usd: float, sell_usd: float,
        buys: int, sells: int, prev: float | None = None) -> Bar:
    """Build a 1s bar. open=prev price (defaults to `price`), close=price; v = buy+sell USD."""
    o = prev if prev is not None else price
    v = buy_usd + sell_usd
    return Bar(
        t=t, o=o, h=max(o, price), l=min(o, price), c=price, v=v,
        buys=buys, sells=sells, buy_vol=buy_usd, sell_vol=sell_usd, dex="Pumpswap",
    )


def rising_buy_surge(mint: str, t0: int, n: int, start: float, step_bps: float,
                     usd_per_bar: float, buy_frac: float, trades_per_bar: int) -> List[Bar]:
    """A clean ramp: price rises step_bps/bar, buy-dominated, `usd_per_bar` USD, `trades_per_bar` trades."""
    bars: List[Bar] = []
    price = start
    prev = start
    for i in range(n):
        price = prev * (1.0 + step_bps / 10_000.0)
        b_usd = usd_per_bar * buy_frac
        s_usd = usd_per_bar * (1.0 - buy_frac)
        buys = max(1, round(trades_per_bar * buy_frac))
        sells = max(0, trades_per_bar - buys)
        bars.append(bar(t0 + i, price, buy_usd=b_usd, sell_usd=s_usd,
                        buys=buys, sells=sells, prev=prev))
        prev = price
    return bars


def feed(det: SurgeDetector, mint: str, bars: List[Bar]) -> List[EntrySignal]:
    """A Bar has no mint field, so the caller supplies it (mirrors one-file-per-mint bar cache)."""
    out: List[EntrySignal] = []
    for b in bars:
        sig = det.update(b, mint=mint)
        if sig is not None:
            out.append(sig)
    return out


# --------------------------------------------------------------------------- checks
_PASS = 0
_FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        _PASS += 1
    else:
        _FAIL += 1
    line = f"  [{tag}] {name}"
    if detail:
        line += f"  ({detail})"
    print(line)


# Config used for A-F. Modest thresholds so the synthetic tapes are unambiguous.
CFG = SurgeConfig(
    window_s=30.0, surge_bps=400.0, min_buy_frac=0.65,
    min_trades=12, min_liq_usd_per_s=15.0, cooldown_s=60.0, idle_evict_s=300.0,
)


def test_A_genuine_surge_fires() -> None:
    det = SurgeDetector(CFG)
    # 10 bars, +100 bps/bar => ~+1050 bps over window; $60/bar => $600/30s = $20/s > 15; buy_frac 0.8; 4 trades/bar => 40.
    bars = rising_buy_surge("MINT_A", 1000, 10, 1.0e-6, step_bps=100.0,
                            usd_per_bar=60.0, buy_frac=0.80, trades_per_bar=4)
    sigs = feed(det, "MINT_A", bars)
    check("A genuine surge FIRES exactly once", len(sigs) == 1, f"{len(sigs)} signal(s)")
    if sigs:
        s = sigs[0]
        ok = (
            s.mint == "MINT_A" and s.surge_bps >= CFG.surge_bps and s.buy_frac >= CFG.min_buy_frac
            and s.liq_usd_per_s >= CFG.min_liq_usd_per_s and s.ref_price_usd > 0
            and s.venue == "Pumpswap" and "surge" in s.reason
        )
        check("A EntrySignal fields well-formed", ok,
              f"surge={s.surge_bps:.0f}bps buy_frac={s.buy_frac:.2f} liq=${s.liq_usd_per_s:.1f}/s")


def test_B_flat_chop_no_fire() -> None:
    det = SurgeDetector(CFG)
    # Price oscillates around 1.0e-6, no net rise; plenty of volume/trades/buys.
    bars: List[Bar] = []
    prev = 1.0e-6
    for i in range(20):
        price = 1.0e-6 * (1.005 if i % 2 == 0 else 0.995)  # chop, no trend
        bars.append(bar(1000 + i, price, buy_usd=40.0, sell_usd=20.0, buys=3, sells=2, prev=prev))
        prev = price
    sigs = feed(det, "MINT", bars)
    check("B flat/chop tape does NOT fire", len(sigs) == 0, f"{len(sigs)} signal(s)")


def test_C_sell_dominated_no_fire() -> None:
    det = SurgeDetector(CFG)
    # Price ramps up hard, liquid, many trades -- but SELL-dominated (buy_frac 0.30 < 0.65).
    bars = rising_buy_surge("MINT_C", 1000, 10, 1.0e-6, step_bps=100.0,
                            usd_per_bar=60.0, buy_frac=0.30, trades_per_bar=4)
    sigs = feed(det, "MINT_C", bars)
    check("C sell-dominated pump does NOT fire", len(sigs) == 0, f"{len(sigs)} signal(s)")


def test_D_thin_surge_rejected() -> None:
    det = SurgeDetector(CFG)
    # Genuine buy-dominated ramp, but THIN: $6/bar => $60/30s = $2/s < 15 liquidity floor.
    # Keep trades high so ONLY the liquidity gate can be the reason it's rejected.
    bars = rising_buy_surge("MINT_D", 1000, 10, 1.0e-6, step_bps=100.0,
                            usd_per_bar=6.0, buy_frac=0.80, trades_per_bar=4)
    sigs = feed(det, "MINT_D", bars)
    # Confirm every OTHER gate passed, so the rejection is specifically the liquidity gate.
    m = det.metrics("MINT_D")
    other_gates_ok = (m is not None and m["surge_bps"] >= CFG.surge_bps
                      and m["buy_frac"] >= CFG.min_buy_frac and m["trades"] >= CFG.min_trades)
    liq_below = m is not None and m["liq_usd_per_s"] < CFG.min_liq_usd_per_s
    check("D thin surge REJECTED by liquidity gate",
          len(sigs) == 0 and other_gates_ok and liq_below,
          f"liq=${m['liq_usd_per_s']:.1f}/s (< {CFG.min_liq_usd_per_s}), other gates ok={other_gates_ok}")


def test_E_debounce_single_then_refire() -> None:
    det = SurgeDetector(CFG)
    # First surge.
    bars1 = rising_buy_surge("MINT_E", 1000, 12, 1.0e-6, step_bps=100.0,
                             usd_per_bar=60.0, buy_frac=0.80, trades_per_bar=4)
    sigs1 = feed(det, "MINT_E", bars1)
    check("E surge fires once despite many qualifying bars", len(sigs1) == 1, f"{len(sigs1)} signal(s)")

    # Quiet gap that flushes the window (past window_s) so the mint RE-ARMS, then a second surge later.
    last_price = bars1[-1].c
    t_gap = bars1[-1].t + int(CFG.window_s) + 200  # > cooldown and > window: fully re-armed
    bars2 = rising_buy_surge("MINT_E", t_gap, 12, last_price, step_bps=100.0,
                             usd_per_bar=60.0, buy_frac=0.80, trades_per_bar=4)
    sigs2 = feed(det, "MINT_E", bars2)
    check("E a fresh re-armed surge fires again", len(sigs2) == 1, f"{len(sigs2)} signal(s)")


def test_F_position_hook_suppresses() -> None:
    open_mints = {"MINT_F"}
    det = SurgeDetector(CFG, position_open=lambda m: m in open_mints)
    bars = rising_buy_surge("MINT_F", 1000, 10, 1.0e-6, step_bps=100.0,
                            usd_per_bar=60.0, buy_frac=0.80, trades_per_bar=4)
    sigs = feed(det, "MINT_F", bars)
    check("F position_open hook suppresses signal", len(sigs) == 0, f"{len(sigs)} signal(s)")


def test_G_grid_sane() -> None:
    grid = params_grid()
    ok = len(grid) >= 3 and all(isinstance(c, SurgeConfig) for c in grid.values())
    check("G params grid exposes >=3 named configs", ok, f"{sorted(grid)}")


def main() -> int:
    print("signals_selftest -- synthetic momentum-surge detector proof")
    for fn in (test_A_genuine_surge_fires, test_B_flat_chop_no_fire, test_C_sell_dominated_no_fire,
               test_D_thin_surge_rejected, test_E_debounce_single_then_refire,
               test_F_position_hook_suppresses, test_G_grid_sane):
        fn()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
