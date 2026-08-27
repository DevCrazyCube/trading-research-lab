# FORMULA SWEEP — MASTER SYNTHESIS

**380 formulas, 6 themes, one pooled multiple-testing correction.**
Written 2026-08-20 as the cross-theme judge over the six wide sweeps. Per-theme reports:
`SWEEP_overnight_equity.{md,json}`, `SWEEP_intraday_rv.{md,json}`,
`SWEEP_crypto_perp_microstructure.{md,json}`, `SWEEP_xll_leadlag.{md,json}`,
`SWEEP_futures_term_structure.{md,json}`, `SWEEP_calendar_session.{md,json}`.

---

## 0. THE ONE-PARAGRAPH ANSWER

Of 380 formulas, **one** clears the pooled noise bar on its design window, is net-positive out of
sample after realistic costs, survives a capacity cut, and is **not** already in BASKET1:
**`XS_GLSR_Z`** — fade the z-score of Binance's global retail account long/short ratio,
cross-sectionally, on perps. Everything else either fails the pooled bar, dies on cost, dies on
capacity, or is a restatement of the T3 overnight reversal that is already leg L1 of the frozen
basket. **Four of the six themes are pure noise** at the pooled bar. The recommendation is
**one new basket leg**, subject to its own pre-registration freeze.

---

## 1. THE POOLED NOISE BAR

### 1.1 Why the per-theme bars are all too low

Each theme built its own joint-null max statistic (shuffle / block-bootstrap / circular-rotation /
sign-flip, always re-scoring the whole family per replicate so within-theme correlation survives).
Those bars are correct **within** a theme and wrong **across** the programme: the search that
actually happened was *six* such searches, and a winner was selected by looking at all six.

Two corrections, and they agree:

**(a) Analytic, in Sharpe-standard-error units.** With N = 380 independent tries the expected max
under the null is `sqrt(2 ln 380)` = **3.447 SE**.

**(b) Empirical, correlation-aware.** Fit a Gumbel to each theme's reported null-max distribution
(from its mean and p95), studentise by that theme's own single-formula null SD, and Monte-Carlo the
max over all eight blocks (400k draws):

| pooled max over 380 formulas | studentised (Sharpe-SE) units |
|---|---|
| mean (the expected-max bar) | **3.443** |
| p50 | 3.201 |
| p90 | 4.668 |
| p95 | 5.351 |

The empirical pooled expected-max lands on **3.44 SE**, essentially identical to the analytic
3.447 — the within-theme correlation that deflates each theme's own bar is offset by the six
independent bites at the apple. **3.44 Sharpe-SE is the headline pooled bar.**

### 1.2 The operative per-theme bars (FWER 5% over 6 themes)

For a decision rule I use the stricter, more defensible construction: a candidate must sit at the
**(1 − 0.05/6) = 99.167th percentile of its own theme's joint-null max**. The theme null already
absorbs within-theme multiplicity; Bonferroni over the six theme-maxima absorbs the rest.

| theme | N | statistic | within-theme p95 | **POOLED BAR** | best design | clears? |
|---|---|---|---|---|---|---|
| Overnight equity (T3 family) | 51 | t | 2.95 | **3.68** | t +6.45 (A08) | **YES** (many) |
| Intraday equity/ETF RV | 98 | net Sharpe | 2.01 | **2.54** | −0.27 | no (0 of 98) |
| Crypto-perp microstructure | 56 | gross Sharpe | 2.80 | **3.36** | 4.94 (XS_GLSR_Z) | **YES** (5 of 56) |
| Lead-lag — equity daily | 31 | Sharpe | 1.25 | **1.56** | 2.12 (P2) | yes on design only |
| Lead-lag — crypto 5m | 32 | Sharpe | 1.86 | **2.31** | 51.35 gross (C1) | yes gross / no net |
| Lead-lag — addendum | 11 | Sharpe | 1.25 | **1.52** | 3.04 | gross-only artefact |
| Futures term structure | 49 | Sharpe | 1.51 | **2.06** | 0.80 | no (0 of 49) |
| Calendar / session | 52 | \|z\| | 3.27 | **3.89** | 3.385 | no (0 of 52) |

