# THOROUGH RE-EXAMINATION OF EVERY KILLED EDGE — definitive ledger

**Date:** 2026-08-20 · **Scope:** 86 killed / shelved / never-tested edges across 11 clusters
(T7, T9, T10, T11, T12, T13, T15/T17/T18 ORB, crypto carry T21–T25, dual-class & wrapper RV,
the ORIGINAL/BROAD/SIZE invention rounds, and the memecoin programme).

**Why this exists.** T3 was killed on Deflated-Sharpe 0.917 < 0.95 *plus* an execution concern that
turned out to be misattributed. Under realistic execution it is +5.04 bp/night, t = 2.57,
Sharpe 1.21, ~99.5% bootstrap-positive — a real edge that a strict certainty gate threw away.
The owner's suspicion was therefore correct in at least one case, and this pass asks the same
question of every other corpse in the repo.

**The honest lens applied to each edge:**
1. Find the **held-out point estimate and its SIGN**, net of realistic costs (T6/T8/M0 conventions;
   realistic near-close market fills per T4/T20, not idealised auction prints).
2. Classify the kill as **(A) genuinely negative / structural / correctly-priced tail → STAYS DEAD**,
   or **(B) positive point estimate killed only for CERTAINTY (DSR/t gate), POWER, SIZE, or a
   MISATTRIBUTED execution assumption → REVIVE CANDIDATE**.
3. Re-run only where a *specific correctable kill-reason* could plausibly flip the verdict **and**
   the harness plus cached data already exist.

**Headline result: 10 revive verdicts covering 7 distinct edges; 75 stay dead; 1 needs an
expensive re-run.** Two of the seven are already live in BASKET1, two are already pending-spec
legs, **two are genuinely new and should be added**, and one is real but venue-blocked for a
US person. The corpus is *not* riddled with wrongly-killed edges — but it is not clean either:
the biggest failure mode found here is not excessive strictness, it is **held-out windows that
were never spent at all** (T12-S2, T23, dual-class, the ORB no-stop residual were all shelved
by argument, never by a number).

---

## 1. REVIVE LIST

Seven distinct edges. Ordered by strength of the held-out evidence.

### R1 — T12-S2 · CEF discount-LEVEL tilt (deployment spec: borrowable-short, H=4) ★ NEW, DIVERSIFYING

| field | value |
|---|---|
| Held-out point estimate | **+13.44 bp/week NET**, t = +3.51, ann. Sharpe **+2.35**, n = 116 weeks (2024-03 → 2026-08) |
| Sibling numbers | unrestricted short leg H=4: +14.48 bp/wk, t = 3.83, SR 2.57 · H=1: +12.93 bp/wk, t = 3.43 · borrowable H=1: +12.25 bp/wk, t = 3.24 |
| Net of cost? | **Yes** — 11.53 bp median CEF half-spread charged both sides; turnover only 0.42 of a 2.0 round trip ⇒ 1.24 bp/wk friction; borrow at the 33 bp/yr ETB floor |
| Killed by | **Never killed by a number.** Set aside solely because it was not the *declared primary* trial (the primary S1 mean-reversion cell was, and S1 is genuinely dead) |
| Re-ran? | **Yes** — tranche-level block bootstrap over the 29 *independent* rebalances: mean +14.46 bp/wk, 95% CI [+6.82, +21.62], P(>0) = 0.9999. Plus three hostile decompositions (below) |
| Certification status | DSR **0.9971 at the full 6 declared trials** — already deflated, already above the 0.95 gate. Permutation p = 0.0005. Disjoint design window 2021–2024: +13.85 bp/wk, t = 3.11 |
| Execution reachability | **Free data, retail rail.** CEFConnect free `/api/v3` discount feed (weekly cadence suffices) + Alpaca equities. ~36 long / ~36 borrowable-short names, 4-week hold, no auction rail needed |
| Rough standalone Sharpe | backtest **2.35**; honest forward expectation after survivorship + PIT-NAV + borrow haircuts **~1.0–1.5** |
| Correlation to BASKET1 | **Genuinely NEW and the best diversifier available.** Monthly horizon, closed-end-fund universe, discount-convergence mechanism. Not overnight-equity (T3), not identical-claim intraday RV (ETFRV). Residual equity beta is small and roughly offsetting across the two legs |

The three objections that were treated as fatal, measured:
- *"Half the P&L is the untradeable NAV leg."* Overstated. The **discount-convergence component alone**
  (raw price return ÷ NAV return, both ex-distribution, same friction) pays **+9.52 bp/wk net, t = 3.23,
  SR 2.17** held out and +9.65 bp/wk, t = 2.51 in design. The claimed mechanism is ~2/3 of the P&L.
- *"It's deep-discount survivorship."* At most half the edge is exposed: the **short leg** (premium funds,
  immune to deep-discount attrition) carries slightly more than the long leg — universe-minus-short
  +17.99 bp/wk (t 4.15) vs long-minus-universe +16.90 bp/wk (t 2.39), both positive in both windows.
  Killing it would require every delisted deep-discount CEF to have lost 56–126% relative before
  vanishing; real CEF liquidations/open-endings pay **near NAV**, i.e. a +23% gain on a −19% discount,
  so the bias plausibly runs *conservative*.
- *"Only 57.2% of short-leg slots are borrowable."* Costs ~1 bp/wk when actually measured. That is why
  the borrowable-only variant is the recommended spec.

**Honest residual risks (must be in the pre-registration):** point-in-time NAV / restatement risk in the
CEFConnect feed is unfalsifiable from that source and hits the discount-only component hardest;
capacity is SIZE-capped to low single-digit $M (closing auctions clear $0.0–0.3M); the 2.4 held-out
years sit in one broad CEF-discount-narrowing regime (2024 +3.66, 2025 +22.85, 2026 +16.03 bp/wk —
all positive but concentrated in 2025); the shortable flag is a **2026 snapshot applied
retrospectively**, an executability *bound* rather than a clean backtest; and a genuinely
hard-to-borrow premium-CEF short at several hundred bp/yr would cost 1–3 bp/wk more than charged.

---

### R2 — T7 ex-OPEN dividend residual (cum-day close → ex-date opening auction) ★ pending-spec leg L4

| field | value |
|---|---|
| Held-out point estimate | **+3.35 bp/event-day NET**, t = +2.96, ann. Sharpe **1.38**, 99.8% bootstrap-positive, n = 1,018 |
| Control-differenced | +3.26 bp net vs same-day non-ex-dividend control (t = 2.86, SR 1.33); permutation p = 0.042 |
| **Design half too** | **+2.25 bp net (t = 2.99)**, +1.55 bp vs control (t = 2.00) — sign consistent across **both** halves, which the T7 write-up never stated |
| Net of cost? | Yes. Stress ladder: 0.5 h/leg +1.92 bp (t 1.70); **full measured half-spread on all four legs +0.49 bp (t 0.43)**; 2 h/leg −2.37 bp |
| Killed by | **Never tested** — the variant was excluded from the declared grid in advance, so no verdict was ever rendered. The *close-to-close* sibling was correctly killed (see §2) |
| Re-ran? | Yes, with costs |
| Execution reachability | **Free data, free rail.** Corporate-actions feed + Alpaca SIP auctions; ex-dates known weeks ahead. Enter MOC on the cum-day (`tif=cls`, before the 15:50 cutoff — no intraday signal is measured, so unlike T3 the cutoff costs nothing), exit MOO (`tif=opg`). M0 measured the open print present on 99.96% of top-500-ADV symbol-days, median 1.38 bp from the opening minute's own VWAP |
| Rough standalone Sharpe | 1.33–1.38 backtest; haircut to a ~**0.6–0.9** realised prior |
| Correlation to BASKET1 | **Adjacent, not diversifying.** Same overnight US-equity session and same MOC→MOO rail as T3 L1, and universes can overlap. Signal is orthogonal (dividend mechanics vs intraday pressure reversal) but the *session risk factor* is shared. Size it as a satellite, not a second anchor |

