# INVENT_2026-08-26B — CEF NAV-innovation underreaction — PRE-REGISTRATION

**Frozen before any return, signal, portfolio, t or Sharpe was computed.** Written 2026-08-26.
Research/paper only. No network. Nothing is wired; basket is locked.

## 0. Disjointness (done before this file)

Grep of `research/trading_bot/*.md` and `research/FINDINGS.md` for NAV / nav_ret / ΔNAV / discount change:

* `DEEPMINE_CEFNAV.md` (weekly grid, 2021-08 → 2026-08): `M01/M02` fade 1w/4w **total** discount change
  (design t 5.48 / 4.17 → **−1.62 / −0.89** after lag-1 + p90 spread: bounce); `S01` fade 4w price−NAV
  spread (4.79 → −0.64); `S03/S04` **raw NAV total-return momentum 4w / 13w, long** — negative on design.
* `INVENT_0822C_cefdeep.md`: category-relative NAV momentum 4w/13w — best new primitive at 2.47, sub-bar, dead.
* `T12_PREREGISTRATION.md` §1: NAV-return decomposition used only as a *diagnostic* of the level tilt, never as a signal.

**Not previously run:** the *daily-grid* decomposition of the k-session discount change (k ≤ 10) into its
NAV-driven and price-driven parts, scored side by side with the price-driven part as an explicit control,
and the 1-week version of that same decomposition on the weekly panel (only the *total* 1w change and the
4w/13w NAV momentum were run). That is the object here. It is adjacent to dead objects and the prior is
strongly toward zero; the point of the round is to close the gap honestly, not to find something.

## 1. Mechanism

The sponsor publishes NAV daily at 16:00 ET (a synchronous published tether). The discount changes
for two reasons: the price moved, or the NAV moved. If retail-dominated CEF prices adjust to NAV
innovations with a lag, then the part of the discount change that was caused by the NAV moving
(price stood still while NAV rose ⇒ discount widened) should be reversed over the next k sessions by
the *price* catching up — i.e. **long funds whose NAV just rose relative to price**. The part caused by
the *price* moving is the closing-print reversal / bid-ask bounce object that has been killed
repeatedly; it is included as the control that must NOT survive the one-session gap. The claim being
tested is specifically: **NAV-driven Δdiscount predicts, price-driven Δdiscount does not (after gap-1)**.

## 2. Data (all pre-existing caches, `research/data/t12_cache/`)

* `history_1Y.json.gz` — 360 funds, daily {price, nav, discount}, 2025-08-18 → 2026-08-14 (253 sessions). Daily panel **D**.
* `history_5Y.json.gz` — same funds, weekly (Friday) {price, nav, discount}, 2021-08-20 → 2026-08-14 (249 weeks). Weekly panel **W**.
* `adjusted_bars.json.gz` — Alpaca distribution-adjusted daily close, 2021-08-20 → 2026-08-07. Used for realised P&L and for the distribution proxy.
* `cef_half_spread.json.gz` — measured closing half-spread: median 11.53 bp, p75 18.38, p90 27.25.
* `alpaca_assets.json.gz` — easy_to_borrow screen for the short leg.

Definitions per fund i, session t (log space):
* `r_p[t]  = log A[t]/A[t-1]` (adjusted price return, realised P&L rail)
* `r_raw[t] = log P[t]/P[t-1]` (raw CEFConnect close)
* `y[t] = r_p[t] − r_raw[t]` (distribution proxy; ≥ 0 on ex-dates, 0 otherwise)
* `r_nav[t] = log NAV[t]/NAV[t-1] + y[t]` (NAV **total** return, so ex-date drops are not "innovations")
* `Δprem_k[t] = Σ_{k} (r_raw − r_nav)` (≈ Δ log(P/NAV) over k sessions) = **price-driven** part Σ r_raw − **NAV-driven** part Σ r_nav.

Screens: price > $5 both legs; short leg easy_to_borrow; NAV must have **changed on ≥ 70 % of sessions**
in the panel (funds with weekly-published NAV are excluded from panel D — their "innovations" are stale
prints, not news); a fund-day needs a non-missing NAV on t and t−k.

## 3. Formulas — N = 12, fixed here

Cross-sectional construction, identical for every formula: on grid date t rank the signal across
eligible funds, go **long the top tercile / short the bottom tercile**, equal-weight, dollar-neutral
(gross 2.0, each leg 1.0). Signal is observed at close t; **entry at close t+1** (one-session gap:
the CEFConnect NAV stamp trails the print by a session per `DEEPMINE_CEFNAV` §6a). Same-close (lag 0)
is computed only as the bounce diagnostic and is never a claim.

