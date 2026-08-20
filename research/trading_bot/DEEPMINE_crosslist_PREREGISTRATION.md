# DEEPMINE: cross-listing / multi-ticker identical-claim RV -- PRE-REGISTRATION

Written 2026-08-20, **before any design-window result exists**. Committed before the sweep runs.

## Sub-family
US-listed lines of the *same economic claim* carried on more than one ticker:
1. **US/US pairs** -- dual-listed-company (DLC) structures and two ADR lines on one foreign
   issuer's two share classes. Both legs tradable in a US account.
2. **ADR vs its home/ordinary listing** -- signal from the foreign line + FX; the *traded book
   is US lines only*.

Deliberately excludes the domestic dual-class-voting pairs already tested (T28) and the
ETF-sibling / CEF-discount legs already in the basket.

## THE HARD CONSTRAINT, STATED UP FRONT
This account can only trade **US-listed** securities. A true two-legged RV trade therefore
requires **both** lines to be US-listed, which is true for only ~10 pairs, half of which
unified or delisted before 2022. For the ADR-vs-home family the home leg is **not tradable
here**, so the home price is used **as a signal only** and every dollar of P&L is computed
from **US-listed adjusted closes**. This is also the sweep's principal lookahead guard: an
error in the FX quote or in the home leg's timestamp can add noise to the signal but
**cannot manufacture P&L**, because no untradable price ever enters the return.

## Data
- US legs: Alpaca SIP daily bars, `raw` (signal; levels are point-in-time) and `all` (P&L).
- Home legs, FX, country ETFs: Yahoo chart API daily. Stooq is unusable from this host
  (JS proof-of-work challenge; solved, then `Access denied`).
- ADR<->ordinary map: **hand-curated, no free machine-readable source reachable**. It is a
  convenience sample with a survivorship tilt toward programmes that still exist. Recorded.
- ADR ratios are **not** encoded: every signal is a rolling-demeaned log spread, so the ratio
  constant, the GBp/GBP factor and any constant FX quoting error cancel exactly.
- Borrow / shortability: Alpaca `/v2/assets` **live** snapshot -- an executability bound
  applied forward, not a point-in-time borrow history.

## Windows -- FIXED NOW
- **DESIGN: 2016-01-04 .. 2021-12-31.** Every choice is made here.
- **HELD OUT: 2022-01-03 .. 2026-08-18.** Read **once**, after the design result is frozen
  to disk. Same split as T28 so the diversification comparison is apples to apples.

## Costs (T6/T8/M0/B22G conventions)
Per round trip, charged on **both** legs:
- half-spread x 2 crossings per leg, half-spread estimated per symbol per window by
  Corwin-Schultz on that symbol's own daily bars;
- SEC section 31 fee 0.278 bp on each of the two sales;
- borrow on the short leg at **33 bp/yr** (B22G easy-to-borrow general collateral) x holding
  period. Shorts are screened to `shortable and easy_to_borrow`. A hard-to-borrow sensitivity
  at 10.28%/yr (B22G) is reported, because HTB is exactly what killed dual-class to -45 bp.
- Cost-stress ladder x1.0 / x1.5 / x2.0 / x3.0 on the half-spread reported for every survivor.

## N and the noise bar
**N = 30 pre-registered formulas**, listed in `xl_formulas.py` before the run. Expected max
|t| under the null over N tries ~ sqrt(2 ln N) = **2.607** SE units. Because SE of an
annualised Sharpe ~ 1/sqrt(years), the design window's noise bar on annualised Sharpe is
2.607/sqrt(6.0) = **1.06**. A formula is a candidate only if its design Sharpe **clearly**
exceeds that AND its held-out number is positive net of costs.

The wider parameter grid run afterwards is reported as a **sign-stability surface**, not as a
selection device; nothing is chosen from it.

## Kill conditions, declared now
- Whole sub-family declared noise if no formula's design Sharpe exceeds 1.06.
- A design survivor that is held-out-negative net is reported dead, not re-tuned.
- The full result distribution of all 30 is reported, not just the best.
