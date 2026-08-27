# T13 — PRE-REGISTRATION: does risk-shaping add anything beyond holding less?

**Written and hashed before any parameter was fitted and before the held-out window was read.**
The runner (`scripts/t13_risk_shaping.py`) refuses to load held-out bars in `design` mode, so the
freeze is enforced by the code and not by my memory of having been careful.

---

## 0. Why this exists, and what would make it a waste of time

Four directional equity candidates are dead (T3, T7, T9, T10). `FINDINGS` §5h states the reason in
arithmetic: at 80 % power, certifying a true annualised Sharpe *S* on daily data needs `(2.80/S)²`
years of **held-out** data, we hold 4.6 years of equity history under the T3/T7 split, and every
remaining shortlist candidate sits below S = 0.5, i.e. needs 31 years. A fifth directional test buys
an honest negative and nothing else.

The only two results that survived this entire programme — the crypto deadness screen and the BTC
crash filter's drawdown reduction — are **distribution-shape claims, not mean claims**. That is why
they survived: a shape claim does not need the mean to clear the noise floor. T13 asks whether that
transfers to equities.

**The thing that would make this a waste of time, named in advance.** A filter that reduces drawdown
*only because it reduces average exposure* has discovered nothing: you can reduce drawdown by holding
70 % of the index and 30 % T-bills, permanently, with zero skill, zero turnover and zero timing. That
null killed the crypto funding-carry claim and it is the primary gate here. **A drawdown reduction is
a finding only if it beats the same reduction bought by holding less.**

**An honesty item that no freeze can fix.** The 200-day moving-average filter is one of the most
data-mined rules in public finance (Faber 2007; Dow theory before that; Zakamulin's replications
after). Freezing my parameters on 1928–1989 protects against *my* fitting. It does not protect
against the *world's* — the rule reached me already selected on roughly this data. **This is exactly
why the verdict does not rest on whether the filter looks good, but on whether it beats two nulls
that hold the same amount of the same asset.** Those nulls are immune to prior data-mining because
they contain no parameter at all.

---

## 1. Data (all fetched, hashed and manifested by `scripts/t13_data.py`)

| series | what | span | role |
|---|---|---|---|
| `spx_price.csv` | ^GSPC daily close, Yahoo | 1927-12-30 → today | **the signal, always.** Price-only, which is what a moving-average rule is computed on |
| `sp500tr.csv` | ^SP500TR daily close, Yahoo | 1988-01-04 → today | **primary held-out return series** — index total return |
| `spy_tr.csv` | SPY daily adjusted close, Yahoo | 1993-01-29 → today | **confirmatory held-out return series** — a real tradeable instrument, carrying real tracking error and a real expense ratio |
| `cash.csv` | 3-month bill / commercial-paper yield, FRED | 1928-01 → today | the cash leg, and the risk-free rate in every Sharpe |

The signal series is **never** the return series. That removes the retroactive-adjustment problem
from the signal entirely: Yahoo's adjusted closes embed dividends and splits that had not happened
yet, and a rule that compares a level to its own moving average would be comparing two retroactively
restated numbers. ^GSPC close is the number that actually printed.

**Declared imprecisions** (also recorded in the data script, so they cannot drift):

- Bill yields are on a **bank-discount** basis and are used here as simple annualised yields. This
  **understates** the cash return by ~2–4 % relative. The filter sits in cash, so the error runs
  against the filter. Left uncorrected.
- Pre-1934 cash is the NBER 3-month **commercial paper** rate, not a bill. It is a credit instrument
  and slightly too generous. It touches the **design window only** — no held-out number depends on it.
- The design window's return series is ^GSPC **price only**: 1928–1989 has no daily total-return
  index. Dividends were 3–5 %/yr then, so design-window CAGR is understated for every strategy
  including buy-and-hold. **The design window selects a parameter; it reports no finding.**

---

## 2. Windows — frozen

| window | span | use |
|---|---|---|
| **design** | 1928-01-03 → 1989-12-29 (≈62 yr) | choose every parameter. May be looked at freely. |
| **held out** | 1990-01-02 → 2026-08-14 (≈36.6 yr) | never read until §5 is written and hashed |

The design window contains 1929–32, 1937–38, 1946, 1962, 1966, 1969–70, 1973–74 and 1987. The
held-out window contains 1990, 1998, 2000–02, 2008–09, 2011, 2018, 2020 and 2022. **Both windows
contain enough crashes to say something about crashes** — which is the whole reason this candidate
gets a 36-year held-out window while T3/T7 got 4.6. The unit of evidence for a drawdown claim is a
*crash*, not a *day*, and that is the arithmetic that makes T13 worth running when T11/T12 are not.

---

## 3. Timing convention — stated once, used everywhere

> **T13-L1.** The exposure applied to the close-to-close return of day *t* is a function only of
> closes up to and including day ***t−2***.

