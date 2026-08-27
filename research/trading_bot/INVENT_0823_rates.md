# INVENT_0823 · RATES / TREASURY TERM-STRUCTURE — MASTER

**Date:** 2026-08-23 · **Scope:** research only. No orders, no money, no network — every input
came from `research/data/ratescredit_cache/` (cached Yahoo adjusted closes + FRED).
**Harness:** `scripts/trading_bot/invent0823_rates.py` ·
`scripts/trading_bot/invent0823_rates_clock.py` · `scripts/trading_bot/invent0823_rates_report.py`
**Pre-registration:** `INVENT_0823_rates_PREREGISTRATION.md` (written before the held-out read).
**Artifacts:** `INVENT_0823_rates_{design,holdout,ANCHORCLOCK}.json`

---

## 0. THE ONE-PARAGRAPH ANSWER

**The theme is noise, and it fails for a reason worth keeping.** 33 pre-registered formulas across
seven families on the US Treasury ETF complex. Zero survivors. But the *way* it dies is new: the
Treasury complex has the best published tether in the entire programme — the US Treasury publishes
the exact constant-maturity curve every wrapper is a claim on, free, daily, permanently, and it
explains **88–92 % of a Treasury ETF's daily variance from 5 years out** (59–73 % at the 1–3 y front
end, where the whole daily move is only ~6 bp), recovering durations of 1.6 / 4.2 / 7.3 / 9.9 / 17.1 /
24.6 y that match the published effective durations. And that anchor is **useless**, because
**FRED H.15 is a 15:30 ET snapshot and the ETF prints at 16:00 ET**. The wrapper-versus-claim
residual is therefore the first difference of the unobservable last half-hour of the session, which
forces `ρ1(Δs) → −0.5` mechanically. Measured: `ρ1 = −0.422` against the published 15:30 anchor,
**`−0.148` against a 16:00 ETF anchor on the same instruments in the same window**, and the
Roll(1984) implied "spread" of the residual correlates **0.995 with σ_daily/√13** (the size of a
30-minute slice) versus **0.210 with the actual bid-ask**, running **7.4× larger than the real
bid-ask**. So the programme's thesis needs one more word: **a published tether must be SYNCHRONOUS,
not merely published.** CEF NAV and ETF-sibling RV work because both sides of the comparison are
struck at 16:00. The Treasury curve fails on the clock, not on the content — and no free feed
publishes a 16:00 curve.

---

## 1. The pooled null

| quantity | value |
|---|---|
| N pre-registered formulas | **33** |
| analytic bar, one-sided `sqrt(2 ln N)` | 2.644 |
| analytic bar, two-sided `sqrt(2 ln 2N)` | **2.895** |
| **size-matched placebo, 400 draws** (design) | mean max\|t\| 2.883 · p50 2.826 · **p95 4.049** · max 4.962 |
| **BAR USED** = max(analytic, placebo p95) | **4.049** |
| placebo / analytic ratio | **1.40×** |
| size-matched placebo, 400 draws (held-out) | mean 2.398 · p50 2.309 · **p95 3.393** · max 4.452 |

In annualised-Sharpe units on the median design book (1,960 days): the analytic bar is **SR 1.04**
and the placebo p95 is **SR 1.45**. Any gross Sharpe below ~1.45 in this theme is indistinguishable
from chance.

**Placebo construction (this matters — the naive null is broken).** XS books get a **per-day
permutation of the signal across panel slots**, with the duration weights left attached to their
slots, so the placebo book has the same gross, the same turnover, the same cost and the same return
covariance; only the signal→instrument assignment is destroyed. TS books get a **circular shift** of
the signal by a uniform offset in [63, T−63]. Rotate-the-returns was **not** used — that null
injects a directional leg and is known-broken in this programme.

**Fourth measurement of the placebo/analytic ratio, and it lands where the prior three said it
would.** 1.08× (disjoint auction book, 0822B), ~2× (overlapping weekly CEF pair book, 0822), 1.14×
(disjoint event book, 0822C), 0.845× (CEF fund-identity permutation) — and now **1.40× on a heavily
overlapping Treasury-ETF book** where all 33 formulas share the same six-to-thirteen instruments.
The inflation continues to track **holding overlap**, not formula count.

---

## 2. Result: 18 formulas clear the gross bar, and every one of them is disqualified

18 of the 33 clear the gross bar of 4.049. The disposal of all 18:

