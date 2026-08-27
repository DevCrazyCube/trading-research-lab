# T13 — RESULT: risk-shaping tested against the only null that matters

**Verdict: DEAD on the frozen gate, both families.** Neither a moving-average crash filter nor a
volatility-targeting overlay beats *simply holding less of the same index* by a margin this
programme can certify on 36.6 years of held-out data.

**And one thing worse than a null result, which is the actual headline:** the crash filter's frozen
configuration ended the held-out window with a **deeper** maximum drawdown than the de-risked
buy-and-hold it is supposed to improve on — **46.7 % against 37.0 %** — *while* protecting more than
the null in every single crash it was designed for. It manufactures its own drawdown out of whipsaw,
in between the crashes, and that drawdown is bigger than the ones it avoids.

| | |
|---|---|
| pre-registration | `T13_PREREGISTRATION.md`, sha256 `0eda5f7aa65b91cc…` |
| frozen config | `T13_FROZEN_CONFIG.json`, sha256 `42ef30e1c30c5407…` |
| design window | ^GSPC, **1929-01-03 → 1989-12-29**, 15,298 bars |
| held out | **1990-01-02 → 2026-08-14**, 9,222 bars, **36.6 years**, 8 crashes |
| instruments | primary ^SP500TR (index total return); confirmatory SPY adjusted (real ETF) |
| declared trials | **14**, counted before the design run |
| frozen by the rule | crash filter **SMA-100**; overlay **L=60, target 10 %, w_max 1.0** |
| lookahead audit | 4 truncation probes, **bit-identical**; negative control **caught** (`T13_DIAGNOSTICS.json`) |
| compounding audit | fold-by-fold vs direct, costs off: **1.4 × 10⁻¹⁴** |

---

## 1. The gates, held out

Every row compares a strategy against **N1** — a constant weight in the *same index*, with the
remainder in T-bills, sized so that its realised volatility over the held-out window **equals the
strategy's**. N1 is fitted with hindsight the strategy never gets. That is deliberate: it is the
strongest possible form of "you could have just held less".

### Family A — crash filter, frozen at SMA-100

| gate | held out | verdict |
|---|---|---|
| **G1** maxDD(F) < maxDD(N1) by ≥3 pp, bootstrap p<0.05 | **−9.65 pp** (46.66 % vs 37.01 %), p = 0.527 | **FAIL, and in the wrong direction** |
| **G2** CAGR(F) ≥ CAGR(N1) − 0.5 %/yr | −1.66 %/yr (6.52 vs 8.18) | FAIL |
| **G3** maxDD below the 5th percentile of its own 9,221 circular rotations | **32.8th percentile** | FAIL |
| **G4** G1∧G2 survive 4× cost | −12.77 pp, −2.65 %/yr | FAIL |
| **G5** DSR of paired excess at 14 trials ≥ 0.95 | **0.0159** | FAIL *(declared in advance as expected)* |

Confirmed on SPY: −9.89 pp, p = 0.514, G3 32.5th percentile. **Verdict: DEAD.**

### Family B — volatility-targeting overlay, frozen at L=60 / 10 % / w_max 1.0

| gate | held out | verdict |
|---|---|---|
| **G1** | **+7.25 pp** (27.63 % vs 34.88 %), **p = 0.233** | **FAIL — on the p-value, not the effect size** |
| **G2** | **+0.66 %/yr** (8.52 vs 7.87) | pass |
| **G3** | **2.24th percentile** of 9,221 rotations | pass |
| **G4** | +7.07 pp and +0.51 %/yr at 4× cost | pass |
| **G5** | DSR **0.3545**; per-obs Sharpe 0.00839 **below** the 0.01228 chance ceiling | FAIL *(as declared)* |

Confirmed on SPY: +7.81 pp, p = 0.237, G3 1.93rd percentile, G2 +0.64 %/yr.

**Frozen verdict logic, applied without softening: G1 fails → DEAD.** The overlay's drawdown
advantage over holding less is **not distinguishable from luck on the evidence we hold**.

### Family C — combined

+4.34 pp (p = 0.354), CAGR −1.10 %/yr, G3 2.43rd percentile. **DEAD.** The filter's return cost
dominates the overlay's drawdown gain.

