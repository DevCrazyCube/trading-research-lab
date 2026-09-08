#!/usr/bin/env python3
"""PREDMARKET1 GAP-CLOSURE DRIFT monitor -- read-only interim leading indicator.

Pre-registered 2026-09-07 (see research/trading_bot/predmarket/PREDMARKET_GAP_CLOSURE_DRIFT_2026-09-07.md).

For every still-open frozen estimate (p0 = p_market at freeze, q = q_agent), measure how much of the
gap we claimed the market has since closed:

    frac_closed = (p1 - p0) / (q - p0)     winsorised to [-2, +2]

frac_closed = 0 -> the market has not moved toward us at all; = 1 -> it has fully come round to us.
Under the null "our estimates carry no information", E[frac_closed] = 0.

This is NOT the verdict -- resolution is (kill switch, N_min=50, 2026-12-31). Drift can be flat while
the estimates are right. It is a LEADING indicator that accumulates continuously instead of in the
single 2026-12-31 world-state lump documented in PREDMARKET_CORRELATED_BOOK_2026-09-06.md, and its
naive i.i.d. se is OPTIMISTIC for exactly the same clustering reason.

Usage:  python -m scripts.trading_bot.predmarket_drift_monitor [pull.json]
        (with no argument it runs `predmarket pull --no-resolve` itself)
"""
from __future__ import annotations

import json
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl"


def _pull() -> dict:
    out = subprocess.run(
        [sys.executable, "-m", "scripts.trading_bot.predmarket", "pull", "--no-resolve", "--limit", "30000"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    if out.returncode != 0:
        raise SystemExit(f"pull failed rc={out.returncode}: {out.stderr[-500:]}")
    return json.loads(out.stdout)


def _stats(v: list[float]) -> str:
    n = len(v)
    if n < 2:
        return f"n={n} (too few)"
    mn, se = st.mean(v), st.stdev(v) / n ** 0.5
    return (f"n={n:3d} mean_gap_closed={mn:+.3f} se={se:.3f} t={mn / se:+.2f} "
            f"lo95={mn - 1.645 * se:+.3f} moved_toward={sum(1 for x in v if x > 0)}/{n}")


def main() -> None:
    pull = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else _pull()
    now = {(m["venue"], str(m["market_id"])): m for m in pull["markets"]}
    groups: dict[str, list[float]] = {"longshot_fade": [], "other": []}
    unmatched = 0
    for line in open(LOG):
        rec = json.loads(line)
        e = rec.get("estimate") or rec
        if e.get("q_agent") is None:
            continue
        m = now.get((e["venue"], str(e["market_id"])))
        if not m or m.get("p_market") is None:
            unmatched += 1
            continue
        p0, q, p1 = e["p_market"], e["q_agent"], m["p_market"]
        gap = q - p0
        if abs(gap) < 1e-9:
            continue
        frac = max(-2.0, min(2.0, (p1 - p0) / gap))
        groups["longshot_fade" if (q < p0 and p0 < 0.25) else "other"].append(frac)

    allv = groups["longshot_fade"] + groups["other"]
    print(f"PREDMARKET1 GAP-CLOSURE DRIFT  (read-only, not the verdict)  unmatched/closed={unmatched}")
    for name in ("longshot_fade", "other"):
        print(f"  {name:14s} {_stats(groups[name])}")
    print(f"  {'ALL':14s} {_stats(allv)}")
    if len(allv) >= 2:
        mn, se = st.mean(allv), st.stdev(allv) / len(allv) ** 0.5
        hi95 = mn + 1.645 * se
        print(f"  PREREG READ: upper-95 bound on mean gap closed = {hi95:+.3f} "
              f"({'BELOW' if hi95 < 0.10 else 'ABOVE'} the 0.10 no-information line)")


if __name__ == "__main__":
    main()
