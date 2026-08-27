# INVENT_0822B — AUCTION IMBALANCE AS A SIGNAL SOURCE

**Date:** 2026-08-22 (2nd rotation) · **Scope:** research only, cached free data, no orders, no
network calls. · **Pre-registration:** `INVENT_0822B_auction_PREREGISTRATION.md`
sha256 `1377e0f207ca1c5fd0c4bb33feae10b498e0ac15075e35bee082181c8e36d4e3`, written and hashed
before the first design-window statistic was computed.

**Artefacts:** `INVENT_0822B_auction.json` (54-cell sweep + nulls) ·
`INVENT_0822B_auction_DIAG.json` (interval decomposition, per-year, deciles, +1-session) ·
`INVENT_0822B_auction_RHO.json` (persistence/bounce anatomy) ·
`INVENT_0822B_auction_TICK.json` (post-hoc characterised object).
**Code:** `scripts/auc0822_prep.py`, `auc0822_engine.py`, `auc0822_diag.py`, `auc0822_rho.py`,
`auc0822_tick.py`. **Data:** already-cached T3 collection only; nothing was fetched.

---

## 0. THE ONE-PARAGRAPH ANSWER

**The theme is noise, and the measurement that kills it is a single number: the median
close-auction dislocation is 1.55 bp — exactly ONE TICK — and it has ρ1(level) = +0.056 with
ρ1(Δ) = −0.498.** Free SIP history does not publish the exchange imbalance feed; the only shadow
of imbalance it publishes is where the official print sits relative to the last continuous trade,
and that quantity is one penny of price grid with no day-to-day memory. Across **54
pre-registered formulas** the best design-window cell reaches gross **t = −4.04**, which clears
both the analytic bar (3.06) and the **size-matched placebo** (max|t| p95 = **3.31**, 0/300 draws
above 4.04) — and then posts held-out **t = −0.20** with net Sharpe **−0.30** on the M0 zero-spread
auction rail. Only **17 of 54** cells keep their sign from design to held-out, *below* the 27 a
coin would give. **Zero survivors, zero freezes.** One object *did* survive out of sample with
t = +26.6 — the cross-sectional persistence of the dislocation itself — and it is worth **1.23
bp/day against a first-party-measured 1.43 bp half-spread you must cross to reach it**: break-even
0.62 bp, i.e. it needs the market to be **2.3× tighter than it is**. That is the theme's real
finding and it is a wall, not an edge.

---

## 1. WHAT WAS ACTUALLY INVENTED, AND HOW IT IS DISTINCT FROM T3

Free data has no imbalance feed. So the theme reconstructs *revealed* imbalance from the prints
that are free (all logs, C/O = official auction prints, P29/P49/P59 = raw SIP 1-min closes):

| primitive | definition | reading |
|---|---|---|
| `d` | ln(C_t / P59_t) | **close-auction dislocation** — where the cross cleared vs the last free reference |
| `q` | ln(O_t / C_{t-1}) | **open-auction gap** |
| `e` | ln(P59_t / P49_t) | drift over the window in which the **imbalance feeds publish** (15:50→) |
| `f` | ln(P49_t / P29_t) | drift **before** imbalance publication |
| `x` | ln(C_t / O_t) | print-to-print day |
| `u` | ln(O_t / P59_{t-1}) | total off-hours |
| `ptc` | ΔlnC − ΔlnP59 | **MOO/MOC print vs continuous divergence** |

**T3 is a pressure signal on the rail (a 15:29→15:49 continuous return, entered MOC).** This theme
asks the opposite question: is the *auction itself* — its clearing dislocation, its gap, its
publication window — a signal source? Only `M01_f|ON_t` restates T3, and it is kept deliberately
as a **rig-validation control** (§5).

### The legality constraint, declared before running, and it is binding
The MOC/LOC cut-off is **15:50 ET**. Any signal containing `P59_t` or `C_t` therefore *cannot*
enter at `C_t`; it can only enter at `O_{t+1}`. Two disjoint blocks follow:

| block | entry | exits | predictors | cells |
|---|---|---|---|---|
| **S** | `O_{t+1}` (MOO) | `C_{t+1}` / `O_{t+2}` | 18 (may use `d`, `e`, `C_t`) | 36 |
| **M** | `C_t` (MOC) | `O_{t+1}` / `C_{t+1}` | 9 (15:49-complete only) | 18 |

**A structural consequence, noted before the run and worth carrying forward:** once legality is
imposed, **no eligible cell shares a price between its predictor and its outcome.** The bid-ask-
bounce manufacture of gross significance is *impossible by construction* in this grid. The rule
that kills half the ideas also immunises the other half.

**Universe/panel:** the cached T3 minute collection *is* the point-in-time top-500-ADV screen and
is exactly the tier M0 measured the rail in. 2,669 days × 1,611 symbols, **1,222,188 usable
symbol-days**, official close print present on **99.97 %** of them (independent re-confirmation of
M0). Filters (disclosed): price ≥ $3; corporate-action cache flags at t−1/t/t+1 dropped; raw-price
split guard |gap| ≤ 20 %, |day| ≤ 25 %; ≥ 50 names/day. Books are cross-sectional winsorised z,
demeaned, Σ|w| = 2. **No regime conditioning anywhere.**

---

## 2. THE TWO NULLS

| null | value |
|---|---|
| N formulas | **54** |
| analytic √(2 ln N) | 2.825 |
| analytic two-sided √(2 ln 2N) | **3.060** |
| **size-matched placebo, median max\|t\|** | 2.262 |
| **size-matched placebo, p95 max\|t\|** | **3.311** |
| placebo p99 max\|t\| | 3.622 |
| placebo p95 for a *single* cell | 1.983 |

Placebo construction: 300 draws; each draw applies one random circular **time shift**
(30 ≤ k ≤ D−30) to the weight matrix of every formula and re-scores all 54, preserving the
cross-section, each symbol's autocorrelation and the return panel exactly, destroying only the
signal↔return alignment. **The measured null sits 1.08× above the analytic bar** — much milder
than the ~2× inflation the 0822 CEF pair-book showed, because a daily dollar-neutral top-500 book
is far less overlapping than a weekly pair book. *The analytic bar is roughly right here; that is
itself worth recording, since the standing lesson is that it usually is not.*

---

## 3. THE LEDGER — every cell that reached either null

| cell | design SR | design t | held SR | held t | held net @0.5 bp | verdict |
|---|---|---|---|---|---|---|
| `S12_x \| DAY_t1` | −1.67 | **−4.04** | −0.11 | −0.23 | −0.30 | clears BOTH nulls on design → **DEAD out of sample** |
| `S12_x \| OO_t1` | −1.40 | **−3.37** | −0.20 | −0.43 | −0.31 | clears both (placebo p ≈ 0.037) → **DEAD** |
| `M08_p49_vs_close \| ON_t` | +1.37 | +3.31 | −0.16 | −0.33 | −0.41 | clears analytic, **fails placebo p95** → DEAD |
| `S13_d_plus_dlag \| DAY_t1` | −1.26 | −3.03 | +0.18 | +0.38 | −0.34 | fails both, **sign flips** |
| `S07_d_volnorm \| DAY_t1` | −1.20 | −2.87 | +0.61 | +1.29 | −0.15 | fails, sign flips |
| `S01_d \| DAY_t1` | −1.04 | −2.50 | +0.66 | +1.40 | +0.13 | fails, sign flips |

Under the placebo, **0 of 300** draws produce a max|t| above 4.04, so the leader's design-window
significance is genuine (p < 0.0033) — and it evaporates completely on 1,139 untouched held-out
sessions. This is the cleanest illustration in the programme so far that *clearing a properly
measured null on design is necessary and nowhere near sufficient.*

**Sign consistency design → held-out: 17 / 54 (S block 13/36, M block 4/18).** A coin gives 27.
The grid is not merely uninformative, it is *anti*-consistent, which is what a family of small
regime-varying microstructure effects looks like.

**Do not be fooled by the held-out column.** The largest held-out |t| in the grid is
`S15_d_change|OO_t1` at **+2.45** — with a design t of **−0.22**. Twenty-two of 54 cells are net-
positive out of sample at 0.5 bp/side. Both facts are held-out mining and neither is claimable;
they are reported to show that the held-out window has its own noise maximum of exactly the size
the placebo predicts.

