# DEEPMINE `etf_structural_rv` — ETF structural relative value, beyond same-index siblings

## VERDICT: the sub-family is NOISE as a tradable claim — 0 of 51 formulas has a positive net Sharpe, on the design window or held out

And the *reason* is the finding, not the verdict. The signal is **not** absent. Forty-two of the
fifty-one formulas have a positive **before-cost** Sharpe; the best is **+2.93**, against a
before-cost block-bootstrap noise bar of **1.48** at p95. ETF structural mispricing at five-minute
resolution is real, it clearly beats the multiple-testing bar, and **it is entirely inside the
half-spread.** Forty-five of the fifty-one formulas would still lose money at a *literally zero*
spread, because at their turnover the SEC §31 and FINRA TAF pass-throughs alone exceed the gross
edge. This family does not need better execution. It needs a different business.

Pre-registration: `DEEPMINE_etf_structural_rv_PREREGISTRATION.md`,
sha256 `1a141a67ae5e30102a51aeaaa00dede7a75f3310be227b67bbf6c0feb217f468`, written and hashed
**before `--stage design` produced a number**. `deepmine_shortlist.py` refuses to run against any
other hash.

---

## 1. What was searched — 51 formulas across five structurally different claims

Same-index siblings (SPY/IVV/VOO, XLK/VGT, GLD/IAU …) are **excluded**: that is `rv_sweep.py`'s
leg and the basket's L2. Everything here is a *different object*.

| grp | claim | n | design best gross | design median gross | design best net | median turn/day |
|---|---|---:|---:|---:|---:|---:|
| **N** | ETF vs the sum of its own components (the free stand-in for iNAV) | 18 | **+2.46** | +0.71 | −5.06 | 8.5 |
| **O** | overlapping-holdings pairs across **different** indices, rolling hedge ratio | 12 | **+2.93** | **+1.53** | −8.82 | 11.2 |
| **L** | leveraged/inverse decay carry, and the levered complex's close rebalance | 9 | +0.93 | +0.18 | **−1.00** | 2.0 |
| **C** | country ETF vs a NAV whose local market shut hours ago | 7 | +2.08 | +0.30 | −1.57 | 2.5 |
| **P** | premium/discount as a **signal**, traded ETF-only or component-only | 5 | +0.54 | +0.02 | −2.87 | 6.0 |

The axes varied inside those groups: basket weighting (equal / ADV-proportional / top-3-by-ADV),
spread measure (log-level z, beta-hedged cumulative residual, session-open-anchored deviation,
EWMA z), z-window (78 / 390 / 1170 bars, EWMA half-life 78), hedge ratio (unit vs rolling OLS beta,
two beta windows), entry rule (continuous, |z| threshold, two no-trade bands), holding period
(every bar vs a 13-bar refresh), conditioners (AR(1) half-life gate, session-open exclusion,
risk-parity sizing), horizon (intraday-flat vs held through the close into the next open), and
which side of the claim is traded (the ETF, the components, or both).

## 2. The full result distribution, and the noise bar it has to clear

Design window **2021-01-04 → 2024-12-31**, 1 005 sessions (3.99 years), 78 375 five-minute bars,
132 symbols.

**Expected max under the null.** N = 51 → `sqrt(2 ln 51)` = **2.80 SE**. One SE of an annualised
Sharpe over 3.99 years is `1/sqrt(3.99)` = 0.501, so the naive bar is **1.40 in Sharpe units**.
The block bootstrap — stationary, block = 5 days, 800 resamples of the *demeaned* daily net PnL,
the **same** day indices across all 51 configs so their cross-correlation is preserved — puts the
max at mean **1.07**, p95 **1.61**, p99 **1.85**. The bootstrap bar sits *above* the naive one
even though the configs are correlated (mean pairwise correlation of daily net PnL 0.13,
participation ratio ≈ 11.6 effective independent bets), because daily RV PnL is fat-tailed and
autocorrelated and the naive formula assumes neither.

