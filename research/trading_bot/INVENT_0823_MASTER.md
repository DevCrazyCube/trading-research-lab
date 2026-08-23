# INVENT_0823 — MASTER SYNTHESIS (2026-08-23)

Three genuinely different angles, **102 pre-registered formula-cells**, pooled correction over the total.

| # | Theme | N cells | Verdict |
|---|---|---|---|
| 1 | Single-name & sector dealer-gamma / options flow (free expired-OPRA bars) | 48 | **1 survivor** |
| 2 | Intraday microstructure beyond the auction (5-min SIP cube + PIT top-500 minute panel) | 28 | noise |
| 3 | Intra-group sympathy / same-tight-group lead-lag | 26 | noise |

> **HEADLINE: 2 of 3 themes are honest zeros. One survivor — `S6_SKEW_TILT|day`, an options
> order-flow imbalance book on 49 liquid single names — clears the POOLED 102-formula bar on both
> nulls (design t 4.53 vs pooled size-matched 3.69; family-wise permutation p ≈ 0.0021 after pooling)
> and is held-out net POSITIVE at every realistic rail (+2.92 Sharpe at 3.0 bp/side, break-even
> 16.1 bp/side, 6× headroom). It is a PROPOSAL ONLY. Basket stays frozen at v9 (four legs: T3,
> DUALCLASS, T12 CEF, ORB). S6 goes to the forward paper queue, size ZERO, with a named kill guard.**

This is the first survivor to clear a pooled bar since the v9 scrub. It is also the first one whose
own author says the mechanism is **mis-named** — see §4. Both facts are load-bearing.

---

## 1. The pooled null over all 102 cells

Exact best-of-N bar for iid two-sided |t| (not the sqrt(2 ln N) approximation, which understates):

| Bar over N = 102 | max abs t | notes |
|---|---|---|
| Analytic, exact p95 | **3.479** | sqrt(2 ln 102) approximation would say 3.041 — 13% too low |
| Analytic, exact p99 | 3.894 | |
| **Size-matched pooled placebo p95** | **3.691** | analytic × 1.061, the ratio measured this round |
| Size-matched pooled placebo p99 | 4.167 | |
| Ultra-conservative (programme-max ratio 1.14, overlapping books) | 3.966 | |

**How the pooled placebo was built.** No single cross-theme permutation is constructible — the three
panels share no instrument, no clock and no statistic (theme 1 is a daily cross-sectional rank book,
theme 2 is an intraday dollar-neutral book, theme 3 is an event book). Each theme ran its own
size-matched null; the pooled bar scales the *largest and most correlated* of them (theme 1's
ADV-slot signal permutation, 2000 draws, one permutation shared per (draw, day) so cross-formula
correlation is preserved) from N=48 up to N=102 by the exact analytic ratio 3.479/3.272 = 1.063.

| Theme | N | own analytic p95 | own size-matched placebo p95 | best design stat |
|---|---|---|---|---|
| 1 gamma / option flow | 48 | 3.272 (t) | 3.471 (t) / 3.127 Sharpe (dense cells) | **t 4.53, SR 3.83** |
| 2 intraday micro | 28 | 3.116 (t) → 1.29 SR | 1.41 SR (block bootstrap, 2000) | SR **+0.21** net, +1.34 gross |
| 3 sympathy | 26 | 3.095 (t) → 1.278 SR | 0.904 SR (day-shift) / 0.835 (sign-flip) | SR **+0.72** gross |

Themes 2 and 3 do not reach even their own per-theme bar, so the pooled bar never binds on them.
It binds only on theme 1, and theme 1's survivor clears it.

**Fourth measurement of the placebo/analytic ratio.** 1.08× (disjoint auction book, 0822B), ~2×
(overlapping weekly CEF pair book, 0822), 1.14× (disjoint event book, 0822C), 0.845× (CEF fund-identity
permutation), and now **1.061×** (ADV-slot signal permutation on a 1-day-hold cross-sectional book).
The standing conclusion holds: the inflation lives in **holding overlap**, not in multiplicity as such.
A one-session hold barely inflates. Keep measuring per book.

