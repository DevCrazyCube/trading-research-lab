# INVENT_0825 — FROZEN SHORTLIST

**Written and committed BEFORE the held-out window (2025-01-02 → 2026-08-14) was read.**
Design window 2021-01-04 → 2024-12-31. Nulls in `INVENT_0825_opendrive_null.json`.

## The bar

Block-bootstrap best-of-26, 2000 resamples, block = 5 sessions, same day indices for every config:

| | net@1.0bp | gross |
|---|---|---|
| mean | +0.93 | +0.93 |
| **p95 — the operative bar** | +1.41 | **+1.44** |
| p99 | +1.74 | +1.72 |
| analytic √(2 ln 26)/√years | +1.31 | — |

**Degeneracy disclosed:** cross-sectional demeaning makes `PB_IDIOGAP_FADE` numerically identical
to `PB_GAPZ_FADE`, and `PB_DRIVE_EXMKT_FADE` identical to `PB_DRIVEZ_FADE`. The 26 pre-registered
books are **24 distinct books**. The bootstrap is run on the 26 actual series as pre-registered
(duplicates cannot raise a maximum, so this is the conservative choice).

## Promotion status on design

| gate | `PA_GAP_CD_FADE` |
|---|---|
| gross > best-of-26 p95 (+1.44) | **+2.36 — PASS** |
| one-bar-gap re-entry gate | gap-fill gross **+2.46** ≥ primary; **PASS** |
| ADV-decile permutation on gross, p < 0.05 | **p = 0.0020** (null mean +0.89, p95 +1.49) — PASS |
| held-out net@1.0bp > 0 | **not yet read** |

**Exactly one of the 26 clears the first three gates.** No other config beats +1.44 gross
(next best `PA_OD30_CD_FADE` +0.98, perm p = 0.088).

## Held-out list (frozen)

| # | config | role |
|---|---|---|
| 1 | `PA_GAP_CD_FADE` | **the candidate** — fade the overnight gap z-score, enter 15:35 (bar 71 VWAP), exit bar-77 VWAP, 34 mega-caps |
| 2 | `PB_GAPZ_FADE` | independent-panel confirmation (point-in-time top-500, auction exit) |
| 3 | `PB_GAPZ_FADE_T150` | the same on the top-150 ADV subset |
| 4 | `PA_OD30_CD_FADE` | negative control — runner-up, failed the permutation |
| 5 | `PA_ODISL_X_GAP` | negative control — best of the new opening-dislocation instrument |
| 6 | `PA_GAP_FADE_ALLDAY` | **POST-HOC, LABELLED, CANNOT BE PROMOTED.** Same score, entry bar 6 (10:00) instead of bar 71, from the entry-slot diagnostic. Reported only to test whether the *mechanism* rather than the *slot* persists. |

**Pre-sample (Panel B only, 2016-01-04 → 2020-12-31, declared in the pre-registration, can only
kill):** `PB_GAPZ_FADE`, `PB_GAPZ_FADE_T150`, `PB_TOTMOVE_FADE`.

## Why `PA_GAP_CD_FADE` was not dismissed as the usual best-of-N fluke

Recorded before the held-out read, so the reasoning cannot be retrofitted:

1. **Anti-artefact decomposition is the mirror image of the one that killed 0823's `G1`.**
   `G1` had **152%** of its gross in the ten minutes right after the signal print. Here the first
   bar after entry (71→72) carries **1.7%** of the gross (+0.02 of +1.44 bp/day); 98.3% is in bars
   72→77. The gap fill scores *higher* than the primary fill (+2.46 vs +2.36).
2. **The entry-slot profile is positive at all ten slots tested** (bars 6, 12, 24, 36, 48, 60, 66,
   71, 74, 76): gross Sharpe +0.33 … +2.36, bp/day +0.20 … +3.69, decaying in bp/day as the hold
   shortens and rising in Sharpe as the late-day noise falls. A single-slot fluke does not do that.
3. **Dose-response is monotone in the signal magnitude.** Splitting the book by |gap z|:
   small-gap tercile **−0.37 bp/day**, mid **+0.34**, large **+1.54**.
4. **Two independent panels agree in sign.** Panel B (point-in-time top-500, official auction
   exit, no survivorship bias, raw prices) gives the same-signed +0.85 gross; the daily-PnL
   correlation between the two books is only 0.23, so they are not the same trade twice.

## What would still kill it, stated in advance

- **Cost.** Design break-even is **0.77 bp/turnover** against a repo-measured 1.13 bp liquid-name
  half-spread. Net@1.0 bp on design is **−1.16**. On the pre-registered rail this is a *gross-real,
  net-dead* object, and it is being carried to the held-out window on the gross gate alone, exactly
  as the discipline prescribes. The only rail that could rescue it is the closing auction (0 bp
  spread, M0-measured), which the Panel-A cube cannot price — Panel B can, and Panel B's
  break-even is only 0.35 bp.
- **Survivorship.** Panel A's 34 mega-caps are today's mega-caps. Panel B is the honest breadth
  check and it is much weaker.
- **Held-out net.** Per §6 of the pre-registration, a negative held-out net@1.0 bp is fatal
  regardless of how good the gross looks.

---
**Nothing in this file may be edited after the held-out window is read.**
