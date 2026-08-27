# DEEPMINE_CEFNAV — deep search inside the CEF / fund NAV-discount family

**Status at the time this section was written: PRE-REGISTRATION. No design number and no
held-out number existed yet.** Sections 1–5 below were written and committed before
`scripts/trading_bot/deepmine_cefnav.py` was run for the first time. Sections 6 onward are the
result and are appended after.

---

## 1. What is already known in this family, and what this is NOT

The basket already carries slot **L5 / `T12CEF`**: a cross-sectional **discount-LEVEL** decile
tilt over the ~360-fund CEFConnect universe — long the ~36 widest-discount borrowable funds,
short the ~36 narrowest/premium borrowable funds, price > $5, dollar-neutral, 4-week hold with
weekly overlapping tranches. Its frozen prior verdict: held out (2024-03 → 2026-08, 116 wk)
**+13.44 bp/week net, t = 3.51, ann Sharpe 2.35**.

Note for the record, because the brief's framing was slightly off: the *pre-registered* T12
primary (trial 4, a 52-week **z-score** of the discount, H = 4) is **DEAD** — it failed three of
four kill gates. The thing that survived and made the basket is **trial 5/6, the raw discount
LEVEL**, promoted out of `T12_DIAGNOSTICS.json`. So the z-score branch of this family has
already been tested and lost, and the level branch has already been tested and won. Neither is
a discovery available to this sweep.

**This sweep therefore does not ask "does the CEF discount tilt work".** It asks: *is there
anything in the CEF NAV-discount family that the basket does not already own?* Every candidate
is scored on two axes:

1. its own stand-alone net Sharpe, and
2. its **alpha to the incumbent** — the intercept of a regression of the candidate's weekly net
   returns on the incumbent's weekly net returns. A candidate with corr 0.9 to L5 and a great
   Sharpe is *not a finding*; it is L5 wearing a hat.

## 2. Data, and its declared limits

100 % cached and free — **no network call is made**. `research/data/t12_cache/`:

| file | content |
|---|---|
| `history_5Y.json.gz` | CEFConnect weekly price / NAV / discount, 353 funds, 249 dates, 2021-08-20 → 2026-08-14 |
| `adjusted_bars.json.gz` | Alpaca SIP daily closes, `adjustment=all` (split **and** distribution adjusted), 358 tickers |
| `universe.json.gz` | CEFConnect statics: Morningstar category, strategy, sponsor, `Term`, `IsLeveraged`, expense, ADV, market cap |
| `alpaca_assets.json.gz` | live `shortable` / `easy_to_borrow` flags (186 of 360 are ETB) |
| `cef_half_spread.json.gz` | first-party SIP measurement: median CEF half-spread **11.53 bp**, p75 18.4, p90 27.2 |

Declared limits, none of them smoothed over:

* **Live-only universe.** CEFConnect serves funds alive today. Funds liquidated, merged,
  open-ended or tendered away between 2021 and today are absent, and those are
  disproportionately wide-discount funds whose discount was closed *by* the event. The
  survivorship direction is plausibly conservative for a long-wide-discount book but it is not
  provably so.
* **Statics are today's snapshot.** Category, sponsor, `Term` and `IsLeveraged` are close to
  time-invariant and are used as conditioners with that declared. Distribution *rate* is NOT
  taken from the snapshot — it is reconstructed point-in-time (§3).
* **NAV is weekly and only 5 years deep.** Alpaca serves no NAV pseudo-ticker history. This is
  the binding constraint on the whole family and nothing in the repo relaxes it.
* **There are no BDCs here.** All 26 Morningstar categories in the snapshot are closed-end
  funds. BDC NAV is quarterly and no free BDC NAV source is wired in this repo, so the BDC
  branch of the brief is **not testable** with what is available. Said rather than faked.

## 3. Point-in-time distribution yield (the one new primitive)

CEFConnect's price history is a **raw** close; Alpaca's bar is **distribution-adjusted**. The
weekly difference of the two return series is therefore the realised distribution:

