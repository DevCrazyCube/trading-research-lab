# T10 — overnight-vs-intraday premium harvesting: the held-out result

## VERDICT: **DEAD — UNDERPOWERED**, by the kill conditions frozen before anything was fitted

| pre-registered kill condition | held-out value | outcome |
|---|---|---|
| 1. net mean per session ≤ 0 | **+1.482 bp/session**, t = **+0.47** | passes, meaninglessly |
| 2. label-permutation p ≥ 0.05 | **p = 0.0020** | passes — **and §5 shows the instrument is wrong for this object** |
| 3. DSR < 0.95 at `trials = 8` | **DSR = 0.3772** | **FAILS → DEAD** |
| power label (declared in advance, cannot promote a failure) | MDE **1.304** annualised Sharpe vs benchmarks 0.903 / 0.382 | **UNDERPOWERED** |

The observed per-observation Sharpe is **0.01405** against an expected-max under the null of
**0.02342** at only eight declared trials. **The result is below the chance ceiling** — the same
shape as the trailing stop (DSR 0.176) and the crash filter (DSR 0.224) in `FINDINGS.md` §5d.

**And the number that matters more than the verdict.** The strategy trades **4.00 of gross
notional per session and sells 2.00 of it** — measured, not assumed, and the runner asserts it.
Its whole gross edge is **+4.29 %/yr**. It therefore survives only while every auction leg costs
under **0.370 bp**, which is **0.26 × the measured quoted half-spread of its own universe**. At
half a half-spread per leg it is **−4.68 %/yr**; at one half-spread, **−11.19 %/yr**.

> **M0's live half — that *our broker's* on-close order joins the cross — is unmeasured, and this
> candidate lives entirely inside it.** T7 needed that assumption to be worth 0.37 bp/event.
> T10 needs it to be worth **1,414 bp/yr**. It is now the single largest unpriced assumption in
> the programme and the pre-registration said so, in advance, in §7.

---

## 0. Provenance

| artifact | value |
|---|---|
| pre-registration | `research/trading_bot/T10_PREREGISTRATION.md`, sha256 `7f66195125718298c5eb545ae936e9bac89ca537482009b2e8e531a75bbb6d99`, frozen **2026-08-17T09:11:58Z** |
| frozen configuration | `research/trading_bot/T10_FROZEN_CONFIG.json`, sha256 `bc5531956560bab380b0518e2bbd4458bba6770e38e6d49dc7799b3eb3a84545`, written **2026-08-17T09:21:39Z** |
| held-out result | `research/trading_bot/T10_HELDOUT_RESULT.json` |
| exploratory diagnostics | `research/trading_bot/T10_DIAGNOSTICS.json` (**not** pre-registered; no verdict follows) |
| declared-deviation diagnostic | `research/trading_bot/T10_LOOKAHEAD_DIAGNOSTIC.json` — §4b, the signal-timing defect and its cost |
| code | `scripts/t10_overnight_intraday.py`, `scripts/t10_diagnostics.py` |
| statistics | `scripts/trading_bot/stats.py` — imported, never reimplemented |
| costs | `scripts/trading_bot/costs.py`, the **T6-corrected per-side** model, **including `measured_auction_leg` — the M0 leg** |
| data | the T3 auction cache: 3,618,237 official prints, 1,648 symbols, 2016-01-04 → 2026-08-14 |

The pre-registration was hashed **before any price was divided by any other price** for this
candidate; §11 of it lists the only things read first, all counts. The design phase then ran on
2016-02 → 2021-12 alone and wrote the frozen configuration; `t10_overnight_intraday.py test`
**refuses to run** if that file is absent or was written under a different pre-registration
hash, so it cannot choose a configuration on the spot. The held-out period was evaluated **once**.

**The disclosure the pre-registration opens with, repeated here.** `B22F` already reported SPY's
overnight/intraday split **year by year through 2026** before this task began, so configuration
**A1 was never blind**. §0 of the pre-registration says so, states what it showed me, and §9
recorded the prediction in advance. The four **Family B** configurations were genuinely blind:
no cross-sectional overnight/intraday quantity had ever been computed anywhere in this
programme, and the frozen configuration is one of them.

---

