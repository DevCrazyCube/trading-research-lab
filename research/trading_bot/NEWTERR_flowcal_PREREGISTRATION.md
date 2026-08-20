# PRE-REGISTRATION — precise calendar / forced-flow sweep (`NEWTERR_flowcal`)

Written **before any design result exists**. Anything below that a later result contradicts
is a failure of this document, not something to be quietly edited.

## Territory

Precise, mechanism-first calendar and event flow. Explicitly **not** the generic calendar
sweep (`SWEEP_calendar_session`, 52 formulas, verdict: noise) — that family was index-level
directional day-of-week / month-of-year / OPEX-long bets. This family is
**cross-sectional and flow-identified**: the calendar picks the *day on which somebody is
forced to trade*, and a second variable picks *which names they are forced to trade*.

The second variable is the part that has never been used here: the T16 Reg SHO daily
short-volume panel (19.3 M rows, 2018-08-01..2026-08-14) and the T16 FINRA bi-monthly short
interest panel (3.9 M rows), neither of which has ever been crossed with a calendar.

## Excluded by construction

Overnight-equity beyond T3/T7, ETF same-index RV, cross-asset lead-lag, futures term
structure, generic calendar, perp funding/OI/flow, CEF/dual-class/ADR RV.

## Datasets and windows (fixed now, not adjustable later)

| dataset | source | span | DESIGN | HOLDOUT |
|---|---|---|---|---|
| `xs` | t17 daily (delisted names included) + Reg SHO + FINRA SI | 2018-08-01 .. 2026-08-14 | `<= 2023-06-30` | `>= 2023-07-01` |
| `etf` | calendar_cache daily ETF/index | 1993-01-29 .. 2026-08-20 | `<= 2016-12-31` | `>= 2017-01-01` |
| `fomc` | subset of `etf` on FOMC announcement dates | 2011-01-01 .. 2026-08 | `<= 2019-12-31` | `>= 2020-01-01` |

The holdout is not to be inspected until the design sweep is frozen and written out.

## Universe and eligibility (`xs`)

Eligible on day *t* iff, using data through *t-1* only: trailing-60-session mean dollar
volume >= \$30 M and close >= \$5. Symbol inclusion in the stored panel is *equivalent* to
that rule (a name that never crosses the bar could never be eligible on any day), so the
panel is not survivorship-screened — delisted tickers are present.

## Costs charged (both legs, always)

* `xs`: **2.5 bp per side** on `|Δw|` (M0 tier A/B measured close half-spread ~1.3 bp plus
  impact headroom), plus **50 bp/yr borrow on the short leg**, charged daily on short
  notional. Every formula in this family is constructed so its short leg is the *low*
  short-interest / low-short-volume side, i.e. easy-to-borrow; any formula whose short leg
  lands on the hard-to-borrow side is disqualified rather than re-priced.
* `etf`: **1.0 bp per side** on `|Δw|`.

## Statistical bar

* `N` = every formula scored, controls included.
* Analytic reference: `sqrt(2 ln N)` SE units.
* Primary bar: an **empirical max-|z| null**. The entire data block for a dataset
  (returns, volumes, short volumes, short interest) is rotated circularly *as one unit*
  against a fixed calendar. That destroys every calendar alignment while preserving serial
  correlation, vol clustering, cross-sectional correlation and the signal/return
  relationship. All formulas are re-scored per replicate; `max |z|` across the family is
  recorded, where `z` is studentised per formula against its own rotated-null mean and sd
  (raw Sharpe would rank the family by turnover).
* 400 replicates.
* A formula is a candidate only if its design `|z|` clearly exceeds the family-max null
  p95 — not merely the expected max.

## The two gates that come before the statistics

**G0 mechanism.** Each formula below carries a one-sentence forced-flow mechanism. A
formula with no mechanism, or with a mechanism this programme has already disproven, is
killed regardless of its statistics.

**Lag-kill.** Any candidate is re-run with one extra session of lag inserted between the
signal inputs and the entry, *holding the calendar gate fixed* (lagging the calendar gate
would kill a genuine day-specific effect and prove nothing). Pure-calendar formulas with no
cross-sectional signal are instead re-run entered at the **open** of the event session
rather than the previous close, which is where same-bar-fill and stale-close artefacts
live. A candidate that largely dies under either is an artefact.

