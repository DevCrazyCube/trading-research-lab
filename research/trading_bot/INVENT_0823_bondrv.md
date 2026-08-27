# INVENT_0823 · BOND / CREDIT-ETF STRUCTURAL RELATIVE VALUE

**Date:** 2026-08-23 · **Scope:** research only. No orders, no money.
**Harness:** `scripts/trading_bot/invent0823_bondrv.py`, `scripts/trading_bot/invent0823_bondrv_ohlc.py`
**Artifacts:** `INVENT_0823_bondrv_DESIGN.json`, `INVENT_0823_bondrv_HOLDOUT.json`, `INVENT_0823_bondrv.json`
**Data:** `research/data/ratescredit_cache/` (Yahoo daily adjusted closes = total return; new
`etf_open.json` adds daily opens) + FRED. All free, all cached.

---

## 0. THE ONE-PARAGRAPH ANSWER

**The theme is noise. 44 formulas, zero survivors, on design and held out.** But it dies in a way
that adds a second clause to the programme's thesis. The direct fixed-income analogue of T12 — bond
ETF premium/discount to its **published NAV** — is **data-blocked**: no free feed serves daily NAV
history for US bond ETFs, and the one published-index total-return series that would substitute is
licence-capped to a rolling three years. What *is* free are two tethers, and each fails differently.
The **published-curve** tethers (Treasury H.15, Moody's, and — tested here for the first time — the
**FRED TIPS breakeven**) fail on the **clock**: ρ1(Δspread) = −0.465 / −0.383, because FRED publishes
a 15:30 ET snapshot and the ETF prints at 16:00, so the residual is the first difference of the
unobserved last half-hour. That mechanism was proven in parallel by `INVENT_0823_rates` and my
numbers replicate it. The **sibling** tether has **no clock problem** — both legs are ETFs struck at
16:00, and ρ1 is only −0.20 to −0.26 — and it still dies, for a new reason: **the deviation is real
but smaller than the spread**. Sibling RV shows a close-to-close Sharpe of 4.6–8.1, but that book is
filled at the very print its signal was computed from. Move the fill to the next open — a *different*
print — and the gross falls 3–5× while **staying above the multiple-testing bar** (1.95 vs 0.87), so
the tether is genuinely informative, and the net goes to **−2.84**, because cost runs **2.4× gross**.
So: **a published tether must be synchronous AND its deviation must exceed the spread.** Bond-ETF
siblings satisfy the first condition and fail the second.

---

## 1. The published tether that would have worked, and why it is unavailable

A bond ETF should be the cleanest tether in the market: the issuer publishes an end-of-day NAV and an
intraday iNAV, and the fund is contractually the claim on that NAV. Bond ETFs really do trade at
material premiums and discounts in stress (HYG traded several per cent below NAV in March 2020), so
the amplitude is there. Probed 2026-08-23:

| source | result |
|---|---|
| iShares `.ajax?fileType=csv&fileName=<T>_NAV&dataType=fund` | HTTP 200 but serves the **product page HTML** — Akamai bot wall. Same on the `blackrock.com` host, with browser UA, `Referer`, `siteEntryPassthrough`, and `asOfDate` |
| SSGA `nav-history-us-en-<t>.xlsx` (two path forms) | **404** |
| Vanguard investor / `api.vanguard.com` price-history | **404 / 400** |
| Yahoo iNAV proxy tickers (`^HYG-IV`, `HYG-IV`, `HYG.IV`, `^HYGIV`) | not served |
| Nasdaq `api/quote/<T>/historical` | works, **price only**, no NAV column |
| FRED ICE BofA index **total return** (`BAMLHYH0A0HYM2TRIV`, `BAMLCC0A0CMTRIV`, …) | free and daily, but **licence-capped to a rolling 3 years** (796 obs), and a *rolling* cap means the design window is not even reproducible |

So the NAV premium/discount trade is not tested here — it is **priced as data-blocked**, alongside
`XS_GLSR_Z`. It is the single highest-value paid-data item this theme identifies: a daily bond-ETF
NAV history would make the T12 structure directly testable in fixed income.

## 2. What was tested instead — three free, permanent tethers, 44 formulas

