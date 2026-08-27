# T12 — pre-registration: closed-end-fund discount mean reversion

**Frozen before any return, discount change, signal, portfolio or Sharpe was computed.**
Written 2026-08-17. Everything done before this file existed was a **data census, a
shortability count and a spread measurement** — counts of observations, counts of flags, and
quoted spreads. **No price has been divided by any other price. No discount has been
differenced. No portfolio exists anywhere on disk at the moment this file is hashed.**

The census is `research/trading_bot/T12_DATA_CENSUS.json`, the friction census is
`research/trading_bot/T12_FRICTION_CENSUS.json`, both are reproduced in §2 below, and together
they are the reason this pre-registration carries a **history gate that decides the verdict
before any held-out number is allowed to speak**.

Candidate under test: **#5 in `EDGE_SHORTLIST.md`** (score 14/20, uniqueness U = 4). Nominated
in `T9_RESULT.md` §8 and `FINDINGS.md` §10 as "the one remaining candidate with a large n — its
problem is friction, which this programme knows how to price, not power". **§2 and §3 below
establish that framing was wrong**: n is large in the *cross-section* and small in *time*, and
it is time that DSR and the friction arithmetic both consume.

Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, moments, Sharpe,
drawdown) and `costs.py` (the **T6-corrected per-side** cost model) are imported, never copied.
Calendar, HTTP transport, paging rule and the quoted-half-spread measurement window come from
`scripts/t3_pressure_reversal.py` unchanged. Collection is
`scripts/t12_cef_discount.py`; the verdict is `scripts/t12_evaluate.py`, which refuses to run
without this file's sha256 on disk.

---

## 1. The claim, and its null

**Mechanism claimed.** A closed-end fund's share count is fixed, so its market price is not
arbitraged to net asset value by creation/redemption the way an ETF's is. Prices therefore
wander to persistent discounts and premia, and the deviation **mean-reverts** (Pontiff, *Closed-
end fund premia and returns*, JFE 37, 1995). The reason it is claimed to survive is not that
nobody knows about it: it is that closing a CEF discount requires either a tender, a merger, an
open-ending or an activist campaign — **institutionally uneconomic at a few hundred million
dollars of fund** — which is the "uncrowded because too small to matter" corner
`EDGE_SHORTLIST.md` §5 nominated it for.

**H1.** A dollar-neutral book, long the widest-discount decile of the CEF cross-section and
short the narrowest, rebalanced on a weekly grid, earns a **positive net (post-friction)**
return.

**H0 (the null actually tested).** The subsequent **price** return of the widest-discount decile
is **≤** that of the narrowest decile, net of friction. This is `EDGE_SHORTLIST.md` §5
candidate 5's own wording — *"Next-month return of the widest-discount decile equals that of the
narrowest, after adjusting for NAV return"* — written 2026-08-16, before any CEF price was
touched, and quoted here as the a-priori commitment it is.

**The pairing is the short leg and it is mandatory.** `FINDINGS.md` §5c: a long-only basket of
2021–2026 CEFs measures the credit-and-equity premium, not a discount effect. The long-short
decile difference cancels the common CEF move by construction.

**The traded object is PRICE, not the discount.** You cannot trade NAV. The verdict series is
therefore the long-short **price**-return series. The NAV-return decomposition — how much of the
P&L came from the discount narrowing versus from the wide-discount funds' assets outperforming —
is reported as a **diagnostic beside it**, never as the verdict. Reversing that would be scoring
the strategy on a leg no account can hold.

---

## 2. The census — stated BEFORE the test, because it decides the verdict

Every number here is a **count**, a **date** or a **quoted spread**. None is a return.

### 2a. What CEFConnect actually serves (`T12_DATA_CENSUS.json`)

`/api/v3/pricinghistory/{ticker}/{period}` serves exactly five periods. Probed:

| period | rows for `ADX` | median gap | verdict |
|---|---|---|---|
| `1M` | 4 | 7 d | weekly |
| `3M` | 10 | 7 d | weekly |
| `6M`, `10Y`, `Max`, and every numeric period | **empty array, HTTP 200** | — | not served |
| `1Y` | 243 | **1 d** | **DAILY** |
| `3Y` | 146 | 7 d | weekly |
| `5Y` | 243 | **7 d** | **WEEKLY** |

Over the whole universe:

