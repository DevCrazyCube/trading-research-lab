# INVENT_0823 — MASTER SYNTHESIS

**Date:** 2026-08-23
**Scope:** 3 fresh published-tether themes, **106 original formulas**, pooled multiple-testing correction over the total.
**Verdict: HONEST ZERO. 0 survivors. 0 basket proposals. 3 of 3 themes are noise.**
**Basket action: NONE.** BASKET1 is at v8 on a fresh forward clock and this round contributes nothing to it — no leg, no re-freeze, no weight change.

---

## 1. What was run

| # | Theme | File | N | Own analytic bar | Own placebo bar | Survivors |
|---|---|---|---:|---|---|---:|
| 1 | Bond/credit-ETF structural RV (HY, IG, agg, muni, EM, loans, preferred siblings; ETF-vs-published-curve; TIPS breakeven) | `INVENT_0823_bondrv.md` | 44 | 0.87 (Sharpe, 9.98y) | 0.82 (Sharpe, 400 draws) | 0 |
| 2 | Rates / Treasury term structure (wrapper-vs-published CMT curve, real-yield ladder, breakeven, carry/roll-down, butterfly) | `INVENT_0823_rates.md` | 33 | 2.895 (t) | 4.049 (t, 400 draws) | 0 |
| 3 | Exotic hard-tether structures (same-coin crypto-ETP wrappers, currency-hedged siblings, leveraged/inverse complex, fund-of-funds) | `INVENT_0823_exotic.md` | 29 | 1.009 (Sharpe, 7.1y) / 2.371 coin subfamily | 1.069 (p95 sign-flip block bootstrap) | 0 |
| | **TOTAL** | | **106** | | | **0** |

All three themes were chosen under the central thesis — *free data prices a statistic, never a claim* — by hunting spreads where a **third party publishes the tether value**: the US Treasury constant-maturity and TIPS real-yield curves (FRED), ETF sibling identity (two wrappers on one claim, both struck 16:00 ET), prospectus daily-leverage mandates, published expense ratios, published fund-of-funds weights, and the physical-coin identity behind spot BTC/ETH ETPs. None of these instrument families had appeared in the repo before.

---

## 2. The pooled correction

Each theme corrected for its own N. Corrected over the **total 106**, every candidate moves further under water.

**Pooled analytic expected-max** = √(2 ln 106) = **3.054 in t-units**, which on a ~10-year design window is a **pooled noise bar of 0.97 Sharpe** (0.95 on 10.4y, 1.15 on the 7.1y exotic window). Two-sided (√(2 ln 212)) = 3.27 t.

Rescaling each theme's own *size-matched placebo* bar to N=106 by √(ln 106 / ln N):

| Theme | Own operative bar | Rescaled to N=106 | Best candidate | Clears pooled? |
|---|---|---|---|---|
| bondrv | 0.87 Sharpe | **0.97 Sharpe** | `BC_xs_z21c` design OO gross **1.95** | yes on design |
| rates | 4.049 t | **4.57 t** | `G1_realladder_resid_fade_5d` design t **4.545** | **no — misses by 0.03 t** |
| exotic | 1.069 Sharpe | **1.30 Sharpe** | `L7_lev_decay_carry` corrected design **0.22** (raw 1.23) | no |
| exotic (coin sub) | 2.371 Sharpe | **2.88 Sharpe** | `C9_feegap_carry` **1.06** | no |

The pooled correction alone eliminates the rates theme's single design-stage passer. **One** candidate in 106 clears the pooled bar on design gross — and it is dead held out.

**The placebo/analytic ratio was measured a fifth and sixth time and continues to track holding overlap, not formula count:** 1.40x (rates, overlapping 5-day books), 0.94x (bondrv, 0.82 placebo vs 0.87 analytic, disjoint daily), 1.06x (exotic long-history), 0.86x (exotic coin subfamily). Prior measurements: 1.08x disjoint auction, ~2x overlapping weekly CEF, 1.14x disjoint event, 0.845x CEF permutation. **The rule is now well-supported: for daily non-overlapping books the analytic bar is roughly right; for multi-day overlapping books it understates by 1.4–2x.** Use the size-matched placebo whenever holdings overlap.

