# FORWARD-CRYPTO v1 — forward paper LOGGER for the two crypto-perp results of FACTORY v2 (pre-registration)

**Author:** Claude (conductor, Fable 5.2). **Status:** FROZEN at the sha256 recorded in `DECISIONS.md`, before the
first forward row exists. Governed by this repo's iteration rule: a running rule is immutable; an improvement is a
new pre-registered test with its own ledger.

## 0. What this is and is not

A **logger**. Once a day it extends the crypto-perp panel with the day that just closed, recomputes each frozen
book's targets, simulates the fills at the pre-declared print with pre-declared costs, and appends rows to an
append-only, hash-chained ledger. It places **no orders**, holds **no keys**, touches **no account**. It reads
public market-data endpoints only. Every P&L number in it is hypothetical.

Why it exists: FACTORY v2 produced one PAPER-CANDIDATE that a post-hoc check showed to be fragile, and one rule
that stayed positive on its sealed holdout without passing (t 1.52). Backtests cannot separate "small real edge"
from "luck of the scaling path" here; only data that did not exist when the rules were frozen can.

## 1. The arms (all frozen; nothing is tuned after today)

Universe, data conventions, sizing and rule code are exactly those of FACTORY v2's `CRYPTO-PERP` lane
(`PREREGISTRATION_v2.md` §2–§3; rule grid sha `01ca21df…`): Binance USD-M perpetuals, point-in-time top 30 by
trailing-30-day quote volume, ≥ 60 days listed, live at the print, the same exclusions; decision on the daily
00:00 UTC close; execution at the 01:00 UTC price; funding accrued as realised.

| arm | book | role |
|---|---|---|
| `A60` | `P.CRYPTO.TREND` as scored in v2: the 20 CORE trend rules, equal-risk ensemble, book vol target 20 % with 60-print windows, gross cap 2×, 10 % no-trade band | the registered candidate |
| `A30`, `A120` | the same book with 30- and 120-print scaling windows | shadows: does the scaling window matter forward? (it moved the 2024–26 Sharpe from −0.04 to +1.27 in the backtest) |
| `A0` | the static mean of the 20 member books × a fixed factor 4.0, gross cap 2×, 10 % band | shadow: the trend signal without any volatility timing |
| `C252` | `XSMOM.HIGH_PROXIMITY.L252` (long the perps nearest their 252-print high, short the furthest, tercile) sized as in v2 × a fixed factor 8.0, gross cap 2×, 10 % band | the ALIVE-UNPROVEN survivor |

Each arm is logged as two accounts: **IDEAL** (every universe instrument, fractional sizes, 7 bp per side) and
**KRAKEN-5K** (only instruments Kraken Derivatives lists on the day the job runs, Kraken's lot precision, 5 bp
fee + 2 bp half-spread, starting equity USD 5,597 = EUR 5,000 at the ECB rate of 2026-11-09). Ten accounts.

## 2. Mechanics

- **Forward start:** the first daily 00:00 UTC row that closes AFTER this document's freeze time. Every account
  opens flat on that row and enters the book's then-current targets at that row's 01:00 UTC price, paying costs.
- **Daily run** (any time after 01:10 UTC): fetch from Binance's public REST the instrument list, daily and hourly
  candles and funding needed to extend the panel through the latest closed day; save every raw response with its
  URL, UTC fetch time and sha256; rebuild the extended panel with the data layer's own functions (the frozen v2
  panel is the history; it is never modified). Then re-simulate each account from the forward start with
  `realism.simulate_account` and append the new rows.
- **Immutability check:** a re-simulation must reproduce every row already in the ledger bit-for-bit (within
  1e-12). If it does not (a data revision upstream, or a code change), the run REFUSES to append, writes an
  incident file and stops; the ledger is never rewritten.
- **Missed days:** the rules are mechanical and the prints are final, so a late run backfills the missed rows with
  the same prints and marks them `backfilled: true`. No decision is ever taken with data later than its row.
- **Ledger:** `research/factory/forward/crypto_v1/ledger.jsonl`, one row per account per day: date, arm, account,
  equity, net and gross return, gross and net exposure, number of positions, turnover, fees, funding, the ten
  largest positions, the sha256 of the data snapshot, and `prev_hash`/`row_hash` forming a chain. A
  human-readable `STATUS.md` is regenerated each run.
- **Venue reality check (informational, never P&L):** at run time, Kraken's public tickers are fetched once and the
  price gap between Kraken and Binance is logged for the instruments held.

## 3. What may be read, and when

- **Any time:** operational parity — the gap between each KRAKEN-5K account and its IDEAL twin, cost per year,
  share of target exposure Kraken cannot hold, failed runs, data incidents.
- **Not before 60 daily rows:** any statement about performance. At 60 and at every further 30 rows `STATUS.md`
  reports, per arm, the realised return, volatility and Sharpe with a stationary-bootstrap 90 % interval, next to
  the backtest's distribution of n-day outcomes.
- **Pre-declared readings at 180 rows (about six months):**
  `A60` and `C252` are each called *consistent with a positive edge* if the IDEAL account's realised Sharpe is
  above 0 and its total return is above the 25th percentile of the backtest's 180-day outcomes; *contradicted* if
  total return is below the 5th percentile of those outcomes; *undecided* otherwise. The shadows are read only
  comparatively: if `A60` beats `A0` by less than the spread among `A30`/`A60`/`A120`, the volatility scaling is
  declared noise.
- **Stop rule:** an arm whose IDEAL account loses 30 % from its forward start is frozen (logged flat from then on)
  and recorded as failed.

## 4. Honest expectations, written before the first row

`A60`: Sharpe between 0 and 0.6; a negative first six months is entirely possible (the book was flat for 18 months
in 2022–23). `A0`: about 0.1–0.2. `C252`: unknown; its sealed-window Sharpe was 0.99 with t 1.52, and it has
never been traded with Kraken's instrument coverage. Six months of daily data can contradict a book; they cannot
prove one (a Sharpe of 0.5 needs about sixteen years for t = 2).

## 5. What a reading triggers

Nothing automatic. A book that is *consistent* at 180 rows becomes a candidate for a demo-API test with orders on
a venue the owner has opened; money, accounts and leverage remain the owner's decisions.
