# T58 — STICKYSHORT (settle-through) — DESIGN HALF: **DEAD at the friction floor (K3)**

Run 2026-09-06 03:00 CEST, CHUNK B (durable supervisor). Shell PROVEN (canary emitted + acked).
Prereg: `research/trading_bot/INVENT_2026-09-05_1500_desk.md` (frozen 2026-09-05 15:00, sha `fc4cec4c…`),
plus sequencing amendment **K0** recorded 2026-09-06 00:00 (`STRATEGIST_2026-09-06_0000.md`):
*run the design half first and alone; if it fails the size bar or carries the wrong sign, the
candidate is DEAD and the held-out half is NOT touched.*

Runner: `/tmp/t58_design.py` (reproduced below in substance); machine output:
`research/trading_bot/T58_STICKYSHORT_DESIGN_HALF.json`.

## What was run — exactly the frozen rules, nothing else

- Panel `research/data/newterr_shortint/panels.npz` (3,812 symbols × 2,669 sessions; 207 settlement dates).
- Design half only: settlement indices 1…102 (prereg dates 1–103). **Held-out 104–207 NOT TOUCHED.**
- `STR = (SI(t) − SI(t−1)) / Σ daily short volume over sessions in (settle(t−1), settle(t)]`, restricted to ΔSI > 0.
- Universe at each t: non-ETF, cum short volume > 100k sh, close ≥ $5 at `si_avail_idx[t]`,
  median dollar volume over the window ≥ $1M, ≥5 finite short-volume sessions.
- Sign as frozen: **long Q1 (churn) / short Q5 (committed)**, equal weight, quintiles.
- Timing as frozen: enter at the **open of the session after `si_avail_idx[t]`**, exit at the open of
  the session after `si_avail_idx[t+1]`. Every entry keys off `si_avail_idx`, never `si_settle`.
- Costs: **10 bp/side on MEASURED turnover** (Σ|Δw| across both legs, period over period), not assumed 100%.

**Breadth (K1).** 102 periods attempted, **88 usable**, 14 skipped on breadth — all of them before
2018-08, i.e. the daily short-volume panel simply does not start until 2018-08. Median usable
N = **1,010 names**/period, far above the K1 floor of 300. The object is not power-blocked on breadth.

## Result

| quantity | value |
|---|---|
| usable design observations | **88** |
| mean measured turnover / period | **1.710** (171% of book, both legs) |
| **gross** annualized (26 obs/yr) | **+6.00%** — CI90 **[−1.20%, +13.37%]**, Sharpe/obs 0.145 |
| cost drag annualized | **−4.45%** |
| **net** annualized | **+1.56%** — CI90 **[−5.63%, +8.92%]** |
| net Sharpe / obs | 0.038 (≈0.19 annualized) |
| periods net-positive | 54.5% |
| subsumption control (days-to-cover L/S, same universe) | **−1.69%**/yr gross |

## Verdict: **DEAD — K3 fires, and K2 fires with it**

- **K3 (net annualized < 3%): FIRES.** +1.56% net, against a pre-committed 3%/yr size floor. This is
  the fourth data family to die exactly where the prior said it would: at the friction floor.
- **K2 (CI-lo ≤ 0): FIRES.** Net CI90-lo = −5.6%/yr. Even *gross* the CI straddles zero
  (−1.2%/yr), so at N=88 the raw effect is not distinguishable from noise — precisely the power
  limit written down before the run (min detectable ≈0.83 annualized Sharpe; observed gross 0.74).
- **K5 (sign flip): does not fire.** The sign came out as frozen — Q1-churn beats Q5-committed.
  The candidate died on *size*, not on direction.
- **K4 (subsumption): moot, but informative.** The days-to-cover long/short on the identical universe
  returns **−1.69%**/yr gross, opposite in sign to STR. So STR is genuinely **not** the published
  short-interest anomaly under a new normalizer — the invention's one distinctive claim survived. It
  just does not survive 10 bp/side.

**Why it dies, mechanically and without ambiguity.** Turnover is **171% of the book every fortnight**.
STR is a *ratio of two noisy differences*, so quintile membership reshuffles almost completely
between settlement dates; at 26 rebalances a year that is 4.45%/yr of cost eating a 6.00%/yr gross
signal that was itself inside its own confidence interval. There is no honest parameter that fixes
this: widening the sort reduces turnover only by diluting the signal, and no cost assumption below
10 bp/side is defensible for a several-hundred-name small/mid-cap short book.

**Per K0 the held-out half (settlement 104–207) was NOT run and must not be run.** The shot is
declined, not spent. No parameter was changed; no rule, threshold, prereg or pin was altered. A dead
design half cannot be revived by a later edit.

## Disclosed deviation (one, and it is not load-bearing)

The prereg's subsumption control specifies **SI/float**. The panel carries no shares-outstanding or
float field, so the control was run as **SI/ADV (days-to-cover)** — the other standard published
normalizer. This is disclosed rather than silently substituted. It changes nothing: K3 and K2 both
fire on the primary result, and the control was directionally *favourable* to us anyway.

## Consequence for the programme

Per the STRATEGIST kill-condition frozen at 2026-09-06 00:00: **a dead design half CLOSES the free
short-side panel family** — the third data family closed after chart-price and carry — and the
programme has **no runnable free direction left**. The honest response is *not* another invention
round; it is to let the 09-22 (T30 borrow) and 09-23 (T31 Deribit) gates drive the pay-or-stop fork
as written in `PAY_OR_STOP_DECISION_PACKET.md`.

Directional record is now **0-for-9**.

## Guardrails
Paper/research only. No orders, no spend, no broker auth. Nothing committed or staged. BASKET1
untouched — no leg, no re-freeze. t4 path untouched. No instrument restarted, re-activated,
re-epoched or resolved. Held-out half untouched.
