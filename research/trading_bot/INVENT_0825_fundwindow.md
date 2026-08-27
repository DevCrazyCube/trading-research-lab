# INVENT_0825 — PERP FUNDING-SETTLEMENT-WINDOW MICRO-DYNAMICS

**Verdict: NOISE for trading purposes. Honest zero.** 28 formulas, nothing survives the
pre-committed bar out of sample, and the whole family's *best* out-of-sample breakeven is
**1.67 bp/side — below Binance USD-M VIP0's own 2.0 bp maker fee.** The theme is uneconomic at
the exchange fee floor even granting a free, perfectly-filled limit order and zero adverse
selection.

This is a fresh theme, not a re-test: the dead carry work (T21/T23/T25) looked at funding
**level**; this looked at the mechanical **behaviour** around the 8h settlement timestamps.

---

## 1. Setup

| item | value |
|---|---|
| Universe | 50 Binance USD-M perps, ranked by **2022** hourly quote volume — entirely before the design window, so no lookahead; delisted names (MATIC 47% coverage, FTM 58%, APE 69%, TLM 8%) are kept and simply go NaN |
| Bars | **5-minute** OHLCV + taker-buy quote (`orphanflush_cache/raw/klines5m`), 2023-01-01 → 2026-08-16, 381,024 bars |
| Open interest | 5-minute `sum_open_interest_value` (`orphanflush_cache/raw/metrics`), 99.8% coverage |
| Funding stamps | exact prints from the survivorship-complete `t23_cache` panel; **8h-interval prints only** (184,475 of 192,718 for this universe; 7,810 are 4h, 433 are 1h). **184,377 usable events / 3,922 stamps**, hours exactly {0, 8, 16} UTC |
| Design | 2023-01-01 → 2024-12-31 |
| Held-out | 2025-01-01 → 2026-07-31, scored **only after** the design freeze (`INVENT_0825_fundwindow_DESIGN.sha256`, `freeze_ok = True`) |
| Fills | **open of the bar AFTER the last bar the signal reads**. Never same-bar, never the close that produced the signal |
| Funding P&L | charged/credited whenever a position is open across a stamp |
| Cost | 5.5 bp/side (4.5 bp Binance USD-M VIP0 taker + 1.0 bp declared half-spread) — repo convention; breakeven reported per formula |

### ρ1 bounce gate — run BEFORE any gross claim

5-minute open-to-open returns on the traded universe: **mean ρ1 = -0.020**,
median -0.017, worst symbol -0.103
(48 symbols). Threshold −0.35. **PASSES comfortably.** Liquid perp 5m opens are not a bounce
series — unlike the memecoin daily book (−0.43…−0.57). So nothing below is a Clause-4 artifact,
and every ρ1(pnl) in the table is inside ±0.12. *This theme did not die of bounce; it died of
cost and of the calendar placebo.*

---

## 2. The two nulls

| null | value |
|---|---|
| Analytic `sqrt(2 ln N)`, N = 28 | **2.58** |
| **Null 1 — size-matched signal permutation** (weights reassigned across the symbols trading at the *same stamp*; per-stamp net exposure and gross size preserved exactly; 300 draws × 28 formulas) | family max&#124;SR&#124; mean **1.57**, **p95 = 2.00** |
| **Null 2 — calendar placebo** (the identical 28 formulas anchored **+1h…+7h after** each stamp — none of those is a funding time; price-only both sides) | family max&#124;SR&#124; per shift 3.07 / 3.91 / 2.77 / **4.58** / 2.29 / 3.16 / 2.65, **mean 3.20** |
| **Pre-committed gross bar** = max of the three | **3.20** |

The calendar placebo is the null that matters and it is **larger than the analytic bar** — the
opposite of the usual understatement. Anchoring a 5-minute cross-sectional reversal book at an
arbitrary hour of the day produces design Sharpes of 2.3–4.6 *with no funding event anywhere near
it*. Any funding-window claim has to clear that, not 2.58.

