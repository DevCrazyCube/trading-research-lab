# INVENT_0822B — MASTER SYNTHESIS (2026-08-22, 2nd rotation)

Three fresh micro-angles, **177 pre-registered formulas**, pooled correction over the total.
Themes: **auction imbalance** (54), **crypto spot cross-section** (81), **futures/FX mechanical roll & seasonal** (42).

**HEADLINE: 2 of 3 themes are noise. One factor survives every gate — and it is neither an invention
nor collectable on free data: cross-sectional realised-volatility on Binance spot is entirely a SHORT
high-vol alt-bleed carry leg, so it is borrow-walled (lesson 7 in its exact form). Freeze the spec,
log it forward, size nothing until a Binance alt borrow-rate/limit curve exists.**

---

## 1. The pooled null over all 177

Each theme measured its own size-matched placebo. To correct over the round as a whole I converted
every theme's placebo max-statistic to **|t| units** (Sharpe × sqrt(design years): crypto ×2.0 for
2019-2023, futroll ×3.464 for 2007-2019, auction already in t), fitted a Gumbel to each theme's
reported quantiles, and took the product of the three CDFs. No single cross-theme placebo is
constructible — the three panels share no instrument, no calendar and no clock — so this is an
assembled pooled null and is labelled as such.

| Bar over N = 177 | max abs t |
|---|---|
| Analytic two-sided sqrt(2 ln 2N) | **3.43** |
| Pooled size-matched placebo, p50 | 2.74 – 2.78 |
| Pooled size-matched placebo, **p95** | **3.56 – 3.71** |
| Pooled size-matched placebo, p99 | 4.08 – 4.31 |

(Range = fitting each theme's Gumbel to (p50,p95) vs (p50,p99); the empirical tails are slightly
fatter than a Gumbel, so the upper end is the conservative one. Per-theme inputs, in t units:
auction N=54 p50 2.26 / p95 3.31 / p99 3.62; crypto N=81 2.60 / 3.50 / 3.95; futroll N=42 2.11 /
2.94 / 3.38.)

**The single most useful number in this round:** the three themes' best DESIGN statistics are
auction |t| **4.04**, crypto |t| **4.04** (H20; 4.28 at H1), futroll t **3.75**. All three sit in the
same place relative to the pooled null — above p95, at or below p99. On design evidence alone they are
indistinguishable. Out of sample the auction cell goes to **t −0.23** and the futroll cell to
**t +1.30**, while the crypto cell goes to **t +5.39** on an untouched window. Design significance,
even properly placebo-measured, separated nothing here. Held-out did all the work.

Note the placebo/analytic ratio also went the other way this round: on the auction book the measured
placebo is only **1.08×** the analytic bar (3.311 vs 3.060). The ~2× inflation seen on the 0822 CEF
pair book is a property of **overlapping weekly pair books**, not of multiple testing generally.
Both directions are now on record; keep measuring rather than assuming either.

---

## 2. Survivors

### 2.1 The one that clears every stated gate

**S1_VOL30|H20 — cross-sectional realised volatility, Binance spot USDT top-50**

* **Formula.** Each day rank the ~50-name top-by-volume Binance spot USDT cross-section (≥$1M ADV,
  stables/wrapped excluded) by 30-day realised volatility of VWAP returns. Long the 10 **lowest**,
  short the 10 **highest**, equal weight, dollar-neutral, in 20 overlapping daily tranches. Signal
  uses data through the close of d−1; entry at VWAP of d, marked to VWAP of d+1; 10 bp/side.
* **Tether / mechanism.** Not a pricing tether — a **funding** one. Leg decomposition at full
  notional, held out: long low-vol **+11.7%/yr**, short high-vol **+120.7%/yr**, equal-weight market
  **−39.9%/yr**. Long low-vol vs short BTC is **−1.26** held out. The entire premium is the short
  leg: high-volatility alts bleed, and this book harvests that bleed while the long leg is a
  financing leg. The published names for it are the crypto low-volatility / lottery (MAX) anomaly.