## The formulas (43)

All `xs` formulas are dollar-neutral decile long/short books (0.5 long, 0.5 short),
signal known at the close of *t-1*, held close *t-1* to close *t*.

### A — turn-of-month index-fund inflow (cap-weighted forced buying)
Mechanism: retirement contributions land on semimonthly paydays; index and target-date
funds must invest them in the index basket at a close, and that basket is cap-weighted, so
the forced buying per name is proportional to index weight.
1. `XS_TOM_SIZE` — last session of the month + first 3: long top size decile / short bottom.
2. `XS_TOM_SIZE_UNWIND` — trading days 4-6: A1 reversed (impact decays).
3. `XS_MID15_SIZE` — the mid-month payday session + 1: A1's position.
4. `XS_TOM_SIZE_CTRL` — A1's position every day (ungated control).
5. `XS_TOM_LOWVOL` — turn-of-month: long low-vol decile / short high-vol decile
   (**discriminator**: index inflow buys a beta-1 basket, so it must *not* show up as a
   low-vol effect; if this scores and A1 does not, the mechanism is not inflow).

### B — quarter-end dealer balance-sheet contraction (stock-loan supply squeeze)
Mechanism: G-SIB surcharge and leverage-ratio reporting are quarter-end snapshots, so
dealers shrink matched-book repo and stock-loan into 31 Mar/Jun/Sep/Dec; loan supply
contracts and recalls rise, and a recalled short must buy the stock back.
6. `XS_QE_SQUEEZE` — last 3 sessions of a quarter: long top-decile short-volume ratio /
   short bottom decile.
7. `XS_QE_SQUEEZE_UNWIND` — first 3 sessions of the new quarter: B6 reversed.
8. `XS_ME_SQUEEZE` — B6 on non-quarter month-ends (mechanism predicts *weaker*).
9. `XS_SQUEEZE_CTRL` — B6's position every day (ungated control).
10. `XS_YE_SQUEEZE` — B6 restricted to the December quarter-end (largest reporting date).

### C — pre-holiday inventory flattening
Mechanism: a market maker cannot hedge across a multi-day closure, so risk limits force
positions flat before it; the largest positions to flatten are the crowded shorts.
11. `XS_PREHOL_COVER` — last session before a holiday: long top-decile short-volume ratio /
    short bottom decile.
12. `XS_POSTHOL_UNWIND` — first session after: C11 reversed.
13. `XS_PREHOL_LONGWK` — C11 restricted to closures of 3+ calendar days.

### D — index-rebalance forced print, identified by abnormal volume
Mechanism: on a rebalance effective date every tracker must trade the same names in the same
direction at one print; abnormal volume on that day *is* the measurement of who got printed,
and one-print impact reverts.
14. `XS_QUADREV` — session after quad-witching Friday: short top-decile abnormal volume /
    long bottom decile.
15. `XS_QUADREV_5D` — D14 held 5 sessions.
16. `XS_MEREV` — D14's rule on the last session of every month.
17. `XS_VOLREV_CTRL` — the abnormal-volume reversal every day (ungated control: is it
    rebalance flow or ordinary liquidity provision?).
18. `XS_OPEXREV` — D14's rule after the monthly non-quad OPEX Friday.

### E — OPEX gamma
Mechanism: option market makers who are net long gamma must trade against price moves to
stay delta-hedged, which mechanically dampens moves and creates reversion; at expiry that
hedging demand disappears at once.
19. `XS_OPEXWK_MR` — OPEX week only: cross-sectional 1-day reversal.
20. `XS_POSTOPEX_MOM` — 3 sessions after expiry: cross-sectional 1-day momentum.
21. `XS_MR_CTRL` — 1-day reversal every day (ungated control).
22. `XS_OPEXWK_MR_MEGA` — E19 restricted to the top size tercile (listed-option open
    interest concentrates there).

