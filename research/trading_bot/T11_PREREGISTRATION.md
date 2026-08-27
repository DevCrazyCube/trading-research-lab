# T11 — pre-registration: cash-merger arbitrage spread

**Frozen before any return, spread, portfolio or Sharpe was computed.** Written 2026-08-17.
Everything done before this file existed was an **event census, a price-availability probe and a
measurement of how often an announcement date can be recovered from the news endpoint** — counts
of records, counts of bars, counts of headline matches. No price has been divided by any other
price and no cash `rate` has been divided by any price anywhere on disk at the moment this file
is hashed. The census is `research/trading_bot/T11_EVENT_CENSUS.json`, reproduced in §2.

Candidate under test: **#7 in `EDGE_SHORTLIST.md`** (score 12/20). Predecessors #1 (`T3_RESULT.md`,
held-out DSR 0.9379), #2 (`T7_RESULT.md`, p = 0.213, DSR 0.076), #4 (`T9_RESULT.md`,
DEAD-BY-INSUFFICIENT-POWER) and #6 (`T10_RESULT.md`, DSR 0.3772) are all dead.

Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, moments, Sharpe,
drawdown) and `costs.py` (the **T6-corrected PER-SIDE** cost model) are imported, never copied.
Calendar, HTTP transport, paging rule, official-auction-print reader and the quoted-half-spread
instrument come from `scripts/t3_pressure_reversal.py` unchanged. Events come from the
universe-wide corporate-actions sweep T7 already paid for
(`research/data/t7_cache/corporate_actions_all.json.gz`).

---

## 1. The claim, its null, and the two things the data cannot give us

**Mechanism claimed** (`EDGE_SHORTLIST.md` §7). After a cash-merger announcement the target
trades at a discount to the offer price. The discount pays for deal risk and for time. Holding
the target to close captures it. Small, retail-scaled deals are claimed to be under-arbitraged.

**H0, exactly as the shortlist wrote it**: *annualised spread capture equals the risk-free rate*
after deal-break losses. The benchmark is therefore **T-bills**, not zero and not SPY.

**H1**: a long position in a target with an announced all-cash offer, held to the cash payment,
earns a **positive net return in excess of T-bills**.

### 1a. Two data facts that are established BEFORE this test and that shape it

**(i) There is no announcement date, and it cannot be manufactured.** `/v1/corporate-actions`
returns the **effective** date and the cash **rate**; it does not return the announcement date or
the original terms. §2c reports a first-party measurement of how well a deterministic Benzinga
headline rule recovers one. The measurement is the reason the traded rule below **never uses an
announcement date**.

**(ii) The feed contains only deals that COMPLETED.** A `cash_merger` record exists because cash
was paid. A deal that was announced and then broke — the entire left tail of this strategy —
leaves **no corporate action of any type**, so it is not rare in this dataset, it is
*structurally absent*. No filter, no window and no amount of care recovers it from this feed.

### 1b. What this test therefore is: an ORACLE UPPER BOUND

Because of 1a(ii), a straight backtest on these events would be conditioned on completion and
would report a number no live account could earn. This pre-registration does not pretend
otherwise. It **grants the strategy the two oracles it would need**, on purpose, and asks whether
it makes money *even then*:

- **Oracle A — completion.** The book only ever holds deals that in fact closed. It never takes a
  break loss. Real break rates are commonly put at **5–10 %** of announced deals.
- **Oracle B — the close date.** The book knows the effective date in advance and enters exactly
  `H` sessions before the target's last trading day. It never sits through an extension and never
  misses the close.

Both oracles are **favourable to the strategy** and neither is available to a live account. This
is the same instrument as `B19P`'s "even trading for free loses 16.89 %": if a rule fails with the
constraints removed, no improvement in execution or information can rescue it.

**One direction of the bound is not favourable and is stated here rather than discovered later.**
Restricting entry to the last `H` sessions may capture *less* annualised spread than entering at
announcement, because merger spreads are usually wider further from close. That is why three
horizons are run (§3) and why the **term structure of the annualised spread across H is reported
as a first-class output**. The bound is a strict upper bound on the *break-free, perfectly-timed*
return; whether the annualised spread is larger further out is measured, not assumed.