* **Design.** gross SR +2.02 (t 4.04), net +1.95 (t 3.91), turnover 0.044/day, break-even 313 bp/side.
* **Held out (2023-01-01 … 2026-08-01, frozen to `_DESIGN.json` before the window was opened).**
  gross +2.92 (t 5.53), **net +2.85 (t 5.39)** at 10 bp/side, +2.77 at a 20 bp shock; 64.5%/yr on
  22.6% vol; break-even 390 bp/side; positive in every calendar year 2019-2026, 69/92 months,
  min rolling-1y net SR +0.08, skew +0.02, max DD 0.79 annual-vol units.
* **Nulls.** Clears the theme analytic bar (1.70 SR), the programme-cumulative bar (1.99 SR) and the
  theme slot-permutation placebo (E[max] 1.31, p95 1.75, p99 1.97; **0 of 400** replicates reach the
  observed 2.14). In pooled t units its design t 4.04–4.28 clears the pooled p95 (3.56–3.71) and sits
  at the pooled p99 (4.08–4.31) — i.e. **pooled, the design evidence is marginal**; the held-out
  t 5.39 is what carries it.
* **ρ1.** Not a spread signal, gate passed and reported: mean ρ1(close-to-close coin returns) −0.042,
  0% of coins below −0.35.
* **Robustness that held.** Close-return vol and Parkinson range vol; lookbacks 10/60/120d; k=5/10;
  universe top-30/50/80/120 (stronger wider); rank-weighting all 50; vol residualised on the 30-day
  return (stronger, 2.50/2.87 — **not** short-horizon reversal in disguise); residualised on log ADV
  (2.04) while pure size sorts to −0.26; excluding BTC / BTC+ETH / top-10 majors; listing-age filters
  ≥90/180/365d; no-lookahead universe check identical; only 2.1% of held-out short-leg P&L from
  names in their final 30 days.
* **H5 and H1 siblings** (net design +1.90 / +1.98, held out +2.68 / +2.63) are the same factor at a
  different rebalance rate, **not independent survivors**.

**Diversification vs BASKET1: partial, and the claim is weaker than it looks.** BASKET1's sized legs
(T3 pressure reversal, ETF-sibling RV, dual-class RV, T7 ex-open, T12 CEF, ORB) are all US-equity
legs on an NYSE session calendar — zero instrument overlap, structurally diversifying, design beta
−0.10 to its own market. **But** BASKET1 also carries two logging-only Binance legs (XS_GLSR_Z and
its smart-vs-crowd sibling), which are cross-sectional books over the same alt universe on the same
exchange. **No P&L-overlap measurement between S1_VOL30 and XS_GLSR_Z was made in this round.** Treat
"diversifying" as established against the equity sleeve and **unmeasured** against the crypto sleeve.

**Freeze recommendation: YES — spec-freeze + forward-log, UNSIZED.**
**Guard (all four required before any sizing):**
1. **Borrow gate.** A collected Binance alt borrow-rate and borrow-limit curve. The trade does not
   die on any plausible number (held-out net 2.45 at 5 bp/day, 2.04 at 10, 1.24 at 20; 1.52 at a
   $25M ADV floor + 10 bp/day) — it dies on **not having the number**. This is exactly lesson 7.
2. **Capacity gate.** 20 names at a $1M ADV floor; the edge halves at a $100M floor. Low single-digit
   $M. Any size beyond that is untested.
3. **Overlap gate.** Measure P&L correlation to XS_GLSR_Z before it shares risk budget with it.
4. **Kill switch.** The premium is one leg. Log the long and short legs separately from day one; if
   the short leg's contribution falls below ~70% of gross over a rolling quarter, the thing being
   collected is not what was frozen.

**Honesty flags carried forward, not buried:** (a) this is a **found published factor**, not an
invention, and it sits against the standing "invent, don't replicate" instruction; (b) the ledger
already contained two unfollowed hints of it — D0821 `D4_XS_AMIHUD` (held out +1.39) and `C4_XS_BAB`
(+0.79), both rejected on their design windows; (c) the genuinely new contribution of this round is
the **leg decomposition** showing it is entirely short-side and therefore borrow-walled;
(d) "short high-vol vs long BTC" (design 1.54 / held out 3.00) was constructed **after** seeing the
decomposition — held-out mining, observation only, never to be quoted as evidence; (e) the 2023-01 …
2026-08 held-out calendar has now been read by D0821 crypto-spot, by rounds 2/3 on perps, and by this
round; (f) short-side financing is quoted as free everywhere outside the borrow section.

