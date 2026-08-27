# Original-strategy shortlist — crypto perpetual microstructure

**What this is.** Eighteen self-invented (not replicated) strategy theories were generated across six
microstructure lenses on crypto perpetual futures, then each was run through an adversarial gauntlet
that scored it on four axes: tail-boundedness, statistical power on free data, honest cost, and
crowding/speed. This document keeps only what survived, ranks it, and writes a freeze-then-test design
for the top two.

**Status.** Synthesis judgement plus a first-party endpoint audit (§7). Every power number below is
recomputed here from the gauntlet's *measured* inputs, not from the proposing theory's assumed ones —
several theories were killed precisely because their assumed σ was 2–5× off the measured σ.

**Why this exercise exists.** `FINDINGS.md` §5d records 0-for-8 on published directional equity edges
and crypto carry dead four independent ways. §5h names the reason: replications are crowded, and daily
equity data at ~1 obs/day over a 4.6-year free window cannot resolve any Sharpe below ~1.3 while every
candidate sat below 0.5. The brief for this round inverted both axes — original theory, high-frequency
instruments — and the results below should be read as a test of whether that inversion actually helps.
**It does, but only barely: 3 of 18 survived, and the failure modes were the same ones.**

---

## 1. Headline

**Three of eighteen theories survived the gauntlet.** Two are worth a test window.

Fifteen died, and the honest observation is that they died of the *same three diseases* as the equity
programme, not of anything new:

| cause of death | count | the §5d analogue |
|---|---|---|
| **cost** — gross edge quoted against a friction estimate taken on the wrong instrument | 8 | the ORB / T10 death |
| **power / event count** — the world does not supply enough events, knowable by counting before building | 4 | T9, T15, T23, T25 |
| **crowding or latency** — the tradeable object is folklore executed by thousands of bots, or requires winning a queue | 3 | the 0-for-8 replication death |

**The one genuinely new thing high-frequency crypto buys is real and worth stating precisely.** It is
not "more power for free" — `(2.80/S_annual)²` years is frequency-invariant, and one gauntlet correctly
caught a theory claiming otherwise. What thousands of observations per day actually buy is (a) a
**higher annual Sharpe for the same per-trade edge**, and (b) **resolution in compute time rather than
calendar time**, because the archive already holds the observations. Both surviving picks resolve
against data that exists today. Neither requires forward collection. That is the single structural
advantage over the equity programme, and it is why 3 survived instead of 0.

**The one genuinely new hazard** is that crypto friction is *state-dependent in the same state the
signal fires*. Eight of the thirteen kills charged a calm-market half-spread to a strategy whose entry
is, by construction, at the widest-spread instant the instrument has. `FINDINGS.md` §5d's "friction is
the binding constraint" now needs a rider: **in crypto, friction is the binding constraint AND it is
correlated with the signal.** A cost model measured on the unconditional distribution is not a cost
model for these strategies.

---

## 2. Gauntlet tally — all eighteen

`PROMISING` = survives. `WEAK` and `KILL` are both out, per the synthesis rule.

| # | lens | theory | verdict | what decided it |
|---|---|---|---|---|
| A1 | funding/basis micro | Dead-Band Release (clamp-conditional basis reversion) | KILL | 26.8 bp honest friction vs 18–25 bp own best-case gross; hedge leg (perp basket) does not hedge the traded object (perp-vs-spot basis) |
| A2 | funding/basis micro | Post-Settlement Re-entry Rebound | **WEAK** | power passes (3.4 mo) but the tradeable object is the most-botted trade on the venue; equilibrium competitor is a 2 bp maker, you are a 5 bp taker |
| A3 | funding/basis micro | Funding-Clock Desynchronisation (Binance vs Hyperliquid) | KILL | charges 19 bp where this repo's own T25 froze 24.1 bp for the identical four legs; 34.5 bp size-aware; needs 3 months of forward recording to measure a known-negative number |
| **B1** | liquidation/OI | **Orphan Flush** (reversal on OI *destruction*) | **PROMISING** | absorbs a 2.4× error in its own key input and still passes power; archive holds 9× the requirement |
| B2 | liquidation/OI | The Leverage Shelf (reconstructed trigger map, trade exhaustion) | KILL | 20.5 mo to resolve; five compounding inferences, two of which the data provably cannot make (taker ratio does not identify side; VWAP error ≈ detent spacing) |
| B3 | liquidation/OI | Fragility-ranked cascade book | KILL | 41–103 bp friction vs 25–40 bp gross, on the thinnest-book decile *by construction* at the most stressed instant *by construction*; `marketTakeBound` measured 76% degenerate |
| C1 | order book | Lean-in vs Flight (passive response signs aggressive flow) | **WEAK** | measured gross +3.22 bp against an 11.7–20 bp friction floor — the author's own pre-declared kill line fired |
| C2 | order book | Forced-flow reversion gated on the 2-second refill | KILL | no liquidation archive exists → 13–15 months of forward collection; measured median prize ≈ 11 bp ≈ one round trip; most contested trade in the asset class |
| C3 | order book | The refill budget (hidden working-order supply) | KILL | Leg A is short-gamma at maker fees behind a professional queue; Leg B — its own declared tail hedge — is an ORB clone this repo already buried, and B22B measured that shape's stop slippage at p90 233 bp |
| D1 | lead-lag | Inverse-vs-Linear Convexity Dislocation (COIN-M vs USD-M) | KILL | p99 dev on ordinary days (2.71/4.50 bp) is *below* the 6 bp all-maker floor; the edge exists ~4 hours per year → 93 months to resolve |
| D2 | lead-lag | OI Signs the Follower's Convergence | **PROMISING** | survives, ranked 3rd — see §4 |
| D3 | lead-lag | The Oracle Is a Lagged Copy (Hyperliquid oraclePx) | KILL | the deviation harvested *is* the half-spread — measured 7.86 bp p50 dev against 21.45 bp p50 impact spread on the same names; scissors with no escape |
| E1 | reflexivity | Liquidation-Map Oracle Snapback | KILL | 492 live snapshots, **zero** crossings of its own 25 bp threshold; 3.15 yr of history says 0.077 crossings/day → 47 months; the 60 s sweep is rate-limit-impossible by 7–28× |
| E2 | reflexivity | OI-Signed Round-Number Break | KILL | 1:1 payoff at 35 bp against 12 bp friction needs a 67.1% hit rate; theory hypothesises 60%. Dead by 7pp on its own arithmetic, before data. Power was excellent — which is what makes the kill unambiguous |
| **E3** | reflexivity | **Coiled Leverage Expansion** | **PROMISING** | only long-gamma survivor; best cost-to-edge ratio; 1.2–3.0 months |
| F1 | session/calendar | Funding-Settlement Flow Release | KILL | measured on 364 settlements across two disjoint windows: **−2.56 bp**, hypothesis +12 to +30 bp excluded at ~11.8 se, and the mechanism is falsified *in sign* |
| F2 | session/calendar | Unmanned-Hours Impact Premium | KILL | short-horizon reversal in liquid alt perps is the most competed systematic strategy in crypto; the paired control leg loses money at every point of its own stated range |
| F3 | session/calendar | Deribit 08:00 UTC Settlement Release | KILL | the conditioning variable is not backtestable (expired-instrument OI is not free); the physically credible version fires 12–16×/year → 59 months |