### Why the leader was never an auction signal anyway
`S12_x` is ln(C_t/O_t) — a one-day return — predicting the next day's intraday leg with a negative
sign. That is **plain short-horizon cross-sectional reversal, on the auction rail**, and
`EXECUTION_COST_WALL.md` already recorded that family as design-strong and held-out-weak. Its
per-year Sharpe: 2016 −1.02, 2017 −2.25, 2018 −1.49, 2019 −0.46, **2020 −3.37**, 2021 −1.33 →
2022 **+1.37**, 2023 −1.03, 2024 −0.08, 2025 −1.13, 2026 −0.67. **A third of the design window's
whole result is 2020.** Design deciles are monotone (+1.85 → −11.86 bp); held-out deciles are
U-shaped (−5.80 … −6.04) — i.e. out of sample the sort picks up *dispersion*, not direction.

`M08_p49_vs_close|ON_t` is the sharpest sign flip: design deciles rise monotonically
(+0.41 → +11.44 bp), held-out deciles **fall** monotonically (+4.76 → +2.94 bp).

---

## 4. THE ρ1 GATE — and why it is the whole answer

Run *before* the gross bar, as required. Per-symbol series, pooled over 1.2 M symbol-days:

| series | ρ1(level) | ρ1(Δ) | sd | median abs | median abs in **half-ticks** |
|---|---|---|---|---|---|
| **`d` close dislocation** | **+0.056** | **−0.498** | 5.50 bp | **1.55 bp** | **2.00** |
| `d49` (C vs 15:49) | −0.019 | −0.517 | 33.53 bp | 13.01 bp | 21.02 |
| `e` imbalance window | −0.024 | −0.516 | 33.58 bp | 12.89 bp | 21.01 |
| `f` pre-publication | +0.008 | −0.503 | 36.52 bp | 14.04 bp | 22.98 |
| `q` open gap | −0.028 | −0.518 | 151.23 bp | 45.31 bp | 76.90 |
| `x` print day | −0.030 | −0.516 | 209.69 bp | 82.92 bp | 138.60 |
| `u` off-hours | −0.028 | −0.517 | 151.27 bp | 45.21 bp | 76.99 |
| **`ptc` print vs continuous** | **−0.494** | −0.666 | 7.53 bp | 2.40 bp | 4.00 |

Two things to read here, and they are the report.

**(a) `d` is one tick, and it is exact.** The *median symbol-day* has |d| = **2.00 half-ticks** —
one penny, dead on. The dislocation of the official closing cross from the last continuous trade
is, at the median, the price grid itself. There is no imbalance *magnitude* in free data; there is
a rounding.

**(b) Every dislocation series fails the gate, and `ptc` fails it twice.** ρ1(Δ) ≈ −0.50 on a
*level* series is the i.i.d. signature: `d` carries nothing from one session to the next. And
`ptc` = d_t − d_{t−1} shows ρ1(**level**) = −0.494 with a median of exactly **4.00 half-ticks** —
a textbook two-tick bounce. The "MOO-vs-MOC print divergence" idea in the brief is, measured,
a bounce estimator. **Gate verdict: FAIL, for the entire family, before any gross bar.** The
grid's gross numbers survive as honest statistics only because the legality constraint of §1
happened to make them bounce-immune by construction; the *signals themselves* are bounce.

---

## 5. RIG VALIDATION — the T3 control reproduces to 0.10 t

`M01_f|ON_t` is T3's post-correction pre-cutoff variant: signal = 15:29→15:49 continuous return,
**both legs official auction prints**, entry MOC. My weighting is long-high-`f`; T3 is the
reversal, i.e. −`f`.

| | this rig | T3 (`FINDINGS.md` §5e) |
|---|---|---|
| held-out t, pre-cutoff auction-to-auction variant | **+1.28** | **+1.38** |

A panel written from scratch, an independent universe assembly and an independent statistic land
within 0.10 t of the frozen T3 number. **The rig is not the reason this theme reads zero.** It
also re-confirms T3's structural point from the other side: the pre-cutoff variant is the only
version of that signal the free auction rail can reach, and it is not significant.

