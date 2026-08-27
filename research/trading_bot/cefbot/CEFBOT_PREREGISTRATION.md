# CEFBOT — pre-registration: closed-end-fund discount-LEVEL tilt, long-vs-market-hedge, paper forward

**Frozen 2026-08-24, before a single forward return was marked.** This document is the immutable
rule of a **paper / hypothetical** forward test. It authorises **no real order, no broker order
of any kind, and no real money.** Marks are mark-to-market against realised prices only, exactly
as `scripts/trading_bot/basket_forward.py` does for its legs. Improvement is governed by
`research/trading_bot/ITERATION_PROTOCOL.md`: this rule is immutable; a better idea is a NEW
pre-registration with its own ledger, never an edit to this one.

The runner (`scripts/trading_bot/cefbot/`) verifies this file's sha256 at start-up and **refuses
to run** if the document has moved since the freeze.

---

## 0. What this is, in one paragraph

The programme re-examined 86 killed edges (`research/trading_bot/THOROUGH_REEXAM.md`). Exactly one
cleared the bar as a genuinely new, diversifying, free-data-reachable revive: **R1 — the T12 CEF
discount-LEVEL tilt** (held-out **+13.44 bp/week net, t 3.51, annualised Sharpe 2.35, DSR 0.9971,
n = 116 weeks**, 2024-03 → 2026-08). It **passed a backtest. It has never passed a forward test.**
This bot is that forward test made concrete: it pulls the live CEFConnect discount snapshot each
week, tilts long into the widest-discount decile, hedges broad-market beta with a short in a
single liquid index ETF, marks to realised price, and logs the result to an append-only ledger
that can certify or kill the edge on data that printed *after* this freeze.

---

## 1. The claim and its null

**Mechanism.** A closed-end fund has a fixed share count, so its price is not arbitraged to NAV by
creation/redemption the way an ETF's is. Prices wander to persistent discounts; the widest
discounts are compensated for the institutional cost of *closing* them (tender, merger,
open-ending, activist campaign — uneconomic at a few hundred $M of fund). The **cross-sectional**
tilt toward the widest-discount decile therefore earns a premium the market leaves uncrowded
because it is too small to matter to size (Pontiff, JFE 37, 1995).

**H1.** A book that is **long the widest-discount decile** of the liquid CEF cross-section and
**short a broad equity index proxy** sized to strip broad-market beta earns a **positive net
(post-friction)** return, and its long leg **beats the equal-weight broad CEF universe** (the pure
cross-sectional discount alpha).

**H0 (null actually tracked).** The widest-discount decile's subsequent **price** return is **≤**
the equal-weight broad CEF universe's, net of friction — i.e. the discount level carries no
cross-sectional information. This is the buy-and-hold-the-CEF-basket null, and it is tracked
weekly beside the book so beta is separated from alpha by construction.

**Why LEVEL not mean-reversion.** T12's declared *primary* was S1 discount **mean-reversion**
(z-score vs the fund's own trailing mean). **S1 is genuinely dead** (held-out −0.27 bp/wk, t
−0.08; `THOROUGH_REEXAM.md` §2). The surviving form is **S2 — the raw discount LEVEL, ranked
cross-sectionally, no trailing window.** This bot trades S2 only.

---

## 2. The frozen rule, in closed form

### 2a. Data
- **Signal + universe:** CEFConnect `GET https://www.cefconnect.com/api/v3/DailyPricing` — keyless,
  free, ~360 fund rows, each with `Ticker`, `Discount` (%, negative = discount), `NAV`, `Price`.
  One snapshot per weekly cycle, cached to `research/data/cefbot_cache/snapshots/`.
- **Hedge mark:** SPY daily close via the programme's existing read-only Alpaca SIP market-data
  rail (`scripts/t3_pressure_reversal.py`). No trading endpoint is ever called.

### 2b. Universe eligibility (applied every rebalance, identically)
1. `Ticker`, `Discount`, `NAV` (> 0) and `Price` all present on the snapshot.
2. `Price` **> $5.00** (sub-$5 CEF friction is not modelled — T12 §4 exclusion 3, same threshold).
3. **No liquidity or shortability screen on the CEF leg** — CEFConnect's ADV is a today-only
   snapshot and screening a past date on it is look-ahead. The consequence (a name may be thin)
   is **priced**, via the measured 11.53 bp half-spread and the capacity cap of §5, never filtered.

