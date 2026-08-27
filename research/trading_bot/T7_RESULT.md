# T7 — ex-dividend drop-off, close-to-close in the auctions: the held-out result

## VERDICT: **DEAD** — by two of the three kill conditions frozen before any data was fitted.

| pre-registered kill condition | held-out value | outcome |
|---|---|---|
| 1. net mean per event-day ≤ 0 | **+0.84 bp/day**, t = **+0.46** | passes, barely and meaninglessly |
| 2. label-permutation p ≥ 0.05 | **p = 0.213** | **FAILS** |
| 3. DSR < 0.95 at trials = 8 | **DSR = 0.076** | **FAILS** |

It was already dead in the design window: **all eight declared configurations had a negative net
Sharpe on 2016–2021**, the best of them at −0.11. The held-out period turned slightly positive and
that is noise, which is exactly what the two failing gates say.

**And it would be dead after tax even if it had passed.** A taxable US retail account running this
at $100 k would book **67.7 % of equity per year in non-qualified ordinary dividend income** against
**65.9 % in short-term capital losses it has no gains to absorb**, to earn a pre-tax **1.86 %**. §6
does that arithmetic properly, including the part the shortlist's framing got wrong.

---

## 0. Provenance

| artifact | value |
|---|---|
| pre-registration | `research/trading_bot/T7_PREREGISTRATION.md`, sha256 `7bd072a7565a27b39d83a35afa659fb4c80bdf700dcb84e1100ea0e1816c7cdd`, frozen 2026-08-16T23:52:35Z |
| frozen configuration | `research/trading_bot/T7_FROZEN_CONFIG.json`, sha256 `2f25e00c64e02b6efd5a36e1c903a8a05bb4c1848ae10707a2a8540172aa3b2c` |
| held-out result | `research/trading_bot/T7_HELDOUT_RESULT.json` |
| exploratory diagnostics | `research/trading_bot/T7_DIAGNOSTICS.json` (**not** pre-registered; no verdict follows) |
| collection + evaluation code | `scripts/t7_dividend_dropoff.py`, `scripts/t7_evaluate.py`, `scripts/t7_diagnostics.py` |

The pre-registration was written and hashed **before any return, signal, portfolio or drop-off
ratio was computed**; §10 of it lists the only three things read first, all structural. The design
phase then ran on 2016–2021 alone and wrote the frozen configuration file; `t7_evaluate.py test`
**refuses to run** if that file is absent, so it cannot choose a configuration on the spot. The
held-out period was evaluated once, after the freeze.

Statistics come from the T2 harness (`scripts/trading_bot/stats.py`) — `deflated_sharpe`,
`sharpe_variance_from_trials`, `permutation_test`, `moments`, `annualised_sharpe`, `max_drawdown`,
`cagr` — imported, not reimplemented. Costs come from `scripts/trading_bot/costs.py`, the
**T6-corrected per-side** model (§4).

---

## 1. The data actually assembled

| quantity | value |
|---|---|
| cash dividends pulled, universe-wide, 2016-01 → 2026-08 | **385,845** |
| …in the tradeable point-in-time top-500-ADV universe | **14,187** |
| dropped as not in that universe | 310,633 |
| official auction prints reused from the T3 cache | 3,618,237 symbol-days, 1,648 symbols |
| **event-days in the panel** | **2,321** (1,302 design + 1,019 held-out) |
| median events per day, held-out | 6.1 |

Exclusions applied identically in both periods: 207 days with no surviving event, 79 days on which
**SPY itself** went ex-dividend (a short SPY hedge held across its own ex-date owes that dividend),
43 ex-dates that were not trading days, 42 early closes, 23 events missing an auction print, 6
events with another corporate action on the cum-day or ex-date, 4 events whose dividend exceeded
20 % of the price, 2 days missing a SPY auction print.