---

## 3. All 28 formulas

Columns: design gross SR · design gross **price-only** SR · design **calendar-placebo mean** ·
held-out gross SR (design sign frozen) · held-out **net** SR @5.5 bp · held-out permutation-null
p95&#124;SR&#124; · held-out calendar-placebo max&#124;SR&#124; · held-out breakeven bp/side.

| formula | kind | des gross | des px-only | des placebo | **OOS gross** | **OOS net** | OOS perm p95 | OOS placebo max | OOS b/e bp |
|---|---|---|---|---|---|---|---|---|---|
| `E3_STAMPBAR_FADE_15` | XS | +5.54 | +5.54 | +3.16 | +3.84 | -28.09 | 1.49 | 4.28 | +0.66 |
| `E2_STAMPBAR_MOM` | XS | -4.38 | -4.38 | -2.23 | +2.81 | -20.66 | 1.55 | 3.41 | +0.66 |
| `E1_STAMPBAR_FADE` | XS | +4.38 | +4.38 | +2.22 | +2.82 | -20.66 | 1.66 | 3.43 | +0.66 |
| `C3_XS_POST_MAG_15` | XS | +3.32 | +3.32 | +0.69 | +0.70 | -41.70 | 1.55 | 1.40 | +0.09 |
| `C2_XS_POST_MAG_30` | XS | +2.66 | +2.66 | +0.60 | +1.37 | -29.75 | 1.59 | 2.14 | +0.24 |
| `C4_XS_POST_MAG_120` | XS | +2.44 | +2.44 | +0.28 | +2.21 | -14.79 | 1.51 | 1.51 | +0.71 |
| `G1_XS_TAKER_PRE_FADE` | XS | +2.20 | +2.35 | +0.96 | +0.76 | -34.15 | 1.44 | 2.80 | +0.12 |
| `G2_XS_TAKER_PRE_MOM` | XS | -2.20 | -2.35 | -0.96 | +0.76 | -34.15 | 1.55 | 2.80 | +0.12 |
| `C1_XS_PRE_MAG_30` | XS | +2.10 | -0.45 | -0.14 | +3.04 | -28.99 | 1.50 | 1.26 | +0.52 |
| `A2_PRE_FADE_15` | TS | +2.01 | +0.56 | -0.41 | +1.46 | -17.50 | 0.88 | 0.97 | +0.42 |
| `F4_XS_OI_SQUEEZE` | XS | +1.64 | +1.60 | +0.27 | -0.71 | -28.77 | 1.62 | 1.73 | -0.14 |
| `D3_FLIP_TO_NEG_LONG` | TS | +1.43 | +1.43 | +0.71 | -0.26 | -2.86 | 0.26 | 0.88 | -0.54 |
| `F2_XS_OI_BUILD_PRE` | XS | -1.22 | -1.24 | -0.61 | +1.64 | -23.57 | 1.59 | 1.04 | +0.36 |
| `F1_XS_OI_UNWIND_PRE` | XS | +1.22 | +1.24 | +0.61 | +1.61 | -23.60 | 1.50 | 1.04 | +0.35 |
| `A6_PRE_FADE_30_BIG` | TS | +1.15 | -0.55 | -0.23 | +1.68 | -4.07 | 1.69 | 1.98 | +1.61 |
| `A1_PRE_FADE_30` | TS | +1.12 | +0.15 | -0.32 | +1.57 | -11.14 | 1.21 | 1.38 | +0.68 |
| `A5_PRE_FOLLOW_30` | TS | -1.12 | -0.15 | +0.32 | +1.57 | -11.14 | 1.23 | 1.38 | +0.68 |
| `B4_POST_FADE_15` | TS | +0.88 | +0.88 | -0.17 | +0.13 | -14.26 | 0.37 | 1.24 | +0.05 |
| `A3_PRE_FADE_60` | TS | +0.76 | +0.12 | -0.46 | +1.23 | -6.94 | 0.87 | 1.39 | +0.83 |
| `G4_XS_VOLSPIKE_FADE` | XS | -0.51 | -0.38 | -0.50 | -0.63 | -26.33 | 1.67 | 0.93 | -0.14 |
| `D1_FLIP_FOLLOW_120` | TS | +0.41 | +0.41 | -0.62 | +1.28 | -2.93 | 2.34 | 0.97 | +1.67 |
| `D2_FLIP_FADE_120` | TS | -0.41 | -0.41 | +0.62 | +1.28 | -2.93 | 2.33 | 0.97 | +1.67 |
| `F3_XS_OI_POST` | XS | -0.40 | -0.40 | +0.54 | +1.84 | -13.12 | 1.68 | 1.56 | +0.68 |
| `B3_POST_FADE_120` | TS | +0.36 | +0.36 | -0.34 | +0.81 | -5.41 | 0.83 | 1.08 | +0.72 |
| `B1_POST_FADE_30` | TS | +0.35 | +0.35 | +0.04 | +0.34 | -10.78 | 0.46 | 0.80 | +0.17 |
| `B2_POST_FOLLOW_30` | TS | -0.35 | -0.35 | -0.04 | +0.34 | -10.78 | 0.49 | 0.80 | +0.17 |
| `G3_XS_RUNUP_FADE_1H` | XS | +0.17 | +0.23 | +0.19 | -1.12 | -17.54 | 1.48 | 2.36 | -0.38 |
| `A4_PRE_FADE_30_FLAT` | TS | +0.07 | +0.07 | -0.20 | +0.91 | -12.86 | 1.03 | 1.35 | +0.36 |