**Caveats on the record:** post-hoc DSR 0.855 at 8 trials (0.836 at 9, 0.651 at 24) — it has never faced
a frozen window because 2022–2026 is burned. Capacity is genuinely small: the opening auction is ~7×
thinner than the close (top-500 median $4.8M, p05 $669k); with ~6 names a night at 50% of equity in
stock and a 1% participation ceiling, capacity is roughly **$100k (thin tail) to ~$600k (median)**.
MOO gives up a median ~11 bp of price certainty vs the post-open quote — variance already inside the
return series, not an unmodelled cost. **Tax:** fatal in a *standalone taxable* account
(221 × 3.35 bp = +7.4%/yr pre-tax against 67.7% of equity/yr in non-qualified ordinary dividend income
whose offsetting short-term capital losses are stranded by IRC §1211(b) → ≈ −16%/yr at 35%). A
tax-deferred account removes the objection entirely, and tax is irrelevant to a paper forward test.

Mechanism note: implied overnight drop-off ratio ~0.88 vs 0.95 close-to-close — the residual appears
overnight and is **given back during the ex-date session**, which is exactly why the close-to-close
form is zero and this form is not.

---

### R3 — Dual-class voting-premium RV, two-timescale z-fade, liquid 16-pair subset ★ pending-spec leg L3

| field | value |
|---|---|
| Held-out point estimate | **+18.4 bp/round-trip NET**, n = 201 trades, t = +2.13, hit 59.7%, per-trade Sharpe 0.150, **book Sharpe 0.99**, bootstrap P(mean ≤ 0) = 1.75% |
| Grid stability | declared-grid median +21.3 bp; **all 18 configs positive**, 13 of 18 with t > 2 |
| Design window | +77.4 bp / SR 2.55 → **4.2× shrinkage with the sign intact** |
| Net of cost? | Yes — measured NBBO half-spreads; per M0 the closing auction is a zero-spread rail for ADV rank ≤ 1500, so the charged number is *conservative* for the trade as specified |
| Killed by | **Certainty + a published-prior argument.** Shelved as "published (Schultz & Shive 2010) + expected power shortfall" without ever spending the held-out window. DSR 0.602 at 18 trials. Being published is a crowding prior, not evidence of zero |
| Re-ran? | Yes — the held-out window was spent once, this pass |
| Execution reachability | **Free Alpaca SIP daily bars** (cached at `/home/anont/meme/research/data/t28_dualclass_cache/`), close-to-close entries/exits, MOC/MOO accepted on the paper account. **Hard constraint: borrow.** The rule shorts whichever class is rich, often the thinner voting class; at HTB rates (10.28%/yr) the edge is **−45 bp**. The forward spec MUST screen the short leg to easy-to-borrow |
| Rough standalone Sharpe | book 0.99 held-out; honest forward expectation **~0.4–0.7** after reconstruction and 18-config-grid haircuts |
| Correlation to BASKET1 | **Partially diversifying.** Market-neutral and multi-day, so orthogonal to T3's overnight directional-neutral book; but it is the *same mechanism family* as ETFRV L2 (z-fade of an identical-claim spread). Expect low realised correlation, shared model risk |

Structural anchor: identical cash-flow claims, so the equilibrium is enforced by corporate law rather
than by a fitted regression. The 16-of-16 AC1/VR signature is demonstrably **not** a Roll/bid-ask
artefact (pairs measure AC1 −0.06…−0.36, VR(5) 0.42–0.88; iid measurement noise gives −0.50 / 0.20).

Pairs: GOOGL/GOOG, BRK.A/BRK.B, FOXA/FOX, NWSA/NWS, UAA/UA, HEI/HEI.A, CWEN/CWEN.A, LGF.A/LGF.B,
CENTA/CENT, LBRDA/LBRDK, LSXMA/LSXMK, FWONA/FWONK, Z/ZG, DISCA/DISCK, PBR/PBR.A, LILA/LILAK.

---

### R4 — ORB no-stop residual (opening-candle breakout, **no intraday stop**, exit MOC) ★ NEW, session-diversifying

| field | value |
|---|---|
| Held-out point estimate | **+4.81 bp/day NET**, ann. Sharpe **0.494**, t = +1.06, ~+9.6%/yr on 24.5% vol at 1× gross, max DD 32.7%, 1,158 sessions / 18,851 trades |
| Design window (2016–2021) | +7.24 bp/day, Sharpe 0.863, t = 2.09 |
| Gross (zero cost) held out | +14.11 bp/day, Sharpe 1.450, t = 3.11 |
| Net of cost? | Yes, at **T18's own tick measurement on these exact stock-days**: entry stop order, 100 ms rung, fill vs breakout level, mean 9.02 bp of notional (median 4.46, decontaminated n = 810), plus 0.28 bp SEC/TAF. MOC exit measured at 99.76% official-print coverage and mean −0.96 bp (slightly favourable) so charged at zero. No borrow (intraday). **No universe-transfer error — that is the exact defect that broke T17** |
| Killed by | **Never tested.** T18 killed ORB-with-a-stop; the no-stop residual was never run |
| Re-ran? | **Yes** |
| Execution reachability | Fully free/cheap: 1-minute bars for the 09:30–09:35 range, 14-session opening-volume history, daily ATR(14) — all cached in `research/data/t17_cache/` (2.4 GB, 2,655 sessions) and all free on Alpaca |
| Rough standalone Sharpe | **~0.5** unconditional held out; ~1.0 on a relvol ≥ 500% subset, **but that threshold is post-hoc and the threshold curve is not clean** (0.43 at 600%, 0.54 at 700%) |
| Correlation to BASKET1 | **Genuinely NEW and the cleanest session diversifier.** It is literally the complementary session to T3: B22F measured overnight and intraday SPY legs at ρ = +0.018 full sample / −0.065 held out. But it is **directional US equity**, not market-neutral, with 24.5% vol and an unbounded intraday tail |

Why removing the stop is a legitimate correction and not a fit: T18 established that ORB's entire
negative comes from the **stop leg** — 87.9% of trades stop out into a quote half as wide as the risk
unit (R/spread ≈ 2.1; one stop exit costs 0.124 R mean into an 18.9 bp quote with 3 shares at the
touch) — while the MOC exit is free and the direction call is real (permutation p = 0.0005 at zero
cost). Deleting the stop deletes the entire measured kill mechanism.

**This is the weakest revive on the list and is flagged forward-test-only, never fundable:**
t = 1.06 over 4.6 years is underpowered; two of four full held-out years are negative
(+25.1 / −14.2 / +16.1 / −12.5, then +41.1 on a 2026 partial); dropping the 5-month 2026 stub
collapses the unconditional result to **Sharpe 0.15, t = 0.31**; it is a post-hoc variant run on an
already-spent window across ~4 weightings and ~12 thresholds, carrying an unpriced multiple-testing
haircut; and a no-stop book has an unbounded intraday tail (worst day −9.6% at 1× gross).

---

### R5 — T13 Family B · volatility-targeting overlay (L=60, target 10%, w_max 1.0) — ALREADY LIVE as the basket's sizing sleeve

| field | value |
|---|---|
| Held-out point estimate | ^SP500TR 1990–2026 (36.6 y), costs ON, vs the ex-post vol-matched constant-weight null: **maxDD 27.63% vs 34.88% = +7.25 pp**; CAGR +0.657 %/yr; Sharpe-over-cash 0.5788 vs 0.5200 |
| Return-side inference (my re-run) | paired daily excess **+0.609 %/yr**, se 0.755, t_iid 0.81, t_NW(10) 0.95, 95% CI [−0.63, +1.87], block-bootstrap **P(>0) = 0.837** |
| SPY replication | +7.81 pp, +0.641 %/yr, P(>0) = 0.806 |
| Net of cost? | Yes and *conservatively* — 2.5 bp/side charged against SPY's real ~0.17 bp half-spread (≈15×). At **4× cost** the drawdown edge moves 0.18 pp |
| Killed by | **Power.** A maxDD claim gets one observation per crash (3 usable crashes in 36.6 y) ⇒ p = 0.233, DSR = 0.355. Those numbers measure *sample size*, not sign |
| Re-ran? | Yes |
| Execution reachability | Trivial, free daily data; 1.74 units of turnover/yr (0.86 round trips). T4's live rail already switched MOC → near-close market DAY order (2026-08-18) after Alpaca expired `tif=cls` unfilled, and logs `cost_if_taker_rail` beside the auction accrual — so the T4/T20 near-close-fill concern is **priced, not assumed away** |
| Rough standalone Sharpe | 0.58 over cash as a long-only sleeve (10.4% vol) vs 0.52 for any constant-weight SPY/T-bill mix. **As an incremental overlay the paired-excess Sharpe is only ~0.13** |
| Correlation to BASKET1 | Not a leg and must never be counted as one — it is a **sizing sleeve** that scales equity exposure, correlated with everything by construction. Already installed as `vol_overlay` in `BASKET_FORWARD_FROZEN.json`; T4_FORWARD_STATE.json shows inception 2026-08-17, sessions_settled = 0 |

