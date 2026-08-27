# PRE-REGISTRATION — bought convexity on the T31 (Deribit) + T33 (Alpaca US) forward panels

**Written and sha256-pinned 2026-08-26 03:00 CEST (task T35, CHUNK B durable tick), on day 3 of
T31 and day 2 of T33, with ZERO numbers read from either forward panel.** Research only; no orders,
no money, no broker auth. Earliest open of the forward panels: **2026-12-23**. Until then the only
numbers anyone reads from `research/data/deribit_forward/` and `research/data/us_options_forward/`
are the manifest/ledger integrity counts.

This is the document T31 §3 and T33 §3 promised: the trigger family stated once, one bar and one
multiple-testing cost pooled over both universes, a kill-condition, and an earliest-open date.
It is written so that the December tick runs it mechanically. Nothing in it may be changed after
opening; a change before opening must be a dated amendment with the prior hash kept as audit trail
(the T33 v2 precedent).

---

## 0. TL;DR

- **Claim:** a *contractually* convex position (bought ~15-delta strangle, bounded loss = premium
  paid at the ask, uncapped payoff, held to expiry) has **positive net expectancy per unit of
  premium under a pre-named conditional trigger**, pooled over BTC/ETH (T31) and the eligible T33
  US names. Three designs, named below, plus one non-promotable control.
- **Design-window prior (DoltHub, US large caps, 2020-01 → 2026-08, §5):** unconditional bought
  strangle = **−31.8 % of premium per 2-week hold, t −19**; the three triggers lift that to
  −26 … −29 %, i.e. **none flips the sign**. Win rate ≈ 20 %, p95 ≈ +1.0–1.3× premium. Entry half-
  spread ≈ 9 % of mid (p75 17–19 %). **Stated expectation: all three designs are DEAD at the bar
  in December**, most likely as "dead" outright, possibly as "undecided-underpowered".
- **What a survivor would need:** cluster-robust t ≥ 2.5 on net mean return per unit premium,
  beating a size-matched random-entry placebo at its 99th percentile, with no single expiry
  cluster carrying > 40 % of the gains, on ≥ 40 clusters. A survivor becomes a **replication
  candidate** on the next +120 days, never a basket leg (BASKET1 is locked, hard rule 2026-08-24).
- **Kill:** if all three designs are dead at the first reading with ≥ 40 clusters each, the
  bought-convexity escape is **CLOSED** for free data and the owner's pay-or-stop fork fires. If
  underpowered, ONE extension to 2027-04-22; no second.

---

## 1. Why this test exists and what it is not

`free-data-convexity-wall`: the only strategy *shape* that survived two invention rounds is genuine
convexity — bounded loss, large winners — and on free data it was untestable because (a) bought
convexity had no historical quotes and (b) synthesised convexity (stop + trail on spot/perps) is
not convex ("a path-dependent exit cannot pay an MFE-derived winner"; SIZE_STRATEGY_SHORTLIST §3).
T31 and T33 remove (a) by forward-collecting real two-sided quotes daily. This document is the test
those panels were built for.

It is **not** a directional test (0-for-8, closed), **not** a short-vol/carry test (T21 §4b: the
variance premium is real and +4σ in our own data — *selling* wings is the crowded side and is
excluded here by construction), **not** a dealer-positioning test (no OI on any free panel), and
**not** a term-structure test (T33 carries only ≤ 45 DTE + two monthlies; DoltHub is front-month).

## 2. Data (fixed)