---

## 6. THE ONE OBJECT THAT SURVIVED OUT OF SAMPLE — and why it is still zero

Found by the pre-registered **interval decomposition** (is the gross an instant or an interval?),
*not* pre-registered itself, so **no promotion claim attaches to it.** Decomposing the MOO→MOC day
into O→15:29 | 15:29→15:49 | 15:49→15:59 | **15:59→C** showed the last component — the next day's
*own* close dislocation `d_{t+1}` — carrying design t **+14.3** and held-out t **+20.6**. That is
an interval-decomposition catching an **instant**: all of it lives inside the closing cross.

Characterised (`INVENT_0822B_auction_TICK.json`), Σ|w| = 2 book, entry must cross the 15:59 quote,
exit is free into the print:

| signal → `d_{t+1}` | design gross | design t | held gross | **held t** | **break-even half-spread** | held net @ measured 1.43 bp |
|---|---|---|---|---|---|---|
| `d_t` | +0.749 bp | +14.26 | +1.006 bp | +20.57 | 0.503 bp | −1.854 bp (t −37.9) |
| `mean5(d)` | +1.089 bp | +22.26 | +1.298 bp | +26.37 | 0.649 bp | −1.562 bp (t −31.8) |
| **`mean20(d)`** | +1.091 bp | +26.76 | **+1.231 bp** | **+26.59** | **0.616 bp** | **−1.629 bp (t −35.2)** |
| `mean60(d)` | +0.967 bp | +25.26 | +0.971 bp | +22.60 | 0.486 bp | −1.889 bp |
| `sign(d_t)` | +0.386 bp | +20.95 | +0.557 bp | +27.28 | 0.279 bp | −2.303 bp |

**What it is.** Roughly half the variance of `d` is a permanent per-name level: sd of the
symbol-mean of `d` is **3.91 bp** against sd(`d`) = 5.50 bp, and pooled ρ1 falls from **+0.056**
to **+0.036** once each symbol is demeaned. So the survivor is *a name's habitual side of the
tick in its own closing cross* — a stable structural fact about where a given ticker's print sits
relative to its last trade, not information about imbalance. Its stability (t +26.6 on 1,139
untouched sessions) is exactly what a fixed effect looks like.

**Why it is zero.** It pays **1.23 bp/day** and to collect it you must buy at 15:59 across a
first-party-measured **1.43 bp** half-spread (T3, same universe, 2022–2026; 1.13 bp 2016–2021).
Break-even **0.616 bp**. The market must become **2.3× tighter** before this exists. This is the
`EXECUTION_COST_WALL` shape inverted: there the cost was the messenger and the signal was the
problem; **here the signal is real, permanent, out-of-sample-confirmed, and smaller than the tick
it lives on.**

---

## 7. VERDICT AND WHAT TO CARRY

**THEME_IS_NOISE = true. Zero survivors. Zero freezes. Nothing to add to BASKET1.**

Carry forward:

1. **The 15:50 cut-off is not a friction, it is a partition.** It splits every auction idea into
   "uses the print, must wait for the next open" and "cannot see the print." It also, for free,
   makes the whole legal grid bounce-immune. Impose it first, before designing anything.
2. **The free tape's auction dislocation is one tick with no memory** (median |d| = 2.00
   half-ticks, ρ1(level) = +0.056). *There is no free imbalance signal to find.* If this theme is
   ever revisited it must be with a purchased **imbalance feed** (Nasdaq NOII / NYSE Order
   Imbalance), which publishes paired/imbalance **share counts** from 15:50 — a claim, not a
   statistic. This is the free-data-convexity wall in its auction-shaped form.
3. **`ptc` (MOO-vs-MOC print divergence) is a bounce estimator, measured:** ρ1(level) −0.494,
   median exactly 4.00 half-ticks. Do not re-propose it.
4. **A placebo that lands close to the analytic bar is informative too.** Here max|t| p95 = 3.31
   vs √(2 ln 2N) = 3.06, 1.08×. The 2× inflation is a property of *overlapping pair books*, not of
   multiple testing generally — measure it, don't assume it in either direction.
5. **The rig replicates T3 to 0.10 t** and is available for any further auction-rail work.