### 2.2 Nothing else is promoted

Zero promotions from auction. Zero from futroll. Two objects are **characterised, not promoted** —
both are real, both are out-of-sample-confirmed, and both are smaller than their own execution cost
or their own significance bar. They are filed so they are never re-discovered as new:

* **Auction tick fixed effect.** `mean20(d_t) → d(t+1)` on the close-auction dislocation:
  design t **+26.8**, held out t **+26.6**, gross +1.23 bp/day. It is stable because it is a fixed
  effect — a name's habitual side of the tick in its own closing cross (sd of per-symbol mean of d =
  3.91 bp vs sd(d) = 5.50 bp; pooled ρ1 falls +0.056 → +0.036 after symbol demeaning). Collecting it
  needs a 15:59 fill across a first-party-measured 1.43 bp half-spread against a 0.616 bp break-even:
  the market must be **2.3× tighter**. Held-out net −1.63 bp/day, t −35.2. Post-hoc (5 cells beyond
  the pre-registered 54).
* **Month-end Treasury index duration extension.** Real and replicating on 64 years the search never
  touched: last-2-business-day fall in yield, raw CBOE yields, t **+2.98 in the 1962-2006 pre-sample**,
  +3.32 design, +2.49 held out on ^TNX, same on ^FVX/^TYX, **flat at the bill** (^IRX t +1.04) — a
  clean duration gradient with the floor the mechanism predicts, and **absent in the 1960s-70s**
  before bond indexing existed at scale. Passes every gate including the cost wall (break-even ~17 bp
  vs a ~1 bp TLT spread — rare here), is an interval not an instant (+0.644 after a session of delay),
  and is fully diversifying vs BASKET1. It fails on **significance alone**: ~0.4–0.5 SR out of sample,
  under the bar. Published phenomenon (Ogden 1987 turn-of-month / index extension); re-derived from
  mechanism, never to be reported as an invention.

---

## 3. Themes that are noise

**Auction imbalance (54 formulas) — NOISE, and closed on free data.**
The ρ1 gate, run before the gross bar as required, is the whole answer. Pooled over 1.2M symbol-days
every dislocation series fails: ρ1(Δ) = −0.498 (d = ln(C/P59)), −0.517 (d49), −0.516 (imbalance
window), −0.503, −0.518 (open gap), −0.516, −0.517, and **−0.666** for the MOO-vs-MOC print
divergence, which has ρ1(level) −0.494 and a median of exactly **4.00 half-ticks** — a textbook
two-tick bounce estimator, measured. Do not re-propose it. The killing number: the median
close-auction dislocation is **1.55 bp = 2.00 half-ticks = one penny**. Free SIP history has no
imbalance feed; the only shadow of imbalance it publishes is where the print sits relative to the
last continuous trade, and that is the **price grid, not information**. The design best
(`S12_x|DAY_t1`, design t −4.04 as traded +4.04, 0/300 placebo draws reach it) dies completely out of
sample — held-out gross −0.11, deciles U-shaped instead of monotone, a third of the design result is
2020 alone — and it was never an auction signal, just one-day cross-sectional reversal wearing an
auction rail. Revisiting requires a **purchased** imbalance feed (Nasdaq NOII / NYSE Order Imbalance,
paired/imbalance share counts from 15:50).

*Structural finding worth carrying:* the **15:50 MOC cut-off is a partition, not a friction**. It
splits every auction idea into "uses the print, must wait for the next open auction" (36 cells) and
"cannot see the print" (18 cells) — and imposing it before designing anything makes the entire legal
grid **bounce-immune by construction**, since no eligible cell shares a price between predictor and
outcome. The rule that kills half the ideas immunises the other half. Rig validation: the deliberate
T3 control `M01_f|ON_t` reproduces T3's published +1.38 at +1.28 on an independently written panel.
Anti-consistency: only 17/54 cells keep their sign design→held-out (a coin gives 27), and 22/54 are
held-out net-positive at 0.5 bp/side with a max held-out |t| of +2.45 on a design t of −0.22 — that
is held-out mining at exactly the size the placebo predicts, and nothing there is claimable.

