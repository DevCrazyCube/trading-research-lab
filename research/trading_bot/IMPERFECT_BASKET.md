# The imperfect-edge basket — a re-audit of every killed edge, split by WHY it died

**What this is.** A re-audit of every trading edge this programme has killed, sorted into two piles we
have been conflating:

- **PILE A — MEASURED-NEGATIVE (stays dead).** The net-of-cost point estimate is ≤ 0, or it flips
  negative under the correct measurement, or the loss is structural. Revisiting these is wasted motion.
- **PILE B — POSITIVE-BUT-UNPROVEN (basket candidates).** The net-of-cost (or plausibly-net) point
  estimate is **positive**, and the edge was killed **only** for failing a *certainty* bar (DSR < 0.95,
  t < 2.80), a *power* bar (insufficient n / MDE > effect), or a *size/capacity* bar — **never for
  being negative**.

The thesis under test: **a portfolio of several weak-but-real positive edges can pay even though no
single one certifies.** Pile B is the candidate set for a **small forward paper-test**. The document
ends with the recommended basket and how to size it.

**The one honesty rule carried through both piles.** A positive point estimate that was reached by a
search is biased *upward* by exactly the selection that DSR/power gates exist to catch. So every Pile-B
number below is an **upper bound on the truth**, and the basket is a reason to **forward-test**, not a
reason to believe. Sizing reflects that.

*Sources: `FINDINGS.md` §5d–§5j; `EDGE_SHORTLIST.md`; `NONDIRECTIONAL_INCOME_SHORTLIST.md`;
`ORIGINAL_STRATEGY_SHORTLIST.md` / `_BROAD.md`; `SIZE_STRATEGY_SHORTLIST.md`; the T3/T7/T9/T10/T11/T12/
T13/T15/T17/T18/T22/T23/T24/T25 result files; `ORPHANFLUSH_*` / `COILED_GATE0_RESULT.json`;
`T25_BOX_PROBE.json`; `agent_graph/agenda.json`; `FORWARD_*`. Read-only; no orders, no backtests, no
commit.*

---

## 1. PILE A — measured-negative, stays dead

Each line carries the killing number so we do not revisit it. Grouped by why it is *structurally* dead.

### 1a. Negative net after real cost / flips negative under correct measurement

| edge | held-out point estimate (net or corrected) | why it stays dead |
|---|---|---|
| **ORB opening-range breakout (T17→T18)** | **net Sharpe −1.078**, −19.9 %/yr, 75 % MDD; tick truth **−0.479 R/trade, t −4.71** | The screen selects names whose quoted spread is ~half the risk unit (R/spread ≈ 2.1). Gross Sharpe 2.74 → −1.08 once the entry-bar stop-through rate is measured (0.487, not 0). Structural, not a gate technicality. The one positive sub-variant (+2.857) assumes a 0 % stop-through it does not have. |
| **T10 overnight-vs-intraday harvest** | gross +4.29 %/yr, but **break-even 0.37 bp = 0.26× one half-spread**; **−4.68 %/yr at 0.5 h** | The paired book turns **4.00× notional and sells 2.00× per session**; SEC §31 alone is 138 bp/yr. Dies at a quarter of one measured half-spread. The overnight/intraday asymmetry is real (SPY o/n Sharpe 0.72 vs intraday 0.28) but it is a risk-shaping *fact*, not a harvestable edge. |
| **T13 crash filter (SMA-100)** | **−9.65 pp maxDD *worse* than "just hold less"**, −1.66 %/yr; frictionless still −8.57 pp | Against the vol-matched de-risked buy-and-hold null it deepens the drawdown (a whipsaw, 10.5 yr underwater). Protects *inside* crashes, costs more *between* them. |
| **T11 cash-merger arb** | full book **−0.83 %/deal, t −0.985**, DSR 0.039, perm p 0.876; loses at **zero** cost | Killed by a **correctly-priced tail**, not friction. The cleanest 317 deals *do* pay +6.66 %/yr over T-bills — with a break-even deal-failure rate of **6.68 %**, inside the 5–10 % quoted band. The spread **is** the deal-risk premium. Also data-unreachable (no free announcement dates). |
| **T12 CEF discount *reversion* (primary form)** | **−0.27 bp/wk, t −0.08**, DSR 0.154, perm p 0.054 | 3 of 4 own-mean-reversion trials went negative out of sample. CEF half-spread **11.53 bp (99× SPY)**, break-even 10.6 bp, and even at *zero* cost only Sharpe 0.68. *(The discount-**level** trial is a different object — see Pile B.)* |
| **T7 ex-dividend, close-to-close (primary)** | **+0.84 bp/event, t +0.46**, DSR 0.076, all 8 design trials negative | Drop-off ratio 0.95, indistinguishable from 1. A near-zero mean with negative design trials, not a credible positive. In a standalone taxable account **−21.8 %/yr** on loss-usability. *(The ex-**open** overnight residual is a different, positive object — see Pile B.)* |
| **VRP harvest — put-write (T21 §4b)** | **−1.53 pp/yr vs vol-matched null, Sharpe −0.090**, β 0.674 | The variance premium is real, large and powered (+4.00 vol pts/mo, t +13.14) — but the retail put-write is 67 % long equity and loses to holding less. Its worst months are *worse* than the null's. The genuinely-neutral delta-hedged straddle is unmeasured and power-blocked (2.5 yr OPRA). |

