# DEEPMINE: cross-listing / multi-ticker identical-claim RV

**2026-08-20. Verdict: the whole sub-family is NOISE, and the reason is structural, not marginal.**

30 pre-registered formulas. Design window 2016-01-04 .. 2021-12-31 (6.0 y). Held-out window
2022-01-03 .. 2026-08-18 (4.6 y), read once, after the design result was frozen and committed.

- **0 of 30** formulas are net-positive on the design window.
- **0 of 29** tradable formulas clear the noise bar on the design window **even at zero cost**.
- Held-out agrees: 1 of 30 is net-positive, at Sharpe 0.29 against a 1.22 bar, and that one
  (B15) was **negative in design** -- a coin flip that landed heads, not a survivor.

The noise bar: N = 30, so the expected maximum |t| under the null is sqrt(2 ln 30) = **2.607**
SE units, which on a 6.0-year design window is an annualised Sharpe of **1.065** (held-out,
4.6 y: **1.216**).

## The finding that matters: the spread is its own measurement error

This is not "the edge was there but costs ate it." At **zero** cost the best tradable formula
scores a gross Sharpe of **0.89** against a 1.065 bar, and the placebo books -- same machinery,
signal shuffled across names -- span -0.58 to +0.45. The real signals sit inside the placebo band.

The mechanism is measurable. If a spread series is `s = (slow true premium) + (iid measurement
error)`, the lag-1 autocorrelation of its daily **change** goes to **-0.50**. Measured:

| bloc | median rho1(ds) | median daily sd of ds |
|---|---:|---:|
| Canada (TSX/NYSE, identical session) | **-0.491** | 49 bp |
| Brazil | -0.425 | 102 bp |
| Mexico | -0.456 | 91 bp |
| UK | -0.481 | 88 bp |
| Continental Europe | -0.520 | 102 bp |
| Japan | -0.490 | 153 bp |
| Hong Kong | -0.440 | 312 bp |
| **Argentina** | **-0.180** | 211 bp |

Canada is the strongest possible case for this sub-family: TSX and NYSE open and close in the
same minute, the two lines are fully fungible, and arbitrageurs equalise them continuously. Its
measured spread still moves **49 bp a day** with rho1 = -0.49. The true premium of a fungible
interlisted pair moves by single-digit bp. **The free daily-close feed cannot see the effect at
all -- it sees its own error**, and fading that error is fading a number that exists in no price
anyone can transact at. Even the tightest names behave identically (BCE -0.52 at 27 bp, RY -0.51
at 30 bp), so this is not a liquidity screen away from working.

Argentina at rho1 = -0.18 is the one bloc carrying a genuinely persistent premium component --
the contado-con-liqui FX-control channel, which is a capital-control spread rather than a
convergence trade. Its costs (182 bp a rebalance) bury it: net -165 bp design, -178 bp held out.

## The trap this sub-family sets, quantified

**B9** is B1 with one change: it enters at the *same* close that generated the signal instead of
two closes later. That single change takes the design gross Sharpe from **-0.37 to +2.34**
(t = 5.6) -- comfortably over the bar, on a series that is otherwise nothing. An unguarded ADR
relative-value backtest reports that number as a discovery. It is an artefact of back-dating the
FX print and the home close by one session. (Its net is still -88 bp, so even the artefact does
not survive costs.)

Two further data-integrity failures were found and corrected before the verdict; both are written
up in the pre-registration amendments:

1. **Yahoo's FX daily bar close runs one FX day stale** against the equity bars (it is stamped
   23:00 UTC of the prior calendar day). Uncorrected, the spread carried a whole day of currency
   move -- RY/RY.TO measured 58 bp of daily "premium" change. Correcting it halves the noise
   (RY 58->29, VALE 160->73, ITUB 159->80; Japan correctly prefers no shift, as its home close is
   14 h before the US close). **The first design pass is void as evidence** -- it measured a
   corrupted spread -- and is kept only as `DEEPMINE_crosslist_DESIGN_v1_voided.json`.
2. **Corwin-Schultz was pricing crossings at exactly 0.00 bp** for high-volatility names, because
   the median of the zero-floored estimator is zero when CS is negative on over half the days.
   That is a zero where a measurement is missing. Fixed to mean-of-zero-floored, then floored
   again by a real point-in-time SIP NBBO measurement and by half a tick.