---

## 2. The crash filter's failure has a shape, and it is not the one anyone expects

The filter **works in crashes.** Against the vol-matched null, per crash:

| crash | N1 loss | filter loss | filter better by |
|---|---|---|---|
| 2000-09-01 → 2002-10-09 | −29.97 % | −19.57 % | **10.40 pp** |
| 2007-10-09 → 2009-03-09 | −37.01 % | −10.56 % | **26.46 pp** |
| 2020-02-19 → 2020-03-23 | −21.80 % | −7.93 % | **13.86 pp** |

Mean **−16.91 pp**, 3 for 3, none harmful. Against plain buy-and-hold the numbers are larger still
(−27.8, −44.7, −25.9, −7.0 pp over four crashes). **On the metric the crypto result was stated in —
"protection in 5 of 7 crashes, zero harmful" — the equity crash filter replicates cleanly.**

And it still ends the window with a deeper maximum drawdown than the null:

| | peak | trough | depth | recovered |
|---|---|---|---|---|
| **filter (SMA-100)** | 1999-07-16 | 2003-04-16 | **46.66 %** | **2010-01-07** |
| N1, vol-matched | 2007-10-09 | 2009-03-09 | 37.01 % | 2011-04-27 |

> **The filter's worst drawdown is not a crash. It is a whipsaw.** Between July 1999 and April 2003
> the SMA-100 rule crossed in and out repeatedly, paying the round trip each time and re-entering
> above where it sold, and the resulting equity hole took **ten and a half years to fill** — against
> three and a half for the null's 2008 hole. Ulcer index **16.35 for the filter against 13.80 for
> undiluted buy-and-hold**: the filter spends more of its life underwater than the thing it de-risks.

**This is the sharpest instrument result in the file, and it generalises past this candidate.**
Crash-by-crash protection and full-path drawdown are *different statistics that can point opposite
ways*, and the crypto crash-filter finding in `FINDINGS` §5b is stated in the first of them.
Measuring only within crashes counts the benefit and not its cost. The cost arrives outside them.

---

## 3. The critical null did its job — and it is not close

The task named the trap in advance: *does the filter beat simply holding less?* It does not, and
the honest way to see how badly is the four nulls side by side (primary instrument, held out):

| | weight | CAGR | vol | maxDD | Ulcer | MAR | Sharpe |
|---|---|---|---|---|---|---|---|
| buy-and-hold | 1.000 | 11.02 % | 17.99 % | 55.25 % | 13.80 | 0.199 | 0.520 |
| **crash filter SMA-100** | 0.718 avg | **6.52 %** | 11.07 % | **46.66 %** | **16.35** | 0.140 | 0.380 |
| **N1** ex-post vol-matched | 0.616 | 8.18 % | 11.07 % | **37.01 %** | 7.72 | 0.221 | 0.520 |
| N2 ex-ante vol-matched (design-set) | 0.634 | 8.32 % | 11.40 % | 38.03 % | 8.00 | 0.219 | 0.520 |
| N3 exposure-matched | 0.718 | 8.98 % | 12.91 % | 42.34 % | 9.31 | 0.212 | 0.520 |
| **vol overlay L60/10 %** | 0.726 avg | 8.52 % | 10.37 % | **27.63 %** | 7.35 | **0.309** | **0.578** |
| N1 for the overlay | 0.576 | 7.87 % | 10.37 % | 34.88 % | 7.11 | 0.226 | 0.520 |

N2 and N3 agree with N1 to within a point and a half of drawdown — **the conclusion does not depend
on which form of "hold less" you pick.** A constant 61.6 % in SPY and 38.4 % in T-bills, rebalanced
and requiring no rule, no signal, no turnover and no attention, beat the frozen crash filter on
**every** column: more return, less drawdown, half the ulcer, +0.14 of Sharpe.

**One asymmetry recorded against ourselves:** N1's continuous rebalancing is modelled free (about
2 bp/yr of real turnover, uncharged) while the strategies pay 2.5 bp per side. That favours the
**null**, which is the conservative direction for the claim being tested, and it is left in.

---

## 4. Where the freeze cost us, stated plainly