| grp | tether | n | structure |
|---|---|--:|---|
| **A** | sibling identity, one pair at a time | 12 | HYG/JNK, LQD/USIG, TLT/VGLT, IEF/VGIT, SHY/VGSH … long the cheap fund, short the identical one |
| **B** | sibling identity, pooled cross-section | 10 | equal-risk book over all 18 pairs that clear $20M ADV |
| **BC** | sibling identity, pooled, **ρ1-clean subset** | 6 | the 11 pairs whose design-window ρ1 clears the bounce floor |
| **C** | **published Treasury par curve** (H.15, DGS2/5/10/30) | 5 | residual of each Treasury ETF's TR against the published curve, cross-sectional, curve-neutralised |
| **D** | **published Moody's corporate yields** (DAAA/DBAA) | 3 | same construction on the IG complex |
| **T** | **published TIPS breakeven** (T5YIE/T10YIE) — *new* | 4 | TIPS and duration-matched nominals in one cross-section, neutral to curve **and** to the published breakeven |
| **E** | published-composition synthetic basket | 4 | AGG/BND vs IEF+MBB+LQD+SHY; USHY vs ½HYG+½JNK; GOVT vs a maturity ladder |

Everything is ETF-vs-ETF. No naked directional leg, no single-stock short. Every leg is a US bond
ETF above $20M median dollar volume — the deepest ETB universe there is — so the borrow wall that
killed preferred-RV does not bind here. Axes varied: z-window (21/63/126/252 and EWMA hl=21), entry
(continuous vs hysteresis bands 1.5/0.5 and 2.0/0.5), hedge ratio (unit vs rolling 126-day OLS),
holding (daily vs 5-day averaged), scoring (z vs cross-sectional rank), loading-fit window (250 vs
500 days).

**Windows.** Design **2010-01-04 → 2019-12-31** (2 515 sessions, 9.98 y). Held out
**2020-01-02 → 2026-08-20** (1 668 sessions, 6.62 y), read once, after the design ranking was on disk.

## 3. The null, measured three ways

| bar | design (9.98 y) | held out (6.62 y) |
|---|--:|--:|
| analytic `sqrt(2 ln 44)/sqrt(yrs)` | 0.87 | 1.07 |
| **size-matched placebo**, 400 signal-rotation draws — close-to-close | 0.84 | 0.87 |
| **size-matched placebo** — open-to-open | 0.82 | 0.91 |
| stationary block bootstrap (block 5 d) — close-to-close | 0.97 | 1.62 |
| stationary block bootstrap — open-to-open | 0.85 | 1.17 |
| **BAR USED** (max) — close-to-close / open-to-open | **0.97 / 0.87** | **1.62 / 1.17** |

The placebo **rotates the signal, not the returns** — the rotate-the-returns null is broken for a
cross-sectional book because it injects a directional leg. Rotation preserves the signal's own
autocorrelation, hence the turnover, hence the cost, and the same offset is used for every formula
inside a draw so their cross-correlation survives the max. It came in slightly *below* analytic; the
block bootstrap came in *above*, as in DEEPMINE, because daily RV PnL is fat-tailed and autocorrelated
and the analytic formula assumes neither. The larger is used.

## 4. Gate 1 — ρ1, run before any Sharpe was believed

| family | ρ1(Δspread), design | verdict |
|---|--:|---|
| C — published Treasury curve | **−0.465** | **bounce — killed**, despite the highest gross Sharpe in the run (10.35) |
| T — published TIPS breakeven | **−0.383** | **bounce — killed** |
| E — GOVT vs published ladder | **−0.432** | **killed** |
| sibling pairs `jnk/hylb −0.496`, `shy/vgsh −0.456`, `tip/schp −0.439`, `shy/scho −0.428`, `spib/igib −0.408`, `tlt/vglt −0.401`, `tlt/sptl −0.377` | | **killed**, removed from the pooled clean book |
| sibling pairs `ief/vgit −0.162`, `pff/pgx −0.202`, `lqd/usig −0.203`, `hyg/ushy −0.216`, `hyg/jnk −0.230`, `mub/tfi −0.238`, `igsb/vcsh −0.239`, `igib/vcit −0.243`, `bkln/srln −0.247`, `sjnk/shyg −0.270`, `emb/pcy −0.285` | | **pass** — the 11-pair clean set |
| D — published Moody's yields | −0.196 | pass |

