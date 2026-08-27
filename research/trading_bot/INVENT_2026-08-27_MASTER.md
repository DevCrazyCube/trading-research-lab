# INVENT 2026-08-27 — MASTER SYNTHESIS (daily invention)

**Date:** 2026-08-27
**Theme:** Three independent microstructure angles run in parallel, each with a held-out split and cost-net scoring:
- **A — Deeper perp OI:** regional session-of-day leverage rotation (`oi_asia/eu/us`), fresh-leverage direction (`add_up/add_dn`), and liquidation asymmetry, cross-sectional dollar-neutral rank book on 333 Binance USD-M perps, daily close-to-close.
- **B — Overnight-vs-intraday component persistence** (Lou–Polk–Skouras clientele tug-of-war) on the free XLL US equity daily panel, single-name dollar-neutral rank books.
- **C — Intraday realized-variance SIGNATURE** cross-section (back/front-loaded, U-curve, jump-share, late-dv concentration → overnight reversal) on the 5-min im0823 cube.

**Data (all cached, no network):** `research/data/oi0824_cache/sym/*.npz` (333 perps, 2177-day union axis), `research/data/xll_cache/eq_daily_panel.npz` (3812 names × 2669 days, 2016–2026), `research/data/im0823_cache/cube.npz` (1410 days × 78 bars × 132 names, 2021–2026).

**Verdict: HONEST ZERO. 0 survivors. 0 basket proposals.**
Zero candidates were fed to the pooled bar (all three angles self-reported honest zeros at their own single-angle stage). Applying the whole-round pooled bar only widens the margin of failure.

**Basket action: NONE.** No leg added, no weight changed, no re-freeze. Forward clock untouched.

---

## 1. The multiple-testing bar for the WHOLE round

Three angles × 9 formulas each = **N_total = 27** formulas tried today. The honest bar is the expected max of N noise draws, **√(2 ln N)** in t-units:

| Bar | N | √(2 ln N) |
|---|---:|---:|
| Single formula (1-sided) | 1 | 1.00 (i.e. use ~2 for two-sided 5%) |
| One angle's family | 9 | **2.096** |
| Two angles pooled | 18 | 2.404 |
| **Whole round (pooled)** | **27** | **2.567** |
| **Whole round, sign picked on design** | **54** | **2.824** |

The operative pooled bar for today is **t ≈ 2.57** (√(2 ln 27)). Because every angle *chose the sign of its book on the design window*, the honest bar is really the two-sided **√(2 ln 2N) = √(2 ln 54) = 2.82**. A formula is REAL today only if it **clearly beats ~2.57–2.82 in design AND stays held-out-positive net of realistic costs.** Nothing in the round does either half of that jointly, let alone both.

Note that the pooled bar is *stricter* than each angle's self-reported 2.096 bar — so any formula that already failed its own angle's bar (all 27 did, on the joint design-and-held-out criterion) fails the pooled bar a fortiori. Pooling cannot rescue a candidate; it can only kill borderline ones. There were no borderline survivors to kill.

---

## 2. Angle A — Deeper perp OI leverage/liquidation cross-section — HONEST ZERO

**Object:** cross-sectional rank-demeaned dollar-neutral book on 333 Binance USD-M perps, gross = 1, cost **3.5 bp/side** on |Δw| turnover. Fields: `add_up/add_dn` (fresh-leverage direction), `oi_asia/eu/us` (session partition), `liq_long/liq_short`, `net`, `churn`, `glsr`, `cov_po`, `maxbuild/maxdrop`, `oiv_mean`, `p_last`. **Design = first 62% / held-out = last 38%** (untouched). Two liquidity screens: >$2M and the tradeable >$20M avg-OI (~107 real names). Sign chosen on design only.

**9 formulas:** F1_add_imbalance, F2_us_short_squeeze, F3_us_vs_asia_build, F4_liq_asym, F5_glsr_fade, F6_covpo_fade, F7_oi_price_diverge, F8_build_drop_fade, F9_ens_F1F3F4.

**Result: no formula clears the angle's 2.096 bar in design while staying held-out-positive net of costs in the liquid universe.**