**Null construction was correct in all three themes.** For cross-sectional books the signal was permuted across panel slots (weights left attached to slots, so gross/turnover/cost/covariance are preserved); circular shift for time-series books. **Rotate-the-returns was not used anywhere** — it injects a directional leg. Two identity-permutation placebos in the exotic theme were correctly inert (design gross −0.36 and −0.16).

---

## 3. Why nothing survived: three new structural clauses on the central thesis

This is the round's real output. The thesis said: *hunt spreads where a third party publishes the tether value.* Three independent themes each hit a different wall, and each wall is a **general, pre-tradeable filter** that costs nothing to apply and would have killed most of these 106 formulas before they were coded.

### Clause 2 — the published tether must be **SYNCHRONOUS**
*(from `INVENT_0823_rates`, replicated in `INVENT_0823_bondrv`)*

The Treasury complex has the programme's **best** published tether: the US Treasury publishes the exact constant-maturity curve every wrapper is a claim on, and it explains 88–92% of a Treasury ETF's daily variance from 5y out, recovering effective durations (1.6 / 4.2 / 7.3 / 9.9 / 17.1 / 24.6y) that match the published ones. It is still useless, because **FRED H.15 is a 15:30 ET snapshot and the ETF prints at 16:00 ET.** The wrapper-vs-claim residual is therefore the first difference of an unobservable last half-hour, which forces ρ1 → −0.5 **mechanically**.

Measured, holding instruments/window/construction fixed and changing **only the anchor's clock**: ρ1 = **−0.422** vs the published 15:30 curve, **−0.148** vs a 16:00 ETF anchor (TLT/IEF goes −0.419 → −0.000). Independently replicated in the bondrv theme at −0.465. And the Roll(1984) implied half-spread of the residual correlates **0.995** with σ_daily/√13 — the size of a 30-minute slice — across a 15x range of duration, versus **0.210** with the actual bid-ask, running 7.44x larger than it (TLT: 19.5 bp Roll-implied against a real ~0.6 bp half-spread).

**An asynchronous anchor does not merely add noise — it MANUFACTURES a ρ1 → −0.5 artifact that looks exactly like a tradable mean-reverting spread and yields gross Sharpes of 3–6 on any fade of it.** Not fixable on free data: a 16:00 curve mark is ICE/Tradeweb paid; CME Treasury futures settle at 14:00 (worse); building the anchor from the ETFs converts the claim back into a statistic. T12's CEF NAV is struck at 16:00 against a 16:00 price and ETF-sibling RV compares two 16:00 prints — **that is why the two ALIVE families are alive.**

### Clause 3 — the deviation must **EXCEED THE SPREAD**
*(from `INVENT_0823_bondrv`)*

The bond/credit sibling families have **no clock problem** — both legs are 16:00-struck, ρ1 runs −0.20 to −0.26, and the de-bounced pooled book (`BC_xs_z21c`, 11 pairs) posts design OO gross **1.95**, clearing all three nulls including the pooled one. **The tether is genuinely informative and the book still loses**, because the mispricing is **0.21 bp/day against a 0.6–1.25 bp half-spread**: cost runs 2.4x gross, net −2.84.

Borrow is explicitly **not** the binding constraint here (unlike preferred-RV): every leg is a bond ETF above $20M ADV, the easiest-to-borrow universe there is, borrow under 0.02 bp/day. This family dies purely on spread. Reported as a near miss and not rounded up: `A_ig_lqd_usig_z63c` (LQD vs USIG) is the only formula stable across the split — OO gross 0.79 → 0.71, net −0.17 → −0.07, positive on both windows at the arithmetic tick-floor bound, cost only 1.11x gross — but its gross is **below the bar on both windows**, so it fails before cost is even discussed. The shape of the miss is the useful part: **IG sibling RV is a genuine, stable, tiny edge almost exactly the width of the spread.**

