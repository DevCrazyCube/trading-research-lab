# PRE-REGISTRATION — INVENT_0822 · LARGE-GROSS forced / mechanical flow

**Date:** 2026-08-22 · **Scope:** research only. No orders, no money, no wallet. Free data only.
**Written and frozen BEFORE any design-window result was computed.**

---

## 1. Why this theme is allowed to exist at all

Every prior round that reached for index reconstitution recorded the same blocker verbatim:
*"index add/delete reconstitution proper — no point-in-time membership data"*
(`INVENT_R3_event_calendar.md`, `INVENT_D0821_MASTER.md`, `DEEPMINE_overnight_event.md`,
`DEEPMINE_MASTER.md` §"Point-in-time index membership"). `DEEPMINE_overnight_event`'s
`R01_rankpromote` was an explicit *proxy* — names entering a trailing top-500-ADV screen — and
it died, correctly, because a liquidity-rank promotion carries **no mandated flow**.

That blocker is now removed. Wikipedia maintains the **constituent-change tables** for the
S&P 500 (`Historical components of the S&P 500`), S&P 400 and S&P 600 — effective date, added
ticker, removed ticker, reason. Scraped: **2,974 change events**, S&P 500 back to 1976, S&P 400
from 2012, S&P 600 from 2019. Restricted to the Alpaca SIP bar window (2016-01-04 →) this is
**~2,400 real forced-flow events with a real effective date.** Alpaca serves **delisted**
symbols (verified: `WLTW` returns bars through its 2022-01-07 merger), so deletions are not
silently dropped and the usual survivorship hole is much smaller than feared.

Corporate-calendar supply events come from **SEC EDGAR full-index**: `424B4` (final IPO
prospectus → IPO date → lockup expiry at +180 calendar days) and `424B5` (shelf takedown =
secondary-offering pricing supplement), joined to tickers through SEC `company_tickers.json`.

## 2. The event clock — and the one convention everything depends on

S&P index changes are effective **prior to the open** of the effective date `ED`. Every index
tracker must therefore execute in the **closing auction of the previous session**. Call that
session **R (the rebalance close)**. All offsets are trading days relative to R.

**Falsifiable check, run before the formulas:** relative dollar volume must spike at **R**, not
at ED. If it spikes at ED the convention is off by one and every offset shifts.
(`inv0822_flow_diag.py`.)

## 3. Signs are fixed by the mechanism, not by the data

| event | mandated flow | pre-R sign | post-R sign |
|---|---|---|---|
| index ADD | forced BUYING into the R close | +1 (run-up) | −1 (give-back) |
| index DELETE | forced SELLING into the R close | −1 | +1 (rebound) |
| IPO lockup expiry | supply cliff at L | −1 | +1 |
| 424B5 shelf takedown | discounted placement at F | — | +1 |

No formula is allowed to flip its sign after the fact.

## 4. Measurement

* Return = close-to-close simple return of the stock **minus the same-window return of a
  size-matched ETF** (S&P 500 → SPY, S&P 400 → MDY, S&P 600 → IJR, corporate → IWM).
* Liquidity screen: median dollar volume over the 20 sessions **before entry** ≥ $2M. Applied
  strictly pre-entry, so no lookahead.
* **Significance number** = t-stat of the mean abnormal return **clustered by event date**.
  Index changes arrive in batches on one date; the naive cross-event t is inflated and is not
  used.
* **Magnitude/fundability number** = annualised Sharpe of the daily equal-weight portfolio that
  actually holds the trades, **idle days counted as zero return**.
* Costs charged at three rails: **0.5 bp/side** (M0-measured closing-auction rail + fee),
  **3.0 bp/side** (Dyhrberg liquid taker + fee), **5.5 bp/side** (the xs-sweep default), plus
  1 bp/side on the ETF hedge leg. Two stock legs + two hedge legs per event.

## 5. The bar

**Amendment, written after the block-1 design pass and before any held-out evaluation.**
Blocks 2–4 below were added *after* seeing block-1's design numbers. That is a real addition to
the search, it is recorded here rather than hidden, and it is why the honest bar for anything in
those blocks is the **two-sided** `sqrt(2 ln 2N)` — they are sign-flipped re-tests, so both tails
were live.

