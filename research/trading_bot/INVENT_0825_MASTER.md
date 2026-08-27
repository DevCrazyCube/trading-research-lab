# INVENT_0825 — MASTER SYNTHESIS (lean daily)

**Date:** 2026-08-25
**Scope:** 2 fresh angles, **54 original formulas**, pooled multiple-testing correction over the total plus size-matched placebo nulls.
**Verdict: HONEST ZERO. 0 survivors. 0 basket proposals. 2 of 2 themes are noise.**
**Basket action: NONE.** BASKET1 is frozen at v8 (`frozen_utc` 2026-08-20T16:20:00Z, preregistration sha256 `fdf3730…3bda4cde`); the forward clock is **LOCKED** and untouched by this round. No leg added, no weight changed, no re-freeze.

---

## 1. What was run

| # | Theme | File | N | Own analytic bar | Own operative (placebo) bar | Survivors |
|---|---|---|---:|---|---|---:|
| 1 | Perp funding-settlement-window micro-dynamics (Binance USD-M, 50 perps, 5m bars, 8h stamps at 00/08/16 UTC): pre-stamp drift, funding-sign-flip reaction, OI unwind, pre-settlement squeeze, stamp-bar cross-section | `INVENT_0825_fundwindow.md` | 28 | 2.58 (SR) | **3.20 (SR, calendar placebo)** / 2.00 (SR, signal permutation p95) | 0 |
| 2 | Intraday equity open-drive / close-drive microstructure (opening auction print, gap-vs-auction, first-hour path efficiency, opening-print dislocation) | `INVENT_0825_opendrive.md` | 26 | 1.28 (SR) | **1.44 (SR, block-bootstrap best-of-26 p95)** / 1.72 p99 | 0 |
| | **TOTAL** | | **54** | | | **0** |

Both themes are event/calendar-clocked and both were run on **pre-existing caches — no network**: `orphanflush_cache/raw/{klines5m,metrics}` + the survivorship-complete `t23_cache` funding panel for theme 1; `im0823_cache/cube.npz` + `auc0822_cache/panel.npz` for theme 2. Every fill is at the open/VWAP of a bar **after** the last bar the signal reads; same-bar fills were used nowhere.

---

## 2. The pooled correction

Each theme corrected for its own N. Corrected over the **total 54**, both candidates move further under water.