**Sharpe-unit pooled bar, and the one place the survivor does NOT clear.** Scaling theme 1's Sharpe
nulls to N=102: dense-cell like-for-like p95 **3.325**, p99 3.749 — survivor design Sharpe 3.83 clears
both. The *all-cell* Sharpe null scales to p95 **4.286**, which the survivor does **not** clear.
That null is inflated by four n=77 OpEx cells whose Sharpe has a much fatter null than a n≈350 cell's;
comparing an n=350 Sharpe to a bar set by n=77 cells is not like-for-like. **The t-statistic
comparison is the correct one** (t is already n-normalised) and the survivor clears it at 4.53 vs 3.691.
Both numbers are stated here because a reader who saw only the all-cell Sharpe null would conclude
the opposite.

---

## 2. The one survivor

### S6_SKEW_TILT|day — options order-flow imbalance, liquid US single names

**Number.**

| | design | held out (2025-07-01..2026-08-21, n=260, untouched) |
|---|---|---|
| Gross Sharpe | 3.83 | **3.58** (t 3.64, +7.90 bp/day) |
| t | **4.53** | 3.64 |
| Net @ 1.0 / 3.0 / 5.5 bp per side | — | **+3.36 / +2.92 / +2.36** |
| Turnover | 0.49/day | 0.49/day |
| Break-even | — | **16.1 bp/side** (6× the 3 bp liquid-taker rail) |
| One-day-gap re-entry placebo | — | **+3.35** (not a bounce artefact) |
| ADV-slot permutation FWER p (48 cells) | **0.0010** (2/2000) | — |
| ADV-slot permutation FWER p, pooled to 102 | **≈0.0021** | — |

**Formula.** Gamma-weighted OTM call-vs-put open-interest tilt,
`(Σ_{K>S} γ_K·callOI_K − Σ_{K<S} γ_K·putOI_K) / Σ_all γ_K·OI_K`, from cumulative per-strike option
volume on the front and next monthly expiry through the close of day *t*. Cross-sectionally
rank-normalised over 49 liquid names, dollar-neutral, long top / short bottom. **Entered at the OPEN
of t+1, exited at the OPEN of t+2.**

**Shared-print check: clean.** Signal is read at the close of *t*; the fill is the open of *t+1*,
a ≥17.5-hour gap. Signal and fill can never share a print. This is the failure mode that killed
ETF-sibling RV (15:45 shared-price bounce) and the entire theme-2/theme-3 catch-up family, and this
book is structurally immune to it.

**ρ1 gate: not applicable, and the substitute passed.** S6 is not a spread trade — it is a
cross-sectional rank book on liquid single names held overnight-to-overnight, so there is no
Δspread series to autocorrelate. The pre-registered substitute is the **one-day-gap re-entry
placebo**, which is the stronger test for this book shape, and S6 scores **+3.35** against a primary
+3.58 (a bounce artefact collapses; this does not). The gate has teeth: `G4_DGEX1|day` cleared the
analytic bar at t 3.32 and was **killed** by exactly this placebo, +3.08 → −0.23.

**Exposure work, all out of sample.** Beta to equal-weight universe 0.036; beta-hedged 3.42.
Residualised on r1/r5/r20 → 4.03; on MA20/MA60 distance → 3.44; on pin-distance → 3.76. Spanning
regression against IV-book, RV-book, REV1, REV5 and market: **alpha +7.84 bp/day at t +3.61**,
residual Sharpe 3.65, IV and RV loadings statistically zero. Worst leave-one-name-out of 49
deletions: 3.09. Every equal-weight tail cut (10/20/33/50%) positive. Positive-day rate 0.596;
worst cumulative-gross drawdown 606 bp.

