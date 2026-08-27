# NEWTERR — Short interest & short volume on US equities — PRE-REGISTRATION

Written **before any design-window result exists**. Territory: FINRA consolidated short
interest (bi-monthly, 207 settlement dates, 3.9M rows) + FINRA Reg SHO daily short-sale
volume (2,020 sessions, 19.3M rows), both already on disk from T16. Prices from the
xll daily panel (3,812 US symbols, 2016-01-04..2026-08-14), split-adjusted from the
T7 corporate-actions cache.

This territory has not been swept by this programme. The exhausted families
(overnight equity, ETF same-index RV, cross-asset lead-lag, futures term structure,
generic calendar, perp funding/OI, CEF/dual-class/ADR RV) are not touched here.

## 0. Point-in-time discipline (the thing that kills this territory if got wrong)

- **Short interest is NOT available on its settlement date.** FINRA disseminates a
  settlement date roughly **8 business days** after it settles. The panel is a
  *backfill*: it carries revisions and has no first-seen stamp for 207 of 207 dates.
  The harness therefore keys every SI print to `avail_idx = settle_session + 8 sessions`
  and refuses to let any signal see it earlier. A backtest keyed to the settlement
  date is looking ~8 sessions into the future — that is the single largest artefact
  risk in this territory and it is closed by construction.
- **Reg SHO daily short volume for session D is a next-morning file.** The harness
  never lets session-D short volume be traded before the close of D+1.
- Backfilled SI carries revisions applied before the panel existed. Revisions are
  small in this file (2 revision observations across 209 snapshots) but they are a
  known, unremovable contaminant and are declared, not hidden.

## 1. Windows

| | |
|---|---|
| DESIGN | 2018-08-01 .. 2022-12-30 (first session Reg SHO exists .. year end) |
| HELD-OUT | 2023-01-03 .. 2026-08-14 — **not run until the design result is frozen** |

Warm-up of 250 sessions before the design start is used for rolling statistics only
(2016-2018 price history), never for scoring.

## 2. Universe (evaluated per session, from data known at that session)

- not flagged as an ETF / fund / ETN / warrant / unit / preferred by the FINRA
  `issueName` token screen (short interest on a creation-redemption vehicle is not
  crowded positioning; it is a hedge leg)
- close >= $5.00
- 20-session **geometric mean** dollar volume >= $10,000,000 (geometric rather than
  arithmetic mean so one print-volume spike cannot drag an illiquid name into the
  universe; cheaper than a rolling median on a 3812x2669 panel and equally robust)
  (this is also the easy-to-borrow
  screen: B22G measured every hard-to-borrow name in an active-stock pool as
  `shortable=false` at the broker, and HTB concentrates in illiquid microcaps)
- valid split-adjusted close on the signal day and at least 60 valid closes behind it
- Reg SHO row present on the signal day (for the daily family)

## 3. Portfolio construction (identical for every formula)

- score `x_i(t)` cross-sectionally ranked inside the day's universe; **top quintile
  long, bottom quintile short**, equal weight inside each leg, dollar-neutral,
  gross exposure 1.0 (0.5 long / 0.5 short)
- **entry at the CLOSE of session t+LAG**, `LAG = 1` in the base specification.
  The first return earned is session t+LAG+1. Holding `H` sessions, overlapping
  tranches, so the position on day u is `(1/H) * sum_{k=LAG+1}^{LAG+H} W(u-k)`.
- horizons `H ∈ {1, 5, 10, 21}` sessions

## 4. Costs — charged on every formula, both legs

| item | charge | provenance |
|---|---|---|
| one-way transaction cost | **4.0 bp of traded notional** | B22B measured median quoted spread 3 bp (p75 6 bp) and median entry slippage 0 on an active-stock pool; 1.5 bp half-spread + impact/fees, rounded up |
| borrow, easy-to-borrow | **60 bp/yr** on short-leg notional | B22G measured IBKR ETB fees on a real pool: p50 33 bp, p75 41 bp, p90 51 bp |
| borrow, crowded name | **1000 bp/yr** on short-leg notional when the name's published days-to-cover > 5.0 | B22G measured HTB p50 = 10.28 %/yr. Crowded-short names ARE the expensive borrows; a short-interest strategy that shorts them and does not pay for them is fiction |

Turnover is `sum_i |P_i(u) - P_i(u-1)|` each session. No shorting of names the
liquidity screen excludes. Dividends are not adjusted for; on a dollar-neutral
quintile book over 1-21 sessions this is second-order and cross-sectionally near-flat,
and it is declared rather than claimed to be zero.

## 5. The three gates, in order

**G0 — MECHANISM.** Every formula below carries a one-sentence causal claim naming who
is forced to trade or what friction bites. A formula with no mechanism, or a
mechanism the data disproves, is killed regardless of its t-stat.

**G1 — LAG-KILL.** Every design survivor is re-run at `LAG = 2` (one extra session
between signal and entry). A survivor must **retain >= 60% of its design Sharpe**.
Below that it is publish-lag / staleness / same-bar-fill and it is killed.