**A sanity check that was run before the held-out period was touched.** The equal-weight
non-ex-dividend universe underperformed SPY by **−1.36 bp/day** on design-period event-days. That
is −3.0 %/yr, and it is the well-known equal-weight-versus-cap-weight gap of 2016–2021 (RSP vs SPY
was about −3.5 %/yr over the same span). The wiring reproduces a number it was not built to
reproduce, which is the only kind of check worth running on a rig before trusting it.

The identity `excess return = yield × (1 − drop-off ratio)` was also verified to reconcile exactly
against the independently-computed event mean (0.1064 bp both ways, design period). No arithmetic
bug stands behind the negative result.

---

## 2. Design phase — 2016-01-04 → 2021-12-31, all eight declared trials

**Every one of the eight was negative.** That is the mirror image of T3, where every one of eight
was positive and the deflation existed for exactly that reason.

| yield filter | universe | specials | gross bp/day | net bp/day | t | ann. Sharpe | drop-off ratio |
|---|---|---|---|---|---|---|---|
| **all** | **top 500** | **in** | **+0.019** | **−0.358** | **−0.27** | **−0.11** | **0.9748** |
| all | top 500 | out | +0.006 | −0.371 | −0.28 | −0.11 | 0.9772 |
| all | top 300 | in | −3.480 | −3.851 | −2.48 | −1.07 | 1.0153 |
| all | top 300 | out | −3.453 | −3.824 | −2.46 | −1.06 | 1.0194 |
| ≥ 0.5 % | top 500 | in | −1.098 | −1.478 | −0.82 | −0.37 | 0.9764 |
| ≥ 0.5 % | top 500 | out | −1.265 | −1.644 | −0.92 | −0.41 | 0.9791 |
| ≥ 0.5 % | top 300 | in | −6.596 | −6.970 | −3.16 | −1.54 | 1.0443 |
| ≥ 0.5 % | top 300 | out | −6.666 | −7.040 | −3.19 | −1.56 | 1.0507 |

Frozen by highest design-period net Sharpe, as pre-registered: **all dividends, top 500, specials
included.** Cross-trial Sharpe variance across the eight: `1.657e-3` — the honest input to the
deflation.

Note the direction of the yield axis. The tax-clientele mechanism predicts a **larger** residual in
higher-yield names. In the design data the ≥ 0.5 % filter makes every configuration **worse**. The
mechanism's own comparative static points the wrong way here, before any out-of-sample test.

---

## 3. The held-out period — 2022-01-03 → 2026-08-14, run once

1,019 event-days, 6,245 events, one configuration, no refits.

| series | mean bp/day | t | ann. Sharpe | ann. return | max DD |
|---|---|---|---|---|---|
| **net, auction rail + regulatory + borrow** | **+0.84** | **+0.46** | **+0.21** | +1.86 % | −20.5 % |
| gross (zero cost — the B19P diagnostic) | +1.21 | +0.66 | +0.31 | +2.67 % | −19.3 % |
| equal-weight **non**-ex-dividend control, same days | −1.41 | −1.11 | −0.52 | −3.11 % | −16.1 % |

Skew −0.83, non-excess kurtosis **9.40** — a fat-tailed daily series, which the deflation charges
for. Annualisation uses **221 observations per year, computed from the panel**, not 252: the book
holds nothing on a trading day with no ex-dividend date, and claiming 252 compounding opportunities
for a strategy that has 221 would flatter it.

**Year by year, net:** 2022 +3.18 bp (t 0.87) · 2023 +5.70 (t 1.73) · 2024 −2.57 (t −0.70) ·
2025 −5.19 (t −1.33) · 2026 YTD +4.48 (t 0.63). Two positive, two negative, none significant.

### The three gates

**Gate 1 — net mean > 0. Passes, and the pass is worth nothing.** +0.84 bp/day at t = 0.46 over
1,019 non-overlapping event-days. A t of 0.46 is a coin landing slightly heads.