### Clause 4 — execution must happen on a **DIFFERENT PRINT** from the signal
*(from `INVENT_0823_exotic` and `INVENT_0823_bondrv`, independently)*

The programme's rule "inside a tethered family a high gross Sharpe is evidence against" **now has a coefficient: up to 63x.**

Every exotic formula was run on three clocks. Honest (signal at close t−1, execute at OPEN t, earn open→open) vs contaminated (signal at close t, earn close t→t+1): `C6_coin_z20_rev_H1` goes **+0.36 → +22.57**; `C3` goes **−0.85 → +21.45**; `H3` +0.57 → +7.92; four more flip sign. The **identity-permutation placebos do not move** (−0.16 → −0.09, −0.36 → −0.34), so the inflation is bid-ask bounce, not machinery and not multiple testing. Control `CTRL_SPY_IVV_z20_H5` — the known-real-but-inside-the-spread sibling structure — behaves exactly as `DEEPMINE_etf_structural_rv` predicts: −0.07 honest, +0.59 contaminated.

The bondrv theme reached the same conclusion by a different route (**the open-to-open discriminator**, recommended for all future RV work): the close-to-close L=1 book is filled *at* the print its signal came from, so a half-spread charge cannot fix a signal correlated with which side printed. Moving the fill to the next open collapses pooled sibling gross **6.17 → 1.28** and Treasury-curve gross **8.89 → 1.29**, and turns net negative for 44/44. Self-tested: the OO panel has 100% coverage and OO daily vol matches CC vol (HYG 44.0 vs 45.7 bp), so the collapse is signal decay, not a data artifact. The one-day lag-kill agrees (6.17 → 0.91).

**The defence costs nothing. Move execution off the signal's own print, always.**

### The ρ1 gate earned its keep, exactly as predicted
`C_tsy_z21c` posts the round's highest gross Sharpe (**10.35**) with a positive headline net (+1.84) and is pure bid-ask bounce at ρ1 −0.465. Killed **before** the Sharpe was believed. Also killed on ρ1: TIPS breakeven (−0.383), GOVT-vs-ladder (−0.432), 7 of 18 bond sibling pairs (−0.377 to −0.496), 16 of 33 rates formulas (−0.37 to −0.46, with design gross t running from +4.76 to **+14.24**), currency-hedged triangles (−0.417), BTC wrappers (−0.470), ETH wrappers (−0.538).

### The decoys fired as pre-registered
`E1` fades the residual of **BIL** — a zero-duration bill fund whose return *is* the published 3-month bill yield over 252 — and scored gross Sharpe +4.20 (t +12.86) design and **+2.79 (t +6.59) HELD OUT**, the single highest gross t of all 33 out of sample, on a break-even half-spread of 0.18 bp. **A pure-tick book beat every real family out of sample.** That is why no gross number in this round was allowed to stand alone.

---

## 4. The NAV data-block: the concrete paid-data ask

The direct T12 analogue for bond ETFs — fund price vs **published NAV** — is **data-blocked**, killed before it could be tested. Probed 2026-08-23:

- iShares `.ajax` NAV CSV returns product-page HTML on both `ishares.com` and `blackrock.com` (bot wall), with browser UA / Referer / `siteEntryPassthrough` / `asOfDate` all tried.
- SSGA `nav-history` xlsx: 404 (two path forms). Vanguard price-history API: 404/400.
- Yahoo iNAV tickers (`^HYG-IV`, `HYG-IV`, `HYG.IV`, `^HYGIV`): not served. Nasdaq historical: price-only.
- FRED ICE BofA index **total-return** series (`BAMLHYH0A0HYM2TRIV` etc.) are free and daily but **licence-capped to a rolling 3 years** — and a *rolling* cap means the design window is not even reproducible.