| disposal | count | which |
|---|---|---|
| **ρ1(Δs) bounce gate, run BEFORE the gross bar** | **16** | all 7 bar-clearing ladder-residual cells + all 9 sibling cells |
| pre-registered **decoy** with no economic content by construction | **1** | `E1_decoy_BIL_vs_publishedbill` |
| passed both gates, **earned the held-out look, died there** | **1** | `G1_realladder_resid_fade_5d`, gross t 4.55 → **0.75** |
| never earned a look (sub-bar on design) | 15 | the rest |

### 2.1 The ρ1 ledger — the gate did all the work

Measured on the design window only, on each book's own daily residual return (which *is* Δspread
for a cumulative-residual book):

| book family | ρ1(Δs) range | verdict |
|---|---|---|
| **ladder residual vs published curve** (13 wrappers) | **−0.366 … −0.462** | **BOUNCE — all dead on arrival** |
| **sibling wrappers** (7 sponsor pairs) | **−0.366 … −0.458** | **BOUNCE — all dead on arrival** |
| real-curve (TIPS) ladder | −0.219 … −0.329 | marginal pass |
| butterfly gap | −0.115 | pass |
| **breakeven gap** | **+0.174 … +0.233** | **pass — the only genuinely non-bounce family** |

The gate is not a formality here. It removed **16 formulas whose design gross t ran from +4.76 to
+14.24** — every one of which would have looked like a spectacular discovery on a gross-Sharpe
screen. Inside a tethered family, high gross Sharpe at short horizon is evidence against.

### 2.2 The decoys fired exactly as pre-registered

`E1_decoy_BIL_vs_publishedbill` fades the residual of **BIL — a zero-duration bill fund whose return
IS the published 3-month bill yield over 252 and nothing else** — against SHV. It has no economic
content by construction. It scored:

| | design | held out |
|---|---|---|
| gross Sharpe | **+4.20** (t **+12.86**, 2nd of 33) | **+2.79** (t **+6.59**, 1st of 33) |
| net Sharpe | −10.66 | −10.57 |
| break-even half-spread | **0.32 bp** | **0.18 bp** |

A pure-tick book is the *highest-scoring gross formula in the theme, out of sample*. That is the
pre-registered signature of a complex whose gross Sharpe is manufactured, and it is the reason no
gross number in this document was allowed to stand on its own.

`E2_decoy_TLH_follows_TLT` behaved the same way: lag-0 diagnostic t **−49.9** (it is reading the bar
it trades), lag-1 t +2.64, lag-2 t −0.09.

### 2.3 The one formula entitled to a held-out look, and its death

`G1_realladder_resid_fade_5d` — TIPS wrappers (STIP / SCHP / LTPZ) against the **published real-yield
curve** (DFII5 / DFII10 / DFII30), cross-sectionally demeaned, duration-neutral. It is the only
formula that passed the ρ1 gate (worst leg −0.329) **and** cleared the bar (gross t 4.545 > 4.049).

| | design | **held out** |
|---|---|---|
| gross Sharpe / t | +1.551 / **+4.545** | +0.316 / **+0.747** |
| net Sharpe / t | −9.135 / −26.771 | −5.794 / −13.714 |
| gross bp/day | 0.741 | 0.192 |
| turnover, cost | 0.842, 5.92 bp/day | 0.830, 3.81 bp/day |
| **break-even half-spread** | **0.88 bp** | **0.23 bp** |

It was dead twice over before the held-out window was opened: a break-even half-spread of **0.88 bp**
against charged half-spreads of **4.0–8.0 bp** on STIP/SCHP/LTPZ means the gross edge is roughly a
*tenth* of the tick. The held-out read then removed the gross edge as well.

### 2.4 The most interesting cell — and why it does not count

`C5_begap_LTPZ_TLT_10d` — long-TIPS wrapper against TLT, with the **published 10-year breakeven** as
the signal anchor (the P&L leg is fully tradable; the published series enters only the signal). It is
the only cell in the theme that is economically shaped like a real edge:

* **ρ1 = +0.184** — not bounce, the only family that is not;
* **break-even half-spread 5.36 bp (design) / 3.97 bp (held out)** — the only cell whose break-even
  sits *above* its charged cost;
* design net Sharpe **+0.08**, held-out net Sharpe **−0.215**.

And its design gross t is **2.935 — below the 4.049 bar** (and barely above the 2.895 analytic one).
**It never earned a held-out look and is not claimed as one.** It is recorded here because it is the
only structure in the theme that the anchor-clock problem does *not* destroy — both legs print at
16:00 and the published breakeven enters the signal only — and because if this theme is ever revisited,
this is the cell to revisit, at a horizon where the gross can clear a bar rather than sit under it.

