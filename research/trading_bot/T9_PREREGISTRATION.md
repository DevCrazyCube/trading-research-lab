# T9 — pre-registration: spin-off forced-selling drift

**Frozen before any return, signal, portfolio, drift or Sharpe was computed.** Written
2026-08-17. Everything done before this file existed was an **event census and a price-
availability probe** — counts of records and counts of bars, no price ever divided by another
price. The census is `research/trading_bot/T9_EVENT_CENSUS.json`, it is reproduced in §2 below,
and it is the reason this pre-registration has a **power gate that the other two did not**.

Candidate under test: **#4 in `EDGE_SHORTLIST.md`** (score 14/20, uniqueness U = 4 — the highest
uniqueness of anything left on the list). Nominated in `T7_RESULT.md` §9 and `FINDINGS.md` §10 as
the successor after #1 (`T3_RESULT.md`, held-out DSR 0.9379) and #2 (`T7_RESULT.md`, held-out
permutation p = 0.213, DSR 0.076) both died.

Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, moments, Sharpe,
drawdown) and `costs.py` (the **T6-corrected per-side** cost model) are imported, never copied.
Calendar, HTTP transport, paging rule, official-auction-print reader and quoted-half-spread
measurement come from `scripts/t3_pressure_reversal.py` unchanged. Events come from the
universe-wide corporate-actions sweep T7 already paid for
(`research/data/t7_cache/corporate_actions_all.json.gz`).

---

## 1. The claim, and its null

**Mechanism claimed.** When a parent spins off a subsidiary, every index fund holding the parent
receives a stub that is **not in the index it tracks**. It must sell that stub on a schedule it
did not choose, for reasons unrelated to the stub's value. Institutional mandates (market-cap
floors, sector limits, "no non-index holdings") force the same sale. The selling is therefore
**price-insensitive, dated and mechanical**, and it is absorbed at a concession. Cusatis, Miles &
Woolridge (1993) document long-run outperformance of spun-off subsidiaries; the forced-selling
story predicts the concession is largest in the weeks immediately after the distribution.

**H1.** A long position in the stub, opened at the first official closing auction print on or
after the spin-off ex-date and held for a fixed number of sessions, market-hedged short SPY,
earns a **positive net (post-friction) return**.

**H0 (the null actually tested).** The market-adjusted return of the stub over the holding window
is **≤ 0** net of friction; receiving a spun-off stub carries no information about its subsequent
market-adjusted return.

**The pairing is mandatory and it is the short SPY leg**, for the reason `FINDINGS.md` §5c
records: an unpaired long basket of 2020–2026 US equities measures the equity premium, not a
spin-off effect. A **same-day, same-holding-period control basket** drawn from the non-event
universe is reported beside every result as a second, independent pairing.

## 2. The census — stated BEFORE the test, because it decides the verdict

Every number in this section is a **count**, taken before this file was written, from the
universe-wide `/v1/corporate-actions` sweep and from bar-presence checks. Nothing here is a
return.

### 2a. What the 243 cached "spin-off records" actually are

| step | count |
|---|---|
| raw `spin_offs` records, 2016-01-04 → 2026-08-14 | **243** |
| unique by the provider's own `id` | 228 |
| unique by `(source_symbol, new_symbol, ex_date)` | **225** |
| …of which `new_symbol` is **not a ticker** — contingent value rights (`…CVR…`), contingent/escrow entitlements (`…CNT…`, `…ESC…`), bare CUSIPs, e.g. `878CVR018`, `007ESC031`, `09175M606` | **48 dropped** |
| **candidate spin-off stub events** | **177** |

The 48 are merger consideration mis-typed as `spin_off`. Nothing quotes them; they are not a
distributed equity stub. The exclusion is a definition (`is_tradeable_stub` in
`scripts/t9_spinoff_drift.py`), applied identically in both periods, and the count it removes is
reported rather than absorbed.

### 2b. The distribution over time, and the fact that kills the standard split

| year | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| candidate stub events | **0** | 1 | **0** | 1 | 5 | 14 | 22 | 37 | 25 | 47 | 23 |

**The provider's spin-off history is truncated, not thin.** Verified by direct probe today:
Corteva (`CTVA`, spun from DowDuPont 2019-06-03), Dow (`DOW`, 2019-04-01), Adient (`ADNT`,
2016-10-31), Lamb Weston (`LW`, 2016-11-09), Valvoline (`VVV`, 2017-05), Resideo (`REZI`,
2018-10-29), Garrett Motion (`GTX`, 2018-10-01), Arlo (`ARLO`, 2018-12-31) and Brighthouse
(`BHF`, 2017-08-04) are **all** real, large, well-known US spin-offs in the design window, and
`/v1/corporate-actions` returns **no `spin_off` record for any of them** — several return cash
dividends over the identical window, so the symbols and the window are being served. The gap is
in the corporate-actions feed's spin-off coverage before ~2020, not in our query.

