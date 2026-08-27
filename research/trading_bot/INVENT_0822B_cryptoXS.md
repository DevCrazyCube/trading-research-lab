# INVENT 0822B — theme: CROSS-SECTIONAL CRYPTO SPOT (momentum / reversal / volume / volatility)

**Date:** 2026-08-22 (2nd rotation) · **Primary tests: 81** (27 signals × 3 holds) ·
**Promotions: 0** · **Forward-log legs: 1** ·
**Verdict: cross-sectional crypto momentum, reversal and volume are noise net of fees — but a
cross-sectional VOLATILITY premium is real, large, cheap to trade, and is entirely a SHORT-side
effect whose true price (alt borrow) is not in any free feed.**

Harness: `scripts/trading_bot/inv0822b_xs_{lib,forms,gate,sweep,diag}.py`.
Results: `INVENT_0822B_cryptoXS.json` (consolidated), `..._GATE.json` (ρ1 + self-test),
`..._DESIGN.json` / `..._HOLDOUT.json` (all 81 rows), `..._DIAG.json` (clean placebo, betas,
liquidity floors), `..._FLOORS.json`.
Data: cached free Binance spot daily klines only (`research/data/xspot_cache/spot_daily.npz`,
677 USDT pairs **including delisted names**, 2017-08 → 2026-08). No network, no orders, no money.

---

## 0. THE ONE-PARAGRAPH ANSWER

I ranked the top-50-by-volume Binance spot USDT cross-section on **27 different signals** —
ten pure trailing-return horizons (1, 2, 3, 5, 7, 14, 30, 60, 90, 180 days), six momentum
refinements (skip-week, blends, vol-adjusted, BTC-beta-residual, path-consistency), five
volume/activity sorts and six volatility/shape sorts — went **long the top 10 / short the
bottom 10**, and traded each at **three overlapping-tranche holds (1, 5, 20 days)**, all executed
**VWAP-to-VWAP** rather than close-to-close. **The return-ranking families are dead**: the 30
pure-horizon tests have a median design gross Sharpe of **+0.47** and a median *held-out net*
of **+0.18**; the 15 volume tests are **−0.13** held out. **The volatility family is not**: its 18
tests have a median design gross of **+1.13** and a median held-out net of **+2.47**, and the
best formula, `S1_VOL30` (long the 10 lowest / short the 10 highest 30-day realised vol, 20-day
tranches), posts design net **+1.95 (t 3.91)**, held-out net **+2.85 (t 5.39)**, turnover
**0.047/day**, break-even **314 bp/side against a 10 bp fee**, positive in **every one of eight
calendar years**, with **skew ≈ 0** and a held-out max drawdown of 0.79 annual-vol units. It
clears the analytic sign-agnostic bar (1.70), the programme-cumulative bar (1.99) and a
**size-matched slot-permutation placebo** (E[max |SR|] = 1.31, p99 = 1.97, **0 of 400** replicates
reach the observed 2.14). And then the structural test kills the trade as stated: **long low-vol
against short BTC is −1.26 held out**. The entire premium is the **short leg** — high-volatility
small alts bleed at **−121%/yr at full notional** in the held-out window — so the trade is not a
cross-sectional premium at all, it is **short alt-bleed carry**, and its price is the **Binance
margin borrow rate and availability on small high-vol alts**, which free daily klines do not
contain. Nothing is promoted; one forward-log leg is opened, conditional on a measured borrow curve.

---

## 1. WHY THIS IS NOT A RE-RUN

| what the ledger already killed | how this round differs |
|---|---|
| `INVENT_D0821_crypto_spot_xs` (34 formulas), families **A** (price structure) and **D** (volume/vol) | Signals **and execution** are on the daily **VWAP** (`quote_volume/base_volume`), the true volume-weighted traded price; D0821 formed on closes and executed at opens. Every formula runs at **three overlapping-tranche holds**; D0821 rebalanced daily throughout (turnover 1.3 vs 0.04–0.27 here). The book is the **extremes (top-10/bottom-10)**, not a rank-z tilt. A **$1M ADV floor** replaces D0821's unfloored top-50. |
| D0821 `C4_XS_BAB` (bet against **BTC beta**) | Beta is a poor proxy for the crypto vol sort — `S1_VOL30` sorts on **realised idiosyncratic-plus-systematic vol**, and the pure-beta version scored +0.04 design in D0821 while this one scores +2.02. Reported below as a hint the ledger already contained and did not follow. |
| D0821 `A1/A2/A3` one-day reversal, `A5` acceleration, `A6/A7` 5-day and 90d-high | Re-tested here **as a control**, at three holds, on VWAP execution, and confirmed dead: `H001_RET\|H1` design net **−0.20**, held-out net **−1.75** (t −3.31); `H002_RET\|H1` design net **−0.94**, held-out net **−0.95**. |
| `INVENT_0822_crypto_tether` (36 formulas, this morning) | Those were **paired convergence trades on a spread**; every formula here is a **cross-sectional ranking across many coins**. Disjoint P&L object, disjoint sign convention, disjoint instruments (no stablecoins, no wrapped/staked, no cross-quote, no cross-venue — all excluded from the universe by name). |
| Regime conditioning / gating (0/107) | **Zero** conditioners. Every formula is a primary sort. |
| Perp funding / positioning (`XS_GLSR_Z`) | Not touched. This is spot. |