The gate earned its keep. `C_tsy_z21c` posts a **gross Sharpe of 10.35** and a positive headline net
of 1.84 — and it is bid-ask bounce, exactly as the hard lesson says a high gross inside a tethered
family should be read. `INVENT_0823_rates` independently established the mechanism: FRED H.15 is a
**15:30 ET** snapshot and the ETF prints at **16:00**, so the wrapper-vs-claim residual is the first
difference of the unobservable last half-hour, forcing ρ1 → −0.5. My −0.465 replicates their −0.422.
**The TIPS-breakeven tether at −0.383 is a fresh instance of the same failure** — the first time that
anchor has been tested, and it fails on the clock, not on the content.

## 5. Gate 2 — the decisive test: fill on a *different print*

The close-to-close L=1 book is formed from close(t) and filled **at close(t)** — the same print. If
the signal says "cheap" partly because a bid print landed, then you are buying the low print, and a
half-spread charge does not fix a signal *correlated with which side printed*. Two independent checks:

* **Lag-kill.** Delay one day: pooled sibling gross **6.17 → 0.91**. Treasury-curve **8.89 → 0.55**.
  The entire edge is in the single step after the signal print.
* **Open-to-open.** Signal from close(t), fill at **open(t+1)**, P&L open(t+1)→open(t+2). Signal price
  and fill price are now different prints. `etf_open.json` was fetched for this.

| formula | ρ1 | CC gross | CC net | **OO gross** | **OO net** | OO net @ tick-floor | cost ÷ gross |
|---|--:|--:|--:|--:|--:|--:|--:|
| `BC_xs_z21c` (clean pool, z21) | −0.238 | 6.46 | +0.88 | **1.95** | **−2.84** | −0.70 | ×2.4 |
| `B_xs_z21c` (all pairs, z21) | −0.258 | 8.05 | +1.50 | 1.73 | −4.66 | −1.78 | ×3.6 |
| `BC_xs_ew21c` | −0.238 | 4.97 | +1.09 | 1.56 | −1.80 | −0.32 | ×2.0 |
| `BC_xs_z63c` | −0.238 | 4.61 | +0.94 | 1.39 | −1.70 | −0.35 | ×2.1 |
| `C_tsy_z21c` (curve tether) | −0.465 | 10.35 | +1.84 | 1.36 | −3.97 | −1.54 | ×3.8 |
| `A_ig_lqd_usig_z63c` | −0.203 | 2.12 | +1.02 | 0.79 | −0.17 | **+0.24** | **×1.11** |
| `E_ushy_split` | −0.198 | 1.50 | +0.77 | 0.57 | −0.38 | +0.04 | ×1.59 |

**This is the finding.** The OO gross of 1.95 clears every null bar (0.87), so the sibling tether
carries real information that is *not* bounce. And **net is negative for all 44 of 44 formulas.** The
gross edge is **0.14–0.21 bp/day** on a book that rewrites a fifth of itself every session; the
half-spread on the legs is 0.6–1.25 bp. At the **arithmetic tick-floor bound** — half of a one-cent
spread, no adversity, no floor, a fill no execution can beat — only **2 of 44** turn positive, and
both are below the gross bar.

## 6. Held out — read once

| formula | design OO gross | design OO net | **held-out OO gross** | **held-out OO net** | held-out OO net @ tick-floor |
|---|--:|--:|--:|--:|--:|
| `BC_xs_z21c` | 1.95 | −2.84 | **0.53** | **−3.22** | −1.54 |
| `B_xs_z21c` | 1.73 | −4.66 | 0.61 | −4.76 | −2.34 |
| `BC_xs_ew21c` | 1.56 | −1.80 | 0.43 | −1.85 | −0.84 |
| `BC_xs_z63c` | 1.39 | −1.70 | 0.45 | −2.02 | −0.94 |
| `C_tsy_z21c` | 1.36 | −3.97 | 0.48 | **−12.75** | −6.90 |
| `A_ig_lqd_usig_z63c` | 0.79 | −0.17 | **0.71** | **−0.07** | **+0.25** |

