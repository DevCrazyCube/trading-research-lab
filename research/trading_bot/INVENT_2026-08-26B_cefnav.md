# INVENT_2026-08-26B — CEF NAV-innovation underreaction — RESULT

**Verdict: DEAD.** The NAV-driven part of the discount change does not predict the next 1–10 sessions or the next week at a one-session-gap entry. The decomposition clause fails at every horizon with the wrong sign (price-driven part beats NAV-driven part everywhere). Nothing proposed; nothing wired.

Pre-registration `INVENT_2026-08-26B_cefnav_PREREG.md` sha256 `f2072b41699ca49f9f31036d1fbb293270411790df5f8ecda863968f07020d21`; frozen shortlist `INVENT_2026-08-26B_cefnav_SHORTLIST.json` sha256 `095e7b61b227d540440e4a7746cf586edee6fb261d951cde14ecd0b70166fc27` written before any held-out number. Harness `scripts/trading_bot/invent_0826b_cefnav.py` (stages `design` / `reveal`).

## 0. Disjointness

Prior dead objects: `DEEPMINE_CEFNAV.md` M01/M02 (fade 1w/4w **total** discount change, weekly grid — bounce, −1.62/−0.89 after lag-1 + p90), S01 (fade 4w price−NAV spread), S03/S04 (raw NAV total-return momentum 4w/13w, negative on design); `INVENT_0822C_cefdeep.md` category-relative NAV momentum (2.47, sub-bar). **New here:** the daily-grid decomposition of the k-session discount change (k = 1/5/10, hold 5) into NAV-driven and price-driven parts scored side by side with the price part as control, and the 1-week decomposition on the weekly panel. Adjacent to dead objects; run to close the gap.

## 1. Data and construction

* Daily panel: `t12_cache/history_1Y` daily price+NAV × `adjusted_bars`, 245 sessions 2025-08-18 → 2026-08-07, 358 funds, 316 with NAV changing on ≥ 70 % of sessions (the rest publish weekly and were excluded). Design 2025-08-18 → 2026-03-18 (60 %), held-out 2026-03-19 → 2026-08-07.
* Weekly panel: `history_5Y` Friday price+NAV, 248 weeks, design 2021-08-20 → 2024-08-16, held-out 2024-08-23 → 2026-08-07 (overlaps T12 held-out; declared in prereg).
* NAV total return = Δlog NAV + (adjusted − raw price return) so ex-distribution drops are not counted as innovations. Tercile L/S, equal-weight, dollar-neutral, price > $5, short leg easy-to-borrow, signal at close t, **entry at close t+1**; same-close (lag 0) reported only as the bounce diagnostic.
* Pooled fund-level ρ1: Δprem (daily) -0.117; raw price return 0.030; NAV total return 0.058. Mild bounce in the discount change, none in the P&L series of any formula (all ρ1(P&L) > −0.17).
* Costs: half-spread 11.53 bp (p75 18.38, p90 27.25) per unit turnover both sides; borrow 200 bp/yr on short leg; SEC 0.278 bp on sales. Bar √(2 ln 12) = **2.229** in t, gross, gap-1. Placebo: cross-sectional signal permutation, 300 draws. Note the placebo t has sd ≈ 0.6 (daily) / 0.88 (weekly), i.e. narrower than N(0,1) because random CEF books have negatively autocorrelated P&L; the 95th percentile of the placebo is used as written.

## 2. Design window (all 12 formulas, gap-1 unless stated)

| id | n | gross bp/period | gross t | Sharpe | same-close t | gap-1/lag0 | ρ1 | turnover | net bp (median hs) | net t | placebo pct | gates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `D_NAV_k1` | 141 | 1.59 | 0.96 | 1.29 | 3.69 | 0.261 | 0.123 | 0.494 | -4.65 | -2.82 | 22.0 | bar, gap1, placebo fail |
| `D_NAV_k5` | 134 | 0.14 | 0.05 | 0.07 | 0.6 | 0.09 | 0.128 | 0.499 | -6.28 | -2.32 | 2.7 | bar, gap1, placebo fail |
| `D_NAV_k10` | 111 | 1.4 | 0.41 | 0.62 | 0.81 | 0.505 | 0.05 | 0.374 | -3.63 | -1.06 | 6.0 | bar, placebo fail |
| `D_PRC_k1` | 141 | 2.24 | 1.48 | 1.98 | 1.05 | 1.408 | 0.01 | 0.532 | -4.44 | -2.93 | 53.3 | bar, placebo fail |
| `D_PRC_k5` | 134 | 3.09 | 1.13 | 1.55 | 1.13 | 1.002 | 0.019 | 0.524 | -3.63 | -1.33 | 41.0 | bar, placebo fail |
| `D_PRC_k10` | 111 | 2.1 | 0.57 | 0.86 | 0.47 | 1.217 | -0.044 | 0.387 | -3.09 | -0.84 | 11.0 | bar, placebo fail |
| `D_TOT_k1` | 141 | 2.58 | 2.92 | 3.91 | 6.76 | 0.432 | -0.033 | 0.528 | -4.03 | -4.56 | 98.7 | gap1 fail |
| `D_TOT_k5` | 134 | 3.33 | 2.53 | 3.46 | 4.09 | 0.618 | 0.022 | 0.556 | -3.74 | -2.85 | 96.3 | PASS |
| `D_TOT_k10` | 111 | 3.78 | 2.24 | 3.37 | 3.19 | 0.702 | 0.049 | 0.425 | -1.82 | -1.08 | 93.0 | placebo fail |
| `W_NAV_1w` | 147 | 7.52 | 0.74 | 0.44 | 2.97 | 0.25 | -0.163 | 2.673 | -42.88 | -4.28 | 90.3 | bar, gap1, placebo fail |
| `W_PRC_1w` | 147 | 27.22 | 3.8 | 2.26 | 2.45 | 1.551 | 0.022 | 2.812 | -24.81 | -3.45 | 100.0 | PASS |
| `W_TOT_1w` | 147 | 34.44 | 6.33 | 3.77 | 9.34 | 0.678 | 0.07 | 2.96 | -19.32 | -3.55 | 100.0 | PASS |