**Design bar clearers (4, all one hypothesis + its mirror):** `E3_STAMPBAR_FADE_15` (+5.54),
`E1/E2_STAMPBAR_FADE/MOM` (±4.38), `C3_XS_POST_MAG_15` (+3.32). Top-3 carried forward per the
frozen rule.

---

## 4. Why it is a zero — four independent kills

**(a) The design winner is not a funding effect.** `E1/E3_STAMPBAR_*` = fade the cross-sectional
rank of the settlement bar's own body over the next 15–30 min. Its calendar placebo mean is
**+3.16 in design and +2.29 out of sample, against a stamp value of +5.54 / +3.84** — and its
out-of-sample placebo *max* is **4.28, above the stamp's own +3.84**. Most of it is generic 5-minute
cross-sectional reversal that exists at 4am as happily as at a funding stamp. The stamp adds a
sliver, and out of sample the sliver does not clear its own placebo. **Fails null 2 OOS.**

**(b) The one genuinely stamp-specific design winner collapsed.** `C3_XS_POST_MAG_15` (long the
most-negative funding names for 15 min starting 5 min after the stamp) was the cleanest theme
evidence in design: +3.32 stamp vs +0.69 placebo mean (z = +4.31). Out of sample: **+0.70**, below
its own permutation p95 of 1.55. Gone.

**(c) The pre-stamp books are a funding snipe, not a price effect.** Decomposing the
positions that hold across the stamp:

| formula | window | gross SR | price-only SR | funding component |
|---|---|---|---|---|
| `C1_XS_PRE_MAG_30` | design | +2.10 | **−0.45** | +2.55 |
| `C1_XS_PRE_MAG_30` | held-out | +3.04 | +1.19 | +1.85 |
| `A6_PRE_FADE_30_BIG` | design | +1.15 | **−0.55** | +1.70 |
| `A6_PRE_FADE_30_BIG` | held-out | +1.68 | +0.60 | +1.09 |