```
Y[t] = ( A[t+1]/A[t] − 1 ) − ( P[t+1]/P[t] − 1 )
```

with `A` the adjusted close and `P` the CEFConnect raw close. Trailing 52-week sum of `Y` is a
genuinely **point-in-time** distribution yield — no look-ahead, unlike the snapshot's
`DistributionRatePrice`. The same `Y` lets a NAV **total** return be built
(`NAV price return + Y`), which is what makes the price-vs-NAV return-spread branch (§4 F)
possible at all.

## 4. The formula catalogue

Structurally different definitions, not a parameter grid around one idea:

* **C — cross-sectional neutralisation of the level:** discount demeaned by Morningstar
  category median; book formed *within* each category; demeaned by broad group
  (muni / taxable-FI / equity / hybrid); book formed within group; demeaned by **sponsor**.
* **Z — own-history normalisation:** percentile rank of the discount inside its own trailing
  52 w history; distance from own 52 w mean **unstandardised**; 13-week z; and — built
  deliberately to be non-collinear — the 52 w and 26 w z **orthogonalised cross-sectionally to
  the level itself**, which is the exact residual the incumbent cannot span.
* **M — discount momentum vs reversion:** fade the 1 / 4 / 13 / 26-week change in the discount,
  and fade discount **acceleration**.
* **S — price-vs-NAV return spread:** fade the 4 w and 13 w cumulative log spread between the
  fund's price total return and its NAV total return; and long NAV total-return **momentum**
  (the price-under-reaction channel), 4 w and 13 w.
* **Y — distribution-yield conditioning:** the PIT trailing-yield tilt on its own with no
  discount in it; the level **orthogonalised to** trailing yield; the level tilt restricted to
  the high-yield half; and to the low-yield half.
* **X — structural screens:** term funds only (mandated wind-up forces convergence); levered
  only; muni only; equity only; taxable-FI only.
* **W — construction:** signal-proportional weights, quintile instead of decile, and a
  threshold entry that trades only names with |z52| > 1.5.

Every structure is run at **both** hold horizons, 1 week and 4 weeks.

## 5. Costs, screens, windows, and the decision rule — all fixed before the run

**Costs (T6/T8/M0 conventions, both legs charged):** measured **11.53 bp** half-spread on every
unit of realised turnover on **both** sides; SEC §31 fee 0.278 bp on sale notional; **borrow at
the realised 200 bp/yr short rate — not the 33 bp ETB floor — on the short half**, accrued
daily. Short leg is screened to Alpaca `easy_to_borrow`, because hard-to-borrow is exactly what
killed the dual-class book to −45 bp. Price > $5 on both legs.

**Windows.** Design **2021-08-20 → 2024-02-23**; held out **2024-03-01 → 2026-08-07**. This is
T12's own frozen split, reused so the incumbent's published numbers are directly comparable.

**Honest declaration about the holdout.** This held-out block is **not virgin at the family
level** — the incumbent was already measured in it at Sharpe 2.35. Any candidate correlated
with the incumbent will inherit that number, and reading a high held-out Sharpe as
"independently confirmed" would be self-deception. The **decisive** held-out statistic is
therefore the **alpha to the incumbent**, which nobody has ever looked at. Both are reported;
only the alpha is treated as evidence of something new.

**Staging.** The script runs in two stages. `design` computes the design window only and writes
`DEEPMINE_CEFNAV_DESIGN.json` with every held-out field literally set to `"SEALED"`. Selection
happens against that file. Only then is `reveal` run.

**Noise bar.** With `N` scored formulas and a sign that could have gone either way, the expected
maximum |t| under the null is `sqrt(2 ln 2N)`. A formula is called real only if it **clearly**
beats that bar on the design window **and** its held-out number survives the same costs.

**Decision rule, fixed now:**

