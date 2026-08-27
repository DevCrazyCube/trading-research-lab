# T10 — pre-registration: overnight-vs-intraday premium harvesting

**Frozen before any return, signal, portfolio, Sharpe or premium was computed on the auction
panel.** Written 2026-08-17. Everything done before this file existed was a **census of counts**
— symbol-days, sessions, auction-print availability — reproduced in §2. No price has been
divided by any other price anywhere in this candidate's code. §11 lists exactly what was read.

Candidate under test: **#6 in `EDGE_SHORTLIST.md`** (score 13/20). It is the fourth equity
candidate through the full bar after #1 (`T3_RESULT.md`, held-out DSR 0.9379), #2
(`T7_RESULT.md`, permutation p = 0.213), #4 (`T9_RESULT.md`, dead by insufficient power).

Harness: **T2**, `scripts/trading_bot/` — `stats.py` (DSR, permutation, moments, Sharpe,
drawdown) and `costs.py` (the **T6-corrected per-side** model, including the **M0** measured
auction leg) are imported, never copied. Calendar, universe screen, auction-print reader and
corporate-action calendar come from `scripts/t3_pressure_reversal.py` unchanged, against the
cache T3 already paid for.

---

## 0. THE DISCLOSURE THAT HAS TO COME FIRST

**Part of this candidate's held-out window has already been looked at, and pretending otherwise
would be the exact dishonesty this programme exists to prevent.**

`research/B22F_OVERNIGHT_INTRADAY_SPLIT.md` (written 2026-08-16, before this task) already
reports, **year by year through 2026**, the SPY overnight and intraday split on
split/dividend-adjusted bars:

| leg | ann. return | ann. vol | Sharpe |
|---|---|---|---|
| overnight (prev close → 09:30) | +10.06 % | 11.55 % | +0.87 |
| intraday (09:30 → 16:00) | +5.79 % | 13.36 % | +0.43 |

So for **configuration A1 (SPY) the 2022–2026 period is not blind.** I have seen that the
market-level overnight-minus-intraday difference is roughly **+4.3 %/yr gross over 2016–2026**,
and that 2022 was −13.8 % overnight against −5.0 % intraday. That is stated here, in advance,
as a **contamination of A1**, and it is why:

- the pre-registration below declares its expectation for A1 **before** the run (§9), so the
  result cannot be re-narrated afterwards;
- the four **Family B** configurations — a cross-sectional overnight/intraday sort — are
  genuinely blind. **No cross-sectional overnight or intraday quantity has ever been computed
  anywhere in this programme**, on any period.

**Nothing in B22F used auction prints.** It used adjusted 30-minute bars. Every price in T10 is
an official single-price auction print, which is a different instrument; but the correlation
between the two is obviously near 1 and the disclosure stands regardless.

---

## 1. The claim, and its null

