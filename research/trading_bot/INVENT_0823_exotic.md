# INVENT_0823 — theme: EXOTIC / LEFT-FIELD, hunting a HARD PUBLISHED TETHER

**Date:** 2026-08-23 · **Scored formulas: 29** (+2 identity-permutation placebos, +2 controls)
· **Survivors under the pre-registered rule: 0**
· **But the round is not empty: two non-searched MECHANISM carries reproduce out of sample at
their published magnitude, and one of them is the cleanest confirmation of the programme's
central thesis it has produced.**

Harness `scripts/trading_bot/exo0823_{fetch,sweep,diag,exec}.py`.
Results `INVENT_0823_exotic{,_DESIGN,_DIAG,_EXEC}.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

Four families, all chosen because a third party publishes the tether rather than because a
statistic looked promising: **same-coin ETP wrappers** (11 spot-bitcoin and 8 spot-ether funds
holding the identical physical asset), **currency-hedged sibling ETFs** (the hedged fund
literally holds the unhedged one plus a forward, so `r_unhedged = r_hedged + r_FX + carry` is
an identity), **the leveraged/inverse complex** (the prospectus promises `m ×` the base's daily
return, making the k-day NAV path deterministic), and **iShares Core fund-of-funds** (published
holdings at published weights). Twenty of the 29 formulas are spread-reversion structures on
those tethers and **every one of them is dead** — the best design gross Sharpe among them is
1.01 against a size-matched bar of 1.07, and it collapses to 0.09 the moment execution is
moved from one clock to another. The nine that are not searched — static carries whose sign
*and magnitude* were fixed in advance by a prospectus number — behave completely differently:
**the GBTC-vs-cheap-wrapper spread drifted +1.268 %/yr out of sample against a published fee gap
of 1.267 %/yr (t vs published = 0.002)**, and the leveraged-fund decay carry is positive,
beta-neutral and near its predicted magnitude in both windows. Neither clears the round's
multiple-testing bar once the financing and borrow the price series does not contain are
charged, and neither is big enough to matter: ~0.45 %/yr and ~0.5 %/yr of gross notional. The
verdict is the programme's familiar one in a new place — **the signal is real and it is smaller
than the frictions that stand in front of it** — plus one methodological result that is worth
more than any of the formulas.

---

## 1. WHY THESE FOUR FAMILIES, AND WHY THEY ARE NOT A RE-RUN

The dead ledger forbids re-proposing the CEF corporate-action layer (`INVENT_0822C`, 114
formulas: distributions, EDGAR form types, rights offerings, NAV erosion — all zero), preferred
RV, futures roll, auction imbalance, forced flow, conditioning, and the 27 crypto-perp exotics
of `INVENT_R3`. `DEEPMINE_etf_structural_rv` already spent 51 formulas on intraday ETF
structural RV, including 9 on the levered complex.

| family | n | the published tether | why it is new to the programme |
|---|---:|---|---|
| **C · same-coin ETP wrappers** | 10 | each sponsor publishes coins-per-share daily; two funds on the same coin are tethered exactly up to the fee gap | **No US spot-crypto ETP has ever appeared in this repo.** `grep` for IBIT/FBTC/GBTC/BITB/ARKB across `research/` and `scripts/` returns nothing but a borrow-flag row. `INVENT_0822_crypto_tether` traded *tokens on crypto venues* (wBTC, XAUT/PAXG) — different venue, different clock, different wrapper. |
| **H · currency-hedged sibling** | 6 | the hedged iShares/Xtrackers fund **holds the unhedged sibling** plus a rolling forward | Never tested. And the FX leg is taken from a **US-listed currency ETF** (FXE/FXY/FXB), so all three legs of the triangle print on the same 16:00 ET clock — the FX-close timing mismatch that would otherwise dominate is removed by construction, not assumed away. |
| **L · leveraged / inverse complex** | 7 | the prospectus daily-leverage mandate | `DEEPMINE`'s group L was **5-minute intraday, close-rebalance flow**. This is the *daily* path residual and the *static* decay carry, at 1/40th the turnover — the escape route from that round's "entirely inside the half-spread" wall. |
| **F · fund-of-funds** | 5 | AOA/AOR/AOM/AOK publish their iShares holdings and target weights | Never tested. |
| *placebos* | 2 | — | fund-identity permutation, fixed through time (the `INVENT_0822C` construction) |
| *controls* | 2 | — | long SPY; the SPY/IVV sibling pair |

Explicitly **not** proposed: SPAC-trust NAV (the trust value per share is not free without a
filings pipeline, and the 2026 universe is too thin), PFF-vs-holdings (preferred RV is dead:
borrow-walled and insignificant), CEF rights offerings (`INVENT_0822C` §7c, weak-label, gross
|t| 1.42, dead), gold/silver sibling RV (that is `rv_sweep`'s L2).

---

## 2. DATA, WINDOWS, EXECUTION, COST

**Data.** Alpaca daily bars, `adjustment=all`, 88 symbols + BIL/SHV, 2016-01-04 → 2026-08-20,
cached to `research/data/exo0823_cache`. Total-return adjustment is the correct choice here
because every tether identity in this round must hold on **total** returns — EZU pays a large
dividend and FXE pays none, so a price-return triangle would be a systematic lie. Delisted
funds are kept (`HEWU` dies 2023-10, `DBGR` 2024-03); the panel masks them out rather than
dropping them from history, so the family is not survivorship-flattered.

**Windows.** Long-history families H/L/F: design **2016-01-05 → 2023-12-29** (2 010 sessions),
held out **2024-01-02 → 2026-08-20** (660). Coin family C: design **2024-01-16 → 2025-06-30**
(364 sessions — the wrappers did not exist before 2024-01-11), held out **2025-07-01 →
2026-08-20** (286). The held-out block was written as the literal string `"SEALED"` in
`INVENT_0823_exotic_DESIGN.json` and every selection below was made against that file.

**Execution, and this is the round's most consequential choice.** A signal is formed from data
through the **close of day t−1**, the book is executed at the **open of day t**, and it earns
**open t → open t+1**. A closing-print bid-ask bounce in the signal therefore cannot pay
itself: by the time you trade, the bounce has already reverted in the opening auction. Two
other clocks are reported for every formula:

* `close_lag` — same signal, executed at the close of t, earning close t → close t+1;
* `close_same` — the signal formed at close t earns close t → close t+1. **This is the
  contaminated construction** and it is reported only to size the bounce.

**Cost.** Half-spread per symbol from **Corwin–Schultz (2012) on the same daily high/low bars
the backtest trades** — measured, not assumed. The median daily estimate is ≤ 0 for every ETF
in this universe (their true daily ranges are dominated by real price movement, not by the
spread), so every symbol floors at **1.0 bp half-spread**, charged at **×1.5 for an opening
print** and shocked **×2**. SEC §31 0.278 bp on sale notional. This is a *generous* cost
model and it is deliberately so: nothing in this round dies of cost alone, so no result can be
argued away as a cost artefact.

**Financing and borrow — the correction that decides the round.** A price-return backtest of a
book with a non-zero net cash position **is not a return**. `L7` holds +0.43 of gross in net
cash; its raw P&L therefore quietly contains the bill rate. Every static structure is
re-stated as an **excess-of-cash** return: net cash weight charged at **BIL total return** (a
free, published overnight-bill proxy), short weight charged at three borrow rates from
`B22G_BORROW_COST.json` — **0.33 %/yr** (this programme's own measured ETB general-collateral
median), 1 %/yr, and 3 %/yr.

**Executability is measured, not assumed.** A live per-symbol `GET /v2/assets` snapshot from the
account this programme would trade in (`research/data/exo0823_cache/alpaca_assets_flags.json`,
read-only endpoint, no order path touched) gives the `shortable`/`easy_to_borrow` flag for all
70 symbols that appear on a short leg. Its verdict is in §6 and it is brutal for two of the
four families.

---

## 3. THE GATES AND THE BARS, FIXED BEFORE THE REVEAL

### 3a. ρ1 bounce gate — reported first, as the standing rule requires

ρ1 of the **daily change** in each family's tether residual, pooled:

| family | n residuals | median ρ1 | p10 | p90 | verdict |
|---|---:|---:|---:|---:|---|
| L · levered path residual | 28 | **−0.329** | −0.526 | −0.072 | passes (> −0.35), barely |
| F · fund-of-funds residual | 4 | **−0.355** | −0.362 | −0.340 | borderline fail |
| H · FX-hedged triangle | 8 | **−0.417** | −0.443 | −0.400 | **fails** |
| C · BTC wrapper residual | 10 | **−0.470** | −0.525 | −0.403 | **fails** |
| C · ETH wrapper residual | 7 | **−0.538** | −0.563 | −0.479 | **fails badly** |

Read this the way the programme has learned to: **a residual with ρ1 ≈ −0.5 is a closing-print
bounce and any reversion Sharpe measured on it is an artefact.** The gate is the right
instrument for the 20 spread-reversion formulas and it condemns families C and H in advance.
It is **not** the right instrument for a zero-turnover static carry, which has no timing to
exploit and cannot harvest a bounce; the gate is therefore not applied to `C7`–`C9`, `L7`, `L8`
or `F5`, and that exemption is stated here rather than discovered later.

### 3b. The noise bar

Size-matched placebo: sign-flip block bootstrap, 10-day blocks, 2 000 replicates, **the maximum
over all formulas re-scored every replicate** with the same block signs across formulas so their
cross-correlation survives into the null.

| | long-history families (n = 19) | coin family (n = 10) |
|---|---:|---:|
| E[max \|Sharpe\|] | 0.715 | 1.221 |
| p95 of max | **1.069** | **2.044** |
| p99 | 1.252 | 2.635 |
| 1 SE of an annualised Sharpe on that window | 0.354 | 0.832 |
| analytic `sqrt(2 ln 2N)` = 2.850 SE, N = 29 | **1.009** | **2.371** |
| **operative bar (larger of the two)** | **1.069** | **2.371** |

Programme-cumulative after this round: ≈ **1 460** distinct formulas,
`sqrt(2 ln 2N)` = 3.99 SE ≈ **1.41 Sharpe** on the long window.

### 3c. Decision rule, fixed before the reveal

A formula is put forward only if, **on the design window**: its **gross** Sharpe clears the
operative bar; it survives the `close_lag` execution change; its **excess-of-cash** number at
the B22G ETB borrow rate is still positive; and every short leg is `shortable` on the live
broker snapshot. The held-out block then confirms or kills.

---

## 4. THE DESIGN RESULT — nothing clears, and the reason is not cost

All 29 scored formulas plus placebos and controls, sorted by design gross Sharpe.
`Dgr/Dnet` design gross/net, `Dclag` design gross under close-lag execution, **`Dcont` design
gross under the CONTAMINATED same-close clock**, `Hgr/Hnet` held out, `Hclag` held-out close-lag.

| formula | fam | Dgr | Dnet | Dclag | **Dcont** | Hgr | Hnet | Hshk | Hclag |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| L7_lev_decay_carry | L | **1.23** | 1.23 | 1.10 | 1.10 | 5.94 | 5.94 | 5.94 | 8.52 |
| C9_feecarry_pooled | C | 1.06 | 1.03 | 1.79 | 1.81 | 1.05 | 1.05 | 1.05 | 2.06 |
| F4_fof_z20_H1 | F | 1.01 | −0.59 | **0.09** | 4.04 | 0.49 | −1.65 | −3.54 | 0.87 |
| *CTRL_LONG_SPY* | *ctrl* | *0.81* | *0.81* | *0.78* | *0.78* | *1.30* | *1.30* | *1.30* | *1.31* |
| H4_tri_d5_H5 | H | 0.70 | −0.66 | 0.62 | 2.92 | −0.34 | −1.65 | −2.85 | −1.20 |
| H6_tri_xs_z20_H5 | H | 0.68 | −0.80 | 0.62 | 3.55 | 0.35 | −0.78 | −1.81 | 0.23 |
| C8_feecarry_eth | C | 0.62 | 0.60 | 1.34 | 1.34 | 0.61 | 0.61 | 0.61 | 1.13 |
| L8_bullbear_shortboth | L | 0.61 | 0.61 | 0.57 | 0.65 | **−1.39** | −1.39 | −1.39 | −4.48 |
| H3_tri_z20_H1 | H | 0.57 | −3.10 | 0.71 | **7.92** | −0.47 | −2.39 | −4.12 | −1.75 |
| L1_lev_te_z20_H1 | L | 0.54 | −5.14 | −0.11 | 3.37 | 1.96 | −16.70 | −32.80 | 1.18 |
| F5_fof_fee_carry | F | 0.44 | 0.44 | 0.57 | 0.57 | 0.48 | 0.48 | 0.48 | 0.65 |
| F3_fof_d5_H5 | F | 0.36 | −0.63 | 0.17 | 1.27 | 0.73 | −0.66 | −1.94 | 0.75 |
| C6_coin_z20_rev_H1 | C | 0.36 | −7.81 | −2.62 | **22.57** | −1.42 | −8.52 | −14.84 | 0.22 |
| H1_tri_z20_H5 | H | 0.25 | −1.05 | 0.14 | 3.50 | −0.57 | −1.06 | −1.51 | −2.06 |
| F1_fof_z20_H5 | F | 0.11 | −0.40 | −0.04 | 0.91 | 0.35 | −0.41 | −1.10 | 0.39 |
| H5_tri_clean_z20_H5 | H | 0.10 | −1.02 | −0.04 | 2.62 | −0.45 | −0.74 | −1.00 | −2.21 |
| F2_fof_z60_H5 | F | 0.09 | −0.23 | 0.13 | 0.77 | 0.10 | −0.28 | −0.63 | 0.19 |
| C7_feecarry_btc | C | 0.03 | 0.03 | 0.53 | 0.53 | 1.35 | 1.35 | 1.35 | 2.25 |
| L4_lev_xs_H5 | L | 0.02 | −0.84 | −0.04 | 0.76 | 2.09 | −1.38 | −4.54 | 1.56 |
| *CTRL_SPY_IVV_z20_H5* | *ctrl* | *−0.07* | *−6.39* | *−0.06* | *0.59* | *−0.50* | *−12.35* | *−13.99* | *0.74* |
| H2_tri_z60_H5 | H | −0.08 | −0.90 | −0.20 | 2.29 | −0.77 | −0.96 | −1.13 | −2.36 |
| C1_coin_z20_rev_H5 | C | −0.11 | −3.10 | −0.93 | 7.20 | −0.83 | −3.64 | −6.20 | −0.34 |
| C4_coin_d5_rev_H5 | C | −0.12 | −4.75 | −0.65 | 6.43 | −0.44 | −3.98 | −7.22 | 0.63 |
| L5_levbull_d20z60_H5 | L | −0.15 | −0.81 | 0.05 | 0.45 | 1.24 | −2.77 | −6.39 | 1.04 |
| C10_coin_cheapest3_vs_group_H5 | C | −0.16 | −3.08 | −1.03 | 6.35 | −0.73 | −3.13 | −5.30 | −0.56 |
| L2_lev_d5_H5 | L | −0.16 | −0.47 | −0.05 | −0.01 | −10.48 | −12.07 | −13.51 | −12.55 |
| **PLACEBO_C_idperm** | *plc* | **−0.16** | −3.74 | −0.15 | **−0.09** | −0.98 | −3.58 | −5.95 | 0.12 |
| **PLACEBO_L_idperm** | *plc* | **−0.36** | −1.35 | −0.41 | **−0.34** | −0.46 | −5.74 | −10.52 | −0.11 |
| L3_lev_d20z60_H5 | L | −0.39 | −1.13 | −0.04 | 0.58 | 2.22 | −0.94 | −3.81 | 1.65 |
| C2_coin_z60_rev_H5 | C | −0.62 | −2.74 | −1.22 | 4.67 | −0.92 | −3.18 | −5.23 | −0.83 |
| L6_bullbear_parity_z20_H5 | L | −0.67 | −0.74 | −0.70 | −0.45 | 1.20 | 1.04 | 0.89 | 3.57 |
| C3_coin_d1_rev_H1 | C | −0.85 | −10.45 | −1.85 | **21.45** | 0.12 | −8.70 | −16.63 | 1.14 |
| C5_coin_d20_rev_H20 | C | −0.96 | −1.90 | −1.17 | 0.54 | −1.22 | −2.33 | −3.36 | −1.58 |

**Under the pre-registered rule: zero formulas survive.**

* `L7` (1.23) is the only book above the 1.069 long-history bar — but its gross number is not a
  return (§5).
* `C9` (1.06) is nowhere near the 2.371 coin bar.
* `F4` (1.01) does not reach the bar, is −0.59 net, and **collapses to 0.09 gross when execution
  moves from the open to the close**. A structure whose entire edge lives in one 24-hour window
  and vanishes in the adjacent one is a clock artefact, not an edge.

  The obvious suspect — a **stale opening print** in the thin AOx funds, which would let a
  close-formed signal "predict" a return it has already seen — was measured and **acquitted**.
  Across all 90 symbols, `open[t]` literally equals `close[t−1]` on 0.6–5.3 % of days, and the
  correlation of the overnight gap `C[t−1]→O[t]` with the *previous* non-overlapping
  close-to-close return is **negative everywhere** (median |ρ| 0.062; AOR −0.122, AOK −0.068,
  SPY −0.084). Staleness would show up as a large **positive** correlation. What is there is
  ordinary overnight gap reversal, which is the same sign and size for SPY as for AOK. So the
  open-execution clock is clean, and `F4` has no mechanism at all —
  `stale_open_diagnostic` in the result JSON.

---

## 5. THE ROUND'S METHODOLOGICAL RESULT: what a bounce is worth, measured

Compare the `Dcont` column with `Dgr`. Identical books, identical signals; the only difference
is whether the signal's own closing print is allowed to pay for itself.

| formula | honest (open exec) | **contaminated (same close)** | inflation |
|---|---:|---:|---:|
| C6_coin_z20_rev_H1 | +0.36 | **+22.57** | ×63 |
| C3_coin_d1_rev_H1 | −0.85 | **+21.45** | sign flip, ×25 in magnitude |
| H3_tri_z20_H1 | +0.57 | +7.92 | ×14 |
| C1_coin_z20_rev_H5 | −0.11 | +7.20 | sign flip |
| C4_coin_d5_rev_H5 | −0.12 | +6.43 | sign flip |
| C10_coin_cheapest3_vs_group | −0.16 | +6.35 | sign flip |
| F4_fof_z20_H1 | +1.01 | +4.04 | ×4 |
| L1_lev_te_z20_H1 | +0.54 | +3.37 | ×6 |
| **PLACEBO_C_idperm** | **−0.16** | **−0.09** | **none** |
| **PLACEBO_L_idperm** | **−0.36** | **−0.34** | **none** |

The two identity-permutation placebos — same books, same turnover, same screens, only the
instrument↔return link destroyed — are **completely inert under the contaminated clock**. So
the ×63 is not the machinery and it is not the multiple testing: it is the bid-ask bounce in
the tether residual, exactly as ρ1 = −0.47 predicted. A Sharpe of 22 on a bitcoin-ETF pair book
is *available to anyone who backtests a close-formed signal against a close-to-close return*,
and it is worth nothing. **Inside a tethered family, a high gross Sharpe is evidence against
the formula** — this round puts a number on how much.

---

## 6. EXECUTABILITY, MEASURED — and it kills two families outright

Live `GET /v2/assets` snapshot, 2026-08-23, from the account this programme would trade in.

| short leg needed by | symbols **not shortable today** | consequence |
|---|---|---|
| **H (all 6 formulas)** | HEZU, HEWG, DBJP, EWG, EWU, **FXE, FXY, FXB, FXC** | **the FX-hedged triangle cannot be traded at all.** Every currency-ETF leg and most hedged siblings are unshortable. Family H is dead on execution independently of its zero signal. |
| **L8 (short both sides)** | SH, SDS, SPXU, SPXS, QID, SQQQ, TWM, TZA, TMV, GLL, DUST, SOXS, FAZ | **13 of the 14 inverse ETFs in the universe are unshortable** (only PSQ is not). `L8` is unimplementable. |
| L7 (short bull LETFs) | TNA, SOXL, ERX | 10 of 13 remain; re-run in §7. |
| F (AOx short leg) | AOK | minor. |
| **C7/C8/C9** | *none* — **GBTC and ETHE are both `shortable: true, easy_to_borrow: true`** | the fee-carry short leg **is** executable, at the B22G ETB rate of 0.33 %/yr. |

This corroborates `DEEPMINE_etf_structural_rv`'s note that the leveraged/inverse wall is a
**broker product restriction**, not borrow scarcity — and extends it: the same broker will not
lend currency ETFs or thin hedged-equity ETFs either.

---

## 7. THE TWO NON-SEARCHED MECHANISM CARRIES

These are not formulas in the search sense. Their sign **and their magnitude** were fixed in
advance by a number in a prospectus, so the right test is not "does it beat a max-of-N bar" but
**"does the realised drift equal the published number?"**. Both are reported with the search
bar anyway, and both fail it.

### 7a. The published-fee tether: GBTC / ETHE versus their cheap siblings

Grayscale charges **1.50 %/yr** on GBTC and **2.50 %/yr** on ETHE. Every competing wrapper on
the identical coin charges ≤ 0.25 %. Two funds holding the same physical asset **must** diverge
at the fee gap. Headline prospectus rates are used, never the launch waivers, which makes the
prediction a **lower bound** (every waiver in the window widened the real gap).

| | published gap | design realised | design t vs published | **held-out realised** | **held-out t vs published** | held-out t vs 0 | spread vol |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BTC** (GBTC vs 9 wrappers) | **1.267 %/yr** | +0.350 %/yr | −1.00 | **+1.268 %/yr** | **+0.002** | 2.39 | 0.57 %/yr |
| **ETH** (ETHE vs 6 wrappers) | **2.260 %/yr** | +2.370 %/yr | +0.07 | +1.083 %/yr | −1.24 | 1.14 | 1.01 %/yr |

The BTC line is the sharpest confirmation of the programme's central thesis on record: a
relationship whose value is *published by a third party* delivered **1.268 %/yr against a
predicted 1.267 %/yr** on a window that was sealed when the prediction was written. The design
shortfall (0.35 vs 1.27) is the residual convergence of GBTC's own discount through 2024, and
it reverses to an exact hit once that is done. The tether is also extremely tight: the
cheap-basket-vs-GBTC spread has an annualised vol of **0.57 %**.

**And it is still not a trade worth having.** As a book (`C9_feecarry_pooled`: long a 0.25
equal-weight basket of low-fee BTC wrappers + 0.25 of low-fee ETH wrappers, short 0.25 GBTC +
0.25 ETHE, static, turnover 0.003/day):

| | design | held out |
|---|---:|---:|
| raw net Sharpe | 1.03 | 1.05 |
| excess-of-cash Sharpe @ ETB 0.33 %/yr borrow | **0.80** (+0.37 %/yr, t 0.96) | **0.77** (+0.45 %/yr, t 0.82) |
| @ 1 %/yr borrow | 0.33 | 0.20 |
| @ 3 %/yr borrow | −1.07 | −1.51 |
| beta to SPY | +0.003 (t 2.4) | −0.003 (t −1.1) |
| beta to IBIT / ETHA | +0.000 / +0.000 | +0.000 / +0.000 |
| held-out worst day / max drawdown | — | −10.9 bp / 14.5 bp of gross |

It is perfectly coin-neutral and equity-neutral, the tail is trivial, and it earns **0.45 %/yr
of gross notional**. Against the coin-family bar of 2.371 it is not close; its own t is under 1
on a 2.6-year sample that cannot be extended backwards because the instruments did not exist.
**Not promoted.** Three further hazards are named: the fee gap is a number the sponsor may cut
at will (benign — the edge vanishes, it does not reverse); GBTC and ETHE are in permanent
outflow and may be wound up; and the ETB flag is a snapshot, not a term sheet.

### 7b. The leveraged-fund decay carry

Long `m` units of the base, short one unit of the levered fund. The prospectus daily-leverage
mandate makes this delta-neutral by construction; it collects the fund's expense ratio
(mean 0.94 %/yr across the complex) and the spread between the fund's financing and yours.
**Predicted magnitude from the published fees alone: ≈ 0.27 %/yr of gross, ≈ 0.44 %/yr once the
fund's financing spread is included.**

`L7` as pre-declared (13 bull funds pooled): design raw Sharpe **1.23**, held out **5.94** —
and both numbers are inflated by the book's +0.43 net cash weight, which the price series
silently pays at the bill rate. Corrected:

| `L7` pooled | design | held out |
|---|---:|---:|
| raw net Sharpe | 1.23 | 5.94 |
| **excess-of-cash @ ETB borrow** | **0.61** (+0.67 %/yr) | **1.34** (+0.58 %/yr) |
| @ 1 %/yr borrow | 0.44 | 0.90 |
| @ 3 %/yr borrow | −0.07 | −0.41 |
| beta to SPY | −0.005 (t −3.5) | +0.002 (t +2.2) |
| worst day / max drawdown (of gross) | −124 bp / 361 bp | −23 bp / 46 bp |

Restricted to the **10 bull funds that are actually shortable today**, and decomposed:

| book | design excess @ETB | design t | held-out excess @ETB | held-out t |
|---|---:|---:|---:|---:|
| **L7_exec (10 funds pooled)** | **+0.27 %/yr** | **0.63** | **+0.51 %/yr** | **2.35** |
| SSO (2× S&P) | +0.50 %/yr | 3.88 | +0.41 %/yr | 3.10 |
| QLD (2× NDX) | +0.57 %/yr | 3.89 | +0.42 %/yr | 2.23 |
| UPRO (3× S&P) | +0.81 %/yr | 3.43 | +0.45 %/yr | 1.86 |
| SPXL (3× S&P) | +0.80 %/yr | 3.09 | +0.41 %/yr | 1.72 |
| TQQQ (3× NDX) | +0.87 %/yr | 3.19 | +0.56 %/yr | 1.62 |
| TMF (3× TLT) | +0.50 %/yr | 1.95 | +0.63 %/yr | 3.19 |
| UWM / UGL | +0.55 / +0.76 | 1.68 / 1.62 | +0.27 / +0.86 | 0.88 / 1.28 |
| NUGT / FAS (sector & commodity) | **−1.73 / −1.13** | −0.48 / −0.48 | +0.72 / +0.36 | 0.65 / 0.50 |

Six broad-index LETFs are positive in **both** windows at 0.4–0.9 %/yr with design t of 1.9–3.9;
the sector and commodity LETFs are noise and are what drags the pooled design number to 0.63.
**That subset was identified after the design window was read, so the held-out numbers in those
rows are not virgin for that choice** — stated, not smoothed over.

**Verdict: real mechanism, sub-bar size.** The pooled, executable, correctly-financed design
statistic is 0.22 Sharpe (t 0.63) against a 1.069 bar. It is not promoted. What it is, is a
**forward-test lead**: a mechanically-guaranteed, beta-neutral cash flow of roughly half a
percent a year on gross notional, whose realised size (0.4–0.9 %/yr) sits right on top of the
0.44 %/yr the published fees predict — the second independent confirmation in this round that
a *published* number prices a *claim*.

### 7c. And one that is pure beta — the value of the diagnostic

`F5_fof_fee_carry` (long the published AOx replication basket, short the wrapper) posts design
0.44 / held-out 0.48 and looks like a third carry. It is not: **beta to SPY +0.049, t = 36.4,
alpha −0.03 bp/day (t −0.2)**. The published target weights I used are simply not the fund's
actual weights, and the residual equity exposure is the entire "edge". `L8_bullbear_shortboth`
is the same story with a worse ending: SPY beta +0.024 (t 6.0), held-out alpha −1.27 bp/day
(t −2.5), held-out Sharpe **−1.39** — short-both-sides of a levered pair is long variance and
short trend, and 2024–2026 was a trend. Both are dead, and the beta regression is what
separates them from `L7`/`C9`, whose betas are ≈ 0 in both windows.

---

## 8. WHAT THIS ADDS TO THE LEDGER

**Dead — searched and found to be noise on free daily data, 2016–2026:**

1. **Same-coin ETP wrapper cross-section** (BTC and ETH spot ETPs): residual z-score reversion at
   20 d and 60 d, 1/5/20-day residual return reversal, and the long-only cheapest-three tilt.
   Six formulas, all negative or trivial honestly-executed, all spectacular under a contaminated
   clock. ρ1 of the wrapper residual is −0.47 (BTC) / −0.54 (ETH): the family is bounce.
2. **Currency-hedged sibling triangles** (`r_unhedged = r_hedged + r_FX`), including the
   same-clock US-listed FX leg that removes the timing mismatch: six formulas, best held-out net
   −0.78, ρ1 −0.42, **and unshortable at the broker**. Closed twice over.
3. **Leveraged-complex path residual at daily horizon** — daily tracking-error z, 5-day and
   20-day anchored residuals, the cross-sectional version, the bull-only version, and bull/bear
   parity. Six formulas; the one with a positive held-out gross (`L3`, `L4`) is net −0.94/−1.38.
   `DEEPMINE`'s intraday verdict survives the move to daily.
4. **Fund-of-funds published-weight replication residual** (AOA/AOR/AOM/AOK): four formulas,
   best held-out net −0.28, and the apparent static carry is an equity beta with t = 36.
5. **Bull/bear short-both decay harvest**: design +0.61 → held out **−1.39**, and unimplementable
   anyway because every inverse ETF is unshortable.

**Not dead, not promoted — two mechanism carries and one lead:**

6. **Published-fee-gap carry between wrappers on the same physical asset** (GBTC/ETHE vs the
   cheap complex). Confirmed out of sample at the published magnitude to three decimal places
   on the BTC leg. Coin-neutral, equity-neutral, executable at ETB, tiny tail — and **0.45 %/yr
   of gross notional at t < 1**. Revisit only when the sample is 5 years, or on a wrapper pair
   with a wider gap.
7. **Leveraged-fund decay carry** (long `m ×` base, short the fund). Positive in both windows on
   the broad-index funds at 0.4–0.9 %/yr, beta-neutral, magnitude matching the published fees.
   Sub-bar pooled; the best available **forward-test lead** in this round.

**Methodological, and the most transferable thing here:**

8. **A same-close backtest of a tether residual inflates the Sharpe by up to ×63, and an
   identity-permutation placebo does not move at all.** The programme's rule "inside a tethered
   family a high gross Sharpe is evidence against" now has a measured coefficient. The cheap
   defence is not a better cost model — it is **moving execution off the signal's own print**,
   which costs nothing and removed the entire artefact here.
9. **A price-return backtest of a book with a non-zero net cash position is not a return.**
   `L7`'s headline fell 1.23 → 0.61 and `F5` was revealed as pure beta once the bill rate and
   the borrow were charged. Any future static-carry structure must be stated excess-of-cash
   before it is compared to anything.
10. **The broker product restriction is wider than believed.** Not just leveraged/inverse ETPs:
    currency ETFs (FXE/FXY/FXB/FXC) and thin hedged-equity ETFs (HEZU/HEWG/DBJP) are also
    unshortable at this programme's broker. Any future RV idea whose short leg is a niche ETF
    should be screened against `/v2/assets` **before** a formula is written, not after.