## 1. The panel

| quantity | value |
|---|---|
| official auction prints available | 3,618,237 symbol-days |
| sessions kept | **2,608** — 1,468 design, **1,140 held out** |
| symbol-days kept | **1,242,102** — 705,838 design, 536,264 held out |
| sessions dropped, early close on t or t−1 | 42 |
| symbol-days dropped, a corporate action on t or t−1 | **57,253** (4.4 %, identically in both periods) |
| symbol-days dropped, a missing official print | 4,645 |
| median names per session | 485 design, 475 held out |

**The rig check, run before the held-out period was touched** (pre-registration §10). The
equal-weight top-500 basket's full-day return minus SPY's, over the 1,403 design sessions where
both exist: **−0.823 bp/day = −2.05 %/yr**. The known equal-weight-versus-cap-weight gap of
2016–2021 is ≈ −3 to −4 %/yr (RSP vs SPY) and T7 independently measured −1.36 bp/day on its own
event-day subsample. Right sign, right order of magnitude, on a rig built for something else.
It is not a perfect match and it is reported as it came out: our basket is top-500-by-ADV, not
the S&P 500, and it excludes every corporate-action day.

---

## 2. Design phase — 2016-02-01 → 2021-12-31, all eight declared trials

All eight positive. That is the T3 shape, not the T7 shape, and it is exactly why the deflation
exists.

| trial | family | configuration | n | gross bp | cost bp | **net bp** | t | **ann. Sharpe** | ann. return |
|---|---|---|---|---|---|---|---|---|---|
| A1 | A | SPY | 1,403 | +1.226 | 0.587 | +0.639 | +0.23 | +0.095 | +0.22 % |
| A2 | A | EW top-100 | 1,468 | +6.110 | 0.660 | +5.450 | +1.83 | +0.751 | +12.63 % |
| A3 | A | EW top-300 | 1,468 | +5.166 | 0.674 | +4.492 | +1.53 | +0.627 | +10.03 % |
| A4 | A | EW top-500 | 1,468 | +4.651 | 0.689 | +3.963 | +1.35 | +0.556 | +8.61 % |
| B1 | B | K=21, cut 0.10 | 1,455 | +3.690 | 0.796 | +2.894 | +1.45 | +0.598 | +6.67 % |
| B2 | B | K=21, cut 0.20 | 1,455 | +2.719 | 0.774 | +1.945 | +1.33 | +0.551 | +4.54 % |
| **B3** | **B** | **K=63, cut 0.10** | **1,430** | **+4.869** | **0.797** | **+4.072** | **+2.17** | **+0.903** | **+9.94 %** |
| B4 | B | K=63, cut 0.20 | 1,430 | +3.660 | 0.773 | +2.887 | +2.11 | +0.880 | +7.07 % |

Frozen by highest design-window net annualised Sharpe, as pre-registered: **B3 — the
cross-sectional tug-of-war, 63-session lookback, top and bottom deciles, top-500 universe.**
Cross-trial Sharpe variance across the eight: **2.577e-4**, the honest input to the deflation.

**A1 came out where §9 predicted it would.** SPY's paired difference is +1.226 bp/session gross
= **+3.1 %/yr** over the design window, against B22F's +4.27 %/yr for 2016–2026 on adjusted
30-minute bars. Two different instruments, the same number to within the difference between the
periods. Its net annualised Sharpe is **+0.095**. The market-level version of this candidate was
never going to clear anything, and that was written down before it was run.

---

## 3. The held-out period — 2022-01-03 → 2026-08-14, run once

1,140 sessions, one configuration, no refits. 247.26 observations per year, **computed from the
panel** rather than assumed to be 252.

| series | mean bp/session | t | ann. Sharpe | ann. return | max DD |
|---|---|---|---|---|---|
| gross (before every cost) | +2.263 | +0.72 | +0.337 | +4.29 % | −18.3 % |
| **net — M0 auction rail + SEC §31 + TAF + borrow** | **+1.482** | **+0.47** | **+0.221** | **+2.30 %** | **−19.1 %** |

Skew **−1.56**, non-excess kurtosis **17.5** — a fat left tail, which the deflation charges for.