**Three lenses returned zero survivors** (funding/basis micro-dynamics, order-book microstructure,
session/calendar). That is informative: the two most obviously "high-frequency" lenses — the ones
closest to market-making — returned nothing, because that is where the professional population lives.
All three survivors sit at the **5-minute** timescale: below where discretionary traders act, above
where HFT competes, and — decisively for two of them — **at the exact grid Binance publishes
open-interest and positioning data on**, which is a structural reason the niche is thin rather than a
hope that it is.

---

## 3. The survivors, and what each survived on

### 3.1 Orphan Flush — reversal conditioned on open-interest DESTRUCTION, not on return

*Buy the wick only when open interest was destroyed (involuntary, price-insensitive flow), never when
it was created (voluntary, informed flow), and only after the destruction rate has decayed to 0.25× its
peak — i.e. after the forced seller is finished, not while they are still selling.*

**Survived because:** the gauntlet measured the power denominator instead of accepting it, found the
60-minute conditional forward-return sd was **218 bp against the 90 bp assumed — a 2.4× error against
the theory** — cut obs/day from 25 to 12, and it *still* resolves in 4.9 months. Nothing else in this
programme has absorbed a 2.4× error in its own key input and survived. T9, T15, T23, T25 all failed
power by 2–7×.

**Mechanism plausibility is the highest of the three,** and this matters more than the arithmetic.
Liquidity concession to price-insensitive forced flow is the most robustly documented inefficiency
class in any market, and perp liquidation is *mechanically* forced — the venue's engine sells at market
irrespective of price. This is not a behavioural conjecture. What is original is the *discriminator*:
Δ open-interest separates the forced seller from the informed one, and no published work uses it that
way.

**Cost is the binding constraint and is correctly identified as such** — 20–50 bp all-in against a
hypothesised 30–50 bp gross. Unlike ORB, gross is 3–5× the fee component and the whole fight is with
spread, which is *measurable from the archive* rather than assumed.

**Mandatory correction carried into §5:** the declared primary estimand (paired flush-minus-control)
is **not** the tradeable estimand and must be demoted. The theory's own thesis says OI-*creating* bars
continue — so a large positive paired difference is exactly what you observe even if flushes never
revert and the control leg merely trends. This is `FINDINGS.md` §5h in a new costume: T10 returned
permutation p = 0.0020 on a series whose own t was +0.47, because a sorted book answers "is this
partition special?" and not "is the mean positive?".

### 3.2 Coiled Leverage Expansion — positioning divergence × compressed-leverage fragility

*When open interest has built while realised volatility compressed (leverage coiled), and the top-trader
positioning ratio diverges from the all-accounts ratio (the informed and the crowd are on opposite
sides), take the expansion with-trend in the informed direction, with a 1-ATR stop and a 6-hour clock.*

**Survived because** it is the only long-gamma candidate in the entire eighteen. Every other survivor
and near-survivor is short-gamma — sells the move, buys the fade — and the brief's honest-tail bar
exists precisely to catch that. Here the worst single trade is a gapped stop, the tail is cumulative and
arithmetic (15–20 consecutive stops for −9 to −12%) rather than a hidden left tail, and the failure mode
is *stated in the rule* (never widen the stop, never re-enter inside the cooldown) rather than
discovered afterwards.

**Best cost-to-edge ratio of any candidate:** ~12 bp all-in against a risk unit (1-hour ATR) measured
today at 44–86 bp on the alt tier — 14–22% of one R, versus 100%+ for most of the corpses.

**Fastest resolution:** 3.0 months at the gauntlet's own harsher 20× correlation deflation, against
2,177 days of free 5-minute archive = ~24× the requirement.

**Mandatory correction carried into §6:** the "3:1 payoff, break-even 25%" claim **is false as
specified**. A ratcheting 1-ATR trailing stop and a 3:1 payoff are mutually exclusive — a winner that
reaches +2R and retraces one ATR exits at +1R. Realised mean win is nearer +1.3 to +1.8R, moving
break-even to roughly 38–43%, which *straddles* the hypothesised 33–38% hit rate. **This single number
decides the candidate and it has not been measured.** It is gate 0 in §6.

### 3.3 OI Signs the Follower's Convergence — ranked third, NOT picked

*BTC leads alts at 5-minute horizon; whether the alt's lag closes (reversion) or widens (continuation)
is signed by whether the alt's open interest rose or fell over the same bar.*

**Survived the gauntlet** on bounded tail (−1.0 to −1.8% of equity in the worst measured 15 minutes),
on a real structural moat (Binance publishes `sum_open_interest` only on a 5-minute grid, so the signal
is *uncomputable* faster than 5 minutes — below HFT, above discretionary), and on 71 months of already-
archived data.

**Not picked, for three reasons, and I want to be explicit that this is a judgement rather than a
verdict reversal:**

1. **The net is under 2% of the gross.** At 90 portfolio observations/day, an annual Sharpe of 1.5
   corresponds to **+0.24 bp net per name-trade**, against a measured 13–17 bp round trip. The cost
   model *is* the strategy; a 1 bp error in it flips the sign. Conversely the theory's claimed +3 to
   +8 bp net implies an annual Sharpe of 19–50, which does not exist in any market — so either the
   hypothesised edge is overstated by an order of magnitude or the residuals are far more correlated
   than a cross-sectional book implies. Neither reading is good.