You see the close of day *t−2*, you place an order that fills at any time during day *t−1*, and you
are marked from the close of *t−1* to the close of *t*. This is **one full session more conservative
than the published implementations**, which decide from *C(t−1)* and fill at that same close — the
exact "fill at the price that produced the decision" that `scripts/trading_bot/engine.py` layer 2
forbids and that T3's nine-minute lookahead was a smaller version of.

The *C(t−1)* convention is computed too and reported as a **lag diagnostic**, never as a result.
FINDINGS §5h: *audit the implementation against the pre-registration's timing sentence, and do not
assume lookahead flatters* — in T10 the correction ran the other way.

**Warm-up is undefined, not "out".** Before *N* closes exist the SMA has no value. Treating undefined
as "out of the market" makes the rule bank a crash it never traded through. Every run starts at the
first bar where every declared statistic is defined, and buy-and-hold is forced onto the identical
bars so the pairing cancels.

---

## 4. The declared grid — 14 trials, counted now

**Family A — crash filter.** `w = 1 if C(t−2) > SMA_N(C(t−N−1..t−2)) else 0`, remainder in cash.
N ∈ **{50, 100, 150, 200, 250}** → **5 trials**.

**Family B — volatility-targeting overlay.** `w = clip(target / realised_vol_L(ending t−2), 0, w_max)`,
realised vol = annualised stdev of the last *L* daily simple returns; remainder in cash; any excess
over 1.0 financed at cash + 150 bp.
L ∈ **{20, 60}** × target ∈ **{10 %, 15 %}** × w_max ∈ **{1.0, 1.5}** → **8 trials**.

**Family C — combined.** Frozen A multiplied by frozen B → **1 trial**.

**Total declared trials: 14.** This number goes into every deflated Sharpe below and is not revised.

**Declared robustness variants, which are NOT selection trials** (run at the frozen parameters only,
after the freeze, and reported as sensitivities): monthly rather than daily signal evaluation; the
*C(t−1)* lag; the SPY instrument; cost multipliers ×1/×2/×4; and the expanding-window walk-forward
of §7.

### Selection rule, frozen

Per family, on the **design window only**, rank configurations by **MAR = CAGR / maxDD**. Take the
top-ranked; if any other configuration is within **5 %** of the top MAR, take the **median parameter
value among that tied set**. The plateau rule is not decoration: FINDINGS §5 records that a knife-edge
optimum means the effect lives in the tuning, and a broad optimum means it belongs to the payoff
shape. If the tied set is not contiguous in the parameter, that is reported as a red flag.

---

## 5. The nulls — this is the experiment

Every null holds **the same asset** and differs only in *how much* and *when*. All are computed on
the held-out window on the identical bars, with identical costs.

| null | definition | what it isolates |
|---|---|---|
| **N1 — ex-post vol-matched buy-and-hold** | constant `w*` such that the realised annualised volatility of `w*·index + (1−w*)·cash` over the **held-out window** equals the filter's realised volatility over the same window. Solved by bisection to 1e-6. | **the primary gate.** N1 is fitted with hindsight the filter does not get. That is deliberate: it is the strongest possible form of "you could have just held less". |
| **N2 — ex-ante vol-matched buy-and-hold** | same, but `w*` is fixed from the **design** window and applied unchanged. | the fair fight, with no hindsight on either side |
| **N3 — exposure-matched buy-and-hold** | constant `w` = the filter's mean held-out exposure | matches capital deployed rather than risk |
| **N4 — circular-shift timing null** | the filter's **own** exposure path, circularly rotated by every possible offset (all ≈9,200 rotations, exact, not sampled), applied to the unshifted market | **the sharpest instrument available.** N4 holds the dose, the run-length structure and the turnover *exactly* constant and destroys only the alignment with the market. If the filter's drawdown reduction is about *timing*, it beats its own rotations. If it is about *dose*, it sits in the middle of them. |

N4 is the exposure-path permutation that `scripts/trading_bot/stats.py` already implements for
return series, adapted to a drawdown statistic. A circular rotation is used rather than a shuffle
because a shuffle destroys the run lengths, and a filter that is out of the market for 40 consecutive
days is not the same object as one that is out on 40 scattered days.

---

## 6. Gates — frozen, in order, with the verdict logic

Let `F` be the frozen filter and `N1` the ex-post vol-matched buy-and-hold, both on the held-out
window, both after costs.

| # | gate | threshold, frozen now |
|---|---|---|
| **G1** | **maxDD(F) < maxDD(N1)** by at least **3.0 percentage points**, *and* the stationary-block-bootstrap p-value for `maxDD(N1) − maxDD(F) > 0` is **< 0.05** (10,000 resamples, mean block 63 trading days, paired: the same resample index drives both legs) | the critical null |
| **G2** | **CAGR(F) ≥ CAGR(N1) − 0.50 %/yr** | the drawdown gain must not be bought back in return *at matched risk* |
| **G3** | **N4 percentile**: maxDD(F) below the **5th percentile** of its own ≈9,200 circular rotations | is it timing, or is it dose? |
| **G4** | G1 and G2 still hold at **4× the modelled round-trip cost** | friction robustness |
| **G5** | *declared and expected to FAIL*: DSR of the paired excess return F − N1, at **14 trials**, ≥ 0.95 | so that no return claim can be made later on this data. FINDINGS §5b already killed this family's return claim on BTC (DSR 0.224–0.341) |