**Consequence, stated before the test:** the T3/T7 split (design 2016–2021, held out 2022–2026)
**cannot be executed as designed for this candidate**. The design window contains 21 records, of
which the availability probe finds **14** with a bar on the ex-date. Fourteen events cannot
select a configuration; a grid fitted on them would be noise, and freezing that noise would be
worse than not freezing at all.

### 2c. Price availability (bar presence only — no price was read into any return)

| | design 2016–2021 | held out 2022–2026 | all |
|---|---|---|---|
| candidate stub events | 21 | 156 | 177 |
| with a daily bar on the ex-date | 14 | 111 | 125 |
| with an **official closing auction print** on the ex-date | 14 | 105 | 119 |
| with ≥ 55 of the next 60 sessions | 14 | 108 | 122 |
| entry-day close > $5 | 14 | 90 | 104 |
| entry-day dollar volume > $1 M | 14 | 91 | 105 |

## 3. How the split is handled, given §2b — and the rule that replaces it

**There is no design phase and no fitted parameter.** Because 14 design-window events cannot
select anything, this pre-registration takes the opposite route and is *stricter* than T3's or
T7's: **the configuration is declared here from the literature and from `EDGE_SHORTLIST.md`'s own
prior wording, and nothing is ever chosen by looking at a result.**

- The primary holding period is **H = 60 trading sessions**, because `EDGE_SHORTLIST.md` §5
  candidate 4 wrote the null as *"market-adjusted return of the stub over the 1–60 trading days
  after the spin-off date is zero"* — written on 2026-08-16, before any spin-off price was
  touched, and quoted here as the a-priori commitment it is.
- Two further horizons, **H = 21** and **H = 126**, are declared as robustness and are the
  **entire** trial space. `trials = 3`.
- **No configuration outside {21, 60, 126} × {the single universe rule of §4} will ever be run for
  the verdict.** If the grid is extended, that is a new pre-registration with a new trial count.
- The held-out period **2022-01-03 → 2026-08-14** is still reported separately and is still the
  headline number, because it is the period in which no human in this programme has looked at a
  spin-off return. The design window is reported beside it as 14 events and labelled as such.

## 4. Universe, events and exclusions — identical in both periods

**Event.** A unique `spin_off` record with `ex_date` in [2016-01-04, 2026-08-14] and a
ticker-shaped `new_symbol` (§2a).

**Entry day.** The first session on or after `ex_date` on which the stub has **both** a raw daily
bar and an official closing auction print (condition `6`, largest size if several). Searched
forward at most **5 sessions**; if none, the event is dropped. Regular-way trading in a stub
begins on the ex-date, so this is the earliest price an account could actually have paid.

**Exclusions, applied identically in the design and held-out periods:**

1. Dropped if no entry day is found within 5 sessions of `ex_date`.
2. Dropped if the entry-day closing auction price is **≤ $5.00**. A sub-$5 stub is not a name this
   programme can model friction for: T1 §2d measured a small-cap most-active quoting at
   **119.6 bp**, and pretending otherwise is the error this rig exists to prevent.
3. Dropped if entry-day **dollar volume ≤ $1 M** (raw `vw × volume`). Same reason. Declared here,
   not discovered later.
4. Dropped if the stub has fewer than `0.9 × H` sessions with bars in the H sessions after entry
   **and** no terminal price (§5 exit rule) — i.e. dropped only when the position could neither be
   held nor closed.
5. Dropped if SPY has no closing auction print on the entry day or the exit day.
6. Dropped if `new_symbol == source_symbol` (a restatement, not a distribution).
7. If the same `new_symbol` appears with several ex-dates, only the **earliest** is an event; the
   later records are restatements of the same distribution.

**No universe screen is applied to the parent.** The stub, not the parent, is what is traded.

## 5. The trade

For each surviving event, with entry day `t0` and exit day `t1` = the H-th session after `t0`:

```
r_stub = ( P_close_auction(stub, t1) - P_close_auction(stub, t0) ) / P_close_auction(stub, t0)
r_spy  = ( P_close_auction(SPY,  t1) - P_close_auction(SPY,  t0) ) / P_close_auction(SPY,  t0)
gross  = 0.5 * r_stub - 0.5 * r_spy          # dollar neutral, gross exposure 100%
```