1. `design t` > `sqrt(2 ln 2N)` — clears the noise bar it was searched over; **and**
2. `|corr| to the incumbent < 0.7` on the design window — it is not L5 wearing a hat; **and**
3. `design alpha-to-incumbent t` > 2.0 — it adds something on top of what the basket owns.

Candidates meeting all three are put forward; the held-out block then either confirms or kills
them, and whichever it does is what gets written down.

---

## 6. Design-window result and the SELECTION — written before the holdout was unsealed

`DEEPMINE_CEFNAV_DESIGN.json`, produced by `deepmine_cefnav.py design`, in which every
held-out field is the literal string `"SEALED"`. **N = 66 scored formulas**, noise bar
`sqrt(2 ln 132)` = **t = 3.125**. Design window 2021-08-20 → 2024-02-23.

### 6a. A post-freeze stress that was added before any selection, and why

Twenty-two of the 66 formulas cleared t = 3.125 on the design window. Under a pure null you
would expect 0.12 of them to. So the family is *not* noise — but the shape of the winners was
wrong: the biggest t-statistics all came from **one-week-hold reversal** structures (13-week
z-score, one-week discount change, four-week price-minus-NAV spread) with turnover of 1.0–1.8
of the book per week. That is the exact signature of **closing-print bid-ask bounce**, not of
NAV convergence: the close alternates between bid and ask, so any signal built on last week's
close and executed at this week's close is partly just buying at the bid and selling at the ask
on paper.

Two structural stresses were therefore added — **motivated by the mechanism, not by any
number**, and both computed on the design window only:

1. **One-trading-day implementation lag.** CEFConnect publishes NAV *after* the close (the
   snapshot's `NAVPublished` trails `LastUpdated` by a session), so a discount observed on
   grid date *k* is actionable no earlier than the **next** session's close. The weekly return
   is rebuilt from the daily adjusted bars on a grid shifted one trading day forward. This is
   not conservatism, it is the correct as-of.
2. **p90 spread instead of median.** The book deliberately holds the *extremes* of a universe
   whose half-spread runs 11.5 bp at the median, 18.4 at p75 and **27.2 at p90**. Charging the
   median to a book that selects the tails understates cost. The ladder charges 11.53 / 18.38 /
   27.25 bp.

### 6b. What the stress did

| formula | design Sh | design t | turn/wk | corr to L5 | α t | +lag1 | +p90 | **lag1 & p90** |
|---|---|---|---|---|---|---|---|---|
| `Z03_z13_H1` 13w z of discount, 1w hold | 4.90 | **7.18** | 1.20 | 0.18 | 6.74 | 3.25 | 2.50 | **0.70** |
| `Z05_z26_resid_level_H1` z26 ⟂ level | 4.79 | **6.61** | 0.94 | 0.00 | 6.58 | 3.12 | 2.89 | **1.14** |
| `M01_dd1_fade_H1` fade 1w discount change | 3.55 | 5.48 | 1.77 | 0.01 | 5.41 | 1.91 | 0.08 | **−1.62** |
| `S01_cum4_fade_H1` fade 4w price−NAV spread | 3.14 | 4.79 | 1.09 | 0.14 | 4.38 | 1.41 | 1.09 | **−0.64** |
| `M02_dd4_fade_H1` | 2.73 | 4.17 | 1.10 | 0.19 | 3.64 | 1.06 | 0.78 | **−0.89** |
| `M05_accel_fade_H1` | 0.49 | 0.73 | 1.21 | 0.29 | −0.10 | −1.16 | −1.99 | **−3.61** |
| **`Y04_level_in_loyield_H4`** | 2.85 | 3.38 | **0.16** | 0.38 | 2.90 | **3.04** | **2.51** | **2.64** |
| `Y05_muni_eq_static_H1` (static twin) | 3.21 | 4.98 | 0.33 | 0.58 | 3.71 | 2.86 | 2.59 | **2.28** |
| `Y04_level_in_loyield_H1` | 3.12 | 3.69 | 0.46 | 0.34 | 3.25 | 2.73 | 2.28 | **1.83** |
| `Y05_muni_eq_static_H4` | 2.28 | 3.54 | 0.13 | 0.66 | 1.76 | 1.93 | 2.03 | **1.70** |
| `X04_equity_H1` | 2.61 | 4.04 | 0.37 | 0.47 | 2.78 | 2.09 | 2.11 | **1.64** |
| `C04_grp_within_H1` group-neutral book | 2.85 | 4.42 | 0.40 | 0.59 | 3.02 | 2.30 | 2.01 | **1.51** |
| `Y03_level_in_hiyield_H4` (the mirror) | 0.90 | 1.07 | 0.14 | 0.77 | −0.49 | 0.60 | 0.63 | **0.35** |
| **`INCUMBENT L5` level, H4** | 2.16 | 3.35 | — | 1.00 | — | 1.71 | 1.91 | **1.49** |

**The entire high-t half of this family is bid-ask bounce.** Every structure with a t above 4
is a one-week-hold reversal, and every one of them loses most or all of its edge to a
one-trading-day lag and a p90 spread. `Z03_z13_H1` goes 4.90 → 0.70; `M01_dd1` goes 3.55 →
−1.62. Those are not edges, they are the spread being counted as profit.

### 6c. The selection, fixed here before the reveal

**Primary pick: `Y04_level_in_loyield_H4`** — the discount-LEVEL decile tilt restricted to the
half of the universe with the **lower trailing 52-week point-in-time distribution yield**,
4-week hold. It is the only formula that satisfies all four of:

* clears the pre-registered rule — design t 3.38 > 3.125, |corr| to L5 0.38 < 0.7, α t 2.90 > 2.0;
* survives the implementation lag *and* the p90 spread at **2.64**, which is **higher than the
  incumbent's own stressed 1.49** on the identical ladder;
* turnover 0.16 of book per week, so it is not a spread-harvesting artefact; and
* has an economic story that predicts its own mirror: among high-distribution-rate funds the
  discount is a yield-chasing instrument rather than a NAV-convergence instrument, so the tilt
  should be weak there — and `Y03_level_in_hiyield_H4` is 0.90 design, 0.35 stressed.

**Secondary, put forward but not as anchors:** `Y05_muni_eq_static_H1`, `Y04_level_in_loyield_H1`,
`X04_equity_H1`, `C04_grp_within_H1`.

**Declared dead on the design window before the reveal:** `Y01` pure distribution-yield tilt
(negative both directions), `X01` term-fund screen (0.02 Sharpe — the mandated-wind-up story
does not pay), `S03/S04` NAV total-return momentum (negative — the price does not under-react
to NAV), `M05` discount acceleration, `X05` taxable-credit-only.

**The honest caveat, stated before the reveal:** design t 3.38 against a bar of 3.125 is
**1.08×**. That is *clearing* the noise bar, not *clearly beating* it. `Y04` also has only
n = 73 design weeks, because the 52-week PIT-yield warm-up eats the first year. The stress
ladder is what distinguishes it, and a stress ladder is a robustness argument, not a
significance argument.

### 6d. One disentangler that matters

The low-yield half is 44 % muni, 33 % equity, 16 % taxable-credit; the high-yield half is 53 %
taxable-credit. So a **static sector screen** could produce almost the same book with no yield
information in it. That twin was built and run:

* `Y05_muni_eq_static_H4` (muni+equity only, no yield): stressed **1.70**
* `Y04_level_in_loyield_H4` (PIT low-yield half): stressed **2.64**
* `Y06_loyield_within_taxfi_H4` (yield conditioner *inside* the credit group, sector held
  fixed): design 1.54, t 1.83, corr −0.16, α t 2.12 — same sign, but only ~3 names a side, so
  it is directionally supportive and statistically almost empty.

Reading: **most, not all, of `Y04` is a sector split; the PIT yield adds roughly 0.9 of stressed
Sharpe on top of its static twin, and the within-credit test agrees in sign but cannot carry
weight.**

---

## 7. The reveal — and the pre-registered primary **failed**

`DEEPMINE_CEFNAV.json`, from `deepmine_cefnav.py reveal`. Held out 2024-03-01 → 2026-08-07.

Two extra controls were added at reveal time, both of which can only make the verdict *harder*
and neither of which can select anything:

* **The incumbent at both horizons.** Any 1-week-hold candidate can show "alpha to L5" that is
  nothing but the horizon difference, since L5 holds 4 weeks. So the held-out alpha is also run
  as a **two-factor** regression on [L5 at H=4, the same signal at H=1]. Column `ha2`.
* **The stress ladder re-run on the held-out block**, so an edge that only exists at the median
  spread and with zero implementation lag is visible as such. Columns `hStrs`, `hs2T`.

### 7a. The headline

**The pre-registered primary, `Y04_level_in_loyield_H4`, failed.**

| | design | held out |
|---|---|---|
| net Sharpe | 2.85 | **1.77** (+18.66 bp/wk, t 2.66) |
| under lag1 + p90 | 2.64 | 1.80 |
| α t to L5 (1-factor) | 2.90 | **0.77** |
| α t to L5 (2-factor) | — | **1.05**, stressed **0.92** |

It stands up as a strategy — positive net of realistic costs, robust to the stress — but its
held-out **alpha to the incumbent is zero**. The design-window alpha of 2.90 did not replicate.
`Y04` is not a new edge; it is a **subset of L5** that happened to look better than the parent
on the design window. And it is *worse* than the parent out of sample: L5 itself held out at
**2.73** over the same weeks. The low-distribution-yield conditioner is a real description of
*where in the universe* L5 earns, and it is worth nothing as a separate leg.

### 7b. The bid-ask-bounce diagnosis was confirmed out of sample, brutally

Every structure the design window ranked highest went **negative** on the held-out block once
the one-day implementation lag and the p90 spread were charged — and negative on the *alpha*,
not merely flat:

| formula | design t | held Sharpe (measured cost) | **held stressed Sharpe** | **held stressed α t** |
|---|---|---|---|---|
| `M01_dd1_fade_H1` | 5.48 | 1.86 | **−5.13** | **−7.07** |
| `M05_accel_fade_H1` | 0.73 | −0.63 | −6.04 | −7.69 |
| `Z03_z13_H1` | **7.18** | 1.64 | **−4.38** | **−5.74** |
| `M02_dd4_fade_H1` | 4.17 | 1.02 | −3.39 | −4.30 |
| `S01_cum4_fade_H1` | 4.79 | 1.12 | −3.39 | −4.22 |
| `Z03_z13_H4` | 4.05 | 0.14 | −2.25 | −3.64 |
| `Z05_z26_resid_level_H1` | 6.61 | 1.76 | −2.62 | −3.16 |
| `Z01_pctrank52_H1` | 4.42 | 2.23 | −2.27 | −3.15 |

This is the most useful thing the sweep produced. **The entire short-horizon
discount-reversal branch of the CEF family — 13-week z, orthogonalised z, 1/4/13/26-week
discount change, discount acceleration, price-minus-NAV return spread — is the closing-print
bid-ask bounce.** It produces t-statistics of 5 to 7 on a design window, it looks like the
strongest thing in the family, it survives a decile-permutation test, and it is worth **less
than nothing** the moment you concede that CEFConnect publishes NAV after the close and that a
book which holds the extremes of a 360-fund universe pays more than the median spread. Anyone
mining this family without those two corrections will find a Sharpe-5 strategy and lose money
on it.

### 7c. One survivor, and it is thin

Of the 22 formulas that passed the pre-registered rule, exactly one has a positive held-out
alpha that survives the stress: **`Y05_muni_eq_static_H1`** — the discount-LEVEL decile tilt
restricted to **muni + equity CEFs only** (i.e. taxable-credit funds excluded), **1-week hold**.
It entered the sweep as a *control*, the static sector twin built in §6d to try to explain
`Y04` away.

| | design (125 wk) | held out (114 wk) |
|---|---|---|
| net Sharpe, measured cost | 3.21 (t 4.98) | **3.07** (+33.26 bp/wk, t 4.54) |
| net Sharpe, lag1 + p90 | 2.28 | **1.95** (t 2.89, +18.58 bp/wk) |
| α t to L5, 2-factor | 3.71 | **4.53** |
| α t to L5, 2-factor, **stressed** | — | **2.93** |
| β to L5 out of sample | — | **−0.003** (uncorrelated) |
| turnover / week | 0.33 | 0.33 |

Second-round noise bar: 22 shortlisted formulas, two-sided, `sqrt(2 ln 44)` = **2.751**. Its
stressed held-out alpha t of **2.93 clears that by 1.06×**. The next-best of the 22 is 0.94.

**Why it is nonetheless thin, stated plainly:**

* **The held-out edge is in one half.** Stressed, first 57 weeks Sharpe **0.54** (+5.19 bp/wk);
  second 57 weeks Sharpe **3.53** (+31.96 bp/wk). That is not a stable edge, it is an edge that
  arrived.
* **37 % of the stressed held-out mean comes from the 5 best weeks** of 114.
* **The short leg is 7 names** (median, held-out) — muni + equity, ETB-screened, decile of a
  restricted universe. Concentration risk is severe and capacity is trivial.
* Block bootstrap (8-week blocks, 5 000 draws) on the stressed held-out alpha: P(α > 0) =
  0.9990, α = +20.2 bp/wk, 95 % CI [+7.6, +32.7]. Encouraging, but the bootstrap cannot repair
  the half-sample instability — it resamples the same second half.
* It was a **secondary**, not the primary. The pre-committed primary failed. Promoting the
  runner-up after the reveal is exactly the move this programme is supposed to distrust, which
  is why it is reported as a **forward-test candidate with a guard, not as a proven edge**.

### 7d. What would have been the pick if I had peeked, and why that matters

`C02_cat_within_H1` (book formed within each Morningstar category) held out at Sharpe 2.60 with
a two-factor alpha t of **3.77**, and `C02_cat_within_H4` at 2.20 with α t **3.15** — better
held-out alphas than almost anything selected. **Neither was selected**, because their design
t-statistics were 2.20 and 1.98, below the 3.125 bar. They are reported here and claimed as
nothing. If the rule had been relaxed after seeing the holdout, they would have become the
finding; that is precisely the failure mode the staging exists to prevent.

### 7e. Verdict on the sub-family

**The family is not noise — but the new territory in it very nearly is.**

* The family demonstrably contains a real edge: L5, which held out again here at Sharpe 2.73
  net of the measured spread and a 200 bp realised borrow.
* **Twenty-one of the 22 rule-passers add nothing to it**, and the most statistically
  impressive of them are a microstructure artefact that loses money once executed honestly.
* **One candidate, `Y05_muni_eq_static_H1`, survived every test but is unstable across the
  held-out halves and runs a 7-name short leg.** The economic claim it encodes — *exclude
  taxable-credit CEFs from the discount tilt, because in credit funds the discount is a
  yield-spread instrument rather than a NAV-convergence instrument* — is coherent, is supported
  in the same direction by `Y04`/`Y03`/`X05`, and is worth a forward test at a satellite budget.
* **Branches killed outright** (design *and* held out): pure distribution-yield tilt (`Y01`,
  negative both windows), term-fund/mandated-wind-up screen (`X01`, 0.02 design / 0.05 held),
  NAV total-return momentum (`S03`/`S04`, negative — the price does **not** under-react to NAV),
  discount acceleration (`M05`, −3.6 design stressed, −7.7 held stressed).
* **Not testable on free data:** BDC discounts. CEFConnect's `DailyPricing` carries zero BDCs,
  BDC NAV is quarterly, and no free BDC NAV source is wired in this repo.