**Signs are fitted on the design window's gross P&L and then frozen**, so the honest analytic bar
is the **sign-agnostic** `sqrt(2 ln 2N)`, not the one-sided version.

---

## 2. THE ρ1 GATE — RUN FIRST, AND IT REWRITES THE LESSON

Lesson 3 says: run the ρ1(Δs) bounce gate before the gross bar for any RV/spread signal.
Run here first, before any P&L, it **passes everything** — and the reason is worth more than the gate.

| series | mean ρ1 | median | p05 … p95 | frac < −0.35 |
|---|---:|---:|---|---:|
| close-to-close coin returns | **−0.042** | −0.043 | −0.170 … +0.085 | **0 %** |
| VWAP-to-VWAP coin returns | **+0.193** | +0.199 | +0.070 … +0.300 | 0 % |

By liquidity tercile the close-return ρ1 is −0.064 (thin, median ADV \$8.6M), −0.034 (mid, \$22M),
−0.028 (thick, \$42M) — bounce is visible, ordered correctly, and **an order of magnitude too small
to matter**.

> **The refinement.** ρ1 is a **spread** diagnostic, not a **cross-sectional-returns** diagnostic.
> The microstructure term's share of measured variance scales as (half-spread / σ)²; a stablecoin
> tether spread has σ ≈ 25 bp/day, a top-50 alt has σ ≈ 500 bp/day. The same 3 bp half-spread that
> drives ρ1(Δs) to −0.45 on a tether moves ρ1(r) to −0.04 on a coin. **Do not spend a round gating
> cross-sectional coin returns on ρ1 — gate the execution instead.**

**The mirror artefact is the real hazard here, and it is the opposite sign.** VWAP is a
**time-averaged** price. Averaged-price returns carry ρ1 = **+0.19** (theory for uniformly
time-averaged Brownian motion: **+0.25**) — they manufacture fake **momentum**, not fake reversal.
Both artefacts are lag-1 (MA(1)) and both are killed by the same thing: the harness's **one-day
gap** (signal through the close of d−1, entry at the VWAP of day d), which puts signal and P&L two
lags apart. The self-test proves it:

| synthetic panel | ρ1 | gross SR, **no gap** | gross SR, **one-day gap (this harness)** |
|---|---:|---:|---:|
| pure bid-ask bounce, no effect | −0.261 | **+36.7** (break-even 91 bp/side) | **−0.32** |
| pure time-averaged price, no effect | **+0.252** | **+31.9** | **−0.55** |
| planted +8 bp cross-sectional effect | — | — | **+2.73** |
| iid random signal | — | — | +0.37 |

---

## 3. DATA, UNIVERSE, WINDOWS, COSTS

**Universe.** Top-50 each day by trailing-30-day mean quote volume, **≥ \$1M/day ADV**, stablecoins,
fiat, wrapped and staked tokens excluded by base symbol. Mean realised size 42.7 (design) / 49.9
(held out). 489 distinct coins enter it over the sample. The panel includes delisted symbols, so the
universe is **survivorship-bias-free**.

**Book.** Long the top 10, short the bottom 10, equal weight, dollar-neutral, unit gross. Holds
H ∈ {1, 5, 20} as **overlapping tranches** (1/H of capital rolled each day), which is what drives
turnover from 0.13 to 0.047 and break-even from 136 to 314 bp/side.

**Execution.** Signal from data through the **close of day d−1**; book entered at the **VWAP of day d**
(`quote_volume / base_volume`, validated to lie inside that day's high/low); marked to the **VWAP of
day d+1**. Cost = `fee × Σ|Δw|` the day weights move, **subtracted after the sign flip**.

**Windows.** Design **2019-01-01 → 2023-01-01** (1,461 d). Held out **2023-01-01 → 2026-08-01**
(1,308 d), opened once, after every sign was frozen to `..._DESIGN.json`.

**Costs.** Headline **10 bp/side** (Binance spot taker, base tier). Shock **20 bp**. Borrow on the
short leg charged separately in §7 at 0/2/5/10/20 bp/day.

---

## 4. THE NULL — AND A PLACEBO THAT HAD TO BE THROWN AWAY

Two size-matched placebos were built. **The first one is wrong and the reason is reusable.**

**Rejected: rotate-the-returns.** Hold each formula's weight matrix exactly fixed (turnover,
universe, cost, hold all preserved) and rotate the *return* panel circularly inside the design
window. It reports E[max |SR|] = **2.17**, p95 = **5.74** over 81 tests — on a per-formula SD of
0.53, i.e. a p95 at **10.8 SD**. That is not a wide null, it is a contaminated one: **coins that
were not yet listed at the rotated date have no return**, so a dollar-neutral book silently acquires
a directional leg. Measured: mean |net dollar exposure among names with a live return| is **0.0036
for the real book and 0.1284 for the rotated books** — a **13 % net directional leg** on a unit-gross
book. Recorded so nobody rebuilds it.

**Used: permute-the-signal-across-ADV-rank-slots.** For each replicate, one fixed permutation of the
50 ADV-rank slots is applied to every formula's signal. A slot is very nearly the same coin day after
day, so the permuted signal keeps the original's persistence and turnover; every leg is a live
universe member, so neutrality and the cross-sectional return covariance are **exactly** preserved;
only the signal-to-coin alignment is destroyed.