- **F3_us_vs_asia_build & F9_ensemble** look strong in design (t≈2.3) but **flip NEGATIVE held-out** (>$20M: F3 HELD t = **−2.12**, F9 HELD t = **−0.61**). Overfit. Their loose-universe apparent strength came from tiny memecoins (reversal / bad-print artifacts).
- **F5_glsr_fade** is the only *consistently* positive signal (>$20M DES 1.73 / HELD 2.02; >$2M DES 1.98 / HELD 2.58, low turnover 0.24) — but **design t (1.73–1.98) is below even the 1-sided angle bar (2.10)**, so it does NOT clearly beat noise, and GLSR-residual is on the scout's heavily-covered/avoid list. See §5 for why its held-out 2.58 is not a survivor.
- **F7_oi_price_diverge** = DES 0.34 / HELD 0.16 (noise); quintiles non-monotonic; jackknife dropping the 5 top coins flips held-out to t = −0.77.

**METHOD BUG CAUGHT (load-bearing, logged so it is not repeated).** An initial pass selected sign by multiplying the **net** PnL series by −1. That is wrong for a costed strategy: −(gp − cost) = (−gp) + cost **adds trading costs back as profit**, manufacturing phantom survivors (F3/F7/F9 "held-out t = 2.5–4.0"). The correct procedure re-books the *negated signal* so cost stays a subtraction in both orientations; **every phantom survivor vanished.** The session partition and fresh-direction imbalances carry **no tradeable cross-sectional edge net of 3.5 bp/side** on this ~198-day sample. **Angle A is noise.**

Scripts: `…/scratchpad/perp_final.py` (correct), `…/scratchpad/perp_test2.py` (buggy sign-flip, kept for the record).

---

## 3. Angle B — Overnight-vs-intraday component persistence — HONEST ZERO

**Object:** decompose daily return into overnight (prevclose→open) and intraday (open→close); cross-sectional dollar-neutral rank books on persistence/reversal of each component. **Design 2016-01..2021-12 (1511 d), held-out 2022-01..2026-08 (1158 d)** untouched. Universe: price>5, top-1000 by trailing-20d dollar volume. Costs 5 bp/side; overnight-only and intraday-only legs force full daily liquidation = **~10 bp/day round-trip**; close-to-close leg uses turnover-based cost. ON component required hard ±0.5 clipping (raw ON std ~30% from bad open prints/splits).

**Result: all 9 formulas NEGATIVE net of costs in BOTH design and held-out.**

Net t-stats (design / held-out):
- F1 ON-persistence→overnight −4.22 / −4.90 (−8.5 bp/d)
- F2 ID-persistence→intraday −6.59 / −5.64
- F3 tug(ON−ID)→overnight −8.44 / −5.59
- F4 −ON3 reversal −7.67 / −4.76
- F5 −ID20→overnight −9.00 / −5.79
- F6 ON-persist carried close-to-close (low turnover) −1.14 / +0.07 (~0 bp, still fails)
- F7 ON information-ratio −8.73 / −9.15
- F8 ON sign-persistence −13.36 / −9.68
- F9 −ID3 intraday reversal −5.18 / −2.37

**Why it dies, honestly:** the tug-of-war IS weakly present GROSS — the overnight-persistence family is correctly signed and positive pre-cost (F1 des t=2.12/ho 0.89; F3 2.55/1.55; F7 2.46/1.11; F8 3.77/1.56). But (a) gross edge is only ~2–3 bp/day and decays to t≈1 held-out — **F8 is the only member to clear the 2.096 bar in design and it collapses to 1.56 OOS**; (b) the edge lives **entirely** in the overnight-only (or intraday-only) leg, which requires flattening every session = ~10 bp/day round-trip — 3–4× the gross spread. The one low-turnover formulation (F6, hold close-to-close) has ~zero gross edge because carrying through the intraday leg cancels the overnight gain (the two clienteles offset within the same name). **No cheap-to-trade version exists.** Cost-wall death identical in character to the perp funding-window and open/close-drive sweeps. **Angle B exhausted for the free daily panel.**

