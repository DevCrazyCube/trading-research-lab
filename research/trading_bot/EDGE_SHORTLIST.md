# T1 — the ranked equity-edge shortlist

**What this is.** A menu of thirteen candidate edges for the US-equity programme, scored on four axes
and ranked, with a mechanism, a null hypothesis and one clean out-of-sample test for each. The point
is to find the **least crowded candidate that can still survive our friction floor** — not to re-run
anything this programme has already killed.

**Status.** Survey plus a **first-party data and execution audit** (§2), which is the only part of
this document that is our own measurement. Every performance number attributed to the literature is
**someone else's measurement, cited so it can be checked, and not yet verified on our instruments**.
That distinction is the rule [B22F](../B22F_OVERNIGHT_INTRADAY_SPLIT.md) forced on us: *citing is not
measuring.*

---

## 1. The three constraints that do the ranking

Everything this programme has established points the same way, so the rubric is not neutral:

1. **Friction is the binding constraint, not signal.** Memecoins (95 bps toll), Binance practitioners
   (12/20 profitable at zero fees → 1/20 with fees), MNQ futures (gross edge 0.07–1.50 pts vs 2.0 pts
   friction). Three unrelated markets, one conclusion (`FINDINGS.md` §5d, B22A §5).
2. **The one structural cost advantage we have found is the auction.** A market-on-close or
   market-on-open order is filled in a single-price auction — **there is no spread to pay**. B22C §4
   already recorded this as worth more than broker selection. §2 below establishes we can actually
   place those orders.
3. **A candidate we cannot get data for is not a candidate.** Scored honestly and ranked down, per the
   task's own guardrail. Half the ideas below fail here and are marked accordingly.

**Killed families, excluded by guardrail and not proposed anywhere below:** the exit-rule family,
minute-scale day trading, naive trend, and market intraday momentum (B22E — dead at *zero* cost, and
its conditional structure inverted). Where a candidate sits *near* one of these, §4 says so explicitly
and states how it differs.

---

## 2. What we actually hold — measured today, not assumed

This is the load-bearing section, because it changes several scores relative to what the programme
believed this morning.

### 2a. The credential finding

`.env` stores the Alpaca keys **single-quoted**. A parser that does not strip quotes gets `401
Authorization Required` on every endpoint and looks exactly like "no subscription". Stripped, the same
keys return **full SIP historical tick data**. Any earlier conclusion about our data tier that was
formed against a 401 should be re-checked.

### 2b. Data inventory (each row probed live)

| capability | verified result |
|---|---|
| SIP **daily bars** | 2016 → present, split/dividend adjusted, multi-symbol |
| SIP **minute bars** | 2016 → present |
| SIP **trades + quotes (tick)** | 2016 → present, nanosecond timestamps, ~15-min recency embargo |
| **Auction prints** (`/v2/stocks/auctions`) | opening **and** closing auction price *and size*, per symbol per day, SIP |
| **Corporate actions** (`/v1/corporate-actions`) | universe-wide, 2016 → present: cash dividends, forward/reverse splits, **spin-offs**, cash/stock/mixed mergers, redemptions, name changes, worthless removals. ~950–990 cash dividends per fortnight |
| **Delisted symbols** | SIVB, FRC, BBBY, TWTR all return bars → **survivorship-bias-free backtests are possible** |
| **Universe size** | 14,234 active + **19,197 inactive** us_equity assets |
| **Shortable universe** | 5,275 shortable / 5,276 easy-to-borrow (live flags only — **no history**) |
| **Options** (OPRA) | bars/trades/snapshots from ~Feb 2024 → present (~2.5 yrs); paper account approved **level 3** |
| **News** (Benzinga) | timestamped headlines; **no earnings estimates or surprises** |
| **FINRA daily short-sale volume** | free, `cdn.finra.org`, 12,197 symbols/day, verified 2018 and 2026 |
| **CEF NAV / discount** (CEFConnect) | free; 360-fund daily snapshot; **daily history only ~1 yr**, 5 yr is weekly-sampled |
| **Index membership history** | ✗ no API; iShares holdings endpoint returned a bot-block page, SSGA 301, Wikipedia table not in the static HTML |
| **Borrow fees / short interest** | ✗ nothing we hold |
| **ETF creation/redemption, iNAV, flows** | ✗ nothing we hold |
| **Auction imbalance feed (Nasdaq NOII / NYSE)** | ✗ paid, and not exposed by the broker |
| **Earnings calendar / estimates** | ✗ nothing we hold |

