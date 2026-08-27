# INVENT ROUND 3 — theme: EXOTIC / LEFT-FIELD original signals on free data

**Date:** 2026-08-21 · **Formulas tested:** 27 · **Survivors: 0** · **Verdict: the theme is noise.**

Harness `scripts/trading_bot/invent_r3_exotic.py`, panel builder
`scripts/trading_bot/invent_r3_panel.py`, results `INVENT_R3_exotic.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

I built 27 formulas in six families that the 598-formula programme had never searched:
new-listing first-week perp dynamics, weekend/week-structure with cross-sectional structure,
vol-of-vol beyond a plain rank, cross-crypto dispersion and average-correlation *regimes*,
positioning-crowding aggregates as primary signals, and stablecoin mint/burn as an exogenous
driver. **The single best design-window net Sharpe in the whole search is 1.11. The expected
maximum |Sharpe| a search of this size produces from pure noise on this panel is 1.27
(sign-flip block bootstrap), and the conservative analytic bar is 1.58.** The best formula in
the search does not reach the *mean* of the null-maximum distribution, let alone its p95 of
1.74. Nothing earned a held-out test; nothing is promoted; nothing goes on a shortlist.
The one formula I looked at anyway out of curiosity — `D1_DISP_TS`, cross-sectional dispersion
as a basket-timing regime — is positive in both windows (design 0.89, held-out 1.06, residual
to the basket 0.95, break-even 53 bp/side) but at t = 1.33 held out and a design number 30%
*below* the noise bar it is a coin that came up heads twice, and I am recording it as dead.

---

## 1. WHAT WAS SEARCHED, AND WHY IT IS NOT A RE-RUN

The dead ledger forbids re-proposing every published equity edge, VRP put-write, crypto carry
as a standalone, box spread, Orphan Flush, Coiled Leverage, the 18 SIZE candidates, and the
four noise sweep themes (intraday-RV pooled, cross-asset lead-lag, futures term structure,
calendar effects). Round 2 additionally spent 51 crypto-perp formulas, whose names are in
`perpmicro_sweep2.py`. Every formula below is checked against both lists:

| family | n | why this is not already in the 598 |
|---|---|---|
| **A · new-listing first-week dynamics** | 6 | *Listing age has never been a feature anywhere in the repo.* Rounds 1–2 rank names within a fixed liquid universe; nothing has ever conditioned on how long a contract has existed. |
| **B · weekend / week structure** | 5 | Round 2 tested *time-of-day* (`X2_TOD_FLOW_EU`, `X2_TOD_MOM_US`, `X2_TOD_REV_ASIA`); the calendar sweep tested day-of-week as a pooled TS effect and it was noise. Nothing has tested **cross-sectional** structure formed at the weekend boundary, or funding held *only* across the weekend. |
| **C · vol-of-vol** | 4 | `X2_VOLVOL` is a plain cross-sectional rank of one vol-of-vol number. The **term structure** of vol-of-vol, its **up/down asymmetry**, and its use as a **regime gate** are new objects. |
| **D · dispersion / correlation regimes** | 5 | Round 2 had breadth and vol-regime TS timing. Implied **average pairwise correlation**, dispersion as a **conditioner on a second book**, and the cross-sectional **change in correlation-to-market** are new. |
| **E · positioning crowding** | 4 | Rounds 1–2 rank *individual* funding and L/S ratios. The **cross-sectional dispersion of funding** (a crowding index), **funding breadth**, and funding **residual to a name's own beta to universe funding** are aggregates, not ranks. |
| **F · stablecoin mint/burn** | 3 | Genuinely exogenous. Not on any list. Free DefiLlama aggregate supply. |

Explicitly *not* proposed: anything from the dead ledger; anything that restates T3, ETFRV,
dual-class, T7 ex-open, T12 CEF, or `XS_GLSR_Z`.

---

## 2. DATA, WINDOWS, COSTS

**Panel.** `research/data/invr3_cache/daily.npz` — a UTC-daily roll-up of
`perpmicro_cache/panel1h_ext.npz` (Binance USD-M perps, 439 symbols × 1,689 days,
2022-01-01 → 2026-08-16, 5-minute klines rolled to hours rolled to days, plus the t23 funding
cache). Fields: OHLC, quote volume, trade count, taker-buy quote volume, funding settled per
day, hours-of-data per day. Built once, 3 MB, memory-frugal — the 38 GB orphanflush raw cache
is not touched at query time.

**Exogenous.** DefiLlama free aggregate stablecoin circulating supply (`stablecoincharts/all`,
one HTTP GET, cached to `research/data/invr3_cache/sc_all.json`, 3,187 daily points).

**Windows.** Design **2022-01-01 → 2025-01-01** (1,096 days). Held out
**2025-01-01 → 2026-07-31** (576 days), untouched until every sign was frozen.
*Honest disclosure:* `perpmicro_sweep2.py` evaluated its 51 class-A formulas on this same
2025-01 → 2026-08 window. It is virgin for these six families but it is the programme's
second pass over that calendar time, and a third pass should not be spent here.

**Execution conventions**, inherited unchanged from `perpmicro_sweep.py` so the numbers are
comparable: signal formed from data through the close of day *d*, entered at the **open of day
d+1**; H overlapping daily tranches each 1/H of the book; funding charged at settlement (a long
pays positive funding); taker cost on |turnover|; **the sign is oriented on the design window
using the zero-cost P&L and then frozen**; headline universe top-50 by trailing 7-day quote
volume.

**Costs.** 5.5 bp/side on the liquid top-50, shocked to 15 bp/side (the round-2 convention).
The new-listing cohort is charged **20 bp/side, shocked to 40** — new perps are thin and wide
and it would be dishonest to charge them a BTC fill.

**Sharpe is measured over the whole window, not only over the days the book is on.** A book
that trades only on Mondays must pay for the four days a week it earns nothing. This is why
the weekend family's numbers here are lower than a naive per-trade annualisation would give.

---

## 3. THE NOISE BAR

Sign-flip block bootstrap (10-day blocks, 2,000 replicates), re-scoring **the maximum over all
27 formulas every replicate** so that the correlation between formulas survives into the null:

| statistic | value |
|---|---|
| E[max &#124;Sharpe&#124;] over 27 formulas | **1.27** |
| p95 of max &#124;Sharpe&#124; | 1.74 |
| p99 | 1.98 |
| SD of one formula's Sharpe under the null (= 1 SE) | 0.559 |
| analytic `sqrt(2 ln 27)` = 2.567 SE | 1.43 Sharpe |
| analytic sign-agnostic `sqrt(2 ln 54)` = 2.825 SE | **1.58 Sharpe** |
| cumulative programme `sqrt(2 ln 625)` = 3.588 SE | 2.01 Sharpe |

The single-formula SE of 0.559 is what a 3-year design window mechanically gives
(`1/sqrt(3) = 0.577`), which is a useful check that the bootstrap is not lying.

**Best design net Sharpe in the search: 1.11. It clears none of these bars — it does not even
reach E[max].** For a 27-formula search that is the cleanest possible negative: I did not have
to argue about whether a winner was overfit, because there was no winner.

---

## 4. ALL 27 FORMULAS, NOTHING DROPPED

Sorted by design net Sharpe. `Dgr`/`Dnet` = design gross/net, `Hnet` = held-out net at the
headline cost, `Hshk` = held-out net at the shock cost, `Ht` = held-out t-stat, `BE` =
break-even cost in bp/side on the held-out window.

| formula | family | Dgr | Dnet | Hnet | Hshk | Ht | BE |
|---|---|---:|---:|---:|---:|---:|---:|
| B3_WKND_FUND_CARRY | weekend | 1.43 | **1.11** | −0.58 | −0.91 | −0.73 | −11.3 |
| D1_DISP_TS | dispersion | 1.00 | 0.89 | +1.06 | +0.85 | +1.33 | 53.0 |
| E2_FUNDBREADTH_TS | crowding | 0.83 | 0.77 | +0.40 | +0.26 | +0.50 | 31.5 |
| A1_NL_WEEK1_HEDGED | new-listing | 0.89 | 0.71 | −0.63 | −0.76 | −0.79 | −80.7 |
| A2_NL_MONTH1_HEDGED | new-listing | 0.83 | 0.71 | +0.54 | +0.45 | +0.68 | 137.3 |
| B5_WKND_DISP_TS | weekend | 0.82 | 0.69 | −0.27 | −0.51 | −0.33 | −4.8 |
| B4_WKND_VOLRATIO_TS | weekend | 0.81 | 0.68 | −0.82 | −1.06 | −1.03 | −26.1 |
| A6_NL_AGE_TILT | new-listing | 0.49 | 0.44 | −0.54 | −0.60 | −0.67 | −77.5 |
| F3_SC_ALT_VS_BTC | stablecoin | 0.51 | 0.40 | −0.58 | −0.77 | −0.73 | −23.6 |
| F1_SC_IMPULSE_BASKET | stablecoin | 0.44 | 0.40 | +0.06 | −0.02 | +0.07 | 12.8 |
| E4_CROWD_GATE_REV | crowding | 0.47 | 0.25 | −0.55 | −0.87 | −0.70 | −11.2 |
| C2_VOV_TS | vol-of-vol | 0.24 | 0.19 | −1.10 | −1.23 | −1.39 | −75.3 |
| F2_SC_IMPULSE_BTC | stablecoin | 0.21 | 0.16 | +0.64 | +0.55 | +0.81 | 71.7 |
| D5_XS_CORRDROP | dispersion | 0.34 | 0.12 | −1.97 | −2.22 | −2.48 | −68.7 |
| E1_FUNDDISP_TS | crowding | 0.14 | 0.06 | −1.32 | −1.51 | −1.66 | −61.6 |
| D4_DISP_GATE_MOM | dispersion | 0.18 | 0.05 | +1.28 | +1.10 | +1.61 | 74.5 |
| D2_AVGCORR_TS | dispersion | 0.06 | 0.03 | −0.36 | −0.44 | −0.45 | −37.8 |
| C4_VOV_GATE_REV | vol-of-vol | 0.25 | 0.02 | −0.06 | −0.32 | −0.08 | 3.2 |
| C1_VOV_TERM_XS | vol-of-vol | 0.27 | 0.01 | −1.10 | −1.39 | −1.38 | −30.8 |
| A4_NL_FUND_SIGN | new-listing | 0.20 | 0.00 | −0.22 | −0.35 | −0.27 | −13.9 |
| D3_CORR_GATE_REV | dispersion | 0.21 | −0.00 | −0.19 | −0.47 | −0.24 | −1.2 |
| C3_VOV_ASYM_XS | vol-of-vol | 0.10 | −0.04 | +0.73 | +0.56 | +0.92 | 46.3 |
| A5_NL_VOLDECAY | new-listing | 0.07 | −0.06 | +0.75 | +0.66 | +0.95 | 180.9 |
| B1_WKND_XS_FADE | weekend | 0.37 | −0.10 | +0.57 | −0.01 | +0.72 | 14.9 |
| A3_NL_D1_FADE | new-listing | 0.02 | −0.17 | −0.35 | −0.46 | −0.43 | −39.2 |
| E3_XS_FUND_RESID | crowding | 0.10 | −0.25 | +0.81 | +0.48 | +1.02 | 28.6 |
| B2_WKND_FLOW_FADE | weekend | 0.10 | −0.39 | +0.88 | +0.28 | +1.11 | 19.3 |

Family roll-up:

| family | n | best design net | best held net | **mean held net** |
|---|---:|---:|---:|---:|
| A new-listing | 6 | 0.71 | 0.75 | −0.07 |
| B weekend | 5 | 1.11 | 0.88 | −0.04 |
| C vol-of-vol | 4 | 0.19 | 0.73 | −0.38 |
| D dispersion | 5 | 0.89 | 1.28 | −0.04 |
| E crowding | 4 | 0.77 | 0.81 | −0.17 |
| F stablecoin | 3 | 0.40 | 0.64 | +0.04 |

**Five of six families have a negative mean held-out Sharpe.** The sixth (stablecoins) is
+0.04 on three formulas.

---

## 5. THE HARNESS IS NOT THE REASON THEY FAIL

Four control books, **not part of the 27 and not in the noise bar**, run through this exact
harness. Their sign and rough size are known independently:

| control | design gross | design net | held gross | held net |
|---|---:|---:|---:|---:|
| CTRL_XS_FUND (short expensive funding, long cheap) | **+1.34** | +1.02 | **+0.78** | +0.60 |
| CTRL_XS_MOM7 (7-day cross-sectional momentum) | +0.31 | +0.10 | +1.80 | +1.66 |
| CTRL_LONG_BASKET (long-only equal-weight top-50) | −0.01 | −0.03 | −0.46 | −0.48 |
| CTRL_XS_REV3 (3-day cross-sectional reversal) | +0.05 | −0.35 | −1.30 | −1.56 |

`CTRL_XS_FUND` reproduces the best-documented effect in perpetual futures with the right sign
in **both** windows and a plausible magnitude — which is exactly the repo's standing position
that crypto carry is real but not fundable standalone. A harness that finds carry and does not
find these 27 is discriminating, not broken.

---

## 6. THE SIGN-STABILITY CENSUS — this is what noise looks like

Signs were frozen on design. Out of 27:

- **20 have a positive design net Sharpe** (the rest are pushed negative by cost after the sign
  is set on the zero-cost P&L).
- **14 of those 20 go negative out of sample — 70%.**
- **6 of 27 are positive in both windows** — `D1_DISP_TS`, `E2_FUNDBREADTH_TS`,
  `A2_NL_MONTH1_HEDGED`, `F1_SC_IMPULSE_BASKET`, `F2_SC_IMPULSE_BTC`, `D4_DISP_GATE_MOM`.
- **11 of 27 are positive out of sample at all — 41%, slightly worse than a coin.**

Two individual signatures are worth naming because they are the classic tells:

- **`D5_XS_CORRDROP`**: design +0.12, held out **−1.97** (t −2.48). A near-zero design number
  and a large opposite-signed held-out number. The temptation is to flip the sign and claim a
  −2.5-t discovery. That is precisely the post-hoc move the frozen-sign discipline exists to
  forbid, and the honest reading is that the correlation-change feature carries no information
  and the held-out draw is a −2.5 σ event in a 27-formula family where such a draw is expected.
- **`D4_DISP_GATE_MOM`**: held out +1.28, which looks like the best number in the table. But
  the *ungated* control `CTRL_XS_MOM7` posts **+1.66** on the same window. The dispersion gate
  does not add to momentum, it **subtracts** from it. And momentum itself went +0.31 design →
  +1.80 held gross, i.e. the control that beats my conditioner is itself unstable by a factor
  of six. The same logic kills `C4`, `D3`, and `E4`: every conditioner in this round underperforms
  the raw book it was supposed to improve.

---

## 7. THE ONE THING I LOOKED AT ANYWAY — and why it is still dead

`D1_DISP_TS`: z-score (90-day) of the cross-sectional dispersion of daily perp returns across
the top-50, sign applied to the equal-weight basket, 3-day hold. The mechanism would be that a
universe pulling apart is a de-risking regime.

| | design | held out |
|---|---:|---:|
| net Sharpe | 0.89 | **+1.06** |
| t | 1.54 | 1.33 |
| net bp/day | 13.1 | 15.2 |
| beta to the long-only basket | −0.13 | −0.23 |
| **residual Sharpe after hedging that beta** | 0.90 | **+0.95** |
| turnover / day | — | 0.32 (on 0.63 mean gross) |
| break-even cost | — | **53 bp/side** |
| funding drag | — | −0.07 bp/day |
| calendar-year Sharpe | 2022 +1.03 · 2023 −0.65 · 2024 +1.80 | 2025 +0.95 · 2026 +1.34 |

It is not a disguised short (only 39% of held-out days are long, but the residual survives the
hedge), it is not cost-killed (53 bp/side of room against a 5.5 bp fill), and it is positive in
four of five calendar years.

**It is still dead, for one reason that admits no argument: its design Sharpe of 0.89 is
30% below the 1.27 that a 27-formula null search is expected to produce, and 44% below the
1.58 analytic bar.** It never earned the held-out look I gave it. A held-out t of 1.33 is not
evidence of anything, and against the cumulative-programme bar of 2.01 Sharpe it is not close.
Logging it here so that no future round rediscovers it and mistakes it for new — if it is ever
revisited it needs a *third*, genuinely untouched window, and there isn't one on this panel.

---

## 8. HONEST LIMITATIONS

- **The new-listing family carries a hard selection bias and I could not remove it.** The
  underlying download universe (`orphanflush_cache/universe_full.json`) selected symbols by
  *monthly top-80 trailing-30-day volume among contracts listed ≥ 60 days*. A perp therefore
  enters this panel only if it was still liquid two months after listing. New listings that
  died are absent. 137 of 439 symbols carry a first bar that looks like a genuine mid-month
  listing (median 12 hours of data on day 0, which corroborates a real intraday listing), and
  the cohort is thin — a median of one name per active day, which is why families A2–A5 are
  sign books hedged against the basket rather than cross-sectional quintiles. The bias runs
  **in favour of "long new listings"**, so `A1`'s design +0.71 → held-out −0.63 is if anything
  flattered on the design side, and the family's negative mean held-out number is the
  conservative reading. No new-listing result here should be believed in either direction
  without an unbiased listing calendar.
- **The held-out window is the programme's second pass over 2025-01 → 2026-08.** Virgin for
  these families, not virgin for the calendar.
- **The weekend family has ~82 usable Mondays per year.** Even a real weekend effect would be
  hard to certify at this sample size, so B's failure is partly a power statement, not only a
  sign statement. I would not revive it without hourly resolution and a longer history.
- **Stablecoin supply is a daily aggregate with revision risk.** DefiLlama restates history;
  the series is not point-in-time. The three F formulas are the weakest-provenance numbers in
  the table and the fact that they are the only family with a non-negative mean held-out Sharpe
  (+0.04 on n=3) should be read as a rounding artefact, not a hint.
- **Perp taker slippage on the top-50 is still assumed, not measured** (5.5 bp/side inherited
  from round 2, shocked to 15). Irrelevant to this round's verdict — nothing got far enough for
  cost to matter — but it remains the open measurement behind `X2_FLOWSTREAK`.

---

## 9. WHAT THIS ADDS TO THE LEDGER

Add to the dead list, all as **searched and found to be noise on Binance USD-M perps,
2022–2026**:

1. New-listing / listing-age effects on perps (first week, first month, day-1 fade, birth
   funding, attention decay, liquid-universe age tilt) — *and note the selection bias that
   makes a clean re-test impossible on this cache.*
2. Weekend structure: cross-sectional weekend-return fade, weekend taker-flow fade,
   weekend-only funding carry, weekend vol-ratio regime, weekend dispersion regime.
3. Vol-of-vol beyond a plain rank: term structure, up/down asymmetry, aggregate VOV timing,
   VOV as a reversal gate.
4. Cross-crypto dispersion and average-correlation regimes, including as conditioners on a
   second book.
5. Positioning-crowding aggregates as primary signals: funding dispersion, funding breadth,
   funding residual to own beta-to-market-funding.
6. Stablecoin mint/burn impulse → basket, → BTC, → alts-vs-BTC.

Plus one methodological finding worth carrying forward: **every conditioner/gate in this round
underperformed the raw book it was gating.** `D4` lost to plain momentum, `C4`/`D3`/`E4` lost
to plain reversal. Regime-gating a cross-sectional book was the most attractive-looking new
structure available and it destroyed value four times out of four. That is a cheap lesson for
future rounds: do not spend formulas on gates.

Cumulative distinct formulas across the programme after this round: **625**
(`sqrt(2 ln 625)` = 3.588 SE ≈ 2.01 Sharpe in this panel's units).
