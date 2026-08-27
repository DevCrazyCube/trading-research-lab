#!/usr/bin/env python3
"""Self-test for the DataProvider layer (PAPER / READ-ONLY, no orders/wallet/keys).

Run from the repo root under the memestream venv (for `websockets` on the live probe):
    scripts/trading_bot/memestream/.venv/bin/python -m scripts.trading_bot.sniper.data.selftest

It (1) proves ReplayProvider works FULLY OFFLINE on the real cache — DataProvider-conformant,
time-ordered ticks, working recent_bars — and (2) probes each live provider's healthy() without
crashing, plus a short live tick sample from whichever live provider is healthy.
"""
from __future__ import annotations

import itertools
import time

from . import (
    BitqueryProvider,
    ChainstackProvider,
    PublicRpcProvider,
    ReplayProvider,
    pick_provider,
)
from ..types import DataProvider


def _hr(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def test_replay_offline() -> bool:
    _hr("1. ReplayProvider — OFFLINE, on the real on-disk cache")
    rp = ReplayProvider()
    print(f"conforms to DataProvider Protocol: {isinstance(rp, DataProvider)}")
    print(f"healthy() (cache present): {rp.healthy()}")
    mints = rp.mints()
    print(f"cache dir: {rp.cache_dir}")
    print(f"mints in cache: {len(mints)}")
    if not mints:
        print("!! no cached mints — cannot prove replay")
        return False

    # Stream a slice and prove strict time ordering across ALL mints.
    stream = rp.stream_ticks()
    sample = list(itertools.islice(stream, 20000))
    ts = [t.ts for t in sample]
    ordered = all(b >= a for a, b in zip(ts, ts[1:]))
    distinct_mints = len({t.mint for t in sample})
    print(f"streamed ticks: {len(sample)} across {distinct_mints} mints")
    print(f"strictly time-ordered (non-decreasing ts): {ordered}")
    print("first 5 synthesized ticks:")
    for t in sample[:5]:
        print(f"  {t.ts:.3f} {t.mint[:10]:<10} {t.side:<4} "
              f"price_usd={t.price_usd:.3e} usd={t.usd:.2f}")

    # recent_bars respects the replay clock (only the past is visible).
    busiest = max(mints, key=lambda m: len(rp._bars_by_mint.get(m, [])))
    bars = rp.recent_bars(busiest, lookback_s=120)
    print(f"recent_bars({busiest[:10]}…, 120s) at clock={rp._clock}: {len(bars)} bars")
    if bars:
        b = bars[-1]
        print(f"  last bar t={b.t} o={b.o:.3e} c={b.c:.3e} v={b.v:.2f} "
              f"buys={b.buys} sells={b.sells}")
    all_le_clock = all(b.t <= rp._clock for b in bars)
    print(f"all returned bars at or before replay clock: {all_le_clock}")
    return bool(sample) and ordered and bool(bars) and all_le_clock


def test_live_probes() -> None:
    _hr("2. Live providers — healthy() probes (must not crash)")
    providers = [ChainstackProvider(), BitqueryProvider(), PublicRpcProvider()]
    healthy_names = []
    for p in providers:
        try:
            ok = p.healthy()
        except Exception as exc:  # noqa: BLE001 — a probe must never crash the selftest
            ok = f"ERROR {exc!r}"
        print(f"  {p.name:<12} conforms={isinstance(p, DataProvider)!s:<5} healthy={ok}")
        if ok is True:
            healthy_names.append(p.name)

    _hr("3. pick_provider() selection")
    chosen = pick_provider()
    print(f"pick_provider() -> {chosen.name}  (healthy live: {healthy_names or 'none'})")

    _hr("4. Live tick sample (Chainstack WS, if healthy) — READ-ONLY")
    cs = ChainstackProvider()
    if not cs.healthy():
        print("Chainstack not healthy; skipping live stream sample.")
        return
    try:
        stream = cs.stream_ticks()
        got = []
        t0 = time.time()
        for tick in stream:
            got.append(tick)
            if len(got) >= 6 or time.time() - t0 > 25:
                break
        print(f"decoded {len(got)} live pump.fun TradeTicks in {time.time()-t0:.1f}s:")
        for t in got:
            print(f"  {t.mint[:10]:<10} {t.side:<4} price_usd={t.price_usd:.3e} "
                  f"usd={t.usd:8.2f} venue={t.venue}")
        if got:
            bars = cs.recent_bars(got[-1].mint, lookback_s=300)
            print(f"recent_bars({got[-1].mint[:10]}…) from live buffer: {len(bars)} bar(s)")
    except Exception as exc:  # noqa: BLE001
        print(f"live stream sample failed gracefully: {exc!r}")


def main() -> int:
    ok = test_replay_offline()
    test_live_probes()
    _hr("RESULT")
    print(f"ReplayProvider offline proof: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