Positive on every axis and instrument, positive-signed in 4/4 decades on drawdown and 8/8 declared
configs on CAGR, cost-insensitive at 4×, G3 circular-shift at the 2.24th percentile (PASS).
**Be honest: at P(>0) = 0.84 this is far weaker than the T3 revival (~99.5%).** It is a legitimate
low-conviction sizing sleeve, never an alpha claim, and T4's own pre-registration is right that it
will almost certainly never certify. (Sibling w_max = 1.5 posts +8.50 pp / +0.71 %/yr but buys no
drawdown for 0.41 pp more vol — stay at 1.0.)

---

### R6 — ETF-sibling pre-cutoff relative value, Arm B (15:45 → closing print) — ALREADY LIVE as leg L2

| field | value |
|---|---|
| Held-out point estimate | +1.0 to +1.5 bp/pair-session expected NET (proposal-stage; the original −0.79…−0.91 close-print beta was **retracted pre-test** as an errors-in-variables artefact) |
| Killed by | **Size / capacity risk** — 9 of 24 nominated wrappers clear < $1M in their own closing auction. Never killed on sign |
| Execution reachability | **Live now.** Design (2016–2021) and held-out (2022–2026) Alpaca SIP data downloaded; MOC/MOO accepted on the paper account; running as leg **L2 "ETFRV"** (IVV/SPY, VOO/SPY, QQQM/QQQ, VTWO/IWM, IJH/MDY, \|z\| > 1.5 fade) |
| Correlation to BASKET1 | It *is* BASKET1. Market-neutral by construction, capacity-capped at 4–6 effective pair-sessions/day |

Mandatory guard already recorded: extract the official close **code-agnostically over conditions
'6' and 'M'** — a '6'-only filter reads VOO's 2026 median close as $0.005M instead of $255M and
manufactures a several-hundred-bp fake dislocation.

Note the correct disposition of the *broad* wrapper family: the concentrated two-pair form survived
into L2; the all-13-pair pooled form stays dead (§2).

---

### R7 — T23 · cross-sectional perp funding carry, liq5m_top3 — REAL, but VENUE-BLOCKED for a US person

| field | value |
|---|---|
| Held-out point estimate | **+15.05 pp/yr excess over by-year T-bills**, frozen held-out window 2023-01 → 2026-07 (n = 43 months), **t = +3.58**, excess sd 7.96, worst month −5.42%, max DD −5.42% |
| Sub-period stability | design 2020–2022 +20.07 pp · unburned 2023-01→2024-09 +5.77 pp (t 1.03) · 2024-10→2026-07 +23.85 pp (t 4.13). Whole liq5m family positive held-out (top3 +15.05, top5 +6.87, top10 +5.62, top20 +4.10) |
| Net of cost? | Yes — 36.8 bp round trip on realised turnover (3.32 pp/yr), −2.00% delisting tail on 3 held delistings (0.56 pp/yr), premium/basis mark-to-market, 1.2× capital multiplier. **3× cost stress still leaves +9.5 pp/yr** |
| Gates | Clears all five pre-registered gates: H1 sign · H2 the +1.00 pp venue-tail bar · **H3 DSR 0.9977 at the full 12 declared trials** · H4/H4b permutation p = 0.0002 against both screened and unscreened universes (random picks from the same pool **lose** −8.98 pp/yr) · H5 capacity $4.9M |
| Killed by | **A power gate that assumed the effect was small and therefore declined to look.** T23 refused to spend the held-out window on an MDE (15.25 pp) calibrated to T21's claimed +2.20 pp and to the *primary* cell's blowup-inflated dispersion |
| Re-ran? | **Yes** — ran the frozen rule on the never-spent window |
| Rough standalone Sharpe | **1.89** annualised excess-over-T-bill (1.98 design); skew +0.26, kurtosis 5.27 — no negative fat tail |
| Execution reachability | **Data yes (free, keyless, 420 MB already cached at `research/data/t23_cache/`); venue NO for a US person.** Binance USD-M perps + Binance spot are not legally reachable by US retail. Capacity is *not* the constraint (median pick ADV $16.4M, H5 capacity $4.9M vs a $100k account) |
| Correlation to BASKET1 | **Zero-ish — statistically the single best diversifier in the entire corpus** (crypto funding carry vs US equity). Which is exactly why the venue block is so expensive |

**This one is a genuine venue/legal gate, not a research call — it goes to the owner, not to the
basket.** Recommendation in §4.

---

## 2. STAYS-DEAD LEDGER — 75 edges, one line each. Do not revisit.

### T7 ex-dividend
| edge | held-out number | why it stays dead |
|---|---|---|
| T7 close-to-close drop-off (frozen primary) | **+0.84 bp/day net, t = 0.46**, SR 0.21; perm p = 0.213 | 8/8 design trials negative (best SR −0.11); t sits 0.8 sd into a null 6× wider than the effect; drop-off ratio 0.95 with CI [0.84, 1.08] — indistinguishable from 1.0 in **both** halves. M0 later verified the execution assumption *in its favour* and it still doesn't move: genuine zero |

### T9 spin-off
| edge | held-out number | why it stays dead |
|---|---|---|
| T9 primary, H=60 long stub / SPY hedge | **−0.82%/event net**, t = −0.39; −0.698% at **zero** cost | Negative frictionless, 37th percentile of a 10,000-shuffle null (p = 0.627), loses to its own control basket (+0.09% vs −0.70% on identical dates) |
| T9 curated-stub sensitivity, H=60 (my re-run) | **+0.63%/event gross**, t = 0.33 | The one correctable defect (ENVXW warrant + APE preferred units) *was* tested: cleaning them flips the sign but leaves t = 0.33, MDE 5.36% vs a 2.40% Cusatis benchmark. "No measurable effect", not a revive |
| T9 short horizon, H=21 | **−1.87%/event net**, t = −1.50, book SR −0.97 | Most negative declared horizon and the closest to significance — on the wrong side of zero for the pre-registered hypothesis |
| T9 §7 sign-flip: SHORT the fresh stub, H=21 | +1.87%/event, t = +1.50 (gross of borrow) | Hypothesis generated from the data it is measured on; **and B22G measured that at this broker HTB means `shortable = False`, not an expensive short** — a freshly distributed stub is the canonical special. The leg cannot be borrowed at all |
| T9 long horizon, H=126 | **+4.64%/event net**, t = +0.73, book SR +0.17 | Sign flips across the three declared horizons (−1.87 / −0.82 / +4.64); per-event sd 48.6% so the mean is two fat right-tail names; 0.17 Sharpe is not an edge |

