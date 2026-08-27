# T3 — pre-registration: end-of-day pressure reversal, held overnight on the auction rail

**Frozen before any return data was fitted.** Written 2026-08-16. The only Alpaca calls made before
this file existed were *structural* probes — does the endpoint exist, what fields does it return, how
fast is a page — listed in §9. No return, no signal and no portfolio was computed before this file was
written and hashed.

Candidate under test: **#1 in `EDGE_SHORTLIST.md`** (score 17/20).
Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, paired excess), `costs.py`
(provenance-carrying cost model), `data.py` (credentials + data-host guard) are imported, not copied.

---

## 1. The claim, and its null

**Mechanism claimed.** Index funds, MOC-mandated flows and ETF NAV tracking must transact at the close
regardless of price. Liquidity to absorb that imbalance is supplied at a **price concession**; the
concession is not information, so it reverts once the mandated flow is gone (Nagel 2012 — reversal is
*compensation for supplying liquidity*, which is why attention has not competed it away).

**H1.** Stocks with the most negative last-10-minute move earn *higher* close→next-opening-auction
returns than stocks with the most positive last-10-minute move, by more than the friction of a
spread-crossing entry.

**H0 (the null actually tested).** The net (post-friction) mean overnight return of the dollar-neutral
pressure-fade long/short portfolio is **≤ 0**; equivalently, the last-10-minute return carries no
information about the overnight return beyond the common overnight drift.

The **dollar-neutral long/short construction is the pairing**, and it is mandatory: B22F measured SPY
overnight at +10.06 %/yr, Sharpe 0.87, so an unpaired long-only mean would be dominated by a drift
that has nothing to do with the signal. `FINDINGS.md` §5c: *paired differences whenever a common
market move would otherwise dominate.* The equal-weight return of the same universe on the same night
is reported beside every result as the explicit control.

---

## 2. Universe — point in time, monthly, survivorship-reduced

**Pool.** Every Alpaca `us_equity` asset with status `active` **or `inactive`**, listed on
NYSE / NASDAQ / AMEX / ARCA / BATS. Delisted names are in the pool by construction (13,096 active +
2,859 inactive listed, probed 2026-08-16), so acquisitions and failures are not silently dropped.

**Screen, computed from RAW monthly bars of month `m-1` and applied to month `m`:**

| filter | value |
|---|---|
| month-end **raw** close | > $5.00 |
| dollar ADV (`vw × volume ÷ trading days in month`) | > $20 M |
| rank by that ADV, keep | **top 500** |

`adjustment='raw'` is mandatory for both level filters — `data.py`'s
`assert_levels_are_point_in_time()` records why (an adjusted 2019 price depends on splits that had not
happened in 2019).

**Declared deviation from the T1 sketch.** T1 §5.1 specified `median quoted spread < 10 bp` as a third
filter. That is **not computable** universe-wide: it needs SIP quotes for ~16,000 symbols × 2,670 days.
It is replaced by (a) the top-500-ADV cut, which selects the same region of the liquidity distribution,
and (b) **measuring** the half-spread on a sampled subset and charging it as a cost (§5). Recorded here
rather than discovered later.

---

## 3. Signal, portfolio, entry, exit

**Signal**, on day `t` for stock `i`:

```
r10(i,t) = close(15:59 ET 1-minute bar) / close(15:49 ET 1-minute bar) − 1
```

SIP, `adjustment='raw'`, `feed='sip'`. The 15:59 bar covers `[15:59, 16:00)` and therefore **excludes**
the closing auction print — the entry decision cannot see the print it is trying to precede.

**On β.** T1 wrote `r10(i) − β × r10(SPY)`. With β = 1 the market term is a constant across the
cross-section, so it **does not change the ranking at all**, and the dollar-neutral construction
removes the common component anyway. The primary rule therefore ranks raw `r10`. A β-estimated variant
is *not* in the trial grid and will not be run.

**Portfolio.** Cross-sectional sort on `r10`. **Long the bottom decile** (50 % of capital, equal
weight), **short the top decile** (50 %, equal weight). Dollar neutral, gross exposure 100 %.

**Entry.** 15:59 minute-bar close. Modelled as a marketable order that **crosses the spread**: a
half-spread is charged on 100 % of capital (§5).

**Exit.** The **next trading day's official opening auction print** from `/v2/stocks/auctions`
(condition code `O`, largest size if several). A single-price auction has **no spread**, so the exit
leg is charged zero — the structural advantage the whole candidate rests on.

**Holding period.** Exactly one overnight session. Positions never overlap (exit at `t+1` open
precedes entry at `t+1` 15:59), so the daily series is one independent-by-construction observation per
night.

---

## 4. Exclusions — identical in design and test periods

1. Symbol-day dropped if the 15:49 or 15:59 minute bar is missing.
2. Symbol-day dropped if the next-day opening auction print is missing.
3. Symbol-day dropped if **any corporate action** (cash dividend ex-date, forward/reverse split,
   spin-off, merger, redemption) has an ex/process date equal to the exit date — raw prices would
   otherwise show a mechanical gap. This also keeps candidate #2's effect out of candidate #1's result.