### 2c. Execution inventory (paper account, probed and cleaned up)

Account: **$100,000 equity, 4× multiplier, shorting enabled, fractional enabled, options level 3.**

Three orders were submitted to the **paper** account purely to test order-type acceptance and then
cancelled; final state verified **0 open orders, 0 positions**.

| order type | encoding | result |
|---|---|---|
| Market-on-close | `type=market, tif=cls` | **accepted** |
| Limit-on-close | `type=limit, tif=cls` | **accepted** |
| Market-on-open | `type=market, tif=opg` | **accepted** |

**The zero-spread auction rail is real and available to us.** That single fact carries most of the
ranking below.

### 2d. Friction floor, measured

Median quoted spread, SIP quotes, 2026-08-12, three sample times:

| SPY | QQQ | TQQQ | SOXL | ROKU | MMM | ADX (CEF) | PDI (CEF) | GBAB (CEF) | BSTZ (CEF) | VBIO (small-cap most-active) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.26 bp | 0.41 bp | 1.34 bp | 3.43 bp | 1.32 bp | 2.71 bp | 3.78 bp | 6.23 bp | 28.4 bp | 35.8 bp | **119.6 bp** |

### 2e. Closing-auction capacity, measured (3 days, Jun–Aug 2026)

Closing-auction size as a share of that day's total volume:

| instrument | auction share of volume | auction notional |
|---|---|---|
| **MMM** | **16.1% / 26.8% / 26.6%** | $84–130 M |
| **ROKU** | 11.3–14.2% | $28–73 M |
| SPY | 1.4–3.8% | $460–911 M |
| QQQ | 1.2–1.5% | $309–344 M |
| TQQQ | 0.3–0.6% | $16–19 M |
| SOXL | 1.3–2.9% | $142–231 M |
| UPRO / TNA / LABU | 0.1–0.4% | $0.2–1.2 M |
| CEFs (ADX/BSTZ/PDI/GBAB) | 0.1–2.8% | **$0.0–0.3 M** |

**Two consequences that decide several rankings.** (i) In NYSE/Nasdaq **single stocks** the closing
auction is an enormous, free-of-spread pool — a quarter of MMM's daily volume. A close-to-close or
close-to-open strategy in single stocks pays **no spread on either leg**. (ii) In **leveraged ETFs and
CEFs** the auction is negligible, so anything built on them must cross the continuous spread, at
3.4 bp (SOXL) to 36 bp (BSTZ).

### 2f. A correction for the peer seat, found in passing

B22B's report of "free-tier SIP minute bars don't reach 2025-01-09" is not a data limit. **2025-01-09
was not a trading day** — confirmed against Alpaca's own calendar, which lists 01-06, 01-07, 01-08,
01-10, 01-13 and skips it (the national day of mourning for President Carter). SIP tick data for 2016
is available to these credentials, so there is no coverage gap. The honest statement in the B22B
result should be *"the pinned 30-day sample contained one market holiday, so 29 days were
measurable"* — a preregistration flaw, not an availability limit. The 29/30 count is unaffected.

---

## 3. The rubric

Each candidate scores **1–5, higher is better**, on four axes:

- **U — uniqueness / lack of crowding.** 5 = we found no retail product or standard desk trade doing
  this; 1 = textbook, and there is an ETF for it.
- **E — plausible edge size vs *our measured* friction** (§2d/§2e), not vs an assumed cost.
- **A — retail accessibility on Alpaca**, using the live flags and order types verified in §2c.
- **D — data availability we actually hold today**, per §2b. Scraping that returned a bot-block page
  scores 1, not 3.

Total is the unweighted sum, but **ties break on D then E** — that ordering is the programme's
earned lesson, not a preference.