**Design → held-out shrinkage: annualised Sharpe +0.903 → +0.221.** Three-quarters of it was
the design window.

**Year by year, net:** 2022 −2.28 bp (t −0.31) · 2023 +2.21 (t +0.57) · 2024 +5.87 (t +0.95) ·
2025 −0.31 (t −0.04) · 2026 YTD +2.21 (t +0.22). Three positive, two negative, none within reach
of significance.

### The three gates

**Gate 1 — net mean > 0. Passes, and the pass is worth nothing.** +1.482 bp/session at t = +0.47
over 1,140 sessions. `FINDINGS.md`'s opening rule applies: distance from zero, not sample size.

**Gate 2 — permutation p < 0.05. Passes at p = 0.0020, and §5 argues the number should not be
read as the gate intended.** The instrument is a cross-sectional label permutation, T3's, and it
is the one `FINDINGS.md` §5c prescribes for a label object. It is not the right instrument for
*this* object and the diagnostic that shows why is in §5.

**Gate 3 — DSR ≥ 0.95 at the eight declared trials. FAILS at 0.3772.**

| | |
|---|---|
| observed Sharpe, per observation | **0.014045** |
| expected-max Sharpe under the null, 8 trials | **0.023421** |
| cross-trial Sharpe variance (from the eight design trials) | 2.577e-4 |
| z | −0.3129 |
| **DSR** | **0.3772** |
| DSR at 24 trials (declared sensitivity) | **0.2770** |

**The observed Sharpe is below the chance ceiling.** The best of eight worthless strategies would
be expected to look *better* than this one does. There is nothing to deflate away from.

### The power statement — computed on design-window quantities, declared in advance

```
MDE(annualised Sharpe, 80% power, two-sided a=0.05) = 2.80 / sqrt(1140 / 247.26) = 1.304
```

| benchmark | value | reachable? |
|---|---|---|
| design-window net Sharpe of the frozen configuration | **0.903** | no |
| B22F's own SPY split, (10.06 − 5.79) %/yr over this strategy's design volatility | **0.382** | no |
| **MDE at 80 % power on 1,140 held-out sessions** | **1.304** | — |

Per the interpretation rule fixed in the pre-registration: the candidate fails the gates **and**
`MDE > max(benchmarks)`, so the verdict is **`DEAD — UNDERPOWERED`**. That label is a statement
about the instrument, not a rescue: the candidate is dead either way.

---

## 4. Friction — the part that is *not* a power question, and it is decisive

Costs were charged against **exact per-auction turnover**, per name, split into its opening and
closing legs by `costs.split_turnover`, never against an assumed number.

| measured | value |
|---|---|
| gross notional **traded** per session | **3.9989** |
| gross notional **sold** per session | **1.9995** |
| total charged friction at the primary rung | **0.781 bp/session = 193 bp/yr** |

Of which: SEC §31 at 0.278 bp on 2.0 of sale notional = **0.556 bp/session**; FINRA TAF on every
share traded (a deliberate ~2× over-charge, since it is legally sale-side only); the M0
`auction_non_fill_provision` at 0.0019 bp/leg — the dearest of the three liquid M0 tiers; and
borrow at B22G's measured 33 bp/yr on the 0.5 of short notional carried overnight.

### The stress ladder, and where it crosses zero

`h` = T3's first-party measured median quoted half-spread in this exact universe and window,
**1.43 bp** for 2022–2026.

| rung, charged on **every** leg | net bp/session | t | ann. Sharpe | ann. return |
|---|---|---|---|---|
| frictionless (B19P diagnostic — every cost zero) | +2.255 | +0.72 | +0.336 | +4.27 % |
| **primary — M0 auction rail + regulatory + borrow** | **+1.482** | **+0.47** | **+0.221** | **+2.30 %** |
| 0.5 h = 0.715 bp | **−1.377** | −0.44 | −0.205 | **−4.68 %** |
| 1.0 h = 1.430 bp | −4.237 | −1.36 | −0.631 | **−11.19 %** |
| 2.0 h = 2.860 bp | −9.955 | −3.19 | −1.484 | −22.91 % |
| 4.0 h = 5.720 bp | −21.392 | −6.85 | −3.189 | −41.93 % |