| | **5Y window** | **1Y window** |
|---|---|---|
| live funds in the snapshot | 360 | 360 |
| funds with history | **353** | 359 |
| sampling (median gap) | **WEEKLY (7 d)** | **DAILY (1 d)** |
| union of dates | **249** | 253 |
| span | **2021-08-20 → 2026-08-14** | 2025-08-18 → 2026-08-14 |
| median obs per fund | 243 | 244 |
| funds with ≥ 200 of the dates | **328** | — |
| rows with a missing NAV or discount | **0** | 0 |
| funds priced on the median date | **331** (min 1, max 347) | — |

**This is the whole of the usable history, and it is stated up front as the task required.**
`EDGE_SHORTLIST.md` §2b's summary — "daily history only ~1 yr, 5 yr is weekly-sampled" — is
**confirmed exactly**, on the full 360-fund universe rather than on one probe.

### 2b. The two mutually exclusive designs this history permits

There is no window that is both long and daily. The choice is forced:

| design | observations | design half | held-out half |
|---|---|---|---|
| **A — weekly, 5 years** | 249 weekly dates | 125 (2021-08-20 → 2024-02-23) | **124 (2024-03-01 → 2026-08-14)** |
| B — daily, 1 year | 253 daily dates | ~127 | ~126, i.e. **six months** |

**Design A is the one this pre-registration runs.** Design B is rejected here and now, before any
result exists, for a reason that is arithmetic rather than taste (§3): six held-out months of
daily data is a *single* regime, and — shown below — it is the **strictly less powerful** of the
two despite having more observations, because power in Sharpe units scales with the *square root
of elapsed years*, not with the number of rows.

### 2c. Survivorship — the limitation that cannot be repaired from this feed

CEFConnect publishes **only funds alive today**. There is no delisted list, no liquidated list,
and no merged list. Every fund that between 2021 and 2026 was **liquidated, merged, open-ended,
converted to an ETF, or tendered by an activist** is **absent from the 249-week panel**.

Those events are exactly what *closes* a wide discount, and they happen disproportionately to
wide-discount funds. **The direction of the bias is therefore not obviously conservative and
this pre-registration does not claim to know it**: removing a fund whose discount was closed by a
tender deletes a favourable observation, while removing one that was liquidated after a
collapsing NAV deletes an adverse one. It is stated as *unknown and unquantifiable from this
feed*, and it is a standing reason a positive result here would not be believable even if one
appeared.

### 2d. Shortability — a live snapshot, and half the universe fails it
(`T12_FRICTION_CENSUS.json`)

| | count |
|---|---|
| CEF tickers in the snapshot | 360 |
| found in Alpaca's active `us_equity` list | **358** (`BXSY`, `FXBY` absent) |
| tradable | 358 |
| **shortable / easy-to-borrow at Alpaca** | **186 (51.96 %)** |

**This is a live flag with no history** — the same limitation `EDGE_SHORTLIST.md` §2b records for
candidate #9 — so it is **not** applied as a historical universe screen anywhere in this test.
It bounds what is *executable today*, which is a different question and still a decisive one for
a strategy whose short leg is half the book.

### 2e. Friction — MEASURED first-party on the traded names, before the freeze

Median `(ask − bid) / (2 × mid)` from SIP quotes in `[15:59:59, 16:00:00) ET`, the same
instrument and declared deviation as `t3.measure_half_spread`, sampled on **the CEF universe
itself** over 12 dates drawn from this candidate's own weekly grid:

| n symbol-days | p25 | **median** | p75 | p90 | p95 | max |
|---|---|---|---|---|---|---|
| **3,067** | 7.15 bp | **11.53 bp** | 18.38 bp | 27.25 bp | 36.40 bp | 185.74 bp |

For scale, on the identical instrument and window this programme has measured SPY at **0.116 bp**,
its top-500-ADV universe at **1.13–1.43 bp**, and a freshly distributed spin-off stub — the
thinnest thing it has ever priced — at **7.47 bp** (`T9_RESULT.md`). **The median CEF is 1.5× more
expensive to cross than a spin-off stub and 99× more expensive than SPY.**

**And there is no auction rail.** `EDGE_SHORTLIST.md` §2e measured CEF closing auctions clearing
**$0.0–0.3 M**. `costs.measured_auction_leg` refuses outside M0's measured ADV tiers, and CEFs are
outside them; the zero-spread MOC exit that carried candidates #1 and #2 **is not available to
this one**, and this pre-registration does not ask for it.

---

## 3. THE HISTORY GATE — the gate this candidate exists to face