Panel D (daily grid, overlapping-portfolio hold h = 5 sessions, Jegadeesh–Titman averaging):
| id | signal (long top tercile of …) | k |
|---|---|---|
| `D_NAV_k1` | Σ_k r_nav (NAV rose ⇒ NAV-driven widening ⇒ long) | 1 |
| `D_NAV_k5` | same | 5 |
| `D_NAV_k10` | same | 10 |
| `D_PRC_k1` | −Σ_k r_raw (price fell ⇒ price-driven widening ⇒ long) — **control, expected to die at gap-1** | 1 |
| `D_PRC_k5` | same | 5 |
| `D_PRC_k10` | same | 10 |
| `D_TOT_k1` | −Δprem_k (total widening ⇒ long) — the OU baseline | 1 |
| `D_TOT_k5` | same | 5 |
| `D_TOT_k10` | same | 10 |

Panel W (weekly grid, k = 1 week, hold 1 week, entry at the session after the Friday stamp, P&L from daily adjusted bars):
| id | signal |
|---|---|
| `W_NAV_1w` | Σ_1w r_nav, long top tercile |
| `W_PRC_1w` | −Σ_1w r_raw, long top tercile (control) |
| `W_TOT_1w` | −Δprem_1w, long top tercile (baseline; `M01` twin, expected dead) |

No regime conditioners, no gates, no category neutralisation, no parameter sweep beyond the k listed.

## 4. Windows

* Panel D: design = first 60 % of sessions with adjusted bars (2025-08-18 → ~2026-02-13); held-out = remainder (~2026-02-17 → 2026-08-07).
* Panel W: design = first 60 % of weeks (2021-08-20 → ~2024-08); held-out = remainder to 2026-08-07.
  **Declared:** the W held-out overlaps T12's held-out, so the discount-*level* family is not virgin there; this round scores no level signal, but any W survivor must be reported with its correlation to the T12 level tilt.

## 5. Bars, gates, nulls — fixed

* **Pooled bar:** √(2 ln N) with N = 12 ⇒ **t ≥ 2.23** (and Sharpe-equivalent) on the design window, **gross**, with entry at close t+1.
* **ρ1 gate (before any gross claim):** lag-1 autocorrelation of the daily L/S P&L series and of the pooled fund-level Δprem series. ρ1 ≤ −0.3 on the P&L ⇒ bounce, formula dead regardless of t.
* **Gap-1 vs same-close:** if gross at gap-1 < 50 % of gross at same-close, the gross was bounce, dead.
* **Decomposition clause:** the NAV formula must beat its PRC control at the same k (t_NAV − t_PRC ≥ 1.0) — otherwise the object is OU/bounce, not NAV underreaction, and is recorded as such.
* **Placebo:** size-matched signal permutation — on every grid date the signal vector is randomly permuted across the eligible funds (same tercile sizes, same dates, same costs), 300 draws; the real t must sit above the 95th percentile of the placebo t distribution.
* **Cost model (reported, never used to rescue):** half-spread 11.53 bp on every unit of realised turnover on both sides (ladder 18.38 / 27.25 also reported); borrow 200 bp/yr on the short leg accrued daily; SEC fee 0.278 bp on sales.
* **Design/held-out:** design shortlist = formulas clearing bar + ρ1 gate + gap-1 clause + placebo. Shortlist written to `INVENT_2026-08-26B_cefnav_SHORTLIST.json` with sha256 **before** any held-out number is produced. Held-out read once, shortlist only.

## 6. KILL conditions (any one ⇒ dead)

1. Design gross t < 2.23 at gap-1.
2. ρ1(P&L) ≤ −0.3, or gap-1 gross < 50 % of same-close gross.
3. Placebo percentile < 95.
4. NAV formula does not beat its PRC control (t gap < 1.0).
5. Held-out: gross t < 0 or net (median half-spread) ≤ 0, or per-year / per-half sign disagreement.
6. Any survivor is a **PROPOSAL ONLY**; nothing is wired.

## 7. Power statement (written before results)

Panel D held-out is ~95 sessions. A daily L/S needs annualised Sharpe ≈ 3.5 to reach t = 2.2 in 95 sessions;
anything below Sharpe ~2 is undetectable there. Panel D can therefore only *confirm* a very large effect or
*fail to reject* a small one; a null on D is "not decisive", and will be said so. Panel W held-out is
~100 weeks, detectable Sharpe ≈ 1.6.