**Consequence for the verdict, fixed now:** a **failure** of the oracle test is a **DEAD** verdict
for the candidate, because the implementable version is strictly worse on both oracles. A **pass**
of the oracle test is **not** a SURVIVES on its own — it must additionally clear the break gate of
§7, which is what converts a completion-conditioned mean into a statement about a book that bears
break risk.

## 2. The census — stated BEFORE the test, because it decides the design

Every number in this section is a **count**. `scripts/t11_merger_arb.py` contains no arithmetic on
a price and says so in its module docstring.

### 2a. What the cached `cash_mergers` records are

| step | count |
|---|---|
| raw `cash_merger` records, 2016-01-04 → 2026-08-14 | **2,028** |
| unique by the provider's own `id` | 1,917 |
| unique by `(acquiree_symbol, effective_date, rate)` | **1,902** |
| …of which the acquiree is **not ticker-shaped** (bare CUSIPs, e.g. `30241C208`) | **120 dropped** |
| **ticker-shaped candidate cash mergers** | **1,782** |

### 2b. The distribution over time, and the truncation it exposes

| year | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ticker-shaped cash mergers | **0** | **0** | **0** | **0** | 85 | 182 | 171 | 350 | 327 | 368 | 299 |

**The provider's cash-merger history begins in 2020, not 2016.** This is the same truncation T9
found in the spin-off feed (`T9_PREREGISTRATION.md` §2b) on the same endpoint, and it is recorded
here as a second instance of it. The declared T3/T7 design window (2016-01-04 → 2021-12-31)
therefore contains only **two years** of events, not six. That is enough to select among three
declared horizons — it is not enough to fit a model, and nothing is fitted (§3).

### 2c. Announcement-date recoverability — the cheap first step §7 of the shortlist asked for

`EDGE_SHORTLIST.md` §7 wrote: *"Cheap first step: measure how reliably an announcement date can be
recovered from the news endpoint on a sample of 50 known deals, before committing."* It has now
been measured on **80** deals drawn at random (seed `20260817`) from the 1,782, searching Benzinga
headlines tagged to the acquiree over the 760 days before the effective date, under two
deterministic rules:

- **LOOSE** — any acquisition-shaped phrase (`to be acquired`, `definitive merger agreement`,
  `/share in cash`, `going private`, `tender offer`, …).
- **STRICT** — the same, but the acquiree must appear in the **object** position of the
  acquisition, matched through the issuer name from `/v2/assets`.

Measured result (§2c of `T11_EVENT_CENSUS.json`):

| rule | matched | of 80 |
|---|---|---|
| LOOSE | **42** | 52.5 % |
| STRICT | **14** | 17.5 % |
| issuer name available at all from `/v2/assets` | **29** | 36 % |

**Neither rule is an announcement-date feed, and the gap between them is the error rate.** Manual
inspection of the LOOSE matches finds the acquiree *acquiring somebody else* (`PAE to Acquire
CENTRA Technology`, `Convey Health to Acquire HealthSmart`, `Nexstar … to Acquire BestReviews from
Tribune Publishing`), an activist letter (`2717 Partners Urges Logility Board to Explore Strategic
Alternatives`), a litigation headline (`Alimera Takes Legal Action Against ANI`) and a newsletter
round-up (`The Daily Biotech Pulse`) — so LOOSE's 52.5 % is an upper bound on recall bought with a
false-positive rate of roughly a third. STRICT's 17.5 % is bounded by a different failure: the
`/v2/assets` endpoint has **no issuer name for 64 % of these delisted symbols**, and where it does
have one the ticker has frequently been **recycled** to an unrelated live instrument (`LMNX` →
a Defiance ETF, `MIC` → a 2× daily ETF, `TRIL` → a Tidal trust). A symbol-keyed join to a delisted
acquiree is not safe.