### 2c. Signal — discount LEVEL (S2)
`s[i] = Discount[i]` (the raw CEFConnect `DiscountData`, % of NAV, negative = discount). Rank the
eligible universe ascending on `s`. **Most negative = widest discount = long.**

### 2d. Long book
Take the **widest-discount decile**: `n_long = round(0.10 × N_eligible)` names, **equal weight**,
total long notional **1.0**.

### 2e. Market hedge — short ONE index ETF, never individual CEFs
Short **SPY** at notional **`beta_h × 1.0`**, `beta_h = 0.50` (**FROZEN prior, not fitted**).
Rationale, fixed in advance: the CEF universe is a bond/equity blend whose realised equity beta is
well below 1; 0.50 is a deliberately conservative central prior that removes broad equity beta
without over-hedging the fixed-income majority. **The hedge is a single deep, easy-to-borrow index
ETF by design** — the R1 caveat is that CEFs are often hard to borrow, so the primary expression
must NOT rely on shorting individual CEFs. `beta_h` is immutable; a different value is a new
pre-registration (a search), not a tweak (`ITERATION_PROTOCOL.md` §8.1).

**Honest limitation, on the record:** an equity-index short hedges *equity* beta only. The
residual rates/credit factor of a bond-heavy CEF book is **not** hedged. The weekly
buy-and-hold-CEF-basket null (§3) is what reveals how much common CEF move survives the hedge.

### 2f. Cadence, hold, and the PIT-NAV timing mechanism
- **Rebalance weekly** (≥ 5 trading sessions since the last rebalance). **Hold = 1 week.** The book
  is fully re-formed each week: settle last week's book at realised prices, enter this week's.
- **PIT-NAV discipline.** `Discount` is a function of `NAV`, and NAV is struck/published *after*
  the close. The discount therefore forms the **signal only** and **never a mark**: all P&L is
  computed from realised **Price** alone. To keep the signal free of same-day NAV look-ahead, the
  signal snapshot is **lagged ≥ 1 trading session** behind the execution/mark snapshot — the book
  entered this session is ranked on the *previous* session's discount and priced at *this*
  session's price. The lag is enforced by the cache mechanism (a book cannot be entered until a
  strictly-earlier snapshot exists), not by prose. The first ever cycle seeds the signal snapshot
  and enters no marked book.

### 2g. Marks (realised Price only)
At each settle, over the names entered one week earlier:
- `long_ret` = equal-weight mean of `Price_exit / Price_entry − 1`.
- `universe_ret` = equal-weight mean of the **same** ratio over **all eligible** funds at entry
  (the buy-and-hold-CEF-basket null).
- `spy_ret` = `SPY_close_exit / SPY_close_entry − 1`; `hedge_ret = − beta_h × spy_ret`.
- `cross_sectional_alpha = long_ret − universe_ret` (pure discount tilt, beta-free by construction).
- `book_gross = long_ret + hedge_ret`; `book_net = book_gross − cost` (§5).

---

## 3. The two benchmarks

1. **Absolute hurdle — T-bill + 1.00 pp/yr.** Weekly hurdle `(1 + r_tbill + 0.01)^(1/52) − 1`.
   `r_tbill` is a **refreshable input** (the current ~3-month T-bill yield, default 4.30 %/yr);
   the **+1.00 pp/yr alpha bar is frozen**. Refreshing the risk-free level is a data refresh
   (maintenance), not a rule change.
2. **Beta-isolation null — buy-and-hold the CEF basket.** `universe_ret` above. The bot's edge over
   this null is the cross-sectional discount-reversion alpha; the gap between `book_net` and this
   null attributes P&L to *tilt* rather than to *being long CEFs in a narrowing-discount regime*.

---

## 4. Costs — per side, honest, none assumed away