Period = session (D) or week (W). Turnover is per period on gross 2.0.

**Decomposition clause (t_NAV − t_PRC at gap-1, needs ≥ +1.0):** D_k1 -0.52, D_k5 -1.08, D_k10 -0.16, W_1w -3.06. **Fails everywhere, wrong sign.** The NAV-driven part is the *weakest* of the three at every horizon.

Reading: `D_NAV_k1` shows t 3.69 at same-close and 0.97 at gap-1 — whatever NAV-driven signal exists is consumed inside the stamp session, exactly the `DEEPMINE_CEFNAV` §6a pattern. `W_NAV_1w` same: 2.97 → 0.74. The three formulas that clear the bar on gross (`D_TOT_k5`, `W_PRC_1w`, `W_TOT_1w`) are the OU baseline and the price-reversal control — none is the object of the round — and all are net-negative at the median half-spread on design (turnover 0.56/session or 2.8–3.0/week against 3–34 bp gross).

## 3. Held-out (shortlist only, read once)

| id | n | gross bp | gross t | Sharpe | same-close t | ρ1 | net bp median | net t median | net t p90 | signs | conc. | corr to level tilt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `D_TOT_k5` | 94 | 0.08 | 0.051 | 0.083 | 2.44 | 0.037 | -7.223 | -4.628 | -10.399 | [1.0, -1.0] | 14.502 | — |
| `W_PRC_1w` | 88 | 21.828 | 1.925 | 1.479 | 2.24 | 0.223 | -30.352 | -2.693 | -6.676 | {'2024': 1.0, '2025': 1.0, '2026': 1.0} | — | -0.188 |
| `W_TOT_1w` | 88 | 10.524 | 1.625 | 1.249 | 5.06 | 0.103 | -43.909 | -6.773 | -14.034 | {'2024': 1.0, '2025': 1.0, '2026': 1.0} | — | 0.225 |

* `D_TOT_k5`: held-out gross **t 0.05** at gap-1 (2.44 at same-close) — the design gap-1 pass (62 % of lag0) was luck; on held-out the entire gross is inside the stamp session. Half-signs disagree. Net −7.2 bp/session. Dead.
* `W_PRC_1w`: held-out gross t 1.93 (below bar), per-year all positive but 2026 ≈ +1 bp/wk, net −30 bp/wk at the median half-spread. Price reversal inside CEFs is a gross-only object. Dead.
* `W_TOT_1w`: held-out gross t 1.63 at gap-1 vs 5.06 at same-close (32 % survives) — bounce; net −44 bp/wk. This is `DEEPMINE_CEFNAV` M01 again in tercile form and it dies the same way. Dead.

## 4. Power

Daily held-out 94 sessions: minimum detectable Sharpe at the bar ≈ 3.65; weekly held-out 88 weeks: ≈ 1.71. The daily panel alone cannot exclude a Sharpe-1 NAV effect. But the *design* NAV numbers on 111–141 sessions (t 0.97 / 0.05 / 0.41, Sharpe 1.3 / 0.07 / 0.6) and the 147-week weekly panel (t 0.74, Sharpe 0.44, with gross 7.5 bp/wk against 31 bp/wk of spread cost) are centred on zero, not on an undetected large effect; and even a Sharpe-1 gross effect at 0.5/session turnover is −4 bp/session net. The object is dead on distance-from-zero and on cost simultaneously.

## 5. Dead-ledger entries

1. NAV-innovation / NAV-momentum / NAV-driven discount change at any horizon 1 session to 13 weeks (dead across DEEPMINE_CEFNAV S03/S04, cefdeep I01, this round D_NAV_k1/5/10, W_NAV_1w)
2. total Δdiscount fade at 1-10 sessions or 1-4 weeks (OU baseline: gross-only, bounce at k=1, net -4 to -44 bp per period, held-out zero at gap-1)
3. price-reversal within CEFs at daily/weekly horizon (W_PRC_1w: gross t 1.9 held-out, net -30 bp/wk)

Mechanism note for the ledger: the CEF NAV tether is published, synchronous and free, yet the price does **not** lag it in any tradable way — the closing print of the stamp session already embeds the NAV move (same-close t 3.7 / 3.0 → gap-1 1.0 / 0.7). This is consistent with the standing conclusion: the level tilt (T12) works because it harvests a slow-moving *statistic*; a NAV *innovation* is news and the auction prices it before a retail rail can act.

## 6. Proposals

None. Basket untouched.

## 7. Files

* `research/trading_bot/INVENT_2026-08-26B_cefnav_PREREG.md`
* `research/trading_bot/INVENT_2026-08-26B_cefnav_DESIGN.json`
* `research/trading_bot/INVENT_2026-08-26B_cefnav_SHORTLIST.json`
* `research/trading_bot/INVENT_2026-08-26B_cefnav_REVEAL.json`
* `research/trading_bot/INVENT_2026-08-26B_cefnav.md`
* `research/trading_bot/INVENT_2026-08-26B_cefnav.json`
* `scripts/trading_bot/invent_0826b_cefnav.py`