**The tether value IS published daily by every issuer and is NOT machine-readable free.** This is the sharpest statement yet of the free-data convexity wall, and the clearest paid-data purchase order the programme has produced: *historical daily ETF NAV, all US bond ETFs, 2010→present.*

---

## 5. Candidates examined and why each is NOT promoted

Nothing below is proposed for the basket. Each is listed so it is not re-derived.

| Candidate | Tether | Design | Held out | Killed by |
|---|---|---|---|---|
| `BC_xs_z21c` — 11-pair bond sibling RV, 21d z, OO fill | sibling identity (both 16:00) | OO gross **1.95** (clears pooled 0.97) | gross **0.53** vs 1.17 bar; net **−3.22** (tick-floor bound −1.54) | held-out gross collapse; net dead by Clause 3 |
| `G1_realladder_resid_fade_5d` — STIP/SCHP/LTPZ vs FRED DFII5/10/30, duration-neutral | published TIPS real-yield CMT curve | t **+4.545** vs pooled bar **4.573** | gross t +0.747; net Sharpe **−5.79** | **pooled null (by 0.03 t)**; then held-out; then cost (break-even 0.88 bp design / 0.23 bp held vs 4–8 bp charged) |
| `L7_lev_decay_carry` — long m·base / short 1 LETF, 13 bull funds, zero turnover | prospectus daily-leverage mandate + published expense ratio | raw 1.23; **corrected excess-of-cash at 0.33%/yr ETB: 0.61 pooled, 0.22 (t 0.63) executable subset** vs bar 1.069 | raw 5.94; corrected 1.34 pooled / **1.45 (t 2.35) executable**; positive both windows on all six broad-index LETFs | **fails the null on the corrected design statistic.** Worth ~0.5%/yr of gross notional |
| `C9_feegap_carry` — long low-fee coin wrappers / short GBTC+ETHE | published expense-ratio gap (1.50% / 2.50% vs ≤0.25%) | 1.06 vs bar 2.371 | +0.45%/yr at ETB; **−1.07/−1.51 at 3%/yr borrow** | sub-bar; 2.6y sample that cannot be extended backwards |
| `A_ig_lqd_usig_z63c` — LQD vs USIG | sibling identity | OO gross 0.79 | 0.71; net −0.07 | below bar in both windows |
| `C5/C6` published-breakeven gap | FRED T10YIE | gross t 2.935 vs bar 4.049 | **never looked at** | sub-bar on design |

**`C9` deserves one sentence on the record even though it is not promoted: it is the cleanest confirmation of the central thesis the programme has.** Two ETPs holding the identical physical bitcoin *must* diverge at the published fee gap. Out of sample the spread drifted **+1.268 %/yr against a published gap of 1.267 %/yr** — t vs published = **0.002** — with spread vol of only 0.57%/yr. The published claim priced itself to three decimal places. It is simply too small to trade at 0.33%/yr borrow with a 2.6-year sample.

**`L7` is the only forward-test lead.** Sized at zero. It is genuinely neutral (SPY beta −0.005, t −3.5 design; +0.002 held out), the realised 0.4–0.9%/yr matches the ~0.44%/yr the published fees predict, and it is positive in both windows on SSO / QLD / TQQQ / TMF. It is also worth about half a percent a year on gross notional, carries product-restriction and borrow risk, and **fails the null**. Carry it as a lead; do not freeze it.

**`C5/C6` is shelved, not killed** — the only non-bounce family in the rates theme (ρ1 **+0.17 to +0.23**, positive), the only cell whose break-even half-spread (5.36 bp design / 3.97 bp held) exceeds its charged cost, both legs 16:00-struck so the anchor-clock defect does not apply, and the published series appears in the **signal only** so the P&L leg stays fully tradable. It never earned a held-out look and is not claimed as one. **If rates are ever revisited, revisit this and nothing else.**

---