**The five declared SMA lengths, held out** — the frozen one is starred:

| N | maxDD | N1 maxDD | ΔmaxDD | ΔCAGR | Ulcer vs N1 |
|---|---|---|---|---|---|
| 50 | 27.2 % | 36.0 % | **+8.79 pp** | −2.33 %/yr | 9.81 / 7.43 |
| **100\*** | **46.7 %** | 37.0 % | **−9.65 pp** | −1.66 %/yr | 16.35 / 7.72 |
| 150 | 31.2 % | 37.8 % | +6.61 pp | +0.30 %/yr | 10.05 / 7.94 |
| 200 | 21.5 % | 38.2 % | **+16.74 pp** | +0.93 %/yr | 8.17 / 8.07 |
| 250 | 23.3 % | 39.5 % | +16.25 pp | −0.08 %/yr | 8.45 / 8.47 |

**Four of five beat the null; the freeze picked the one that did not, and it is worse than its
neighbours by 16 pp.** Design-window MAR ranked `150 > 100 > 250 > 200 > 50`; held-out drawdown
improvement ranks `200 > 250 > 50 > 150 > 100`. **The two orderings are close to inverted.** The
design window did not merely fail to identify the good parameter — it actively preferred the bad one.

**And the plateau rule, which `FINDINGS` §5 endorses, is what did it.** SMA-100 and SMA-150 were
within 5 % of each other on design MAR — a plateau by the rule's own definition, which the rule
reads as *"the effect belongs to the payoff shape, not the tuning."* Out of sample those two
neighbours differ by **15.5 pp of maximum drawdown**.

> **Method rule earned here: a plateau in a *ratio* is not a plateau in the statistic you care
> about.** MAR = CAGR/maxDD can be flat across two parameters whose *drawdowns* differ by half.
> Check the plateau in the metric the claim will be made in, and check it out of sample before
> believing it means the effect is structural.

**This does not rescue the family.** The expanding-window walk-forward re-selected N at every one of
the 37 year-ends using only data available at the time, chose **150 every single year**, and still
failed: **+6.61 pp at p = 0.304**, G4 failed at 4× cost (4.81 round trips/yr), DSR 0.158. Even the
best-case selection path is not certifiable. And *choosing again after seeing this table is not
available* — that is what the freeze is for.

**Family B is not fragile in the same way.** Across all eight declared configurations the drawdown
improvement ranges −1.03 to +8.50 pp (7 of 8 positive) and the CAGR gap is **positive in 8 of 8**
(+0.51 to +0.94 %/yr). The frozen member sits at the good end but is not an outlier, and the ordering
is interpretable rather than arbitrary: the 10 % targets beat the 15 % targets because a 15 % target
on a 18 %-vol index barely de-risks at all.

**Levering back to volatility was priced, not assumed away.** The four `w_max = 1.5` members borrow
in calm regimes and are charged **cash + 150 bp on the levered notional, accrued on calendar days**
so a Friday position pays for the weekend. They are not thereby ruined — L60/10 %/1.5 posts
+8.50 pp and +0.71 %/yr — but they add volatility (10.78 % vs 10.37 %) for no drawdown gain, which
is the expected shape: margin interest is a certain cost paid to acquire an uncertain one.

---

## 5. Why the overlay fails G1 even at +7.25 pp — the drawdown power problem

`FINDINGS` §5h established the programme's binding constraint for *mean* claims: `(2.80/S)²` years.
**T13 establishes the analogous constraint for *drawdown* claims, and it is worse.**

Maximum drawdown is **one order statistic of one path**. The paired stationary block bootstrap
(10,000 resamples, mean block 63 days) puts the 5–95 range of the overlay's drawdown advantage at
**−3.68 pp to +13.01 pp** around a point estimate of +7.25 pp, median +3.31 pp. **The sampling error
is the same size as the effect.**

The crash table says the same thing in plainer language:

| crash | N1 loss | overlay loss | overlay better by |
|---|---|---|---|
| 2000-09-01 → 2002-10-09 | −27.96 % | −26.85 % | 1.11 pp |
| 2007-10-09 → 2009-03-09 | −34.88 % | −21.07 % | **13.82 pp** |
| 2020-02-19 → 2020-03-23 | −20.50 % | −17.42 % | 3.08 pp |