The task's own guardrail: *"CHECK the usable span FIRST; if it cannot support a clean
out-of-sample design/test split, declare DEAD-BY-INSUFFICIENT-HISTORY rather than force it."*
So the span question is settled **here, in advance, on structural quantities only** — the number
of held-out observations and the declared trial count — and it can produce a verdict on its own.

### 3a. The minimum detectable Sharpe, computed from n alone

`stats.deflated_sharpe` passes at 0.95 when

```
z = (SR − SR0) · √(n − 1) / √(1 − skew·SR + (kurt−1)/4 · SR²)  ≥  1.6449
```

with `SR0 = stats.expected_max_sharpe(trials, V)`. Solving for `SR` at the Gaussian reference
(skew 0, kurtosis 3), with `n = 123` held-out weekly returns:

| held-out design | trials | sd of trial Sharpes | min detectable per-obs SR | **min detectable ANNUALISED Sharpe** |
|---|---|---|---|---|
| **A — weekly, n = 123** | **1** (no search penalty at all) | 0 | 0.1498 | **1.080** |
| **A — weekly, n = 123** | **6** | 0.020 | ~0.176 | **~1.27** |
| A — weekly, n = 123 | 8 | 0.040 | 0.2089 | 1.506 |
| A — weekly, n = 123 | 8 | 0.060 | 0.2386 | 1.720 |
| B — daily, n = 126 | 1 | 0 | 0.1479 | **2.348** |
| B — daily, n = 126 | 8 | 0.040 | 0.2070 | 3.287 |

**Two facts are fixed by this table before any data is fitted.** (i) Design A needs a net
held-out **annualised Sharpe above ~1.1 even if we had run exactly one configuration and paid no
search penalty whatsoever** — and above ~1.3 at the six trials §4 actually declares. (ii) Design
B, the daily feed, is *worse by more than a factor of two* despite having three more rows,
which is why §2b rejected it in advance.

This is the same wall `FINDINGS.md` §10 already records for the programme as a whole — *"our
held-out window cannot certify anything below annualised Sharpe 1.3"* — arriving here on a
five-year weekly panel instead of a five-year daily one.

### 3b. The benchmark effect, declared from the literature before it is measured

Pontiff (1995) is the citation `EDGE_SHORTLIST.md` §5 rests candidate #5 on, and its headline is
that a portfolio of funds at a 20 % discount outperforms one at par by about **6 % per year**.
That is the *largest* clean number in this literature and it is the one used here, deliberately,
because a gate should be asked whether it can see the **strongest documented version** of the
effect — the same construction `T9_PREREGISTRATION.md` §7 used with Cusatis's +2.4 %.

Turning a return into a Sharpe needs a volatility, and this pre-registration will not assume one.
**σ̂ — the standard deviation of the weekly long-short net return — is estimated on the DESIGN
window only** (2021-08-20 → 2024-02-23, 125 weekly dates), at the primary configuration of §4. A
design-window estimate is what a design window is for.

```
benchmark_annualised_sharpe = 0.06 / σ̂_annualised
```

> **GATE.** The held-out test is **adequately powered** only if
> `min_detectable_annualised_sharpe ≤ benchmark_annualised_sharpe`, i.e. only if this instrument
> could detect the strongest documented version of the CEF discount effect at the DSR threshold
> the programme requires. Equivalently, only if
> **σ̂_annualised ≤ 0.06 / min_detectable_annualised_sharpe**.

**If the gate fails, the verdict is `DEAD-BY-INSUFFICIENT-HISTORY`, and no held-out number can
overturn it.** The held-out configuration is still run **exactly once** and reported in full —
a point estimate with an honest interval is worth having and hiding it would be its own
dishonesty — but a positive result under a failed gate is reported as **not established**, never
as SURVIVES. Written down before the number exists so it cannot be renegotiated after.

The result also reports **`years_required`**: the number of years of weekly history that would
make `min_detectable_annualised_sharpe` equal to the benchmark, and therefore how long forward
collection would have to run. That number, not the point estimate, is this candidate's real
finding if the gate fails.

---

## 4. The configuration, the trial space, and the primary

**Signal, family S1 — the fund's own mean (the Pontiff form).** For fund `i` at weekly date `t`:

```
z[i,t] = ( d[i,t] − mean(d[i, t−L .. t−1]) ) / sd(d[i, t−L .. t−1])
```

where `d` is CEFConnect's `DiscountData` (negative = discount). Strictly trailing: the window
ends at `t−1`, so `z` at `t` uses no contemporaneous information. `L ∈ {26, 52}` weeks.