| statistic | value |
|---|---|
| tests pooled into the null | **81** |
| permutations | 400 |
| SD of one formula's placebo Sharpe (4.00 y) | 0.524 |
| **placebo E[max &#124;Sharpe&#124;]** | **1.308** |
| placebo p95 / p99 of max &#124;Sharpe&#124; | **1.749 / 1.974** |
| analytic one-sided `sqrt(2 ln 81)`·SE | 1.579 |
| **analytic sign-agnostic `sqrt(2 ln 162)`·SE** | **1.699** |
| programme-cumulative `sqrt(2 ln 1040)`·SE | 1.986 |
| **observed max design gross** (`S1_VOL30\|H1`) | **2.140** |
| replicates whose max ≥ observed | **0 / 400** |

`S1_VOL30` at 2.02–2.14 clears **every** bar including the programme-cumulative one. Nothing else in
the search does: the runner-up, `S3_MAX20|H20` at 1.72, sits **below** the placebo p95.

---

## 5. ALL 81 TESTS, NOTHING DROPPED

`turn` mean daily Σ|Δw| · `Dgr/Dgt` design gross Sharpe/t · `Dnet/Dnt` design net · `Hgr/Hnet/Hnt`
held-out · `BEd` design break-even bp/side · `lag1` gross under one extra day of delay ·
`β` design beta to the equal-weight universe. Sorted by design gross.

| formula | fam | turn | Dgr | Dgt | Dnet | Dnt | Hgr | Hnet | Hnt | BEd | lag1 D | lag1 H | β |
|---|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `S1_VOL30|H1` | S | 0.128 | +2.14 | +4.28 | +1.98 | +3.97 | +2.81 | +2.63 | +4.99 | 136 | +1.99 | +2.81 | -0.11 |
| `S1_VOL30|H20` | S | 0.044 | +2.02 | +4.04 | +1.95 | +3.91 | +2.92 | +2.85 | +5.39 | 313 | +2.01 | +2.96 | -0.10 |
| `S1_VOL30|H5` | S | 0.074 | +1.99 | +3.99 | +1.90 | +3.80 | +2.79 | +2.68 | +5.08 | 209 | +1.98 | +2.86 | -0.11 |
| `S3_MAX20|H20` | S | 0.062 | +1.72 | +3.45 | +1.62 | +3.25 | +2.41 | +2.29 | +4.33 | 172 | +1.76 | +2.43 | -0.07 |
| `S2_VOLOFVOL60|H20` | S | 0.042 | +1.45 | +2.91 | +1.38 | +2.76 | +2.95 | +2.86 | +5.42 | 205 | +1.46 | +2.95 | -0.06 |
| `S2_VOLOFVOL60|H5` | S | 0.062 | +1.37 | +2.74 | +1.28 | +2.56 | +2.97 | +2.85 | +5.39 | 148 | +1.32 | +2.98 | -0.06 |
| `S2_VOLOFVOL60|H1` | S | 0.086 | +1.25 | +2.51 | +1.13 | +2.26 | +2.79 | +2.63 | +4.98 | 104 | +1.17 | +2.78 | -0.07 |
| `S6_ILLIQ30|H5` | S | 0.058 | +1.18 | +2.36 | +1.10 | +2.20 | +2.57 | +2.47 | +4.67 | 141 | +1.22 | +2.55 | -0.08 |
| `H002_RET|H5` | H | 0.267 | +1.18 | +2.36 | +0.73 | +1.45 | -0.43 | -1.15 | -2.17 | 26 | +1.00 | -0.48 | -0.04 |
| `V2_DVOL_GROWTH|H1` | V | 0.257 | +1.17 | +2.35 | +0.85 | +1.70 | +0.66 | +0.20 | +0.38 | 36 | +0.68 | +0.56 | -0.00 |
| `V4_TAKER_SHARE20|H1` | V | 0.184 | +1.15 | +2.30 | +0.86 | +1.72 | -0.02 | -0.48 | -0.92 | 40 | +1.27 | +0.16 | -0.03 |
| `S3_MAX20|H5` | S | 0.112 | +1.13 | +2.27 | +0.98 | +1.96 | +2.32 | +2.13 | +4.04 | 74 | +1.15 | +2.26 | -0.07 |
| `H001_RET|H1` | H | 1.180 | +1.11 | +2.23 | -0.20 | -0.39 | +0.22 | -1.75 | -3.31 | 9 | -0.65 | +0.85 | +0.03 |
| `S6_ILLIQ30|H1` | S | 0.088 | +1.08 | +2.17 | +0.97 | +1.93 | +2.79 | +2.63 | +4.98 | 92 | +1.18 | +2.65 | -0.09 |
| `S3_MAX20|H1` | S | 0.167 | +1.07 | +2.15 | +0.87 | +1.74 | +2.28 | +2.03 | +3.84 | 52 | +0.89 | +2.26 | -0.07 |
| `V5_VOL_TREND|H20` | V | 0.050 | +1.07 | +2.13 | +0.98 | +1.97 | +1.88 | +1.77 | +3.35 | 129 | +1.08 | +1.92 | -0.01 |
| `V5_VOL_TREND|H1` | V | 0.106 | +1.06 | +2.12 | +0.92 | +1.85 | +1.71 | +1.51 | +2.85 | 78 | +0.88 | +1.71 | -0.00 |
| `S6_ILLIQ30|H20` | S | 0.036 | +1.06 | +2.12 | +1.00 | +2.00 | +2.89 | +2.81 | +5.32 | 182 | +1.07 | +2.90 | -0.08 |
| `V5_VOL_TREND|H5` | V | 0.072 | +0.93 | +1.87 | +0.83 | +1.67 | +1.77 | +1.62 | +3.07 | 92 | +0.94 | +1.77 | -0.01 |
| `H005_RET|H1` | H | 0.548 | +0.88 | +1.75 | +0.32 | +0.63 | -0.49 | -1.37 | -2.59 | 16 | +1.13 | -0.54 | -0.06 |
| `H003_RET|H5` | H | 0.268 | +0.85 | +1.70 | +0.45 | +0.90 | -0.51 | -1.15 | -2.17 | 21 | +0.62 | -0.55 | -0.04 |
| `X5_IDIO60|H5` | X | 0.082 | +0.83 | +1.66 | +0.72 | +1.44 | +1.22 | +1.06 | +2.01 | 76 | +0.94 | +1.22 | -0.02 |
| `V4_TAKER_SHARE20|H5` | V | 0.095 | +0.83 | +1.66 | +0.67 | +1.34 | +0.13 | -0.13 | -0.25 | 52 | +0.78 | +0.11 | -0.04 |
| `H002_RET|H20` | H | 0.071 | +0.74 | +1.48 | +0.49 | +0.99 | +0.65 | +0.24 | +0.45 | 30 | +0.66 | +0.59 | -0.02 |
| `V4_TAKER_SHARE20|H20` | V | 0.051 | +0.71 | +1.41 | +0.61 | +1.22 | +0.46 | +0.30 | +0.56 | 74 | +0.72 | +0.46 | -0.03 |
| `X5_IDIO60|H20` | X | 0.044 | +0.70 | +1.41 | +0.63 | +1.26 | +1.15 | +1.05 | +1.99 | 99 | +0.72 | +1.16 | -0.03 |
| `H001_RET|H20` | H | 0.071 | +0.69 | +1.39 | +0.40 | +0.79 | +0.91 | +0.41 | +0.77 | 23 | +0.89 | +0.85 | -0.02 |
| `V2_DVOL_GROWTH|H5` | V | 0.163 | +0.69 | +1.38 | +0.46 | +0.92 | +0.27 | -0.06 | -0.12 | 30 | +0.75 | +0.31 | -0.00 |
| `H001_RET|H5` | H | 0.268 | +0.67 | +1.35 | +0.11 | +0.21 | -0.43 | -1.33 | -2.51 | 12 | +1.22 | -0.50 | -0.03 |
| `H060_RET|H5` | H | 0.082 | +0.66 | +1.33 | +0.56 | +1.11 | +1.28 | +1.13 | +2.15 | 62 | +0.72 | +1.34 | -0.02 |
| `V2_DVOL_GROWTH|H20` | V | 0.066 | +0.64 | +1.28 | +0.51 | +1.02 | -0.14 | -0.33 | -0.62 | 49 | +0.59 | -0.05 | +0.00 |
| `H014_RET|H1` | H | 0.339 | +0.63 | +1.26 | +0.28 | +0.55 | -0.32 | -0.84 | -1.60 | 18 | +0.62 | -0.24 | -0.06 |
| `X3_BLEND_7_30_90|H1` | X | 0.306 | +0.61 | +1.23 | +0.21 | +0.41 | -0.29 | -0.85 | -1.61 | 15 | +0.53 | -0.67 | -0.00 |
| `H060_RET|H1` | H | 0.164 | +0.58 | +1.17 | +0.39 | +0.78 | +1.11 | +0.83 | +1.58 | 30 | +0.45 | +1.15 | -0.01 |
| `X5_IDIO60|H1` | X | 0.162 | +0.57 | +1.15 | +0.37 | +0.74 | +1.03 | +0.74 | +1.40 | 29 | +0.58 | +1.01 | -0.02 |
| `H060_RET|H20` | H | 0.045 | +0.55 | +1.11 | +0.49 | +0.98 | +1.24 | +1.15 | +2.17 | 84 | +0.57 | +1.25 | -0.04 |
| `H014_RET|H20` | H | 0.073 | +0.50 | +0.99 | +0.37 | +0.75 | +0.37 | +0.18 | +0.35 | 41 | +0.44 | +0.31 | -0.02 |
| `H003_RET|H1` | H | 0.702 | +0.49 | +0.98 | -0.23 | -0.45 | -0.62 | -1.78 | -3.37 | 7 | +1.47 | -0.51 | -0.07 |
| `H014_RET|H5` | H | 0.170 | +0.47 | +0.94 | +0.27 | +0.55 | -0.17 | -0.49 | -0.92 | 24 | +0.37 | -0.23 | -0.05 |
| `H005_RET|H5` | H | 0.267 | +0.47 | +0.93 | +0.11 | +0.23 | -0.28 | -0.84 | -1.59 | 13 | -0.00 | -0.33 | -0.04 |
| `X4_VOLADJ60|H20` | X | 0.045 | +0.46 | +0.91 | +0.38 | +0.76 | +0.94 | +0.84 | +1.60 | 60 | +0.46 | +0.95 | -0.03 |
| `H003_RET|H20` | H | 0.072 | +0.43 | +0.87 | +0.22 | +0.44 | +0.44 | +0.09 | +0.17 | 20 | +0.34 | +0.38 | -0.02 |
| `X3_BLEND_7_30_90|H20` | X | 0.051 | +0.41 | +0.82 | +0.31 | +0.63 | -0.68 | -0.81 | -1.54 | 43 | +0.39 | -0.70 | +0.02 |
| `H005_RET|H20` | H | 0.072 | +0.40 | +0.81 | +0.23 | +0.46 | +0.55 | +0.26 | +0.50 | 23 | +0.32 | +0.59 | -0.03 |
| `X3_BLEND_7_30_90|H5` | X | 0.144 | +0.39 | +0.78 | +0.18 | +0.36 | -0.77 | -1.06 | -2.01 | 18 | +0.23 | -0.87 | +0.01 |
| `H090_RET|H1` | H | 0.135 | +0.39 | +0.78 | +0.21 | +0.42 | +1.08 | +0.84 | +1.58 | 22 | +0.23 | +1.19 | -0.03 |
| `H007_RET|H20` | H | 0.072 | +0.39 | +0.77 | +0.23 | +0.46 | +0.44 | +0.19 | +0.36 | 25 | +0.41 | +0.45 | -0.03 |
| `S4_SKEW60|H20` | S | 0.045 | +0.37 | +0.75 | +0.29 | +0.58 | +1.73 | +1.61 | +3.05 | 44 | +0.42 | +1.81 | -0.04 |
| `X1_SKIP30_7|H20` | X | 0.068 | +0.37 | +0.74 | +0.26 | +0.53 | +0.96 | +0.80 | +1.52 | 35 | +0.40 | +1.09 | -0.03 |
| `X6_CONSIST60|H1` | X | 0.208 | +0.36 | +0.73 | +0.06 | +0.12 | +1.19 | +0.77 | +1.45 | 12 | +0.65 | +0.99 | -0.01 |
| `V3_TICKET|H20` | V | 0.037 | +0.33 | +0.65 | +0.26 | +0.52 | -3.02 | -3.10 | -5.87 | 49 | +0.28 | -3.03 | +0.10 |
| `H090_RET|H5` | H | 0.068 | +0.32 | +0.63 | +0.22 | +0.45 | +1.35 | +1.22 | +2.30 | 34 | +0.36 | +1.40 | -0.04 |
| `X4_VOLADJ60|H5` | X | 0.087 | +0.31 | +0.62 | +0.18 | +0.36 | +1.03 | +0.86 | +1.63 | 24 | +0.42 | +1.15 | -0.02 |
| `H007_RET|H1` | H | 0.464 | +0.30 | +0.60 | -0.18 | -0.36 | -0.33 | -1.09 | -2.06 | 6 | +0.56 | -0.49 | -0.06 |
| `X6_CONSIST60|H5` | X | 0.096 | +0.29 | +0.57 | +0.13 | +0.26 | +1.04 | +0.82 | +1.55 | 19 | +0.23 | +0.86 | -0.01 |
| `S5_DOWNRATIO60|H5` | S | 0.084 | +0.28 | +0.56 | +0.17 | +0.34 | +1.67 | +1.51 | +2.85 | 25 | +0.44 | +1.87 | -0.04 |
| `S5_DOWNRATIO60|H1` | S | 0.150 | +0.26 | +0.52 | +0.07 | +0.15 | +1.22 | +0.96 | +1.81 | 14 | +0.15 | +1.56 | -0.03 |
| `V1_ADV_LEVEL|H1` | V | 0.119 | +0.26 | +0.51 | +0.05 | +0.11 | -2.06 | -2.37 | -4.48 | 13 | -0.07 | -1.97 | +0.06 |
| `S4_SKEW60|H5` | S | 0.078 | +0.26 | +0.51 | +0.13 | +0.26 | +1.36 | +1.19 | +2.25 | 21 | +0.39 | +1.51 | -0.04 |
| `H030_RET|H20` | H | 0.062 | +0.24 | +0.49 | +0.16 | +0.31 | +0.84 | +0.70 | +1.33 | 27 | +0.31 | +0.96 | -0.02 |
| `X2_SKIP90_14|H1` | X | 0.150 | +0.23 | +0.46 | +0.02 | +0.05 | +1.20 | +0.92 | +1.74 | 11 | +0.13 | +1.22 | -0.03 |
| `H180_RET|H5` | H | 0.053 | +0.21 | +0.42 | +0.13 | +0.25 | +1.25 | +1.14 | +2.15 | 25 | +0.25 | +1.22 | -0.05 |
| `X6_CONSIST60|H20` | X | 0.047 | +0.20 | +0.41 | +0.12 | +0.24 | +1.39 | +1.26 | +2.39 | 24 | +0.21 | +1.35 | -0.01 |
| `H180_RET|H1` | H | 0.104 | +0.19 | +0.38 | +0.04 | +0.07 | +1.18 | +0.97 | +1.84 | 12 | +0.12 | +1.03 | -0.05 |
| `S5_DOWNRATIO60|H20` | S | 0.046 | +0.19 | +0.38 | +0.12 | +0.24 | +1.96 | +1.85 | +3.50 | 27 | +0.21 | +2.00 | -0.05 |
| `H180_RET|H20` | H | 0.028 | +0.18 | +0.37 | +0.13 | +0.27 | +0.99 | +0.93 | +1.76 | 37 | +0.18 | +0.99 | -0.05 |
| `H030_RET|H1` | H | 0.240 | +0.18 | +0.36 | -0.07 | -0.15 | -0.06 | -0.42 | -0.79 | 7 | +0.10 | -0.32 | -0.02 |
| `S4_SKEW60|H1` | S | 0.131 | +0.16 | +0.33 | -0.03 | -0.06 | +0.96 | +0.71 | +1.34 | 9 | +0.12 | +1.30 | -0.04 |
| `X2_SKIP90_14|H5` | X | 0.075 | +0.13 | +0.26 | +0.02 | +0.04 | -1.39 | -1.55 | -2.94 | 12 | +0.17 | -1.28 | +0.04 |
| `H090_RET|H20` | H | 0.037 | +0.12 | +0.24 | +0.06 | +0.13 | +1.35 | +1.27 | +2.41 | 21 | +0.12 | +1.40 | -0.05 |
| `X1_SKIP30_7|H5` | X | 0.134 | +0.12 | +0.24 | -0.05 | -0.09 | +0.31 | +0.07 | +0.14 | 7 | +0.18 | +0.58 | +0.01 |
| `X1_SKIP30_7|H1` | X | 0.266 | +0.11 | +0.22 | -0.19 | -0.38 | -0.22 | -0.64 | -1.21 | 4 | +0.19 | -0.04 | +0.02 |
| `X2_SKIP90_14|H20` | X | 0.041 | +0.08 | +0.17 | +0.02 | +0.04 | +1.35 | +1.25 | +2.37 | 13 | +0.10 | +1.29 | -0.05 |
| `V3_TICKET|H1` | V | 0.090 | +0.05 | +0.10 | -0.08 | -0.17 | +3.21 | +3.05 | +5.78 | 4 | +0.05 | +3.25 | -0.11 |
| `H007_RET|H5` | H | 0.232 | +0.04 | +0.08 | -0.25 | -0.50 | -0.29 | -0.74 | -1.40 | 1 | -0.10 | -0.37 | -0.04 |
| `X4_VOLADJ60|H1` | X | 0.174 | +0.03 | +0.06 | -0.21 | -0.41 | +0.97 | +0.66 | +1.25 | 1 | +0.04 | +0.83 | -0.02 |
| `V3_TICKET|H5` | V | 0.061 | +0.02 | +0.04 | -0.08 | -0.15 | -3.18 | -3.29 | -6.23 | 2 | +0.01 | -3.19 | +0.11 |
| `V1_ADV_LEVEL|H20` | V | 0.039 | +0.02 | +0.03 | -0.07 | -0.13 | -2.06 | -2.18 | -4.13 | 2 | +0.00 | -2.10 | +0.06 |
| `H030_RET|H5` | H | 0.121 | +0.01 | +0.02 | -0.13 | -0.25 | +0.34 | +0.14 | +0.27 | 1 | +0.18 | +0.54 | +0.01 |
| `H002_RET|H1` | H | 0.873 | +0.01 | +0.02 | -0.94 | -1.88 | +0.48 | -0.95 | -1.80 | 0 | -1.11 | +0.94 | +0.06 |
| `V1_ADV_LEVEL|H5` | V | 0.075 | +0.00 | +0.01 | -0.14 | -0.28 | -1.76 | -1.97 | -3.73 | 0 | -0.09 | -1.69 | +0.06 |

**Family key** — **H** (30 tests) pure trailing-return horizon ranking at 1/2/3/5/7/14/30/60/90/180
days. **X** (18) momentum refinements: 30-day-skip-7, 90-day-skip-14, a 7/30/90 rank-z blend,
60-day vol-adjusted, 60-day BTC-beta-residual, 60-day up-day fraction. **V** (15) volume/activity:
ADV level, 5d-vs-60d dollar-volume growth, 20d mean ticket size, 20d taker-buy share, 30d-vs-90d
volume trend. **S** (18) volatility/shape: 30d realised vol, 60d vol-of-vol, 20d max daily return
(lottery), 60d skew, 60d downside-vol ratio, 30d Amihud illiquidity.

**Family verdicts, on the held-out window:**

| family | tests | median design gross | median **held-out net** | verdict |
|---|---:|---:|---:|---|
| **H** pure return horizons | 30 | +0.47 | **+0.18** | **noise** — cross-sectional crypto momentum and reversal do not exist net of 10 bp |
| **V** volume / activity | 15 | +0.69 | **−0.13** | **noise** |
| **X** momentum refinements | 18 | +0.36 | +0.80 | weak, none clears the design bar |
| **S** volatility / shape | 18 | +1.13 | **+2.47** | **survives** |

The one line to keep from the H family: `H001_RET|H1` (plain one-day cross-sectional reversal) has a
design **gross** of +1.11 on a break-even of **8.5 bp/side** and a design **net** of **−0.20**. That
replicates D0821's cost wall exactly, on a different execution price and a different universe.

---

## 6. THE SURVIVOR, AND EVERY WAY I TRIED TO BREAK IT

**`S1_VOL30|H20`** — each day rank the ~50-name universe by 30-day realised volatility (VWAP
returns); hold long the 10 lowest and short the 10 highest, equal weight, dollar-neutral, in 20
overlapping daily tranches.

| | design 2019–2022 | held out 2023–2026 |
|---|---:|---:|
| gross Sharpe (t) | **+2.02** (4.04) | **+2.92** (5.53) |
| net Sharpe @10 bp (t) | **+1.95** (3.91) | **+2.85** (5.39) |
| net @20 bp shock | +1.89 | +2.77 |
| annualised net return / vol | 48.8 % / 25.0 % | 64.5 % / 22.6 % |
| turnover Σ&#124;Δw&#124;/day | 0.044 | 0.047 |
| break-even | **314 bp/side** | **390 bp/side** |
| one-extra-day LAG1 gross | +2.01 | +2.96 |
| skew / kurtosis | −0.02 / 8.0 | +0.02 / 4.6 |
| worst day / max drawdown | −778 bp / 1.63 ann-vol units | −530 bp / 0.79 ann-vol units |

Net Sharpe by calendar year: **2019 1.72 · 2020 1.83 · 2021 1.79 · 2022 2.75 · 2023 1.39 ·
2024 1.77 · 2025 3.60 · 2026 5.86**. 69 of 92 months positive. Minimum rolling-1-year net Sharpe
over the whole sample: **+0.08** — never negative.

| attack | design | held out | reading |
|---|---:|---:|---|
| vol from **close** returns instead of VWAP | 1.89 / 1.83 | 3.12 / 3.04 | not a VWAP artefact |
| vol from **Parkinson high/low range** | 1.92 / 1.86 | 3.15 / 3.08 | not a return-estimator artefact |
| lookback 10 / 60 / 120 d | 2.02 / 1.71 / 1.50 | 2.42 / 2.91 / 2.68 | flat in the lookback |
| extremes k = 5 / 10 / 15 | 2.15 / 2.14 / 1.49 | — | flat until the extremes stop being extreme |
| universe top-30 / 50 / 80 / 120 | 1.89 / 2.14 / 2.91 / 2.82 | — | **stronger** in a wider universe |
| rank-weight all 50 names | 1.93 | 2.66 | not an extremes artefact |
| **vol residualised on the 30-day return** | **2.50** | **2.87** | **not short-horizon reversal in disguise — it is stronger** |
| vol residualised on log ADV | 2.04 | — | not a size sort |
| pure ADV (size) sort, same book | **−0.26** | — | the size sort by itself is worthless |
| exclude BTC / BTC+ETH / top-10 majors | 1.85 / 1.73 / 1.34 | — | not a majors bet, but weakens |
| listing age ≥ 90 / 180 / 365 d | 1.62 / 1.24 / 1.13 | 2.53 / 2.57 / 2.16 | new listings help in design, not needed |
| drop the "tradable tomorrow" universe condition | 1.95 | 2.85 | **no lookahead in the universe** |
| short-leg P&L from names in their final 30 days of data | 9.7 % | **2.1 %** | **not a delisting artefact** |
| inverse-vol-weighted (risk-balanced) legs | 1.79 | 1.62 | weakens — the P&L lives in the high-vol leg's notional |
| ADV floor \$5M / \$25M / \$100M (net) | 1.96 / 1.26 / 0.95 | 2.82 / 2.16 / 0.96 | survives \$25M; **halves at \$100M** |
| design beta to the equal-weight universe | −0.10 (halves: −0.07, −0.11) | — | stable, small, not a market bet |

---

## 7. WHAT IT ACTUALLY IS — AND THE WALL

Decompose the book into its two legs at full notional, annualised:

| leg | design | held out |
|---|---:|---:|
| long the 10 lowest-vol coins | +47.8 %/yr | **+11.7 %/yr** |
| short the 10 highest-vol coins | +53.0 %/yr | **+120.7 %/yr** |
| equal-weight universe (reference) | +11.2 %/yr | **−39.9 %/yr** |

And the decisive structural test:

| variant | design net | held-out net |
|---|---:|---:|
| long low-vol basket, **short BTC** | +0.11 | **−1.26** |
| **short high-vol basket, long BTC** *(chosen after seeing this — an observation, not evidence)* | +1.54 | +3.00 |

> **This is not a cross-sectional premium. It is short alt-bleed carry.** The long low-vol leg
> contributes nothing you could not get from BTC; the whole object is that **small, high-realised-
> volatility Binance-spot alts lose money at an extraordinary and persistent rate**. That is a real,
> eight-years-consistent, tail-controlled phenomenon — and it means the trade cannot be run without
> **borrowing small alts**.

Borrow charged on the 0.50 short notional:

| borrow | design net | held-out net |
|---|---:|---:|
| 0 bp/day | +1.95 | +2.85 |
| 2 bp/day (7 %/yr) | +1.83 | +2.69 |
| 5 bp/day (18 %/yr) | +1.63 | +2.45 |
| 10 bp/day (37 %/yr) | +1.31 | +2.04 |
| 20 bp/day (73 %/yr) | +0.67 | +1.24 |

At a \$25M ADV floor and 10 bp/day borrow the held-out net is still **+1.52**. So the trade does not
die on any *plausible* borrow number — **it dies on not having the number at all**. Lesson 7 in its
exact form: **free data prices a statistic, not a claim.** The claim here is "you can borrow these
20 names, at this rate, in this size, every day for eight years." Binance publishes an hourly margin
interest curve and a per-asset borrow limit; neither is in the kline archive, neither is in this
cache, and the tail names in the short leg are precisely the ones whose borrow gets suspended in the
weeks the trade earns most. **A short-side book whose availability is unmeasured is not a book.**

Capacity is the second wall: 20 equal-weighted names at a \$1M ADV floor, and the edge halves at a
\$100M floor. This is a small-single-digit-\$M strategy at best.

---

## 8. VERDICT

**0 promotions. 1 forward-log leg.**

1. **The theme's headline question — is there a real cross-sectional crypto momentum/reversal
   premium OOS net of 10 bp? — is answered NO.** Thirty pure-horizon tests from 1 to 180 days at
   three holds have a median held-out **net** Sharpe of **+0.18**; volume sorts are **−0.13**. The
   one-day reversal effect is measurable and **8.5 bp/side wide** against a 10 bp fee. This is the
   D0821 cost wall re-measured on VWAP execution with 1/10th the turnover, and it does not move.
2. **It is all bounce? No — and that answer needed a correction to the method.** ρ1 on coin returns
   is −0.04, nowhere near the −0.35 gate: bid-ask bounce cannot dominate a series with 500 bp/day
   volatility. **ρ1 is a spread diagnostic, not a returns diagnostic.** The artefact that *does*
   threaten this theme is the mirror one — **time-averaged (VWAP) prices manufacture fake momentum,
   ρ1 = +0.19** — and both are neutralised by the one-day gap, which the self-test shows is worth
   the difference between a fake Sharpe of **+36.7** and a true one of **−0.32**.
3. **One factor survives everything: cross-sectional realised volatility.** Design net +1.95,
   held-out net +2.85, break-even 314–390 bp/side against a 10 bp fee, positive in eight of eight
   years, skew ≈ 0, minimum rolling-1y Sharpe +0.08, orthogonal to past return and to size, robust
   to the vol estimator, the lookback, the universe width and the weighting. It clears the analytic
   sign-agnostic bar, the programme-cumulative bar, and a size-matched placebo at 0/400.
4. **And it is not what it looks like.** Long low-vol versus short BTC is **−1.26 held out**. The
   premium is one-sided: it is the short leg, and therefore it is a **borrow trade**, priced by a
   number free daily klines do not contain.
5. **Honest non-originality.** `S1_VOL30` is the crypto low-volatility / lottery (MAX) anomaly — a
   published effect, not an invention. The owner's standing instruction is to invent, not to
   replicate; this is recorded as a **found factor**. Worse, the programme already had two unfollowed
   hints of it: D0821's `D4_XS_AMIHUD` (held-out +1.39, t 2.64) and `C4_XS_BAB` (held-out +0.79),
   both rejected on their design windows. The new information is not the factor, it is that the
   factor is **entirely short-side** and therefore **borrow-walled**.

**Recorded as a forward-log leg, not promoted:** `S1_VOL30|H20`, frozen exactly as specified in §6,
**conditional on a measured Binance alt borrow-rate-and-availability curve**. Until that curve
exists this is a statistic, not a strategy. If it is ever collected, the natural implementation is
**short via USD-M alt perpetuals** (where the cost is funding, historically a tailwind for shorts on
high-vol alts) rather than spot margin — which is a different instrument and would need its own round.

**Do not re-propose:** cross-sectional trailing-return ranking on crypto spot at any horizon from 1
to 180 days, at any hold, on any of close/open/VWAP execution; cross-sectional dollar-volume growth,
ticket size, taker-buy share, ADV level and volume trend; and the long side of the low-volatility sort.

---

## 9. HONEST DISCLOSURES

* **N = 81 primary tests** (27 signals × 3 holds); all 81 are in §5, none dropped or
  re-parameterised after scoring. Roughly **40 further P&L objects** were scored in §6–§7 as
  robustness attacks on an already-selected formula (estimator, lookback, k, universe width,
  exclusions, orthogonalisations, age filters, liquidity floors, weightings, borrow, leg
  decompositions). Those are *after-the-fact looks*, they are all reported, and none of them is
  counted in the null — which is why the null is quoted on the 81 and the survivor is quoted
  against the p99 of the max, not the p50.
* **Held-out calendar reuse.** 2023-01 → 2026-08 has now been read by D0821 crypto-spot, by rounds 2
  and 3 on perps, and by this round. The design-window result was frozen to `..._DESIGN.json`
  before the held-out window was opened, and stands on its own; the held-out number is a third pass
  over that calendar.
* **`short high-vol vs long BTC` (design 1.54 / held out 3.00) was constructed after seeing the leg
  decomposition.** It is held-out mining and is recorded as an observation only.
* **Short-side financing is quoted as free everywhere except §7.** Every net number in §5 and §6 is
  therefore optimistic by the borrow cost.
* **The universe's early years are thin.** 2019 has ~30–40 qualifying pairs; cross-sectional
  statistics from 2019–2020 are noisier than the day count suggests.
* **VWAP is `quote_volume / base_volume` from the kline**, i.e. the day's true volume-weighted
  traded price, validated to lie inside the day's high/low. Executing at it requires a VWAP/TWAP
  algo running the full UTC day; a book with 0.047/day turnover can do that, a daily-rebalance book
  at 1.3 turnover could not.