**And the recall failure is not random.** The misses are concentrated in the small, thinly-covered
names — `news_items_seen = 0` for a large share of them — which is precisely the "retail-scaled
small deals are genuinely under-arbitraged" population the mechanism claims the edge lives in. A
test built on the recovered subset would be a test of *large, well-covered deals*, mislabelled.

**Decision, taken here and not later:** the traded rule does not use an announcement date. It uses
Oracle B (§1b) instead, and the lookahead that Oracle B creates is fenced by §4's discount cap.

### 2d. Price availability (bar and print presence only — no price read into any return)

Counted before this file was written, from `T11_EVENT_CENSUS.json` §funnel. Every row is a
presence check or a threshold comparison; no price is divided by any other price.

| funnel step (H = 21) | design 2020–2021 | held out 2022–2026 |
|---|---|---|
| ticker-shaped cash mergers | **267** | **1,515** |
| `rate > 0` | 267 | 1,515 |
| has any raw daily bar | 204 | 1,363 |
| **stops trading** within 10 sessions of the effective date (§4 exclusion 3) | 176 | 1,280 |
| has a raw bar on the entry day `t0` | 176 | 1,279 |
| has an **official closing auction print** on `t0` | 167 | 813 |
| entry close > $5 | 142 | 678 |
| entry dollar volume > $1 M | **117** | **487** |

At H = 5 the funnel ends at 117 / 482 and at H = 63 at 112 / 443. The discount cap of §4
exclusion 8 is applied *after* this funnel and its count is reported in the result. Note that the
official-closing-print requirement is where the biggest single cut falls in the held-out window
(1,279 → 813): a third of these names are OTC or otherwise have no closing auction, which is a
statement about what fraction of the completed-merger population is reachable at all.

## 3. The split, the trial space, and the one thing the design window selects

- **Design window: 2020-01-02 → 2021-12-31.** Its *only* jobs are (a) to select the primary
  horizon `H` from the three declared below, once, and (b) to supply σ̂ for the power gate of §9.
  **The selection criterion is fixed here: the `H` with the highest design-window t-statistic on
  the per-event net excess return over T-bills.** Ties break to the smaller `H`. Nothing else in
  the rule is ever chosen by looking at a result, in either window.
- **Held out: 2022-01-03 → 2026-08-14.** Run **once**. It is the headline.
- **The entire trial space is `H ∈ {5, 21, 63}` trading sessions.** `trials = 3`. 5 sessions is a
  week to close, 21 a month, 63 a quarter. No fourth horizon, no other universe rule, no other
  entry price and no other cost rung will ever be run for the verdict. Extending the grid is a new
  pre-registration with a new trial count.
- All three horizons are reported on the held-out period as robustness and as the term structure
  §1b requires; only the design-selected `H` decides the gates.

## 4. Universe, events and exclusions — identical in both periods

**Event.** A unique `cash_merger` record (§2a) with `effective_date` in [2016-01-04, 2026-08-14],
a ticker-shaped `acquiree_symbol`, and `rate > 0`.

**Last trading day `t_last`.** The last session with a raw daily bar on or before `effective_date`.

**Entry day `t0`.** The session exactly `H` trading sessions before `t_last`.

**Exclusions, applied identically in the design and held-out periods:**

1. `rate` absent or ≤ 0.
2. No raw daily bar for the acquiree anywhere in the sample.
3. **The name does not stop trading.** Dropped unless the acquiree has **no** daily bar more than
   **10 trading sessions** after `effective_date`. A cash merger extinguishes the equity; a symbol
   that keeps printing bars afterwards is a **recycled ticker** (§2c measured that recycling
   happening) or a record that does not mean what it says. This is a presence rule, not a price
   rule, and it is the cheapest available defence against the symbol-reuse contamination.
4. No raw daily bar on `t0`, or `t0` falls before the start of the sample.
5. No **official closing auction print** (condition `6`, largest size if several) on `t0`.
6. Entry-day closing auction price **≤ $5.00**. T1 §2d measured a small-cap most-active quoting at
   **119.6 bp**; this rig does not pretend to model friction below $5.