## 6. Diversification check vs BASKET1 (v8)

Moot — there are no proposals. Recorded for completeness: BASKET1's four roughly-independent sources are overnight (T3+T7, 0.28), identical-claim RV (ETF-sibling + dual-class, 0.29), CEF discount (0.27), and crypto-perp positioning (0.12), plus a 0.04 ORB probe.

Had anything survived, **only `L7` and `C9` would have diversified** — both are static, near-zero-turnover carries on published fees/mandates, uncorrelated with every existing leg (betas ~0 to SPY and to the coin in both windows). Every spread-reversion candidate in this round (bond siblings, Treasury siblings, hedged-sibling triangles, coin-wrapper reversion) sits **inside the identical-claim RV bucket that already holds 0.29 of the risk budget** — i.e. the round's most numerous ideas were also its least diversifying.

---

## 7. Additions to the DEAD ledger

Do not re-propose:

1. **Bond/credit-ETF sibling RV** — HY, IG, Treasury, agg, TIPS, muni, EM, loans, preferred. Dies on Clause 3 (edge ≈ spread width), not on borrow.
2. **Bond-ETF vs published-Treasury-curve residual RV**, and vs published-Moody's-yield residual RV.
3. **TIPS-breakeven tether RV** (ρ1 −0.383).
4. **Bond-ETF vs published-composition synthetic basket RV.**
5. **Treasury-wrapper-vs-published-curve residual RV**, any horizon/panel, nominal or real — killed *structurally* by the anchor clock (Clause 2).
6. **Treasury sponsor-sibling RV** (SHY/VGSH/SCHO, IEI/VGIT/SCHR, TLT/VGLT/SPTL, EDV/ZROZ) — ρ1 −0.37 to −0.46 on all seven pairs; break-evens 1.35–8.64 bp against Roll-measured half-spreads of 2.0–17.4 bp. Same tether as the ALIVE ETF-sibling family; what differs is that Treasury siblings track the curve so tightly no dislocation ever exceeds the spread.
7. **Published curve carry / roll-down, duration-neutral** — worse than insignificant: gross t ~0 through the ZIRP decade, then **−3.3 to −4.3** (net Sharpe −1.8 to −2.0) through the hiking cycle at negligible turnover (0.010–0.087, so not a cost artifact), on a well-formed book (net duration +0.015y, gross 0.905). **Carry stays dead even in the one instrument class where the carry is published exactly.**
8. **ETF-implied vs published butterfly gap** — ρ1 clean (−0.115) but sub-bar, break-even 0.45 bp.
9. **Same-coin crypto-ETP wrapper cross-sectional reversion** — z20/z60/1d/5d/20d/long-only-cheapest-3.
10. **Currency-hedged sibling triangles**, including the same-clock FX-ETF construction (and unshortable besides).
11. **Leveraged-complex path residuals at DAILY horizon** — DEEPMINE's intraday verdict survives the move to daily.
12. **Fund-of-funds published-weight replication residual** — `F5_fof_fee_carry` (design 0.44 / held 0.48) is **pure equity beta**: SPY beta +0.049, **t = 36.4**, alpha −0.03 bp/day (t −0.2).
13. **Bull/bear short-both decay harvest** (`L8`) — SPY beta +0.024 (t 6.0), held-out Sharpe −1.39, and unimplementable anyway.

---

## 8. Operational findings to act on

**(a) LIVE INFRASTRUCTURE BUG, contained.** `scripts/trading_bot/newterr_ratescredit.py:70` does `utcfromtimestamp(ts + 43200)`, but the daily bars in the shared `ratescredit_cache` are stamped at the session **open** (13:30 UTC), already on the correct calendar day. **The +12h offset rolls every bar forward one day.** Measured on TLT vs DGS20: corr **−0.20** and implied duration **3.7y** under the buggy convention, versus corr **−0.744** and **13.85y** correct. That script's entire premise (FRED-conditioned rates/credit signals) was computing against a curve a day out of alignment. It has **never written a result file, so no published finding needs revision** — but `ratescredit_cache` is shared and the convention is a trap for the next user. **Recommend fixing or deleting it.** (The rates agent hit the same bug first; it is what initially made its A-family look like a clean pass of the bounce gate at ρ1 −0.15.)