---

## 4. The ranked shortlist

| # | candidate | U | E | A | D | **total** |
|---|---|---|---|---|---|---|
| **1** | **End-of-day pressure reversal, held overnight on the auction rail** | 3 | 4 | 5 | 5 | **17** |
| **2** | **Ex-dividend drop-off, executed close-to-close in the auctions** | 2 | 3 | 5 | 5 | **15** |
| 3 | Turn-of-month forced rebalancing ("dash for cash") | 2 | 3 | 5 | 5 | 15 |
| 4 | Spin-off forced-selling drift — **DEAD by insufficient power, T9** | 4 | 3 | 3 | 4 | 14 |
| 5 | Closed-end-fund discount mean reversion — **DEAD: held-out net −0.27 bp/wk, DSR 0.154, perm p 0.054, T12** | 4 | 3 | 4 | 3 | 14 |
| 6 | Overnight-vs-intraday premium harvesting — **DEAD: underpowered *and* dead at 0.26 × a half-spread, T10** | 1 | 2 | 5 | 5 | 13 |
| 7 | Merger-arb spread on announced cash deals | 3 | 3 | 4 | 2 | 12 |
| 8 | Reverse-split drift (small-cap dilution machines) | 4 | 3 | 1 | 4 | 12 |
| 9 | Short-borrow-fee / hard-to-borrow signal | 4 | 4 | 2 | 1 | 11 |
| 10 | LETF end-of-day rebalance imbalance | 2 | 2 | 4 | 2 | 10 |
| 11 | Volatility-ETP roll carry | 1 | 3 | 2 | 4 | 10 |
| 12 | PEAD (post-earnings-announcement drift) | 1 | 2 | 4 | 2 | 9 |
| 13 | Index reconstitution add/drop drift | 1 | 1 | 4 | 1 | 7 |

---

## 5. The candidates in detail

### 1. End-of-day pressure reversal, held overnight on the auction rail — **17**