### T10 overnight / intraday
| edge | held-out number | why it stays dead |
|---|---|---|
| T10-B3 frozen cross-sectional tug-of-war | +1.482 bp/session on the auction rail (t 0.47) → **−1.377 bp at 0.5 h, −4.237 bp at 1.0 h** | Break-even 0.370 bp/leg = **0.26×** its universe's own measured 1.43 bp half-spread (4.00 of gross notional flipped per session). Execution isn't misattributed, it *is* the result. DSR 0.377 is not a near-miss — observed Sharpe 0.01405 sits **below** the 8-trial expected-max under the null (0.02342) |
| T10-B3 lookahead-corrected | +2.972 bp on the auction rail (t 0.97) → **+0.113 bp at 0.5 h**, −2.746 bp at 1.0 h | Removing the lookahead genuinely doubles the number (**precision correction to T10_RESULT.md §4b: at 0.5 h this is +0.11 bp, i.e. indistinguishable from zero, not "still negative"**), but break-even only rises to 0.52× the half-spread. Nothing to certify at t = 0.97 |
| T10-A1 SPY market-level paired harvest | **−0.569 bp/session net = −3.07%/yr**, SR −0.078, t = −0.17 (re-run) | The strongest test of the hypothesis on the cheapest instrument in the programme, and it loses: **SEC §31 alone (0.556 bp/session on 2.0× sale notional) exceeds the entire gross premium of 0.531 bp.** Held-out gross collapsed from +2.58 bp (design), consistent with the NY Fed's Jul-2026 "Disappearing Overnight Drift" |
| T10-A2/A3/A4 EW top-100/300/500 harvest | net **−1.946 bp at 0.5 h**, −4.806 bp at 1.0 h (+0.914 bp auction-rail only) | Same 4× turnover on a 1.43 bp universe with a shrinking gross premium (+2.58 → +1.60 bp); break-even 0.28× its own half-spread |
| Overnight-only long, minimum-turnover variant (re-run) | **+2.415 bp/session net, SR +0.583** — positive against zero, but buy-and-hold SPY is **SR +0.782 for zero legs** | Loses to the free alternative *structurally*: the two legs are ~uncorrelated (ρ +0.018 / −0.065) and the intraday leg's expected return is **positive** (+5.0…+5.2%/yr per B22F's own correction), so dropping it can only lower the combined Sharpe. Fails at **zero** execution cost (0.715 vs 0.782), so no M0-C4 result can rescue it |
| Overnight-only levered to full-day vol (T13 §8b risk-shaping form) (re-run) | **+4.38%/yr at SR 0.335** (4.5% margin) vs buy-and-hold +12.73% at SR 0.782, DD −36.4% vs −24.5% | This was the one genuinely open question a cheap re-run could have flipped. It did not flip: levering costs margin on 0.65 of notional every calendar night for a third of the return at a deeper drawdown |
| Long-decile-only variant (never run as a trial) | +3.656 bp auction-rail → **+0.796 bp at 0.5 h**, −2.064 bp at 1.0 h | Dropping the empirically dead short block (−0.57 bp, t −0.10) nearly triples break-even to 0.989 bp/leg — still only **0.69×** the universe's half-spread, and t = +0.58 on a burned window. Dead by known arithmetic |