| statistic | before cost | **net (headline cost model)** | flat 1.0 bp | flat 2.5 bp |
|---|---:|---:|---:|---:|
| max | **+2.93** | **−1.00** | −0.33 | −1.30 |
| p90 | +1.96 | −1.61 | −1.12 | −2.20 |
| p75 | +1.07 | −5.71 | −4.08 | −9.07 |
| median | +0.63 | −13.93 | −7.81 | −17.67 |
| p25 | +0.15 | −27.31 | −19.77 | −38.76 |
| min | −1.13 | −66.27 | −54.66 | −85.22 |
| **n positive** | **42 / 51** | **0 / 51** | 0 / 51 | 0 / 51 |

The before-cost max of **+2.93** clears the before-cost bootstrap bar of 1.48 comfortably. The net
max of **−1.00** does not come within three Sharpe of the net bar of 1.61. Nothing passed §5's
gates, so §5's floor carried the top three by design net Sharpe to the held-out window anyway,
labelled **BELOW THE NOISE BAR** — running them was not a promotion.

## 3. Held out — read once, after the shortlist was on disk

Held-out window **2025-01-02 → 2026-08-15**, 405 sessions.

| formula | design gross | design net | **held-out gross** | **held-out net** | turn/day | short notional this broker won't lend |
|---|---:|---:|---:|---:|---:|---:|
| `L07_rebal_flow_fade_nextopen` | +0.84 | −1.00 | **+1.63** | **−0.19** | 2.0 | 0 % |
| `L09_rebal_flow_cont_overnight` | +0.25 | −1.12 | +0.79 | −0.16 | 2.0 | 0 % |
| `L02_decay_pair_short_both` | +0.13 | −1.26 | −0.71 | −1.31 | 0.2 | **42 %** |

`L07` is the only formula in the family that gets close: fade the levered-ETF complex's
close-rebalance flow, cross-sectionally across ten index/sector ETFs, put on at the next open.
Its before-cost Sharpe **doubled** out of sample (+0.84 → +1.63) and it needs spreads only **1.1×
tighter** than it was charged to break even. It is still **negative net on both windows**, so by
§6 it is not REAL, and it is reported here because the pre-registration says a near miss is
reported as a near miss rather than rounded up.

## 4. Why it dies — the number that makes this a structural finding

A market-neutral ETF-structural book normalised to one unit of gross exposure has an annualised
volatility of **1.2 % – 2.0 %**. These spreads barely move. The consequence:

| formula | gross earned | cost paid | cost ÷ gross | what would have to change |
|---|---:|---:|---:|---|
| `O01_overlap_beta_z78` (best gross) | 1.83 bp/day | 37.7 bp/day | **×20.6** | even a ZERO spread loses: fees alone > edge |
| `N01_synth_eq_lvl_z78` | 1.65 bp/day | 28.0 bp/day | ×17.0 | even a ZERO spread loses |
| `C06_country_xs_rev_lb6` | 4.77 bp/day | 136.6 bp/day | ×28.6 | even a ZERO spread loses |
| `O05_overlap_beta_band_2.0_0.5` | 1.18 bp/day | 9.4 bp/day | ×7.9 | spreads 25× tighter |
| `L07_rebal_flow_fade_nextopen` | 1.65 bp/day | 3.6 bp/day | ×2.2 | spreads 2.5× tighter (1.1× held out) |

**45 of 51 formulas lose at a literally zero spread.** That is the sentence worth keeping. The
edge is a bp or two a day on a book that has to be rewritten ten to twenty times a session; SEC
§31 plus FINRA TAF, at 0.15 bp per unit of turnover, is on its own larger than the whole gross
edge for most of the family. Tighter fills, a better broker, a smarter order type — none of them
reach.

The one degree of freedom that *does* move the answer is turnover, and the family's own ranking
proves it: **the top four formulas by net Sharpe are the four with the lowest turnover**, and they
are the ones whose gross signal is weakest. Slowing the rule down keeps the cost but throws away
the edge, because the deviations mean-revert in minutes.