**(b) SCREEN SHORTABILITY BEFORE WRITING FORMULAS.** A live `/v2/assets` snapshot shows the broker product restriction is far wider than assumed: **13 of 14 inverse ETFs**, plus TNA / SOXL / ERX, plus **all four currency ETFs** (FXE/FXY/FXB/FXC), plus HEZU/HEWG/DBJP/EWG/EWU/AOK are **not shortable**. Family H was unimplementable independently of its zero signal. Add an `/v2/assets` short-leg screen to the front of every RV harness.

**(c) A PRICE-RETURN BACKTEST OF A BOOK WITH NON-ZERO NET CASH IS NOT A RETURN.** `L7` carries +0.43 of gross in net cash, which the price series silently pays at the bill rate. Charging net cash at BIL and the short weight at B22G's measured borrow ladder cut it from **1.23 to 0.61**, and exposed `F5` as pure beta. Any book that is not dollar-neutral must be scored excess-of-cash.

**(d) A stale-opening-print lookahead was suspected for thin funds and MEASURED AND ACQUITTED:** open == prev close on 0.6–5.3% of days, and the overnight-gap vs previous **non-overlapping** close-to-close correlation is negative everywhere (median |ρ| 0.062, AOR −0.122, SPY −0.084). Staleness would show as a large positive. Noted because the first version of that diagnostic used *overlapping* windows and produced spurious +0.6 correlations — found and rewritten before publication.

---

## 9. Recommended amendment to the central thesis (for FINDINGS.md)

> **Free data prices a statistic, never a claim.** An edge is only available where a third party publishes the tether value — *and all four of the following hold:*
>
> 1. **PUBLISHED** — a third party, not you, states the fair value (NAV, shared index, prospectus mandate, expense ratio, sibling identity).
> 2. **SYNCHRONOUS** — the tether is struck on the same clock as the tradable print. An asynchronous anchor does not add noise, it *manufactures* a ρ1 → −0.5 artifact that mimics a tradable spread and yields gross Sharpes of 3–6 on any fade of it.
> 3. **WIDER THAN THE SPREAD** — the typical deviation must exceed the round-trip half-spread. A tether can be genuinely informative (design gross 1.95, clears every null) and still be untradable at 0.21 bp/day against a 0.6–1.25 bp half-spread.
> 4. **EXECUTABLE OFF ITS OWN PRINT** — the fill must be a *different* print from the one the signal was computed on. Contaminated close-to-close fills inflate gross Sharpe by up to **63x** in tethered families, and no half-spread charge can repair a signal correlated with which side printed.
>
> Clause 1 alone was the 2026-08 thesis. Clauses 2–4 are what 106 formulas across bonds, rates and exotics cost to learn. T12 CEF and ETF-sibling RV are ALIVE precisely because they satisfy all four.

---

## 10. Method (all three themes)