7. Entry-day **dollar volume ≤ $1 M** (raw `vw × volume`). Declared here, not discovered later.
8. **THE DISCOUNT CAP — the lookahead fence.** Dropped if the entry-day implied gross spread
   `(rate − P₀)/P₀` exceeds **+20 %**.

   Exclusion 8 exists because Oracle B can place `t0` **before the deal was announced**, and
   buying a stock the session before a 30 % takeover bid is not merger arbitrage, it is
   clairvoyance. A pre-announcement entry shows up as an implausibly large "discount", so the cap
   removes it. The cap is **conservative by construction** — it deletes the largest winners and
   nothing else — and the count it removes, together with what those events would have
   contributed, is reported rather than absorbed. Negative spreads are **not** capped: they are
   adverse, and discarding adverse observations is the error this rig exists to prevent. A
   symmetric `|spread| ≤ 20 %` variant is reported beside the primary as declared robustness.

No screen is applied to the acquirer. The target, not the acquirer, is what is traded.

## 5. The trade, and the accounting

For each surviving event with entry day `t0`, last trading day `t_last`, effective date `E` and
cash rate `R`:

```
P0     = official closing auction print of the target on t0          (raw, unadjusted)
gross  = R / P0 - 1                                                   # cash received per share
rf     = BIL total return from t0 to the cash date                    # the null's benchmark
net    = gross - entry_cost - exit_cost - regulatory
excess = net - rf
```

- **Cash date** = `E + 5 calendar days`. Merger consideration is not in the account on the
  effective date; five days is a conservative stand-in for the paying-agent lag, and it is
  conservative in the right direction because it *lengthens* the window the T-bill benchmark is
  compounded over. Declared here.
- **Risk-free** = **BIL** (1–3 month T-bill ETF), **dividend-adjusted** daily bars, first-party
  from the same SIP feed. It is a traded instrument, so it is the return the account actually
  forgoes. Compounded across the exact calendar window.
- **Prices are RAW.** `R` is a cash amount per share as of `E`; dividing it by a split- or
  dividend-adjusted price is a category error that would manufacture a spread out of the
  adjustment factor.
- **No hedge leg.** An announced cash deal is pinned to `R` and carries near-zero market beta;
  a short SPY leg would add borrow cost and variance without cancelling a common move that is not
  there. SPY is nevertheless carried as a **reported paired control** (§8), not as a position.

**Two reported objects, because they answer different questions:**

- **the per-event cross-section** — one net excess return per event, which the permutation and the
  power calculation act on;
- **the daily portfolio series** — equal weight across every deal held on that session, one
  observation per session on which the book holds at least one name, net of costs and of the daily
  BIL return. This is the series `stats.deflated_sharpe` acts on, because DSR needs a return
  series (`FINDINGS.md` §5c).

## 6. Costs — the T6-corrected PER-SIDE model, with the spread MEASURED on the traded names

`costs.py` is imported and a `CostModel` is constructed with **both** sides named explicitly.

| component | charged | basis |
|---|---|---|
| `entry_half_spread` | **measured**, `h` below | The entry is the target's closing auction on `t0`. M0 has measured that an official print exists and is large, but not that *our* order joins the cross (`FINDINGS.md` §10), so the primary rung charges the **measured quoted half-spread of the merger targets themselves**, not zero. |
| `exit_half_spread` | **the same `h`, charged anyway** | The exit is **not a trade**: cash is paid by the acquirer's paying agent for the extinguished share. A half-spread is therefore *over*-conservative here. It is charged rather than argued down, and it is stated in its own component so a future change to one leg cannot silently move the other — that is the T6 correction. |
| `entry_extra_slippage` / `exit_extra_slippage` | **0 bp** | A stated LOWER BOUND, not a claim. Swept by the stress ladder. |
| regulatory pass-through | SEC §31 at **0.278 bp** + FINRA TAF at **$0.000166/share**, charged on the **cash-out** as if it were a sale | A merger cash-out is not an exchange sale and almost certainly bears neither. Charged anyway; adverse, and declared. |
| commission | **0** | Alpaca, $0/share. |
| borrow | not charged | Long only. The component is still constructed (`costs.measured_borrow_annual`) so the model refuses if it is missing. |