## 5. Cost model, and the sensitivity that shows the verdict does not depend on it

**Headline**: every unit of turnover is charged at that symbol's own half-spread,
`max(1.0 bp, 2 × (half a cent / price))` — provenance
`TICK_FLOOR_TIMES_ADVERSITY_NOT_A_QUOTE_MEASUREMENT`, from `deepmine_spread_calib.py`. Both legs
pay. Plus 0.15 bp/turnover of SEC §31 + FINRA TAF on every rung. Plus, for the configs that hold
through the close, borrow at B22G's measured ETB general-collateral median **0.33 %/yr on short
notional per calendar day**. Intraday-flat configs pay zero borrow, and that is a claim with a
reason: US borrow fees accrue overnight.

The 1.0 bp floor is generous *against* the strategy for the tightest legs — SPY's true half-spread
is nearer 0.08 bp — so the verdict was re-run against the **arithmetic lower bound**: the raw
half-tick, no adversity multiplier, no floor. That is not a realistic fill; it is the number you
would get if every order always rested at a one-cent-wide touch, and no execution can beat it.

Twelve formulas — the lowest-turnover one from each group plus all three shortlisted — were re-run
on both windows at that bound (`*_tickfloor.json`). **The verdict survives it**, and one result
inside it is the most useful thing this run produced:

| formula | design net, headline | design net, **tick-floor bound** | held-out net, headline | held-out net, **tick-floor bound** |
|---|---:|---:|---:|---:|
| `L07_rebal_flow_fade_nextopen` | −1.00 | **−0.07** | −0.19 | **+0.74** |
| `L09_rebal_flow_cont_overnight` | −1.12 | −0.44 | −0.16 | **+0.32** |
| `P03_pd_xs_etfonly_band` | −2.87 | −1.45 | — | −0.47 |
| `N10_synth_eq_band_2.0_0.5` | −5.87 | −2.61 | — | −2.67 |
| `O05_overlap_beta_band_2.0_0.5` | −8.82 | −3.85 | — | −2.98 |
| `C03_stalenav_cont_overnight` | −1.57 | −0.70 | — | −2.27 |
| `L02_decay_pair_short_both` | −1.26 | −0.67 | −1.31 | −1.07 |

Every N, O, P and C formula loses at the lower bound, on both windows. Only the two
levered-rebalance-flow rules turn positive there, and **only out of sample and only at a cost no
account can achieve**: negative on the design window even at the bound, and negative on both
windows at any executable model. Reported because it is the honest shape of the near miss — it
says the gap for `L07` is roughly one tick of execution quality, not an order of magnitude — and
**not** as a result. A Sharpe that requires a fill nobody can get is not an edge.

**Shortability is a constraint, not a price.** Screened on the traded account 2026-08-20 via
`/v2/assets`: **SDS, SH, SQQQ, TMV, TNA, TZA, USO and VIS are not shortable at all.** That is a
broker product restriction on leveraged/inverse ETPs, not borrow scarcity — and it removes the
levered-decay-carry formulas (`L01`, `L02`) independently of their economics: 42–43 % of their
short notional sits in names this account cannot borrow. Their Sharpes are reported with that
share next to them rather than netted into them.

## 6. What was NOT available, stated rather than silently substituted

* **Real iNAV/IIV is not obtainable free.** Alpaca returns zero bars for every pseudo-ticker
  probed (`SPY.IV`, `QQQ.IV`, `EWJ.IV`, `XLKIV`, `SXV`, `IVSPY`, `EWJIV`). Group N's component
  sum is a **proxy for** iNAV and is called that throughout. A true premium/discount test needs a
  paid feed.
* **Published index weights are not free here**, so the "component sum" uses equal,
  ADV-proportional or top-3-by-ADV weights and only the members this cache holds — 2 names of
  XLE, 33 of the S&P 500. That partial replication is why every N variant has a beta-hedged twin.