### Does it diversify the four sized legs? YES, structurally.

| Sized leg | Instrument | Clock | Statistic | Overlap with S6 |
|---|---|---|---|---|
| T3 overnight reversal | US equities | close → open | own past return | none — S6 residualises to 4.03 on r1/r5/r20 |
| DUALCLASS (gap-1, no BRK) | share-class pairs | gap | intra-issuer price spread | none — disjoint universe shape |
| **T12 CEF discount** (anchor, held-out net SR 2.73 t 4.10) | closed-end funds | weekly | NAV discount | none — no CEF is optionable in this universe |
| ORB | US equities | intraday range | opening range | none — S6 holds open-to-open, no intraday leg |

**None of the four reads an option feed.** S6's only input is expired-OPRA per-strike volume, a data
source no existing leg touches. Its market beta is 0.036 and its momentum/mean-reversion residual
Sharpe is *higher* than its raw Sharpe. This is the cleanest diversification case any candidate has
presented since T12.

### Freeze recommendation: **NO. Queue, do not size.**

Basket is frozen at v9 pending forward accrual, and S6 does not get an exception. Three reasons
beyond the freeze:

1. **Only 260 held-out sessions.** Free expired OPRA starts 2024-02-01 — 2.5 years total. Every
   other sized leg was frozen on multi-year held-out evidence.
2. **The mechanism is mis-named** (§4). A candidate whose stated causal story is wrong is a
   candidate whose out-of-sample decay is unbounded, even when the statistic is sound.
3. **Standing programme prior:** selection-inflated estimates are upper bounds. Held-out +2.92 net
   is the ceiling, not the expectation.

### Guard (pre-register these NOW, before any forward log starts)

- **Forward paper log, size ZERO, minimum 60 sessions** before the promotion question is reopened.
- **Kill if** forward *gross* Sharpe < 0 over any trailing 60 sessions, **or** net@3.0bp Sharpe
  < +1.0 over the full forward log, **or** the one-day-gap re-entry placebo drops below +2.0.
- **Kill if** the single-names-only sub-book decays below +1.5. The sector-ETF half is already dead
  (held-out 0.55, net −0.01) and must be excluded from the traded book from day one — do not
  re-include it "for breadth".
- **Data-continuity guard.** OPRA monthly expiries only; weeklies and 0DTE — now the majority of
  single-name option volume — are absent, and cumulative traded volume is an **OI proxy, not open
  interest**. Log a monthly coverage check; a feed change or an expiry-calendar shift voids the log
  rather than degrades it. (Memory: XS_GLSR_Z died exactly this way.)
- **Head-to-head against the crude variant.** Pre-register `(callVol − putVol)/(callVol + putVol)`
  — no greeks — as a competing forward book from the same start date. If the crude book matches or
  beats S6 forward, S6's Black-Scholes machinery is confirmed decorative and the crude book, not S6,
  is the promotion candidate.
- **Two strike-grid bugs were caught and fixed before any result existed** (a grid step that is not a
  divisor of the listed step silently drops most of the ladder). Any refetch must re-run the shipped
  fine-grid + coarse-grid union and diff the strike count against the cached panel.

---

## 3. The two honest zeros

### Theme 2 — Intraday microstructure beyond the auction: NOISE (28 cells)

**0/28 beat the best-of-28 block-bootstrap bar on NET (+1.41 p95) and 0/28 beat it on GROSS (+1.40).**
Best design gross in the whole sweep +1.34 (`F2_LD_REV`); best design net@1.0bp +0.21
(`E4_PDPOC_MAGNET`), which then **failed the pre-registered one-bar-gap gate on the design window
itself** (+0.21 → −0.03) and was never a candidate. Held-out shortlist all negative: E4 −0.57,
A5_DRIVE_EX_GAP −0.50, F2_LD_REV −0.61, G3_LD500_CONT_TOP150 −2.20.