**Terminal price rule, declared in advance.** If the stub stops having bars before `t1` — it was
acquired, delisted, or merged away — the exit is the **last official closing auction print
available**, and if there is none, the last daily close. The position is closed there and the SPY
leg is closed on the same date. Refusing to model this would silently drop exactly the events
where forced selling ended in a takeover, which is the direction that would flatter the result.

**Two reported objects, because they answer different questions:**

- **the per-event cross-section** — one net excess return per event, which is what the permutation
  and the power calculation act on;
- **the daily portfolio series** — equal weight across every stub currently held, dollar-neutral
  against SPY, one observation per session on which the book holds at least one name. This is the
  series `deflated_sharpe` acts on, because DSR needs a return series (`FINDINGS.md` §5c).

**Control basket (second pairing).** For each event, `k = 5` symbols drawn without replacement,
seed `20260817`, from the set of symbols that have bars on both `t0` and `t1`, are **not** a stub
of any spin-off, and pass the same $5 / $1 M entry-day filters. Their mean market-adjusted return
over the identical dates is the control. It differs from the event only in whether the name was
spun off.

## 6. Costs — the T6-corrected PER-SIDE model, with the stub spread MEASURED not assumed

`costs.py` is imported and a `CostModel` is constructed with **both** sides named explicitly.

| component | charged | basis |
|---|---|---|
| `entry_half_spread` | **measured**, see below | The entry is the stub's **closing auction** on the entry day — a single-price call with no bid-ask to cross *if it fills at the print*. **M0 is still unperformed** (`FINDINGS.md` §10; two dead candidates already rest on it) and a fresh spin-off stub's closing auction is the thinnest auction in this programme. The primary rung therefore charges the **measured quoted half-spread of the stub names themselves**, not zero. |
| `exit_half_spread` | **measured**, same number, **declared separately** | The exit is the same object 60 sessions later. Stated in its own component so a future change to one leg cannot silently move the other — that is the T6 correction. |
| `entry_extra_slippage` / `exit_extra_slippage` | **0 bp** | A stated LOWER BOUND, not a claim. Swept by the stress ladder. |
| regulatory pass-through, **sale legs only** | SEC §31 at **0.278 bp** of sale notional + FINRA TAF at **$0.000166/share** sold | Two sale legs: the stub sold at `t1` and the **short sale** of SPY at `t0`. §31 charged at the top of the 2016–2026 range in both periods. |
| commission | **0** | Alpaca, $0/share. |
| borrow | **33 bp/yr** on the 50 % SPY short notional, per **calendar** day held | `costs.measured_borrow_annual("etb_general_collateral")` — B22G's measured ETB general-collateral median. SPY is easy to borrow. **At H = 60 sessions this is ~87 calendar days and is a real charge, not a rounding error.** |

**`h` is measured first-party, on the traded names.** Median `(ask − bid) / (2 × mid)` from SIP
quotes in `[15:59:59, 16:00:00) ET` — the same instrument, window and declared deviation T3 used
(`t3.measure_half_spread`) — sampled on **the actual entry and exit days of the actual stubs**,
not on a liquid proxy universe. Reported in the result whatever it turns out to be.

**Stress ladder, reported always:** half-spread charged on **all four legs** at `0`, `0.5h`, `h`
(primary), `2h`, `4h`, plus the B19P frictionless diagnostic (every cost zero, regulatory
included). *If it loses at zero cost, no execution improvement can rescue it.*

## 7. THE POWER GATE — the gate this candidate exists to face

Spin-offs are rare. `FINDINGS.md` §5 records this programme's own version of the lesson: *at
n ≈ 2,000 with 43 % volatility you can rank shapes but not certify levels.* Here n is **two
orders of magnitude smaller**. So the power question is settled **before** the verdict, on
**design-window and structural quantities only**, and it can produce a verdict on its own.

**Procedure, fixed here:**

1. σ̂ — the standard deviation of the per-event net excess return — is estimated on the
   **design window only** (2016–2021, the 14 events of §2c), at H = 60. A design-window estimate
   is what a design window is for.
2. The **minimum detectable effect** at the conventional 80 % power, two-sided α = 0.05, is
   `MDE = 2.80 × σ̂ / √n_test`, with `n_test` the held-out event count.
3. The **benchmark effect** is the literature's own, converted to this holding period:
   Cusatis, Miles & Woolridge (1993) report roughly **+10 %/yr** of abnormal return in the first
   years after a spin-off, and that is the *largest* figure in the literature — McConnell &
   Ovtchinnikov (2004) find it concentrated in a few outliers, and Invesco's S&P Spin-Off ETF
   (`CSD`) was **liquidated in 2020**, which is a real-world out-of-sample datum against the
   effect surviving. +10 %/yr over 60 trading sessions ≈ **+2.4 %**.