## What could and could not be traded

The account can only trade **US-listed** securities, so a genuine two-legged RV trade needs both
lines on a US tape. That is true for exactly **five** pairs with usable history -- CCL/CUK,
BBL/BHP, RDS.A/RDS.B, AMX/AMOV, PBR/PBR.A -- and three of them unified or delisted in or before
January 2022, so Family A's held-out window is thin by construction. All four Family A formulas
are negative in both windows (design -27 to -146 bp; held out -43 to -255 bp).

For the ADR-vs-home family the home leg is not tradable here, so the home price is used **as a
signal only** and every dollar of P&L comes from **US-listed adjusted closes**. That is also the
sweep's main lookahead guard: an error in the FX quote or the home timestamp can add noise to the
signal but cannot manufacture P&L, because no untradable price ever enters a return.

## Costs, measured

Half-spread charge = `max(Corwin-Schultz/2, measured point-in-time SIP NBBO/2, half a tick)`,
per symbol per window; median 22.9 bp (p25 12.7, p75 37.7), against a measured NBBO median of
3.6 bp -- the CS term binds almost everywhere and is the conservative one. Costs are
**turnover-aware**: `sum|dw| x half-spread` against the previous book, so a persistent signal
pays less than a full round trip. Borrow has three states: 167 names easy-to-borrow at 33 bp/yr
(B22G), 25 unknown (delisted today, or shortable but not ETB) charged at the **hard-to-borrow
10.28 %/yr** because absence is refusal and refusal is priced expensively, and 18 live-and-not-
shortable, excluded. SEC section 31 at 0.278 bp per sale.

## Data provenance and its limits

- US legs: Alpaca SIP daily bars, `raw` for signal levels, `all` for P&L. NBBO from SIP quote
  ticks, 18 sampled sessions across both windows.
- Home legs, FX, country ETFs: Yahoo chart API. **Stooq is unusable from this host** -- it serves
  a JS proof-of-work challenge, and it returns `Access denied` even after the PoW is solved.
- **The ADR <-> ordinary map is hand-curated.** No free machine-readable ADR directory is
  reachable from here. 164 of 179 mapped pairs resolved (60 Canada, 15 Brazil, 15 UK, 13 Hong
  Kong, 12 Europe, 12 Argentina, 7 Japan, and single digits elsewhere). It is a convenience
  sample with a survivorship tilt toward programmes that still exist, and that is a real
  limitation on the census, though not on the verdict -- the verdict rests on a measurement-noise
  statistic that every bloc shares.
- ADR ratios are deliberately not encoded: every signal is a rolling-demeaned log spread, so the
  ratio constant, the GBp/GBP factor and any constant FX quoting error cancel exactly.

## Full result distribution -- all 30 formulas, both windows