| panel | clock | first day in test | rows | role |
|---|---|---|---|---|
| T31 Deribit BTC/ETH | 00:15 UTC daily | 2026-08-24 (day 0 was 13:06 UTC — **excluded**, clock mismatch; test starts 2026-08-25) | Tardis `options_chain` layout, bid/ask/size, IV, greeks, `delivery_prices.json` | held-out, universe 1 |
| T33 Alpaca US options | 15:45 ET trading days | **first clean v2 day (2026-08-26)** | 30 cols incl. bid/ask/size/quote_ts, IV/greeks as served, `underlying_price` | held-out, universe 2 |
| 9 Deribit historical Tardis samples (`deribit_free_samples/`, `_m15`) | 00:15 UTC, first-of-month | — | same layout | **entry-cost priors only** (no continuity → no trigger, no P&L) |
| DoltHub weekly EOD (`doltopts_cache/`, 345 snapshots 2020-01-08 → 2026-08-19, ~50 names) | uncertain EOD stamp | — | bid/ask, IV, greeks; no OI; front-month | **design window only** (§5); never a test |

**T33 eligibility rule (restated from T33 Amendment v2, evaluated at the ≈ 2026-10-07 day-30
gate, before any design number is read):** an underlying enters the December design **only if
`fresh_ok` (per-underlying two-sided-quote freshness ≥ 0.70) on ≥ 95 % of clean days.** The
design is written here on the **full frozen 14-name universe** `SPY QQQ IWM TLT HYG GLD XLE XLF
NVDA TSLA AAPL AMZN MSFT AMD` with that exclusion rule; the surviving set is whatever the rule
yields, not a post-peek choice. Stated expectation (from the day-1 integrity counts): HYG
excluded; XLE/XLF at risk.

**The 2026-08-25 T33 partial (14/14 rows, ledgered `failed` under rule v1): EXCLUDED.** Decided
now, before opening: it was failed by the rule in force on its day; it is one day of ~120 and adds
no power; admitting it would set a retro-admission precedent that is worth more than the day.
T31 day 0 is excluded for the same reason (off-clock).

**Missing days.** A trade whose expiry-day snapshot is missing (failed/absent day) is DROPPED
(collector failure is independent of P&L, so the drop is unbiased). If > 10 % of a design's
trades are dropped, that design is UNDECIDED, not dead.

## 3. The instrument (identical in both universes)

Per underlying, per snapshot: the **~15-delta strangle** on the **nearest listed expiry with
3 ≤ DTE ≤ 10** (Deribit dailies/weeklies; US weeklies exist for all 14 names). Legs: the call with
served delta nearest +0.15 and the put nearest −0.15, tolerance ± 0.07, both with a live two-sided
quote stamped on the capture date (T33 `quote_ts` on the ET trading date; T31 `local_timestamp`
within the run). No served delta within tolerance → no trade for that underlying-day (recorded).

- **Entry:** buy 1 contract of each leg **at the ask**. Premium paid P = ask_c + ask_p (+ fees).
- **Fees:** Deribit 0.0003 × index per contract, capped at 12.5 % of the option premium, per leg
  (binds on far wings; `deribit_wing_estimator.py` model). US: $0.05 per contract (regulatory-only
  on a commission-free venue; ≈ 0.04–0.06 % of premium, immaterial).
- **Exit:** **held to expiry, no stop, no trail** (the whole point: the loss is bounded by
  contract). Deribit: settled at the `delivery_prices.json` print for that expiry. US: intrinsic
  at `underlying_price` on the expiry-date 15:45 ET snapshot (the last 15 minutes are ignored —
  stated approximation, same for every trade; no early exit of any kind).
- **P&L unit:** `r = (payoff − P) / P`, return per unit premium. Every trade has r ≥ −1 by
  contract. Equal premium weight per trade.
- **Clusters:** `(underlying, expiry)`. Entries on consecutive days into the same expiry are one
  cluster for every standard error below.

## 4. The trigger family (stated once; three designs; nothing else will be scored)

All triggers use only information available **at or before** the entry snapshot. Trailing
windows are in snapshots (= trading days for T33, calendar days for T31); the first 40 snapshots of
each panel are burn-in for D3 and 20 for D1/D2.