### 1b. Carry family — one financing rate on several rails, all decayed to/below cash

| edge | net estimate | why dead |
|---|---|---|
| **Funding carry, BTC unconditional** | **−0.46 pp vs T-bills**; needs +1.47 pp for the tail | Below the risk-free forward. |
| **T22 leveraged BTC cash-and-carry** | spread f − r_b **−0.81 pp/yr, t −4.15** (942 days, 38 % positive); best +0.71 pp at 4× | You borrow to lever at the same rate the carry pays; +0.71 pp loses to a ~1 %/yr venue-failure base rate. |
| **T24 CME futures basis carry** | net-on-capital **+0.44 pp full sample, −0.75 pp today, −1.22 pp YTD**, t 1.31, CI [−1.21, +5.01] | Below its own MDE (4.45 pp) *and* negative today; frictions (1.62 pp) exceed the ~1 %/yr tail the CFTC rail removes. Roll drag −1.02 pp/yr. |
| **T25 cross-venue funding differential** | powered config **topN=20 −1.47 pp/yr, t −2.43**; best topN=3 +0.74 pp (t 0.53) | "The signal works and loses to T-bills." Halving the differential for double collateral, then subtracting 3.84 %, is what does it. Only the underpowered top-3 book is positive. |
| **Box spread / synthetic financing (SPX)** | executable **+0.06 %/yr = 3.65 pp BELOW T-bills** (mid +0.37 pp) | Four-leg bid-ask is several times the whole financing spread; the surface disagrees with itself by ~5.5 pp, ~15× the pickup. A rate level below cash. |

### 1c. Invented micro/vol strategies — signal vanishes under realistic fills