* **Local-market index history is daily-only (Stooq) and is not tradable by a US retail account.**
  Group C therefore tests the formulation that *can* be traded — the US-listed country ETF, with
  its US-hours residual to SPY as the stale-NAV signal — and does not pretend to trade Tokyo.
* **ADR ↔ ordinary and holdco ↔ constituent maps are not free on this host.** Not tested. Absent,
  not zero. If those maps were bought, the ADR-vs-ordinary claim is the one part of ETF-adjacent
  structural RV this run could not reach.

## 7. Harness self-test — run before any design number was believed

`DEEPMINE_etf_structural_rv_selftest.json`, three synthetic panels on the real calendar:

| probe | what it plants | result |
|---|---|---|
| **NULL** | independent random walks, vwap = close | max gross Sharpe **+1.00 = 1.4 SE**; mean +0.08. Nothing lights up. |
| **LOOKAHEAD** | same walks, but the fill is the geometric **midpoint** of the bar, so a one-bar peek becomes free money | real configs max **+2.04**; two deliberately leaky controls (`N02`/`O02` with the shift removed) score **−26.8** and **−38.1**. A genuine one-bar leak is worth ~30 Sharpe on this panel; the harness scores 2. **No lookahead.** |
| **PLANTED** | XLK = its own component basket + an OU deviation, half-life ≈ 14 bars | `N02` finds it at **+11.7**, and at **−12.6** when the plant is negated. The wiring measures the thing it claims to. |

The NULL probe alone would have been worthless and is documented as such: with `vwap == close`
a one-bar leak is invisible on a random walk, which is exactly why the LOOKAHEAD panel exists.

## 8. Basket implication

**Nothing here is basket-ready.** No formula is REAL under §6, so none is proposed as a leg, and
no diversification claim against L1 (T3 overnight), L2 (ETF-sibling RV), L3 (dual-class) or L4
(T7 ex-dividend) is worth computing for a leg that loses money.

The one thing worth carrying forward is **`L07`, and as a hypothesis rather than a candidate**:
the levered-complex close-rebalance fade is the only formula whose out-of-sample gross edge grew,
whose turnover is already at the floor (2.0/day — one entry, one exit), whose short leg is fully
borrowable, and whose break-even is within ~10 % of the charged spread. Its natural next form is
**not** a 5-minute rule at all but a once-a-session one in the L2 mould — measure at the close,
trade the open, one round trip. That is a different frozen test with its own pre-registration,
not an edit to this one, and it must not be scored on this design window again.

---

### Files

| path | what |
|---|---|
| `research/trading_bot/DEEPMINE_etf_structural_rv_PREREGISTRATION.md` | frozen rule + hash |
| `research/trading_bot/DEEPMINE_etf_structural_rv.json` | this document, machine-readable |
| `research/trading_bot/DEEPMINE_etf_structural_rv_design.json` | all 51 design rows + noise bar |
| `research/trading_bot/DEEPMINE_etf_structural_rv_heldout.json` | the three held-out rows |
| `research/trading_bot/DEEPMINE_etf_structural_rv_SHORTLIST.json` | the mechanically-applied §5 gate |
| `research/trading_bot/DEEPMINE_etf_structural_rv_BREAKEVEN.json` | POST-HOC break-even diagnostic |
| `research/trading_bot/DEEPMINE_etf_structural_rv_selftest.json` | null / lookahead / planted probes |
| `scripts/trading_bot/deepmine_etfstruct.py` | the sweep |
| `scripts/trading_bot/deepmine_spread_calib.py` | per-symbol half-spread proxy |
| `scripts/trading_bot/deepmine_selftest.py` | the three probes |
| `scripts/trading_bot/deepmine_shortlist.py` | §5, applied mechanically |
| `scripts/trading_bot/deepmine_breakeven.py` | §4's post-hoc diagnostic |