**Futures / FX mechanical roll & seasonal (42 formulas, third round; 140 across three rounds) —
NOISE. Recommend closing the theme on free data.**
Correction to the brief: this was not the least-worked theme. The four new families all fail.
Q (bond month-end): primary Q01 held out +0.470, t 1.30, below the pre-registered t>1.5 gate; the
mid-month placebo scores 82% of the pick and the SPY asset control 94%, and the a-priori window ranks
only 5 of 18 held out — decay is measurable, not luck (TLT month-end +17.95 → +9.43 bp/day while
daily vol rose 90.6 → 100.9 bp). P (FX month-end hedge rebalancing, 13): best design +0.136 vs
E[max] 0.608; the unsigned dummy and the mid-month placebo score as well as the signed formula, so
the sign carries nothing — the flow prints at the **WMR 16:00 London fix** and a close-to-close
series cannot see it. R (GSCI/BCOM roll, 7): its own non-roll-window placebo **out-scores** the
a-priori roll window on design (+0.299 vs +0.243). S (commodity seasonals, 6): the round's top
held-out formula (S06 +1.015) has design +0.207 at the **opposite sign** — a coin, recorded so it is
never quoted as evidence. Six explicit placebos/controls were carried **inside N** rather than bolted
on, and three of them scored at or above their own family's a-priori formula; that is how P and R
died.

*Data fact, closing round 2's open door.* Per-contract futures history is **unreconstructable on free
data**. Stooq is behind a JS proof-of-work (re-verified). Yahoo chart v8 serves per-contract futures
history only for contracts **still listed**: 172 symbols probed, 64 served; live contracts carry deep
history (CLZ26 to 2017-11-21) but the earliest served CL expiry is Sep-2026 = today's front, so at any
past date t the shallowest available maturity is ~(today − t) forward — on 2018-01-22 the nearest CL
contract is **8.6 years out**. The panel is a diagonal of ever-deferred contracts, not a curve. The
five genuinely available calendar spreads (both legs still listed) all pass ρ1 (−0.03 to +0.03) but
have n_independent ≈ 2, so no formula was scored on them.

---

## 4. Method corrections — worth more than the formula

1. **ρ1 is a SPREAD diagnostic, not a cross-sectional-returns diagnostic.** Bounce share of variance
   scales as (half-spread/σ)²; a tether spread has σ ≈ 25 bp/day, a top-50 alt ≈ 500 bp/day. Measured
   mean ρ1 on coin returns = −0.042, 0% below −0.35: the gate passes everything and gates nothing.
   The artefact that *does* threaten a VWAP book is the **mirror image** — VWAP is a time-averaged
   price and averaged-price returns carry ρ1 = **+0.193** (theory +0.25), manufacturing fake
   **momentum**. Both artefacts are lag-1 and both are neutralised by a one-day gap (signal through
   close d−1, entry at VWAP d), which puts signal and P&L two lags apart. Verified on synthetic
   panels with no effect in them: pure bounce gives +36.7 with no gap and −0.32 with the gap; pure
   time-averaged price gives +31.9 with no gap and −0.55 with the gap; a planted 8 bp effect is
   recovered at +2.73. **Add the mirror gate to the standing checklist for any averaged-price rail.**
2. **A "rotate-the-returns" size-matched placebo is BROKEN — do not rebuild it.** Holding weights
   fixed and rotating the return panel looks perfectly size-matched, but coins not yet listed at the
   rotated date have no return, so a dollar-neutral book silently acquires a directional leg:
   mean |net dollar exposure among names with a live return| = **0.0036 real vs 0.1284 rotated**.
   It reports p95 at 10.8 SD and would have falsely killed the one survivor. The correct construction
   is to **permute the signal across the day's ADV-rank slots**, one permutation per replicate: slot j
   is nearly the same coin day to day, so persistence, turnover, neutrality and cross-sectional return
   covariance all survive and only signal-to-coin alignment is destroyed.