| edge | corrected estimate | why dead |
|---|---|---|
| **Orphan Flush** | **−10.99 bp/cluster gross under real book-depth, t −0.53**; net −31 to −61 bp | The apparent +42 bp existed only under a depth-free denominator; the real ±1 % depth denominator flips the sign before any cost. |
| **Coiled Leverage** | gate-0 fail: ratio mode **−2.31 %** below breakeven; W = 1.088 vs assumed 3.0 | The "3:1 payoff / 25 % break-even" spec is internally contradictory; realised win multiple is ~1.09. |
| **Cascade Relay (size round)** | gross EV **−0.18 R before friction**; mirror fade −10.99 bp/cluster | Stop sits inside one bar's noise; friction charged at the calm rate, not the 50 bp cascade-moment rate. |
| **Settlement-print concession (broad Pick 2)** | CME's own TAS basis trades **0–2.9 bp**, at/below the ETF round-trip | The market quotes the concession below our cost bar. |
| **Wrapper-redundancy RV (11 of 13 pairs)** | pooled **+0.83 bp ≈ friction floor** | 92 % of the +2.33 bp gross is two pairs (VOO/SPY, IVV/SPY) that are almost certainly borrow-/timing-arbitraged; the rest is noise. |
| **Pump "own the house" yield** | price below launch after 9 months / 100 % of >$1 B revenue | The experiment ran and failed. |
| **Trailing-stop / crash-filter *return* (crypto)** | DSR 0.176 / 0.224–0.341 — **below the chance ceiling** | Nine of ten filter lengths lose return vs holding. |
| **SIZE round (all 18)** | all `KILL`; measured ones negative — Lookback Exile −0.038 R, Pin Release **−57 to −80 %/yr**, Regime Ignition sign-inverted | Median power 126 months; "convexity you can measure on free data is not real convexity." |
| **Crypto invented kills (F1, C1, D1, E2, …)** | F1 **−2.56 bp sign-falsified**; C1 +3.22 bp < 11.7 bp floor; the rest negative-after-cost / data-unreachable | Enumerated in `ORIGINAL_STRATEGY_SHORTLIST.md`. |

### 1d. Negative *sign* even though the label said "underpowered"

| edge | held-out estimate | note |
|---|---|---|
| **T9 spin-off drift** | **−0.82 %/event, t −0.39**, CI [−4.9 %, +3.3 %] | Killed on power (MDE 5.51 % vs 2.40 % literature, 62 events) — but the point estimate is **negative**, so it fails the sign rule regardless. True value unknown; measured value negative. |

### 1e. No positive estimate exists (power-blocked before it was run)

| edge | status | note |
|---|---|---|
| **T15 PEAD** | never run; MDE **4.44 % vs 0.90 % gate**; SUE free for only 33.9 % of events | No held-out estimate at all, and the literature has large-cap PEAD at ≈0 since 2006. Nothing to put in a basket. Its only value is the free 8-K/XBRL **earnings-date calendar** for *avoiding* earnings in other edges. |

---

## 2. PILE B — positive-but-unproven (the basket candidate set)

Every row here has a **positive** net (or plausibly-net) point estimate and was killed for
**certainty / power / size**, not sign. Columns: the point estimate with sign, the honest uncertainty,
why it was killed, whether it is reachable at retail on free/cheap data, its rough standalone Sharpe,
and what family it belongs to (for the diversification check in §3).

### B1. T3 — end-of-day cross-sectional pressure reversal, held overnight ★ anchor
- **Point estimate (NET):** **+5.35 bp/night**, t **+2.73**, Sharpe **1.29**, cross-sectional label
  permutation **p = 0.0001**. Net = the 15:59 marketable entry already pays its ~1.4 bp half-spread;
  exit is the next opening auction. On the bounce-free closing-auction print the signal is +6.07 bp,
  t +3.10 — confirming it is not the bid-ask bounce.
- **Uncertainty / why killed:** **DSR = 0.9379 against a 0.95 threshold frozen first.** A *certainty*
  miss by 0.0121 — the cleanest Pile-B case in the programme. All eight design trials were positive.
- **Reachable at retail on free data?** **Yes, honestly.** Entry: a marketable order at ~15:59 (pays
  the spread, already in the number). Exit: MOO — and M0 measured **99.96 % fill at the official print**
  for the top-500-ADV universe. Data is free Alpaca SIP. **The caveat, stated plainly:** the *fully
  spread-free* both-legs-in-auction version needs the 15:50 MOC cutoff, and by 15:50 the signal decays
  to t = 1.38 — so we trade the +5.35 bp reachable version, **not** the prettier unreachable one.
- **Standalone Sharpe:** ~1.29 (held out); haircut for selection → assume ~0.6–0.9 realised.
- **Family / risk:** short-horizon liquidity-provision reversal; overnight gap risk (a paired control
  does not remove the gap). Directional-ish overnight equity exposure.