- **Design/held-out split declared before scoring; held-out read once, after the design ranking was on disk.** bondrv 2010-01-04→2019-12-31 design (2515 sessions) / 2020-01-02→2026-08-20 held out (6.62y). rates 2010-08-06→2020-12-31 / 2021-01-01→2026-08-18 (5.6y = the entire hiking cycle, the deepest inversion since 1981, and the re-steepening); the design stage built its panel with `end=2020-12-31`, so held-out rows were **unreachable**, not merely unscored.
- **No regime conditioning anywhere.** Signs pre-registered (mean reversion = positive Sharpe; a negative Sharpe is a failure, not a flip).
- **Nulls, three ways:** analytic √(2 ln N) or √(2 ln 2N); size-matched placebo permuting the **signal** (400 draws bondrv/rates, 2000-rep sign-flip block bootstrap exotic, common offset/block-signs across formulas so cross-correlation survives the max); stationary block bootstrap of demeaned daily gross PnL. Bar = max of the three, then re-corrected pooled over 106 here.
- **ρ1(Δspread) bounce gate run BEFORE the gross bar**, as required. Exempted only for the 6 zero-turnover static carries, which have no timing to exploit — exemption stated in advance.
- **Costs:** both legs pay max(1.0 bp, 2 × half-a-cent/price) tick-floor-times-adversity proxy (×1.5 for an opening print, shocked ×2), + 0.15–0.278 bp SEC 31 / FINRA TAF, + B22G's measured 0.33%/yr ETB borrow on short notional per calendar day, + net cash at BIL. Corwin-Schultz effective half-spreads were estimated from the same daily bars and floored at 1.0 bp (every median estimate was ≤0). **Deliberately generous — nothing here dies of cost alone.** An arithmetic tick-floor lower bound is reported alongside every number.
- **Controls:** `CTRL_LONG_SPY` design 0.81 / held 1.30 (harness sane). `CTRL_SPY_IVV_z20_H5` behaves exactly as documented. Two identity-permutation placebos inert.
- **Overlap caveat:** the bondrv and rates themes ran concurrently and overlap on the Treasury sibling pairs and the published-curve tether; **their results agree** (ρ1 −0.465 vs −0.422 on the curve anchor). The overlap is counted once in N=106 only in the sense that the formulas are distinct; the agreement is treated as replication, not as two independent findings.
- **Data:** cached/free only — Alpaca daily bars (`adjustment=all`, 90 symbols), Yahoo adjusted closes, FRED, Stooq. No network crawls inside agents, no orders, nothing committed to BASKET1.

---

## 11. Deliverables

```
research/trading_bot/INVENT_0823_MASTER.md          <- this file
research/trading_bot/INVENT_0823_bondrv.{md,json}
research/trading_bot/INVENT_0823_bondrv_{DESIGN,HOLDOUT}.json
research/trading_bot/INVENT_0823_rates.{md,json}
research/trading_bot/INVENT_0823_rates_PREREGISTRATION.md
research/trading_bot/INVENT_0823_rates_{design,holdout,ANCHORCLOCK}.json
research/trading_bot/INVENT_0823_exotic.{md,json}
research/trading_bot/INVENT_0823_exotic_{DESIGN,DIAG,EXEC}.json
scripts/trading_bot/invent0823_bondrv.py, invent0823_bondrv_ohlc.py
scripts/trading_bot/invent0823_rates{,_clock,_report}.py
scripts/trading_bot/exo0823_{fetch,sweep,diag,exec}.py
research/data/ratescredit_cache/etf_open.json        (new, 42 symbols)
research/data/exo0823_cache/                          (new, 90 symbols)
```

---

## 12. Bottom line

**106 formulas, 3 published-tether themes, 0 survivors, 0 proposals, 3 of 3 themes noise. No basket change; BASKET1 v8 runs untouched on its fresh forward clock.**

The round is not empty. It converted the central thesis from a one-clause heuristic into a **four-clause pre-tradeable filter**, produced the programme's cleanest single confirmation of that thesis (a published 1.267%/yr fee gap realising at 1.268%/yr), identified the exact paid-data purchase that would unblock the largest untested family (historical daily bond-ETF NAV), found a live cache-convention bug before it could contaminate a published result, and killed thirteen families that would otherwise have looked like obvious next ideas.

The honest reading: **the published-tether class is now well-explored on free daily data, and the two ALIVE members (T12 CEF, ETF-sibling RV) look less like the head of a rich family and more like the only two instances that satisfy all four clauses at once.** Further search inside this class has low expected value. The next real move is Clause-2/3 relief — a synchronous 16:00 tether or a wider-than-spread deviation — and both are paid-data or forward-collection problems, not search problems.