**This is a harder negative than the Aug-20 intraday-RV sweep, and it retro-explains it.** The RV
sweep found a real replicable *gross* edge (+6.86 design / +5.41 held out, 50/98 beat the gross bar)
that failed only on friction. This round changed exactly two things — holding period from minutes to
hours, and a fill that never shares a print with the signal — and **the gross edge vanished
entirely**. The earlier gross number was made of the two things this round removed.

Mechanism, decomposed: `G1_LD500_CONT` looks like +0.55 gross; the 15:49→15:59 leg earns
+0.605 bp/day (152% of the total, SR +0.83) and the 15:59→close leg **loses** −0.207 bp/day at
SR −2.27. Not drift — a ten-minute continuation of the signal print that reverses into the close,
the same object that died on ρ1 in the auction-imbalance round.

**Deadest sub-family is the newest instrument.** Family B built close-location-value × volume order
flow, average-trade-size-vs-own-20d-norm, volume front-loading and trade-count acceleration from
5-min trade counts and highs/lows. Best gross +0.12, best break-even 0.10 bp. **Free 5-minute bars
carry no recoverable order-flow information about the rest of the session.**

**Reusable methodological finding, disclosed not buried:** an ADV-slot signal permutation run on a
**NET** series is mis-specified — a permuted book still pays full cost, so the null sits far below
zero and any non-negative-gross config "beats" it (E4 scored p=0.004 against a null p95 of −0.33).
Re-run on GROSS, four configs carry per-config p<0.01, which still does not make them real: those
p-values are uncorrected for the 28 draws that produced the ranking. Note also the permutation null's
**mean is positive** (+0.21..+0.55) — the score-magnitude profile alone, with the symbol mapping
destroyed, already earns something. **Run permutation nulls on GROSS. Always.**

### Theme 3 — Intra-group sympathy: NOISE, and it dies GROSS (26 cells)

**0/26 passed any of the four pre-registered design gates.** Design gross max +0.72, median +0.10;
net max +0.01, 1/26 positive. Bar used 1.278 (analytic); both size-matched placebos were *lower*
(day-shift 0.904, sign-flip 0.835).

**The friction floor is not the story.** At a literally zero half-spread (only the 0.15 bp/turnover
SEC+TAF pass-through), **18/26 are still net-negative** and the best is +0.42.

Mechanism, measured: (1) at a 3σ leader shock, peers already transmit **0.883** of their beta-implied
move *inside the same 5-min bar*, vs 0.986 on an average bar; (2) the missing 12% **never converges**
— the peer closes 0.36 bp of a 19.25 bp gap over the next hour (t 0.87), peak 0.54 bp at 40 min,
against a 3.46 bp round trip; (3) the pure direction trade earns +0.09 bp/day (t +0.10) design and
−0.59 bp/day (t −0.52) held out. **A sharp leader move is simply more idiosyncratic than its average
move, and the market prices that in real time.**

**New failure mode named: the bounce can live in the SIGNAL, not the spread.** ρ1(Δspread) on all 41
traded hedged spreads: min −0.153, median −0.028, **0 fail** the −0.35 gate. Yet the catch-up family's
gross decays +0.83 → +0.33 → −0.07 at entry lags 0/1/2. The deficit is measured off the peer's *own*
bar-b close, so a bid print manufactures a positive deficit that gets filled at the ask one print
later. **A clean ρ1 on the spread does not clear a book whose signal is built from a single own-print
close. Add the lag-decay test to the standard gate set.** Self-test confirms the harness would have
found a real effect: +16.3 Sharpe when a synthetic catch-up lands at b+2/b+3, +1.9 when it lands in
the forfeited bar b+1, −0.26 under a sign flip.