### Verdict logic, frozen

- **G1 ∧ G2 ∧ G3 pass** → risk-shaping adds real out-of-sample risk-adjusted value **beyond holding
  less**. Status: ALIVE as *insurance*, never as alpha (G5 governs that and is expected to fail).
- **G1 fails** → **DEAD**. The filter does not beat holding less of the same index. This is to be
  reported plainly and without softening, as the headline result.
- **G1 passes, G3 fails** → the reduction is a **dose effect wearing a timing costume**. Report as
  DEAD for the timing claim, and report the dose effect as what it is: a constant weight anyone can
  hold without a rule.
- **G1 ∧ G3 pass, G2 fails** → CONDITIONAL: report the exchange rate in CAGR per point of drawdown
  and hand the scope call to the owner, who is the one who prices that trade-off.

**No gate is scored on beating the market on return.** The index will out-return every de-risked
variant over a 36-year bull sample and that fact carries no information about risk shaping.

---

## 7. Walk-forward — because one split is not evidence

Beyond the single freeze, an **expanding-window** walk-forward over the held-out window: at each
calendar year-end from 1989 onward, re-select N by §4's rule using **all data up to that point**, and
apply it for the following calendar year. The result is **one continuous equity curve** in which only
N changes at the boundaries.

> The compounding trap is named in advance because this programme has already hit it:
> `scripts/btc_crash_filter_replicate.py` records a walk-forward that computed each fold as its own
> curve starting at 1.0 and multiplied the folds, **skipping the return across every fold join** —
> 21 lost daily returns and a 5 % inflation of buy-and-hold. The audit is that buy-and-hold compounded
> fold-by-fold must equal buy-and-hold computed directly over the same span, and the runner asserts it.

The walk-forward curve is scored against a walk-forward N1 (vol-matched over the same span) on G1 and
G2. **A pass on the single freeze and a fail on the walk-forward is a fail.**

---

## 8. Costs, charged per side

Via `scripts/trading_bot/costs.py`'s per-side decomposition (`split_turnover`), because a change of
exposure from 1.0 to 0.0 is an exit and from 0.0 to 1.0 is an entry and the two are priced separately.

| component | charge | source |
|---|---|---|
| half-spread + slippage, each side | **2.5 bp** per side (5.0 bp round trip) | `retail_taker_costs()`, Dyhrberg/Shkilko/Werner JFE 168 (2025) |
| SEC §31 transaction fee | **0.278 bp** on the **sell** side only | the rate T10 measured as 0.556 bp per double-sided session |
| margin, when w > 1 | cash rate **+ 150 bp**, on `(w−1)` notional, **calendar**-day accrual | broker call-rate spread; calendar because interest accrues over weekends |
| stress ladder | ×1, ×2, ×4 on the spread term | G4 |

**This is deliberately expensive for SPY.** T3 measured SPY's own quoted half-spread at **0.116 bp**
— retail_taker's 2.5 bp is 21× that. The conservative number is charged and the measured one is
reported beside it, so nobody can claim the verdict turned on an optimistic fill.

---

## 9. Metrics reported for every strategy and every null

CAGR · annualised volatility · Sharpe over the **cash** leg (not over zero) · **maxDD** · **Ulcer
index** · **UPI** · **MAR = CAGR/maxDD** · worst rolling 12-month return · time in market · round
trips per year · total turnover · and a **crash-by-crash table**: every peak-to-trough episode in
which buy-and-hold fell more than 20 %, with the filter's loss over the identical dates.

The crash table is the honest unit. Full-sample maxDD is one number from one path; 8 crashes is 8
observations, and *how many it helped, how many it hurt, and by how much* is the claim that either
replicates or does not.

---

## 10. What a pass would and would not license

A pass licenses exactly one sentence: *on a position in a broad index that the owner has already
decided to hold, this rule has historically reduced the depth of drawdowns by more than an equivalent
reduction in position size would have.* It licenses **no** return claim (G5 exists to make that
impossible), **no** claim about individual equities, and **no** live order — execution remains
owner-gated per PLAN.md and `paper.py`'s `submit()` still refuses.

A fail is reported as a fail, in the headline, with the number that killed it.

---

*Freeze: this document is hashed into `T13_FROZEN_CONFIG.json` before `scripts/t13_risk_shaping.py
heldout` is permitted to run. The runner recomputes the hash and refuses on a mismatch.*