**Mechanism claimed.** Lou, Polk & Skouras (JFE 2019, *"A tug of war: Overnight versus intraday
expected returns"*) document that the equity premium and the premia of standard anomaly
portfolios accrue **overnight**, and are partially reversed **intraday**; and that the split is
**persistent at the firm level** — a stock whose returns have historically arrived overnight
continues to earn overnight and to give back intraday. The proposed structural causes are
clientele-based: retail/liquidity-demanding order flow concentrated at the open, institutional
and index flow concentrated at the close, and inventory risk that dealers will not carry
overnight without compensation. None of those is an information event, so attention does not
obviously compete them away.

**H1.** A position that is **long the overnight session and short the intraday session** — the
paired difference — earns a **positive net (post-friction) return**, either at the market level
(Family A) or in the cross-section of the firm-level split (Family B).

**H0 (the null actually tested).** The overnight and the intraday session carry the **same**
expected return, so the paired difference is ≤ 0 net of friction; and the firm-level history of
that split carries no information about its future value.

**The pairing is mandatory and it is the whole strategy.** `FINDINGS.md` §5c records this
programme's own version of the error: an unpaired overnight-only book measures the equity
premium, not an overnight *premium*. B22F is the measurement that makes it concrete — SPY
overnight Sharpe 0.87 against full-day 0.89 means **overnight-only is exposure re-slicing, not
alpha**, and `EDGE_SHORTLIST.md` §5 candidate 6 says so in those words. Overnight-only is
therefore **reported as a diagnostic and is not one of the eight trials**.

**And the thing that will most likely decide this:** the paired difference requires the book to
be **flipped at every auction, twice a day, every day**. That is ~400 % of gross notional traded
per session and **~200 % of gross notional SOLD per session**. This is the highest-turnover
candidate in the programme by two orders of magnitude, and the per-side cost model is
load-bearing in a way it was not for T3, T7 or T9.

---

## 2. The census — counts only, taken before this file was written

From `scripts/t3_pressure_reversal.py`'s cached artifacts: `calendar`, `asset_pool`,
`monthly_bars`, `auctions`, `corporate_actions`.

| quantity | value |
|---|---|
| official auction records on disk (`t3_cache/auctions.json.gz`) | **3,618,237** symbol-days, **1,648** symbols, 2016-01-04 → 2026-08-14 |
| …with **both** an official open and an official close print | 3,562,029 |
| point-in-time top-500-ADV universe months | 128 (2016-02 → 2026-08), 500 names in every month |
| NYSE/Nasdaq sessions in window | 2,669 |
| sessions dropped — early close on t or t−1 | 42 |
| sessions dropped — no universe (January 2016 has no month m−1) | 18 |
| **sessions kept** | **2,608** — 1,468 design, 1,140 held out |
| first / last session kept | 2016-02-01 / 2026-08-14 |
| symbol-days dropped — no prior-session official close print | 3,289 |
| symbol-days dropped — no open **and** close print on session t | 1,356 |
| symbol-days dropped — a corporate action lands on t or t−1 | **57,253** |
| **symbol-days kept** | **1,242,102** — 705,838 design, 536,264 held out |
| median names per session | 485 design, 475 held out |
| SPY sessions surviving the identical filter | 1,403 design, 1,055 held out |

**Power is not this candidate's problem and that is worth stating before the test.** T9 died on
n = 62 events. Here the held-out period is **1,140 daily observations** and half a million
symbol-days. What T10 can fail on is effect size and friction, not counting.

---

## 3. The split, and the freeze

- **Design window: 2016-02-01 → 2021-12-31** (1,468 sessions). All eight declared
  configurations are run here, and **exactly one** is selected.
- **Held-out window: 2022-01-03 → 2026-08-14** (1,140 sessions). Run **once**, after the
  frozen configuration is written to `research/trading_bot/T10_FROZEN_CONFIG.json`.
- The evaluation script **refuses to run the held-out period if the frozen config file is
  absent**, exactly as `t7_evaluate.py` does, so it cannot select a configuration on the spot.
- **Selection rule, fixed here:** the configuration with the **highest net annualised Sharpe on
  the design window at the primary cost rung**. Ties break on the higher net mean per session.

---

## 4. Universe, sessions and exclusions — identical in both periods

**Universe.** The point-in-time top-500-ADV screen already used by T3 and T7: month *m*'s
tradeable set is the 500 US-equity symbols with the largest raw dollar ADV in month *m−1*,
restricted to raw close > $5 and month-*m−1* dollar ADV > $20 M, drawn from the **14,234 active
plus 19,197 inactive** asset pool so the backtest is survivorship-bias-free. No value from month
*m* or later touches the selection. `top_n` is a declared trial axis (§6).

**Session.** A session `t` enters the panel iff:

1. `t` and the preceding session `t−1` are both **full 16:00 closes** (early closes excluded —
   the same exclusion T3, T7, T9 and M0 all made, for the same reason);
2. `t` lies in [2016-02-01, 2026-08-14] and has a universe month.

**Symbol-day.** A symbol `i` enters session `t` iff:

3. `i` is in the point-in-time universe for month of `t`;
4. `i` has an **official closing auction print** (condition `6`, largest size wins) on `t−1`
   **and** an **official opening auction print** (condition `O`) **and** an official closing
   print on `t`;
5. **no corporate action of any kind** lands on `t` or `t−1` for `i` — any `ex_date`,
   `process_date`, `effective_date`, `payable_date` or `record_date` in the universe-wide
   `/v1/corporate-actions` sweep;
6. all three prices are strictly positive.

**Why exclusion 5 is the load-bearing one, and why it is exclusion rather than adjustment.**
Auction prints are **raw**. A dividend or a split falls entirely inside the *overnight* leg and
none of it inside the intraday leg, so on raw prices an ex-date manufactures a spurious negative
overnight return of exactly the dividend — a systematic ~1.5–2 %/yr bias **against** the very
thing being tested. Dropping those symbol-days rather than adding the dividend back is the
choice made here because (i) the economics of holding across an ex-date is *drop plus dividend*,
which T7 measured first-party at **0.95 × D against D**, i.e. a residual of ~5 % of a ~0.5 %
quarterly dividend ≈ 0.25 bp — smaller than any number this test can resolve; and (ii) it uses
the identical corporate-action calendar T3 already built, with no new arithmetic. It removes
**4.4 %** of symbol-days, identically in both periods, and that count is reported.

---

## 5. The two strategy families, stated as formulae

For a surviving symbol-day, with `C(i,t−1)`, `O(i,t)`, `C(i,t)` the three official prints:

```
r_on(i,t) = O(i,t) / C(i,t-1) - 1          # overnight session
r_id(i,t) = C(i,t) / O(i,t)   - 1          # intraday session
```

### Family A — market level, unit gross exposure at all times

Weight vector at the **close of t−1** (entered by MOC): `w = +1/N_t` on every surviving name.
Weight vector at the **open of t** (flipped by MOO): `w = −1/N_t` on every surviving name.

```
gross_A(t) = mean_i r_on(i,t) - mean_i r_id(i,t)
```

`A1` is the same thing with the single name **SPY** in place of the basket.

### Family B — cross-sectional tug of war, dollar-neutral, unit gross exposure

Signal for name `i` at session `t`, computed **only from sessions ≤ t−1**:

```
s(i,t) = mean over the last K sessions with a surviving record of [ r_on(i,·) - r_id(i,·) ]
```

Requires at least `ceil(0.6 K)` such sessions or the name is not ranked that day. Rank the
day's ranked names on `s`; `L` = top `cut` fraction, `S` = bottom `cut` fraction.

Overnight book (entered by MOC at t−1): `+0.5/|L|` on L, `−0.5/|S|` on S.
Intraday book (flipped by MOO at t): `−0.5/|L|` on L, `+0.5/|S|` on S.

```
gross_B(t) = 0.5*(mean_L r_on - mean_S r_on) + 0.5*(mean_S r_id - mean_L r_id)
```

**Every input to `s(i,t)` is known before the closing auction of `t−1`**, which is when the
first leg is submitted — an MOC must be at the broker by 15:50, and `s` uses nothing after the
*previous* session's close. There is no 15:50/15:59 lookahead of the kind T3's first
auction-to-auction diagnostic contained (`FINDINGS.md` §5e); the signal is one full session
stale by construction.

### The reported objects

- **the daily net return series** — one observation per surviving session; this is what
  `deflated_sharpe` acts on, per the rule in `FINDINGS.md` §5c;
- **the per-session cross-section of name-level paired differences** (Family B only) — what the
  label permutation acts on;
- **diagnostics, explicitly not trials:** overnight-only and intraday-only leg returns, the
  full-day return of the same basket, and SPY's full-day return over identical sessions.

---

## 6. The trial space — exactly eight, declared here, and nothing else

| # | family | configuration |
|---|---|---|
| A1 | A | instrument = **SPY** |
| A2 | A | equal-weight basket, `top_n` = **100** |
| A3 | A | equal-weight basket, `top_n` = **300** |
| A4 | A | equal-weight basket, `top_n` = **500** |
| B1 | B | `top_n` = 500, `K` = **21**, `cut` = **0.10** |
| B2 | B | `top_n` = 500, `K` = **21**, `cut` = **0.20** |
| B3 | B | `top_n` = 500, `K` = **63**, `cut` = **0.10** |
| B4 | B | `top_n` = 500, `K` = **63**, `cut` = **0.20** |

**`trials = 8`.** No configuration outside this table will ever be run for the verdict. If the
grid is extended, that is a new pre-registration with a new trial count. DSR sensitivity is
additionally reported at `trials = 24` (8 × the three plausible unstated axes: weighting,
holding side, and cost rung), because a declared trial count that flatters the searcher is the
failure mode DSR exists to catch.

---

## 7. Costs — the T6-corrected PER-SIDE model with the M0 auction leg, charged on exact turnover

**Turnover is computed exactly, not assumed.** At each auction the runner holds the previous
weight vector and the target weight vector and computes, per name,
`traded_i = |w_new,i − w_old,i|`, `sold_i = max(0, w_old,i − w_new,i)`. Those are summed and
charged. For Family A that is 2.0 of notional traded and 1.0 sold at each of the two daily
auctions — **4.0 traded and 2.0 sold per session** — and the runner asserts it rather than
hard-coding it.

| component | charged at the primary rung | basis |
|---|---|---|
| `entry_half_spread` / `exit_half_spread` | **0 bp**, stated separately for each side | Both legs are official single-price auction prints and the backtest **marks at the same print**, so there is no bid-ask to cross. This is no longer a mechanism argument: **M0 measured** an official closing print on **99.96 %** of top-500-ADV symbol-days clearing a median **$37 M**, so a retail order is not the auction. `costs.measured_auction_leg` is the source. |
| `entry_extra_slippage` / `exit_extra_slippage` | **0.0019 bp** per leg | `costs.measured_auction_leg(...)`'s `auction_non_fill_provision`, taken at the **most expensive of the three liquid M0 tiers** (`A_rank_1_50`, P(no print) = 0.106 %). Tiers B and C measure exactly 0. A FLOOR: it prices the manual unwind of an unfilled MOC and **not** the gap risk of carrying an unintended position. |
| **SEC §31** | **0.278 bp of SALE notional**, ≈ **0.556 bp/session** for Family A | $27.80 per $1 M of sale proceeds — the **top** of the 2016–2026 range, charged at that level in both periods. Charged on **every** sale leg including short sales, which is the law. |
| **FINRA TAF** | **$0.000166 per share**, charged on **every share traded** | Legally sale-side only, so charging both directions **over-charges by ~2×**; that is the conservative direction and it is stated, not optimised away. Priced at the actual auction print of that leg. |
| commission | **0** | Alpaca, $0/share. |
| borrow | **33 bp/yr** on **overnight short notional only**, per **calendar** day | `costs.measured_borrow_annual("etb_general_collateral")`, B22G's measured ETB general-collateral median. Family A carries **no overnight short** (its short is intraday) and is charged zero here. Family B carries 0.5 short overnight and **is** charged. |
| **intraday borrow / locate** | **0**, declared a LOWER BOUND | A US broker does not accrue a stock-loan fee on a position flat at settlement, and Alpaca charges none intraday. But a short sale needs a Reg SHO locate, and locate availability in 500 names every single morning is **not measured by this programme**. Stated as an unpriced risk, not as a zero cost. §12. |

**Stress ladder, reported always.** `h` = T3's own first-party measured median quoted half-spread
in this exact universe and window (**1.13 bp** 2016–2021, **1.43 bp** 2022–2026, ≈20,000
symbol-days per period), charged on **every leg** at `0` (primary), `0.5h`, `h`, `2h`, `4h`,
plus the B19P **frictionless** diagnostic with every cost including regulatory set to zero.

> **The arithmetic that makes the ladder decisive here, computed in advance:** at rung `h` the
> strategy pays `4.0 × 1.43 = 5.7 bp per session ≈ 1,440 bp/yr` on top of the ~140 bp/yr of
> regulatory pass-through. **If M0's live half — that our broker's on-close order joins the
> cross — is wrong, this candidate is dead by a factor of ten and no signal can rescue it.**
> That is written here, before the numbers, because it is the honest statement of what the
> whole result rests on.

---

## 8. The gates — fixed in advance

Computed on the **held-out** period, at the **primary cost rung**, on the **single frozen**
configuration.

**DEAD if ANY of the following holds:**

1. **net mean per session ≤ 0**; **or**
2. **permutation p ≥ 0.05** (right tail, add-one corrected, 10,000 draws, seed `20260817`);
3. **DSR < 0.95** at `trials = 8`.

**SURVIVES** only if all three pass. Anything else is *not established*, which is not a pass.

### The permutation instrument, declared per family because they are different objects

- **Family A — session-label exchangeability.** Under H0 the overnight and the intraday session
  of a given day are exchangeable in mean, so the sign of `r_on(t) − r_id(t)` is symmetric about
  zero. Each draw multiplies every session's **gross** difference by an independent ±1 and
  re-charges the identical deterministic cost schedule. Right tail on the net mean. This is the
  standard randomisation test for a paired design and it is valid under the symmetry the null
  asserts.
- **Family B — cross-sectional label permutation.** Each draw shuffles the signal ranks across
  the names **within each session**, preserving that session's realised cross-section of
  overnight and intraday returns exactly, and changing only *which name was ranked where*. This
  is T3's instrument and the one `FINDINGS.md` §5c prescribes for a label object.

### DSR inputs

`stats.deflated_sharpe(net_daily, trials=8, sharpe_variance=...)` with `sharpe_variance` from
`stats.sharpe_variance_from_trials` over the **eight design-window per-observation Sharpes** —
the honest cross-trial dispersion, not an invented one. Annualisation uses **observations per
year computed from the panel**, not a hard-coded 252.

### The power statement — declared here, reported always, and it LABELS the verdict

Computed on **design-window and structural quantities only**, before any held-out number exists:

```
MDE_sharpe(annualised) = 2.80 / sqrt(n_test / obs_per_year)      # 80% power, two-sided a=0.05
```

with `n_test = 1,140`. Two benchmarks are reported beside it:

- `benchmark_B22F` — B22F's own first-party SPY split, `(10.06 − 5.79)%` of annual return over
  the **design-window measured** volatility of the paired difference. This programme's own
  measurement of the market-level version of the effect.
- `benchmark_design` — the design-window net annualised Sharpe of the frozen configuration.

**Interpretation rule, fixed now so it cannot be renegotiated:** if the candidate fails the gates
**and** `MDE > max(benchmark_B22F, benchmark_design)`, the verdict is
**`DEAD — UNDERPOWERED`**: dead, and the instrument could not have detected the documented
effect even had it been present. If it fails and `MDE ≤` that maximum, the verdict is
**`DEAD — NO SIGNAL`**. The distinction changes what the programme should do next and nothing
about the verdict itself. This gate cannot promote a failure to a pass.

---

## 9. What I expect, written before the run, so it cannot be re-narrated afterwards

Stated because §0 has already shown me part of the answer for A1 and honesty requires putting the
prediction on the record rather than discovering it.

- **A1 (SPY) will be positive gross and small.** B22F implies ≈ **+4.3 %/yr** gross over
  2016–2026, against a paired-difference volatility that must be ≈ 15–18 %/yr if the two legs are
  close to uncorrelated — an annualised Sharpe of roughly **0.25**, against an MDE near **1.3**.
  On that arithmetic **A1 cannot pass gate 3 even if every basis point of it is real**, and I
  expect a `DEAD — UNDERPOWERED` label rather than a `NO SIGNAL` one for the Family A branch.
- **Family B is the only branch with a live chance**, because a dollar-neutral cross-sectional
  sort strips out the market's own overnight drift and can carry a much higher Sharpe per unit
  of return. It is also the branch that is genuinely blind.
- **Regulatory friction alone is ≈ 140 bp/yr** and is unavoidable at this turnover. Any
  configuration whose gross edge is under ~1.5 %/yr is dead on arithmetic before statistics.
- If the primary rung passes and rung `h` does not, **the verdict is still decided at the primary
  rung** — that is what "primary" means and it is fixed here — but the result document will say
  so in its first paragraph, because a candidate that lives only inside an unverified live fill
  assumption is not a candidate anyone should fund.

## 10. A rig check that runs before the held-out period is touched

The equal-weight top-500 basket's **full-day** return over the design sessions, against SPY's
full-day return over the identical sessions, must reproduce the known equal-weight-versus-cap-
weight gap of 2016–2021 (RSP vs SPY, ≈ −3 to −4 %/yr; T7 independently measured −1.36 bp/day on
its own event-day subsample). A rig that reproduces a number it was not built to reproduce is the
only kind worth trusting, and this one costs nothing.

## 11. What was read before this file was hashed

**Counts and structure only. No price was divided by any other price. No return, signal,
portfolio, Sharpe or premium for this candidate exists anywhere on disk at the moment this file
is hashed.**

- `t3_cache/{calendar,asset_pool,monthly_bars,auctions,corporate_actions}.json.gz` were read for
  **record counts and key presence** — "is this (symbol, date) in the auction dict", "is this
  date in the corporate-action set" — to produce §2;
- `research/trading_bot/M0_AUCTION_FILLS.json` was read for its non-fill provisions;
- `research/B22F_OVERNIGHT_INTRADAY_SPLIT.md` was read in full — it is a **pre-existing**
  measurement of this programme's, on different instruments (adjusted 30-minute bars, SPY only),
  and §0 discloses exactly what it shows me;
- `T3/T7/T9` pre-registrations and results, `EDGE_SHORTLIST.md`, `FINDINGS.md`, `costs.py`,
  `stats.py`.

## 12. What this pre-registration does not claim

- It does not claim MOC/MOO orders from **our** broker join the cross. That is M0's **C4**, the
  half a tape cannot answer, and it is **unperformed**. Four candidates now rest on it. §7's
  ladder prices being wrong about it, and the arithmetic there says being wrong about it is fatal
  for T10 specifically.
- It does not model **queue position, partial fills, or size-dependent impact** in the auction.
  At $100 k against auctions clearing $28–130 M this is tolerable; at any size it is not, and no
  capacity claim is made.
- It does not price a **Reg SHO locate** for 500 short sales every morning, or the risk that a
  locate is unavailable. That is a real operational constraint that this backtest treats as
  frictionless, and it is stated rather than hidden.
- It does not model **short-sale price tests** (Rule 201 circuit-breaker), which would prevent
  the intraday short leg in any name down 10 % on the prior session.
- It does not model **taxes**. This strategy realises ~100 % of its P&L as short-term gains, and
  T7 §6's lesson — that loss *usability* under IRC §1211(b), not a rate differential, is the real
  obstacle — applies with more force here at 250 round trips a year. Owner-facing, account-type
  dependent, not decided by me.
- It does not correct survivorship perfectly; Alpaca's inactive list is a partial record.
- It does not authorise execution of any kind. Real money remains owner-gated.