| component | charge | basis |
|---|---|---|
| CEF leg half-spread | **11.53 bp** entry + 11.53 bp exit, on realised turnover | T12 first-party measurement, 3,067 CEF symbol-days, SIP quotes (`T12_FRICTION_CENSUS.json`). **Not the auction rail** — CEF closing auctions clear $0.0–0.3 M, so every leg crosses a continuous spread. |
| SPY hedge half-spread | **0.116 bp** each side | Programme's measured SPY half-spread, same window/instrument. |
| SEC §31 | **0.278 bp** of sale notional | Charged on the CEF sell side and on opening the SPY short (a sale). Top of the 2016–2026 range. |
| FINRA TAF | **$0.000166 / share** sold | Same convention as T9/T10/T12. |
| SPY borrow | **33 bp/yr** on short notional, per calendar day held | B22G measured ETB general-collateral median; SPY is deep GC. A FLOOR. |
| CEF borrow | **not charged** | The primary expression holds **no** short CEF. |
| commission | **0** | Alpaca $0/share. |

Turnover is decomposed per name each rebalance (a name that stays in the decile is charged
nothing; a name that leaves is charged an exit). Realised turnover is **reported, not assumed.**

---

## 5. Capacity, and what the log may never claim

- **Capacity is SIZE-capped to low single-digit $M** (`THOROUGH_REEXAM.md` R1: closing auctions
  clear $0.0–0.3 M; the median CEF's whole auction is under $0.3 M). This is a paper test; capacity
  is stated, never modelled away, and no result here implies it scales past a few $M.
- **Point-in-time NAV risk is unfalsifiable from this feed** and hits the discount signal hardest;
  survivorship (CEFConnect lists only funds alive today) has an **unknown sign**. Both are standing
  reasons a positive forward result is *supporting*, not *dispositive*, evidence.
- **The log may never support:** a live-money claim; a capacity above low-single-digit $M; a Sharpe,
  CAGR, annualised return or p-value quoted as a *result* below the §6 minimum; or any assertion
  that the backtest's 2.35 Sharpe is the forward expectation (honest forward prior after
  survivorship + PIT-NAV + hedge-basis haircuts is **~1.0–1.5**, and this long-vs-hedge H = 1
  expression is a *distinct, weaker-expected* deployment of the family, not the H = 4 long-short
  cell that produced 2.35).

---

## 6. Minimum sample, gates, and the pre-registered kill rule

**Below the minimum, there is NO VERDICT — behaviour is not evidence.** Everything computed below
the minimum lives in an `inputs_that_are_not_results` block and is never annualised as a claim
(`ITERATION_PROTOCOL.md` §8.5).

- **Verdict minimum: 123 settled weekly observations.** This is the programme's own power floor
  (`T12_PREREGISTRATION.md` §3a: the CEF weekly instrument cannot certify an annualised Sharpe
  below ~1.1–1.3 with fewer). SURVIVES may be declared only at `n ≥ 123` **and** net mean > 0
  **and** `t_net ≥ 1.645` **and** the long leg beat the buy-hold null.
- **Kill rule (pre-registered, fires early): `n ≥ 26` and cumulative net < 0 and `t_net ≤ −2.0`
  → HALT, verdict `DEAD — FORWARD-NEGATIVE`.** A significant negative is detectable long before the
  certification floor; the programme does not keep paying friction into a measured loser.
- **Drawdown halt: realised peak-to-trough drawdown ≥ 25 % → HALT**, verdict `DEAD — DRAWDOWN`.
- **Fidelity/rail halts** per `ITERATION_PROTOCOL.md` §2 (a marked weight ≠ the frozen rule's
  weight invalidates the window; SPY-mark rail failure is restated, not silently dropped).

**Honest iterate.** A variant (a different `beta_h`, decile width, hold, or an added rates hedge)
is a **new pre-registration with a new ledger and its own trial count**, never a retroactive edit
here. Both variants, if run, count toward the family DSR forever.

---

## 7. Trial accounting

This is trial **T12-S2 / long-vs-hedge / H=1**, one cell of the CEF discount family. The family's
declared cells (all counted for DSR, forever): the six T12 backtest trials (S1×{26,52}×{1,4},
S2×{1,4}), the basket's live L5 (S2 long-short borrowable H=4) and L9 (muni+equity S2 H=1), and
this bot. Under-declaring trials is how a chance maximum becomes a discovery; they are listed here
so it cannot happen quietly.

---

## 8. What this pre-registration does not authorise

Real orders; real money; any broker trading endpoint; a live `shortable`/borrow constraint modelled
as anything but the priced cost of §4; a capacity claim above low-single-digit $M; or any edit to
this document. Live execution remains owner-gated and this bot does not reach it.