### B2. T7 — ex-dividend **overnight** residual (exit at the ex-date *opening* auction)
- **Point estimate (NET):** **+3.63 bp/event vs the same-day non-ex-dividend control, t +3.18**,
  permutation **p = 0.042** (+3.72 bp/day unpaired, t 3.29). Both legs auction prints → modelled spread
  zero.
- **Uncertainty / why killed:** **Exploratory** — it was *excluded from the declared grid*, so
  2022–2026 is **burned** for it and the significance above is not a clean frozen test. This is a
  *certainty/selection* kill, not a sign kill: the residual is real, it just has never faced a
  pre-registered window. **It needs a prospective forward test — which is exactly what the basket is.**
- **Reachable at retail on free data?** Yes — corporate-actions feed (free), close(cum) → ex-open
  auction. Tax is irrelevant to a paper test (and a tax-deferred account removes the objection live).
- **Standalone Sharpe:** not published; the residual is ~3.6 bp against ~2.4 bp of one-day portfolio
  noise → a per-event t ~3.2 implies a respectable but event-sparse Sharpe.
- **Family / risk:** ex-dividend overnight tax-clientele. **Partly overlaps B1** (both are overnight
  equity close→open moves) — the diversification credit is discounted for this in §3.

### B3. ETF-sibling pre-cutoff relative value (broad Pick 1)
- **Point estimate (NET, proposal-stage):** **+1.0–1.5 bp/pair-session** expected (pre-registered as
  the *smaller* of the range), sign positive (relative reversion between same-claim wrappers). The
  original −0.79…−0.91 close-print beta was **retracted before testing** as an errors-in-variables
  artefact; the surviving arm is the 15:45→close-print relative move.
- **Uncertainty / why killed:** **not yet run**, and at risk of a **size/capacity** death, not a sign
  death: the auction-coverage probe cut ~15 nominal wrapper spreads to **4–6 effective pair-sessions/
  day** (9 of 24 wrappers clear < $1 M in their own closing auction). A *paired, factor-neutral* return,
  so the `(2.80/S)²`-years power wall does **not** engage — it resolves on **compute, not calendar**.
- **Reachable at retail on free data?** **Yes** — both design (2016–2021) and held-out (2022–2026)
  windows are already downloaded on free Alpaca SIP; MOC/MOO accepted on the paper account.
- **Standalone Sharpe:** not stated; economics are marginal and **capacity-bound** (sub-T-bill on
  unlevered equity, so it must beat by-year T-bills + 1 pp to count).
- **Family / risk:** identical-claim relative value; **market-neutral by construction** → a genuine
  diversifier against B1/B2. Tiny dollar capacity.

### B4. Dual-class voting-premium relative value (two-timescale filter)
- **Point estimate (IN-SAMPLE, measured):** **+26.6 bp/trade mean, 61.8 % hit-rate, per-trade Sharpe
  0.125, book Sharpe 1.31** over 744 design-window round trips. Real structural anchor (identical
  cash-flow claims on the two share classes).
- **Uncertainty / why killed:** **shelved, not tested out of sample** — for *certainty/crowding*
  reasons: it is a **published** edge (Schultz & Shive 2010; Lamont–Thaler 2003), obs/day were
  overstated 4.2×, and it needs 55–61 months against 56 available, so this programme's typical 4.1×
  design→held-out shrinkage would likely erase it. Positive sign, killed on the expectation it won't
  *certify* — a textbook Pile-B profile.
- **Reachable at retail on free data?** Yes — dual-class pairs (e.g. GOOG/GOOGL and peers), free SIP
  data, retail execution.
- **Standalone Sharpe:** book 1.31 **in-sample** → expect heavy shrinkage; assume ~0.5–0.8 if real.
- **Family / risk:** dual-class relative value; **market-neutral pairs** → diversifier. Limited name
  count; crowded at the mechanism.