Three themes produce **zero** formulas above their pooled bar. One (lead-lag) produces winners that
clear only on a gross basis and invert to −200 Sharpe on cost. Two produce genuine clearances.

### 1.3 What the widening cost

The bar moved a long way. T3 was killed at 8 declared trials with a deflated Sharpe of 0.9379 against
the repo's frozen 0.95 gate. At 51 trials the best overnight formula's DSR is 0.8297 (generous input)
/ 0.0000 (López de Prado's own trial-dispersion input). At **380** trials the bar is past everything
the overnight theme found. That is the honest cost of a wide search: it prices in the searching.

---

## 2. FULL DESIGN DISTRIBUTIONS (all 380, nothing dropped)

| theme | min | p25 | median | p75 | max | # net-positive |
|---|---|---|---|---|---|---|
| Overnight equity (net SR, 51) | −2.53 | −0.10 | +1.65 | +2.08 | +3.65 | 35 |
| Intraday RV (net SR @1bp, 98) | −315 | −93.0 | −28.2 | −10.1 | **−0.27** | **0** |
| Crypto perp (gross SR, 56) | — | — | — | — | +4.94 | 15 above own bar |
| Lead-lag crypto 5m (gross SR, 32) | −20.25 | −0.67 | +1.36 | +12.24 | +51.35 | 0 net |
| Lead-lag equity (gross SR, 31) | −2.12 | −0.32 | −0.05 | +0.43 | +2.12 | 1 marginal |
| Futures TS (net SR, 49) | −0.69 | −0.03 | +0.14 | +0.28 | **+0.80** | 1 above E[max] |
| Calendar (\|z\|, 52) | — | — | — | — | 3.385 | 1 above E[max] |

The shape worth staring at is the **intraday RV** row: 50 of 98 formulas beat the *gross* noise bar
and the gross signal replicates out of sample (+6.86 design → +5.41 held out), yet **zero of 98** are
net-positive at 1 bp/side. The best formula can bear 0.031 bp per unit of turnover; the headline rung
charges 1.15 bp. 82 of 98 cannot cover the 0.15 bp SEC-31 + FINRA-TAF pass-through alone. That is not
noise — it is a real effect that is 37× too small to touch as a taker. It is also the sharpest
statement in the whole programme of why "beats the noise bar" and "is an edge" are different claims.

---

## 3. THE SHORTLIST — clears the pooled bar AND is held-out net-positive

Three gates, applied in order, no exceptions:
**G1** design statistic above the theme's pooled (FWER-6) bar ·
**G2** held-out net positive after the theme's realistic cost model ·
**G3** survives the capacity/cost-shock cut where the cost assumption is actually defensible.

| # | formula | theme | G1 design | G2 held out | G3 capacity | verdict |
|---|---|---|---|---|---|---|
| 1 | **XS_GLSR_Z** | crypto perp | gross 4.94 vs bar 3.36 ✅ | gross 3.92 / **net +2.38** @5.5bp, +34.5%/yr, breakeven **14.0 bp/side** ✅ | top-50 net **+0.73** ⚠️ (positive but thin) | **PROMOTE — one new leg** |
| 2 | XS_SMART | crypto perp | gross 3.25 vs bar 3.36 ❌ **near-miss** | gross 1.90 / net +1.42, breakeven 22.1 bp ✅ | top-50 design +3.29, OOS **+1.53**, **+0.80 at 15 bp/side** ✅✅ | **TRACK, do not size** — same idea as #1 |
| 3 | A08_p10_resid_day | overnight equity | t +6.45 vs bar 3.68 ✅ | net **+4.99 bp/night**, t +2.98, SR +1.40 ✅ | SR 0.86 at 2× half-spread ⚠️ | **ALREADY IN BASKET** as L1 (T3) |
| 4 | A09_p10_over_vol | overnight equity | t ≈ +6.4 vs bar 3.68 ✅ | net +2.91 bp/night, t +2.42, SR +1.14 ✅ | weaker than #3 | same signal as L1, no |

Everything else fails a gate outright:

- **XS_SMART_CHG** (design 4.10, rank 2) → held-out net **−1.74**. **XS_GLSR_CHG** (design 4.05,
  rank 3) → **−1.13**. The sweep's clearest overfits, and a reminder that design rank carries
  almost no information about held-out rank at this bar.
- **XS_CROWD_UNWIND** (design 3.90, OOS net +1.63) and **XS_ATS_Z** (design 3.64, OOS +1.55) pass G1
  and G2 and **die on G3**: top-50 net −0.64 and −1.71. They were illiquidity tilts inside the thin
  tail of the top-120, not edges. Same for XS_AMIHUD (+1.71 → −2.73), XS_QV_Z (+2.03 → −0.59),
  XS_LIQPROX (+1.98 → +0.23). **The capacity test killed five of eight survivors.** It should be a
  standing gate, not a robustness footnote.
- **P2_ovn_gap_reversal** (lead-lag, design 2.12 vs bar 1.56) passes G1 and fails G2/G3: held-out net
  **+0.15** at 5 bp/side, breakeven 5.6 bp against a market-on-open fill across ~2,900 names; on the
  top half by dollar volume held-out gross falls to 0.83, top quintile 0.13. The effect lives exactly
  where the cost assumption stops being defensible. Its own focused pass also showed the cross-asset
  term contributes nothing (deleting it *raises* held-out gross to 1.54) — it is a plain single-name
  overnight-gap reversal, i.e. a cousin of L1, not a lead-lag.
- **C1_betagap_rank_5m** (design gross 51.35 — the largest number in the whole sweep, 40× its bar) is
  the bid-ask bounce on the laggard's own return: net −225.87. **D2_btcpush_illiq_5m** (+7.54, the one
  genuine cross-asset transmission found) does not survive a holding period long enough to amortise
  6 bp/side: 30m/1h/4h/1d held-out 0.02/−1.33/−0.51/−1.43.