> **GATE.** The held-out test is **adequately powered** only if `MDE ≤ 2.4 %`, i.e. only if this
> instrument could detect the strongest documented version of the effect eight times out of ten.

4. **If the gate fails, the verdict is `DEAD-BY-INSUFFICIENT-POWER`, and it cannot be overturned
   by any held-out number.** The held-out configuration is still run **exactly once** and reported
   in full — a point estimate with an honest confidence interval is worth having, and hiding it
   would be its own dishonesty — but a positive result under a failed power gate is reported as
   *not established*, never as SURVIVES. This is the guardrail the task set, written down before
   the number exists so it cannot be renegotiated after.
5. The result also reports **`n_required`** — the number of events needed to reach MDE = 2.4 % —
   and, at the observed arrival rate of spin-offs, **how many years of prospective collection that
   is**. That number, not the point estimate, is this candidate's real finding.

## 8. Held-out test — 2022-01-03 → 2026-08-14, run ONCE

Reported:

- net mean per event and its t-statistic, at H = 60 and at the two declared robustness horizons;
- the daily portfolio series: net annualised Sharpe, annualised return, max drawdown, t;
- **DSR** (`stats.deflated_sharpe`) on the held-out **daily portfolio** net series, `trials = 3`,
  with `sharpe_variance` from `stats.sharpe_variance_from_trials` over the three declared
  horizons' per-observation Sharpes; sensitivity reported at `trials = 12`;
- **event-label permutation**, 10,000 shuffles, seed `20260817`: each real event is replaced by a
  control name drawn from the same day's eligible non-stub pool, holding the same dates, the same
  count and the same market move. Only *which stock was the spin-off stub* changes. Add-one
  corrected, right tail. This is the instrument `FINDINGS.md` §5c prescribes for a label object;
- the control-basket pairing;
- the full stress ladder of §6 and the zero-cost diagnostic;
- a year-by-year net breakdown;
- the design-window 14 events, reported and labelled as underpowered rather than omitted.

## 9. Kill conditions — fixed in advance

**DEAD if ANY of the following holds:**

0. **the power gate of §7 fails** → `DEAD-BY-INSUFFICIENT-POWER`; **or**
1. net mean per event **≤ 0** on the held-out period at the primary cost rung; **or**
2. event-label permutation right-tail **p ≥ 0.05**; **or**
3. **DSR < 0.95** at `trials = 3`.

**SURVIVES** only if **all four** pass. Anything else is *not established*, which is not a pass.

**If DEAD, a next candidate is nominated** from `EDGE_SHORTLIST.md`, with the reason, in the
result document.

## 10. What was probed before this file was written

Counts and structure only. **No price was divided by any other price. No return, signal,
portfolio, drift, Sharpe or drop-off exists anywhere on disk at the moment this file is hashed.**

- the cached `corporate_actions_all.json.gz` was read for record counts by type and by year;
- five live `/v1/corporate-actions` calls, universe-wide, one per year 2016–2020, `spin_off`
  counts only, to confirm the truncation of §2b independently of the cache;
- one live `/v1/corporate-actions` call for nine named symbols over 2016–2020, returning **which
  action types exist**, to confirm those symbols are served while their spin-offs are absent;
- raw daily bars and auction prints for the 177 stubs, their parents and SPY were **downloaded and
  cached**, and interrogated for **presence only** — `is this date in the bar dict` — to produce
  §2c. `scripts/t9_spinoff_drift.py` contains no arithmetic on a price and the file states so.

## 11. What this pre-registration does not claim

- It does not claim the provider's spin-off list is complete **after** 2020 either. §2b shows it
  is demonstrably incomplete before 2020; a feed that lost eight major 2016–2019 spin-offs may be
  losing smaller ones later, and this test cannot see what it is not sent. The direction of that
  bias is unknown, and *unknown* is what it is reported as.
- It does not model when-issued trading, the due-bill period, odd-lot/cash-in-lieu treatment of
  fractional stub entitlements, or the parent's own price behaviour.
- It does not model queue position, partial fills, or size-dependent impact in a stub's first
  closing auction — which is exactly where a $100 k account is *least* likely to be a negligible
  participant, and where M0's absence bites hardest.
- It does not correct survivorship perfectly; Alpaca's inactive list is a partial record.
- It does not authorise execution of any kind. Real money remains owner-gated.
