# T32 — SPX box-spread lending rate, REGULAR TRADING HOURS (final probe)

**Status:** COMPLETE  
**Script:** `scripts/trading_bot/t32_box_rth.py` (detached; capture + analysis in one process)  
**Task:** `T32_spx_box_rth_probe` — third and FINAL probe of the box.

## Pre-registered protocol (frozen at launch, before any RTH quote was read)

```
(frozen before any RTH quote is read):
  * Primary expiry = 2027-08-20 (~1.0 y). Secondary: 2027-06-17, 2027-12-17 (rate
    curve shape) and 2026-12-18 (direct comparison with T25's closed-market read).
  * Box(K1<K2) = +C(K1) -C(K2) -P(K1) +P(K2); pays K2-K1 at expiry (European, cash).
    Lender BUYS the box: mid cost uses four mids; EXECUTABLE cost = ask C1 - bid C2
    - bid P1 + ask P2 (crossing all four spreads, no leg legged).
  * Rate = simple annualised: ((K2-K1)/cost - 1) / T * 100, T in ACT/365 years.
  * Pair filter: all four legs two-sided (bid>0, ask>0) with quote timestamp on the
    capture day; both strikes within [0.70, 1.30] x parity-implied forward; width
    500 <= K2-K1 <= 2000 index points.
  * Per snapshot per expiry: n_pairs, p25 / median / p75 / p90 of mid and executable.
    Session number = MEDIAN across snapshots of the per-snapshot MEDIAN (same estimand
    T25 reported). p90 is reported as context ("a lender cherry-picking the best
    decile of pairs") but the verdict is on the median.
  * Benchmark: latest FRED DTB3 (3-month T-bill, %), fetched live, cache fallback.
  * KILL-CONDITION (frozen in agenda T32): primary-expiry session-median EXECUTABLE
    four-leg rate below the T-bill => the box is PERMANENTLY DEAD, no fourth probe.
    Only if it clears T-bills does a next step exist (and it would be a design, not
    a trade).
```

Launch record: {"launched_utc": "2026-08-24T13:07:17Z", "capture_start_utc": "2026-08-24T13:30:00Z", "duration_min": 60, "interval_min": 5, "expiries": ["2027-08-20", "2027-06-17", "2027-12-17", "2026-12-18"], "primary": "2027-08-20", "band": [0.7, 1.3], "width": [500.0, 2000.0]}

## Result

T-bill benchmark: **3.71 %** (FRED DTB3 2026-08-20 (live)). Snapshots: 13 clean of 13 taken, 2026-08-24T13:30:05Z -> 2026-08-24T14:30:02Z UTC. Market open at first snapshot: True.

| expiry | T (y) | snaps | pairs/snap | mid median % | exec median % | exec p90 % | best-snap exec median % | exec − T-bill (pp) | p90 exec − T-bill (pp) |
|---|---|---|---|---|---|---|---|---|---|
| 2027-08-20 (primary) | 0.989 | 13 | 5643.0 | 4.323 | 2.958 | 5.314 | 3.26 | -0.752 | 1.604 |
| 2027-06-17 | 0.814 | 13 | 5789.0 | 4.253 | 2.784 | 5.577 | 3.124 | -0.926 | 1.867 |
| 2027-12-17 | 1.315 | 13 | 1570.0 | 4.376 | 3.287 | 5.113 | 3.457 | -0.423 | 1.403 |
| 2026-12-18 | 0.318 | 13 | 28386.0 | 3.065 | 0.323 | 6.013 | 0.637 | -3.387 | 2.303 |

## Verdict (mechanical, from the frozen rule)

**BOX PERMANENTLY DEAD — executable four-leg rate below T-bills during RTH (third probe; no fourth)**

Primary expiry session-median executable 2.958 % vs T-bill 3.71 % (-0.75 pp). Even the p90 executable pair sits at 5.314 % (1.60 pp vs T-bill). Mid 4.323 % (0.61 pp). The estimand is a rate level, so power is not the issue.

Comparison with T25 (market closed, 2026-08-19): 1y executable +0.06 % = −3.65 pp vs T-bills; mid +0.37 pp over. RTH read on the primary expiry: executable -0.752 pp, mid 0.613 pp.