### T11 merger arbitrage
| edge | held-out number | why it stays dead |
|---|---|---|
| T11 frozen primary, H=63, one-sided +20% cap | **−0.827%/event net**, t = −0.985, book SR −0.30 | Dead as a **broken rule**, not as economics. **Correction to FINDINGS: T11_RESULT.md §2's claim that "it loses with every cost switched off, this is an economics death" is WRONG and should be retired.** Repairing four self-reported feed defects (cash+stock counted cash-leg-only, warrants/units cashed at $0.01, names that stopped trading years pre-effective, restated duplicates) moves it to +1.418% (t 3.28) |
| T11 defect-repaired, H=63 | **+1.418%/event net, t = +3.28**, book SR 1.28, DSR 0.942 — but **break-free (Oracle A)** | Survivorship here is *structural*, not a strictness gate: the feed contains **no broken deals at all**, so the entire left tail is absent by construction. Break-even break rate b* = 5.2% at L = −25%, inside the 5–10% quoted band; net excess +0.18%/yr at b = 5%. ~9% is also Oracle-B clairvoyance |
| T11 repaired **and lookahead-fenced** (spread ≤ +10%) — the honest number | **+0.902%/event, t = +5.21, +3.35%/yr, SR 1.21**, break-free; **b\* = 3.35%, BELOW the 5–10% band** | The defensible estimate, landing on the literature (+3.3%/yr vs Mitchell–Pulvino's 4%) — and it loses to its own tail: −1.64%/yr at b = 5%, +0.35%/yr at b = 3%. **T11's tail conclusion was CORRECT even though the number that reached it was wrong** |
| T11 short horizons, H=5 / H=21 | repaired: **+0.072% (t 0.33)** and +0.340% (t 1.44) | The only two "> 2 se negative" T11 results were feed-defect artefacts too; repaired they are zero break-free, and b* = 0.3% / 1.3% cannot survive any break rate at all |
| T11 "symmetric cap" clean variant (§5) | +1.866%/event, t = +6.87, +6.66%/yr (repaired: +2.056%, SR 1.82) | **Flagged as the trap:** inflated in two directions at once — Oracle A deletes the break tail, *and* the one-sided cap lets 24 pre-announcement entries (mean +13.9% net) through, supplying **60% of the mean**. Do not treat +6.66%/yr as achievable |

*All T11 variants share a second blocker: no announcement-date feed. `/v1/corporate-actions` publishes
cash mergers only after completion; the Benzinga headline probe recovered 52.5% with ~1/3 false
positives (17.5% strict). EDGAR 8-K item 1.01 / SC TO-T full text is a possible free path, untested.*

### T12 CEF
| edge | held-out number | why it stays dead |
|---|---|---|
| T12-S1 discount MEAN REVERSION (frozen primary, L=52, H=4) | **−0.27 bp/wk net**, t = −0.08; frictionless only +3.25 bp/wk (SR 0.68, t ≈ 1.0) | Negative net **and** the zero-cost series is too weak for any execution fix to rescue; there is no auction rail to find (CEF closing auctions clear $0.0–0.3M, so the 11.53 bp half-spread *is* the realistic fill). 3 of 4 S1 trials flipped negative out of sample after +7…+16 bp/wk in design — textbook overfit |

### T13 risk shaping
| edge | held-out number | why it stays dead |
|---|---|---|
| T13 Family A crash filter, **walk-forward** (SMA-150) | **+0.284 %/yr**, t = 0.18, P(>0) = 0.597; maxDD +6.61 pp (p 0.304) | **Not a genuine negative and I won't call it one** — it was pre-declared, lookahead-free, and positive on both axes. It stays dead for other reasons: the +0.28 %/yr edge is smaller than its own 24 bp/yr trading bill and is erased by a mere ×2 cost error (+0.029 %/yr) and negative at ×4; and it is **strictly dominated by the Family B overlay on every axis** (SR 0.545 vs 0.579, DD 31.2% vs 27.6%, 4.81 vs 0.86 round trips/yr) |
| T13 Family A **frozen** config SMA-100 | **−1.665 %/yr**, maxDD **−9.65 pp WORSE**, SR 0.380 vs 0.520; **still −8.57 pp / −1.33 %/yr at literally zero cost** | Mechanism identified and structural: the worst drawdown (46.7%, peaking 1999-07-16, unhealed to 2010-01-07) is a **whipsaw the rule manufactures between crashes**, not a crash it failed to dodge. It protects 3-for-3 *inside* crashes (mean 16.9 pp) and still loses on full-path drawdown — the transferable lesson. G3 32.8th percentile |
| T13 Family C (filter + overlay) | maxDD +4.34 pp (p 0.354) but **CAGR −1.10 %/yr** | Composition makes both legs worse: smaller drawdown gain than the overlay alone *and* a negative return. Dominated on both axes by a component already held |

### T15 PEAD / T17 / T18 ORB
| edge | held-out number | why it stays dead |
|---|---|---|
| T15 PEAD primary, SUE decile L/S, BHAR[2,60] | **No estimate exists** — MDE at 80% power = **4.44%** vs a pre-hashed 0.90% gate. Fails by 4.93× | Power kill with exact, unfixable arithmetic: 145,743 events needed vs 5,991 available = 113 years of collection, or a 12,164-name universe that does not exist. **The sign prior is not neutral** — Martineau (2021) CFR Table 4B measures exactly this surprise/size/horizon at ≤ 0 in every subperiod since 1996 and −0.003 in 2016–19, overlapping our design window. PIT-SUE restriction makes the MDE 1.7× worse. *Positive residual: the free 8-K item-2.02 second-resolution calendar (72,649 filings, cached) is a reusable asset for event-**avoidance** filters* |
| T15 PEAD H=5 short-horizon | No estimate; MDE 1.29% over BHAR[2,5] | The tempting revive, and it fails: the 0.90% benchmark that makes 1.29% look near-miss is Martineau's **[2,60]** number and cannot be transplanted to [2,5], where his all-but-microcap coefficient is ~zero in every period after 1990. The only surviving short-horizon drift is in microcaps, where T1 §2d measured **120 bp/leg** spreads |
| T17 ORB published primary | **+1.088 Sharpe, t = +2.33** as published → **−1.078 corrected** | **The most important negative in this pass: this looks exactly like T3 (positive, t 2.33, killed on DSR 0.2945 with PSR(1 trial) = 0.9931) and it is the one case where the misattributed execution assumption inflated rather than deflated.** T18 measured both load-bearing inputs on ticks: entry-bar stop-through assumed at 0% is actually **48.7%** (154/316, Wilson 95% LB > 0.43); entry slippage borrowed from B22B's 2025 most-actives pool is **8.8× too cheap** on the names this screen selects (2,402 vs 273 bp of R). The DSR gate reached the right verdict for the wrong reason |
| T17 ORB post-paper window (2024–2026) | +1.207 Sharpe, t = +1.95 | Inherits the identical refutation; T18's tick sample was stratified across 2022–2026 including 2026. "Has not decayed since publication" is a statement about the **gross signal**, not the net edge |
| T17 ORB rank-truncated sizing (~2 names/day) | +1.084 Sharpe, **max DD 75.2%** | Same refuted rule concentrated: a correctly-priced tail on top of a point estimate T18 showed is negative |
| T18 ORB tick-measured primary | **−1.078 Sharpe, t = −2.31**; direct tick truth on 712 decontaminated stock-days: **−0.479 R/trade, session-clustered t = −4.71**, win rate 13.6%. Both legs measured: −3.921 Sharpe | Structural negative with a *measured* mechanism: the top-20-by-relative-volume screen selects names with 16.4 bp quoted spread against R = 34.2 bp (R/spread ≈ 2.1); one stop exit costs 0.124 R into an 18.9 bp quote with **3 shares at the touch**. The permutation null still fails (p = 0.0125) — the opening candle's colour genuinely predicts direction — but realised friction exceeds the signal. No order type recovers it: a limit that doesn't cross forfeits the breakout |
| T18 ORB exit-correction-only config | +2.857 Sharpe, t = +6.12, PSR(1) = 1.0000 | **The trap in this cluster.** Reading only T18 §1–2 makes ORB look rescued at SR 2.86 — but that configuration holds the entry-bar stop-through rate at **0**, which the ticks measure at 0.4873 (95% LB > 0.43, quote-confirmed floor 0.3006). The post-hoc sweep is already under water at 0.30 |

### Crypto carry (T21–T25)
| edge | held-out number | why it stays dead |
|---|---|---|
| T23 **pre-registered primary** cell liq20m_top3 (the cell T21's "+2.20 pp/yr" refers to) | **+0.43 pp/yr, t = +0.04**, SR +0.02, one −29.98% month, **max DD −36.52%**, DSR 0.342; on T21's own search window **−8.45 pp/yr** | The window T23 declined to spend now says T21's claim doesn't merely fail to certify — under a leakage-free implementation the exact selected configuration is a genuine negative with an enormous tail. The $20M and $50M screen families are zero-to-negative at every topN (−6.15 to +4.82) |
| T25 cross-venue perp funding differential (Hyperliquid vs Binance) | never-spent window 2023-06→2024-09 (n=14): **all four topN positive** (+4.54 / +5.18 / +4.56 / +2.47 pp, t 1.03–1.63); full joint history +2.21 / +2.01 / +1.42 / +0.10 pp | Sign is honestly positive so the power block wasn't the whole story — but **net of the gate's own +1.00 pp two-venue failure bar the full-history estimate is ≈ +0.4 pp on a $33k book (~$130/yr)**. Depth-capped: 10% of HL top-20-level thinner-side depth ⇒ $10k / $33k / $67k books. Dominated by the T23 liq5m revive at **150× the capacity**. Burned window 2024-10→2026-07 is +0.74 / −0.02 / −0.67 / −1.47 pp; gross differential halved from ~21 to ~11 pp/yr |
| T22 **leveraged** crypto funding carry | the quantity leverage multiplies, **f − r_b = −0.81 pp/yr, t = −4.15** since 2024-01 (positive on 38.2% of days); corr(f, r_b) = 0.934; book at 50× = −14.18 pp/yr | Definitional death: the spot leg is unlevered cash and is 83–98% of committed capital, so λ moves only 0.833 → 0.980 (a capped +17.6% uplift) while liquidations go 3.1 → 33.0/yr. Levering means borrowing at r_b, which is priced the same as f. Kelly sleeve 0% at every λ ≥ 3 in every regime since 2023. Borrow proxy self-validates at 11 bp |
| T22 **unlevered BTC-only** cash-and-carry (= T23's btc_only control) | my re-run on the T23 panel with full costs: **+1.45 pp/yr** (t 1.80, max DD −0.29%) → **+0.14 pp in the last 22 months** | Genuinely positive with a beautiful risk profile, and still dead: the excess is **smaller than the venue-failure tail that funds it** (break-even venue-failure probability 0.68%/yr against a ~1%/yr base rate). A correctly-priced income stream, not an edge — and decaying on the same clock as the CME rail |
| T24 CME regulated crypto-futures basis | headline +2.08 pp/yr is **gross and on notional**; net on committed capital **+0.44 pp/yr** full sample, +2.42 (2024), +0.14 (2025), **−1.22 (2026 YTD)**, −0.75 on today's front month | An empty shelf — an *inventory* fact, not a power fact. **0 of 8 2026 cycles clear rf + 4 pp.** At an FCM that pays nothing on futures cash (the norm outside IBKR) every row is negative. Needs a new FCM relationship; front-month-only liquidity forces 12 rolls/yr at the lowest point on the curve |
| T21 VRP via cash-secured SPX put-write (CBOE PUT) | **−1.53 pp/yr of CAGR** vs the vol-matched de-risked null, Sharpe −0.090, paired t = −0.93 | The premium is real, huge and powered (+4.00 vol pts/month, t = +13.14 on 438 non-overlapping months; held-out 2022+ +3.21 pts, t = +3.95) but the retail harvest is **67% long equity** (β = 0.674). Measured against holding *less equity* rather than against cash it loses, and its worst months are worse than the null's in 5 of 6 — it fails to protect exactly where protection is wanted. The benchmark is the correct one |

### Dual-class & wrapper RV
| edge | held-out number | why it stays dead |
|---|---|---|
| Dual-class **full 24-pair universe** variant | **+16.5 bp/round-trip net, t = +1.32**, book SR 0.62; the 66 incremental trades average +10.7 bp | Strictly dominated by the liquid subset and indistinguishable from zero on its own. The incremental names carry measured spreads of **65–830 bp** (GEF.B 68, RUSHB 84, WSO.B 99, MOG.B 117, MKC.V 159, AGM.A 338, KELYB 415, GTN.A 826) with closing auctions in M0 tier E/F where M0 **explicitly refuses** to model a zero-spread fill. Widening the universe buys cost, not edge |
| Dual-class **flow residue** (index rules split cash flow between classes) | **No estimate of any kind exists** — no census, no script, no cached data, no result file | Not a separate tradeable object: the price series it would trade is the same share-class spread already measured. Its distinguishing claim needs index-membership history, which EDGE_SHORTLIST 2b records as the one dataset this programme cannot get (no API; iShares returns a bot-block page; SSGA 301s; the Wikipedia table isn't in the static HTML) |
| Wrapper redundancy — **all-13-pair pooled** form | +2.33 bp gross pooled over 1,168 round trips, but **92% sits in two pairs** (VOO/SPY +20.9, IVV/SPY +17.6); the other eleven pool to **+0.83 bp against a 0.6–1.2 bp friction floor** | The eleven-pair pool is at zero net by its own numbers, and the concentrated two-pair gross sits in exactly the close-print series the same document **retracted as an errors-in-variables artefact** (AC1 −0.44…−0.55, VR(5) 0.20–0.27 — the iid-measurement-noise limit). The part that looks big is the part that is print noise. The genuinely positive sub-component was **not** discarded — it is leg L2 |

### Invention rounds (ORIGINAL / BROAD / SIZE)
| edge | held-out number | why it stays dead |
|---|---|---|
| Orphan Flush — FLUSH leg, real ±1% bookDepth denominator (the pre-registered estimator) | design-window gross **−10.99 bp/cluster**, t = −0.53, n = 521; net −31 to −61 bp across the 20/25/35/50 bp friction curve | Negative gross on the correct (pre-registered) denominator with a clean lookahead audit (zero violations). Held-out window never needed |
| Orphan Flush — depth-FREE proxy-q variant (the "+42 bp revival") | gross +41.92 bp, t = +1.98 → net **+16.9 bp (t 0.80)** at central 25 bp friction, **−8.1 bp at the design's own cascade-moment 50 bp** | **Honest correction to the "revived-then-died" story: the flattering variant was NEVER net-positive-with-confidence.** It died on arithmetic, not only on the depth denominator. (Caveat: proxy-q fires 323 events/169 clusters vs depth-q's 669/521 — different event populations, not a re-costing of one) |
| Coiled Leverage Expansion — coil-mode = **diff** (the near-miss) | in-sample net **+1.81 bp/trade**, naive t bounded above by **0.99**, deflated at the design's own ×20 simultaneity **t ≤ 0.22** | **The +0.03 gate margin is NOT what killed this — I checked.** Strip the margin entirely and it is indistinguishable from zero *on its own design window*. Structural cause: realised W = 1.088 R vs the spec's assumed 3.0 R, because **a ratcheting stop cannot pay an MFE-derived win**. 3× more data moves t by at most √3, still < 1.7 |
| Coiled Leverage Expansion — coil-mode = **ratio** | in-sample net **−5.0 bp/trade**, hit 38.13% vs p* 40.44% | Negative in sample. Averaging the two pre-registered coil modes gives −1.59 bp/trade: **the declared trial set as a whole is net negative**, so promoting "diff" alone would be exactly the selection this programme keeps dying of |
| Settlement-Print Concession (BROAD Pick 2) | never run; **net ≤ 0 by an observable quoted price** — CME's own WTI TAS basis trades 0–2 ticks = **0–2.9 bp** against a measured ETF round trip of 1.02 (GLD) to 3.60 bp (DBC) | The market explicitly prices the exact risk transfer *below* our cost bar. Compounding: the universe collapses to 3 factors and is adversely sorted — the cheap names (GLD, 0.37 bp) are the most arbitraged, the names where the flow should bite (UNG 10.06 bp round trip, PDBC, DBO, BOIL) are cost-dead |
| SIZE #2 Cascade Relay | recomputed gross EV **−0.18 R before friction**; first-party mirror gives **+10.99 bp gross at t = +0.53 against the ~150 bp required** | Three independent deaths, two arithmetic: the "exhaustion exit" is a ratchet in costume (W = 1.088 vs assumed 3.0); R = 0.9 × an ATR frozen at t−12 puts a 40–80 bp stop inside a bar printing 100 bp+ (L ≈ 1.8–2.5 R, not 1.35 R); friction charged at 12–20 bp when the repo's frozen number for this order shape is 25/50 bp. **The proposed salvage census is pre-answered by sign-flipping the depth-q result — close it, don't run it** |
| SIZE #7 Lookback Exile (standalone timing edge) | real-OHLC **−0.038 R/trade** 2023–26; quoted W = 10.97 R → 5.45 R real → **3.16 R modern**, below its own 3.5 R blocking floor | The close-only prior was an artefact; measured on real OHLC the modern-regime expectancy is negative and the win multiple breaches its own pre-registered floor |
| SIZE #7b Lookback Exile's **listing-age effect** | in-sample **+0.896 R young vs −0.162 R mature** (1.06 R gap); modern fat-tail ratio 0.96% vs 0.24% | The clearest positive sub-component in the SIZE round, and **not** wrongly discarded — already filed as salvage item 7, a cross-sectional **conditioner / risk-shaping input**. It cannot certify as a mean: the top 5% of trades contribute 118% of total R, effective n ≈ 1–1.7 forty-R trades/yr, and normal-theory SE understates a tail-carried mean by 1.5–2×. A distribution-shape claim, which per this programme's own rule survives *as a conditioner, never as a standalone timing edge* |
| SIZE #8 Unlevered Ascent | baseline **sign-flips on real OHLC**: 6.11 R → 2.20 R, expectancy **−0.162 R/trade**; power 1,512 months | Negative under correct measurement, and 126 years to resolve |
| SIZE #9 Regime Ignition (gated arm) | its own pre-registered Gate 0 fired **with the sign inverted**: gated **−0.094 R/trade**; the breadth gate moved mean win −1.47 R where its rule required +1.00 R | Cleanest self-falsification in the round — the conditioner that is its entire original content makes the trade worse |
| SIZE #9b Regime Ignition **ungated control** | in-sample **+0.305 R/trade** | The filter-OFF null arm: zero original content (plain unconditional crypto breakout + trailing stop), MFE-derived win the ratchet can't pay (max trade +146 R → +31 R once measured), no cost charged, 240 months to resolve. Value is as **method evidence** — a control whose success falsifies the treatment worked as designed |
| SIZE #1 Leverage-Fuel Convexity | **never testable** — expired-option prices exist in no free archive (Deribit chart endpoint → no_data; last_trades include_old → []; expired instruments returns 56, all from one expiry). Break-even moves 26.2% → 30–33% once the live 10–17% wing spread and the 12.5%-of-premium fee cap are charged | A data-existence wall, plus a design that declared **no Fuel-off control arm**, making its originality claim untestable by construction. Its pre-registered "+5 pp pass" would not have been tradeable |
| SIZE #3 The Named Ladder | never run; capacity overstated **25–100×** — Hyperliquid `l2Book` returns exactly 20 levels/side, all inside ±1%, so the "±1% band notional" denominator is truncated by the **API cap**, not the band | Orphan Flush's depth-denominator hole re-opened on a new venue: signal and capacity claim are both manufactured by the level cap. Independently pre-killed by the HLP tape census — 2,000 liquidator fills on 2025-10-11 averaging **$173 each** carrying a twapId, with the largest positions assumed by HLP off-book: **the biggest forced-flow events supply the LEAST price impact** |
| SIZE #4 Mandated Overwrite Discount | **premise falsified by filing** — TSLY's NPORT-P shows the fund short 21,819 calls at 380–390 and **LONG 21,819 at 397.5–407.5 same expiry**: it writes a call *spread*, net premium 0.53% of NAV. Per-line supply 0.37–1.01× OI, not 2–5× | The model-free parity estimator is identically **0** — a 12% call-only "discount" would be a riskless conversion, not a mispricing — and the only estimator that could see the effect (fitted-smile IV) is the archetypal artefact the design bans |
| SIZE #5 Unhedged Unlock | never run; event rate overstated **3–8×** (123–308 events total across 370 protocols and all of 2021–2026, of which **6–15/yr are tradeable**); magnitude 1.2–3.0%/yr; power 100 months | Killed partly on the round's own life-changing-**magnitude** mandate, which under the honest lens is normally a revive class — but 6–15 tradeable events/yr against a 100-month requirement can *never* certify and no measurement of the sign exists. Its real output is the census, which pre-kills every future unlock-timing candidate |
| SIZE #6 Above the Pin | never run; **flow sign INVERTED** by the same NPORT-P call-spread finding; part of the flow is FLEX (strikes 405.01 / 410.01) that never prints on the lit book; power 680 months | The mechanism runs the other way than assumed. Killed by reading the filing |
| SIZE #10 Passive Float Delta | never run; buys the documented net-issuance anomaly **backwards**; power 65 months | Sign-inverted against a documented anomaly, plus a 13F/13G **double-subtraction bug** (BlackRock/Vanguard/State Street file 13G on the same shares they report on 13F) that biases the float denominator down and the trigger up — the estimator manufactures its own fires |
| SIZE #11 Vertical Float | the entire claimed +9.8%/event is **one invented decile at +95%**; strip it and the design's own arithmetic gives **+0.014 R ≈ 0** | Textbook assumed-tail-decile kill, and the trigger simultaneously selects names carrying four documented **negative** return predictors |
| SIZE #12 The Benchmark Hour | **no valid estimate can exist** — the SEC permitted in-kind creation/redemption for spot BTC/ETH ETPs on 2025-07-29 (release 2025-101) and IBIT has flipped. The entire 490-session design window sits inside a regime that no longer exists | The write-up names in-kind approval as its own retire trigger, and that trigger had **already fired thirteen months before the design was written**. No out-of-sample period will ever accrue. Its slippage-sampling method was worth copying, and already has been |
| SIZE #13 Par-Claim Ladder | the biggest cascade ever observed pays **+5.3%**; 14 clusters measured where 120–150 were asserted | A correctly-priced tail — i.e. exactly the STAYS_DEAD class: collect +5.3% in the worst cascade on record, lose the principal in the first genuine de-peg. The premium is small *because* it compensates a loss the sample has not yet drawn. It is a written solvency put |
| SIZE #14 Cascade Basis Snap | sign **never measured**; arrival rate **3 clusters in 4.6 years** against the design's own "DEAD below 22" | Fired its own pre-registered arrival-rate gate by 7×, so it can never accumulate evidence in this programme's lifetime. Its only free data source is the artefact generator: the DefiLlama daily cross-source join produces **−1,760 bp "discounts"** that are pure timestamp mismatch on assets moving 5–15%/day |
| SIZE #15 The Queue Is The Stop | never run; fire rate overstated **5–15×** (2.8/yr measured on the nearest real instrument) | The cheapest data path is a pure artefact generator — a daily snapshot joined across two independent sources on a 5–15%/day asset. Any backtest measures the join, not the market |
| SIZE #16 Clamp Excess | **no population**: the frozen rule fires **zero** times in 166 days — 12 clamped symbol-windows in 34,280 prints, peak cross-sectional breadth 2.5% against a rule needing 50 pp (assumed 40–70 episodes/yr) | The switch is never thrown; there is no estimate to be strict or lenient about. Salvage only: funding caps are 0.300%/8h for BTC/ETH, 0.375% for SOL/XRP/BNB, 2.000% for 685 of 760 symbols, and clamp state is free to recover as `fundingPrint < premiumTWAP + interest` |
| SIZE #17 Pin Release | measured EV **−57% to −80%/yr** | The most decisively negative candidate in the round: it systematically buys overpriced convexity |
| SIZE #18 Roll Shadow | never run; **zero break-even margin by its own arithmetic**, and the stated mechanism does not imply the stated trade | Same family error as the Fragmented Roll Calendar kill: "the concession is a permanent step down in the fund's NAV" is wrong — if the index is computed at the distorted settlement then the fund's NAV is too, so no relative step ever appears |

### Memecoin programme
| edge | held-out number | why it stays dead |
|---|---|---|
| Exit-rule family (26 rules, 2 channels, 16 TP×deadline cells) | **−18.94% per position, t = −16.2** | Sixteen sigma the wrong way with every cost lever bounded on data already held: **zero transaction cost → −16.89%, infinite size → −16.69%, perfect liquidity → −12.78%**. The failure is the 45%-win-small / 55%-lose-big shape |
| Cashback / rebate capture | **−5.4% of traded volume** for the largest observed rebate-farming wallet (−51.56 SOL on 951.77 SOL, 35% winners) | A rebate is a cost reduction, and the zero-cost bound already grants a 100% rebate on everything — trading entirely free still loses 16.89%. The "97% concentration" that made this look like someone's business was retracted as a wrong-field error (in-window top claimer is 12%) |
| LP provision to graduated PumpSwap pools | **0 bp of deposit** — median 0.00015 SOL of fees on 0.334 SOL of pool volume against an 84.99 SOL deposit, across 33 pools | The fee numerator rounds to zero while the LP carries full memecoin inventory risk. **No non-protocol wallet ever deposited or withdrew in the entire window** — the market's own verdict on the same arithmetic |
| Launch sniper (0.1 SOL, direct RPC, t0+1/2/4 slots) | median net **−10.9M to −11.2M lamports on a 100M-lamport position (≈ −11%) in all 18 frozen groups**; −15.0M stressed; 96.5–98.5% of cells ≤ 0 | Pre-registered before any figure and priced with per-launch decoded fee schedules. The median cell's book absorbs an exit of **12–15 lamports**, ~7 million times smaller than the tested position; only 9.9–17.9% of cells reach the 0.1 SOL ceiling at all. **Winning the HFT race makes it worse** — landing probability only scales exposure to a negative-median, mostly-unexecutable opportunity |
| PUMP token "own the house" revenue share | nine months of the venue directing **100% of > $1B** of protocol revenue at the token, and the price is **below its launch price** | The cleanest kill in the corpus because it is not our backtest at all — the venue ran the experiment itself at full scale, routed the entire fee stream (the thing our own structural finding says *is* the house edge) into the token, and the holder still lost |
| Migration arb (curve final price vs pool opening price) | **+3 bp gross**, 82/82 one-directional, zero dispersion → **−90 to −297 bp net** of the cheapest toll | Sign-perfect and still dead: 3 bp is a deterministic migration rounding convention, ~90× too small to clear the cheapest toll on the venue |
| Trailing-stop right-tail instrument (10% give-back, t0+200, real 125 bp fees) — **the cluster's only positive point estimate** | **+0.482%/position net**, n = 1,978, t = **+0.50**, 95% CI [−1.43%, +2.39%], bootstrap **67%** above zero; largest single position = **138% of total profit**; DSR 0.176 | Checked hardest because it is the T3 shape on paper and **is not the T3 shape in fact**: T3 is t = 2.73 with 99.5% bootstrap-positive; this is t = 0.50 with 67%, and its observed Sharpe (0.01114) is **below** the expected-max from sweeping ten meaningless parameters on pure noise (0.01854). Needs ~30,965 positions (≈8 windows) to distinguish from zero. Independently fails on capacity: at face value Kelly = 2.57% → a **3.9 SOL** maximum bankroll returning a median ×1.042 over 1,000 trades (≈0.16 SOL), with 44% of campaigns ending down. *What survives is the paired instrument finding — trailing beats fixed by +2.7 pp, 5 folds to 0 — a transferable rule-shape fact, not an edge* |
| Patient entry / entry-delay filter (enter at t0+5000) | gross **+2.70%** at t0+5000 (buy-and-hold −10.48% → +1.27%); best held-out searched edge 0.86% (in-sample 2.48%) against a **~3.0% round-trip bar** → net **−0.30% to −2.14%** | The strongest single non-cost effect the programme found — monotone in delay, genuinely causal, no lookahead — and it still lands below the bar (2.57% venue fee at 125 bp × 2 legs + ~0.46% irreducible transaction cost after legitimate rent reclaim) |
| Cheap-tier (25 bp) graduated-pool config — the 7 bp near-miss | held-out gross **0.86%** against a **0.93%** all-in bar (0.50% fees + 0.22% measured slippage + 0.21% txn) → **−0.07 pp net, before any search-max haircut** | The closest thing in the cluster to a strictness kill, failing honestly three ways: already negative before haircuts; 0.86% is the **maximum of a feature/threshold search** whose in-sample twin was 2.48%, so honest expectation is lower; and it **splices an edge measured on BONDING CURVES onto a fee measured on GRADUATED POOLS**, two populations that never met. 72% fee persistence measured on 18 pools — the 28% that turn expensive pay 95–125 bp on the exit leg alone, larger than the whole edge |
| **Deadness screen** (largest-buyer share ≥ 0.95 at t0+60) as a source of return | **0 return by construction** — it is a classifier: unexitable rate 35.3% base → **13.0%** among passed tokens, 69.7% precision / 77.7% recall, +52.4 pp train vs +56.7 pp test (no shrinkage), permutation p = 0.002 both tails, replicated on a different corpus (n = 606, +46 pp, p = 0.000) | STAYS_DEAD only in the sense that **it never was an edge and does not become one**. It avoids a class of guaranteed losses at a real cost (18% of genuinely exitable tokens discarded). It is the one thing in this cluster that is alive, correctly frozen, and already under a blind window-2 test — **it stays a forward-test candidate as a FILTER and must never be re-labelled as alpha.** Applying DSR to it would report a failure that does not exist |
| Deadness screen **combined with an entry** | bounded above at **−12.78%/position, t = −13.2** — the ceiling from deleting **all** never-sellable curves, i.e. a hypothetical screen with 100% recall *and* 100% precision | Answered by a dispositive bound, not needing a re-run: B19N/B19P delete every never-sellable position outright and the exit family still returns −12.78% at 13σ. The bound argument is airtight (a never-sellable curve has no buyers, so under real liquidity it exits near the floor; "exits at a large profit" cannot occur because profit requires buyers). **One honest gap not papered over:** that bound is computed on the B19K +6%-TP family, which B19Q later showed was the wrong instrument, so screen × **trailing-stop** was never computed — but no committed harness exists for the B19Q trailing-stop analysis (ad hoc, not preserved), so it is not a cheap re-run, and the combination inherits the same 3.9 SOL Kelly capacity wall regardless of which way the mean moves |

---

## 3. NEEDS-RERUN

Exactly one edge in 86 warrants an expensive re-run, and it is **not** recommended at current priority.

**T21 · VRP harvest via DELTA-HEDGED SHORT STRADDLE** (the genuinely neutral expression, which the
put-write kill explicitly does *not* settle).

- **Status:** never measured in this repo. No point estimate of any kind exists. Sign genuinely unknown.
- **The premium it targets is real and powered:** implied − realised = **+4.00 vol pts/month, t = +13.14**
  on 438 non-overlapping months; held-out 2022+ **+3.21 pts, t = +3.95**. The put-write result kills a
  *67%-long-equity wrapper*, not the premium.
- **What to run:** a delta-hedged short-straddle book on SPX/SPY options with an explicit hedging-cost
  model (discrete rehedge band, gamma-scalping loss, bid-ask on the option legs at retail size),
  benchmarked against T-bills + 1.00 pp/yr, pre-registered before the data is touched.
- **What it costs:** **paid data.** The repo holds only 2.5 years of OPRA bars, and T10's own arithmetic
  says an S = 0.8 claim needs **12.2 held-out years**. So this needs a multi-year paid options dataset
  (see DATA_PURCHASE_SCOPE.md) plus a hedging-cost model that does not currently exist.
- **Prior:** the literature's own finding is that continuous delta-hedging consumes most of the premium
  at retail size.
- **Recommendation:** **do not spend on it now.** It ranks below finishing the L3/L4 specs and standing
  up the T12-S2 leg, all of which cost zero data dollars. Revisit only if the forward basket certifies
  and there is budget for a data purchase.

Two items explicitly **closed as pre-answered** rather than queued (saving the runs):
- SIZE #2 Cascade Relay's proposed "salvage census" — answered free by sign-flipping the already-measured
  depth-q result (+11 bp gross at t 0.53 where ~150 bp is needed).
- Memecoin "screen × trailing-stop" — not a cheap re-run (no committed harness), and capacity-walled
  either way.

---

## 4. RECOMMENDED BASKET1 CHANGES

Current state of `research/trading_bot/BASKET_FORWARD_FROZEN.json`:

| slot | id | status |
|---|---|---|
| L1 | T3 | ACTIVE |
| L2 | ETFRV | ACTIVE |
| L3 | DUALCLASS | PENDING_SPEC |
| L4 | T7 | PENDING_SPEC |
| — | T13 vol overlay | installed as the sizing sleeve (T4 live, sessions_settled = 0) |

### Recommendation, in priority order

**1. Add L5 = T12-S2 CEF discount-level tilt (borrowable-short, H=4). Highest priority. ★**
It is the strongest revive in the corpus on held-out evidence (t = 3.51, DSR **0.9971 already deflated
over all six declared trials**, permutation p = 0.0005, block-bootstrap P(>0) = 0.9999 over 29
*independent* rebalances, and a positive disjoint design window), and it is the **most diversifying
leg available** — monthly horizon, CEF universe, discount-convergence mechanism, correlated with
neither T3's overnight book nor ETFRV's intraday identical-claim fade. Free data, retail rail, and a
live forward panel is the only instrument that fixes survivorship **and** point-in-time NAV
simultaneously — no further backtesting can. Freeze the spec at: ~36 long / ~36 **borrowable** short,
price > $5, 4-week hold, CEFConnect `/api/v3` weekly discount snapshot, Alpaca execution, borrow
charged at realised rate (not the 33 bp ETB floor), sized at low single-digit $M capacity.

**2. Finish the L3 DUALCLASS spec.** Already committed; the held-out number now exists (+18.4 bp/RT,
t = 2.13, all 18 grid configs positive). **The spec must screen the short leg to easy-to-borrow** —
at HTB rates the edge is −45 bp, which is the difference between an edge and a loss.

**3. Finish the L4 T7 ex-open spec.** Already committed; positive in both halves, executable on the
M0-verified auction rail. Size it small — capacity is $100k–$600k of book and it shares the overnight
session factor with L1, so it is a satellite rather than a second anchor. Note the taxable-account
IRC §1211(b) problem in the spec even though it is irrelevant to a paper test.

**4. Add L6 = ORB no-stop residual — as a REDUCED-BUDGET / logging-only leg.**
It is the only genuinely *session-diversifying* candidate (the intraday complement to T3's overnight
leg, ρ ≈ 0.02 between the two SPY legs), costs nothing to log because the harness, the 2.4 GB cache
and the MOC rail already exist, and is positive net of **tick-measured** cost in both windows. But
t = 1.06, two of four full held-out years are negative, the unconditional result collapses to
Sharpe 0.15 once the 2026 stub is dropped, the relvol threshold is post-hoc with a non-monotone
curve, and a no-stop book has an unbounded intraday tail. **Freeze the threshold and weighting in
advance, cap its risk budget below the market-neutral legs, and treat it as a hypothesis test rather
than an allocation.**

**5. T23 liq5m perp carry — DO NOT add to BASKET1; escalate to the owner as a venue question.**
The measurement is the strongest in the corpus (+15.05 pp/yr, t = 3.58, DSR 0.9977, all five gates
cleared, 3× cost stress still +9.5 pp/yr) and it is the only true portfolio diversifier — but the
instrument is Binance USD-M perps + Binance spot, **not legally reachable by US retail**. That is a
real-money / venue gate, not a research call. Recommendation: **stand up a free paper shadow log** on
the cached panel so the forward record accrues, and put the venue question to the owner separately.

**6. Nothing else changes.** The T13 vol overlay stays as the sizing sleeve (never counted as a leg —
its incremental paired-excess Sharpe is ~0.13 at P(>0) = 0.84). The memecoin deadness screen stays a
**filter** under its existing blind window-2 test and is never re-labelled as alpha.

### Selection-inflation accounting — stated honestly

This pass searched **86 killed edges** and surfaced 7 revives. That is a search, and the basket's own
gate is designed to price exactly this:

- `combined_gate.declared_trials_now` must rise from **2 to 6** once L3–L6 stand up (the frozen file's
  own rule: "= number of legs ever stood up in this basket family; retired/killed legs keep counting
  forever"). That mechanically raises the DSR bar every leg must clear.
- Every backtested number in §1 is a **selection-inflated upper bound**. The programme's own measured
  design→held-out shrinkage is ~4.2× (dual-class) and the realised-Sharpe prior for the basket is
  **0.3–0.6, and could be zero**.
- Four of the seven revives were revived on a *held-out window that had already been spent or was
  spent by this pass*, so none of them has faced a genuinely frozen forward window. That is precisely
  what BASKET1 is for, and it is why every new leg needs its **own pre-registration freeze** before it
  logs a single row.
- Honest counterweight in the other direction: **T17 ORB is the case where a positive t = 2.33 with
  PSR(1 trial) = 0.9931 was correct to kill** — tick measurement took it from +1.088 to −1.078 Sharpe.
  The lens cuts both ways, and this pass applied it both ways.

### Corrections to the existing record that should propagate to FINDINGS.md

1. **T11_RESULT.md §2** — "it loses with every cost switched off, this is an economics death" is
   **wrong**. The published −0.827% is a payoff-measurement artefact of four feed defects; repaired,
   the same rule is +1.418% (t = 3.28). T11's *conclusion* (tail-priced, stays dead) is right; the
   reasoning that reached it is not.
2. **T10_RESULT.md §4b** — the lookahead-corrected B3 variant at 0.5× half-spread is **+0.11 bp/session
   (indistinguishable from zero)**, not "still negative". The correct held-out auction-rail number is
   +2.97 bp, not +1.48 bp.
3. **T7** — the ex-open variant's **design half is positive too** (+2.25 bp net, t = 2.99), which the
   T7 write-up never stated.
4. **Orphan Flush** — the "revived-then-died" narrative is wrong: the flattering proxy-q variant was
   **never** net-positive-with-confidence (t = 0.80 at central friction, negative at cascade-moment
   friction). It died on arithmetic, not only on the depth denominator.
5. **Coiled Leverage Expansion** — the +0.03 gate margin was **not** the kill; the in-sample net edge is
   ~zero on its own design window (deflated t ≤ 0.22).
6. **T12** — S2 was never killed by a number, and it clears its own pre-registered gates with DSR
   already deflated over all six declared trials.

---

*Ledger produced 2026-08-20. 86 edges examined · 7 distinct revives (10 revive verdicts) · 75 stay
dead · 1 needs an expensive re-run. Every number above is a backtest or a held-out re-run, not a
realised P&L; the only realised evidence this programme has is the BASKET1 forward log, which
currently has zero settled sessions.*
