#!/usr/bin/env python3
"""strategy_selftest.py — synthetic proofs for the CONVEXITY strategy module.

Read-only, deterministic, no wallet / no orders / no network. Feeds hand-built EntrySignals + Bars +
simulated executor Fills through ConvexityStrategy and asserts every claimed behavior:

  T1  entry sizes correctly (fractional * inverse-vol) and returns a buy/entry intent, frozen.
  T2  bankroll: per-mint cap, concurrency cap, and gross-exposure budget all REFUSE.
  T3  sizing SHRINKS as concurrent gross exposure grows.
  T4  a winner that keeps running is HELD, then exits on the TRAILING give-back with a large +R.
  T5  a flow-flip (buy fraction below floor for k consecutive s, after min hold) triggers an exit.
  T6  the WIDE catastrophe backstop fires on a crash (labeled 'catastrophe', ~ -1R).
  T7  max-hold caps a stagnant position.

Run: python3 strategy_selftest.py
"""
from __future__ import annotations

# The sibling contract file is named types.py (same as the stdlib module `types`). Running this script
# auto-prepends its own directory to sys.path, which would make `import types` (done lazily by
# enum/dataclasses/importlib) resolve to the LOCAL file and break the interpreter. os/sys are already
# cached at startup, so importing them is safe; strip our dir from sys.path BEFORE any other import,
# then load the sibling files by explicit file path via importlib (no sys.path needed).
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path[:] = [p for p in _sys.path if _os.path.abspath(p or ".") != _HERE]

import importlib.util as _ilu  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


def _load(mod_name: str, filename: str):
    spec = _ilu.spec_from_file_location(mod_name, _os.path.join(_HERE, filename))
    mod = _ilu.module_from_spec(spec)
    # register before exec: dataclasses (and others) resolve cls.__module__ via sys.modules.
    _sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_types = _load("_sniper_types", "types.py")
_strat = _load("_sniper_strategy", "strategy.py")

Bar = _types.Bar
EntrySignal = _types.EntrySignal
Fill = _types.Fill
Position = _types.Position
ConvexityStrategy = _strat.ConvexityStrategy
ConvexityConfig = _strat.ConvexityConfig
PRESETS = _strat.PRESETS
build_strategy = _strat.build_strategy

# a fixed clock so the freeze stamp (and thus the whole run) is deterministic
FIXED_NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
CLOCK = lambda: FIXED_NOW  # noqa: E731

PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond), detail))
    print(f"  [{PASS if cond else FAIL}] {name}" + (f" :: {detail}" if detail else ""))


def sig(mint: str, ts: float, price: float, surge_bps: float = 300.0,
        buy_frac: float = 0.85, liq: float = 5000.0) -> EntrySignal:
    return EntrySignal(mint=mint, ts=ts, ref_price_usd=price, surge_bps=surge_bps,
                       buy_frac=buy_frac, liq_usd_per_s=liq, venue="Pumpfun",
                       reason=f"surge {surge_bps:.0f}bps")


def fill(intent, price=None, ts=None) -> Fill:
    """Simulate the executor: fill at the intent's ref price (self-test only; real fills come from
    execution.py with slippage/toll)."""
    return Fill(mint=intent.mint, side=intent.side,
                ts=ts if ts is not None else intent.ts,
                price_usd=price if price is not None else intent.ref_price_usd,
                usd_size=intent.usd_size, toll_bps=0.0, slip_bps=0.0, tip_usd=0.0, dry_run=True)


def bar(mint, t, o, h, l, c, buy_vol, sell_vol) -> Bar:
    buys = 10 if buy_vol > 0 else 0
    sells = 10 if sell_vol > 0 else 0
    return Bar(t=t, o=o, h=h, l=l, c=c, v=buy_vol + sell_vol,
               buys=buys, sells=sells, buy_vol=buy_vol, sell_vol=sell_vol, dex="Pumpswap")