**Gate 2 — label permutation. FAILS: p = 0.213.** 10,000 permutations in which each day's `k` real
ex-dividend names are replaced by `k` names drawn from that same day's *non*-ex-dividend universe
members, holding the days, the cross-section size and the market move fixed. Observed +1.21 bp/day;
null mean −0.73 bp, null sd **2.43 bp**, null 95th percentile +3.24 bp. The observed value sits
0.8 standard deviations into a null that is six times wider than the effect.

This is the number that explains the whole result. A six-name basket's one-day idiosyncratic noise
is ±2.4 bp/day at the portfolio level. **The drop-off residual being sought is ~2.9 bp per event.**
The signal and the noise are the same size, one event at a time, and there are only 1,019 days.

**Gate 3 — Deflated Sharpe. FAILS badly. DSR = 0.076 against the pre-registered 0.95.**

| input | value |
|---|---|
| observed Sharpe (per event-day) | 0.01428 |
| expected-max Sharpe under the null, 8 trials | **0.05940** |
| z | −1.431 |
| **DSR** | **0.0762** |
| sensitivity at 24 trials | 0.0177 |

The observed Sharpe is **below the chance ceiling** — a quarter of it. This is the same shape as
`FINDINGS.md` §5's +0.48 % dying at DSR 0.176, not the near-miss shape of T3's 0.9379.

### The wiring check, reported so it is not mistaken for evidence

`stats.permutation_test` on the exposure path returns **p = 1.0** with `degenerate_exposure: true`.
Correct and expected: this book is fully invested and dollar-neutral on every observation day, so
its exposure is constant and permutes to itself. The instrument that bears on the claim is the
cross-sectional label permutation above (`FINDINGS.md` §5c).

---

## 4. What the drop-off ratio actually is, measured

The literature's own quantity, `(market-adjusted price fall) / dividend`. This is the part of the
candidate that is **not** dead: the mechanism is visible, it is just too small to trade.

| | design 2016–2021 | held-out 2022–2026 |
|---|---|---|
| dollar-weighted drop-off ratio | **0.9748** | **0.9524** |
| day-clustered point estimate | 0.9994 | 0.9606 |
| **95 % CI on the day-clustered estimate** | **[0.916, 1.083]** | **[0.843, 1.079]** |
| mean dividend yield per event | 0.627 % | 0.613 % |

**The point estimate is below 1 in both periods, and in neither is it distinguishable from 1.**
Elton & Gruber's 0.78 is outside both intervals on the low side; a ratio of exactly 1 is inside
both. The honest statement is that on liquid US large caps in 2016–2026 the price falls by
essentially the full dividend, and any residual is smaller than we can measure with 2,321
event-days.

The yield buckets (exploratory, `T7_DIAGNOSTICS.json`) do not replicate at all — the `< 0.25 %`
bucket reads 0.835 in design and **1.594** held-out. A quantity that moves that far between halves
of the sample is measuring noise, and the buckets are reported only to say so.

---

## 5. The cost model, and the stress ladder

The T6-corrected **per-side** model, with both sides named explicitly and neither inheriting the
other. New provenance added to `costs.py` for this: `EXCHANGE_MECHANISM_UNVERIFIED_FILL`, whose own
docstring requires that any component carrying it be accompanied by a stress rung charging a real
half-spread on the same leg.

| component | charged | why |
|---|---|---|
| entry half-spread | **0 bp** | cum-day **closing auction**: single-price call, no bid-ask to cross |
| exit half-spread | **0 bp** | ex-date **closing auction**, same mechanism, **declared not inherited** |
| entry/exit extra slippage | 0 bp | stated lower bound, swept by the ladder |
| SEC §31 | **0.278 bp** of sale notional, both sale legs, both periods | charged at $27.80/$1 M, the **top** of the 2016–2026 range |
| FINRA TAF | $0.000166/share, **every** share | legally sale-side only; the field is side-agnostic, so this over-charges ~2× — the conservative direction |
| borrow | 33 bp/yr on the 50 % SPY short | B22G's **measured** ETB general-collateral median, not the 30 bp default |

Total charged at the primary rung: **0.37 bp per event-day**. The auction removes the spread; it
does not remove the regulator.