**G2 — STATISTICAL BAR.** N = number of (formula × horizon) design cells evaluated,
reported exactly. Pooled expected max |t| under the null is `sqrt(2 ln N)`. A design
cell is promoted to the hold-out only if
`|t_design| > sqrt(2 ln N) + 0.5` **and** net-of-cost mean return has the sign the
mechanism predicts **and** it passes G1. t-stats are **Newey-West** with lag `H+1`
because the overlapping tranches induce autocorrelation.

**VERDICT.** A formula is real only if, in the untouched hold-out window, its net
Sharpe is positive in the same direction with |t| > 1.5. Anything else — including a
design cell with a spectacular t that dies on the hold-out — is reported as noise.

## 6. Formula roster (mechanism stated up front)

SI family — mechanism: *published crowding tells you who is positioned and how many
days of volume it takes them to get out; forced covering is a real flow.*

| id | formula | sign claim |
|---|---|---|
| S01 | -published days-to-cover | short sellers are informed; follow them (short crowded) |
| S02 | -(short position / live 20d share ADV) | same, with a non-stale denominator |
| S03 | -(SI_t / SI_prev - 1) | shorts *adding* is the informed flow, not the level |
| S04 | -(SI_t - SI_prev)/ADV20 | the same change in units of days-to-cover |
| S05 | -(ΔSI_t - ΔSI_{t-1}) | acceleration of short building |
| S06 | -z(SI over own last 12 prints) | crowding relative to the name's own history |
| S07 | +DTC rank, only where 20d return > 0 | squeeze fuel: crowded shorts in a rising name are the forced buyers |
| S08 | +DTC rank, only where 20d return < 0 | covering-exhaustion bounce in a crowded loser |
| S09 | -z(DTC) x z(ret20) | shorts pressing a loser keeps working |
| S10 | -z(ΔSI) x z(ret20) | same interaction on the flow rather than the level |
| S11 | -(DTC_t - DTC_{t-1}) | change in the cover-time itself |
| S12 | -(SI x price)/20d dollar ADV | dollar crowding, size-neutral |

Reg SHO daily family — mechanism: *the short-volume share is a daily read on
market-maker inventory and directional short flow between the bi-monthly prints.*

| id | formula | sign claim |
|---|---|---|
| S13 | -1d short-volume ratio | heavy shorting today is informed flow |
| S14 | -5d mean short-volume ratio | the smoothed version |
| S15 | -(5d SVR - 60d SVR) | short-flow momentum, name-demeaned by construction |
| S16 | -z20(SVR) | today's SVR spike vs the name's own 20d |
| S17 | -(5d SVR - 250d SVR) | slow-demeaned; removes the permanent MM component |
| S18 | +z20(SVR) | opposite sign: MM inventory absorbs a spike and it reverts |
| S19 | -z20(SVR) x z(ret1) | shorting into strength vs into weakness are different trades |
| S20 | +z(5d SVR) where ret5 < 0 | shorts pressed a loser → covering bounce |
| S21 | +z(5d SVR) where ret5 > 0 | a rally *with* short fuel keeps going; without it, no fuel |
| S22 | -10d OLS slope of SVR | the trend rather than the level |
| S23 | +z(5d short-exempt ratio) | Rule 201 short-sale-circuit-breaker names are already down and constrained |
| S24 | +1{1d exempt ratio > 3x its 60d mean} | discrete SSR-trigger event |

Venue family — mechanism: *the FINRA file covers off-exchange + TRF prints, so
(FINRA total / consolidated volume) is a clean free read on internalised retail share.*

| id | formula | sign claim |
|---|---|---|
| S25 | -z(5d off-exchange share) | retail-dominated tape is the fade side |
| S26 | -(5d offex - 60d offex) | the momentum version |
| S27 | -z(offex) x z(ret5) | retail chasing is the fade |
| S28 | +z(non-short off-exchange notional / dollar ADV) | internalised *buy* pressure |

Cross-family — mechanism: *published crowding tells you the stock of shorts; daily
short volume since that print tells you whether they are still adding or covering.*

| id | formula | sign claim |
|---|---|---|
| S29 | +z(DTC) x -z(SVR since last settlement) | crowded AND covering → long |
| S30 | -z(cumulative net short volume since last settlement / ADV20) | shorts building between prints |
| S31 | -z(live DTC - published DTC) | the staleness correction is itself the signal |

31 formulas x 4 horizons = 124 design cells. `sqrt(2 ln 124) = 3.10`.
This is the bar. It is written down before the first number exists.

## 7. What "the territory is noise" looks like

If no cell clears |t| = 3.10 + 0.5 on the design window, or every cell that clears it
loses more than 40% of its Sharpe under the extra lag, or every promoted cell dies on
the hold-out, the honest report is: **short interest and short volume on free FINRA
data do not carry a tradable cross-sectional edge net of borrow at this horizon.**
That is a publishable result for this programme and it will be reported as such.