- **D8_CRUDE_DRIVING_SEASON** (futures, design 0.80 vs pooled bar 2.06) behaved exactly like a noise
  winner out of sample: +0.13 with an −87% drawdown.
- **REBAL_UNWIND_2D** (calendar, |z| 3.385 vs pooled bar 3.89) halved out of sample (0.717 → 0.412),
  and an **ungated control of the same signal earns +0.355 with no calendar rule at all** — the
  calendar gate buys 0.16 Sharpe, inside sampling error. It is a weak cross-asset reversal wearing a
  calendar costume.

---

## 4. THE ONE CANDIDATE, IN DETAIL

### XS_GLSR_Z — cross-sectional fade of retail account positioning (Binance USD-M perps)

- **Signal.** z-score of `count_long_short_ratio` (Binance global *account* long/short ratio) against
  its own trailing 7d history, per symbol. **Negative sign**: SHORT names where retail account
  positioning just spiked long, LONG names where it spiked short. Cross-sectional quintile
  long/short, 24h hold, entry and exit at the OPEN of the bar after the signal bar.
- **Universe.** Point-in-time top-N perps by trailing-7d quote volume. Design used top-120;
  **the freeze must use top-50**, the only universe where 5.5 bp/side is defensible.
- **Numbers.** Design (2023-01-01..2024-04-01, 456d): gross 4.94, net 3.37, +49.4%/yr, turnover
  1.14×/day, correlation to an equal-weight perp basket −0.01. Held out (2024-04-01..2025-01-01,
  275d, sign frozen from design): gross 3.92, **net +2.38**, +34.5%/yr, **breakeven 14.0 bp/side**.
  Top-50 capacity cut: net **+0.73**; −1.19 at a 15 bp/side shock.
- **Why I believe the theme and not just the formula.** Three independent pieces of evidence the
  crypto-perp sweep produced: design→held-out gross-Sharpe Spearman **+0.44** across all 56; the 15
  design-bar clearers averaged **2.48** gross OOS versus **0.82** for the other 41; and the held-out
  window was run on all 56 with design signs frozen, so that rank correlation is a real statistic and
  not a survivor's anecdote. A lookahead audit destroyed every panel input after the design cut and
  reproduced bit-identical weights: 0 violations.