**Signal, family S2 — the raw level (the naive form).** `s[i,t] = d[i,t]`, ranked
cross-sectionally. No trailing window.

**Portfolio.** At each rebalance date: rank eligible funds on the signal ascending (most negative
= widest discount first), go **long the bottom decile, short the top decile**, equal weight
within each leg, **0.5 gross long / 0.5 gross short** so gross exposure is 1.0 and the book is
dollar-neutral. Hold `H ∈ {1, 4}` weeks, then rebalance. Non-overlapping tranches.

**THE TRIAL SPACE IS EXACTLY THESE SIX AND NOTHING ELSE:**

| | H = 1 | H = 4 |
|---|---|---|
| S1, L = 26 | trial 1 | trial 2 |
| S1, L = 52 | trial 3 | **trial 4 — PRIMARY** |
| S2 | trial 5 | trial 6 |

`trials = 6`. **No configuration outside this table will ever be run for the verdict.** Extending
the grid is a new pre-registration with a new trial count.

**The primary is trial 4 and it is chosen a priori, not by result.** `L = 52` because Pontiff's
mechanism is reversion to the fund's **own** mean and one year is the natural window for it;
`H = 4` because `EDGE_SHORTLIST.md` §5 wrote the null as **"next-month return"** on 2026-08-16
before any CEF price was touched. Both halves of the primary are quotations of prior commitments.

**Eligibility, applied identically in both periods:**

1. The fund must have a NAV, a price and a discount on the rebalance date and on the exit date.
2. The fund must have at least `L` prior weekly observations (S1 only). Funds that do not are
   dropped from that date, not back-filled.
3. Price on the rebalance date **> $5.00**. Sub-$5 CEFs are 25 of the 360 today and this
   programme does not model their friction (`T9_PREREGISTRATION.md` §4 exclusion 2, same
   threshold, same reason).
4. **No liquidity screen is applied**, because CEFConnect's `AvgDailyVolume` is a *today*
   snapshot with no history and screening a 2021 date on a 2026 statistic is look-ahead. The
   consequence — that the book may contain names too thin to trade — is priced instead, by the
   measured spread of §2e and by the stress ladder of §5.
5. **The live `shortable` flag of §2d is NOT used as a screen**, for the same reason. Its
   consequence is reported as an executability caveat in the result, not smuggled into the
   backtest as a filter that had no 2021 counterpart.

---

## 5. Costs — the T6-corrected PER-SIDE model, with the CEF spread MEASURED not assumed

`costs.py` is imported and a `CostModel` is constructed with **both** sides named explicitly.

| component | charged | basis |
|---|---|---|
| `entry_half_spread` | **11.53 bp — MEASURED** | §2e, 3,067 CEF symbol-days, first party. **Not zero, and not the auction rail**: `costs.measured_auction_leg` refuses for CEFs and `EDGE_SHORTLIST.md` §2e measured CEF closing auctions at $0.0–0.3 M. Every leg of this candidate crosses a continuous spread. |
| `exit_half_spread` | **11.53 bp — MEASURED, declared separately** | Same measurement, stated in its own component so a change to one leg cannot silently move the other. That separation *is* the T6 correction. |
| `entry_extra_slippage` / `exit_extra_slippage` | **0 bp** | A stated LOWER BOUND, not a claim. Swept by the stress ladder. |
| regulatory pass-through, **sale legs only** | SEC §31 at **0.278 bp** of sale notional + FINRA TAF at **$0.000166/share** sold | Charged at the top of the 2016–2026 §31 range in both periods, as T9 and T10 did. |
| commission | **0** | Alpaca, $0/share. |
| borrow | **33 bp/yr** on short notional, per **calendar** day held | `costs.measured_borrow_annual("etb_general_collateral")`, B22G's measured ETB general-collateral median. **A stated FLOOR**: §2d shows 48 % of the universe is not borrowable at this broker at all, and a CEF that is borrowable is not guaranteed to be general collateral. |

**Turnover is decomposed with `costs.split_turnover` per name at every rebalance**, so a name
that stays in the same decile is charged nothing and a name that flips from long to short is
charged an exit *and* an entry. Realised turnover is **reported**, not assumed.

**Stress ladder, reported always:** extra slippage on both sides at `0` (primary), `5`, `10`,
`25`, `50` bp; plus a half-spread ladder at `0`, `0.5 h`, `h` (primary), `2 h`; plus the B19P
frictionless diagnostic (every cost zero, regulatory included). *If it loses at zero cost, no
execution improvement can rescue it.*

---