3. **Placebo-vs-analytic inflation is book-shaped, not universal.** 1.08× on the auction book,
   ~2× on the 0822 overlapping-weekly CEF pair book. Measure it per book.
4. **Lesson 1 held a third time.** Zero formulas used regime conditioning; the two calendar
   conditioners that were tested as controls were *worse* than unconditioned (+0.478/+0.389 vs
   +0.947).
5. **Every mechanical flow in the futures theme executes at a fix**, and a daily close is the wrong
   clock for all of them — the same conclusion the forced-flow equity family reached, now from a
   second independent direction.

---

## 5. Where this leaves the programme

The pattern across the round is one statement: **the wall is data, not ideas.** Three independent
angles each terminated on a purchasable feed — an imbalance feed (Nasdaq NOII / NYSE), per-contract
futures settlements plus 16:00-London fix quotes, and a Binance alt borrow curve. That is the third
consecutive round to end there, and it is now the recommendation rather than a footnote:

* **Auction:** closed on free data. Re-open only with a purchased imbalance feed.
* **Futures/FX mechanical roll:** closed on free data after 140 formulas / 3 rounds. The next move is
  **data, not a fourth sweep** — either purchased per-contract settlements, or forward collection
  from live-contract snapshots, which accrues a genuine front curve at ~1 maturity/month.
* **Crypto spot cross-section:** momentum, reversal and volume/activity families **closed for good**
  (30 + 15 + 18 tests; median held-out net +0.18 / −0.13 / +0.80, nothing clearing the bar; plain
  1-day reversal held out −1.75). The vol factor is frozen, logged, and gated on a borrow feed. If
  that feed is collected, the natural implementation is a short via **USD-M alt perps** — a different
  instrument, needing its own round, where the cost is funding rather than borrow.

**Discipline record.** All three themes pre-registered before the first design statistic (auction
prereg sha256 `1377e0f207ca1c5fd0c4bb33feae10b498e0ac15075e35bee082181c8e36d4e3`; futroll `_FREEZE.md`
written with pass criteria before the held-out was read; crypto signs frozen to `_DESIGN.json`).
Held-out windows untouched until the rules were fixed. No regime conditioning anywhere. No network
crawls inside agents. No git commits, no orders, BASKET1 untouched. All 177 primary tests reported,
none dropped; the crypto theme's ~40 further robustness objects are excluded from the null (which is
why its survivor is quoted against the p99 of the max, not the p50).

---

## 6. Artifacts

**Theme reports** (all under `/home/anont/meme/research/trading_bot/`):
`INVENT_0822B_auction.{md,json}`, `_auction_SUMMARY.json`, `_auction_DIAG.json`, `_auction_RHO.json`,
`_auction_TICK.json`, `_auction_PREREGISTRATION.md`;
`INVENT_0822B_cryptoXS.{md,json}`, `_cryptoXS_DESIGN.json`, `_cryptoXS_HOLDOUT.json`,
`_cryptoXS_DIAG.json`, `_cryptoXS_GATE.json`, `_cryptoXS_FLOORS.json`;
`INVENT_0822B_futroll.{md,json}`, `_futroll_FREEZE.md`, `_futroll_DESIGN.json`,
`_futroll_HOLDOUT.json`, `_futroll_NULLS_DESIGN.json`, `_futroll_NULLP.json`.

**Pooled null:** `/home/anont/meme/research/trading_bot/INVENT_0822B_MASTER_POOLED_NULL.json`

**Code:** `/home/anont/meme/scripts/auc0822_{prep,engine,diag,rho,tick}.py`;
`/home/anont/meme/scripts/trading_bot/inv0822b_{lib,sweep,nulls,fetch,contract_probe}.py`.

**Panels:** `/home/anont/meme/research/data/auc0822_cache/panel.npz` (2669 × 1611) + `placebo_t.npy`;
`/home/anont/meme/research/data/inv0822b_cache/`.
