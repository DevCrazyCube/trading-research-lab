# INVENT-0823 — SINGLE-NAME & SECTOR DEALER-GAMMA / OPTIONS-FLOW — PRE-REGISTRATION

**Written 2026-08-23, BEFORE any design-window result was computed.** Committed before the
first backtest number exists. Research only; no orders, no money; free/cached data only.

---

## 1. Why this theme, given round 3 already killed SPY GEX

Round 3 (`INVENT_R3_MASTER.md` §5, ledger correction 2) established two things:

1. Free per-strike dealer-gamma data **is** computable — Alpaca serves expired OPRA daily bars
   from 2024-02-01, so cumulative per-contract volume is a legitimate open-interest proxy.
2. On **SPY at short tenor the textbook GEX sign-flip is structurally degenerate**: near-money
   gamma-weighted option volume is put-dominated on 97% of days, so dealers are *always* net
   short gamma, `A4_GAMMA_FLIP_LEVEL` collapsed to n=30 and `A6_CALL_WALL_RESIST` to n=0.

That degeneracy is an *index* fact, not an options fact. Index options are the hedging instrument,
so their flow is structurally put-heavy. Single names are the opposite: retail and overwriting flow
is call-heavy, and the call/put balance differs enormously **across names** (TSLA/PLTR/COIN vs
utilities vs sector ETFs). The cross-sectional dispersion in dealer-gamma sign that SPY does not
have is exactly the variation this theme needs, and it is un-worked. The theme is therefore a
genuinely new angle, not a re-run.