| id | name | trigger at snapshot t | mechanism claimed |
|---|---|---|---|
| **D1** | IV-under-realised | front ATM IV (delta nearest 0.5 on the chosen expiry) ÷ realised vol of the underlying over the trailing **20** snapshots (annualised) **≤ 0.90** | the weekly wing is priced below what the underlying has just been doing; gamma is cheap relative to the recent path |
| **D2** | Aftershock | \|log return of the underlying over the last snapshot\| ≥ **2.5 ×** the sd of the prior **20** snapshot returns | after a shock the venue's quoted convexity lags the regime (cascade regimes are where convexity pays; "Cascade Relay" died only because a spot stop cannot hold the payoff) |
| **D3** | IV-compression | front ATM IV ≤ the **20th percentile** of its own trailing **40** snapshots (≥ 20 available) | the cheapest fifth of the underlying's own recent vol surface |
| C0 | Unconditional (control) | every snapshot | measures the carry every design must beat; **never promotable** |

Thresholds are fixed here. There is no grid. D2 on the T31 panel uses calendar-day returns
(Deribit trades weekends); on T33 it uses trading days. Both universes are scored **in one pooled
book** per design (equal premium weight per trade); per-universe splits are reported but are
descriptive only.

## 5. Design-window priors (DoltHub, `convexity_design_costing.py` → `CONVEXITY_DESIGN_COSTING.json`)

The free DoltHub panel lists only ~3 expiries per name (≈ 2 w / 4 w / 7 w), so the forward
instrument (3–10 DTE, held to expiry) cannot be replayed there. What *can* be measured, and was:

| quantity | value (median over 2020-01 → 2026-08, ~50 US large caps) |
|---|---|
| ~14-DTE 15-delta strangle: premium / spot | 1.03 % (n 16,807) |
| ~14-DTE: relative half-spread (ask − mid)/mid | **8.8 %** (p75 16.9 %) |
| ~28-DTE 15-delta strangle: premium / spot | 1.46 % (n 16,701) |
| ~28-DTE: relative half-spread | **9.1 %** (p75 19.1 %) |
| fee (US model) | 0.04–0.06 % of premium (immaterial) |

Carry, weekly analogues of the triggers (buy ~28-DTE at ask, mark at **bid two snapshots ≈ 14 d
later**; 5,707 marked of 16,701 priced — the rest lost their listing before the mark, a coverage
limit of the cache, noted):

| cell | n trades | clusters (dates) | trigger freq | mean r | cluster t | win | p95 r |
|---|---|---|---|---|---|---|---|
| C0 unconditional | 5,707 | 335 | 1.000 | **−0.318** | −19.2 | 0.18 | +0.98 |
| D1 IV-under-realised (8-wk RV analogue) | 1,664 | 302 | 0.294 | −0.262 | −9.9 | 0.20 | +1.31 |
| D2 aftershock (weekly-return analogue) | 184 | 110 | 0.033 | −0.286 | −4.1 | 0.20 | +1.34 |
| D3 IV-compression | 1,314 | 215 | 0.240 | −0.264 | −8.2 | 0.19 | +1.18 |

Reading, written before the forward panels are opened: roughly **18 pp of the −32 % is the
round-trip spread** (9 % half-spread paid twice) and the rest is theta over two weeks; the
triggers claw back ~3–6 pp, not 32. A to-expiry hold on 3–10 DTE removes the exit spread (payoff
is settled, not sold) but pays proportionally more theta per day and a wider relative spread on
the shorter tenor. **The prior is that every design is negative in the goal universe.** Deribit's
historical samples say the same for BTC/ETH on the entry side (wing spreads 2–18 % relative, fee
5–8 % of premium, break-even moves 5.6–12 % inside ~4 DTE — T31 §"Honest expectation").

These figures set N_min and the placebo; they do not touch any threshold in §4.

## 6. Bar, multiple-testing cost, verdict rules (mechanical)

Scored cells: **3** (D1, D2, D3 pooled books). C0 and every per-universe split are descriptive.
The analytic pooled bar √(2 ln 3) = 1.48 is below the programme's floor, so the floor binds.

A design is **ALIVE** at a reading only if ALL of:

1. **N_min:** ≥ **40 clusters** `(underlying, expiry)` with a settled payoff, and ≤ 10 % of its
   trades dropped for missing expiry-day snapshots. Otherwise **UNDECIDED** (not dead).
2. **Net mean r > 0** (ask entry, fees, settlement exit) with **cluster-robust t ≥ 2.5**.
3. **Size-matched random-entry placebo:** 1,000 draws of C0 trades sub-sampled to the design's
   cluster count on the same underlying set; the design's mean r must exceed the **99th
   percentile** of the placebo distribution (3 cells → family-wise ≈ 97 %). This is the calendar
   placebo required for event-clocked themes (INVENT_0825 rule) and the honest null for D1/D3 too:
   the trigger must beat *timing luck*, not just zero.
4. **Concentration:** the single largest positive cluster contributes ≤ **40 %** of the sum of
   positive cluster P&L. A design that is one cascade is not a design; it is UNDECIDED and waits
   for the extension.
5. **Sign agreement (descriptive → hard only if violated loudly):** if either universe alone shows
   t ≤ −2.0 while the pooled book passes, the design is UNDECIDED, not alive.

Otherwise, with N_min met and any of 2–3 failing, the design is **DEAD**. Verdicts are written by
the evaluator to `CONVEXITY_VERDICT_<date>.json`; no re-reading, no threshold edits.

**What ALIVE means.** A proposal record in this doc's ledger and a **replication requirement** on
the next +120 days of both panels (the second reading, §7). Only a design alive on **both**
readings may be written up as an owner-facing proposal. It is never wired into BASKET1 or any
paper loop autonomously.

## 7. Calendar (fixed)

| date | event |
|---|---|
| ≈ 2026-09-23 | T31 collector gate (≥ 95 % clean of calendar days) |
| ≈ 2026-10-07 | T33 collector gate (≥ 95 % clean of trading days) + **T33 eligibility set fixed** by the §2 rule |
| **2026-12-23** | **First reading.** T31 panel 2026-08-25 → 2026-12-22 (≈ 120 d), T33 panel 2026-08-26 → 2026-12-22 (≈ 83 trading days). Evaluator run once; verdict per design. |
| 2027-04-22 | **Second reading** (replication for anything alive; the one extension for anything undecided). Panels 2026-12-23 → 2027-04-21. No third reading. |

Power, stated now: at ~4 % trigger frequency D2 yields ≈ 40–60 clusters by 12-23 across 15–16
underlyings (borderline N_min); D1/D3 at 20–30 % frequency yield hundreds. The first reading is
therefore likely decisive for D1/D3 and borderline for D2.

## 8. Kill-condition (the programme-level one)