There is **no pre-settlement price squeeze**. The raw 5-minute drift profile from −90m to +90m,
split by funding sign, oscillates ±3 bp with no coherent shape in either direction. What these
books earn is the funding payment itself, collected by holding for 30 minutes around the stamp
instead of 8 hours. That mechanic is real — and it pays **mean &#124;funding&#124; = 1.21 bp**
(median 1.00, p90 1.97, p99 6.98) against an **11 bp round trip**. Uneconomic by ~9×. `C1` is the
theme's most interesting object — held-out gross +3.04 with a calendar placebo of −0.14/max 1.26,
i.e. unambiguously stamp-specific — and it is still a 0.52 bp/side breakeven. It is an
**observation, not a finding**: design gross +2.10 was below the 3.20 bar, so under the
pre-committed protocol it never earned the held-out window.

**(d) The cost wall, stated exactly.** Across all 28 formulas and both windows the largest
breakeven is **3.48 bp/side in design and 1.67 bp/side out of sample**. Binance USD-M VIP0 is
**4.5 bp taker / 2.0 bp maker**. The best member of this family does not clear the **maker** fee
with a free spread and zero adverse selection. Mean out-of-sample gross is **0.93 bp per round
trip**; the single best is 3.35 bp. There is no hold-length, no sizing and no venue tier that
turns 1–3 bp of 3×-per-day signal into a positive number against an 11 bp toll. This is
`EXECUTION_COST_WALL.md`'s point in its purest form: the toll is a **significance** wall here —
you would need roughly 10× the signal, not 10% better execution.

---

## 5. Is the theme itself anything?

Design→held-out rank correlation across all 28 formulas: **ρ = +0.198** (t ≈ 1.03, n = 28)
— indistinguishable from zero, i.e. the design window does not tell you which funding-window
formula will work next. 24 of 28 are positive on out-of-sample gross with the frozen design sign,
but that count is inflated by six mirror pairs and by the generic-reversal component that the
calendar placebo shows is not a funding effect at all.

**Two things about the funding window are true and worth keeping:**

1. **The settlement instant is a mild cross-sectional reversal amplifier** — the stamp-bar fade
   runs ~1.5 SR hotter at the stamp than at non-funding anchors, consistently in both windows.
   Real, tiny, and already inside the generic 5m-reversal family.
2. **Full 8h funding is collectable in a 30-minute hold**, and the cross-sectional version of that
   snipe is genuinely stamp-specific out of sample (`C1`, placebo −0.14). At retail perp fees the
   snipe pays 1.2 bp and costs 11 bp. It only becomes interesting to somebody who is *already*
   trading the name and can time an existing position's entry/exit to the stamp — i.e. it is an
   **execution-timing overlay**, not a strategy.

**Nothing here is proposed for the basket. The forward clock stays untouched.**

---

## 6. Dead-ledger entries

Add: *pre-settlement positioning drift* (A-family), *post-settlement funding-sign reaction*
(B-family), *funding-sign-flip reactions* (D-family), *OI unwind/build around settlement*
(F-family), *pre-stamp taker-flow / run-up / volume-spike fades* (G-family), and
*settlement-bar cross-sectional reversal* (E-family, = generic 5m reversal in a calendar mask).
Keep as a **logged-only observation**: `C1_XS_PRE_MAG_30`, the 30-minute cross-sectional funding
snipe — stamp-specific, sub-breakeven, protocol-ineligible.

## 7. Artefacts

- `scripts/trading_bot/f0825_panel.py` — 5m panel builder (universe from 2022 volume only)
- `scripts/trading_bot/f0825_lib.py` — harness (next-bar fills, funding P&L, ρ1, evaluate)
- `scripts/trading_bot/f0825_formulas.py` — the 28 formulas
- `scripts/trading_bot/f0825_design.py` — design scoring + both nulls + freeze
- `scripts/trading_bot/f0825_holdout.py` — held-out scoring against the frozen file
- `research/trading_bot/INVENT_0825_fundwindow_DESIGN.json` (+ `.sha256`)
- `research/trading_bot/INVENT_0825_fundwindow_HOLDOUT.json`
- `research/data/fund0825_cache/` — panel5m.npz (213 MB), funding.pkl, logs (gitignored, regenerable)