### 2.5 Published carry / roll-down: not merely insignificant — regime-fragile

The `D` family computes carry + roll-down per unit duration from the published curve alone (no
fitting) and trades it duration-neutral across the six-segment ladder. The book is well-formed:
mean net duration **+0.015 y**, gross 0.905, and it tilts the way the ZIRP curve says it should
(mean weights SHY +0.23, IEI +0.13, IEF +0.07, TLH −0.00, TLT −0.03, EDV −0.03).

| | design gross t | **held-out gross t** | held-out net SR |
|---|---|---|---|
| D1 daily | −0.09 | **−3.32** | −1.86 |
| D2 weekly | −0.20 | **−3.73** | −1.82 |
| D3 smooth21 weekly | +0.05 | **−4.05** | −1.90 |
| D4 smooth21 monthly | +0.02 | **−4.28** | −1.99 |

Zero across the ZIRP decade, then **−1.8 to −2.0 Sharpe through the hiking cycle**, on almost no
turnover (0.010–0.087) so it is not a cost artifact. The published curve's shape told you to own the
front end and short the long end; 2022 sold off the front end hardest. This is the classic
short-volatility signature of a carry trade and it is one more entry for the programme's
carry-is-dead ledger — this time in the one instrument class where the carry is *published exactly*
rather than estimated. **Publishing the carry does not make it earnable.**

---

## 3. THE STRUCTURAL FINDING: a published tether must be SYNCHRONOUS

This is the part worth keeping.

`INVENT_0823_rates_ANCHORCLOCK.json` holds the instruments, the window and the construction fixed
and changes exactly one thing — whether the anchor prints on the same clock as the tradable leg.

**P1 — swap the 15:30 published anchor for a 16:00 ETF anchor on a *different* curve segment
(so it is not a sponsor sibling):**

| wrapper / 16:00 anchor | ρ1(raw return) | ρ1 vs **published 15:30** curve | ρ1 vs **16:00** ETF anchor |
|---|---|---|---|
| TLT / IEF | −0.034 | **−0.419** | **−0.000** |
| IEF / TLT | −0.048 | **−0.434** | **−0.009** |
| IEI / IEF | −0.038 | **−0.440** | **−0.068** |
| TLH / IEF | −0.031 | −0.410 | −0.183 |
| SHY / IEI | −0.093 | −0.396 | −0.280 |
| EDV / TLT | −0.001 | −0.431 | −0.349 |
| **mean** | | **−0.422** | **−0.148** |

The raw returns have no autocorrelation. The residual against the published curve has ρ1 ≈ −0.42.
The residual against a 16:00 anchor has ρ1 ≈ −0.15 — and the part that remains is concentrated in the
genuinely thin wrappers (EDV 32k shares/day, TLH 51k), i.e. that remainder *is* real bid-ask bounce
while the rest was the clock.

**P2 — the Roll(1984) implied half-spread of the residual is the missing half-hour, not the tick:**

| wrapper | daily σ | σ/√13 (a 30-min slice) | Roll-implied half-spread | actual charged half-spread |
|---|---|---|---|---|
| SHY | 5.8 bp | 1.6 bp | **1.9 bp** | 1.2 bp |
| IEI | 19.8 | 5.5 | **3.6** | 2.5 |
| IEF | 38.1 | 10.6 | **7.4** | 1.2 |
| TLH | 57.0 | 15.8 | **12.1** | 8.0 |
| TLT | 92.3 | 25.6 | **19.5** | **0.7** |
| EDV | 130.4 | 36.2 | **24.4** | 4.0 |

`corr(Roll, σ/√13) = **0.995**` across a 15× range of duration (1.60 y → 24.62 y).
`corr(Roll, actual bid-ask) = 0.210`.
The Roll number averages **7.44×** the real bid-ask and **0.79×** the predicted 30-minute slice. TLT
is the decisive case: a penny-wide ETF whose true half-spread is ~0.6 bp shows a Roll-implied 19.5 bp
— 30× too large for a spread, and dead-on for half an hour of 17-year duration.

**The generalisation.** The programme's thesis has been *free data prices a statistic, never a claim;
hunt spreads where a third party publishes the tether value.* This theme adds the missing clause:

> **The published tether must be struck on the SAME CLOCK as the tradable leg.** T12's CEF NAV is
> struck at 16:00 against a 16:00 price. ETF-sibling RV compares two 16:00 prints. The Treasury
> constant-maturity curve is published at 15:30 against a 16:00 print, and that half-hour gap is
> large enough — because Treasury ETF duration multiplies it — to swamp any dislocation the tether
> was supposed to reveal. An asynchronous anchor does not merely add noise; it manufactures a
> `ρ1 → −0.5` artifact that *looks exactly like* a tradable mean-reverting spread and will produce
> gross Sharpes of 3–6 on any fade of it.

**This is not fixable on free data.** A 16:00 Treasury curve mark is a paid product (ICE / Tradeweb
closing curve); CME Treasury futures settle at 14:00, which is worse, not better; and building the
anchor out of the ETFs themselves converts the claim back into a statistic, which is the dead zone.
The escape route is the same one `DATA_PURCHASE_SCOPE.md` already names.

---

## 4. Infrastructure: one bug, contained but live

`scripts/trading_bot/newterr_ratescredit.py:70` converts Yahoo timestamps with

```python
return dt.datetime.utcfromtimestamp(ts + 43200).strftime("%Y-%m-%d")
```

The daily bars in `research/data/ratescredit_cache/etf_daily.json` are stamped at the **session open,
13:30 UTC** (09:30 EDT) — already on the correct UTC calendar day. Adding 12 hours rolls **every bar
forward one day**. Measured on TLT vs DGS20 over 2010–2020:

| alignment | corr(r_TLT, Δy20) | implied duration |
|---|---|---|
| the `+43200` convention | **−0.20** | 3.7 y |
| **correct** | **−0.74** | **13.9 y** |

Under the buggy convention the whole point of that script — FRED-conditioned rates/credit signals —
was being computed against a curve shifted a day out of alignment, and the recovered durations were
~1/4.5 of the truth. That script has **never written a result file**, so nothing downstream is
contaminated and no published finding needs revision. But `ratescredit_cache` is a shared cache and
the convention is a live trap for the next user of it. `invent0823_rates.py:_to_date` uses the correct
conversion and documents why in a comment. **Recommendation: fix or delete
`newterr_ratescredit.py:70` before that script is ever run.**

---

## 5. Ledger entries

**DEAD — do not re-propose:**

* **Treasury-wrapper-vs-published-curve residual RV** (any horizon, any panel, nominal or real curve)
  — killed by the 15:30/16:00 anchor-clock artifact, which is structural and unfixable on free data.
* **Treasury sponsor-sibling RV** (SHY/VGSH/SCHO, IEI/VGIT/SCHR, TLT/VGLT/SPTL, EDV/ZROZ) — ρ1 −0.37
  to −0.46 on all seven pairs; break-even half-spreads 1.35–8.64 bp against Roll-measured effective
  half-spreads of 2.0–17.4 bp. The edge is smaller than the tick. *Note this is the same tether as
  the ALIVE `ETF-sibling RV`; what differs is that the Treasury siblings track the same curve so
  tightly that no dislocation ever exceeds the spread.*
* **Published curve carry / roll-down, duration-neutral** — zero on design, −1.8 to −2.0 Sharpe out of
  sample at negligible turnover. Carry remains dead, now including the case where it is published.
* **Curve steepener/flattener momentum and reversal via SHY/IEF/TLT** — covered by the ladder-residual
  and butterfly families; nothing above the bar.
* **ETF-implied vs published butterfly gap** — ρ1 clean (−0.115) but gross t 3.07 / 0.75, sub-bar, and
  break-even 0.45 bp.

**SHELVED, not killed:** `C5 / C6` **published-breakeven gap** (TIPS wrapper vs duration-matched
nominal wrapper, anchored on FRED T10YIE). Sub-bar on design so it never earned a held-out look, but
it is the only non-bounce family in the theme (ρ1 +0.17…+0.23) and the only cell whose break-even
half-spread exceeds its cost. Both legs print at 16:00, so the anchor-clock defect does not apply.
If rates are revisited, revisit this and nothing else.

**ALIVE, untouched by this round:** T3, ETF-sibling RV, dual-class RV, T7, T12 CEF, CRYPTO_LOWVOL.

---

## 6. What was NOT done

No regime conditioning, no macro gating, no Fed-cycle state variable, no VIX/NFCI switch — that was a
pre-registration commitment, not a post-hoc choice. Nothing was committed to BASKET1. No orders, no
network, no spend.