**Break-even, solved exactly.** 1.482 bp/session of surviving edge over 4.00 of traded notional:

> **0.370 bp per auction leg — 26 % of the measured quoted half-spread of its own universe.**

At 250 round trips a year the friction slope is **≈ 14 %/yr per basis point of half-spread**,
against a gross edge of 4.29 %/yr. **This is the highest-turnover candidate the programme has
run, by two orders of magnitude, and it is the first one where the auction-rail assumption is
not a refinement but the entire result.**

**T9 inverted the programme's usual finding — friction 11.78 bp against 1,635 bp of per-event
noise, 139× — and concluded that the binding constraint was n, not friction. T10 inverts it
back, and does both at once:** it is underpowered *and* it dies at a quarter of one measured
half-spread. Those are two independent deaths, and neither needs the other.

---

## 4b. A DECLARED DEVIATION found by auditing the code against its own pre-registration — and it ran the *other* way

**The defect.** Pre-registration §5 asserts that *"every input to `s(i,t)` is known before the
closing auction of `t−1`… the signal is one full session stale by construction."* **The
implementation does not satisfy that sentence.** At session `t` the signal's most recent term is
`d(i, t−1) = r_on(i,t−1) − r_id(i,t−1)`, and `r_id(i,t−1)` ends at `C(i,t−1)` — **the very
closing auction print at which the overnight leg is entered**, and which an MOC due at **15:50**
cannot see. One of 63 terms, ~1.6 % of the signal's weight, but it is the exact class of defect
`FINDINGS.md` §5e records T3 catching in its own hand-written diagnostic, and it is reported
here rather than left for someone else to find.

**Quantified, on both windows, with the frozen configuration otherwise untouched**
(`T10_LOOKAHEAD_DIAGNOSTIC.json`, exploratory):

| | design net bp | design ann. Sharpe | **held-out net bp** | held-out t | **held-out DSR (8)** |
|---|---|---|---|---|---|
| as frozen — signal ends at `C(t−1)` | +4.072 | +0.903 | **+1.482** | +0.47 | **0.3772** |
| corrected — signal ends at `C(t−2)` | +5.158 | +1.150 | **+2.972** | +0.97 | **0.5713** |

**The lookahead was *costing* the strategy, not flattering it.** Including the most recent
session's own paired difference adds a short-horizon reversal term that fights the 63-session
sort. Removing it roughly doubles the held-out net return.

**And the verdict is unchanged, which is the point of having frozen it.** The corrected variant
is **not** the frozen configuration; it is a ninth trial, run after the fact, on data that is now
burned. Its DSR is **0.5713 against the 0.95 gate** — and honestly deflated at `trials = 9` it is
lower still. It fails gate 3 by a wide margin, its t is **+0.97**, and the §3 power statement
applies to it identically: **MDE 1.304 against an annualised Sharpe of 0.454.** The friction
arithmetic of §4 also barely moves — at 0.5 h the corrected variant is still negative.

> **The rule this earns:** *audit the implementation against the pre-registration's own timing
> sentence, not only against the strategy's intent.* T3 found a nine-minute lookahead worth more
> than half its result; T10 found a ten-minute one worth **minus** half of its result. Both were
> found by re-reading a claim about *when* information exists, and in neither case did the
> direction of the error match the intuition that "lookahead flatters."

## 5. The method finding: a cross-sectional label permutation is the WRONG instrument for a factor-loaded return series

**This is the part worth carrying forward, and it was found by checking rather than by
intending.** Gate 2 returned **p = 0.0020** on a series whose own t-statistic is **+0.72 gross /
+0.47 net**. Both cannot be describing the same quantity.

`T10_DIAGNOSTICS.json`, exploratory:

| quantity, held-out, 1,140 sessions | value |
|---|---|
| per-session SD of the **real** decile book | **105.49 bp** |
| per-session SD of a **random partition** of the same names, same day, same block sizes | **27.20 bp** |
| **ratio** | **3.88×** |
| standard error of the mean, real book | **3.124 bp** |
| standard error of the mean, permutation null | **0.806 bp** |
| market beta of the long-short book | **−0.036** |
| residual annualised Sharpe after removing the market | 0.374 (vs 0.337 gross) |