Near miss, one line: `C3b` (index heavyweight → QQQ, beta-hedged) is the only cell whose gross does
not decay with the fill (+0.57/+0.65/+0.58 at lags 0/1/2) and it persists out of sample (post-hoc:
+0.55 lag1, +0.95 lag2). Its net is −2.7 on both windows; it needs spreads 6× tighter than a 1 bp
floor. Real micro-effect, not a business. **Do not re-test this theme with a cheaper rail.**

---

## 4. The survivor's biggest caveat: the mechanism is mis-named

The Black–Scholes apparatus **contributes nothing**. A crude greeks-free
`(callVol − putVol)/(callVol + putVol)` imbalance does as well in design (SR 3.68) and **better out
of sample** (SR 4.32, net 4.15 at 3 bp). Two supporting facts point the same way:

- |net gamma| vs the **next** session's realised range has rank correlation **+0.094 / +0.035** —
  weakly *positive*. Long dealer gamma does **not** dampen next-day range.
- All four pin cells, all four flip cells, and all four charm/vanna cells are noise.

So the real finding is an **options ORDER-FLOW IMBALANCE predictor in liquid single names**, not a
dealer-gamma effect. The crude variant is post-hoc (built after both windows were read) and has no
clean holdout — it is a mechanism diagnostic and **must be pre-registered and tested forward**, which
is exactly what the guard in §2 requires.

### One apparent contradiction, reported in full

Cross-sectionally orthogonalising the **S6 signal** on implied vol + 20d realised vol cuts held-out
Sharpe 3.58 → 0.95. That strips the vol *ordering* out of the signal — S6 is legitimately +0.25 to
+0.29 correlated with vol because high-vol names carry more OTM call OI — rather than hedging the vol
*books*, and is the wrong exposure test. The spanning regression is the right one, and the IV/RV
loadings are statistically zero out of sample. **Both numbers are here because a reader who ran only
the first would conclude the opposite.** A forward reader should treat this as the single most likely
place S6 turns out to be a repackaged vol exposure.

### Ledger correction to Round 3

"The textbook GEX sign-flip is structurally degenerate" is true for **index** options at short tenor
**only**. Pooled over this universe, net dealer gamma is positive on 78.3% of name-days, but **32 of
49 names flip sign between 10% and 90% of the time** — IWM 0.15 and XLRE 0.17 (put-dominated) versus
AMZN 0.99, META 0.97, NVDA 0.96 (call-dominated). The cross-sectional dispersion SPY lacks **does**
exist in single names, which is why this theme was worth working.

---

## 5. Dead list — do not re-test

**Theme 1 (options):** gamma-flip level as support/resistance (F1–F4); max-gamma-strike pinning in
all four forms incl. OpEx-week and expiry-session windows (P1–P4); charm, vanna, post-OpEx roll-off,
pre-OpEx front-month gamma (C1–C4); GEX level / z-score / 1d and 5d change / gamma×reversal
interaction (G1–G6); put/call ratio level and its 1d and 5d shift (S1–S3); OTM call surge (S5).
**The entire sector/broad-ETF half of the theme is dead** — survivor's sector-only book is held-out
Sharpe 0.55 (net −0.01) vs 3.61 single-names-only. Note the direction: the dead pool is the *more*
liquid one, so this is not an illiquid-name artefact.

**Theme 2:** opening drive, bar-level order flow / trade size from free 5-min bars, VWAP deviation,
opening-range breakout beyond the existing ORB leg, volume-profile value area / POC magnet, late-day
drift. All six sub-families.

**Theme 3:** all twelve claims — leader→peer catch-up/fade, index-heavyweight→QQQ, group-consensus→
laggard, overnight-gap sympathy, leader last-30-min → peer next-morning gap, volume-shock sympathy,
ETF-leads-members direction, up/down asymmetry, cumulative-30-min leader move, post-shock intra-group
dispersion.

---

## 6. Basket state — UNCHANGED