**Mechanism.** Index funds, MOC-mandated flows and ETF NAV tracking must transact at the close
regardless of price (Codex's forced-flow branch: *attention does not remove a constraint*). The
liquidity to absorb that imbalance is supplied at a **price concession**, and the concession is not an
information event, so it reverts once the mandated flow is gone. This is Nagel's (2012) "evaporating
liquidity" framing: short-horizon reversal returns are **compensation for supplying liquidity**, not a
mispricing, which is precisely why attention has not competed them away.

**Why it ranks first is execution, not novelty.** Reversal is old (Lehmann 1990; Jegadeesh 1990) and
`U=3` says so. What is new *for us* is that §2c/§2e make it executable on a rail with **no spread on
the exit leg and a 20%-of-volume pool to exit into**, using data we already hold.

**Null hypothesis.** The overnight return (close → next opening auction print) of the
pressure-fade portfolio is **equal to that of an equal-weight control drawn from the same universe** —
i.e. the last-10-minute residual move carries no information about the overnight return beyond the
common overnight drift that B22F measured (SPY overnight +10.06%/yr, Sharpe 0.87). *The paired form is
mandatory:* an unpaired mean would be dominated by that common drift, which is the exact error §5c of
`FINDINGS.md` records.

**The single cleanest OOS test.**
- Universe: price > $5, dollar ADV > $20 M, median quoted spread < 10 bp — all computable from §2b.
- Signal at **15:59:30 ET**: the stock's last-10-minute return minus β × SPY's. Fade the top/bottom
  deciles.
- Entry: market order at ~15:59:5x, **priced from the SIP quote actually prevailing** (far touch, not
  mid — the B22B discipline), not from a bar close.
- Exit: **the opening auction print** from `/v2/stocks/auctions` — a real, spread-free rail.
- Design on **2016–2021**, freeze, test **2022-01 → 2026-08** untouched. Paired against the
  equal-weight control; permutation on the signal labels; DSR against a declared trial count.
- **Kill condition, fixed in advance:** net mean ≤ 0 in the held-out period, or permutation p ≥ 0.05.

**Proximity to a killed family, stated plainly.** B22E killed *market-level intraday momentum* (SPY,
sign of the morning return → last-half-hour position). This is a different family — **cross-sectional,
single-stock, reversal not momentum, held overnight rather than intraday** — and B22E's own
decomposition is weakly *consistent* with it (largest-|r1| tercile was the most negative, −3.77%/yr,
which is what a pressure-reversal story predicts). It is not the same trade, but the resemblance is
close enough that the kill condition must be pre-committed before any data is touched.

**Honest risks.** (a) Entry pays one half-spread (1–3 bp measured) against an edge that may be only a
few bp. (b) Overnight holding carries gap risk that a paired control does not remove. (c) Quote-level
fill modelling across ~500 names × 2,500 days is a large pull; do signal work on minute bars and
model fills from quotes on a sampled subset, exactly as B22B did.

### 2. Ex-dividend drop-off, executed close-to-close in the auctions — **15**

**Mechanism.** On the ex-date the price falls by **less than the dividend** on average (Elton & Gruber
1970; shrunk but not eliminated post-decimalisation per Graham, Michaely & Roberts 2003). The residual
is a **tax-clientele** effect — a constraint, not an information edge — so attention does not compete
it away.

**Null hypothesis.** The drop-off ratio equals 1: `E[(P_cum_close − P_ex_open) / D] = 1`, i.e. the
market-adjusted cum-to-ex return net of the dividend is zero.

**The single cleanest OOS test.** Pull every cash dividend from the corporate-actions API (≈25,000
events, 2016 → present, universe-wide, delisted included). Measure close(cum) → opening auction
print(ex) — **both legs are auction prints, so the modelled friction is zero and the only cost
assumption is commission, which is $0 at Alpaca**. Market-adjust with SPY over the identical window.
Design on 2016–2021, test 2022–2026. Report in bp *and* in $/share, since the arithmetic that matters
is $-edge vs $-spread.

**The caveat that could kill it before we trade it.** The residual exists *because* dividends are
taxed differently from capital gains. A taxable US retail account receives the dividend as ordinary
income; the pre-tax edge must exceed the tax differential or the strategy is negative after tax while
looking positive on price data. **The tax arithmetic must be settled before, not after, the backtest
is believed** — and it is an owner-facing question, not one I should decide.

> **STATUS: TESTED AND DEAD — `T7_RESULT.md` (2026-08-17).** Held-out label-permutation p = 0.213
> and DSR 0.076, against gates frozen first; all eight design-window trials were negative. Measured
> drop-off ratio **0.95** (design 0.9748, held-out 0.9524), below 1 in both periods and
> distinguishable from 1 in neither.
>
> **And the caveat above is wrong in its mechanics**, which `T7_RESULT.md` §6 corrects. For a
> one-day capture there is **no rate differential**: the offsetting price fall is a *short-term*
> capital loss, taxed at the same ordinary rates as the non-qualified dividend. The real obstacle
> is **loss usability** under IRC §1211(b) — the strategy books 67.7 % of equity per year in
> ordinary dividend income against 65.9 % in short-term capital losses it produces no gains to
> absorb, to earn 1.86 % pre-tax. Break-even in a standalone taxable account needs a drop-off ratio
> below `1 − t` ≈ **0.65**. A tax-deferred account removes the objection entirely.

### 3. Turn-of-month forced rebalancing — **15**

**Mechanism.** Month-end pension/mutual-fund rebalancing and settlement cash needs create predictable
month-end demand (Etula, Rinne, Suominen & Vaittinen, *Dash for Cash*, JFQA 2020). Mandated, therefore
not competed away by attention.

**Null.** Mean market-adjusted return over the month-end window equals the mean over all other
same-length windows.

**Cleanest OOS test.** Daily bars only; close-to-close, so both legs are auction prints and friction
is zero. Design on 2016–2021, test 2022–2026.

**Why it is not higher despite a perfect data score.** ≈127 month-ends in the whole sample, ~60 in the
held-out period. **The power is poor and it should be pre-registered as such** — this is the
n≈2,000-at-43%-vol lesson from `FINDINGS.md` §5 in a new costume. Also very well known.

### 4. Spin-off forced-selling drift — **14**

**Mechanism.** When a parent spins off a subsidiary, index funds holding the parent receive a stub
that is **not in their index** and must sell it on a schedule, regardless of value; long-run
outperformance of spin-offs is documented (Cusatis, Miles & Woolridge 1993). Forced, dated, and
mechanical.

**Null.** Market-adjusted return of the stub over the 1–60 trading days after the spin-off date is
zero.

**Cleanest OOS test.** `spin_off` events come universe-wide from the corporate-actions API back to
2016 — no scraping. Event study on market-adjusted returns, design 2016–2021, test 2022–2026.

**Honest limits.** n is small (tens per year, so a few hundred events total), stubs are often illiquid
(§2d says a small-cap most-active quotes at 120 bp), and the clean version is long-only.

> **STATUS: TESTED AND DEAD — `T9_RESULT.md` (2026-08-17). DEAD BY INSUFFICIENT POWER**, against a
> power gate frozen in the pre-registration before any return existed, and it also fails all three
> statistical gates (net mean −0.82 %/event t −0.39; permutation **p = 0.627**; **DSR 0.063**).
>
> **The "243 spin-off records already on disk" was my count and it was wrong about the world.**
> 243 raw → 225 unique → 177 with a ticker `new_symbol` (48 are CVRs, escrow/contingent
> entitlements and bare CUSIPs) → **82 tradeable events, 62 of them held out.** And the feed's
> spin-off history is **truncated, not thin**: zero records in 2016, zero in 2018, one in 2019.
> Corteva, Dow, Adient, Lamb Weston, Valvoline, Resideo, Garrett, Arlo and Brighthouse are all
> absent, while five of them return cash dividends over the identical query window.
>
> **The number that matters:** σ̂ = 15.5 % per event ⇒ **MDE 5.51 %** at 80 % power on 62 events,
> against Cusatis's own ≈ **2.40 %** over the same horizon. **327 events are needed; at 13.4
> tradeable events a year that is 24 years of prospective collection.** Friction is 11.8 bp
> against 1,635 bp of per-event noise — **139×** — so this is the first candidate in the programme
> that does **not** die at the friction floor. It dies at n.
>
> **Measured and reusable:** the median quoted half-spread of a freshly distributed stub is
> **7.47 bp** (p75 18.4, p95 59.6, n = 134 symbol-days), against SPY's 0.116 bp and the
> top-500-ADV universe's 1.13–1.43 bp, same instrument and window.

### 5. Closed-end-fund discount mean reversion — **14**

**Mechanism.** CEF prices deviate from NAV and the discount mean-reverts (Pontiff 1995). It survives
because it is **institutionally uneconomic to arbitrage at these sizes** — which is exactly the
"uncrowded because too small to matter" corner a $100k account should want.

**Null.** Next-month return of the widest-discount decile equals that of the narrowest, after
adjusting for NAV return.

**Cleanest OOS test.** CEFConnect gives a free 360-fund daily snapshot and ~1 year of daily NAV
history (5 years only weekly-sampled), so the honest test is **weekly, 5 years**, plus **forward
daily collection starting now** — which is the more valuable of the two and costs one cron job.

**What holds it down.** §2e: CEF closing auctions clear **$0–0.3 M**, so the free rail is unavailable
and every leg crosses a 4–36 bp spread; §2d BSTZ at 35.8 bp is a real number, not a worst case. And
the NAV history we can get is shallow.

> **STATUS: TESTED AND DEAD — `T12_RESULT.md` (2026-08-17).** Against gates frozen first
> (`T12_PREREGISTRATION.md`, sha256 `d8866300…`): held-out net **−0.27 bp/week, t −0.08**,
> label-permutation **p = 0.0539**, **DSR 0.1542** at the six declared trials. Three of the four
> kill conditions failed.
>
> **It did NOT die of thin history, which is what the task expected.** The power gate *passed*
> (min detectable annualised Sharpe **1.745** ≤ the 6 %/yr Pontiff benchmark's **1.859**) — but
> only because a dollar-neutral CEF decile book is unusually quiet, **σ̂ = 3.23 %/yr**. At an
> ordinary 10 %/yr it would have been `DEAD-BY-INSUFFICIENT-HISTORY`. The span in §2b above is
> **confirmed exactly** on all 360 funds: 5 yr weekly (**243 usable weekly dates**, design 125 /
> held out 117) or 1 yr daily, never both, and the broker does not relax it — the NAV pseudo-
> ticker `XADEX` returns **zero bars** where `ADX` returns ten years of price.
>
> **The mean-reversion family is dead in every declared form.** All four own-mean-reversion
> trials were positive in the design window (+7 to +16 bp/wk, ann. Sharpe 1.15–2.42); **three of
> four went negative out of sample.**
>
> **New first-party friction number, and it outlives the candidate: the median CEF quoted
> half-spread is 11.53 bp** (n = **3,067 symbol-days**, SIP, `[15:59:59, 16:00:00)` ET; p75 18.4,
> p90 27.2, p95 36.4, max 185.7). That is **99× SPY** (0.116 bp) and **1.5× a fresh spin-off
> stub** (7.47 bp, T9) — the most expensive universe this programme has priced. Break-even is
> ≈ **10.6 bp**. But **at zero cost it is still only annualised Sharpe 0.68**, so unlike T10 no
> execution improvement rescues it.
>
> **One trial did not die, and it is not a pass.** The *raw discount level* form (trials 5–6,
> declared but not primary) returned **+12.9 / +14.5 bp/week held out, ann. Sharpe +2.30 / +2.57,
> DSR 0.991 / 0.997**, consistent with its design window. `T12_DIAGNOSTICS.json` attacks it:
> **81 % of both deciles carry over each rebalance** (it is a near-static tilt, not reversion);
> about half the P&L is the **NAV leg** (+9.45 bp/wk), i.e. the assets rather than the discount;
> **57 % of the short leg is shortable** at this broker; and the panel is **100 % survivors**
> with a heuristic **~27 %** of the 2021 CEF population invisible. It also is *not* an
> equity-vs-bond tilt — β to (SPY − AGG) is only **+0.057** — which corrects my own first reading.
> It needs its own pre-registration built on a survivorship-robust panel, and that is an owner
> scope call (`T12_RESULT.md` §8).

### 6. Overnight-vs-intraday premium harvesting — **13**

**Mechanism.** The overnight session has historically carried a disproportionate share of the equity
premium (Lou, Polk & Skouras, JFE 2019). Executable MOC→MOO on the free rail.

**Null.** Overnight-only holding has the same Sharpe as buy-and-hold.

**Cleanest OOS test.** Already half-done and it is *not* encouraging: B22F measured SPY overnight
Sharpe **0.87** vs full-day **0.89** — so on our own instrument the overnight slice is not
risk-adjusted-better than simply holding, and the NY Fed's *Disappearing Overnight Drift* (July 2026)
documents the mechanism weakening. **This is exposure re-slicing, not alpha**, and it is listed for
completeness rather than promise.

> **STATUS: TESTED AND DEAD — `T10_RESULT.md` (2026-08-17). DEAD — UNDERPOWERED**, against gates
> frozen first (`T10_PREREGISTRATION.md`, sha256 `7f661951…`). Held-out **DSR 0.3772** at the
> eight declared trials — the observed per-observation Sharpe **0.01405** sits *below* the
> expected-max under the null, **0.02342**. Design → held-out annualised Sharpe **+0.903 →
> +0.221**; net **+1.48 bp/session, t +0.47** on 1,140 held-out sessions.
>
> **The null above was the wrong null, and the pre-registration replaced it.** "Overnight-only
> has the same Sharpe as buy-and-hold" is an unpaired comparison; the premium claim is the
> **paired difference** (long overnight, short intraday), which is what T10 actually tested, in
> two families — market-level (SPY and equal-weight top-100/300/500) and the Lou-Polk-Skouras
> **cross-sectional tug of war**. The frozen configuration was the cross-sectional one.
>
> **The decisive number is friction, and it is not a power question.** The paired trade turns
> **4.00 of gross notional per session and sells 2.00** (measured, asserted in the runner). SEC
> §31 alone is **0.556 bp/session = 138 bp/yr**. Total gross edge: **+4.29 %/yr**. Break-even is
> **0.370 bp per auction leg = 0.26 × the measured quoted half-spread of its own universe**. At
> 0.5 h it is −4.68 %/yr, at 1 h −11.19 %/yr. **M0's unmeasured live half — that our broker's
> on-close order joins the cross — is now worth 1,414 bp/yr to this candidate.**
>
> **What DID replicate, out of sample, on auction prints:** SPY overnight **+7.29 %/yr,
> Sharpe 0.724** against intraday **+3.15 %/yr, Sharpe 0.284** (held out 2022–2026); EW top-500
> +7.15 %/0.670 against +2.38 %/0.228. The Lou-Polk-Skouras asymmetry is real and reproduces on a
> second instrument. **Harvesting it is what does not work.**
>
> **And one method finding that outlives the candidate.** The gate-2 label permutation returned
> **p = 0.0020** on a series whose own t is **+0.47**. The real decile book carries **3.88×** the
> per-session dispersion of a random partition of the same names (105.5 bp vs 27.2 bp) and it is
> **not** market beta (β = −0.036). A cross-sectional label permutation on a *sorted return
> series* answers "is this partition special?", not "is the mean positive?". See
> `T10_RESULT.md` §5.

### 7. Merger-arb spread on announced cash deals — **12**

**Mechanism.** The target trades below the offer; the discount pays deal risk and time. Retail-scaled
small deals are genuinely under-arbitraged.

**Null.** Annualised spread capture equals the risk-free rate after deal-break losses.

**Cleanest OOS test.** Blocked on data: the corporate-actions API supplies **effective** dates and
rates but not **announcement** dates or terms (`D=2`). Without announcement dates the event window
cannot be built, and reconstructing it from Benzinga headlines is an NLP project with its own error
rate. Cheap first step: measure how reliably an announcement date can be recovered from the news
endpoint on a sample of 50 known deals, before committing.

### 8. Reverse-split drift — **12**

**Mechanism.** Reverse splits cluster in serially dilutive small caps; the documented post-event drift
is negative. The corporate-actions API records **every** reverse split universe-wide (24 in a single
fortnight of 2025).

**Null.** Market-adjusted return over the 1–60 days after a reverse split is zero.

**Why `A=1` sinks it.** The tradable side is the **short** side, and these names are exactly the ones
Alpaca will not lend — SOXL, VXX and SVXY are already flagged not-shortable/not-ETB (§2b), and a
$20 M shell is far outside that. The long side of a negative-drift signal is not a strategy. Worth
recording because the *data* is unusually good; not worth building.

### 9. Short-borrow-fee / hard-to-borrow signal — **11**

**Mechanism.** High borrow fees are among the strongest cross-sectional predictors of negative
abnormal returns (D'Avolio 2002; Drechsler & Drechsler).

**Null.** High-fee names earn the same market-adjusted return as low-fee names.

**Why it ranks below its quality.** `D=1`: we hold **no** borrow-fee or short-interest history. The
`easy_to_borrow` flag is a **live snapshot with no history**, so it cannot be backtested at all.
FINRA's free daily short-*volume* file is a weak proxy for short *interest* and a weaker one for
*fee*. And `A=2`: the fee **is** the price of the edge — you pay it — and the names where it is
largest are the ones Alpaca will not lend. Revisit only if a borrow-fee feed is bought.

### 10. LETF end-of-day rebalance imbalance — **10**

**Mechanism.** A levered ETF must trade in the direction of the day's move, daily, by prospectus, in
size proportional to `(L² − L) × AUM × r`.

**Null.** The last-30-minute return of the underlying is unrelated to the day's return interacted with
LETF assets in that sector.

**Why it ranks low despite being the archetype of a forced flow.** (a) `D=2` — the AUM/shares-
outstanding history needed to size the imbalance is issuer-published and our scrape of the analogous
iShares endpoint returned a **bot-block page**. (b) **B22E is a partial pre-refutation**: its
largest-|r1| tercile — the days when index-level rebalance flow is largest — was the *worst*
(−3.77%/yr, t = −1.04). (c) The index-level version is uncomfortably close to the killed intraday
momentum family. (d) Ivanov & Lenkey (2014) find secondary-market flows substantially offset the
mechanical imbalance. The only version not already spoken to is **high-LETF-share sectors**
(semiconductors), and that needs the AUM data we do not have.

### 11. Volatility-ETP roll carry — **10**

**Mechanism.** VIX futures in contango make long-vol ETPs bleed; the carry accrues to the short side.

**Null.** Long-SVXY (or short-VXX) excess return equals zero after the tail.

**Why not.** `A=2`: §2b measured **VXX and SVXY as not shortable and not easy-to-borrow at Alpaca**, so
only the long-SVXY expression is available — a single-instrument tail bet whose predecessor (XIV) lost
~90% overnight in February 2018. This is a known risk premium, not an edge, and its tail is the
product.

### 12. PEAD — **9**

**Mechanism.** Prices under-react to earnings surprises and drift.

**Null.** Post-announcement market-adjusted drift is zero conditional on surprise decile.

**Why last-but-one.** The most-studied anomaly in the literature (`U=1`), documented to have decayed
in liquid names (Chordia, Goyal & Sadka), surviving mainly where §2d measured spreads at **120 bp**,
and `D=2` — we hold **no earnings calendar and no estimates**, only headlines.

### 13. Index reconstitution add/drop drift — **7**

**Mechanism.** Index funds must buy the add at the close. The canonical forced flow.

**Null.** Abnormal return between announcement and effective date is zero.

**Why it is last and should stay last.** Greenwood & Sammon (*The Disappearing Index Effect*) document
the S&P addition premium falling from roughly 7% in the 1990s to approximately **zero** in recent
years — the null is close to *already accepted* in the literature. And `D=1`: no membership-history
API, iShares bot-blocked, SSGA 301, the Wikipedia changes table absent from the static HTML. Highest
name recognition, lowest expected value.

---

## 6. Recommendation

**Pursue #1 (end-of-day pressure reversal on the auction rail) as primary, and #2 (ex-dividend
drop-off) as secondary.** They share one execution rail, one dataset and one prerequisite measurement,
so the second costs a fraction of the first.

**Do the prerequisite measurement before either backtest — this is the B22A/B22B pattern that has
already saved this programme twice.**

> **M0 — auction fill realism.** For a pinned sample of dates and names: (a) does an MOC/LOC order
> submitted to the paper account actually fill **at the official closing print**, and (b) what is the
> distribution of the pre-close half-spread we would pay on the entry leg, measured from SIP quotes,
> not bars?

Properties that make M0 the right first move, mirroring B22A §7: it is bounded (days, not years), it
needs no strategy implementation, it is a **measurement rather than a search** so there is no
multiple-testing exposure, and **either outcome is worth having**. If MOC orders do not fill at the
print, the entire rail — and with it the ranking above — is wrong, and we find out for the price of a
fortnight of paper orders. If they do, both #1 and #2 inherit a verified zero-spread exit.

**One preregistration discipline carried forward explicitly:** the pinned day-sample must be drawn
from Alpaca's **trading calendar**, not from weekdays. §2f shows why.

---

## 7. What this document does not claim

- **No edge here has been measured by us.** §2 is our own measurement; §4 and §5 are a ranking of
  other people's results by our criteria.
- **Every literature figure is cited, not verified.** B22F's rule applies in full: a literature claim
  used as an argument for a decision gets measured on our own instrument and period before it carries
  weight.
- **The scores are judgements, not statistics.** U and E in particular are priors. D and A are
  measured, which is why ties break on them.
- **Nothing here authorises real-money execution**, which remains owner-gated.

---

*First-party measurements in §2 were taken 16 Aug 2026 against the Alpaca SIP feed and the paper
trading account. The three paper orders placed to verify auction order-type support were cancelled
immediately; the account was left with 0 open orders and 0 positions.*