# ============================================================================
def t1_entry_sizes_and_freezes():
    print("\nT1 entry sizes correctly + frozen intent")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    # V2: explicit $1,000 paper equity, max_frac 0.02 => $20; normal surge => scale 1.0.
    intent = s.on_signal(sig("MINT_A", ts=1000.0, price=1.0, surge_bps=300.0))
    check("returns an intent", intent is not None)
    check("side buy, tag entry", intent.side == "buy" and intent.tag == "entry", intent.tag)
    check("base fractional size == $20", abs(intent.usd_size - 20.0) < 1e-9, f"{intent.usd_size}")
    # inverse-vol: a violent surge (600bps) => scale 0.5 => $10
    s2 = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    i2 = s2.on_signal(sig("MINT_B", ts=1000.0, price=1.0, surge_bps=600.0))
    check("inverse-vol shrinks on violent surge ($10)", abs(i2.usd_size - 10.0) < 1e-9, f"{i2.usd_size}")
    # a mild surge (150bps) => scale 2.0 clamped to hi 1.5 => $30
    s3 = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    i3 = s3.on_signal(sig("MINT_C", ts=1000.0, price=1.0, surge_bps=150.0))
    check("inverse-vol grows on mild surge, clamped hi ($30)", abs(i3.usd_size - 30.0) < 1e-9, f"{i3.usd_size}")
    # freeze: opening the fill carries a 64-hex sha256 + the UTC stamp
    pos = s.apply_fill(fill(intent))
    check("position opened", pos is not None and pos.is_open)
    check("entry frozen (sha256)", len(pos.frozen_sha256) == 64 and all(ch in "0123456789abcdef" for ch in pos.frozen_sha256))
    check("freeze UTC stamped before outcome", pos.meta.get("frozen_utc") == FIXED_NOW.isoformat())


def t2_bankroll_caps_refuse():
    print("\nT2 bankroll / concurrency / per-mint caps refuse")
    # per-mint cap
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    i1 = s.on_signal(sig("DUP", 1000.0, 1.0))
    i2 = s.on_signal(sig("DUP", 1001.0, 1.1))  # same mint still pending
    check("per-mint one-position cap refuses 2nd", i1 is not None and i2 is None)

    # concurrency cap: tiny bankroll-independent cap
    cfg = ConvexityConfig(name="cc", initial_bankroll_usd=1000.0, max_frac_per_trade=0.001,
                          max_concurrent_positions=3, max_gross_exposure_frac=1.0,
                          min_trade_notional=1e-6, inverse_vol=False)
    s2 = ConvexityStrategy(cfg, clock=CLOCK)
    opened = 0
    for k in range(5):
        it = s2.on_signal(sig(f"M{k}", 1000.0 + k, 1.0))
        if it is not None:
            s2.apply_fill(fill(it))
            opened += 1
    check("concurrency cap stops at 3", opened == 3, f"opened={opened}")

    # gross-exposure budget: 50% of bankroll only
    cfg2 = ConvexityConfig(name="cg", initial_bankroll_usd=10.0, max_frac_per_trade=0.20,
                           max_concurrent_positions=100, max_gross_exposure_frac=0.50,
                           min_trade_notional=1e-6, inverse_vol=False)
    s3 = ConvexityStrategy(cfg2, clock=CLOCK)
    total = 0.0
    got = 0
    for k in range(20):
        it = s3.on_signal(sig(f"G{k}", 1000.0 + k, 1.0))
        if it is None:
            break
        s3.apply_fill(fill(it))
        total += it.usd_size
        got += 1
    budget = 10.0 * 0.50
    check("gross exposure never exceeds budget", total <= budget + 1e-9, f"total={total} budget={budget}")
    check("budget is fully deployed then refuses", abs(total - budget) < 1e-9 and got >= 1, f"total={total} got={got}")


def t3_sizing_shrinks_with_exposure():
    print("\nT3 sizing shrinks as concurrent exposure grows")
    # near the budget edge, each successive trade should be clamped smaller by the remaining budget.
    cfg = ConvexityConfig(name="shrink", initial_bankroll_usd=10.0, max_frac_per_trade=0.20,
                          max_concurrent_positions=100, max_gross_exposure_frac=0.50,
                          min_trade_notional=1e-6, inverse_vol=False)
    s = ConvexityStrategy(cfg, clock=CLOCK)
    sizes = []
    for k in range(4):
        it = s.on_signal(sig(f"S{k}", 1000.0 + k, 1.0))
        if it is None:
            break
        s.apply_fill(fill(it))
        sizes.append(it.usd_size)
    # base = 2.0 each; budget = 5.0. Expect 2.0, 2.0, 1.0 (clamped by remaining), then refuse.
    check("first two at full base 2.0", len(sizes) >= 3 and abs(sizes[0] - 2.0) < 1e-9 and abs(sizes[1] - 2.0) < 1e-9, f"{sizes}")
    check("third clamped smaller (1.0)", len(sizes) >= 3 and sizes[2] < sizes[1] and abs(sizes[2] - 1.0) < 1e-9, f"{sizes}")
    check("monotonic non-increasing", all(sizes[i] >= sizes[i + 1] for i in range(len(sizes) - 1)), f"{sizes}")