- **All three designs DEAD at a reading with N_min met** → the bought-convexity escape on free
  forward data is **CLOSED**; both collectors downgrade to passive archive; the STRATEGIST puts
  the pay-or-stop fork to the owner (this was the last free-data lever named in the 2026-08-24/25
  directives; T30's borrow wall must also have been read by then, ≈ 09-22).
- **Any design UNDECIDED at the first reading** → exactly one extension to 2027-04-22, then the
  rule above applies with no further extension. Underpowered after two readings counts as CLOSED
  (a design that cannot be decided in 8 months of free daily data is not a retail edge).
- **Any design ALIVE at the first reading** → replication reading 2027-04-22; alive on both →
  owner-facing proposal; dead on the second → dead ledger, escape CLOSED unless another design is
  alive.
- If a collector fails its own gate and is killed, its universe drops out and the pooled book is
  the other universe alone with N_min unchanged.

## 9. What is explicitly NOT allowed after this hash

Adding a fourth design; moving any threshold in §3–§4; changing the exit from hold-to-expiry;
re-weighting universes after seeing per-universe splits; admitting the 08-25 T33 partial or T31
day 0; re-running the placebo with a different draw count; reading either forward panel before
2026-12-23 for anything but integrity counts; proposing anything to BASKET1.

## 10. Files

- this document + `CONVEXITY_PREREGISTRATION.sha256` (pins this doc, the costing script and its
  JSON output)
- `scripts/trading_bot/convexity_design_costing.py`, `research/trading_bot/CONVEXITY_DESIGN_COSTING.json`
- The mechanical evaluator (`scripts/trading_bot/convexity_evaluate.py`) is to be written and pinned
  by a tick **before 2026-12-01** as an amendment to this file (hash appended, no rule changes); if it
  is not on disk by then, the first reading slips until it is — the reading never precedes the pin.

---

## Amendment A1 — 2026-08-26 15:00 CEST: the mechanical evaluator is pinned (task T36)

**What changed:** nothing in §2–§9. `scripts/trading_bot/convexity_evaluate.py` now exists and its
hash is appended to `CONVEXITY_PREREGISTRATION.sha256`; this section records the mechanical
resolutions the script had to make where the prose above was silent. Pinned on T31 day 3 / T33
day 1 (first v2 capture this evening), with **zero rows read from either forward panel** — the
script was developed and tested only against synthetic panels it generates itself
(`--selftest`: null panels → C0 ≈ −0.70/premium, no design ALIVE; planted aftershock → D2 ALIVE;
one-cluster windfall → never ALIVE; N_min / drop / sign-agreement refusals; `--evaluate` refuses
before the reading date). The prior doc hash `5bded3ea…` is kept in the `.sha256` file as audit trail.

Mechanical resolutions (none is a threshold, a design, a date or an exit rule):

1. **DTE** = integer calendar-date difference (expiry date − snapshot date) in both universes.
2. **ATM IV** for D1/D3 = served IV of the call with served delta nearest +0.5 on the chosen
   expiry; if no call on that expiry carries a served delta, the call whose strike is nearest
   the spot. T31 `mark_iv` is in percent (÷100); T33 `iv` is a decimal; any IV > 3 is treated
   as percent.
3. **Spot series:** T33 = the snapshot's `underlying_price`; T31 = median `index_price` of the
   currency's rows (fallback: `underlying_price` of the nearest expiry). Realised vol annualises
   with 252 (T33) and 365 (T31).
4. **D2 on T31** is not evaluated at a snapshot whose predecessor is > 3 calendar days earlier
   (the "last snapshot" return would span several days). D1/D3 count snapshots regardless.
5. **Burn-in:** D1 needs ≥ 20 prior snapshots; D2 needs 20 prior *returns* (index ≥ 21); D3
   needs ≥ 40 prior snapshots and ≥ 20 non-missing ATM IVs inside that window.
6. **Unsettled at reading:** a trade whose expiry falls after the reading's panel end is neither
   counted nor dropped — it belongs to no reading. Trades whose expiry is inside the window but
   whose settlement print / expiry-day snapshot is absent are DROPPED (§2).
7. **Placebo:** 1,000 draws of C0 *clusters* without replacement, restricted to the design's
   underlying set, k = the design's cluster count, RNG seed 20261223, fixed.
8. **Fees:** T33 $0.05 per contract on entry; Deribit 0.0003 × index per leg on entry, capped at
   12.5 % of that leg's premium; no delivery fee (exactly §3).
9. **T33 eligibility** is computed by the script from the first 30 clean trading days of the
   ledger/manifest (`fresh_ok` ≥ 95 %); the eligible set is written into the verdict file.
10. **Two-sided** = bid > 0, ask > 0, ask ≥ bid, and (T33) `quote_ts` stamped on the snapshot's
    ET date; T31 rows all carry the run's `local_timestamp` by construction.
11. **Refusals:** `--evaluate` refuses before the reading's open date (rc 3, no panel file is
    opened), on any pin drift among the four pinned files (rc 4), and if the verdict file for
    that reading already exists (rc 5; §6 "no re-reading"). The only mode that touches the real
    directories before December is `--plan`, which prints ledger/manifest dates and counts.