| rung | mean bp/day | t | ann. Sharpe |
|---|---|---|---|
| zero cost (B19P diagnostic) | +1.21 | +0.66 | +0.31 |
| **PRIMARY: auction rail + SEC31 + TAF + borrow** | **+0.84** | **+0.46** | **+0.21** |
| 0.5h per leg | −0.59 | −0.32 | −0.15 |
| **h per leg — M0 wrong, MOC fills at the touch** | **−2.02** | **−1.10** | **−0.51** |
| 2h per leg | −4.88 | −2.65 | −1.23 |
| 4h per leg | −10.60 | −5.75 | −2.68 |

`h` = **1.43 bp**, T3's own first-party measured median quoted half-spread in this exact universe.

**Read the third row.** Charging *half* the measured half-spread on each of the four legs already
turns the strategy negative. This candidate was ranked above three others precisely because both
its legs are auction prints; the ladder says that if **M0** — *does an MOC order actually fill at
the official closing print?* — comes back even half-wrong, there is nothing left. M0 is still
unperformed, and this is now the **second** consecutive candidate whose result rests on it.

---

## 6. THE TAX ARITHMETIC — owner-facing, and the shortlist framed it wrongly

`EDGE_SHORTLIST.md` §5.2 says: *"a taxable US retail account receives the dividend as ordinary
income; the pre-tax edge must exceed the tax differential."* **That framing implies a rate
differential between ordinary income and capital gains, and for a one-day dividend capture there
is no such differential.** The offsetting price fall is a **short-term** capital loss, and
short-term capital gains and losses are taxed at the *same* ordinary rates. The real problem is not
a rate gap. It is **usability**, and it is much worse than a rate gap.

**The two facts that set it up.**

1. A one-day hold can never satisfy the **61-days-in-a-121-day-window** qualified-dividend holding
   period (IRC §1(h)(11)(B)(iii)). Every dollar of dividend this strategy collects is **ordinary
   income**, at up to 37 % federal plus 3.8 % NIIT plus state.
2. The offsetting loss is a **capital** loss, and IRC §1211(b) lets an individual deduct capital
   losses only against capital **gains**, plus **$3,000 per year** against ordinary income. The
   excess carries forward, indefinitely, waiting for gains that this strategy does not produce.

**What the strategy actually generates per year, from the held-out numbers** (50 % of equity long
the basket, 221 event-days/yr, 0.613 % mean yield per event):

| flow | % of equity per year | on $100 k |
|---|---|---|
| **ordinary (non-qualified) dividend income** | **+67.7 %** | **+$67,713** |
| **short-term capital loss** | **−65.9 %** | **−$65,856** |
| **pre-tax economic profit** | **+1.86 %** | **+$1,857** |

**Case A — the losses are fully absorbed** by other realised capital gains the account has from
elsewhere. Then there is no differential at all and after-tax return is simply
`pre-tax × (1 − t)`:

| marginal ordinary rate | 24 % | 32 % | 35 % | 37 % | 40.8 % |
|---|---|---|---|---|---|
| after-tax return | +1.41 % | +1.26 % | +1.21 % | +1.17 % | +1.10 % |

**Case B — the losses are not absorbed**, which is the default for a standalone taxable deployment,
because this strategy is a **net capital-loss machine by construction** and produces no gains to
offset:

| marginal ordinary rate | 24 % | 32 % | 35 % | 37 % | 40.8 % |
|---|---|---|---|---|---|
| tax on the dividend alone | 16.3 % | 21.7 % | 23.7 % | 25.1 % | 27.6 % |
| **after-tax return** | **−14.4 %** | **−19.8 %** | **−21.8 %** | **−23.2 %** | **−25.8 %** |
| **drop-off ratio needed to break even** | **< 0.76** | **< 0.68** | **< 0.65** | **< 0.63** | **< 0.59** |

At $100 k the $3,000 annual deduction recovers **4.6 %** of the losses; the rest carries forward
against gains that never come. The $3,000 is a fixed dollar amount, so this gets *relatively* worse
as the account grows.