Mean −6.00 pp, **sd 6.84 on n = 3**. **The 7.25 pp headline is essentially 2008.** In the other two
crashes the overlay is worth one to three points, which is inside the noise of anything.

> **The unit of evidence for a drawdown claim is a crash, not a day.** 36.6 years of daily data is
> 9,222 return observations and **three usable crash comparisons**. T9 needed 327 events and got
> 13.4 a year; T13 needs perhaps twenty crashes and gets **one every nine years**. That is
> **180 years**, and no amount of daily data substitutes, because the daily observations inside one
> crash are one event.

**The decade breakdown confirms it is not a fluke of one window and confirms it is small.** Overlay
drawdown improvement vs its matched null by decade: **+0.84, +1.04, +0.59, +2.04 pp** — *positive in
all four*, and *tiny in all four*. The filter's: **−0.26, −12.00, −3.21, +1.03 pp** — negative in
three of four. **Consistent sign, negligible size** is the overlay's honest description.

---

## 6. What G3 established, and the limit on reading it

The circular-shift null rotates the strategy's **own** exposure path against the unshifted market,
which holds the dose, the run-length structure and the turnover **exactly** fixed and destroys only
the alignment. All 9,221 rotations were computed, not sampled.

| | strategy maxDD | rotation p05 | rotation median | strategy percentile |
|---|---|---|---|---|
| crash filter SMA-100 | 46.66 % | 35.25 % | 49.88 % | **32.8 %** — indistinguishable from random placement |
| vol overlay | 27.63 % | 33.60 % | 45.71 % | **2.2 %** — the alignment is real |
| walk-forward SMA-150 | 31.16 % | — | — | **1.2 %** |

**The overlay's timing is genuinely informative about when the market will fall — and that still is
not enough to beat a constant weight.** Both statements are in the table above, and they are not in
tension: G3's null is a *rotated time-varying* path, whose median drawdown (45.7 %) is far worse than
a *constant* weight's (34.9 %). Randomly-placed variable exposure is a bad thing to hold.

> **Recorded as a limit on our own instrument: G3 is the weaker of the two nulls and must never be
> reported without G1 beside it.** A strategy can sit in the 2nd percentile of its own rotations and
> still lose to a flat line. This one does.

---

## 7. Costs, and the one place they matter

| | round trips/yr | ΔmaxDD ×1 | ×2 | ×4 | ΔCAGR ×1 | ×4 |
|---|---|---|---|---|---|---|
| crash filter SMA-100 | 5.84 | −9.65 pp | −10.71 | −12.77 | −1.66 %/yr | −2.65 |
| **vol overlay** | **0.86** | +7.25 pp | +7.19 | +7.07 | +0.66 %/yr | +0.51 |

**The overlay is cheap and the filter is not.** 5.84 round trips a year at 2.5 bp a side is a real
drag on a rule whose whole claim is that it costs you nothing; the overlay's exposure moves slowly
enough that 4× the cost changes its drawdown advantage by 0.18 pp.

**T13 is the first equity candidate in this programme that does not die at the friction floor**, and
the second (after T9) whose binding constraint is sample size. The B19P frictionless bound confirms
it — **charging literally zero cost does not rescue Family A**:

| zero cost, held out | ΔmaxDD vs N1 | ΔCAGR vs N1 |
|---|---|---|
| crash filter SMA-100 | **−8.57 pp** (45.58 % vs 37.01 %) | −1.33 %/yr |
| vol overlay | +7.31 pp | +0.71 %/yr |

Costs move the filter's verdict by 1.1 pp and the overlay's by 0.06 pp. **Neither answer is about
execution**, which is what makes this a clean power result rather than a friction one.

---

## 8. What is and is not claimed

**Established.**

1. **A moving-average crash filter on the S&P 500 does not beat holding less of it.** Frozen
   configuration: −9.65 pp of drawdown, −1.66 %/yr, higher ulcer than *undiluted* buy-and-hold,
   p = 0.53. Out of sample, on 36.6 years, on two instruments.
