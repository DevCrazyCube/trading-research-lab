# FASTMOM v1 — minute-scale momentum on the three most liquid crypto perps (pre-registration)

**Author:** Claude (conductor, Fable 5.2). **Written:** 2026-11-10 (UTC time of freeze recorded in `DECISIONS.md`
with this file's sha256). **Status:** FROZEN before any minute bar is loaded. Separate from FACTORY v2: its own
question, its own trial count, its own windows.

**Owner question (2026-11-10):** "why wouldn't we just be able to short term / momentum trading — buying and
selling within minutes?" This tests exactly that — buy what is moving, sell within minutes — on the venue where it
has the best chance: the deepest perps, the lowest retail fee, long and short.

**Prior evidence in this repo (stated before the run):** minute-scale and intraday momentum has failed here on
memecoins (momentum entry −9.05 % vs +0.63 % random; the owner's fast scalp −11.8 %/trade over 322 trades), on US
equities (dead at zero cost) and in a practitioner set on Binance (12/20 profitable at zero fees, 1/20 with fees).
Expectation: gross per-trade edge of 0–3 bp against a 10–11 bp round trip, so net negative everywhere. If that is
wrong, this test will show it.

## 1. Data

Binance USD-M perpetuals `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, 1-minute klines from the public archive
(`data.binance.vision`, monthly zips, each verified against its published `.CHECKSUM`), 2021-01-01 → 2026-10-31.
Bars are open-time stamped; a signal computed from the bar that CLOSES at minute t is acted on at the OPEN of the
next bar. Zero-volume bars are no-trade bars. Realised funding is ignored (holding periods are minutes; funding
is paid only by positions open across an 8-hourly timestamp and is second-order here — stated as a limit).

Design window 2021-01-01 → 2023-12-31. Holdout 2024-01-01 → 2026-10-31, read once, only for formulas that pass
the design rule.

## 2. Costs (from `landscape/venues.json`, Kraken Derivatives EEA; measured half-spreads of 2026-11-10)

Per side: taker fee 5.0 bp + half-spread BTC 0.07 / ETH 0.24 / SOL 0.60 bp. Round trip ≈ 10.1 / 10.5 / 11.2 bp.
Also reported for every formula: the result at ZERO cost (gross), and the breakeven cost per side. A "maker"
row at 2.0 bp per side with no spread is reported as an OPTIMISTIC BOUND only: it assumes every passive order
fills and ignores adverse selection, which cannot be measured from bars.

## 3. Formulas (43 per symbol, 129 formula-symbol pairs; nothing else is run)

σ_k = the trailing 1,440-bar (24 h) standard deviation of k-minute returns, known at the signal bar.

- **M1 — momentum burst, fixed hold (36):** if the last k-minute return > +x·σ_k go long, if < −x·σ_k go short;
  enter at the next bar's open; exit at the open h minutes later; k ∈ {1, 5, 15}, x ∈ {1, 2, 3},
  h ∈ {1, 5, 15, 60}. One position at a time per formula-symbol; signals during an open position are ignored.
- **M2 — minute breakout with a trailing stop (4):** go long on a close above the highest high of the previous N
  bars (short below the lowest low), N ∈ {30, 120}; exit when price retraces y·σ_5 from the best price since
  entry, y ∈ {1, 2}, or after 60 minutes. Stops are evaluated on each bar's high/low and filled AT THE STOP LEVEL
  if the bar opens beyond it, at the open (gap-through is paid).
- **M3 — scalp with take-profit and stop-loss (3):** entry as M1 with k = 5, x = 2; exit at +a·σ_5 (take-profit) or
  −b·σ_5 (stop-loss) or after 30 minutes, (a, b) ∈ {(1, 1), (2, 1), (1, 2)}. If a bar's range touches both levels,
  the STOP is assumed to fill first (pessimistic ordering).

## 4. Statistics and the decision rule

Per formula-symbol: number of trades, win rate, mean and median net return per trade (bp), mean gross per trade
(bp), breakeven cost per side (bp), total net return, Sharpe of the daily P&L (a day with no trade = 0), and a
t-statistic of the mean net per trade clustered by UTC day.

**Design pass:** mean net per trade > 0 with day-clustered t ≥ 3.0 AND the Benjamini–Hochberg test at q = 10 %
over all 129 pairs rejects it. **Holdout (one shot, passers only):** PASS = mean net per trade > 0 with
day-clustered t ≥ 2.0. Everything else is DEAD at this cost. The full ledger (129 rows, design; passers' holdout)
is written whatever the outcome, with the gross rows, so "the signal exists but the fee eats it" and "there is no
signal" can be told apart.

## 5. What a result means

A PASS would be the first evidence in this repository that a minutes-scale rule survives real fees, and would go
to a forward paper test on a demo API before anything else. No pass means: at 5 bp per side on the deepest perps,
buying and selling within minutes loses to the fee — and the gross rows say by how much.