---

## 4. Angle C — Intraday RV-signature → overnight reversal — HONEST ZERO

**Object:** RV-shape cube (5-min bars), 9 dollar-neutral cross-sectional rank/demean books, entry-at-close / exit-next-open (overnight, the angle) plus a next-intraday alt-exit control. **Design = first 900 days (~2021-01..2024-06), held-out = days 900..1409 (~2024-07..2026-08)** untouched. Costs primary 5 bp/side, sensitivity 1.5 bp/side. Three universes: ALL 132, SINGLE 34 mega-caps, NOLEV 119 (drop leveraged/inverse ETFs).

**9 formulas:** F1 backload-fade, F2 pure last-hour reversal (control), F3 jump-share fade, F4 RV-expansion fade, F5 late-dv-concentration fade, F6 backload-weighted intraday reversal (smile), F7 abnormal-backload-alone, F8 front-loaded continuation, F9 plain intraday reversal (baseline).

**Result: honest zero.**
1. The scout's mean-reversion hypothesis is **wrong-signed** — back-loaded/stretched names mildly **continue** overnight, not revert.
2. The gross effect is real but tiny: best continuation gross held-out Sharpe ~0.3–1.0 and **unstable** (≈half the gross held-out Sharpes are negative across universes/exits).
3. Overnight-only holding forces a full round trip every day (enter close + exit open = 2 sides). At 5 bp/side (10 bp/day) the cost exceeds the gross edge in **either** direction — **every formula loses net in the design window itself** (all design net t negative, both signs).
4. The only positive held-out NET numbers (F8_frontcont next-intraday-exit +0.59t; F4_rvexpand SINGLE overnight +0.84t; F8 SINGLE next-intraday +0.24t) appear only at an optimistic 1.5 bp/side AND only on the off-angle next-intraday exit, all **t<1** — below the single-formula bar and far below the multiplicity-inflated bar (~3.1 for 3 universes × 2 exits × 2 directions).

Also confirmed leveraged/inverse ETFs mechanically inflate raw back-load t-stats (NOLEV/SINGLE weaker than ALL) — part of the apparent signal is an artifact. **Angle refuted: RV-signature is a genuine micro-effect fully consumed by the overnight round-trip toll.**

Scripts: `…/scratchpad/rvsig.py`, `…/scratchpad/flip.py`.

---

## 5. Does ANY candidate clear the POOLED bar AND stay held-out-positive net of costs?

**No.** Walk the closest three:

| Closest candidate | Design t | Held-out t | Net of cost? | Clears pooled 2.57? | Why not a survivor |
|---|---:|---:|---|---|---|
| **A · F5_glsr_fade** (>$2M) | 1.98 | 2.58 | yes (turnover 0.24) | held-out ~clips it, **design 1.98 does not** | Design t below even the 1-sided single-angle bar (2.10). A survivor must clear the bar **in design** (the held-out is a confirmation, not the selection window) — you cannot promote on an out-of-sample t while the in-sample t says noise. Also on the scout's GLSR-residual avoid list, and it weakens to DES 1.73/HELD 2.02 in the *tradeable* >$20M universe. |
| **B · F8** ON sign-persistence | 3.77 (GROSS) | 1.56 (GROSS) | **negative net** | n/a | Only clears in design **gross**; net of the ~10 bp/day overnight round-trip it is −13.4 / −9.7. Untradeable. |
| **C · F4_rvexpand** SINGLE | negative net | +0.84 (1.5 bp only) | only at optimistic 1.5 bp, off-angle exit | no | t<1, off-angle exit, sign unstable. |

The single most seductive number in the round is **A·F5's held-out t=2.58**, which nominally grazes the pooled bar (2.57). It is **not** a survivor:
- Its **design** t is 1.98 — below the single-angle bar and far below the pooled bar. Selection happens on design; you don't get to promote a formula whose in-sample evidence is noise just because its held-out slice printed high. That is the multiple-testing trap the whole exercise exists to avoid.
- It shrinks to DES 1.73 / HELD 2.02 in the only genuinely tradeable universe (>$20M avg-OI).
- GLSR-residual is on the heavily-covered avoid list — the prior is that this is a known, crowded factor, not a fresh edge.