2. **It nevertheless protects inside crashes** — 3 for 3 against the matched null, mean 16.9 pp —
   and that fact is compatible with (1) because its own worst drawdown is a whipsaw, not a crash.
3. **A 60-day volatility-targeting overlay is the better-behaved object**: cheaper (0.86 vs 5.84
   round trips/yr), positive-signed in all four decades and all eight declared configurations, and
   its timing beats random placement of its own exposure at the 2nd percentile. **Its advantage over
   holding less is +7.25 pp of drawdown and +0.66 %/yr, and neither is certifiable** (p = 0.233;
   DSR 0.355 against a 0.95 gate).
4. **No return claim of any kind.** G5 was declared in advance as expected to fail and it did, for
   every configuration: the overlay's paired per-observation Sharpe of 0.00839 is **below** the
   0.01228 chance ceiling at 14 trials.

**Not claimed, and specifically disclaimed.** That the overlay works; that SMA-200 works because it
scored +16.74 pp on a table we read after the freeze; that any of this licenses an order. `paper.py`
`submit()` still refuses and execution remains owner-gated.

**An honesty item the freeze cannot fix, restated from the pre-registration.** The 200-day filter and
the vol-managed portfolio (Moreira & Muir 2017) are both heavily pre-mined public results, and the
vol-managed one is contested in the published record (Cederburg, O'Doherty, Wang & Yan, JFE 2020,
find no real-time utility gain). Freezing on 1929–1989 protects against *our* fitting, not the
world's. **That is exactly why the verdict rests on nulls that contain no parameter at all** — a
constant weight cannot have been data-mined into existence.

---

## 9. What this changes about the programme

**The pivot's premise was right and its hoped-for conclusion was wrong.** T10's arithmetic said a
fifth *directional* test buys only an honest negative, and that distribution-shape claims survive
where mean claims do not. T13 accepted that and found the shape claim runs into **its own, harsher
power wall**: a mean claim gets one observation per day, a drawdown claim gets one per crash.

**Three things worth carrying.**

- **Crash-by-crash protection is not full-path drawdown reduction.** The crypto crash-filter result
  in `FINDINGS` §5b is stated in the first metric. **The equity replication passes that metric and
  fails the second**, and the second is the one an owner actually experiences. *`FINDINGS` §5b should
  be read as "protects in crashes", never as "reduces the drawdown you will live through".* Whether
  the BTC result survives the vol-matched null is now an open question with a known method — the
  runner here does it in one call.
- **Volatility targeting is the surviving direction, and it should be tested prospectively, not
  re-run.** It is cheap, consistently signed, structurally motivated (volatility clustering is the
  most robust regularity in the field), and it fails only on power. **1990–2026 is now burned for
  it.** A pre-registered *forward* test is the only honest next instrument — and at one crash per
  nine years, that is a decade-scale commitment, which is an owner scope call, not a technical one.
- **The de-risked buy-and-hold null belongs in this programme's standard battery.** It cost one
  function, it has no parameters, and it killed both families here after killing funding carry in
  the crypto phase. **Any future claim of the form "this reduces risk" gets it automatically.**

---

## 10. Reproduction

```bash
python scripts/t13_data.py build            # 4 series, hashed into research/data/t13_cache/MANIFEST.json
python scripts/t13_risk_shaping.py design   # refuses to read a bar dated >= 1990-01-02
python scripts/t13_risk_shaping.py heldout  # refuses unless the pre-registration hash matches
python scripts/t13_risk_shaping.py audit    # truncation probes + the negative control
```

Data spot-checked against known prints before use: 1929-10-29 = 20.43, 1987-10-19 = 224.84,
2020-03-23 = 2237.40.

| artifact | what |
|---|---|
| `T13_PREREGISTRATION.md` | the freeze — grid, gates, nulls, verdict logic |
| `T13_FROZEN_CONFIG.json` | design-window output and the frozen parameters, with the pre-reg hash |
| `T13_HELDOUT_RESULT.json` | every number above |
| `T13_DIAGNOSTICS.json` | the lookahead audit |
| `scripts/t13_data.py` | fetch, splice, hash |
| `scripts/t13_risk_shaping.py` | design / heldout / audit |