BASKET v9 remains frozen at **four sized legs**: T3 (overnight reversal), DUALCLASS (gap-1, no BRK),
**T12 CEF discount** (anchor, held-out net Sharpe 2.73 / t 4.10), ORB.
Logging-only and not to be rebuilt on: ETF-sibling RV (15:45 shared-price bounce artefact, fails ρ1),
T7 ex-dividend (duplicated-dividend data bug, collapses to t 0.81 clean), CRYPTO_LOWVOL
(short-alt-borrow-walled published factor). XS_GLSR_Z is data-dead.

**Queue (size zero, forward paper only): S6_SKEW_TILT|day + its pre-registered crude-imbalance
competitor.** No promotion, no sizing, no orders.

---

## 7. Process ledger

| Theme | prereg commit | frozen shortlist/design | result |
|---|---|---|---|
| 1 gamma | `a86abe1` (before any backtest number existed) | `e8dd7a0` (design table + held-out sign, before the held-out window was read) | `914764e` |
| 2 intramicro | `01ef87c` | `0f13929` | `3980e86`, artifact `23cf3df` |
| 3 sympathy | prereg sha256 `2d284d0b7dd22f5b2c068cf8ec9ce7e523463ec09b1ef172a8f1941753db43aa`, hashed before any design number; engine refuses a second hash | shortlist on disk before holdout | `45e5bcc` |

Design/held-out splits: theme 1 held out 2025-07-01..2026-08-21 (260 sessions); theme 3 design
2021-01-04..2024-12-31 (1005), held out 2025-01-02..2026-08-14 (405); theme 2 carried a declared
2016–2020 pre-sample read only after the freeze.

## 8. Artefacts

- **Master:** `/home/anont/meme/research/trading_bot/INVENT_0823_MASTER.md`, `.json`
- **Theme 1:** `INVENT_0823_gamma.{md,json}`, `_PREREGISTRATION.md`, `_DESIGN_TABLE.md`,
  `_design.json`, `_heldout.json`, `_DIAG.json`, `_nulldraws.json`;
  `scripts/invent0823_gex_{fetch,panel,eval,diag}.py`; data `research/data/inv0823_gex/`
  (127 MB, regenerable in ~50 min)
- **Theme 2:** `INVENT_0823_intramicro.{md,json}` + `_PREREGISTRATION.md`, `_SHORTLIST.md`,
  `_selftest.json`, `_design.json`, `_null.json`, `_permgross.json`, `_heldout.json`,
  `_presample.json`, `_DIAG.json`; `scripts/trading_bot/im0823_{panel,sweep,selftest,diag,permgross}.py`;
  cube `research/data/im0823_cache/cube.npz`
- **Theme 3:** `INVENT_0823_sympathy.{md,json}` + `_SELFTEST/_DESIGN/_DIAG/_NULLS/_SHORTLIST/`
  `_HOLDOUT/_ADDENDUM/_TRANSMISSION/_DIRECTIONAL{,_CLUSTERED}.json`;
  `scripts/trading_bot/sympathy0823.py`, `sympathy0823_addendum.py`

---

## 9. Carry-forward rules earned this round

1. **Use the exact best-of-N bar, not sqrt(2 ln N).** At N=102 the approximation says 3.041 and the
   truth is 3.479 — a 13% under-statement, which is the difference between a survivor and a false
   positive.
2. **Run permutation nulls on GROSS.** A net-series permutation null is mis-specified: the permuted
   book pays full cost, the null sits below zero, and everything "wins".
3. **A clean ρ1 on the spread does not clear the book.** If the signal is built from a single own-print
   close, run the entry-lag decay test (lags 0/1/2). Theme 3's whole catch-up family passed ρ1 and
   died on lag decay.
4. **Placebo/analytic ratio tracks holding overlap, not multiplicity.** One-session hold → 1.06×;
   overlapping weekly book → ~2×. Fifth data point recorded.
5. **The dead pool being the *more* liquid one is evidence for, not against.** Theme 1's sector ETFs
   died while single names lived — the opposite of the illiquidity-artefact signature.