### B5. T12 — CEF discount-**LEVEL** tilt (the trial that did *not* die out of sample)
- **Point estimate (NET, held-out):** **+12.9 / +14.5 bp/week, annualised Sharpe +2.30 / +2.57,
  DSR 0.991 / 0.997** — consistent with its design window. This is the *raw discount level* form
  (trials 5–6), **not** the mean-reversion form that died.
- **Uncertainty / why killed:** it was **declared-but-not-primary** (selection), and diagnostics attack
  it hard: **81 % of both deciles carry over each rebalance** (it is a near-static tilt, not reversion),
  **about half the P&L is the NAV leg** (the assets, not the discount), 57 % of the short leg is
  shortable, and the panel is **100 % survivors** with ~27 % of the 2021 CEF population invisible. So
  the high DSR is real but the *object* may be a survivorship-flattered static value/beta tilt. Killed
  for needing its own survivorship-robust pre-registration (an owner scope call), **not** for sign.
- **Reachable at retail on free data?** Partly — CEFConnect NAV is free (1 yr daily / 5 yr weekly),
  CEF half-spread is 11.53 bp, **but** the 81 % carryover means turnover is ~19 %/wk, so friction
  (~4.4 bp/wk) sits well under the +12.9 bp gross. No auction rail; cross the continuous spread.
- **Standalone Sharpe:** 2.30–2.57 held-out **on a survivor panel** → discount heavily; a
  survivorship-robust reduced form is the only honest version.
- **Family / risk:** CEF value tilt — **carries market beta** via the NAV leg (β to SPY−AGG only
  +0.057, but ~half the return is the funds themselves). Diversifies the RV legs but is not neutral.

### B6. T13 — volatility-targeting overlay (a sizing sleeve, not an alpha)
- **Point estimate (NET ≈ gross):** **+0.66 %/yr CAGR and +7.25 pp of maxDD** vs the vol-matched null,
  standalone Sharpe **0.578 vs 0.520** (Δ +0.058). Positive-signed in **all four decades and all eight
  configurations**; cheap (0.86 round-trips/yr, 4× cost moves it 0.18 pp).
- **Uncertainty / why killed:** **certainty/power** — bootstrap p = 0.233, DSR 0.355, and the
  drawdown-claim resolution is one observation per *crash* (~3 usable), CI on the drawdown edge
  −3.68 to +13.01 pp. The **+7.25 pp headline is essentially 2008 alone.** Not a sign death.
- **Reachable at retail on free data?** Yes — daily SPY, slow turnover. **Already the sole strategy in
  forward paper testing** (`T4`, rule `T13-VOL-L60-T0.1-WMAX1.0`, running since 2026-08-17; no verdict —
  needs decades — and its live execution rail FG4 is at risk at a 5.07 bp shortfall).
- **Standalone Sharpe:** 0.578.
- **Family / risk:** this is a **market-beta timing/sizing overlay**, not a diversifying return stream.
  Its right role in the basket is to **size the aggregate book**, not to be a leg.

### B-ledger (positive-but-power-blocked, **excluded** from the executable basket)
- **T23 cross-sectional perp funding carry — +2.20 pp/yr over T-bills** (implied excess Sharpe ~0.714;
  design-window `liq20m_top3` +17.21 pp, Sharpe 1.67, t 2.81). Killed **purely for power** — held-out
  MDE 15.25 pp (6.93× the claim), window never spent — so by the sign rule it is Pile B. **But it fails
  the basket's execution test:** Binance.com perps are not US-legal, Alpaca cannot express either leg,
  capacity is $30–60 k (below the account), the venue-failure tail (~1 %/yr) is roughly the whole edge,
  and both known leakages flatter it. **Positive-but-unproven, and not executable here.** Kept in the
  ledger for completeness; **kept out of the basket** on accessibility + tail.

---

## 3. The basket — assembly, diversification, sizing

### 3a. Which candidates survive all four basket tests