**The signal-sorted deciles carry roughly four times the common-factor dispersion of a random
partition of the same cross-section, and it is not market beta.** Sorting on 63 sessions of past
overnight-minus-intraday return is, empirically, also sorting on *something* — the residual
Sharpe barely moves when the market is projected out, so the factor is idiosyncratic-volatility
or size-like, not the index.

**Why that breaks the gate.** The label permutation tests the *sharp* null that no name's rank
carries information. Under that null the observed partition is exchangeable with a random one,
so the test is formally valid. But the tradeable series' standard error is **3.9× the null's**,
so a p-value of 0.002 corresponds to a distance from zero that the strategy's own sampling
distribution puts at **t ≈ 0.7**. The permutation is detecting *that the sort is not random* —
which is true, and is a statement about risk exposure — and it is being read as *that the mean is
positive*, which the data does not support.

> **Rule earned here, extending `FINDINGS.md` §5c:** a cross-sectional label permutation is the
> right instrument for a **classifier**. For a **return series produced by a sort**, it answers
> "is this partition special?" and not "is the mean positive?", and the two diverge by exactly
> the factor loading the sort picks up. **Report the ratio of the real book's dispersion to the
> permutation null's alongside any permutation p-value on a sorted portfolio.** If it is far from
> 1, the p-value is not a statement about the mean.

**This does not overturn T3.** T3's permutation returned p = 0.0001 with a held-out t of **+2.73**
on its own series — the two agreed there, and T3 died on DSR regardless. But the same ratio should
be reported for T3 if that result is ever revisited, and it is cheap.

---

## 6. What replicated, and it is not the trade

The pre-registration declared these as diagnostics, not trials. They are the cleanest thing to
come out of T10, and they are measured on **official auction prints over the held-out window**,
which is a different instrument and a different period from B22F's adjusted 30-minute bars.

| held-out 2022-01 → 2026-08 | ann. return | ann. Sharpe |
|---|---|---|
| **SPY, overnight session** (prev close print → open print) | **+7.29 %** | **+0.724** |
| **SPY, intraday session** (open print → close print) | **+3.15 %** | **+0.284** |
| EW top-500, overnight session | +7.15 % | +0.670 |
| EW top-500, intraday session | +2.38 % | +0.228 |

**Lou, Polk & Skouras's qualitative claim survives an honest out-of-sample test on our own
instrument: the overnight session is about 2.5× as risk-efficient as the intraday session.**
B22F measured 0.87 vs 0.43 on 2016–2026 adjusted bars; T10 measures 0.72 vs 0.28 on 2022–2026
auction prints. Different data, different window, same asymmetry, same factor.

**And it is still not a trade, for the reason B22F and `EDGE_SHORTLIST.md` both already said.**
Harvesting the *difference* requires flipping the book twice a day; that costs 193 bp/yr of
unavoidable regulatory friction before any spread, and the difference itself is only ~4.3 %/yr on
~17 %/yr of volatility. **The asymmetry is real, and the arbitrage of it is not.** What the
asymmetry supports is a *risk-shaping* statement — see §8.

---

## 7. What this result does not claim

- It does not claim the effect is absent. It claims this instrument **could not have detected it**
  at any size the literature or our own measurements suggest (§3), **and** that it dies at a
  quarter of one measured half-spread (§4). The first is a limit of the test; the second is not.
- It does not claim MOC/MOO orders from our broker join the cross. That is M0's **C4**, still
  unperformed, and T10 depends on it more heavily than any candidate so far.
- It does not model Reg SHO locates for ~50 short sales every morning, Rule 201 short-sale price
  tests, queue position, partial fills, or size-dependent impact.
- It does not model taxes. ~250 round trips a year realises essentially everything as short-term
  gains; T7 §6's loss-usability arithmetic applies with far more force here.
- The 4.4 % of symbol-days removed for corporate actions is an exclusion, not an adjustment. §4 of
  the pre-registration argues the residual is ≈ 0.25 bp — smaller than anything this test
  resolves — and that argument is stated rather than verified.

---

## 8. Where this leaves the programme, and what I recommend

### 8a. The scoreboard, and the pattern in it

