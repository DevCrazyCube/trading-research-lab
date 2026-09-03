# Answer: no family has a defensible prior Sharpe above 0.9 — and the power ceiling is dead

The operator asked for the falsification test I named. It ran. **One half of my claim was wrong.**

## The power ceiling IS falsified

I claimed the binding constraint was that 8 years of data cannot establish a Sharpe below ~0.879. That was
wrong, because long free survivorship-complete data exists and is now mirrored locally:

| dataset | span | independent years | MDE_Sharpe |
|---|---|---|---|
| Ken French Data Library (CRSP, incl. delistings) | 1926-07 → 2026-06 | **100.0** | **0.249** |
| AQR Century of Factor Premia | 1926-07 → 2026-02 | 99.7 | 0.249 |
| AQR TSMOM Factors | 1985-01 → 2026-05 | 41.4 | 0.386 |
| Cboe option benchmarks | 1986-06 → | 40.2 (19 live) | 0.392 |

**0.249, not 0.879 — 3.5× more resolving power.** The design was never the wall. I was wrong about that,
and the operator was right to push.

## And with that power, the answer is still no

Every load-bearing number below was recomputed from the raw files, not quoted:

| family | discovery | post-publication | verdict |
|---|---|---|---|
| Multi-asset TSMOM | **1.411** (1985–2009) | **0.402** (2010–2026) | 72% decay, worse than McLean-Pontiff's 58% |
| AQR's own live trend fund (AQMIX) | — | **0.336** (16.4y) | SPY over the same window: **0.92** |
| Cross-asset carry | 0.604 (pre-2012) | **−0.069** OOS | dead |
| Index put-writing (Cboe PUT) | — | 0.556 total, **alpha +0.01%/yr (t=0.01)** | de-levered beta, not alpha |
| Turn-of-month | t=**7.00** over 101y | t=**+0.05** since 2006 | dead, totally |
| 10-month trend overlay | 0.621 vs 0.449 buy-and-hold (99y) | **0.885 vs 0.934** since 2012 | lost to doing nothing |
| Betting-against-beta | 1.01 | costs cut ~60%; VW version 0.80 | commits $1.05/dollar to the bottom 1% of market cap |

**The two families that would have printed above 0.9 on a century of data — turn-of-month (t=7.00) and
cross-sectional momentum — are exactly the two the same century shows dead post-publication.** Lifting the
ceiling did not find an edge. It made the absence legible.

A sign-flip worth its own line: four Cboe option-writing indices show positive alpha in their **backfilled**
history and negative alpha **live** (BXY +2.58% → −0.47%; BXMD +1.96% → −1.16%; CNDR +2.60% → −2.04%;
WPUT +1.28% → **−4.22%/yr, t=−2.72**). 100% of the alpha lives in the part that was never traded.

## The best honest answer, stated as a prior

**Multi-asset trend following as a diversifying sleeve against an equity core** — the only family clearing
all four bars (published, independently replicated by a competitor, post-publication evidence measured,
net-of-cost figures published by the manager itself). It has a structurally negative equity correlation
(−0.18 to −0.21, and **still −0.206 in the worst equity decile** — the hedge improved as the return decayed).

    trend sleeve, live net           0.34   (AQMIX, 16.4y; AQR's own page says 0.26)
    equity sleeve, 100-year          0.454
    combination, pre-tax             0.52 – 0.63
    after Dutch box 3                0.30 – 0.47
    equity alone after box 3        ~0.34

**By the operator's own decision rule — fund only above 0.9 — this is a pre-registered KILL.**

## The epistemic finding that outlasts the answer

Free data verifies **existence** at t = 4.5–14. But the post-publication window is only 13–17 years
(MDE 0.61–0.68), and every measured post-publication Sharpe (0.2–0.4) sits **below its own detection floor**.

> Free data can tell you a premium **was** real. It cannot tell you whether it has **broken** — and that is
> the only question that matters for deployment. **More data cannot fix this: the calendar has run out.**

Stated symmetrically, because honesty cuts both ways: at 13–17 years those series cannot statistically
*reject* 0.9 either (QSPIX z = −1.31, SPY z = −1.55). Non-rejection is not evidence. The prior must be the
point estimate, and every point estimate is 0.3–0.6.

## The trap to avoid

US equities returned a **0.895** Sharpe since 2010 against a **0.454** hundred-year value. Any strategy
Sharpe computed on a post-2010 sample is mostly that borrowed beta wearing a strategy's name. Never
substitute the recent equity Sharpe for the century value in a sizing calculation.

## Operational note

The AQR long-history files are **delisted from AQR's own dataset index page but still served at their direct
URLs**. The entire long-history case for two families rested on two undocumented vendor-owned links. All
four datasets are now mirrored to `research/data/longhistory/` with SHA256SUMS.txt.