A basket leg must be (i) positive point estimate, (ii) mutually diversifying, (iii) executable at retail
on free/cheap data, (iv) honestly sizable.

| candidate | (i) positive | (ii) diversifying | (iii) executable | (iv) sizable | in basket? |
|---|---|---|---|---|---|
| **B1 T3 pressure reversal** | +5.35 bp/night | overnight equity (anchor) | **yes** (15:59 mkt + MOO, M0-verified) | yes, top-500-ADV | **YES — anchor** |
| **B3 ETF-sibling RV** | +1.0–1.5 bp/pair | **market-neutral** (uncorrelated) | yes (data downloaded) | tiny ($ capacity) | **YES — RV leg** |
| **B4 dual-class voting** | +26.6 bp in-sample | **market-neutral** (uncorrelated) | yes | limited names | **YES — RV leg** |
| **B2 T7 ex-open dividend** | +3.63 bp/event | overnight (overlaps B1) | yes (auctions) | event-sparse | **YES — event leg (discounted)** |
| **B5 T12 discount-level tilt** | +12.9 bp/wk | value/beta (not neutral) | partly (11.5 bp spread) | survivor-caveat | **OPTIONAL — reduced form only** |
| **B6 T13 vol overlay** | +0.66 %/yr | market-beta sizing | yes (already live) | yes | **as the SIZING OVERLAY, not a leg** |
| B-ledger T23 carry | +2.20 pp/yr | crypto carry (would diversify) | **no** (US-legal + capacity) | no | **NO — excluded** |

### 3b. The diversification check (a basket needs *different* trades)

- **B1 and B2** are both overnight equity close→open moves → **positively correlated**. B2 is kept
  because its trigger (ex-dividend events) is orthogonal to B1's (last-10-min pressure), but its
  diversification credit is **halved** in the sizing below.
- **B3 and B4** are both *identical-claim relative value*, **market-neutral by construction**, and
  their realised correlation to the overnight legs should be low (different exposure, different clock).
  They are the genuine diversifiers and the reason the basket is more than "T3 twice."
- **B5** adds a **value/beta** stream (~half its P&L is the CEF NAV leg) — it diversifies the RV legs
  but *adds* market beta, which is why it is optional and reduced-form only.
- **B6** is not a leg; it is a **beta-timing overlay** that sizes the whole book down when realised vol
  rises. It correlates with the market direction of the aggregate, so it belongs on top, not beside.

Net: the basket has **two overnight-equity legs (correlated), two market-neutral RV legs
(diversifying), and an optional beta-tilt leg**, sized under one vol overlay. That is three roughly
independent risk sources, not five — honest, and still better than any single leg.

### 3c. Recommended forward basket (4 return legs + 1 overlay)

1. **T3 end-of-day pressure reversal** — anchor. Largest capacity, cleanest kill (DSR 0.9379), M0-verified exit.
2. **ETF-sibling relative value** — market-neutral diversifier; resolves on compute, tiny $.
3. **Dual-class voting premium** — market-neutral diversifier; different instrument from #2.
4. **T7 ex-open dividend residual** — event overnight; correlated with #1, weighted down.
5. *(optional)* **T12 discount-level tilt, survivorship-robust reduced form** — only if a
   survivorship-complete CEF panel is built first (owner scope call); otherwise leave out.
6. **T13 vol-targeting overlay** — sizes the aggregate book (already running as `T4`).

### 3d. Sizing — capacity-first, conviction-second, tiny in dollars

Because these are unproven and two are capacity-tiny, **size to generate observations, not P&L**, and
let **capacity, not conviction, set the dollar caps**:

- **Risk-parity across the return sources**, not the legs: give the two correlated overnight legs (B1+B2)
  **one** combined risk budget, and each RV leg (B3, B4) its own — i.e. ~1/3 of book risk to overnight,
  ~1/3 to ETF-sibling RV, ~1/3 to dual-class RV. The optional B5 draws from a separate small sleeve.