4. Whole day dropped if the exchange calendar shows an **early close** (≠ 16:00) on `t` or on `t+1`.
5. Whole day dropped if fewer than **100** symbols survive filters 1–4 (so each decile holds ≥ 10 names).

---

## 5. Costs — measured, not assumed

| component | charged | basis |
|---|---|---|
| entry half-spread `h` | on **100 %** of capital, every night | **measured**: median of `(ask−bid)/(2·mid)` from SIP quotes in `[15:59:00, 16:00:00)` over a random sample (seed `20260816`) of 40 trading days, all universe members on those days. Measured **separately for the design and test periods**; each period is charged its own number. |
| exit spread | **0** | single-price auction, no spread. T1 §2c verified `type=market, tif=opg` is accepted by the broker. |
| commission | 0 | Alpaca, $0/share |
| borrow | 30 bp/yr GC on the 50 % short notional, per **calendar** day held | `costs.py` default; not hard-to-borrow |

**Stress ladder, reported always, never a single cost number:** `h`, `2h`, `4h`, and a fourth rung in
which the **exit also pays `h`** (i.e. the auction rail turns out not to be free). Plus the B19P
frictionless diagnostic (`h = 0`): *if it loses there, no execution improvement can rescue it.*

**Assumption stated, not hidden.** T1's prerequisite measurement **M0 — do MOC/MOO orders actually
fill at the official print — has NOT been performed.** This test assumes they do. The fourth stress
rung is the price of being wrong about that.

---

## 6. Design phase — 2016-01-04 → 2021-12-31

The **only** configurations that will ever be run, and there are exactly **eight**:

| axis | values |
|---|---|
| signal window | 10 min, 30 min |
| cross-sectional cut | decile (10 %), quintile (20 %) |
| universe size | top 300, top 500 |

2 × 2 × 2 = **8 trials. Declared here, before any of them is run.** The configuration with the highest
net annualised Sharpe on the design period is frozen. The sample variance of the eight design-period
per-observation Sharpes is the `sharpe_variance` input to the deflation — the honest input
`stats.sharpe_variance_from_trials` asks for.

No configuration outside this grid will be run. If the grid is extended for any reason, the extension
is a new pre-registration and the trial count changes with it.

---

## 7. Held-out test — 2022-01-03 → 2026-08-14

The single frozen configuration is run **once**. Reported:

- net mean per night, its t-statistic, annualised Sharpe, CAGR, max drawdown, turnover;
- the equal-weight control's return on the same nights (the pairing);
- **DSR** (`stats.deflated_sharpe`) on the held-out net return series, `trials=8` with the
  design-phase cross-trial Sharpe variance; sensitivity reported at `trials=24`;
- **label permutation**, 10,000 shuffles, seed `20260816`: within each day the cross-sectional signal
  labels are shuffled across the surviving symbols, so every permutation holds the same number of
  names long and short on the same nights and only *which* stock gets which label changes. Add-one
  corrected. This is the instrument `FINDINGS.md` §5c prescribes for a label/classifier object;
- the T2 exposure-timing permutation (`stats.permutation_test`) for completeness;
- the full stress ladder of §5 and the zero-cost diagnostic.

## 8. Kill conditions — fixed in advance

**DEAD if ANY of the following holds on the held-out period:**

1. net mean per night **≤ 0** at the measured half-spread `h`; **or**
2. label-permutation right-tail **p ≥ 0.05**; **or**
3. **DSR < 0.95** at `trials = 8`.

**SURVIVES** only if all three pass. Anything in between is reported as *not established*, which is not
a pass.

**If DEAD, the nominated next candidate is #2, ex-dividend drop-off executed close-to-close in the
auctions**, whose T1 caveat (the tax arithmetic is owner-facing and must be settled *before* the
backtest is believed) carries forward unchanged.

---

## 9. What was probed before this file was written

Structural only, no returns, no signal, no portfolio:

- `/v2/assets` active + inactive counts (14,234 / 19,197; 13,096 / 2,859 on major exchanges);
- one `/v2/stocks/bars` page each at `1Day`, `1Month`, `1Min` to time a page and confirm the 2016 start
  and the bar-boundary behaviour at 15:59 vs 16:00;
- one `/v2/stocks/auctions` page to confirm the print structure (`c` code `O` for the official open,
  `6` for the official close) in both 2016 and 2026;
- one `/v1/corporate-actions` and one `/v2/calendar` page to confirm field names.

## 10. What this pre-registration does not claim

- It does not claim the rail is free: M0 is unperformed and §5's fourth stress rung exists for that.
- It does not correct survivorship perfectly — Alpaca's inactive list is a partial record of what once
  listed, and a name that never appears in it is invisible to this test.
- It does not model queue position, partial fills, or size-dependent impact. At $100 k against a
  closing auction that clears $28–130 M in single stocks (T1 §2e) that is a tolerable omission, and it
  is an omission all the same.
- It does not authorise execution of any kind. Real money remains owner-gated.