**`h` is measured first-party on the traded names.** Median `(ask − bid) / (2 × mid)` from SIP
quotes in `[15:59:59, 16:00:00) ET` — the T3 instrument and its declared deviation
(`t3.measure_half_spread`) — sampled on **the actual entry days of the actual targets**. Reported
in the result whatever it turns out to be, per period.

**Stress ladder, reported always:** half-spread charged on both legs at `0`, `0.5h`, `h`
(primary), `2h`, `4h`, plus the B19P frictionless diagnostic (every cost zero, regulatory
included). *If it loses at zero cost, no execution improvement can rescue it.*

## 7. THE BREAK GATE — the fat left tail, modelled explicitly

`FINDINGS.md` has no entry for a strategy killed by a tail, because no candidate so far had one.
This one does, it is the whole reason merger arb pays anything, and §1a(ii) established that this
dataset **cannot show it**. So it is modelled, in advance, three ways, and one of them is a gate.

**Break loss `L`.** On a break the target falls back towards its pre-announcement price. Cash-deal
announcement premia are commonly in the 20–40 % range, so the loss from a price near the deal
value is of that order. Declared band: `L ∈ {−10 %, −20 %, −25 %, −30 %, −40 %}`, **primary
`L = −25 %`**.

**Break rate `b`.** Commonly quoted at **5–10 %** of announced deals. Declared band
`b ∈ {0, 2 %, 5 %, 6 %, 8 %, 10 %, 15 %}`.

**(a) The break-even break rate `b*`.** With `μ` the held-out mean net excess return per event
(Oracle A, i.e. break-free) the mixture mean is `(1 − b)·μ + b·(L − rf)` and

```
b* = μ / ( μ + rf − L )
```

is the break rate at which the whole edge is exactly zero. `b*` is reported for every `L` in the
band, and it is the single most decision-relevant number this test produces.

> **GATE (break).** The candidate clears the break gate only if `b*` at the primary `L = −25 %`
> exceeds **10 %** — the pessimistic end of the quoted failure band. A `b*` below 5 % means the
> measured spread cannot survive even an optimistic break rate and the candidate is DEAD on the
> tail alone, whatever its mean says.

**(b) The tail, not the mean.** The full per-event distribution is reported: mean, median, sd,
skew, kurtosis, min, p1, p5, and the count and identity of losing events — including the losers
that exist *inside* the completed set (entry above the final cash rate, renegotiated-down terms).

**(c) A break-injected Monte Carlo.** 10,000 draws, seed `20260817`: resample the held-out event
book, mark a fraction `b` of events as breaks and replace their return with `L`, and report the
portfolio mean, 5 % VaR, 5 % CVaR and P(annual loss) on the `b × L` grid. A mean-only result is
not acceptable under this task's guardrail and this is the object that satisfies it.

## 8. Held-out test — 2022-01-03 → 2026-08-14, run ONCE

Reported:

- net mean excess-over-T-bills per event and its t-statistic, at the design-selected `H` and at
  the two robustness horizons; annualised, with the mean holding period stated;
- the daily portfolio series: net annualised Sharpe, annualised return, max drawdown, t;
- **DSR** (`stats.deflated_sharpe`) on the held-out daily portfolio net-excess series,
  `trials = 3`, `sharpe_variance` from `stats.sharpe_variance_from_trials` over the three
  horizons' per-observation Sharpes; sensitivity at `trials = 12`;
- **event-label permutation**, 10,000 draws, seed `20260817`: each real target is replaced by a
  control name drawn from the T3 point-in-time top-500-ADV pool that has an official closing print
  on both `t0` and the exit date, held over the identical dates. Only *which stock was the merger
  target* changes. Add-one corrected, right tail. This is the instrument `FINDINGS.md` §5c
  prescribes for a label object;
- the paired difference against SPY over identical dates, reported (not a position);
- the full break analysis of §7;
- the full stress ladder of §6 and the zero-cost diagnostic;
- the discount-cap accounting: how many events exclusion 8 removed and what they would have added;
- a year-by-year net breakdown;
- the design window reported beside it and labelled as two years, not six.