def t4_winner_held_then_trails():
    print("\nT4 winner runs -> HELD -> exits on trailing give-back with large +R")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)  # trail 3500bps=35%, cat 0.60
    it = s.on_signal(sig("RUN", ts=0.0, price=1.0, surge_bps=300.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    # strong buy-dominated run: 1 -> 5 over many seconds, no reversal. Should be HELD the whole way.
    prices = [1.2, 1.6, 2.1, 2.8, 3.6, 4.4, 5.0]
    held_all = True
    t = 1
    last_c = 1.0
    for p in prices:
        out = s.on_bar("RUN", bar("RUN", t, o=last_c, h=p, l=last_c * 0.99, c=p, buy_vol=900.0, sell_vol=100.0))
        if out:
            held_all = False
        last_c = p
        t += 1
    check("winner HELD through the run (no exit)", held_all and len(s.open_positions()) == 1)
    peak = s.open_positions()[0].peak_price
    check("peak tracked to top (5.0)", abs(peak - 5.0) < 1e-9, f"peak={peak}")
    # now a give-back that trips the 35% trail: peak 5.0 -> trail level 3.25; a bar low at 3.2 trips it.
    out = s.on_bar("RUN", bar("RUN", t, o=5.0, h=5.0, l=3.2, c=3.3, buy_vol=300.0, sell_vol=700.0))
    check("trailing give-back fires an exit", len(out) == 1 and out[0].tag == "exit:trail", str([o.tag for o in out]))
    exit_price = out[0].ref_price_usd  # trail level = 5.0 * 0.65 = 3.25
    pos = s.apply_fill(fill(out[0], price=exit_price, ts=t))
    # R vs risk unit = entry_price * catastrophe_frac = 1.0*0.60 = 0.60; (3.25-1.0)/0.60 = 3.75R
    check("realized R large & positive (~3.75R)", pos.realized_r is not None and pos.realized_r > 3.0, f"R={pos.realized_r:.3f}")
    check("position closed & reasoned", not pos.is_open and pos.exit_reason == "exit:trail")


def t5_flow_flip_exit():
    print("\nT5 flow-flip (buy fraction collapses for k consecutive s) triggers exit")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)  # flow_exit_frac 0.45, k 5, min_hold 20
    it = s.on_signal(sig("FLOW", ts=0.0, price=1.0, surge_bps=300.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    # hold past min_hold_s (20) with healthy buy flow, price drifts up modestly (won't trip 35% trail)
    t = 1
    while t <= 22:
        s.on_bar("FLOW", bar("FLOW", t, o=1.0, h=1.05, l=1.0, c=1.02, buy_vol=800.0, sell_vol=200.0))
        t += 1
    check("still open after healthy-flow hold", len(s.open_positions()) == 1)
    # now buy fraction collapses to ~0.2 (< 0.45) for 5 consecutive seconds; price barely moves (no trail)
    out = []
    for _ in range(5):
        out = s.on_bar("FLOW", bar("FLOW", t, o=1.0, h=1.02, l=0.99, c=1.0, buy_vol=200.0, sell_vol=800.0))
        t += 1
        if out:
            break
    check("flow reversal fires after k consecutive low-buy s", len(out) == 1 and out[0].tag == "exit:flow", str([o.tag for o in out]))
    pos = s.apply_fill(fill(out[0], ts=t))
    check("closed with flow reason", not pos.is_open and pos.exit_reason == "exit:flow")


def t6_catastrophe_backstop():
    print("\nT6 wide catastrophe backstop fires on a crash (~ -1R)")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)  # catastrophe 0.60 => level 0.40
    it = s.on_signal(sig("RUG", ts=0.0, price=1.0, surge_bps=300.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    # a single bar craters straight through everything to -70% low
    out = s.on_bar("RUG", bar("RUG", 5, o=1.0, h=1.0, l=0.30, c=0.30, buy_vol=50.0, sell_vol=950.0))
    check("catastrophe fires (not labeled trail)", len(out) == 1 and out[0].tag == "exit:catastrophe", str([o.tag for o in out]))
    # A gap-through is priced at the worse observed close (0.30), not the flattering 0.40 trigger.
    pos = s.apply_fill(fill(out[0], price=out[0].ref_price_usd, ts=5))
    check("gap-through exceeds -1R honestly (~ -1.167R)",
          abs(pos.realized_r - ((0.30 - 1.0) / 0.60)) < 1e-9, f"R={pos.realized_r:.3f}")


def t7_max_hold_cap():
    print("\nT7 max-hold caps a stagnant position")
    cfg = ConvexityConfig(name="mh", initial_bankroll_usd=10.0, max_frac_per_trade=0.02,
                          min_trade_notional=1e-6, max_hold_s=30,
                          trail_bps=3500.0, catastrophe_frac=0.60, flow_exit_frac=0.45,
                          flow_exit_k=5, min_hold_s=20)
    s = ConvexityStrategy(cfg, clock=CLOCK)
    it = s.on_signal(sig("FLAT", ts=0.0, price=1.0, surge_bps=300.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    # dead-flat, balanced flow (buy_frac 0.5 => not below 0.45, no flow exit), no trail, no crash
    out = []
    for t in range(1, 40):
        out = s.on_bar("FLAT", bar("FLAT", t, o=1.0, h=1.0, l=1.0, c=1.0, buy_vol=500.0, sell_vol=500.0))
        if out:
            break
    check("max-hold fires at horizon", len(out) == 1 and out[0].tag == "exit:maxhold", str([o.tag for o in out]))
    check("fired at/after max_hold_s=30", out and out[0].ts >= 30, f"t={out[0].ts if out else None}")


def t8_scope_and_equity_are_enforced():
    print("\nT8 Pump-only scope + realized losses shrink current-equity sizing")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    off_scope = sig("AMM", 0.0, 1.0)
    off_scope = EntrySignal(**{**off_scope.__dict__, "venue": "Pumpswap"})
    check("migrated AMM entry is refused in the Pump-only V2 regime", s.on_signal(off_scope) is None)

    it = s.on_signal(sig("LOSS", 0.0, 1.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    out = s.on_bar("LOSS", bar("LOSS", 1, o=1.0, h=1.0, l=0.30, c=0.30,
                                buy_vol=10.0, sell_vol=990.0))
    s.apply_fill(fill(out[0], price=out[0].ref_price_usd, ts=1))
    next_it = s.on_signal(sig("NEXT", 2.0, 1.0))
    check("loss lowers paper equity", s.book_summary()["equity_usd"] < 1000.0,
          str(s.book_summary()["equity_usd"]))
    check("next 2% order sizes from lower equity", next_it is not None and next_it.usd_size < 20.0,
          str(next_it and next_it.usd_size))


def t9_silent_timeout_has_no_fantasy_exit():
    print("\nT9 silent token timeout uses the full-loss adjudication mark")
    cfg = ConvexityConfig(name="silent", max_hold_s=5)
    s = ConvexityStrategy(cfg, clock=CLOCK)
    it = s.on_signal(sig("SILENT", 0.0, 1.0))
    s.apply_fill(fill(it, price=1.0, ts=0.0))
    stale = s.sweep_stale(6.0)
    check("silent position emits one timeout", len(stale) == 1)
    intent = stale[0][1]
    check("timeout does not reuse stale last price", intent.ref_price_usd == 0.0,
          str(intent.ref_price_usd))
    pos = s.apply_fill(fill(intent, price=0.0, ts=6.0))
    check("silent timeout is worse than -1R", pos.realized_r < -1.0, str(pos.realized_r))


def main() -> int:
    print("=" * 78)
    print("CONVEXITY STRATEGY SELF-TEST (paper / read-only / deterministic)")
    print("=" * 78)
    t1_entry_sizes_and_freezes()
    t2_bankroll_caps_refuse()
    t3_sizing_shrinks_with_exposure()
    t4_winner_held_then_trails()
    t5_flow_flip_exit()
    t6_catastrophe_backstop()
    t7_max_hold_cap()
    t8_scope_and_equity_are_enforced()
    t9_silent_timeout_has_no_fantasy_exit()

    # a small end-to-end book summary sanity print
    print("\nBook summary sanity (fresh mixed book):")
    s = ConvexityStrategy(PRESETS["convex_core"], clock=CLOCK)
    for k in range(3):
        it = s.on_signal(sig(f"BK{k}", 0.0, 1.0))
        s.apply_fill(fill(it))
    summ = s.book_summary()
    print(f"  {summ}")
    check("book_summary reports 3 open, budget respected", summ["open"] == 3 and summ["gross_exposure"] <= summ["gross_budget"] + 1e-9)

    npass = sum(1 for _, ok, _ in _results if ok)
    ntot = len(_results)
    print("\n" + "=" * 78)
    print(f"RESULT: {npass}/{ntot} checks passed")
    print("=" * 78)
    return 0 if npass == ntot else 1


if __name__ == "__main__":
    raise SystemExit(main())