## 6. Held-out test — 2024-03-01 → 2026-08-14, run ONCE

Reported:

- net mean per week and its t-statistic, at the primary and at all six declared trials;
- the weekly portfolio series: net annualised Sharpe, annualised return, max drawdown, t;
- **DSR** (`stats.deflated_sharpe`) on the held-out **weekly net** series, `trials = 6`, with
  `sharpe_variance` from `stats.sharpe_variance_from_trials` over the six declared trials'
  design-window per-observation Sharpes; sensitivity reported at `trials = 1` and `trials = 12`;
- **decile-label permutation**, 10,000 shuffles, seed `20260817`: at each rebalance the long and
  short decile memberships are redrawn at random from the same eligible pool, same counts, same
  dates, same holding period. Only *which fund was called wide-discount* changes. Add-one
  corrected, right tail;
- **and, mandatorily beside it, the dispersion ratio** — the real book's per-week return
  dispersion divided by the permutation null's. `FINDINGS.md` §5c, extended by `T10_RESULT.md`
  §5: a cross-sectional label permutation on a sorted return series answers *"is this partition
  special?"*, not *"is the mean positive?"*, and the two diverge by exactly the factor the sort
  picks up. **A ratio far from 1 means the p-value is not about the mean, and the result must say
  so.**
- the **NAV-return decomposition** diagnostic of §1 — price return, NAV return, and the implied
  discount change, per leg;
- realised turnover per rebalance and the implied annual friction bill;
- the full stress ladder of §5 and the zero-cost diagnostic;
- a year-by-year net breakdown;
- the design-window result, reported and labelled as the design window.

---

## 7. Kill conditions — fixed in advance

**DEAD if ANY of the following holds:**

0. **the history gate of §3 fails** → `DEAD-BY-INSUFFICIENT-HISTORY`; **or**
1. net mean per week **≤ 0** on the held-out period at the primary cost rung; **or**
2. decile-label permutation right-tail **p ≥ 0.05**; **or**
3. **DSR < 0.95** at `trials = 6`.

**SURVIVES** only if **all four** pass. Anything else is *not established*, which is not a pass.

**If DEAD, the result states what would have to change** — more history, a different rail, a
cheaper universe — rather than nominating a replacement reflexively; `FINDINGS.md` §10 records
that the remaining shortlist is thin and that the next move is an owner scope call.

---

## 8. What was probed before this file was written

Counts, dates, flags and spreads only.

- `/api/v3/pricinghistory/ADX/{P}` for eleven candidate period strings, to establish which five
  are served and at what sampling frequency (§2a). Row counts and dates only.
- `/api/v3/DailyPricing` once — the 360-fund live snapshot (§2c, §2d).
- `/api/v3/pricinghistory/{t}/5Y` and `/1Y` for all 360 tickers, **cached**, and interrogated for
  **presence and date only** (§2a). `scripts/t12_cef_discount.py` contains no arithmetic on a
  price or a discount and the file says so.
- Alpaca `/v2/assets` once, read-only, for the live tradable/shortable/ETB flags (§2d).
- Alpaca `/v2/stocks/quotes`, SIP, 12 dates × 360 names, for the quoted half-spread (§2e). A
  spread is a cost, not a return.
- Alpaca `/v2/stocks/bars` for `ADX`, `PDI`, `BSTZ`, `XADEX` over one month of 2016, to test
  whether the NAV pseudo-ticker is served and therefore whether deeper NAV history exists inside
  the broker. **It is not**: `XADEX` returns zero bars where `ADX` returns five. Presence only.

## 9. What this pre-registration does not claim

- It does not claim CEFConnect's discount is the discount an account could have acted on. NAV is
  struck after the close and published with a lag; the weekly series is what the site serves
  today for a past date, and whether it was *available* on that date is not something this feed
  can be asked. The design mitigates it by acting on the **following** week's price, never the
  same day's, but the mitigation is not a proof.
- It does not repair survivorship (§2c) and does not know the sign of the bias.
- It does not model queue position, partial fills, or size-dependent impact in a $389 M-median
  fund — the median CEF's whole closing auction is under $0.3 M.
- It does not model the borrow constraint as a constraint (§2d); it prices borrow as a cost and
  reports the 48 % non-shortable share as an executability caveat.
- It does not test the *forward daily collection* idea `EDGE_SHORTLIST.md` §5 proposed. That is a
  prospective instrument, not a test, and it is out of scope here.
- It does not authorise execution of any kind. Real money remains owner-gated.
