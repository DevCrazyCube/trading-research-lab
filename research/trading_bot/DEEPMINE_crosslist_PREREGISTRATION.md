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

---

## AMENDMENT 1 (2026-08-20, before any Family-B design result was read)

**A one-hour lookahead was found in the signal and closed.**

Yahoo's `<CCY>USD=X` daily bar closes at ~17:00 ET, one hour *after* the 16:00 ET equity
close. The spread `log(P_us) - log(P_home) - log(FX)` therefore embedded the last hour of
currency tape. That is not harmless here: a Canadian company's USD-quoted ADR mechanically
rises when CAD strengthens, so an FX print taken an hour after the close genuinely predicts
the next US-session return of the ADR. It could have manufactured P&L, not merely added noise.

**Fix, applied to every Family-B formula:** `entry_lag = 1`. The signal is computed from the
closes of day *t* and the book is entered at the close of day *t+1*, so every input --
US close, home close, FX print -- is strictly in the past at the moment of trading.

`B9` is repurposed as the **t+0 optimistic bound**: same formula, entered at the close that
generated it. It is explicitly *not tradable* and exists only to price what the lag costs.

N is unchanged at 30. The windows are unchanged. No design result had been read for the
Canadian, European or Latin-American blocs when this amendment was made; the only numbers
seen were harness smoke tests on the Asian bloc, which were deeply negative net of costs and
from which nothing was selected. The amendment makes every formula strictly more conservative.

## AMENDMENT 2 (same sitting): two cost-model corrections

1. **Corwin-Schultz median -> mean.** The first implementation took the median of the
   zero-floored CS series. For a high-volatility name CS is negative on more than half of
   days, so the median was exactly **0.00 bp** -- a free crossing, which is the one cost
   failure this programme has a written rule against. Now: mean of the zero-floored series
   (the estimator's own convention), and the charge is
   `max(CS/2, measured-NBBO/2, half-a-tick)` -- three independent lower bounds, largest wins.
   The NBBO term is a real point-in-time SIP quote measurement sampled *inside the same
   window* (`xl_quotes.py`, 18 sessions, 60s at 19:55-19:56Z).
2. **Borrow has three states, not two.** A live `/v2/assets` snapshot cannot say what a
   delisted ticker's borrow was in 2018, and reading `inactive` as `not shortable` silently
   deletes exactly the pairs this study exists to test (CUK, BBL, RDS.A/B, AMOV are all
   inactive today). So: `etb` -> 33 bp/yr; `unknown` (delisted, or shortable-but-not-ETB)
   -> charged the **hard-to-borrow 10.28 %/yr**, because absence is refusal and refusal is
   priced expensively rather than at zero; `htb` (live and flagged not-shortable) -> excluded.
3. **Turnover-aware spreads.** Cost is now `sum|dw| x half-spread` against the previous
   book, not a full round trip every period. A complete rebuild reproduces the old number
   exactly; a persistent signal pays less. This matters most at h=1, where the old model
   charged ~50 bp a day.