- **Why I do not believe it very much.** One held-out regime only (Apr–Dec 2024, 275 days), no
  walk-forward, no 2025-26 confirmation because the metrics cache thins to ~30 symbols. The 5.5 bp
  cost is 4.5 bp published exchange fee + **1.0 bp declared, never-measured** half-spread — this
  programme has never measured perp slippage. `bookdepth` is in the cache and was not used, so
  capacity is untested beyond a volume screen. And XS_GLSR_Z / XS_GLSR / XS_SMART / XS_TTS /
  XS_TSIZE are all built from the same two Binance long/short-ratio fields: **that is ONE idea that
  passed, not five.**
- **The uncomfortable internal split, stated rather than smoothed.** The formula that clears the
  pooled *design* bar (XS_GLSR_Z, 4.94) and the formula that survives every *robustness* cut
  (XS_SMART, top-50 OOS +1.53 and still +0.80 at 15 bp/side) are not the same formula, and XS_SMART
  misses the pooled bar by 0.11. They are the same hypothesis. The freeze names **XS_GLSR_Z on the
  top-50 universe** as the sized leg — it is the only formula in 380 that passes all three gates —
  and logs **XS_SMART in parallel, unsized**, as the pre-declared robustness sibling. If GLSR_Z's
  forward log dies and SMART's does not, that is information, not a licence to swap.

---

## 5. DIVERSIFICATION VS BASKET1

BASKET1 (frozen 2026-08-20, `BASKET_FORWARD_PREREGISTRATION.md`) is: **L1** T3 end-of-day pressure
reversal (US equity, overnight cross-sectional reversal, close→next open), **L2** ETF-sibling
identical-claim RV (US equity intraday, 15:45→close), plus L3/L4 PENDING_SPEC and a T13 vol-targeting
sleeve.

| candidate | relation to BASKET1 | add? |
|---|---|---|
| **XS_GLSR_Z** | **NEW DIVERSIFIER.** Different asset class (crypto perps), different venue, different data source (exchange positioning metrics, not price), different horizon (24h), different holding calendar (24/7). No shared instrument, no shared factor, no overlapping trading window with L1 or L2. Its design correlation to an equal-weight perp basket is −0.01, so it is not crypto beta either. | **YES — new leg, own freeze** |
| XS_SMART | Same hypothesis as XS_GLSR_Z (both are Binance long/short-ratio fields). Diversifying vs BASKET1, redundant vs the leg above. | log unsized under the same freeze |
| A08 / A09 / A01 (overnight family) | **CORRELATED — this IS L1.** A08's held-out improvement over the T3 baseline is +0.31 bp/night, t 0.43: the design improvement does not replicate. Swapping L1's spec would break the freeze to buy a statistically absent gain. | **NO** |
| P2_ovn_gap_reversal | Correlated with L1 (single-name overnight-gap reversal once the cross-asset term is deleted), and net-dead where costs are defensible. | **NO** |

**One new leg.** It slots as **L5**, and it raises `declared_trials_now` on the combined basket gate —
killed and retired legs keep counting forever, and so do these 380 formulas for anything drawn from
them.

---

## 6. HOW MANY THEMES WERE PURE NOISE

**Four of six.**