| id | universe | signal | h | design gross S | design net bp | design net S | held-out gross S | held-out net bp | held-out net S |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | US/US all pairs | L=250 K=2.0 mh=20 | 20 | -- | -110.79 | -1.90 | -- | -123.46 | -1.03 |
| A2 | US/US all pairs | L=120 K=1.5 mh=40 | 40 | -- | -114.50 | -2.06 | -- | -122.80 | -1.92 |
| A3 | US/US DLC only | L=250 K=2.0 mh=20 | 20 | -- | -145.66 | -2.60 | -- | -254.77 | -1.27 |
| A4 | US/US ADR-class only | L=250 K=2.0 mh=20 | 20 | -- | -27.09 | -0.20 | -- | -43.22 | -0.31 |
| B1 | CA | z L=60 | 1 | -0.37 | -120.58 | -10.33 | 0.40 | -103.46 | -10.12 |
| B2 | CA | z L=60 | 5 | -0.31 | -140.29 | -2.58 | 0.29 | -98.62 | -1.93 |
| B3 | CA | z L=250 | 5 | -0.10 | -125.41 | -2.32 | 0.31 | -94.90 | -1.84 |
| B4 | CA | z L=20 | 1 | 0.07 | -118.00 | -10.19 | 0.45 | -107.19 | -10.47 |
| B5 | CA | d1 | 1 | 0.65 | -146.16 | -11.68 | 1.29 | -133.98 | -12.44 |
| B6 | CA | dev L=60 | 5 | -0.36 | -152.27 | -2.42 | -0.21 | -124.66 | -2.34 |
| B7 | CA | z L=60 gate|z|>=1.5 | 5 | -0.84 | -131.44 | -3.01 | -2.51 | -198.02 | -5.28 |
| B8 | CA | z L=60 inv-vol | 5 | -0.79 | -119.29 | -3.32 | 0.21 | -84.12 | -2.25 |
| B9 | CA | z L=60 **t+0 LOOKAHEAD BOUND** | 1 | 2.34 | -87.75 | -7.17 | 1.31 | -93.92 | -8.95 |
| B10 | CA | ewma L=60 | 5 | -0.28 | -138.17 | -2.43 | 0.48 | -86.38 | -1.63 |
| B11 | BR+MX | z L=60 | 5 | -0.12 | -93.87 | -1.81 | 0.34 | -56.16 | -1.40 |
| B12 | BR+MX | z L=60 | 1 | -0.19 | -82.89 | -8.06 | -0.35 | -66.79 | -7.76 |
| B13 | full-overlap | z L=60 reg-neut | 5 | 0.26 | -93.10 | -2.38 | 0.31 | -83.10 | -2.11 |
| B14 | full-overlap | z L=250 reg-neut | 10 | -0.05 | -99.88 | -1.19 | 0.58 | -39.54 | -0.46 |
| B15 | Europe/IL | z L=60 | 5 | -0.04 | -39.23 | -1.17 | 1.60 | 9.35 | 0.29 |
| B16 | Europe/IL | z L=60 | 1 | 0.48 | -30.54 | -4.80 | 0.58 | -34.72 | -5.06 |
| B17 | Europe/IL | d1 | 1 | 0.03 | -50.29 | -6.39 | 0.04 | -56.88 | -7.23 |
| B18 | Asia/AU | z L=60 | 5 | 0.53 | -18.53 | -0.49 | 0.81 | -19.05 | -0.41 |
| B19 | Asia/AU | z L=60 | 1 | 0.40 | -29.26 | -4.00 | 0.53 | -44.51 | -4.60 |
| B20 | Asia/AU | d1 | 1 | -0.02 | -53.32 | -6.53 | 0.50 | -77.61 | -6.20 |
| B21 | all blocs | z L=60 reg-neut | 5 | 0.70 | -44.70 | -1.85 | 1.21 | -34.51 | -1.35 |
| B22 | all blocs | z L=60 reg-neut | 1 | 0.89 | -50.12 | -10.02 | 0.91 | -53.46 | -10.86 |
| B23 | all blocs | twoscale L=60 reg-neut | 5 | -0.09 | -53.79 | -2.04 | 0.82 | -37.86 | -1.57 |
| B24 | AR | z L=60 | 5 | 0.23 | -165.23 | -2.29 | 0.06 | -178.14 | -2.40 |
| B25 | CA | z L=60 gate|z|>=2.0 | 20 | -1.59 | -375.49 | -2.11 | -- | -- | -- |
| B26 | CA | z L=60 no-ETB-screen | 5 | -0.28 | -137.06 | -2.53 | 0.25 | -100.43 | -2.00 |

`B9` is the t+0 lookahead bound and is **not** a candidate; it is carried to price the artefact.
`B25`'s wide gate fires 6 times in design and never enough in held-out to score.

## Is anything diversifying versus the existing legs?

No. Nothing survived, so there is nothing to add to the ETF-sibling, CEF-discount or dual-class
legs. The one adjacent result worth carrying forward is negative and useful: the dual-class leg
(T28) works on **US/US** pairs where both closes come off the same tape at the same instant. The
moment a second venue, a second currency or a second timestamp enters the spread, the measurement
error swamps the effect on free daily data. That is a sharp boundary on where this whole family
can live.

## What would change the answer

Intraday quotes on **both** legs during the overlapping session -- TSX and NYSE 09:30-16:00 ET is
the natural laboratory, and Brazil's B3 is a second. The effect is real; it is roughly single-digit
bp and lives inside the session, which is precisely the resolution the free daily feed does not
have. This is the same wall the programme has already hit elsewhere: the edge is not absent, it is
below the resolution of free data. Nothing in this sub-family should be retried on daily closes.