**Explicit non-goals** (banned by prior findings, will not be tested): single-leg regime
conditioning of an existing basket leg on a gamma variable (round 3, 4-for-4 harmful; round 5,
"gating destroys value" is the programme's most replicated negative); anything built on ETFRV or
T7 (exposed as artefacts in the 2026-08-23 v9 scrub); any signal whose fill price is the same
print as the signal price.

---

## 2. Data (frozen before design)

| item | choice |
|---|---|
| Option data | Alpaca `/v1beta1/options/bars`, 1Day, expired OPRA. |
| Contracts | Every **monthly (3rd-Friday) expiry** 2024-02 … 2026-08, calls+puts, strike ladder anchored at the underlying raw close E−60/E−25/E−5 days, ±20 steps at the listed increment ($0.5/<20, $1/<200, $2.50/<500, $5/<1000, $10 above). |
| History per expiry | `[E − 70 calendar days, E]` — so on any day *t* the front monthly (0–30 DTE) **and** the next monthly (30–60 DTE) are both observed. |
| OI proxy | Cumulative traded contract volume per strike from the start of the window through the close of day *t*. **This is a proxy, not OI**; there is no free OI history. Its known bias (it misses accumulation older than 70 days, and counts closing trades as opening) is documented, not hidden. |
| Underlying | Alpaca daily bars, `adjustment=raw` for the strike ladder, `adjustment=all` (split+dividend) for returns. |
| Universe | 34 liquid single names + 15 sector/broad ETFs = 49. All are top-decile ADV; **there is no illiquid tail in this universe by construction**, which is how the "just illiquid-name noise" question is answered structurally rather than by a post-hoc filter. |
| Greeks | Black–Scholes with a **flat per-(name, expiry, day) ATM implied vol** backed out from the nearest-to-money call and put closes. Flat-IV is a simplification; it is applied identically to every formula so it cannot favour one. |

**Universe list (frozen):** AAPL MSFT NVDA TSLA AMZN META GOOGL AMD NFLX AVGO JPM BAC XOM CVX
WMT COST CRM INTC MU PLTR COIN BA DIS UBER PYPL GS PFE JNJ T VZ ORCL QCOM CAT LLY / XLF XLE XLK
XLV XLI XLP XLU XLB XLRE XLC SMH IWM QQQ DIA EEM.

---

## 3. Windows (frozen; held-out is untouched until the design table is written)

| window | dates | purpose |
|---|---|---|
| **DESIGN** | 2024-02-01 … 2025-06-30 | every sign, threshold, tercile cut, horizon is fitted here |
| **HELD-OUT** | 2025-07-01 … 2026-08-21 | not read until the design table exists |

Roughly 350 / 285 trading days. The short history is a *known weakness of the theme* (free expired
OPRA starts 2024-02) and is stated up front: this theme cannot produce a 10-year track record and
any survivor is provisional on that ground alone.

---

## 4. Execution rail and cost (frozen)

* Signal is built from option bars through the **close of day t**.
* Entry is the **open of day t+1**; exit the **close of day t+1** (intraday leg) or the **open of
  day t+1+h** (multi-day leg). Signal and fill therefore never share a print, and are separated by
  a ≥17.5-hour gap.
* Costs, per side, from `EXECUTION_COST_WALL.md` §1: **1.0 bp** (auction rail 0 + 0.5 fee, rounded
  up), **3.0 bp** (Dyhrberg liquid retail taker 2.5 + 0.5 fee — the **primary** number for this
  universe), **5.5 bp** (the conservative sweep default). Break-even one-way cost is reported for
  every formula.
* Turnover is measured, not assumed.

---

## 5. The formulas (frozen list, N = 24)

Fitted in design: the **sign** of each signal and nothing else, except where a horizon is named.
No thresholds, no regime gates, no per-name parameters.

**A. Net dealer gamma level and change**
1. `G1_GEXNORM` — net dealer GEX ÷ 20-day dollar ADV, cross-sectional.
2. `G2_GEXZ` — within-name 60-day z-score of G1 (removes the name fixed effect).
3. `G3_GAMMA_REV_INTERACT` — −sign(GEX) × r₁d(t): long-gamma names fade yesterday, short-gamma names follow.
4. `G4_DGEX1` — 1-day change in G2.
5. `G5_DGEX5` — 5-day change in G2.
6. `G6_GEXFRAC` — net GEX ÷ gross GEX (a scale-free gamma-balance number).

**B. Pin / magnet**
7. `P1_PIN_DIST` — (max-gamma strike − S)/S.
8. `P2_PIN_X_GEX` — P1 × positive part of G1 (continuous interaction, no gate).
9. `P3_PIN_OPEXWEEK` — P1 restricted to the 5 sessions ending at the monthly expiry (the mechanism's own window, not a fitted gate).
10. `P4_PIN_EXPIRY_DAY` — P1 on the expiry session itself.

**C. Gamma-flip level as support/resistance**
11. `F1_FLIP_DIST` — (S − K*)/S where K* is the zero-crossing of the simulated net-gamma profile.
12. `F2_FLIP_CROSS` — 3-day change in sign(S − K*).
13. `F3_WALL_ASYM` — (distance to call wall − distance to put wall)/S.
14. `F4_FLIP_X_GEX` — F1 × G6.

**D. Put/call OI-skew level and shift**
15. `S1_CPRATIO` — log(gamma-weighted call OI ÷ put OI).
16. `S2_DCP1` — 1-day change in S1.
17. `S3_DCP5` — 5-day change in S1.
18. `S4_PUT_SURGE` — put volume in [0.90S, 0.97S] ÷ its own 20-day mean.
19. `S5_CALL_SURGE` — call volume in [1.03S, 1.10S] ÷ its own 20-day mean.
20. `S6_SKEW_TILT` — (OTM call gamma-OI − OTM put gamma-OI) ÷ total gamma-OI.

**E. Charm / vanna / expiry cycle**
21. `C1_CHARM` — aggregate dealer charm (∂Δ/∂t), the mechanical per-day hedge flow into expiry.
22. `C2_VANNA` — aggregate dealer vanna × the 5-day change in ATM IV.
23. `C3_OPEX_ROLLOFF` — front-monthly share of total gamma, traded the session after monthly expiry.
24. `C4_PREOPEX` — front-monthly net gamma × (1/DTE) during the pre-expiry week.

**F. Controls run alongside (not counted in N, they cannot be "wins")**
* `R_*` residualised twins of the best 3 signals, orthogonalised on r₁d and r₅d of the underlying,
  to prove the signal is not short-term reversal in a gamma costume.
* Sector-ETF-only and single-name-only splits of any survivor.
* `|GEX|` → next-day realised range: a **mechanism diagnostic**, reported, never traded.

---

## 6. Bars a formula must clear (all four, in this order)

1. **Structural non-degeneracy** — if the signal has no cross-sectional dispersion (the SPY failure
   mode: sign constant on >90% of name-days), it is recorded as degenerate and not scored.
2. **Gross design bar** — |t| on the design window must exceed **both** (a) the analytic
   multiple-testing bar for N = 24, and (b) a **size-matched placebo null**: the max |Sharpe| over
   24 placebo formulas built by **ADV-slot signal permutation** (permute the signal within
   ADV-decile slots each day, preserving the cross-sectional size and turnover profile;
   rotate-the-returns is known-broken and is not used), 2000 draws. Both nulls reported.
3. **Fill realism** — a one-day-gap re-entry placebo (enter at t+2 open instead of t+1 open). A
   signal that survives only at the immediate fill is microstructure bounce and is killed.
4. **Held-out net** — net Sharpe positive at the 3.0 bp/side primary rail on the untouched window,
   with the sign frozen from design.

A formula is **real** only if it clears 1–4. Anything else is reported as noise, with its number.

---

## 7. Pre-committed honest-zero clause

If no formula clears, the deliverable is the negative plus the mechanism diagnosis: *why* the
single-name/sector gamma proxy fails (degeneracy, proxy error, cost, or absence of signal), stated
with the numbers, and a ledger entry telling round 4+ not to re-test it. The prior from five
consecutive sweeps is that this is the likely outcome, and it is an acceptable one.