## 9. The power gate

σ̂ — the standard deviation of the per-event net excess return — is estimated on the **design
window only** (2020–2021), at the design-selected `H`. The minimum detectable effect at 80 %
power, two-sided α = 0.05, is `MDE = 2.80 × σ̂ / √n_test`.

**Benchmark effect.** Mitchell & Pulvino (2001) find risk arbitrage earns roughly **4 % a year in
excess of the risk-free rate after transaction costs** — and their sample is 4,750 deals over 35
years, which is the strongest version of this claim in the literature. Converted to the holding
period: `benchmark = 0.04 × (mean holding period in calendar days) / 365`.

> **GATE (power).** The held-out test is adequately powered only if `MDE ≤ benchmark`. If it
> fails, the verdict is **DEAD-BY-INSUFFICIENT-POWER** and cannot be overturned by any held-out
> number; the run still happens once and is reported in full with an honest confidence interval,
> but a positive result under a failed power gate is reported as *not established*, never as
> SURVIVES. `n_required` is reported beside it.

## 10. Kill conditions — fixed in advance

**DEAD if ANY of the following holds:**

0. the power gate of §9 fails → `DEAD-BY-INSUFFICIENT-POWER`; **or**
1. net mean excess-over-T-bills per event **≤ 0** on the held-out period at the primary cost rung
   and the design-selected `H`; **or**
2. event-label permutation right-tail **p ≥ 0.05**; **or**
3. **DSR < 0.95** at `trials = 3`; **or**
4. the **break gate** of §7 fails — `b*(L = −25 %) ≤ 10 %`.

**SURVIVES** only if **all five** pass, and even then the verdict is explicitly labelled as
**conditional on Oracle A and Oracle B** (§1b) and therefore as an upper bound, with a live
paper-trading prospective test the only way to remove the oracles. Anything else is *not
established*, which is not a pass.

**If DEAD, a next candidate is nominated** from `EDGE_SHORTLIST.md`, with the reason, in
`T11_RESULT.md`.

## 11. What was probed before this file was written

Counts and structure only. **No price was divided by any other price, no cash rate was divided by
any price, and no return, spread, portfolio or Sharpe exists anywhere on disk at the moment this
file is hashed.**

- the cached `corporate_actions_all.json.gz` was read for record counts by type and by year;
- raw daily bars and official auction prints for the 1,782 acquirees, `SPY` and `BIL` were
  **downloaded and cached**, and interrogated for **presence only** — "is this date in the bar
  dict", "is there a closing print on this date" — plus the entry-day close and dollar volume,
  which are compared to the $5 / $1 M thresholds of §4 and to nothing else;
- 80 news queries against `/v1beta1/news` for the announcement probe of §2c, scored for
  **headline matches**, with no price involved;
- two `/v2/assets` calls (active and inactive) for issuer names, used only by that probe.

## 12. What this pre-registration does not claim

- It does not claim the provider's cash-merger list is complete **after** 2020 either. §2b shows
  it is empty before 2020; a feed that has no 2016–2019 cash mergers at all may be losing smaller
  ones later. This test cannot see what it is not sent, and the direction of that bias is unknown.
- It does not model stock or mixed consideration (`stock_mergers`, `stock_and_cash_mergers`),
  competing bids, price bumps, appraisal rights, contingent value rights, or the odd-lot and
  cash-in-lieu treatment of fractional entitlements.
- It does not model queue position, partial fills, or size-dependent impact in the closing auction
  of a name that is about to be extinguished — which is exactly where a $100 k account is least
  likely to be a negligible participant.
- It does not model the financing, margin or short-rebate structure a real risk-arbitrage desk
  uses, and it takes no leverage.
- It does not correct survivorship perfectly; Alpaca's inactive list is a partial record.
- **It does not, and structurally cannot, measure the deal-break rate first-party.** §7 models it
  from a declared band and reports the break-even rate. That is a sensitivity analysis, not a
  measurement, and it is labelled as one everywhere it appears.
- It does not authorise execution of any kind. Real money remains owner-gated.