**The bar, stated as a single number.** In case B the after-tax edge is positive only if
`drop-off ratio < 1 − t`. At a 35 % rate that is **0.65**. The measured ratio is **0.95**, with a
95 % interval of **[0.84, 1.08]**. Even **Elton & Gruber's original 0.78** — the strongest figure
the literature ever reported, from the pre-decimalisation 1960s — would not clear the bar.

### So: does #2 clear the bar after tax? **No, and it does not clear it before tax either.**

- **Taxable account:** unambiguously no. Dead on the statistics (permutation p 0.213, DSR 0.076)
  and then dead again, by a factor of twelve, on tax.
- **Tax-deferred account (IRA/Roth):** the tax objection disappears completely — no ordinary income
  event, no capital-loss usability problem. **The statistical verdict is unchanged and still DEAD.**
  This matters for the *next* candidate, not this one: it says the tax gate is an
  account-type question the owner can dispose of, and it should not be allowed to sink a candidate
  that passes on the statistics.

**This is the owner's call and I have not made it.** The recommendation attached to it is in §9.

---

## 7. One exploratory diagnostic that is genuinely interesting — and is NOT a result

**NOT pre-registered. Deliberately excluded from the trial grid (pre-registration §7). No verdict
follows. Recorded because suppressing it would be worse than the risk of it being over-read.**

**D1 — exit at the ex-date *opening* auction instead of its closing auction.** Both legs are still
genuine auction prints, and the ex-date is known weeks ahead, so an MOO exit is submittable.

| | design 2016–2021 | held-out 2022–2026 |
|---|---|---|
| basket vs SPY, gross | +2.63 bp/day, t 3.48 | **+3.72 bp/day, t 3.29** |
| same-day non-ex-dividend control | +0.70 bp, t 2.66 | +0.08 bp, t 0.22 |
| **basket minus control** | **+1.93 bp, t 2.49** | **+3.63 bp, t 3.18** |
| label permutation, p right tail | 0.083 | **0.042** |

**What it says.** The drop-off residual, to whatever extent it exists, appears **overnight** and is
**given back during the ex-date session**. The frozen close-to-close rule holds straight through
the give-back — it captures +1.21 bp where the overnight-only leg captured +3.72 bp. The control
row is doing real work here: in the design window a third of the raw number was just the
equal-weight universe drifting against SPY overnight, and only the differenced row separates a
dividend effect from an overnight-beta tilt.

**Four reasons this is not a finding, and the third is the one that matters.**

1. It was excluded from the declared grid **in advance**, so it carries no verdict. Promoting it
   now is precisely the search the deflation exists to charge for.
2. It has not been deflated. At 8 declared trials the chance ceiling was 0.0594 per observation;
   this variant's per-observation Sharpe is ≈0.10, so it *might* clear it — that is a reason to
   pre-register it, not a reason to believe it.
3. **I have now looked at 2022–2026 for it.** That period is **burned** for this variant. A new
   pre-registration of the close-to-open rule cannot be tested on any data in this cache and would
   need a **prospective, forward** test. Saying otherwise would be the exact failure `FINDINGS.md`
   §6 records eight times over, every one of them flattering.
4. **The tax arithmetic of §6 is unchanged and just as fatal.** An overnight hold is still under 61
   days, so the dividend is still ordinary income and the loss is still short-term. In a taxable
   account this variant is at best +3.63 bp/day gross against a 23.7 % of equity annual tax bill on
   the dividend stream. It would have to be run in a tax-deferred account or not at all.

---

## 8. Deviations from the pre-registration

**One, and it is additive.** `costs.py` gained a new `SlippageProvenance` member,
`EXCHANGE_MECHANISM_UNVERIFIED_FILL`, because the existing vocabulary had no honest label for "a
single-price auction has no spread to cross, *and* nobody has verified we get filled at the print".
The alternatives were to mislabel the zero as a broker schedule or as a stress rung. The new
member's own definition **requires** an accompanying stress rung, which §5 supplies. No existing
component, model or number changed.