**Pooled analytic expected-max** = √(2 ln 54) = **2.825** (in the Sharpe units of each theme's own window). Rescaling each theme's own size-matched placebo bar to N=54 by √(ln 54 / ln N):

| Theme | Own operative bar | Rescaled to N=54 | Best candidate (design gross) | Clears pooled? | Verdict |
|---|---|---|---|---|---|
| fundwindow | 3.20 SR (calendar placebo) | **3.50 SR** | `E3_STAMPBAR_FADE_15` **+5.54** | yes on design | **DEAD** — fails its own calendar placebo OOS (placebo max **+4.28** > its own **+3.84**); OOS net at 5.5 bp/side **−28.09** |
| fundwindow (permutation branch) | 2.00 SR p95 | 2.19 SR | `C3_XS_POST_MAG_15` +3.32 (stamp-specific, z=+4.31 vs placebo) | yes on design | **DEAD** — collapses to **+0.70** OOS, under its own permutation p95 of 1.55 |
| opendrive | 1.44 SR (bootstrap p95) | **1.59 SR** | `PA_GAP_CD_FADE` **+2.36** | yes on design, above own p99 | **DEAD on net** — breakeven **0.90 bp/turnover** vs a measured **1.13 bp** liquid half-spread |

Two of 54 clear the pooled gross bar on design. **Neither clears the full conjunction** (gross > both nulls **AND** held-out net positive **AND** ρ1 gate **AND** executable off its own print). Nothing is promoted.

**ρ1 gate.** Theme 1 was gated before any gross claim: 5m open-to-open ρ1 mean **−0.020**, median −0.017, worst symbol −0.103 across 48 symbols — comfortably inside the −0.35 threshold, and every ρ1(pnl) in the family sits within ±0.12. Liquid perp 5m opens are **not** a bounce series, so nothing in theme 1 is a Clause-4 artifact: it died of the calendar placebo and of cost, not of bounce. Theme 2's headline object is the mirror image of the 0823 G1 tell that ρ1 catches — only **1.7%** of its gross sits in the first bar after entry (G1 had 152%) — but the theme's *rescuing rail* is bounce-contaminated: the closing-auction variant puts **75–87%** of the return in the ten minutes after a single-print entry, and `PB_DRIVEZ_FADE` puts **209%** of its hold in the 15:59-print-to-auction leg, the same close-auction bounce that killed auction-imbalance.

**Placebo/analytic ratio, measured twice more.** fundwindow: **1.24x** (3.20 calendar placebo vs 2.58 analytic) on 15–30 minute non-overlapping books; opendrive: **1.12x** (1.44 vs 1.28) on disjoint daily books. Both extend the standing rule — for disjoint books the analytic bar is roughly right to mildly optimistic; the 2x understatement shows up on multi-day overlapping holds. **But fundwindow's excess comes from a different source than holding overlap:** the calendar placebo is large because the *underlying* effect (generic 5m cross-sectional reversal) exists at every anchor, not because the books overlap. That is the round's main methodological result.

---

## 3. Why nothing survived: two clean, different deaths

### 3.1 fundwindow — killed by the **CALENDAR PLACEBO**, a null the standard gauntlet did not have

`E3_STAMPBAR_FADE_15` is a genuine object: fade the settlement bar's own body cross-sectionally across 50 perps, enter at the open of B+1, hold 15 minutes, dollar-neutral rank weights. Design gross **+5.54**; held-out gross **+3.84** with the design sign frozen, above the permutation p95 of 1.49. On the standard two-null gauntlet it passes.

It dies because the **identical 28 formulas re-anchored at +1h…+7h after each stamp — times that are not funding times — score a family max of 3.07/3.91/2.77/**4.58**/2.29/3.16/2.65 (mean **3.20**), and E3's own OOS placebo max of **+4.28 exceeds its own OOS +3.84**. It is generic 5-minute cross-sectional reversal wearing a calendar mask.

Four independent kills, three of them structural:
- **(a) Not a funding effect.** Above.
- **(b) The one genuinely stamp-specific design winner collapsed.** `C3_XS_POST_MAG_15`: +3.32 stamp vs +0.69 placebo mean in design (z = +4.31) → **+0.70** OOS, below its own permutation p95.
- **(c) The pre-stamp books are a funding SNIPE, not a price effect.** `C1_XS_PRE_MAG_30` design gross +2.10 but **price-only −0.45**; `A6_PRE_FADE_30_BIG` +1.15 gross, **price-only −0.55**. The raw −90m…+90m drift profile split by funding sign oscillates ±3 bp with no coherent shape. **There is no pre-settlement price squeeze.**
- **(d) The cost wall, exactly.** Largest breakeven anywhere in the family: **3.48 bp/side design, 1.67 bp/side OOS**, against Binance USD-M VIP0 of 4.5 bp taker / **2.0 bp maker**. The best member does not clear the **maker** fee with a free spread and zero adverse selection. Mean OOS gross is **0.93 bp per round trip** (max 3.35) against an 11 bp round trip — this needs **~10x the signal**, not 10% better execution.

**Theme test:** design→held-out rank correlation across all 28 formulas ρ = **+0.198** (t≈1.03, n=28). The design window does not tell you which funding-window formula works next.

### 3.2 opendrive — killed by the **EXECUTION COST WALL**, at 80% of its own floor

Three of the brief's four bullets were **already dead** (INVENT_0823_intramicro killed opening drive, close drive and first-hour range/ORB across 28 formulas *on gross*). The round was correctly pre-registered as a disjointness sweep on three instruments 0823 never touched — the official opening-auction print, first-hour path efficiency, opening-print dislocation — plus the one untested cell, gap-vs-opening-auction. **Only that cell had anything in it:** path efficiency best +0.43, opening-print dislocation best +0.60 (perm p=0.26), vol-scaled drive best +0.58.

`PA_GAP_CD_FADE` (cross-sectional fade of the overnight gap z-score across 34 mega-caps; signal fully known at 09:30, entry at 15:35–15:40 VWAP, exit at 15:55–16:00 VWAP, flat at every close so borrow is exactly zero) is the **strongest gross object this programme has invented that still failed**:

- Gross **+2.36** design, above the best-of-26 block-bootstrap **p99** (+1.72) → family-wise p < 0.01
- **Replicates out of sample:** gross **+2.09**, and gross bp/day *rises* 1.44 → 1.81
- ADV-decile signal permutation on **gross** (not net, not rotate-the-returns): p = **0.0020**
- One-bar-gap fill **+2.46 ≥ primary** — no fill artefact
- Net@0.5bp **+0.59**; **net@1.0bp (headline) −0.57**. Breakeven **0.90 bp/turnover** vs a repo-measured **1.13 bp** liquid half-spread = **80% of its own execution floor.** Gate 4 fails. Not promoted.

Three independent kills:
1. **The rescuing rail can only be priced where the signal is absent.** Closing-auction exit (0 bp spread) gives gross +2.60/+1.23/+1.45 across pre-sample/design/held-out — positive over 11 years — but net@1bp +0.10/−1.57/−0.58, and the only positive window is the **oldest** (wider spreads = wrong direction). And that table is an upper bound anyway: 75–87% of the return lands in the ten minutes after a single-print entry.
2. **Survivorship-free breadth version is zero.** Point-in-time top-500 gap fade: +0.28 (2016–20) / +0.85 (design) / **−0.02** (held out).
3. **The mechanism claim fails OOS.** The entry-slot profile (positive at all 10 slots) was the best argument for mechanism-over-slot, so it was tested: same score entered at 10:00 = +1.47 design, **−0.47** held out. Sign flip across windows = noise.

---

## 4. What this round actually contributes

### 4.1 NEW STANDARD NULL: the **CALENDAR PLACEBO** for every event-clocked theme
Re-anchor the *identical formula family* at times that are not the event. Here it produced **3.20** against an analytic **2.58** and a signal-permutation **2.00** — it was both the largest bar and **the only null that killed the design winner**. Signal permutation destroys the cross-section; the calendar placebo keeps the cross-section intact and asks the one question that matters: *is the effect at the event, or everywhere?* **Add it to the standard gauntlet for every event-clocked theme** (funding stamps, earnings, index rebalances, auctions, expiries, macro prints).

### 4.2 NEW BOOKKEEPING RULE: in a dollar-neutral sweep, **"market-adjusted X" and "X" are the same formula**
Cross-sectional demeaning makes the subtraction a no-op. `PB_IDIOGAP_FADE ≡ PB_GAPZ_FADE`; `PB_DRIVE_EXMKT_FADE ≡ PB_DRIVEZ_FADE`. The 26 pre-registered books are **24 distinct books**. Pre-registering both halves of such a pair inflates apparent search breadth without inflating the bar — a small, silent way to cheat yourself. Dedupe before counting N.

### 4.3 A sharper statement of the free-data convexity wall
Both deaths are *the same wall seen from two sides*. fundwindow needs **10x** the signal (0.93 bp gross per round trip vs 11 bp cost) — hopeless, not marginal. opendrive needs **1.25x** — it is **18–20% short**, the closest anything invented here has come without clearing it, and it got *stronger* out of sample. That is the cleanest observation of the wall to date: **the structure is real and the spread eats it.** It is an execution/data wall, not an absence of structure.

### 4.4 Two keepers for the record (logged-only, protocol-ineligible)
- **The settlement instant is a mild cross-sectional reversal amplifier.** The stamp-bar fade runs ~1.5 SR hotter at the stamp than at non-funding anchors, consistently in both windows. Real, tiny, already inside the generic 5m-reversal family.
- **Full 8h funding is collectable in a 30-minute hold, and the cross-sectional version is stamp-specific OOS.** `C1_XS_PRE_MAG_30`: held-out gross **+3.04** with a calendar placebo of −0.14 (max 1.26) — unambiguously stamp-specific. But design gross +2.10 was below the 3.20 bar so it **never earned the holdout**; its edge is the funding payment, not price; and mean |funding| is **1.21 bp** (median 1.00, p90 1.97, p99 6.98) against an 11 bp round trip — uneconomic by ~9x. **This is an execution-timing overlay for a position you already hold, not a strategy.**

---

## 5. Dead-ledger additions

**Perp funding-settlement window (whole theme, 28 formulas):** pre-settlement positioning drift (A), post-settlement funding-sign reaction (B), cross-sectional funding-magnitude books around the stamp (C), funding-sign-flip reactions (D), settlement-bar cross-sectional reversal (E — = generic 5m reversal in a calendar mask), OI unwind/build around settlement (F), pre-stamp taker-flow / run-up / volume-spike fades (G). **Do not re-propose "funding window" in any form.**

**Intraday equity open/close microstructure (whole area, now 54 formulas across 0823 + 0825):** first-hour path efficiency / choppiness, opening-print dislocation, vol-scaled open drive, and gap-vs-opening-auction. Combined with 0823's kills of opening drive, close drive and ORB, **free-bar intraday equity microstructure is CLOSED.** Re-open only if the execution assumption itself changes: measured price improvement on mega-cap marketable orders, a midpoint rail, or paid data. `PA_GAP_CD_FADE` is the correct first object to re-test on that day, and only on that day.

**Also confirmed dead as claims, not as objects:** the "pre-settlement squeeze" narrative (no coherent drift profile exists) and the "mechanism-not-slot" defence of any single-slot intraday book (test it at another slot — it sign-flipped here).

---

## 6. Basket

**Nothing proposed. Nothing added. Forward clock LOCKED and untouched.**

`E3_STAMPBAR_FADE_15` is logged as **calendar-placebo-dead**. `PA_GAP_CD_FADE` is logged as **GROSS-REAL / NET-DEAD** — not a proposal leg. `C1_XS_PRE_MAG_30` is logged as an **execution-timing overlay**, not a leg. Diversification-vs-BASKET1 was not assessed for any of them because none earned the question.

---

## 7. Discipline / disclosure

- **fundwindow:** design 2023-01-01…2024-12-31; held out 2025-01-01…2026-07-31, scored only after the design freeze (sha256 verified, `freeze_ok=true`). 184,377 events / 3,922 stamps, hours exactly {0,8,16} UTC; 8h-interval prints only (184,475 of 192,718). Universe = top 50 by **2022** hourly quote volume — entirely pre-design; delisted names kept and allowed to go NaN (MATIC 47% coverage, FTM 58%, APE 69%). Funding P&L charged whenever a position is open across a stamp. Cost 5.5 bp/side (4.5 bp VIP0 taker + 1.0 bp declared half-spread). Nulls: 300 permutation draws x 28 formulas, weights reassigned across symbols trading at the **same stamp** (ADV-slot analogue; per-stamp net exposure and gross size preserved exactly).
- **opendrive:** pre-registration committed at `1f3f6a9` **before any design number**; shortlist at `56129f7` **before the held-out read**. Design 2021-01-04…2024-12-31 (1005 sessions); held out 2025-01-02…2026-08-14 (405); Panel-B pre-sample 2016-01-04…2020-12-31 (1259, declared in advance, can only kill). Nulls: stationary block bootstrap (block 5 sessions, 2000 resamples, **same day indices across configs**) + ADV-decile signal permutation, 500 draws, on **gross**. Self-test: planted edge +41.01 mirroring to −41.01; random +0.58; planted one-bar artefact +0.75 collapsing to −0.98 under the gap fill. **Contamination disclosed:** 0823 read the 2025-26 window for 4 named configs, none among these 26. **Truncation disclosed:** permutation ran on the top 8 by design gross; the other 18 have gross ≤ +0.58 against a +1.44 bar, so no p-value could change a verdict. Zero of 26 are net-positive at the headline 1.0 bp rung on design (best −0.26).
- **No network in either theme.** All data from pre-existing gitignored caches.

## 8. Files

- `research/trading_bot/INVENT_0825_fundwindow.{md,json}`, `_DESIGN.json`, `_DESIGN.sha256`, `_HOLDOUT.json`; code `scripts/trading_bot/f0825_{panel,lib,formulas,design,holdout}.py`; data `research/data/fund0825_cache/` (gitignored).
- `research/trading_bot/INVENT_0825_opendrive.{md,json}`, `_PREREGISTRATION.md`, `_SHORTLIST.md`, `_design.json`, `_null.json`, `_heldout.json`, `_presample.json`, `_DIAG.json`, `_AUCTIONRAIL.json`, `_selftest.json`; code `scripts/trading_bot/od0825_{sweep,diag,auction_rail}.py`.
- This file: `research/trading_bot/INVENT_0825_MASTER.md` (+ `.json`).

## 9. Recommendation

1. **Adopt the calendar placebo** as a required null for event-clocked themes; adopt the **dedupe-before-counting-N** rule for dollar-neutral sweeps.
2. **Close free-bar intraday equity microstructure** and **close the perp funding window.** Both are now over-tested relative to what free bars can price.
3. The programme has now produced, twice in one day, objects that are **statistically real on gross and dead on the spread**. The next marginal unit of effort belongs on the **execution/data side** — measured price improvement, a midpoint rail, or paid data — not on inventing formula number 55. `PA_GAP_CD_FADE` at 80% of its floor is the concrete test case that would settle it.