Net: **no candidate clears the pooled bar in design while staying held-out-positive net of realistic costs.**

---

## 6. SURVIVORS

**[] — HONEST ZERO.** All three angles are honest zeros. Nothing is promoted, no basket leg proposed, forward clock untouched.

---

## 7. Basket proposal

**NONE.** There is no candidate that clears the pooled √(2 ln 27) = 2.57 bar in design and is held-out-positive net of costs, so there is no leg to propose and no guard to write. The honest outcome is a full zero for the 2026-08-27 round.

---

## 8. Dead-ledger additions (do not re-propose)

- **Perp OI session-of-day / fresh-leverage-direction / liquidation-asymmetry cross-section** (Angle A, F1–F9). Session partition (`oi_asia/eu/us`) and `add_up−add_dn` fresh-direction imbalances carry **no tradeable cross-sectional edge net of 3.5 bp/side** on ~198 days of 333 Binance USD-M perps. Design-strong members (F3/F9) sign-flip held-out; apparent loose-universe strength is a tiny-memecoin artifact. **DEAD.**
- **GLSR-residual fade** (A·F5). Consistently mildly positive but **design t 1.73–1.98 never clears the bar**, weakest in the tradeable universe, and on the crowded/avoid list. Not a fresh edge. **DEAD as a standalone leg.**
- **Overnight-vs-intraday component persistence (Lou–Polk–Skouras tug-of-war) on the free daily panel** (Angle B, F1–F9). Micro-signal is weakly present GROSS (~2–3 bp/day, decays to t≈1 OOS) but lives entirely in the single-session leg → ~10 bp/day round-trip kills it; the low-turnover carry version has ~zero gross edge (clienteles offset within-name). **No cheap-to-trade version. DEAD.** (Consistent with prior: T3 overnight reversal survives only as a market/portfolio leg, not single-name component persistence.)
- **Intraday RV-signature → overnight reversal** (Angle C, F1–F9). Hypothesis is wrong-signed (mild continuation, not reversal); gross effect tiny and unstable; overnight round-trip toll exceeds the edge in either direction so **every formula loses net in design**; leveraged/inverse ETFs inflate the raw t-stats mechanically. **DEAD.**
- **Method note for the ledger (repeat of A's catch):** never pick a costed strategy's sign by negating the **net** PnL series — −(gp−cost) adds cost back as profit and manufactures phantom held-out survivors. Always re-book the *negated signal* so cost stays a subtraction in both orientations.

---

## 9. Discipline / disclosure

- **Splits:** A design 62%/held-out 38% (untouched); B design 2016–2021 / held-out 2022–2026 (untouched); C design first 900 d / held-out 900–1409 (untouched). Sign chosen on design only in all three.
- **Pooled correction:** whole-round bar = expected max of N_total = 27 via √(2 ln N) = **2.567**; sign-selection-aware **√(2 ln 54) = 2.824**. Stricter than each angle's self-reported 2.096 bar.
- **Net of cost:** A 3.5 bp/side on turnover; B 5 bp/side (single-session legs ~10 bp/day round-trip); C 5 bp/side primary, 1.5 bp/side sensitivity.
- **Point-in-time entry:** A next-day entry on daily close-to-close; B/C entry at close, single-session legs flatten at the next open. No same-bar/look-ahead fills.
- **No network.** All reads from pre-existing gitignored caches (`oi0824_cache`, `xll_cache`, `im0823_cache`).
- **Research only.** No orders, no money, no git-commit forced by this round.

## 10. Files

- This file: `research/trading_bot/INVENT_2026-08-27_MASTER.md`
- Data (gitignored): `research/data/oi0824_cache/sym/*.npz`, `research/data/xll_cache/eq_daily_panel.npz`, `research/data/im0823_cache/cube.npz`
- Scratch code: `…/scratchpad/{perp_final.py, perp_test2.py, rvsig.py, flip.py}`