2. **The bounce confound can produce the entire predicted effect.** `klines` close is a *last-trade*
   price. An OI-down bar is by construction a one-sided forced-liquidation bar that closes at the bid,
   on which the spread widens 10–50×. Mechanical bid-ask bounce alone produces "reversion" in exactly
   the bucket the theory selects, and it is unharvestable because you must cross to enter.
3. **It consumes 42 of the 71 available months** at Sharpe 1.5, leaving a 29-month design window, and
   **fails outright at Sharpe 1.0** (needs 94 months, 71 exist). It is the only survivor whose split is
   tight.

**What to do with it instead — and this is not a consolation prize.** Its confound test is *the same
afternoon's work* as Pick 1's blocking control (§5, gate C), because both require recomputing returns
from `markPriceKlines` instead of `klines`. Run that once, for both. If mark-price returns kill the
OI-signed reversion, Pick 1 learns something it needed to know anyway; if they do not, this candidate
is promoted to the next test window with a measured rather than assumed cost model. **Cost: zero
incremental — it rides on Pick 1's data build.**

---

## 4. Ranking

Scored 1–5 on the four axes the brief specified. These are judgements, but each is anchored to a
measured number from §2–3 rather than to the proposing theory's own claim.

| | **originality** | **inefficiency is real** | **resolvable on free data in months** | **bounded tail** | **total** |
|---|---|---|---|---|---|
| **1. Orphan Flush** | 4 — Δ OI as a forced/voluntary discriminator, plus decay-rate entry timing, is unpublished; "buy the wick" is folk but the conditioning is not | **5** — forced-flow liquidity concession, and the forcing is *mechanical* (the venue's engine), not behavioural | **5** — 4.9 mo central / 16.5 pessimistic; archive holds **9×** the requirement, so this is compute time not calendar time | 4 — bounded by construction (one lot, 60-min clock, ≤5 concurrent); correlated −5 to −10% is a bad day, not ruin | **18** |
| **2. Coiled Leverage Expansion** | 4 — top-trader-minus-crowd as a *signed direction* × OI-z compression; no equity analogue at any price | 3 — positioning-squeeze reflexivity is real but more diffuse than forced flow; inputs are retail-visible (Coinglass mirrors both series) | **5** — 3.0 mo at a harsh 20× deflation; ~24× archive coverage | **5** — the only **long-gamma** survivor; no hidden short-vol; drawdown tail is arithmetic and stated up front | **17** |
| 3. OI Signs the Follower | 3 — base signal is the most populated niche in crypto; the OI conditioner is the whole claim | 2 — the bid-ask bounce confound can produce the entire effect in exactly the selected bucket | 2 — needs 42 of 71 available months; **fails outright at Sharpe 1.0**; net is <2% of gross | 4 — bounded, −1.0 to −1.8% worst 15 min | **11** |

**Picks 1 and 2, and they should be run together rather than sequentially.** Three reasons:

- **They share one data build.** Both need the same 5-minute `metrics` + `klines` panel from
  `data.binance.vision` over the same universe. §7 prices that build at ~2.5 hours of downloads and
  ~4 GB. Running the second candidate after the first costs the *analysis*, not the data.
- **Their tails are opposite in sign.** Pick 1 is short-gamma (buys the fade of forced flow) and loses
  in a multi-stage cascade. Pick 2 is long-gamma (takes the expansion with-trend) and *wins* in exactly
  that regime while bleeding in the chop where Pick 1 works. That is a genuine portfolio property, not
  a rationalisation — but it must be *verified*, not assumed: §6 gate 4 requires the realised
  correlation of the two return streams on the shared design window to be reported, and a measured
  correlation above +0.3 removes this argument entirely.
- **They fail differently, so the round is informative either way.** Pick 1 dying on cost and Pick 2
  dying on hit rate are different lessons; two candidates dying of the same disease is one lesson paid
  for twice.

---

## 5. PICK 1 — Orphan Flush: freeze-then-test design

### 5.1 Instrument and venue

- **Instrument:** Binance USD-M **USDT-margined perpetual futures**, 5-minute bars.
- **Universe:** point-in-time, trailing-only, survivorship-complete. Top 80 symbols by trailing-30-day
  quote volume as of each month-start, with ≥ 60 days of listed history. Verified survivorship-complete
  (§7): `LUNAUSDT` and `FTTUSDT` serve 2022-05-10 and 404 today; `ARBUSDT`/`OPUSDT`/`INJUSDT`/`LDOUSDT`
  404 in 2022 because they were not yet listed. **This is the property T23 found T21 was missing — 31.2%
  of the names its rule selected no longer trade.**
- **Exclusions, applied point-in-time:** any symbol within 7 days of a listing, a delisting
  announcement, or a leverage-tier change.

### 5.2 Free data — exact endpoints, all no-auth

All from `https://data.binance.vision/data/futures/um/`. Verified live this session (HTTP 206 on ranged
GET):

| what | path | granularity | earliest verified | size |
|---|---|---|---|---|
| open interest + positioning | `daily/metrics/{SYM}/{SYM}-metrics-{YYYY-MM-DD}.zip` | **5-min, 288 rows/day** | **2020-09-01** | 11.6 KB/day |
| price bars | `monthly/klines/{SYM}/5m/{SYM}-5m-{YYYY-MM}.zip` | 5-min | 2020-09-01 | 368 KB/month |
| **mark** price bars (bounce control) | `daily/markPriceKlines/{SYM}/5m/…zip` | 5-min | 2020-09-01 | ~12 KB/day |
| book depth (q denominator) | `daily/bookDepth/{SYM}/{SYM}-bookDepth-{YYYY-MM-DD}.zip` | ~2,879 snaps/day, ±1–5% bands | **2023-01-01** | 563 KB/day |

`metrics` columns, confirmed by download: `create_time, symbol, sum_open_interest,
sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
count_long_short_ratio, sum_taker_long_short_vol_ratio`.

**Three fetch facts that change the build plan and were verified rather than assumed:**

1. **`metrics` and `bookDepth` have NO monthly archives** (404 on `monthly/metrics/…` and
   `monthly/bookDepth/…`; `monthly/klines/…` returns 206). The metrics panel is therefore
   80 symbols × 2,177 days ≈ **174,000 individual daily requests**. At a polite 20 req/s that is
   ~2.5 hours. Klines come from 5,760 monthly files in minutes.
2. **`bookDepth` starts 2023-01-01, not 2020-09.** Bisected in an earlier pass: 2022-12-01 → 404,
   2023-01-01 → 200. Every depth-conditioned statistic is computed on 3.6 years that **exclude LUNA
   (2022-05), 3AC/Celsius (2022-06) and FTX (2022-11)** — precisely the three events this strategy
   names as its worst case. **The backtest structurally cannot see its own fat tail.** This is why
   gate D below is blocking.
3. **The tightest depth band is ±1%, not ±0.2%.** The file has exactly ten levels
   (−5,−4,−3,−2,−1,1,2,3,4,5). The depth denominator is therefore systematically *generous* for a thin
   name, and the slippage model inherits that optimism. Charge spread from `bookTicker` quotes where
   available, never from ±1% depth.

**Per-symbol network etiquette:** run the build as a detached background subprocess, never inside an
agent turn (`MEMORY.md`: no network crawls in agents — request-timeout wall).

### 5.3 Signal, frozen before any return is computed

For symbol *i*, 5-minute bar *t*:

- `oi_value(i,t)` = `sum_open_interest_value` at bar close.
- `dOI(i,t) = oi_value(i,t) − oi_value(i,t−1)` — **destruction** when negative.
- `r_resid(i,t)` = the bar's log return minus `β(i) ×` BTCUSDT's log return, with `β(i)` fitted on a
  **trailing 30-day** window of 5-minute returns, refit monthly, **no forward data**.
- `z(i,t)` = `r_resid(i,t)` standardised by a trailing 30-day residual sd.
- `q(i,t)` = `|dOI(i,t)| ÷` (trailing-24h median ±1% book notional). Depth-free fallback for the
  pre-2023 tail check: `|dOI(i,t)| ÷` trailing-24h quote volume.

**FLUSH event** (the treated leg) fires at bar *t* when all four hold:

1. `z(i,t) ≤ −2.5` (a down-shock in BTC-neutralised residual space);
2. `dOI(i,t) < 0` — **open interest was destroyed**, the involuntary-flow discriminator;
3. `q(i,t) ≥` its own trailing-30-day 90th percentile — the destruction is large relative to the book
   that had to absorb it;
4. the destruction rate has **decayed to ≤ 0.25× its peak** over the last 3 bars — the forced seller is
   finished, not still selling.

**CONTROL event** (mechanism leg only, never the tradeable estimand): identical on 1 and 3, but
`dOI(i,t) > 0` — open interest was *created*.

**Entry** at the **open of bar t+1** (never at bar *t*'s close — no same-bar fill). **Exit** at the
earlier of 60 minutes or a resting exchange-side reduce-only stop. Long only on the down-shock side; the
short-side mirror is a *separate declared trial* and must be counted in the DSR trial count.

**Anti-lookahead, declared before the harness (the T3/T10 rule).** `metrics` files are published with a
latency this design has not yet measured. **Blocking pre-step, ~1 hour:** poll the live
`/futures/data/openInterestHist` REST endpoint at 10-second intervals for 24 hours and measure the wall-
clock lag between a 5-minute bar's close and the availability of its OI print. **If that lag exceeds
60 seconds, the entry moves from bar t+1's open to bar t+2's open and the whole design is re-powered
before anything else runs.** T3 found a nine-minute lookahead worth more than half its result; T10 found
a ten-minute one worth *minus* half of its. Assume neither sign.

### 5.4 Estimand and observation unit

**Primary estimand (tradeable, and this is the mandated correction):** the **standalone** mean
BTC-neutralised 60-minute forward return of the FLUSH leg, **net of charged friction**.

**NOT** the paired flush-minus-control difference. That difference is contaminated by construction: the
theory's own thesis says OI-creating bars *continue*, so a large positive paired difference appears even
if flushes never revert and the control leg merely trends. The paired difference is demoted to a
**mechanism check** (gate B), reported with the ratio of the real book's dispersion to the permutation
null's beside any p-value (`FINDINGS.md` §5h).

**Observation unit: the FLUSH CLUSTER, not the symbol-event.** Alt residuals stay correlated within a
sector cluster even after BTC-beta neutralisation, and a cascade fires many names inside one bar.
Cluster = all flush events sharing a 5-minute timestamp, aggregated to one equal-weighted return. This
is the T15 estimator rule: count what the estimator actually compares.

**Realistic obs/day: 12 clusters.** (The proposing theory claimed 25. The gauntlet cut it to 12 on the
grounds that the tradeable universe is 80–250 names, not the 700 claimed — 527 USDT perps are TRADING
today, measured live — and that within-cluster correlation collapses simultaneous events.)

### 5.5 Power calculation, explicit

Inputs, **measured** (2024-03, BTC-neutralised residuals, 5-min bars) rather than assumed:

- 60-minute forward return sd **conditional on a |z| ≥ 2.5 shock**: ARB 196 bp, OP 266, LDO 174,
  INJ 238 → mean **218 bp**. (The theory assumed 90 bp. It was wrong by 2.4× *against itself*.)
- Cluster-level sd after equal-weighting ~3 names at residual correlation ~0.5: **σ = 180 bp**.
- Hypothesised net edge after 25 bp charged friction: **μ = 12 bp**.

Two-sided α = 0.05, 80% power → `n = (2.80 σ / μ)²`:

| scenario | μ (net) | σ | n clusters | at 12/day | months |
|---|---|---|---|---|---|
| central | 12 bp | 180 bp | `(2.80 × 180 / 12)² = 42.0² =` **1,764** | 147 days | **4.9** |
| pessimistic | 8 bp | 220 bp | `(2.80 × 220 / 8)² = 77.0² =` **5,929** | 494 days | **16.5** |
| optimistic | 20 bp | 180 bp | `(2.80 × 180 / 20)² = 25.2² =` **635** | 53 days | 1.7 |

**The central case resolves in 4.9 months and the pessimistic case in 16.5. But neither is calendar
time.** The depth-conditioned archive runs 2023-01-01 → 2026-08-17 = **1,325 days × 12 = ~15,900
clusters = 9.0× the central requirement.** Months-to-resolve is therefore **compute time**: the ~2.5-hour
metrics build plus ~60 GB of bookDepth. Even the pessimistic 5,929 is covered 2.7×.

**This is the property no equity candidate in this programme ever had.** T10's arithmetic —
`(2.80/S)²` years, 4.6 available — was a *calendar* wall. Here the wall is a download.

### 5.6 Design / held-out split, frozen before any number

| window | dates | days | clusters | multiple of central n |
|---|---|---|---|---|
| **design** (all parameter choices, all diagnostics) | 2023-01-01 → 2024-12-31 | 730 | ~8,760 | 5.0× |
| **held-out** (touched exactly once) | 2025-01-01 → 2026-08-17 | 595 | ~7,140 | 4.0× |
| **tail check** (depth-free q only) | 2020-09-01 → 2022-12-31 | 852 | ~10,200 | — |

Declared trials, counted for DSR before anything runs: **6** (long-side / short-side × three q-threshold
choices {p85, p90, p95}). No other variant may be added after the freeze; any that is becomes a declared
seventh and re-inflates the deflation.

### 5.7 Cost model — honest, and state-dependent

The gauntlet's most repeated kill was charging a calm-market spread to a strategy that trades at the
widest-spread instant. Charged here:

| component | value | source |
|---|---|---|
| taker fee, VIP-0 | 5.0 bp × 2 legs = **10.0 bp** | Binance published schedule. **BNB discount NOT assumed.** |
| half-spread, calm baseline | 1.7 bp | T21 §3e first-party measurement on ≥$20M/day perps |
| **cascade multiplier** | **×3** | entry is a marketable limit at the far touch at a stress moment; exit is a market/stop. There is **no maker path on either leg** |
| half-spread charged | 5.0 bp × 2 = **10.0 bp** | |
| impact at ticket size | included in the ×3 | T25 §1 measured a 7.1× top-of-book→impact factor at ~$20k on Hyperliquid; ×3 on Binance at a smaller ticket is the conservative read, not the charitable one |
| **central charged friction** | **25 bp round trip** | |

**Sensitivity is pre-registered, not chosen afterwards.** Report net at **20 / 25 / 35 / 50 bp**. The
50 bp case is the honest cascade-moment number and the candidate must not be promoted on the 20 bp one.

Where `bookTicker` exists (2023-05 →), **replace the assumed half-spread with the measured quote at the
entry timestamp** for every event that has one, and report both. If the measured cascade half-spread
exceeds 8 bp per side at the median event, the central friction is re-frozen upward before the held-out
run.

### 5.8 Position sizing and the worst case, stated explicitly

- One lot per symbol, **ever**. No averaging down, no scaling, no re-entry inside the 60-minute clock.
- 3% of account notional per name; **≤5 concurrent**; **≤2× gross**.
- Resting **exchange-side reduce-only stop**, placed with the entry, never widened.
- Hard 60-minute time exit.

**Worst-case single trade: −0.6% to −0.9% of account.** A stop that gaps 3× through its level on a
3%-notional lot at ≤2× gross.

**Worst-case correlated event: −5% to −10% of account in one hour** — five concurrent positions all
gapping in a market-wide cascade. That is the honest number and it is a bad day, not a ruin event.

**Two failure modes that no stop bounds, stated rather than hidden:** (a) auto-deleveraging can
force-close a position at the venue's price rather than yours mid-cascade; (b) a delisting notice on a
held name is a −60% event the stop cannot execute through. The 7-day exclusion window addresses (b)
only for *announced* delistings.

**This is a short-gamma strategy and it is labelled as one.** It buys the fade of forced flow. Its
win rate is deliberately projected at 55–60%, not 90% — a projected 90% win rate on a fade strategy is
the signature of a hidden tail, which is what the brief's honest-tail bar exists to catch.

### 5.9 Pre-registered gates — numeric, frozen first, SURVIVES/DEAD

**Gate 0 — GROSS-AT-ZERO-COST CENSUS. Blocking. Costs one afternoon and no held-out window.**

Run the FLUSH leg on the **design window only**, at **zero friction**, primary estimand (standalone,
BTC-neutralised, 60-min, cluster-level).

> **DEAD if mean gross < 35 bp per cluster.** No harness is written, no held-out window is spent.

Rationale: 35 bp is the 25 bp central friction plus a margin that survives the 35 bp sensitivity. Below
it, no friction assumption rescues the candidate and the remaining work is wasted. This is the
`FINDINGS.md` §5j process rule — power/friction census before a line of harness.

**Gate A — PRIMARY. Blocking. Held-out window, touched once.**

> **SURVIVES only if** mean standalone FLUSH-leg return **net of 25 bp ≥ +10 bp per cluster**
> **AND** `t ≥ 2.80` on cluster-level observations **AND** the point estimate remains **> 0 at 35 bp**
> charged friction.
>
> **DEAD** if any of the three fails.

**Gate B — MECHANISM. Reported, non-blocking, but its absence is disqualifying.**

Paired FLUSH-minus-CONTROL difference, reported **with** the ratio of the real book's cross-sectional
dispersion to the label-permutation null's. **A ratio far from 1 means the p-value is not about the
mean** (§5h). A large paired difference with a failing gate A is reported as *"the partition is special
and the trade does not pay"* — which is T10's finding, and it is a finding, not a rescue.

**Gate C — BOUNCE CONTROL. Blocking.**

Recompute the entire primary estimand from **`markPriceKlines`** instead of `klines`. A flush bar is by
construction a one-sided forced-selling bar that closes **at the bid**, on which the spread widens
10–50×; mechanical bid-ask bounce alone can manufacture the full 60-minute "reversion" in exactly the
selected bucket, and it is unharvestable because you must cross to enter.

> **DEAD if the sign does not survive on mark prices, or if the mark-price point estimate is less than
> 60% of the last-trade one.**

This control also answers rank-3 (§3.3) at zero incremental cost. Run it once, report both.

**Gate D — TAIL CHECK ON THE UNSEEN CRISES. Blocking.**

Depth-free `q` (`|dOI| ÷` trailing-24h quote volume) over **2020-09-01 → 2022-12-31** — the LUNA / 3AC /
FTX window `bookDepth` cannot see. `metrics` genuinely reaches 2020-09 and is survivorship-complete
(verified §7).

> **DEAD if the maximum cluster-level drawdown in that window exceeds −25% of book** at the frozen
> sizing, regardless of the mean in gates A–C.

A strategy whose backtest cannot see its own worst regime has not been backtested.

---

## 6. PICK 2 — Coiled Leverage Expansion: freeze-then-test design

### 6.1 Instrument, venue, universe

- **Instrument:** Binance USD-M USDT perpetuals, 5-minute bars, 6-hour holds.
- **Universe:** point-in-time top-80 by trailing-30-day quote volume, **restricted to the ATR tier**:
  trailing-30-day median 1-hour ATR **≥ 45 bp**. This is a *pre-registered universe constraint*, not a
  discovered one, and it matters: measured today, median 1-hour ATR is BTC 29.1 bp, ETH 40.0, DOGE 43.8,
  SOL 44.4, SUI 54.8, AVAX 61.9, LINK 65.4, APT 68.1, INJ 86.4. **Against ~12 bp all-in friction, BTC
  and ETH contribute approximately zero expectancy** — the round trip is 41% of one risk unit on BTC and
  14–22% on the alt tier. The proposing theory's census was run on 12 *majors*, i.e. **not on the
  population that will actually trade**. That error is corrected here before anything runs.
- Same point-in-time listing/delisting/leverage-change exclusions as Pick 1.

### 6.2 Free data — identical build to Pick 1

`daily/metrics/{SYM}/…` (5-min, 288 rows/day, from 2020-09-01) for `sum_open_interest_value`,
`sum_toptrader_long_short_ratio` and `count_long_short_ratio`; `monthly/klines/{SYM}/5m/…` for prices and
ATR. **Zero incremental data cost over Pick 1** — this is the whole efficiency argument for running the
two together. `bookDepth` is **not** required (this candidate does not use a depth denominator), so
Pick 2 can run on the ~4 GB metrics+klines panel alone, without Pick 1's ~60 GB depth build.

### 6.3 Signal, frozen before any return is computed

For symbol *i*, 5-minute bar *t*:

- **Positioning divergence:**
  `D(i,t) = log(sum_toptrader_long_short_ratio) − log(count_long_short_ratio)`.
  The first series is position-weighted among large accounts; the second is a headcount across all
  accounts. `D > 0` = the large accounts are longer than the crowd; `D < 0` = the crowd is longer than
  the large accounts. **This is the entire original content of the candidate.**
- **Coil state:** `C(i,t)` = z-score of `sum_open_interest_value` over a trailing 24 h, **divided by**
  the z-score of trailing 24 h realised 5-minute volatility. High `C` = open interest built while
  volatility compressed = leverage coiled.
- **Trigger:** `C(i,t)` in its own trailing-30-day **top decile**, `|D(i,t)|` in its own trailing-30-day
  **top decile**, and the bar's range breaks the trailing 12-bar high (long) or low (short) **in the
  direction of `sign(D)`**.

**Entry** at the open of bar *t+1*, **with-trend, in the direction the large accounts are positioned**.
**Stop:** resting exchange-side stop-market at 1 × trailing 1-hour ATR, ratcheting up behind the trade,
**never widened**. **Exit:** stop, or a hard **6-hour** time exit. **One entry per coin per 6 hours.**
**≤20 concurrent positions.** No re-entry inside the cooldown — this is written into the rule, not left
to discipline.

Same blocking OI-publication-latency pre-step as §5.3. It is one measurement serving both picks.

### 6.4 Estimand and observation unit

**Estimand:** mean net return per trade, expressed in **R-units** where `R = 1 × ATR at entry`, net of
12 bp charged friction, **on the ATR ≥ 45 bp tier only**.

**Observation unit: the TRADE**, with the standard error deflated **×20** for cross-coin simultaneity.
The gauntlet's reasoning for ×20 rather than the theory's ×8 is correct and load-bearing: the coil state
is **market-wide** — everything compresses together and everything expands together — so the ≤20-coin
concurrency cap binds hardest at exactly the moments the signal fires. The effective independent unit is
closer to the *expansion episode* than to the trade.

**Realistic obs/day: 23 trades** across the 80-name ATR-screened universe.

### 6.5 Power calculation, explicit

- Per-trade sd: **σ = 110 bp** (R ≈ 90–110 bp on the ATR-screened tier).
- Hypothesised net edge: **μ = +30 bp** central.
- `n_raw = (2.80 × 110 / 30)² = 10.27² = 105` trades.
- **× 20 simultaneity deflation = 2,100 trades.**
- At 23 trades/day → **91 days = 3.0 months.**

| scenario | μ (net) | σ | n_raw | ×20 | at 23/day | months |
|---|---|---|---|---|---|---|
| central | 30 bp | 110 bp | 105 | 2,100 | 91 days | **3.0** |
| pessimistic | 18 bp | 130 bp | 409 | 8,180 | 356 days | **11.7** |
| optimistic | 40 bp | 110 bp | 59 | 1,180 | 51 days | 1.7 |

**The pessimistic case is 11.7 months — inside the 12-month bar, but only just.** State that plainly
rather than quoting the central case alone.

**Archive coverage:** 2020-09-01 → 2026-08-17 = **2,177 days × 23 = ~50,000 trades = 24×** the central
requirement, **6.1×** the pessimistic one. Again compute time, not calendar time.

### 6.6 Design / held-out split, frozen before any number

| window | dates | days | trades | multiple of central n (2,100) |
|---|---|---|---|---|
| **design** | 2020-09-01 → 2023-12-31 | 1,217 | ~28,000 | 13.3× |
| **held-out** (touched once) | 2024-01-01 → 2026-08-17 | 960 | ~22,000 | 10.5× |

Declared trials before the freeze: **4** (long/short × two coil-decile choices {top 10%, top 20%}).

### 6.7 Cost model

| component | value | source |
|---|---|---|
| taker fee, VIP-0 | 5.0 bp × 2 = **10.0 bp** | published schedule; BNB discount not assumed |
| full spread, measured live | BTC 0.015 bp, ETH 0.048, SOL/SUI/LINK/AVAX/DOGE/ARB/OP 1.0–1.5, APT 1.85, INJ 2.27 | live top-of-book, this session's gauntlet |
| spread charged | **~1.5 bp round trip** | mid of the alt tier |
| stop-market slippage | **charged separately, from B22B's measured distribution** — p90 **233 bp**, p95 **420 bp** on the stop-order shape | `research/B22B_SLIPPAGE_RESULT.json` |
| **central charged friction** | **12 bp + the measured stop-slippage distribution on exits that stop out** | |

**The stop-slippage charge is not optional and it is what killed a sibling candidate** (C3's Leg B).
This design's exit is a resting stop-market, which is structurally the instrument B22B measured. Model
losing exits by **sampling from B22B's empirical slippage distribution**, not by assuming the stop fills
at its level. Report net with and without that charge; **promote only on the with-charge number.**

At 12 bp against a risk unit of 60–90 bp on the ATR tier, friction is **13–20% of one R** — the best
ratio of any candidate in the eighteen, and the reason this survives where E2 (1:1 payoff, needed a
67.1% hit rate, hypothesised 60%) did not.

### 6.8 Sizing and the worst case, stated explicitly

- **0.6% of equity risked per trade at 1R.** ≤20 concurrent. No averaging, no scaling, no stop-widening,
  no re-entry inside 6 h.
- **Worst single trade: −1.5% to −2.5% of position notional** (a two-sided liquidity sweep gapping the
  stop in a thin second) → **−0.9% to −1.5% of equity** at the frozen sizing.
- **Worst cumulative case, and it is arithmetic rather than hypothetical: 15–20 consecutive stops for
  −9% to −12% of equity.** At a 35% hit rate the probability of 12 straight losers somewhere in an
  850-trade sample is roughly 4%. **Sizing is chosen so that 20 straight stops costs ≤12% of equity.**

**This is a long-gamma strategy and that is the point.** It takes the expansion rather than selling it,
so there is no hidden short-vol blow-up: the loss distribution is a large number of small stops with a
right-tail of winners. It is the structural counterweight to Pick 1, which is short-gamma. The named
failure mode is **behavioural, not statistical** — widening the stop or re-entering inside the cooldown
— and it is forbidden in the rule rather than discouraged in prose.

### 6.9 Pre-registered gates — numeric, frozen first, SURVIVES/DEAD

**Gate 0 — THE REALISED R-MULTIPLE DISTRIBUTION. Blocking. This is the number that decides the
candidate, and it has never been measured.**

On the **design window only**, with the ratcheting 1-ATR trail in place, measure:

- `W` = realised mean **win** in R-units. (The theory asserts 3.0. A ratcheting trail and a 3:1 payoff
  are **mutually exclusive** — a winner reaching +2R and retracing one ATR exits at +1R. Expect
  **W ≈ 1.3–1.8**.)
- `L` = realised mean **loss** in R-units, including B22B stop slippage. (Expect **L ≈ 1.1–1.3**, not
  1.0.)
- Break-even hit rate `p* = L / (W + L)` **plus** the friction term `12 bp / (R × (W+L))`.

> **DEAD if the measured design-window hit rate is below `p* + 3pp`.** No held-out window is spent.

The theory hypothesises a 33–38% hit rate. If `W = 1.5, L = 1.2`, then `p* = 44.4%` before friction —
**above the entire hypothesised band, and the candidate is dead on arithmetic alone.** If `W = 1.8,
L = 1.1`, `p* = 37.9%` — inside the band and alive. **The whole candidate turns on a quantity nobody has
computed.** Compute it first. Keep the trail (`FINDINGS.md` §5: trailing beats fixed for right-tail
assets) and **re-derive the break-even; never quote 3:1**.

**Gate 1 — PRIMARY. Blocking. Held-out window, touched once.**

> **SURVIVES only if** mean net return per trade **≥ +18 bp** (the pessimistic-case edge) **AND**
> `t ≥ 2.80` **after the ×20 simultaneity deflation of the standard error** **AND** the number is
> computed **with** the B22B stop-slippage charge applied.
>
> **DEAD** if any fails.

**Gate 2 — FILTER-OFF CONTROL ARM. Blocking, and this is the originality test.**

Run an identical arm with the `D`-divergence gate **removed** (coil state and breakout only).

> **DEAD if the treated arm does not beat the control arm by ≥ 12 bp per trade with `t ≥ 2.0` on the
> paired difference.**

Rationale, and it is the most important gate in this document: **the positioning divergence IS the
entire original content.** Strip it and what remains is a volatility-compression breakout — i.e. plain
intraday momentum, which **B22E already killed at zero cost** and which this programme is 0-for-8 on. If
the control arm matches the treated arm, the candidate has collapsed into a dead family and must be
reported dead **regardless of gate 1**. A profitable control arm is not a second edge; it is evidence
that the first one does not exist.

**Gate 3 — POWER CENSUS ON THE ESTIMATOR. Blocking, runs before a line of harness.**

Count actual triggers on the design window **with the ≤20-coin cap applied and on the ATR ≥ 45 bp tier**.

> **DEAD if the realised trigger rate implies > 12 months to 80% power** at the pessimistic μ = 18 bp,
> σ = 130 bp and the ×20 deflation.

The 23/day figure was **extrapolated from a 12-major census to a 60–80 coin universe the census never
touched**, and the ATR tier that pays is not the tier that was censused. That is the T15 scoping error
(wrong by 9.8×) in a new costume. Count first.

**Gate 4 — PORTFOLIO INDEPENDENCE FROM PICK 1. Reported, blocking only on the joint claim.**

Report the realised correlation of Pick 1's and Pick 2's daily return streams on the shared design
window.

> **A measured correlation above +0.3 removes the "opposite tails" argument in §4** and the two must
> then be judged, and sized, as one candidate rather than two.

---

## 7. First-party endpoint audit — measured this session, not cited

Every row probed live. `MEMORY.md` rule: citing is not measuring.

| check | result |
|---|---|
| `metrics` earliest — `BTCUSDT-metrics-2020-09-01.zip` | **HTTP 206** ✓ |
| `metrics` latest — `BTCUSDT-metrics-2026-08-17.zip` | **206** ✓ |
| `metrics` grid | **288 distinct 5-min timestamps/day**, 00:00 → 23:55, downloaded and counted ✓ |
| `metrics` columns | `create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio` — **every field both picks need** ✓ |
| 5m `klines` 2020-09-01 and 2026-08-17 | **206 / 206** ✓ |
| `markPriceKlines` 5m (bounce control) | **206** ✓ |
| `bookDepth` 2023-01-01 | **206**; 2022-12-01 → **404**. Depth panel is 3.6 yr, **excludes LUNA/3AC/FTX** ⚠ |
| **monthly** archives | `monthly/klines/…` **206**; `monthly/metrics/…` **404**; `monthly/bookDepth/…` **404** → metrics is a **~174,000-request daily-only build** ⚠ |
| **survivorship completeness** | `LUNAUSDT` and `FTTUSDT`: **206** on 2022-05-10, **404** today. `ARBUSDT`/`OPUSDT`/`INJUSDT`/`LDOUSDT`: **404** on 2022-05-10 (not yet listed), **206** today. **Point-in-time correct in both directions** ✓ |
| live universe (`fapi/v1/exchangeInfo`) | **527** USDT perpetuals with status TRADING (several theories assumed ~700) |
| file sizes | metrics 11.6 KB/day, klines-5m 12.2 KB/day (368 KB/month), bookDepth **563 KB/day** |

**Build cost, honest.** Pick 2 alone (metrics + klines, 80 symbols × 2,177 days): ~174,000 requests,
~4 GB, ~2.5 h at 20 req/s. Pick 1 adds bookDepth from 2023-01-01 (80 × 1,325 × 563 KB): **~60 GB** and
another ~1.5 h. **Gate 0 of Pick 1 and gates 0/3 of Pick 2 need no bookDepth at all** — sequence the
build so that ~2.5 hours of downloads can kill either candidate before the 60 GB is fetched.

---

## 8. Salvage — free measurements worth taking from the corpses

Each is an afternoon, none burns a held-out window, and several are directly useful to the two picks.

1. **The bounce control, run once for three candidates.** `markPriceKlines` vs `klines` on the OI-down
   bucket. It is Pick 1's gate C, it is rank-3's decisive test, and it prices a hazard that applies to
   *any* future strategy entering right after a one-sided bar. **Highest value-per-hour item in this
   document.**
2. **Fragility → destruction regression** (from B3). Regress realised ΔOI on ex-ante
   `Φ = OI × retail-share ÷ ±1% depth` over ~10M symbol-bars. If fragility predicts destruction
   amplitude it becomes a **name-selection input for Pick 1's universe screen**. Zero multiple-testing
   exposure; either outcome is informative.
3. **The funding cross-section tie-break trap — record in `FINDINGS.md` §8 immediately.** The *realised*
   funding cross-section is **degenerate**: a median of only 25 distinct values among 60 names, because
   a large plurality sit at exactly the 0.01%/8h interest baseline, which is *also the top of the
   distribution*. Sorting `(funding, return)` tuples silently drops the tie-break onto the **return**
   field and **fabricated +39.8 bp at t = +12.5 with an 80.9% win rate**, rising to +63.3 bp / t +15.4 /
   93.4% win at top-and-bottom decile. Deterministic tie-break on symbol name: the entire effect
   vanishes to −2.09 bp. **Any funding-ranked book must sort on the continuous premium-index
   reconstruction and must fix the tie-break off the outcome field.** This is a T3/T10-shaped
   implementation-audit finding and is worth more than most of the theories that produced it.
4. **`marketTakeBound` is 76% degenerate** — 402 of 527 TRADING USDT perps sit at 0.15, no 0.03 exists
   anywhere. Any design treating it as a cross-sectional ranking variable is using near-constant data.
   Record it so it is not rediscovered.
5. **The placebo construction from A3.** On an 8h-funding symbol, 21 of 24 hours contain a Hyperliquid
   settlement and no Binance settlement — a null measurable at ~60× the precision of the effect. It is a
   **null-measurement technique, not a trade**; bolt it onto any future settlement-timing census.
6. **`metaAndAssetCtxs`** returns `midPx, oraclePx, markPx, funding, openInterest, dayNtlVlm,
   impactPxs` for 177 names in **one unauthenticated call** — the cheapest live cross-venue liquidity
   and venue-risk monitor available to this programme. Useful for kill-switch logic; **not a signal**.

---

## 9. Method rules this round adds

Candidates for `FINDINGS.md` §8.

- **In crypto, friction is not merely the binding constraint — it is correlated with the signal.** Eight
  of thirteen kills charged a calm-market half-spread to a strategy whose entry is by construction at the
  widest-spread instant. **A cost model measured on the unconditional distribution is not a cost model
  for an event-conditioned strategy.** Charge the conditional spread or do not charge one at all.
- **High frequency does not create power; it creates a higher Sharpe for the same per-trade edge, and it
  converts calendar time into compute time.** `(2.80/S_annual)²` years is frequency-invariant. One
  theory claimed "resolves in weeks" from obs/day alone and was wrong in kind. The real benefit — an
  archive that already holds 9–24× the required observations — is large, and it is a *different* benefit.
- **A hedge must hedge the object you are trading.** A1 hedged a perp-vs-*spot* basis with a basket of
  other *perps*, leaving 30 bp of signal inside 80 bp of unhedged idiosyncratic move. Name the P&L
  identity before naming the hedge.
- **A stop declared in one dimension does not bound a loss that lives in another.** A1's "120 bp stop"
  was in premium space while its P&L was in price space. **State the stop in the units of the loss.**
- **When a strategy's declared tail hedge is itself a dead strategy, the tail is unhedged.** C3's Leg B
  was an ORB clone; B22B measures that shape's stop slippage at p90 233 bp. Check the hedge against the
  ledger before crediting it.
- **A filter-off control arm is the originality test, and it should be mandatory for any candidate whose
  novelty is a conditioner.** If the arm with the novel conditioner removed performs the same, the
  candidate has collapsed into whatever family the base signal belongs to — and for this programme that
  family is usually already dead. Pick 2's gate 2 is the template.
- **Count the events before building the harness — now confirmed on a sixth and seventh candidate.**
  E1 asserted 20 obs/day and the live poll returned **zero threshold crossings in 492 snapshots**; F3's
  physically credible version fires 12–16×/year against a 59-event requirement. §5j's rule keeps paying.