Everything else ran as frozen: the universe screen, the exclusions, the eight trials, the freezing
rule, the single held-out run, the permutation construction, the cost rungs.

---

## 9. What this means, and what to do next

**Stated plainly: the mechanism is visible and the trade is not there.** The price does fall by
slightly less than the dividend — 0.95 of it, both periods, point estimate below 1 both times. That
residual is ~2.9 bp per event against ±2.4 bp of one-day portfolio noise and 0.37 bp of
irreducible regulatory friction, and half of one measured half-spread on each leg wipes it out
entirely.

**Two candidates have now died at the statistical gate rather than the economic one**, and their
deaths were opposite in shape: T3's eight design trials were all positive and it missed DSR by
0.012; T7's eight were all negative and it missed by 0.874. Pre-registration was load-bearing in
both directions.

### Nomination, with a recommendation and a fork for the owner

The shortlist's ranked successor is **#3, turn-of-month forced rebalancing** (score 15). I am
nominating it as the ranked candidate but **recommending against running it next**, for a reason
its own shortlist entry states: ≈127 month-ends in the whole sample and **~60 in the held-out
period**. T7 just died on a permutation whose null was 2.4 bp wide at n = 1,019. At n = 60 the null
would be wider than anything the effect could plausibly be. It is a pre-registered failure waiting
to happen.

**My recommendation is to spend the next slice on M0 instead, and then on #4.**

1. **M0 — do MOC/MOO orders actually fill at the official auction print?** Bounded (a fortnight of
   paper orders), a measurement rather than a search so it carries no multiple-testing charge, and
   **both T3 and T7 now rest on it**. T7's ladder says half a half-spread per leg is the difference
   between +0.84 bp and −0.59 bp. It is the cheapest outstanding thing in the programme and it has
   been outstanding since T1.
2. **#4 — spin-off forced-selling drift** (score 14, and **U = 4**, the highest uniqueness of
   anything above it). The forced flow is mechanical and dated, the horizon is 1–60 days rather
   than one, and **the data is already on disk from this run**: the universe-wide sweep in
   `t7_dividend_dropoff.corporate_actions_all()` pulled **243 spin-offs** along with the dividends.
   Its honest weakness is n in the low hundreds and illiquid stubs, and a pre-registration would
   have to state a power calculation up front — which, after T7, is a thing this programme should
   be doing before it collects rather than after it fails.

**This is a scope call and it is the owner's**, not mine. The three options are: run #3 as ranked;
run M0 then #4 as recommended; or pre-register the close-to-open variant of §7 as a **prospective**
forward test, accepting that it cannot be validated on any data we hold.

---

## 10. What this document does not claim

- **Nothing here authorises execution.** No order of any kind was submitted. The only endpoints
  touched were market-data reads plus the read-only `/v2/assets` and `/v2/calendar`.
- **M0 is still unperformed.** Both auction legs assume a fill at the print. §5's ladder prices
  being wrong about it and says the strategy does not survive being half-wrong.
- **The universe is the tradeable one, not the whole market.** 310,633 of 385,845 cash dividends
  are outside the top-500-ADV screen. The tax-clientele story predicts a larger residual in small,
  high-yield, illiquid names — which this test cannot reach and which the auction rail cannot
  execute in (T1 §2e). This is a stated scope limit, declared in the pre-registration §2, not a
  discovery.
- **Survivorship is reduced, not eliminated.** Alpaca's inactive list is a partial record.
- **The dividend is credited on the ex-date**, not on the payable date weeks later. That flatters
  the strategy by the risk-free carry over the lag — far below the resolution of anything measured
  here, and stated rather than omitted.
- **The tax analysis is arithmetic, not tax advice**, and it deliberately does not model state tax,
  the wash-sale interaction on a repeatedly re-established SPY short (IRC §1091 via §1233), or
  entity structures. Every one of those makes case B worse, not better.
