# T17 — the POWER GATE for the ORB multi-position day-trading test

**Status: FROZEN. Hashed before the census that it judges was computed.**

This document exists because of `T15_RESULT.md` §10 and the rule it earned: *a candidate is
power-blocked until the census says otherwise, and the census is judged against a threshold
written down first.* T9 and T15 both died on power **after** their windows had been spent. The
thresholds below are therefore fixed here, in advance, and the census is run afterwards against
them. Nothing in this file is derived from a T17 measurement, because none exists when it is
hashed.

Verification of that claim is mechanical: at the moment this file is hashed,
`research/trading_bot/T17_POWER_CENSUS.json` **does not exist**, and the command that records
the hash asserts its absence in the same invocation.

---

## 0. What is being powered

The candidate is Zarattini, Barbon & Aziz (2024), SSRN 4729284 — opening-range breakout on the
top-20 US stocks by opening relative volume, entered on a stop at the 5-minute high/low, stopped
at 10 % of ATR(14), exited at the close. Reported **annualised Sharpe 2.81** over 2016–2023,
net of a $0.0035/share commission and **nothing else**: the paper's text contains the strings
`slippage`, `bid-ask`, `market impact`, `capacity` and `fill` exactly zero times.

Two distinct quantities have to be powered, and they fail in different ways:

| | statistic | why it can fail |
|---|---|---|
| **A. Portfolio** | annualised Sharpe of the daily portfolio return | too few *independent days* |
| **B. Per trade** | mean per-trade PnL in R units | too few *trades*, or too much dispersion |

**A is the binding one and B is a diagnostic.** Trades taken on the same morning share a market
factor, so a trade-level t-statistic overstates the evidence. The portfolio-level daily series is
the honest unit and the gate is written on it.

---

## 1. The daily-Sharpe power wall, stated as arithmetic

For a daily return series, the t-statistic of the mean is

> t ≈ SR_annual × √(T_years)

so certifying an annualised Sharpe `S` at a critical value `z` needs

> **T_years = (z / S)²**

This programme uses **z = 2.80** (two-sided 5 % with a modest multiple-testing allowance; it is
the same constant the task states). The wall, tabulated so that no result can later be described
as surprising:

| true annualised Sharpe | years needed at z = 2.80 |
|---|---|
| 2.81 (the paper's claim) | **0.99** |
| 2.00 | 1.96 |
| 1.40 (half the claim) | 4.00 |
| 1.00 | 7.84 |
| 0.78 (S&P 500 buy-and-hold) | 12.9 |
| 0.50 | 31.4 |

The claim is *easy* to power. That is the unusual feature of this candidate and it is why it is
worth the held-out window at all: unlike T9, T11 and T15, the effect being tested is large
relative to its own noise. What is **not** easy to power is a heavily cost-degraded version of
it, and the gate below is written against that, not against the headline.

---

## 2. The gates. All are pass/fail and all are frozen here.

### G0 — DATA CENSUS (structural)
The window must actually contain intraday data. **Pass** iff the held-out window contains
≥ 900 sessions on which the universe screen returns ≥ 20 eligible names, and the SIP intraday
feed serves 5-minute and 1-minute bars for ≥ 98 % of the selected stock-days. A day for which
data is missing is recorded as missing, never as a no-trade day.

### G1 — PORTFOLIO POWER (the binding gate)
**Pass** iff the held-out window contains enough independent trading days that

> MDE_Sharpe(held-out) = 2.80 / √(T_years) **≤ 1.405**

i.e. **T_years ≥ 3.97**. 1.405 is *half* the claimed 2.81. The rationale, fixed before the
number is known: a test that can only detect the claim exactly as stated is worthless, because
the whole question is how much of the claim the omitted friction removes. The window must be
able to see an effect half the advertised size. **Fail ⇒ POWER-BLOCKED and the window is not
spent**, exactly as T15 was handled.

### G2 — TRADE COUNT (secondary)
**Pass** iff the held-out window produces ≥ 2,000 triggered trades on ≥ 500 distinct sessions.
Below that a per-trade mean in R is not worth reporting even as a diagnostic.

### G3 — PER-TRADE MDE (secondary, with its clustering caveat stated)
**Pass** iff the per-trade minimum detectable effect

> MDE_R = 2.80 × sd(per-trade R) / √(n_trades)

is **≤ 0.080 R**, the paper's own reported per-trade edge in the RelVol > 100 % bucket it
actually trades. This is computed on the *design* window only, so that the held-out window is
not read to decide whether to read it. Because same-day trades are correlated, the honest
version of this number is inflated by a same-day cluster factor and both are reported.

### G4 — COST RESOLUTION (the gate this candidate is really about)
The T5/B22B slippage measurement is in two units and the strategy's PnL is in a third. **Pass**
iff R (= 10 % of ATR(14)) can be expressed as a fraction of notional on the *screened* universe
from ≥ 100 stock-days of first-party measurement, so that the T6 round-trip cost in bp of
notional can be converted into R without an assumed ATR. **Fail ⇒ the cost cannot be charged in
the strategy's own units and the test is not run.**

---

## 3. The pre-registered arithmetic that this census will make concrete

Written down now so that it cannot be presented afterwards as a discovery:

* The T6 per-side cost model round trip is **5.59 bp of notional** (entry 1.55 measured +
  exit 2.50 half-spread + exit 1.55 adverse proxy), `DECISIONS.md` 2026-08-17.
* If R is *x* bp of notional on the screened universe, the round-trip cost is **5.59 / x** in R
  units.
* The paper's own reported per-trade edge is **+0.08 R** at the RelVol > 100 % filter it uses,
  and **+0.38 R** in its most favourable RelVol > 30× bucket.
* Therefore: **if R is below ≈ 70 bp of notional, the honest round-trip cost exceeds the paper's
  own headline per-trade edge before a single trade is simulated.** That is not a verdict — the
  top-20 selection sits far above the 100 % threshold, so the realistic edge is higher than
  0.08 R — but it is the quantity on which everything turns, and it is being written down before
  it is looked up.

---

## 4. What a PASS authorises, and what it does not

A PASS authorises **one** evaluation pass over the held-out window under
`T17_PREREGISTRATION.md`, whose hash is recorded before any held-out number is computed. It does
not authorise re-running with different filters, a different top-N, or a different slippage rung.
Each of those is a new document with a new hash.

A PASS is *not* evidence that the strategy works. It is only the statement that this window can
tell the difference.