| candidate | how it died |
|---|---|
| #1 T3 end-of-day reversal | real signal (+5.35 bp/night, t +2.73, p 0.0001), **DSR 0.9379** — missed by 0.012 |
| #2 T7 ex-dividend drop-off | **no signal** (p 0.213, DSR 0.076); all eight design trials negative |
| #4 T9 spin-off drift | **no power** (62 events, MDE 5.51 % vs a 2.40 % effect) |
| **#6 T10 overnight/intraday** | **no power** (MDE Sharpe 1.30 vs an effect of ≤ 0.38) **and** dead at 0.26 × a half-spread |

**The constraint that binds is not signal and it is not friction. It is the resolution of the
test itself,** and T10 makes it quantitative for the first time:

```
years of held-out DAILY data needed to certify a true annualised Sharpe, at 80% power:
    Sharpe 1.3 ->  4.6 yr      Sharpe 0.8 -> 12.2 yr
    Sharpe 1.0 ->  7.8 yr      Sharpe 0.5 -> 31.4 yr      Sharpe 0.3 -> 87.1 yr
```

We hold **4.6 years** of held-out daily data and 10.6 years in total. **Every remaining
directional candidate on `EDGE_SHORTLIST.md` has a literature effect size below Sharpe 0.5.**
Turn-of-month (#3) is worse still — ~60 held-out month-ends, which T9 already made quantitative.
CEF discount reversion (#5) has the n but has no auction rail and quotes at 4–36 bp. Merger arb
(#7) is blocked on announcement dates we do not hold.

**The directional well is dry — not because the effects are absent, but because our instrument
cannot certify anything in the size range they occupy.** Running a fifth directional candidate
buys another honest negative and no information we do not already have.

### 8b. Recommendation: the risk/sizing pivot — and it is an owner call, not mine

**Recommended: pivot to risk and sizing.** The argument is not defeatism, it is the resolution
arithmetic above plus one observation about what has actually survived this programme:

> **Both survivors in `FINDINGS.md` are distribution-shape claims, not mean claims** — the crash
> filter's ~15pp drawdown reduction (which DSR does not bear on, and which held across two data
> sources and two implementations) and the deadness screen (a classifier, permutation p = 0.000,
> replicated on a different corpus). **Neither needed a certifiable Sharpe, which is exactly why
> both are still standing while four directional candidates are not.**

A drawdown reduction of 15pp is measurable on 1,140 sessions. A Sharpe of 0.3 is not. **The pivot
is to the class of question this data can actually answer.**

Two concrete first moves, in order:

1. **M0's C4 — the live half.** Bounded, days not years, no strategy implementation, and both
   outcomes are worth having. **Four dead candidates now rest on it**, and T10 has just made it
   quantitative: the break-even is **0.370 bp per auction leg**. Any future candidate that uses
   the rail inherits this. `M0_AUCTION_FILLS.md` §10 already contains the protocol; it needs live
   paper sessions and nothing else.
2. **The risk/sizing work proper**, framed as distribution-shape questions with pre-registered
   thresholds: drawdown control, position sizing against the measured cost curve, and the
   overnight-session exposure of §6 evaluated **as risk shaping rather than as alpha** — it
   captures ~69 % of SPY's return on ~58 % of its volatility, which is a real fact and a
   defensible *allocation* question, and it is emphatically **not** free: 250 round trips a year
   on the rail costs ~70 bp/yr even with only two legs a day, and levering back to full-day
   volatility pays margin interest that would consume the difference. That arithmetic is the
   first thing to settle.

**The alternatives, stated so the owner is choosing rather than ratifying:**
- **#5 CEF discount mean reversion** — the last large-n directional candidate. Its problem is
  friction, which this programme prices well; but it has **no auction rail** (T1 §2e: CEF closing
  auctions clear $0–0.3 M) and only ~1 year of daily NAV history. A power census first would cost
  an hour and would probably kill it the way T9's did.
- **Pre-register T7's close-to-open variant as a prospective forward test** — it was +3.72 bp/day
  held out but 2022–2026 is burned for it, so it needs forward collection, not another backtest.

Per the standing instruction, this is a **scope call for the owner** and I am not taking it
autonomously. My recommendation is **(1) then (2)**.