* **Block 2 (F35–F38)** — block 1 pre-registered "promotion = mandated net BUY". The design data
  contradicted that. Block 2 re-tests the opposite sign.
* **Block 3 (F39–F41)** — split terminal (M&A) deletes from live ones.
* **Block 4 (F42–F47)** — the correction that matters: the four migration TYPES do not share a
  sign. Passive ownership is ~20% of float for an S&P 500 name, ~4% for S&P 400, ~7% for S&P
  600, so `400→500` is a **huge net BUY** while `600→400` is a **modest net SELL**. Block 2
  pooled them and therefore pooled two opposite mechanisms. Block 4 signs each transition by
  the passive-ownership differential.

`N = 47` formulas in total → expected max under the null ≈ `sqrt(2 ln 47)` = **2.78** one-sided,
`sqrt(2 ln 94)` = **3.02** two-sided.

*(The original block-1 statement, kept for the record: `N = 34` pre-registered formulas →
expected max |t| under the null ≈ `sqrt(2 ln 34)` = **2.65**.)*
The pooled bar carried forward from earlier rounds is **3.28**. A formula is real only if:

1. **GROSS** design t clearly beats the bar (the `EXECUTION_COST_WALL` lesson: the wall is a
   significance wall — a sub-bar gross signal is not rescued by a cheaper rail); **and**
2. held-out **net** is positive at a rail that actually exists; **and**
3. the magnitude is large enough to matter (mean event alpha materially above the ~10-12 bp
   round-trip cost, not a 3 bp edge wearing a t-stat).

The `ρ1(Δs)` gate does not apply: these are event returns, not an RV spread, so there is no
bid-ask bounce being mistaken for convergence. The gate it replaces is the **volume-spike
convention check** in §2 plus the requirement that the flow be *mandated*, not merely observed.

**No regime conditioners.** Zero formulas spend themselves on market-state gates (0/107 in
round 3). The two conditioned families (F30–F34) condition on **the size of this event's own
mandated flow**, read off the rebalance close itself — event intensity, not market regime.

## 6. Windows

* **Design:** events with R-date 2016-01-04 … 2021-12-31.
* **Held-out:** 2022-01-01 … 2026-08-14. Not evaluated until the design JSON is on disk.

## 7. The 34 formulas

F01 SP500 add, long R−5→R · F02 SP500 add, long R−1→R · F03 SP500 add, short R→R+5 ·
F04 SP500 add, short R→R+20 · F05 SP500 add, short R→R+60 · F06 SP500 delete, short R−5→R ·
F07 SP500 delete, long R→R+10 · F08 SP500 delete, long R→R+60 · F09 SP400 add, long R−5→R ·
F10 SP400 add, short R→R+20 · F11 SP400 delete, long R→R+20 · F12 SP600 add, long R−5→R ·
F13 SP600 add, short R→R+20 · F14 SP600 delete, long R→R+20 · F15 migration UP, long R−5→R ·
F16 migration UP, short R→R+20 · F17 migration DOWN, long R→R+20 · F18 all adds, short R→R+20 ·
F19 all deletes, long R→R+20 · F20 all adds, long R−1→R · F21 all adds, short R→R+3 ·
F22 all deletes, long R→R+3 · F23 self-hedged pair (long deletes / short adds) R→R+20 ·
F24 lockup, short L−5→L−1 · F25 lockup, long L→L+10 · F26 lockup, short L−10→L ·
F27 424B5, long F→F+5 · F28 424B5, long F→F+20 · F29 424B5, short F−5→F−1 **(not tradable —
the filing date is not known ex ante; reported as a mechanism check only)** ·
F30 adds with top-tercile R-close volume spike, short R→R+20 · F31 deletes with top-tercile
spike, long R→R+20 · F32 adds with the largest R−5→R run-up, short R→R+20 · F33 deletes with
the largest R−5→R drop, long R→R+20 · F34 self-hedged pair on top-tercile spikes, R→R+20.

**Tradability flags.** `ANN` = the entry at R−5 presumes the change was already announced;
S&P usually announces 2–10 sessions ahead but not always, so an `ANN`-flagged formula cannot be
promoted on this data alone. `ANN-mild` = entry at R−1. `CLEAN` = entry at or after the R close,
when the change is unambiguously public.