| theme | verdict at the pooled bar |
|---|---|
| Intraday equity/ETF RV (98) | **NOISE as a tradeable theme.** 0 of 98 net-positive. Real gross effect, 37× too small for a taker. Only the maker side is untested, and this data cannot support it. |
| Cross-asset / cross-venue lead-lag (74) | **NOISE.** Every large crypto number contains the laggard's own lagged return (bid-ask bounce); every pure-transmission formula is at or below zero. Equity transmission flatly dead across rates, USD, oil, credit, vol, gold, overseas. The one design winner is not a lead-lag and dies on cost. |
| Futures term structure / carry / seasonality (49) | **NOISE.** 1 of 49 above E[max], 0 of 49 above its own p95, best +0.80 → +0.13 out of sample with an −87% drawdown. |
| Calendar / session / structural flow (52) | **NOISE.** 0 of 52 above the pooled bar. Every classic named effect (day-of-week, turn-of-month, Halloween, Santa, OPEX, pre-holiday, weekend) at \|z\| < 1.2. |
| Overnight equity, T3 family (51) | **NOT noise — but produces nothing new.** 27 of 51 clear the within-theme bar and 5 clear it with the opposite sign, but all 27 restate one feature (the last ten minutes reverse overnight) and that feature is already leg L1. No formulation beats T3 out of sample. |
| Crypto-perp microstructure (56) | **NOT noise, and produces one leg.** Design→OOS rank correlation +0.44, clearers average 2.48 OOS vs 0.82 for the rest. One idea (account positioning), one promotable formula. |

---

## 7. FINDINGS THAT SURVIVE EVEN THOUGH THE FORMULAS DIDN'T

These are the durable outputs — cheaper to reuse than to rediscover.

1. **The last ten minutes reverse; the rest of the session continues.** Fading the open→close move
   overnight is significantly *negative* (t −4.83, 6 of 6 years); fading the 15:49→15:59 move is
   positive. That asymmetry is why residualising on the session move was the only improvement in 50
   tries, and why a naive `z(p10)+z(day)` composite destroys the signal (Sharpe −0.07).
2. **The MOC-legal rail is dead in all eight formulations** (best net Sharpe 0.37, t 0.89). The free,
   spread-less rung cannot reach any overnight signal in this cache — T3's structural finding
   reproduced from seven new directions.
3. **Run a dislocation census before any RV sweep.** `rv_census.py` predicted the intraday RV theme's
   total failure *before* a single config was scored: same-claim pairs (SPY/IVV) have p95 dislocation
   0.33× the four-half-spread round trip and ac(1) +0.14, while the pairs with big persistent spreads
   (SMH/SOXX, ac(1) +0.96) are the ones that are not the same claim. A one-hour pre-filter would have
   saved a 98-formula sweep.
4. **Capacity is a gate, not a footnote.** It killed five of eight crypto survivors and it killed P2.
   Any formula whose edge concentrates in the illiquid tail of its universe is an illiquidity tilt
   until proven otherwise.
5. **Yahoo `X=F` continuous futures silently delete roll yield** — CL=F fell ~25% over 2007-2018 while
   USO fell 80.4%. Any backtest P&L'ing off `=F` returns books that 55pp gap as profit. Use `=F` for
   signal only; P&L off a holdable ETF.
6. **Ranking a sign-agnostic search by |t| of the net series promotes turnover, not signal.** Score
   `max(SR_net(+W), SR_net(−W))` and draw the identical statistic in the null.
7. **Carry is now dead five independent ways** (crypto funding family, futures term structure, ETF
   ladder, VIX curve, rates curve). Stop testing carry.
8. **Two real bugs were caught by automated lookahead audits, not by review**: an equity lead-lag
   formula using the leader basket's same-day return (+2.83 → +0.43 corrected) and a held-out
   turnover diagnostic understated 3.5× by `np.bincount` over global day indices. The audits earned
   their cost.

---

## 8. WHAT I AM NOT CLAIMING

- The overnight held-out window was already spent by T3, so its baseline replication there is not a
  virgin test.
- Every equity universe in this sweep comes from a current broker asset list — **survivorship-biased
  by construction**. Dollar-neutral cross-sectional demeaning absorbs most of it, not all.
- The crypto-perp cost model contains a **declared, never-measured** 1 bp half-spread. Breakeven cost
  per side is reported for every formula precisely so that number can be re-charged when measured.
- One held-out regime per theme, no walk-forward anywhere. A single 275-day or 1,139-day window is
  one draw.
- 380 formulas is the count of what was *scored*. The true trial count across this programme's
  history is larger, and it only ever goes up.

**Bottom line: 380 formulas in, one leg out, and that leg is a small crypto-perp positioning fade
with a thin capacity margin and a single held-out regime behind it. That is the honest yield.**
