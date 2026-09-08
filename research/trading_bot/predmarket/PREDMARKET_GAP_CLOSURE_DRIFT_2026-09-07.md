# PREDMARKET1: a continuous interim read on our own book — the market has closed +7% of the gap we claimed

**Date:** 2026-09-07 (predmarket tick, hour 21, CHUNK D)
**Status:** NEW MONITOR PRE-REGISTERED + first read taken. No estimate frozen this tick (abstention
logged). No spec edited, no bet, no money. Read-only.
**One line:** two weeks after freezing 73 probability estimates, the market has moved
**+0.073 ± 0.083** of the way toward them (t=+0.88, 36/73 moved toward us) — consistent with **zero
information**, though not yet powered to exclude a small positive.

## 1. Why this measurement exists

PREDMARKET1 has two known, documented problems and no live evidence between now and year-end:

* `PREDMARKET_CORRELATED_BOOK_2026-09-06.md` — the open book is 69% a single longshot-fade cluster,
  and `kill_switch.N_min=50` is crossed only when a **24-market lump settles on 2026-12-31**, i.e. on
  one draw of one variable ("was 2026 a quiet year?"). The scorer's i.i.d. `se` would report that as
  a significant pass. **First verdict is therefore both far away and structurally untrustworthy.**
* `PREDMARKET_STALE_PRIOR_INVERSION_2026-09-06.md` — every non-news edge thesis is dead, and the last
  one is *inverted*: ranking candidates by `|q_agent − p_market|` ranks them by agent staleness.

So the instrument is in a state where it cannot honestly add positions and cannot learn anything
until December. This monitor is the cheap way out of that gap: **price drift after freeze is
information that arrived after our commitment**, it accumulates continuously rather than in one lump,
and it costs one read-only pull.

## 2. The metric (pre-registered BEFORE the numbers below were taken as evidence)

For each still-open frozen estimate, with `p0` = p_market at freeze, `q` = q_agent, `p1` = p_market now:

```
frac_closed = (p1 - p0) / (q - p0)      winsorised to [-2, +2]
```

`0` = the market has not come toward us at all. `1` = it has fully converged to our number.
Null hypothesis (our estimates carry no information): **E[frac_closed] = 0**.
Implementation: `scripts/trading_bot/predmarket_drift_monitor.py` (read-only; re-runnable any tick).

**Declared limits, stated before the read:**
1. Drift is **NOT** resolution. A fade can be correct at settlement while the price never moves. This
   monitor can never *pass* the instrument; it can only build a case that it is dead early.
2. The naive i.i.d. `se` printed here is **optimistic** for the same clustering reason as the scorer.
   Treat the confidence bound as an upper bound on our confidence, not a real one.
3. Estimates whose market has closed/vanished drop out (1 of 74 today) — a small survivorship notch.

**Kill-condition (pre-registered):** if, at the **2026-11-03** read (the 11-market close block, by
which point the book has had ~10 weeks of drift), the ALL-estimates
`upper-95 bound on mean frac_closed < 0.10`, then PREDMARKET1's discretionary channel is declared
**dead on leading evidence** and no further prior-driven estimates are frozen — the instrument runs
to 2026-12-31 as a pure calibration logger only. Nothing about the frozen kill switch changes; this
is a separate, additional, one-way brake.

## 3. First read — 2026-09-07 (freezes span 2026-08-24 … 09-05)

| slice | n | mean gap closed | se | t | lo95 | moved toward us |
|---|---|---|---|---|---|---|
| longshot fade (`q<p0`, `p0<0.25`) | 51 | **+0.028** | 0.081 | +0.35 | −0.105 | 25/51 |
| everything else | 22 | +0.176 | 0.203 | +0.87 | −0.158 | 11/22 |
| **ALL** | **73** | **+0.073** | 0.083 | +0.88 | −0.063 | **36/73** |

Upper-95 bound on ALL = **+0.209**, so the kill-condition is **NOT** met today: the data cannot yet
exclude a modest positive drift. That is the honest statement. What it *does* exclude is any claim of
a fat, obvious edge: after two weeks a book of 73 supposedly-mispriced markets has moved 7% of the
way to us, half of it moved away, and the load-bearing 69% cluster is at **+0.028 — flat**.

Largest single mover *against* us is instructive rather than unlucky: Kreiss-Tomkins (AK governor)
was faded at 0.315→0.250 and now trades **0.589** — a 27-point move against, i.e. exactly the
post-cutoff-news mechanism the stale-prior inversion doc predicted, showing up in live prices.

## 4. What this changes

* **Nothing is frozen this tick.** An abstention is logged in `PREDMARKET_PREREGISTRATION_LOG.jsonl`.
  Adding a 74th prior-driven estimate would deepen a 69%-correlated book that a leading indicator now
  shows to be flat.
* **The instrument now has a clock that ticks before December.** Re-run the monitor each predmarket
  tick; the binding read is 2026-11-03.
* **Programme-level:** this is consistent with the standing verdict that the agent's non-news priors
  are not a tradeable information source. It does not touch the equities line.

## 5. Reproduce

```
python -m scripts.trading_bot.predmarket_drift_monitor           # pulls fresh
python -m scripts.trading_bot.predmarket_drift_monitor pull.json # re-read a saved pull
```