### F — Russell reconstitution
Mechanism: every Russell tracker must execute the entire reconstitution at one closing print
on the last Friday of June — the largest single forced trade of the year.
23. `XS_RECON_RUNUP` — 1 May to recon day: long the index-boundary band / short the
    safely-inside band.
24. `XS_RECON_REV` — 5 sessions after recon day: F23 reversed.

### G — FINRA short-interest dissemination
Mechanism: short interest is disseminated on a published schedule ~8 business days after the
settlement date; days-to-cover screens are mechanically triggered by that release, and
reporting itself gives shorts a reason to be flat on the settlement date.
25. `XS_SIPUB_SQUEEZE` — session after dissemination, held 2: long top-decile SI increase /
    short bottom decile.
26. `XS_SISETTLE_COVER` — 2 sessions into a settlement date: long top-decile days-to-cover /
    short bottom decile.
27. `XS_SIPUB_CTRL` — G25's position every day (ungated control).

### H — month-end bond-index duration extension
Mechanism: bond index funds must match the index's duration, and the index extends on the
last calendar day of the month when newly issued longer paper enters it; matching is forced
and dated.
28. `ETF_MEEXT_CURVE` — last 2 sessions: long TLT / short IEF.
29. `ETF_MEEXT_REFUND` — H28 restricted to Feb/May/Aug/Nov (refunding months, largest
    extension).
30. `ETF_MEEXT_UNWIND` — first 2 sessions of the month: H28 reversed.
31. `ETF_MEEXT_CTRL` — H28 every day (ungated control).

### I — Treasury settlement and tax-date cash drains
Mechanism: on settlement and estimated-tax dates cash leaves the banking system into the
Treasury General Account; dealers who took down the auction must fund inventory, and reserve
scarcity is dated to the day.
32. `ETF_REFUND_SETTLE` — settlement session on/after the 15th of Feb/May/Aug/Nov + 1:
    short SPY.
33. `ETF_TAXDRAIN_APR` — 15-20 April: short SPY.
34. `ETF_TAXDRAIN_CREDIT` — quarterly estimated-tax dates + 2: short HYG / long IEF.
35. `ETF_AUCTION_CONCESSION` — 2 sessions before refunding settlement short TLT, 2 after
    long TLT (dealer inventory concession, then relief).
36. `ETF_MIDMONTH_CTRL` — short SPY on the session on/after the 15th of *every* month
    (ungated control for I32).

### J — cap-weighted inflow at index level
Mechanism: same as A, observed where the cap-weighting is explicit.
37. `ETF_TOM_CAPWT` — turn-of-month: long SPY / short RSP (equal-weight S&P).
38. `ETF_TOM_CAPWT_UNWIND` — trading days 4-6: J37 reversed.
39. `ETF_TOM_OEF_IWM` — turn-of-month: long OEF (S&P 100) / short IWM.

### K — pre-FOMC (window 2011+, scheduled meetings only; the March 2020 emergency actions
are excluded a priori because an unscheduled action has no pre-announcement window)
Mechanism (weakest in this family, and stated as such): dealers and vol sellers cut risk
into a scheduled binary event and must re-establish it after, so the risk premium is earned
by whoever holds through the announcement window.
40. `ETF_PREFOMC_24H` — close *t-2* to close *t-1*: long SPY.
41. `ETF_PREFOMC_BETA` — same window: long QQQ / short SPY.
42. `ETF_POSTFOMC_REV` — session after the announcement: short SPY.
43. `ETF_FOMCDAY` — announcement session only: long SPY.

FOMC dates are hand-entered from the published schedule. A date entered wrong destroys a
real effect and cannot manufacture a false one, so the error direction is conservative.

## Declared expectations

* This family is a classic data-mining trap and the prior is that it is noise. The honest
  base rate from this programme is 0-for-8 on directional candidates.
* Power is the binding constraint on B, F and G: 20 quarter-ends, 5 reconstitutions and
  ~60 dissemination dates in the design window. F is pre-declared **underpowered** — it is
  scored for completeness and cannot promote on its own.
* The controls exist so that a gated formula must beat its own *ungated* version, not just
  beat zero. `SWEEP_calendar_session` lost its one leader exactly there.