- **Dollar caps from measured capacity:** B3 and B4 are hard-capped by auction depth (ETF-sibling
  ~$1 M-per-wrapper auctions, only 4–6 pairs/day; dual-class limited names) → each runs at a **few $k
  gross**. B1 has room in the top-500-ADV auction pool. So the *dollar* book is dominated by B1 even
  though its *risk* budget is shared.
- **Keep most of the $100 k in T-bills** — that is both prudent for an unproven book and the correct
  benchmark every one of these edges must beat.
- **One vol overlay (B6) on the aggregate** — scale total gross down when trailing realised vol rises.
- **Pre-register the whole basket before it runs:** declared trial count = the number of legs, a DSR/t
  gate on the *combined* series, and a per-leg kill switch at net ≤ 0 over the forward window. Forward
  paper only; live execution stays owner-gated.

### 3e. What the basket is worth **if the point estimates are real** — and the caveat that dominates

If the legs realise their point estimates **and** the two market-neutral RV legs are genuinely
uncorrelated with the overnight legs, three roughly-independent risk sources each at a
selection-haircut Sharpe of ~**0.6** combine to roughly **0.6 × √3 ≈ 1.0**, and with the optional
value leg ~**1.1–1.3**. That is the *optimistic* number.

**The caveat is the whole point.** Every Pile-B estimate is an **upper bound**: selection bias inflates
each one, the two overnight legs are correlated (so the effective √N is smaller than the leg count),
the capacity-tiny legs cannot carry much risk, and B4/B5 are in-sample or survivor-flattered. A candid
expectation for the *realised* forward Sharpe is **~0.3–0.6**, and it could be zero. **This is precisely
why the basket must be forward paper-tested, not trusted** — the diversified small-book structure is a
way to *find out* whether several weak positives survive contact with a clean window, at the cost of a
few $k of paper risk and no certainty borrowed from any single leg.

---

## 4. One-line disposition of every edge audited

**Pile A (dead):** ORB (−1.08 Sharpe net) · T10 overnight harvest (−4.68 %/yr) · T13 crash filter
(−9.65 pp DD) · T11 merger-arb (−0.83 %/deal; tail correctly priced) · T12 discount *reversion*
(−0.27 bp/wk) · T7 close-to-close (+0.84 bp, DSR 0.076, negative design trials) · VRP put-write
(−1.53 pp/yr vs null) · BTC funding carry (−0.46 pp) · T22 levered carry (−0.81 pp spread) · T24 CME
basis (−0.75 pp today) · T25 cross-venue (−1.47 pp powered) · box spread (−3.65 pp vs T-bills) ·
Orphan Flush (−11 bp/cluster) · Coiled Leverage (W 1.088, ratio −2.31 %) · Cascade Relay (−0.18 R) ·
settlement-print concession (0–2.9 bp < bar) · wrapper RV rest (+0.83 bp ≈ floor) · PUMP yield (below
launch) · crash/trailing *return* (below chance ceiling) · SIZE round ×18 (all KILL) · crypto invented
kills (F1 −2.56 bp, …) · T9 spin-off (−0.82 %/event — negative sign) · T15 PEAD (no estimate;
undetectable + ≈0 for large caps).

**Pile B (basket candidates):** T3 pressure reversal (+5.35 bp/night, DSR 0.9379) · ETF-sibling RV
(+1.0–1.5 bp/pair) · dual-class voting (+26.6 bp in-sample) · T7 ex-open dividend (+3.63 bp/event) ·
T12 discount-*level* tilt (+12.9 bp/wk, survivor-caveat) · T13 vol overlay (+0.66 %/yr — as the sizing
sleeve).

**Pile B but excluded from the executable basket:** T23 cross-sectional funding carry (+2.20 pp/yr,
power-blocked) — not US-legal, capacity below the account, venue tail ≈ the edge.

---

*Read-only analysis. No orders, no new backtests, no purchases, no commit. Every Pile-B number is an
upper bound; the basket is a forward-test proposal, not a belief.*
