# THE EXECUTION-COST WALL — can a cheaper rail revive the cost-killed signals?

**Date:** 2026-08-21 · **Scope:** research only, no orders, no money, cached/free data only.
**Re-run harness:** `newterr_xseq_sweep` engine driven by
`scratchpad/exec_wall_rerun.py` (reversal family × 3 universes × 3 horizons × 2 lags × 3 flat
costs, design 2016–2021 / held-out 2022-08). Cost facts from `scripts/trading_bot/costs.py`,
`M0_AUCTION_FILLS.{md,json}`, `B22B_SLIPPAGE_RESULT.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

**Yes, a cheaper rail flips the SIGN of the persistent equity reversal from net-negative to
net-positive out of sample — and no, that does not produce a fundable signal, because the
constraint was never really the spread.** The one signal that persisted cleanly (`FR_REV1` h=5,
factor-neutral 5-day reversal) breaks even at **5.13 bp/side**, and its held-out gross Sharpe is
**+0.86 at t = 1.85**. On the M0-measured auction rail (≈0 spread) or at the Dyhrberg liquid-taker
half-spread (2.5 bp) its net goes to **≈ +0.8 / +0.4 SR** — positive, confirmed on cached data. But
**t = 1.85 is the *frictionless* number, and it already sits below the round's design bar of
2.98 (pooled 3.28) *before a single basis point of cost is charged.*** Execution cost turned a
sub-bar-positive signal into a sub-bar-negative one; the levers un-do that, recovering a sub-bar-
positive sleeve identical in status to `BETA_INSTAB`. No lever — not even a hypothetical perfect
maker fill that *earns* the spread (ceiling t ≈ 2.75) — lifts it to the promotion bar. **The wall
these signals die at is the multiple-testing significance bar, not the spread.** For crypto spot the
answer is cleaner still: the fast signals' held-out *gross* Sharpe is ≈ 0, so a maker rebate to zero
fee revives nothing. **Stop re-testing the daily equity/crypto cross-section for a cost fix; the cost
was the messenger.**

---

## 1. What each dead signal is actually charged, and where that number comes from

| rail / population | half-spread per side | provenance | round-trip |
|---|---|---|---|
| Equity xs-sweep default (universe-mean, Corwin-Schultz shape anchored) | **5.0 bp** + 0.5 fee | anchored to a "$20M+ ADV" mean; conservative | ~11 bp |
| Equity retail continuous **taker**, liquid name | **2.5 bp** | Dyhrberg/Shkilko/Werner JFE 168 (2025): 49 bp effective − 44% price-improvement → 2.4, rounded up | 5.0 bp |
| Equity **auction rail** (MOO/MOC), ADV rank ≤ 1500 | **0 bp** + a ~0.002 bp non-fill provision | **MEASURED** (M0: official print on 99.96% of top-500 symbol-days, median $37M close / $4.8M open) | ~0 bp |
| Crypto spot **taker**, Binance base tier | **10 bp** | published schedule (0.10%) | 20 bp |

The sweep's 5.0 bp is **2× the liquid-taker number**, and the auction rail is a *measured* zero for
the liquid tiers. So the break-even of a persistent signal can sit *above* the real liquid cost and
still *below* the sweep's charge — which is exactly the FR_REV1 case, and the reason this
investigation was worth running rather than assuming.

My re-run's own cost model reports its charged half-spread as **5.02 bp** (full universe), **4.61 bp**
(top-500), **4.22 bp** (top-100) — i.e. restricting to liquid names barely lowers *this* model's
charged spread, because it anchors the cross-sectional shape to a 5 bp mean. The real liquid-name
spread (Dyhrberg 2.5 bp) is charged as the flat `liquid(2.5)` column below.

---

## 2. The signal the whole question rests on

`FR_REV1` h=5 — full multi-factor-residual 5-day reversal — is the only cell in 216 that *fully
persisted* out of sample (design gross SR 0.89 → held-out 0.86). From
`INVENT_D0821_xsfactor_HOLDOUT.json`, held-out (n=1158, 4.6 y):

| quantity | value |
|---|---|
| gross Sharpe | **+0.861** |
| **gross t** | **+1.846** |
| break-even one-way cost | **5.133 bp** ( = gross 1.708 bp/day ÷ turnover 0.333/day ) |
| net Sharpe at the shaped ~5 bp + fee | **−0.287** (t −0.62) |
| net Sharpe at flat 5 bp | −0.092 |
| **design bar (within-theme t)** | **2.977** — pooled **3.28** |

Because net_bps = gross_bps − cost × turnover is exact and linear, net at any half-spread `c` is a
straight line from the frictionless ceiling to zero at 5.13 bp:

| rail | one-way cost (bp) | **net SR** | net t |
|---|---|---|---|
| frictionless ceiling (gross) | 0.0 | **+0.86** | +1.85 |
| **auction rail** (0 spread + 0.5 fee) | 0.5 | **+0.78** | +1.67 |
| **liquid taker** (2.5 + 0.5 fee) | 3.0 | **+0.36** | +0.77 |
| flat 5 bp | 5.0 | −0.09 | −0.20 |
| sweep default (shaped ~5 + 0.5) | ~5.5 | −0.29 | −0.62 |

**The decisive line is the top one.** At *zero cost* the signal is t 1.85, already **0.62× the design
bar**. Every lever below can only move net along this line toward the +0.86 ceiling. The ceiling is
sub-bar. This is not a cost wall; it is a signal that is too small to certify, wearing a cost wall's
clothes.

---

## 3. Per-lever verdicts

### Lever 1 — LIMIT / PASSIVE (maker) execution — **cannot be settled on free data; and bounded out anyway**

A short-horizon reversal is a liquidity-*providing* trade: it buys yesterday's losers and sells
yesterday's winners, which is the side a resting limit order wants to be on. In principle a maker
fill flips the half-spread from a −2.5 bp *cost* to a +2.5 bp *capture* — a 5 bp/side swing.

Two things kill this as a rescue:

1. **Adverse selection on the fill, unmeasurable here.** For a reversal, the orders that *don't*
   fill are precisely the correct predictions — the losers that bounced away before your bid was hit
   — while the orders that *do* fill are the continuations that kept falling into your resting bid.
   The filled subset is adversely selected against the signal. FORMULA_SWEEP_MASTER §6 records the
   same wall on the intraday-RV theme verbatim: *"only the maker side is untested and this data
   cannot backtest it."* No cached free data (no order book, no live fills) can estimate the fill
   probability or its selection bias. This is an **estimate, not a measurement**, and the honest
   estimate is that adverse selection claws back most of the capture.
2. **Even the theoretical maximum is sub-bar.** Grant the impossible — a 100% maker fill that *earns*
   2.5 bp/side with zero adverse selection. Then net_bps = 1.708 + 2.5 × 0.333 = 2.54 → **SR +1.28,
   t +2.75**, *still below the 2.98 bar*, and that is the ceiling of a fantasy. Realistic maker
   execution lands far under it.

**Verdict: no revival, and the lever is capped below the promotion bar by arithmetic before any fill
model is even needed.**

### Lever 2 — LIQUID SUB-UNIVERSE (top-100 / top-500 ADV) — **does not lift the gross alpha; re-run**

Re-run of the reversal family restricted to the top-100 and top-500 names by trailing $ADV, held-out
gross Sharpe (h=5):

| signal | full | top-500 | top-100 |
|---|---|---|---|
| REV1 h=5 gross SR | +1.10 (t 2.36) | +1.07 (t 2.29) | +1.17 (t 2.50) |
| REV1_RESID h=5 gross SR | +0.77 (t 1.66) | +0.74 (t 1.58) | +0.71 (t 1.53) |
| REV5_STD h=5 gross SR | +0.78 (t 1.67) | +0.64 (t 1.36) | +0.56 (t 1.20) |

Restricting the universe **does not strengthen the reversal** — the gross Sharpe and t are flat to
slightly weaker on top-100. The only thing a liquid cut buys is a lower *spread*, and it buys that
only if you believe the top-100 half-spread is materially below 5 bp (it is — Dyhrberg says 2.5). So
lever 2 collapses into lever 1/3: it is the *spread* assumption, not the *universe*, that moves net.
On this model's own shaped spread (4.22 bp for top-100) the h=5 reversal is still ≈ break-even.

**Verdict: no independent revival. It flips the sign only through the spread it implies (→ lever 3),
and it does not raise the sub-bar gross ceiling.**

### Lever 3 — AUCTION-RAIL execution (MOO/MOC, ≈0 spread) — **flips the sign; feasibility depends on where the alpha lives; still sub-bar**

M0 *measured* the auction rail at zero half-spread for ADV rank ≤ 1500. Charging the reversal book
zero (auction) vs the flat liquid 2.5 bp, held-out net Sharpe:

| signal (h=5, full) | auction (0) | liquid (2.5) | sweep (5.0) |
|---|---|---|---|
| REV1 | **+1.03** | +0.76 | +0.49 |
| REV1_RESID | +0.68 | +0.32 | −0.04 |
| REV5_STD | +0.70 | +0.46 | +0.21 |

So on the auction rail the h=5 reversal is unambiguously net-positive (+0.7 to +1.0 SR), matching the
FR_REV1 arithmetic in §2 (+0.78, t 1.67). **But three measured facts cap it:**

1. **Feasibility hinges on the signal's timing.** A close-based reversal can be executed
   **MOO at the next open** (submit after 16:00, before the 09:28 cutoff) — zero extra lag, and the
   opening auction is a measured zero-spread rail (99.96% availability, but ~7× thinner than the
   close, median $4.8M). That is the lag-0 column above. If instead you must go **MOC on day t+1**
   (a one-day lag), the re-run shows the decay is severe for the fast leg and moderate for h=5:

   | signal | lag 0 gross t | lag 1 gross t |
   |---|---|---|
   | REV1 h=1 (holdout) | +1.37 | **+0.11** (dead) |
   | REV1 h=5 (holdout) | +2.36 | +1.66 |

   The 1-day reversal — the *strongest* gross cell — is entirely destroyed by a one-day execution
   lag. Only the slower h=5 survives, and only because its hold is long relative to the lag.
   **Corollary (already in the record): for signals whose alpha lives in the last ten minutes (the
   T3 family), the auction rail is *unreachable* — the broker rejects MOC after 15:50, so the
   MOC-legal signal loses exactly the information that is the edge. FORMULA_SWEEP §8.3: "the
   MOC-legal rail is dead in all eight formulations (best net SR 0.37, t 0.89)."**

2. **The programme already built this and measured it dead on significance.** T10 (cross-sectional
   overnight tug-of-war) *is* the daily equity reversal executed on the auction rail with the full
   harness and multiple-testing accounting: held-out **+1.48 to +3.66 bp/session at t 0.47–0.58,
   DSR 0.377 — below the expected max under its own null.** My quick REV1 t 2.36 is a single raw cell
   without that accounting; T10's t ≈ 0.5 is the number that binds.

3. **The ceiling is sub-bar (§2).** Auction execution recovers the ~5 bp, taking net to the +0.86
   frictionless ceiling — t 1.85, below 2.98.

**Verdict: genuinely flips FR_REV1 h=5 from −0.29 to ≈ +0.78 net OOS (real, measured rail), and is
operationally feasible via MOO-at-next-open for a daily signal. But the revived signal is t ≈ 1.7–1.9
(and t ≈ 0.5 in the programme's careful T10 build) — a sub-bar sleeve, not a promotable leg.**

### Lever 4 — LONGER HOLD / LOWER TURNOVER — **exhausted; the reversal alpha dies before the cost does**

Extending the hold raises the break-even (turnover falls) but the reversal effect decays. Re-run,
held-out gross Sharpe on the auction rail, REV1 full:

| horizon | h=1 | h=5 | h=10 |
|---|---|---|---|
| REV1 net SR (auction) | +0.50 | **+1.03** | +0.63 |
| REV5 net SR (auction) | +0.78 | +0.59 | +0.15 |
| REV10 net SR (auction) | +0.26 | +0.13 | −0.01 |

The alpha peaks at **h=5** and is gone by h=10 — precisely where the sweep already found the best
break-even (5.13 bp). Pushing turnover lower than h=5 lands on characteristic tilts like
`BETA_INSTAB` (turnover 3.5%/day, break-even **53.6 bp** — miles above any spread) whose held-out
**gross t is 0.71**. This is the sweep's own "families with room have no signal, families with signal
have no room" wall, now confirmed dynamically: you cannot buy your way past the spread by holding
longer, because the reversal is a short-horizon effect that dies at the horizon where the cost stops
biting.

**Verdict: no revival. h=5 is already the joint optimum, and it is sub-bar.**

### Lever 5 — CRYPTO maker rebates / venue selection — **cannot revive; the OOS signal is absent, not cost-blocked**

The crypto-spot fast reversal formulas break even at **1–3 bp/side** against the 10 bp Binance taker
fee. But their held-out **gross** Sharpe is ≈ 0 to negative (`A1_XS_REV1` gross held-out −0.33,
`A6_XS_REV5` +0.31, `A2` +0.36; from `INVENT_D0821_crypto_spot_xs.md` §4). A maker rebate that took
the fee to 0 would leave a book whose *gross* OOS edge is already zero. The design-window gross that
looked tradeable does not survive to the held-out window at any fee.

- **Maker fee floor:** Binance base spot is 0.10% maker = 10 bp (no rebate); BNB discount → 7.5 bp;
  meaningful maker rebates require VIP volume tiers a retail book does not reach. There is no retail
  path from 10 bp to the 1–3 bp break-even.
- **Adverse selection** on a reversal maker fill applies here exactly as in lever 1.
- **Short-leg financing** (spot margin borrow or a perp overlay) is charged as free in these
  backtests, so every net number is already optimistic.
- The **slow** crypto formulas (break-even 22–200 bp) are *not* cost-constrained at all — they simply
  have no Sharpe (`INVENT_D0821_crypto_spot_xs.md` §6).

**Verdict: no revival. There is no crypto-spot signal that is "persistent-gross but only fee-killed";
the fast ones are signal-absent OOS and the slow ones are not cost-limited. Maker/venue is moot.**

---

## 4. The revived candidate, stated honestly

**There is a sign-revival, and it is not a basket candidate.** `FR_REV1` h=5 (and the raw `REV1` h=5
proxy) go from net −0.29 to **net +0.4 (liquid taker 2.5 bp) / +0.78 (auction rail)** SR held out —
a real, cached-data-confirmed flip driven by a *measured* cheaper rail. This corrects the framing in
INVENT_D0821_MASTER that these signals sit "exactly at the modelled half spread": they sit at the
*conservative universe-mean* spread; at the liquid or auction spread they clear it.

But the revived signal is the same object the programme already logged and declined:

- Frictionless gross **t = 1.85 < design bar 2.98** (pooled 3.28). Cost was never the binding gate.
- The careful auction-rail build of this signal class (T10) is **t ≈ 0.5, DSR 0.377**, below its own
  null's expected max.
- It is statistically indistinguishable from `BETA_INSTAB` (held-out net t 0.60, break-even 53 bp) —
  a ~0.3–0.8 Sharpe sleeve on 4.6 years, exactly the status round 3 and the D0821 round said not to
  promote.

**Guard, if it were ever logged as a zero-size sleeve (it should not be sized):** MOO-at-next-open
execution only (never MOC — the reversal is not a last-10-minute signal, but the MOC cutoff still
forces a fatal 1-day lag if used); ADV rank ≤ 500 so the auction rail's zero-spread measurement
applies; h=5 hold (h=1 dies on the execution lag, h=10 has no alpha); hard kill if held-out gross t
over any rolling 3-year window drops below 1.0. Realistic forward expectation: never certifies.

---

## 5. Definitive guidance — stop re-testing these for a cost fix

1. **The execution-cost wall is real but it is downstream of a significance wall.** For the one
   equity signal that persisted, the *frictionless* ceiling (t 1.85) is already below the bar. No
   execution lever can manufacture significance that the gross signal does not have. **Stop
   attributing the death of the daily equity cross-section to the spread — at zero cost it still
   fails, by t 1.85 vs 2.98.**
2. **The auction rail is the one genuinely measured cheap rail, and it works — for the right signal
   shape.** It flips the *sign* of a daily (not last-10-minute) cross-sectional reversal, executed
   MOO-at-next-open, ADV rank ≤ 1500. It does not flip the *verdict*. Any future daily-cadence
   candidate should be priced on the auction rail from the start (it is free and measured), but a
   candidate must clear the multiple-testing bar on *gross* before the rail matters.
3. **A forced 1-day lag is fatal to the fast leg.** Any signal that can only reach a zero-spread rail
   through a next-day MOC (because its own timing collides with the 15:50 cutoff) loses the h=1 edge
   entirely. Reachability of the auction rail is a property of *when the alpha lives*, and must be
   checked per candidate, not assumed.
4. **Crypto spot is closed to this line of attack.** The fee is not the binding constraint — the OOS
   gross signal is. Do not spend a round chasing maker rebates or venues for it.
5. **Lever 1 (maker) is the only lever free data cannot resolve, and it is bounded below the bar
   anyway** (fantasy ceiling t 2.75). If maker execution is ever pursued it needs live fill data and a
   signal whose *frictionless gross* already clears the bar — which none of the cost-killed corpses
   have.

**Net: one sign-revival, zero verdict-revivals, and a reframing that should end the re-testing —
the persistent-but-cost-killed signals are persistent-but-*sub-bar*; the spread was hiding a corpse,
not killing a live edge.**

---

## 6. Files

- This document.
- Re-run script: `scratchpad/exec_wall_rerun.py` (reversal family × universe × horizon × lag × flat
  cost; cached panel only, no network, no orders).
- Anchors: `INVENT_D0821_xsfactor_HOLDOUT.json` (FR_REV1 h=5: gross t 1.846, break-even 5.133 bp),
  `M0_AUCTION_FILLS.{md,json}` (auction rail = measured 0 spread, rank ≤ 1500),
  `B22B_SLIPPAGE_RESULT.json` + `costs.py` (2.5 bp liquid taker, per-side convention),
  `INVENT_D0821_crypto_spot_xs.md` (crypto fast reversal gross ≈ 0 OOS),
  `THOROUGH_REEXAM.md` (T10 auction-rail reversal t ≈ 0.5), `FORMULA_SWEEP_MASTER.md` (§8.3 MOC-legal
  rail dead; §6 intraday-RV maker side untestable on free data).