* **0 of 44 have a positive held-out OO net.** Best is −0.07.
* Held-out max OO gross is **0.71** against a bar of **1.17** — out of sample the de-bounced gross
  does not clear the multiple-testing bar at all. The design OO gross of 1.39–1.95 decayed to 0.43–0.61.
* Even the optimistic close-to-close structure is net-positive for only **2 of 44** held out.

**The near miss, reported as a near miss.** `A_ig_lqd_usig_z63c` — LQD vs USIG, two investment-grade
corporate ETFs holding near-identical portfolios — is the only formula stable across the split:
OO gross 0.79 → 0.71, OO net −0.17 → −0.07, and **positive on both windows at the tick-floor bound**
(+0.24 / +0.25). Its cost is **1.11× its gross**: it needs execution roughly one tick better than it
was charged. It is **not real** — its OO gross is below the bar on both windows, so it fails on gross
before cost is even discussed — and it is written down because the shape of the miss is informative:
IG sibling RV is a genuine, stable, tiny edge that is almost exactly the width of the spread.

## 7. Cost model

Both legs pay. Headline half-spread per symbol `max(1.0 bp, 2 × (half a cent / price))` — a
tick-floor-times-adversity **proxy, not a quote measurement**, said out loud. Plus 0.15 bp per unit of
turnover for SEC §31 + FINRA TAF. Plus borrow at B22G's measured ETB general-collateral median
**0.33 %/yr** on short notional per calendar day — all legs here are bond ETFs, the easiest borrow in
the market, so borrow is a rounding error (< 0.02 bp/day) and is *not* what kills the family. The
**tick-floor lower bound** (half of a one-cent spread, no adversity, no floor) is reported alongside
every number as the arithmetic floor. The verdict survives it: 42 of 44 lose even there on design,
44 of 44 held out on the scored open-to-open structure.

## 8. What this adds to the programme

1. **The thesis needs two clauses, not one.** "Free data prices a statistic, never a claim" is right,
   and `INVENT_0823_rates` added "a published tether must be **synchronous**." This run adds the
   third: **the deviation must also be larger than the spread.** Bond-ETF siblings are the cleanest
   synchronous tether the programme has found — two 16:00-struck ETFs on the same claim, ρ1 ≈ −0.21,
   de-bounced gross above the bar — and they still lose, because the mispricing is 0.2 bp/day and the
   spread is 0.6–1.25 bp. Synchrony was necessary, not sufficient.
2. **Bond-ETF NAV history is the concrete paid-data ask.** Unlike most data walls this one has a
   clean shape: the tether value *is* published daily by every issuer and is *not* machine-readable
   free. It is the only route left to test the T12 structure in fixed income.
3. **The TIPS-breakeven anchor is dead for the same clock reason** as the Treasury curve — recorded
   so it is not re-proposed.
4. **Do not re-propose:** bond/credit-ETF sibling RV (HY, IG, Treasury, agg, TIPS, muni, EM, loans,
   preferred), bond-ETF-vs-published-curve residual RV, bond-ETF-vs-published-Moody's residual RV,
   TIPS-breakeven tether RV, bond-ETF-vs-published-composition basket RV. All measured, all noise.

## 9. Overlap with `INVENT_0823_rates`

That run and this one were executed concurrently and overlap on the Treasury sibling pairs
(SHY/VGSH, TLT/SPTL, TLT/VGLT) and the published-curve tether. The results agree: high gross,
negative net, ρ1 in the bounce band. Their contribution is the **clock mechanism** (H.15 15:30 vs ETF
16:00, with a 16:00-anchor control showing ρ1 → −0.148). This run's distinct contribution is the
**credit side** (HY / IG / EM / muni / preferred / convertible-adjacent siblings, untouched there),
the **NAV data-block probe**, the **TIPS-breakeven tether**, and the **open-to-open discriminator**
that separates close-print bounce from real edge in the synchronous sibling families where the clock
argument does not apply.

---

**VERDICT: NOISE.** 44 formulas, 0 survivors on design, 0 on held out, 0 with positive held-out net
under the executable structure. Honest zero.
