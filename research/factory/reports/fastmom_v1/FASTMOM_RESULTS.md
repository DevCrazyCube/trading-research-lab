# FASTMOM v1 — results: minute-scale momentum on BTC / ETH / SOL perps at real fees

**Generated** 2026-11-10T19:12:55Z by `scripts/factory/fastmom.py report` (module sha256 `72b810a95ff76f0d840447d39376a5e907df3a023ad9c0f42c11d86a00ff2d46`). Engineer and analyst: Claude, model ID `claude-fable-5-2`.  
**Spec:** `research/factory/FASTMOM_PREREGISTRATION.md`, sha256 `340b178b79d23fabd4c12939c68cfaebf91c3740a95e875623906e549e284f24`, frozen 2026-11-10 18:09 UTC (DECISIONS.md) and not edited; every stage re-hashes it and refuses on a mismatch.  
**Design passers frozen** 2026-11-10T18:44:54Z: `runs/fastmom_v1/DESIGN_PASSERS.json`, sha256 `2a8e0f670c65a8f46a3ceac769e957fcd8e7f8896e586609be6e789e51cd5d32` (0 passers). The code parses no bar after 2023-12-31 until that file exists.  
Research / paper only. No orders, keys, accounts or spend.

Labels used below: **[fact]** a number this code produced from the checksum-verified archive files; **[reading]** how an open point of the pre-registration was resolved (section 10); **[interpretation]** my judgement, not a measurement.

## 1. Verdict

**DEAD at this cost. No formula passes the design rule, none has a positive average return after costs, and none comes close.** [fact] On the design window (2021-01-01 → 2023-12-31) the 129 formula-symbol pairs made 6,400,436 simulated trades. After the round-trip cost all 129 lose on average: the best pair loses 6.90 bp per trade (ETHUSDT M1.k15.x3.h60), the median pair loses 11.02 bp — the typical formula hands over the whole round trip (10.14–11.20 bp) and a little more. Before any cost the average trade makes between -6.00 and +3.58 bp depending on the formula (median -0.36 bp; for the 108 fixed-hold pairs the median size of the gross mean is 0.45 bp). The median break-even cost is -0.18 bp per side against the 5.07–5.60 bp charged. 33 of 129 pairs are positive before costs, but only 1 of them is statistically distinguishable from zero on the right side (SOLUSDT M1.k1.x1.h1: +0.21 bp per trade, t = 3.6, 280,795 trades) — 52 times smaller than its own round-trip cost, and in the descriptive 2024–2026 table the same pair is -0.18 bp (t = -5.3) — while 14 of the 108 fixed-hold pairs are significantly NEGATIVE before costs (t ≤ −3) — at these horizons a burst is more often partly given back than continued — and 21 of the 21 stop-based pairs are negative before costs: the trailing-stop pairs mostly because of the pessimistic intrabar ordering (median drag -3.80 bp, median directional edge -0.30 bp), the target/stop pairs because following the burst did no better than fading it (median drag -0.51 bp, median edge -0.84 bp; section 8.2). Under the optimistic maker bound (2 bp per side, every passive order assumed filled, no adverse selection) 0 of 129 are positive. Because no pair passed, no formula earned the one-shot holdout read. The descriptive 2024-01 → 2026-10 table (not evidence; computed only after the passers file was frozen) says the same, a little worse: 10 of 129 positive before costs, 0 after, best -9.77 bp per trade. The pre-registration expected a gross edge of 0–3 bp against a 10–11 bp round trip; the measured gross is lower than that expectation and the net conclusion is the one it predicted. [interpretation] In plain words: buying what is moving and selling within minutes does not fail here because of a badly chosen stop or parameter. It fails because, once the bar that shows the move has closed, what is left to catch is a fraction of a basis point — more often against you than for you — and the fee to try is ten.

## 2. What was run

| Item | Value |
| :--- | :--- |
| Data | Binance USD-M perpetual 1-minute klines, public archive `data.binance.vision`, 210 monthly zips (3 symbols × 70 months, 2021-01 → 2026-10), 376.5 MB, every zip sha256-verified against its published `.CHECKSUM` (fetched 2026-11-10T18:22:08Z → 2026-11-10T18:24:55Z) |
| Design window | 2021-01-01 → 2023-12-31: 1,095 days, 1,576,800 minutes per symbol |
| Holdout window | 2024-01-01 → 2026-10-31: 1,035 days, 1,490,400 minutes per symbol (December 2023 is loaded as warm-up only) |
| Cost per side | taker 5.0 bp + half-spread: BTC 5.07 bp, ETH 5.24 bp, SOL 5.60 bp → round trip 10.14 / 10.48 / 11.20 bp |
| Formulas | 43 per symbol = 129 pairs: M1 burst + fixed hold (36), M2 breakout + trailing stop (4), M3 scalp with target and stop (3). Nothing else enters the decision. |
| Timing | signal from the bar that closes at minute t → filled at the OPEN of bar t+1; one position at a time per pair; entry and exit each pay the per-side cost; returns are simple returns on notional |
| Trades simulated | design 6,400,436; holdout (descriptive) 6,251,540 |

## 3. Design window — every formula-symbol pair

Columns: **Trades**; **Win %** = share of trades that make money AFTER costs; **Gross** = mean bp per trade before costs; **Net** = mean bp per trade after the round trip; **Break-even** = gross / 2 = the per-side cost at which the pair would just break even (charged: BTC 5.07, ETH 5.24, SOL 5.60); **t (net)** = t-statistic of the mean net per trade, clustered by UTC day; **Sharpe** = annualised (√365) Sharpe of the daily net P&L, a day with no trade = 0; **t (gross)** = the same clustered t for the gross mean, i.e. whether there is any signal at zero cost. Formula names: `M1.k5.x2.h15` = 5-minute return beyond 2 σ₅, hold 15 minutes; `M2.N30.y1` = 30-bar breakout, trail 1 σ₅; `M3.a2.b1` = target 2 σ₅, stop 1 σ₅.

### 3.1 M1 — momentum burst, fixed hold (108 pairs)

| Pair | Trades | Win % | Gross bp | Net bp | Break-even bp/side | t (net) | Sharpe (daily, ann.) | t (gross) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC M1.k1.x1.h1 | 256,308 | 11.6 | -0.02 | -10.16 | -0.01 | -329.8 | -72.0 | -0.8 |
| BTC M1.k1.x1.h5 | 141,630 | 21.8 | -0.16 | -10.30 | -0.08 | -142.2 | -62.5 | -2.2 |
| BTC M1.k1.x1.h15 | 71,335 | 28.8 | -0.49 | -10.63 | -0.25 | -66.4 | -37.0 | -3.1 |
| BTC M1.k1.x1.h60 | 23,119 | 36.5 | -0.68 | -10.82 | -0.34 | -22.7 | -13.1 | -1.4 |
| BTC M1.k1.x2.h1 | 62,858 | 16.4 | -0.02 | -10.16 | -0.01 | -143.9 | -40.7 | -0.3 |
| BTC M1.k1.x2.h5 | 44,320 | 25.3 | -0.26 | -10.40 | -0.13 | -61.9 | -30.4 | -1.6 |
| BTC M1.k1.x2.h15 | 29,666 | 30.7 | -0.36 | -10.50 | -0.18 | -38.0 | -21.6 | -1.3 |
| BTC M1.k1.x2.h60 | 14,267 | 36.5 | -1.25 | -11.39 | -0.62 | -17.3 | -9.9 | -1.9 |
| BTC M1.k1.x3.h1 | 19,937 | 20.7 | +0.10 | -10.04 | +0.05 | -59.4 | -24.4 | +0.6 |
| BTC M1.k1.x3.h5 | 15,357 | 28.7 | -0.18 | -10.32 | -0.09 | -29.4 | -16.2 | -0.5 |
| BTC M1.k1.x3.h15 | 11,670 | 33.0 | +0.78 | -9.36 | +0.39 | -16.9 | -9.8 | +1.4 |
| BTC M1.k1.x3.h60 | 7,314 | 36.8 | -0.25 | -10.39 | -0.12 | -9.6 | -5.5 | -0.2 |
| BTC M1.k5.x1.h1 | 215,160 | 12.0 | -0.12 | -10.26 | -0.06 | -362.2 | -66.7 | -4.2 |
| BTC M1.k5.x1.h5 | 111,796 | 21.4 | -0.64 | -10.78 | -0.32 | -135.8 | -54.2 | -8.1 |
| BTC M1.k5.x1.h15 | 60,822 | 28.4 | -0.70 | -10.84 | -0.35 | -67.6 | -37.1 | -4.3 |
| BTC M1.k5.x1.h60 | 21,539 | 35.9 | -0.50 | -10.64 | -0.25 | -21.2 | -12.3 | -1.0 |
| BTC M1.k5.x2.h1 | 50,675 | 17.3 | -0.18 | -10.32 | -0.09 | -112.3 | -35.8 | -2.0 |
| BTC M1.k5.x2.h5 | 30,020 | 25.1 | -1.20 | -11.34 | -0.60 | -53.7 | -25.6 | -5.7 |
| BTC M1.k5.x2.h15 | 20,796 | 30.2 | -1.30 | -11.44 | -0.65 | -30.2 | -17.1 | -3.4 |
| BTC M1.k5.x2.h60 | 11,217 | 36.5 | -0.64 | -10.78 | -0.32 | -13.5 | -7.8 | -0.8 |
| BTC M1.k5.x3.h1 | 16,731 | 21.0 | -0.41 | -10.55 | -0.21 | -46.9 | -20.2 | -1.8 |
| BTC M1.k5.x3.h5 | 10,070 | 28.6 | -1.32 | -11.46 | -0.66 | -26.2 | -14.0 | -3.0 |
| BTC M1.k5.x3.h15 | 7,737 | 32.5 | -1.57 | -11.71 | -0.79 | -16.2 | -9.2 | -2.2 |
| BTC M1.k5.x3.h60 | 5,260 | 36.2 | -2.74 | -12.88 | -1.37 | -9.4 | -5.4 | -2.0 |
| BTC M1.k15.x1.h1 | 199,361 | 12.5 | -0.12 | -10.26 | -0.06 | -358.8 | -63.9 | -4.1 |
| BTC M1.k15.x1.h5 | 91,986 | 22.3 | -0.44 | -10.58 | -0.22 | -138.0 | -56.3 | -5.8 |
| BTC M1.k15.x1.h15 | 48,884 | 28.0 | -1.03 | -11.17 | -0.51 | -63.4 | -33.5 | -5.8 |
| BTC M1.k15.x1.h60 | 19,189 | 35.1 | -1.33 | -11.47 | -0.66 | -21.2 | -12.2 | -2.5 |
| BTC M1.k15.x2.h1 | 48,397 | 18.1 | -0.11 | -10.25 | -0.05 | -123.0 | -35.2 | -1.3 |
| BTC M1.k15.x2.h5 | 23,375 | 26.9 | -0.51 | -10.65 | -0.25 | -46.9 | -23.6 | -2.2 |
| BTC M1.k15.x2.h15 | 13,935 | 30.9 | -1.45 | -11.59 | -0.73 | -26.2 | -14.6 | -3.3 |
| BTC M1.k15.x2.h60 | 8,089 | 35.8 | -1.59 | -11.73 | -0.79 | -11.1 | -6.4 | -1.5 |
| BTC M1.k15.x3.h1 | 17,207 | 21.8 | -0.04 | -10.18 | -0.02 | -57.1 | -22.0 | -0.2 |
| BTC M1.k15.x3.h5 | 8,292 | 30.6 | -0.31 | -10.45 | -0.16 | -21.3 | -11.9 | -0.6 |
| BTC M1.k15.x3.h15 | 4,983 | 34.4 | -0.02 | -10.16 | -0.01 | -10.6 | -6.0 | -0.0 |
| BTC M1.k15.x3.h60 | 3,495 | 36.9 | +0.26 | -9.88 | +0.13 | -5.4 | -3.1 | +0.1 |
| ETH M1.k1.x1.h1 | 266,087 | 14.5 | -0.03 | -10.51 | -0.02 | -304.1 | -73.9 | -1.0 |
| ETH M1.k1.x1.h5 | 146,418 | 25.1 | -0.13 | -10.61 | -0.07 | -138.5 | -64.4 | -1.7 |
| ETH M1.k1.x1.h15 | 73,153 | 32.1 | +0.14 | -10.34 | +0.07 | -58.6 | -33.3 | +0.8 |
| ETH M1.k1.x1.h60 | 23,359 | 38.5 | -0.30 | -10.78 | -0.15 | -17.9 | -10.4 | -0.5 |
| ETH M1.k1.x2.h1 | 63,667 | 19.4 | +0.10 | -10.38 | +0.05 | -124.1 | -40.3 | +1.2 |
| ETH M1.k1.x2.h5 | 45,140 | 28.6 | +0.23 | -10.25 | +0.11 | -54.7 | -28.1 | +1.2 |
| ETH M1.k1.x2.h15 | 30,235 | 34.4 | +0.94 | -9.54 | +0.47 | -29.6 | -17.0 | +2.9 |
| ETH M1.k1.x2.h60 | 14,503 | 39.1 | +1.34 | -9.14 | +0.67 | -11.6 | -6.7 | +1.7 |
| ETH M1.k1.x3.h1 | 19,030 | 23.2 | -0.09 | -10.57 | -0.04 | -54.0 | -23.5 | -0.4 |
| ETH M1.k1.x3.h5 | 14,806 | 31.5 | +0.64 | -9.84 | +0.32 | -22.1 | -12.6 | +1.4 |
| ETH M1.k1.x3.h15 | 11,348 | 35.6 | +0.64 | -9.84 | +0.32 | -13.9 | -8.1 | +0.9 |
| ETH M1.k1.x3.h60 | 7,157 | 39.0 | +1.51 | -8.97 | +0.75 | -7.0 | -4.1 | +1.2 |
| ETH M1.k5.x1.h1 | 222,158 | 14.9 | -0.07 | -10.55 | -0.03 | -326.8 | -69.3 | -2.1 |
| ETH M1.k5.x1.h5 | 115,227 | 24.7 | -0.54 | -11.02 | -0.27 | -109.5 | -49.5 | -5.4 |
| ETH M1.k5.x1.h15 | 62,476 | 31.5 | -0.23 | -10.71 | -0.11 | -58.3 | -32.7 | -1.2 |
| ETH M1.k5.x1.h60 | 21,794 | 38.6 | +0.35 | -10.13 | +0.18 | -16.4 | -9.4 | +0.6 |
| ETH M1.k5.x2.h1 | 51,057 | 20.4 | +0.04 | -10.44 | +0.02 | -100.9 | -35.9 | +0.4 |
| ETH M1.k5.x2.h5 | 30,282 | 28.2 | -0.80 | -11.28 | -0.40 | -48.2 | -24.2 | -3.4 |
| ETH M1.k5.x2.h15 | 21,116 | 33.9 | +0.47 | -10.01 | +0.24 | -22.6 | -13.0 | +1.1 |
| ETH M1.k5.x2.h60 | 11,451 | 38.5 | +0.09 | -10.39 | +0.04 | -10.9 | -6.3 | +0.1 |
| ETH M1.k5.x3.h1 | 16,343 | 23.7 | -0.07 | -10.55 | -0.04 | -48.6 | -21.2 | -0.3 |
| ETH M1.k5.x3.h5 | 9,919 | 31.5 | -1.13 | -11.61 | -0.57 | -20.5 | -11.2 | -2.0 |
| ETH M1.k5.x3.h15 | 7,707 | 35.4 | +0.25 | -10.23 | +0.12 | -12.1 | -7.0 | +0.3 |
| ETH M1.k5.x3.h60 | 5,218 | 39.2 | +0.84 | -9.64 | +0.42 | -5.9 | -3.4 | +0.5 |
| ETH M1.k15.x1.h1 | 204,521 | 15.3 | -0.07 | -10.55 | -0.03 | -282.2 | -65.3 | -1.8 |
| ETH M1.k15.x1.h5 | 94,164 | 25.3 | -0.21 | -10.69 | -0.11 | -99.1 | -47.4 | -2.0 |
| ETH M1.k15.x1.h15 | 49,898 | 31.1 | -0.45 | -10.93 | -0.22 | -45.0 | -25.1 | -1.8 |
| ETH M1.k15.x1.h60 | 19,475 | 38.5 | +0.49 | -9.99 | +0.25 | -14.5 | -8.4 | +0.7 |
| ETH M1.k15.x2.h1 | 48,634 | 20.9 | -0.10 | -10.58 | -0.05 | -105.2 | -35.4 | -1.0 |
| ETH M1.k15.x2.h5 | 23,462 | 29.9 | -0.17 | -10.65 | -0.08 | -40.5 | -21.4 | -0.6 |
| ETH M1.k15.x2.h15 | 14,076 | 33.3 | -0.84 | -11.32 | -0.42 | -21.3 | -11.9 | -1.6 |
| ETH M1.k15.x2.h60 | 8,272 | 38.7 | +0.97 | -9.51 | +0.49 | -7.5 | -4.3 | +0.8 |
| ETH M1.k15.x3.h1 | 16,516 | 24.0 | -0.11 | -10.59 | -0.06 | -51.1 | -21.4 | -0.5 |
| ETH M1.k15.x3.h5 | 8,033 | 32.7 | -1.06 | -11.54 | -0.53 | -14.3 | -7.9 | -1.3 |
| ETH M1.k15.x3.h15 | 4,904 | 36.2 | -1.31 | -11.79 | -0.65 | -10.6 | -6.0 | -1.2 |
| ETH M1.k15.x3.h60 | 3,477 | 40.1 | +3.58 | -6.90 | +1.79 | -3.3 | -1.9 | +1.7 |
| SOL M1.k1.x1.h1 | 280,795 | 20.7 | +0.21 | -10.99 | +0.11 | -187.1 | -69.4 | +3.6 |
| SOL M1.k1.x1.h5 | 153,963 | 32.0 | -0.01 | -11.21 | -0.00 | -83.2 | -43.7 | -0.1 |
| SOL M1.k1.x1.h15 | 75,662 | 38.3 | +0.10 | -11.10 | +0.05 | -39.2 | -22.3 | +0.4 |
| SOL M1.k1.x1.h60 | 23,632 | 43.3 | +1.10 | -10.10 | +0.55 | -11.1 | -6.4 | +1.2 |
| SOL M1.k1.x2.h1 | 66,187 | 25.7 | +0.38 | -10.82 | +0.19 | -72.4 | -32.5 | +2.5 |
| SOL M1.k1.x2.h5 | 47,983 | 34.6 | +0.36 | -10.84 | +0.18 | -34.8 | -19.4 | +1.2 |
| SOL M1.k1.x2.h15 | 32,092 | 38.4 | -0.58 | -11.78 | -0.29 | -24.7 | -14.0 | -1.2 |
| SOL M1.k1.x2.h60 | 15,168 | 43.3 | +1.36 | -9.84 | +0.68 | -7.7 | -4.5 | +1.1 |
| SOL M1.k1.x3.h1 | 18,811 | 29.5 | +0.15 | -11.05 | +0.07 | -29.8 | -15.5 | +0.4 |
| SOL M1.k1.x3.h5 | 15,013 | 36.2 | +0.04 | -11.16 | +0.02 | -15.8 | -8.9 | +0.1 |
| SOL M1.k1.x3.h15 | 11,678 | 39.1 | -1.27 | -12.47 | -0.64 | -10.7 | -6.1 | -1.1 |
| SOL M1.k1.x3.h60 | 7,419 | 41.7 | -0.59 | -11.79 | -0.29 | -5.7 | -3.3 | -0.3 |
| SOL M1.k5.x1.h1 | 237,863 | 20.7 | +0.06 | -11.14 | +0.03 | -210.9 | -66.1 | +1.2 |
| SOL M1.k5.x1.h5 | 122,447 | 31.7 | -0.32 | -11.52 | -0.16 | -77.5 | -39.1 | -2.2 |
| SOL M1.k5.x1.h15 | 65,715 | 37.8 | -0.30 | -11.50 | -0.15 | -35.1 | -19.9 | -0.9 |
| SOL M1.k5.x1.h60 | 22,363 | 43.4 | +1.64 | -9.56 | +0.82 | -9.7 | -5.6 | +1.7 |
| SOL M1.k5.x2.h1 | 52,324 | 25.7 | -0.23 | -11.43 | -0.12 | -73.8 | -30.8 | -1.5 |
| SOL M1.k5.x2.h5 | 31,610 | 33.9 | -0.77 | -11.97 | -0.39 | -33.6 | -18.1 | -2.2 |
| SOL M1.k5.x2.h15 | 22,309 | 38.6 | +0.26 | -10.94 | +0.13 | -15.7 | -9.0 | +0.4 |
| SOL M1.k5.x2.h60 | 11,819 | 42.4 | +0.07 | -11.13 | +0.04 | -7.2 | -4.2 | +0.0 |
| SOL M1.k5.x3.h1 | 14,927 | 29.3 | -0.97 | -12.17 | -0.49 | -25.7 | -13.2 | -2.1 |
| SOL M1.k5.x3.h5 | 9,372 | 35.3 | -2.24 | -13.44 | -1.12 | -13.6 | -7.5 | -2.3 |
| SOL M1.k5.x3.h15 | 7,423 | 37.7 | -2.54 | -13.74 | -1.27 | -8.8 | -5.0 | -1.6 |
| SOL M1.k5.x3.h60 | 5,063 | 41.7 | -0.46 | -11.66 | -0.23 | -4.4 | -2.6 | -0.2 |
| SOL M1.k15.x1.h1 | 222,081 | 20.9 | -0.13 | -11.33 | -0.06 | -211.4 | -63.6 | -2.4 |
| SOL M1.k15.x1.h5 | 101,446 | 31.9 | -0.22 | -11.42 | -0.11 | -71.3 | -36.9 | -1.4 |
| SOL M1.k15.x1.h15 | 53,175 | 37.2 | -0.45 | -11.65 | -0.23 | -33.6 | -19.0 | -1.3 |
| SOL M1.k15.x1.h60 | 20,224 | 42.6 | +1.99 | -9.21 | +0.99 | -7.8 | -4.5 | +1.7 |
| SOL M1.k15.x2.h1 | 49,439 | 26.2 | -0.39 | -11.59 | -0.20 | -67.5 | -28.3 | -2.3 |
| SOL M1.k15.x2.h5 | 24,285 | 33.7 | -1.56 | -12.76 | -0.78 | -28.8 | -15.6 | -3.5 |
| SOL M1.k15.x2.h15 | 14,808 | 37.7 | -1.72 | -12.92 | -0.86 | -14.6 | -8.3 | -1.9 |
| SOL M1.k15.x2.h60 | 8,715 | 41.3 | -1.77 | -12.97 | -0.89 | -7.2 | -4.2 | -1.0 |
| SOL M1.k15.x3.h1 | 14,458 | 29.7 | -0.94 | -12.14 | -0.47 | -31.7 | -16.0 | -2.5 |
| SOL M1.k15.x3.h5 | 7,237 | 35.0 | -3.31 | -14.51 | -1.66 | -12.2 | -7.2 | -2.8 |
| SOL M1.k15.x3.h15 | 4,630 | 37.1 | -4.34 | -15.54 | -2.17 | -7.3 | -4.2 | -2.0 |
| SOL M1.k15.x3.h60 | 3,342 | 40.6 | -5.67 | -16.87 | -2.83 | -4.6 | -2.7 | -1.5 |

### 3.2 M2 — minute breakout with a trailing stop, 60-minute limit (12 pairs)

| Pair | Trades | Win % | Gross bp | Net bp | Break-even bp/side | t (net) | Sharpe (daily, ann.) | t (gross) | Hold min |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC M2.N30.y1 | 78,384 | 13.6 | -3.24 | -13.38 | -1.62 | -103.5 | -47.6 | -25.1 | 5.6 |
| BTC M2.N30.y2 | 46,122 | 23.2 | -3.88 | -14.02 | -1.94 | -73.8 | -38.6 | -20.4 | 19.4 |
| BTC M2.N120.y1 | 33,756 | 14.1 | -3.24 | -13.38 | -1.62 | -66.4 | -31.8 | -16.1 | 3.7 |
| BTC M2.N120.y2 | 22,393 | 21.0 | -4.96 | -15.10 | -2.48 | -50.8 | -27.7 | -16.7 | 14.4 |
| ETH M2.N30.y1 | 80,502 | 15.7 | -3.89 | -14.37 | -1.95 | -100.7 | -44.3 | -27.3 | 5.3 |
| ETH M2.N30.y2 | 45,975 | 26.1 | -3.72 | -14.20 | -1.86 | -73.2 | -37.0 | -19.2 | 19.4 |
| ETH M2.N120.y1 | 35,631 | 16.7 | -3.81 | -14.29 | -1.90 | -71.5 | -31.2 | -19.0 | 3.6 |
| ETH M2.N120.y2 | 22,558 | 24.7 | -4.58 | -15.06 | -2.29 | -53.5 | -27.6 | -16.3 | 14.2 |
| SOL M2.N30.y1 | 81,064 | 20.0 | -5.80 | -17.00 | -2.90 | -83.1 | -39.6 | -28.3 | 4.8 |
| SOL M2.N30.y2 | 45,258 | 29.6 | -4.97 | -16.17 | -2.48 | -48.2 | -26.0 | -14.8 | 18.9 |
| SOL M2.N120.y1 | 37,928 | 20.8 | -5.50 | -16.70 | -2.75 | -58.4 | -28.7 | -19.2 | 3.6 |
| SOL M2.N120.y2 | 22,784 | 28.3 | -6.00 | -17.20 | -3.00 | -33.7 | -18.5 | -11.8 | 14.7 |

The gross of M2 is negative mostly because of the pessimistic intrabar ordering (reading R8), not because of the signal: see section 8.2 (follow vs fade) and section 11 (the alternative reading).

### 3.3 M3 — scalp with take-profit and stop-loss, 30-minute limit (9 pairs)

| Pair | Trades | Win % | Gross bp | Net bp | Break-even bp/side | t (net) | Sharpe (daily, ann.) | t (gross) | Hold min |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC M3.a1.b1 | 55,211 | 36.2 | -1.46 | -11.60 | -0.73 | -107.7 | -31.8 | -13.6 | 3.1 |
| BTC M3.a2.b1 | 44,501 | 30.5 | -1.16 | -11.30 | -0.58 | -77.5 | -30.7 | -7.9 | 5.4 |
| BTC M3.a1.b2 | 48,510 | 50.0 | -0.92 | -11.06 | -0.46 | -71.2 | -28.3 | -5.9 | 6.5 |
| ETH M3.a1.b1 | 54,746 | 40.6 | -1.18 | -11.66 | -0.59 | -81.9 | -29.0 | -8.3 | 3.2 |
| ETH M3.a2.b1 | 43,869 | 32.3 | -0.60 | -11.08 | -0.30 | -64.3 | -27.5 | -3.5 | 5.7 |
| ETH M3.a1.b2 | 48,617 | 55.0 | -0.60 | -11.08 | -0.30 | -60.3 | -26.1 | -3.2 | 6.6 |
| SOL M3.a1.b1 | 53,887 | 46.6 | -2.19 | -13.39 | -1.10 | -63.3 | -26.2 | -10.4 | 3.4 |
| SOL M3.a2.b1 | 43,037 | 32.6 | -1.30 | -12.50 | -0.65 | -42.8 | -21.7 | -4.5 | 6.1 |
| SOL M3.a1.b2 | 48,345 | 63.1 | -1.74 | -12.94 | -0.87 | -40.1 | -20.1 | -5.4 | 6.9 |

## 4. The single best pairs (design window)

- [fact] Best by GROSS: **ETHUSDT M1.k15.x3.h60** — 3,477 trades, win rate 40.1 % net (46.2 % gross), gross +3.58 bp per trade (t +1.70), net -6.90 bp per trade (median -16.89, t -3.28), break-even +1.79 bp per side against 5.24 charged, sum of net returns -240 % of one trade's notional, daily Sharpe -1.9.
- [fact] Best by NET: the same pair, -6.90 bp per trade — it loses 66 % of its round-trip cost instead of all of it.
- [fact] In the descriptive holdout the best-gross design pair has gross -1.84 bp (t -1.03), net -12.32 bp.
- [fact] The only pair whose gross mean is significantly positive (t ≥ 3): **SOLUSDT M1.k1.x1.h1**, +0.213 bp per trade on 280,795 trades (t +3.63); net -10.99 bp. Descriptive holdout: gross -0.183 bp (t -5.25).
- [fact] Worst by net: SOLUSDT M2.N120.y2, -17.20 bp per trade.
- [interpretation] The best gross figure belongs to one of the smallest samples in the grid (3,477 trades, t +1.70): the largest of 129 noisy means, not a discovery.

## 5. Aggregates (design window)

| Group | Pairs | Trades | Gross > 0 | Net > 0 | Median gross bp | Median break-even bp/side | Charged bp/side | Best net bp | Gross t >= 3 | Gross t <= -3 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All pairs | 129 | 6,400,436 | 33 (26 %) | 0 (0 %) | -0.36 | -0.18 | 5.07-5.60 | -6.90 | 1 | 35 |
| M1 burst, fixed hold | 108 | 5,407,358 | 33 (31 %) | 0 (0 %) | -0.20 | -0.10 | 5.07-5.60 | -6.90 | 1 | 14 |
| M2 breakout, trailing stop | 12 | 552,355 | 0 (0 %) | 0 (0 %) | -4.23 | -2.12 | 5.07-5.60 | -13.38 | 0 | 12 |
| M3 scalp, target / stop | 9 | 440,723 | 0 (0 %) | 0 (0 %) | -1.18 | -0.59 | 5.07-5.60 | -11.06 | 0 | 9 |
| BTCUSDT | 43 | 2,075,674 | 3 (7 %) | 0 (0 %) | -0.51 | -0.25 | 5.07 | -9.36 | 0 | 18 |
| ETHUSDT | 43 | 2,116,981 | 17 (40 %) | 0 (0 %) | -0.09 | -0.04 | 5.24 | -6.90 | 0 | 9 |
| SOLUSDT | 43 | 2,207,781 | 13 (30 %) | 0 (0 %) | -0.46 | -0.23 | 5.60 | -9.21 | 1 | 8 |

[fact] Share of pairs with a positive mean before costs: 33 / 129 = 26 %. After costs: 0 / 129. Median break-even cost per side -0.18 bp (best pair +1.79 bp) versus 5.07–5.60 bp actually charged: the median formula would lose money even if trading were free, and the best one would need the all-in cost per side to fall by 66 %. Gross means significantly above zero (t ≥ 3): 1; significantly below zero (t ≤ −3): 35. Design rule: mean net > 0: 0; t ≥ 3.0: 0; Benjamini–Hochberg at q = 10 % over 129 rejects (one-sided, mean > 0): 0; (two-sided): 129 — every two-sided rejection is on the LOSING side. Passers: 0.

[fact] Sum of net returns per pair over the three years, on a fixed stake per trade: between -240 % and -30,850 % of that stake (median -3,116 %). The more often a formula trades, the more it loses: the pair with the most trades (SOLUSDT M1.k1.x1.h1, 256 trades a day) loses 30,850 % of its stake.

## 6. Maker optimistic bound (2.0 bp per side, no spread)

[fact] Same trades, charged 2.0 bp per side instead of the taker cost: 0 of 129 pairs have a positive mean. The best is ETHUSDT M1.k15.x3.h60 at -0.42 bp per trade (t -0.20); the median pair makes -4.36 bp. Descriptive holdout: 0 of 129 positive, best -2.95 bp (SOLUSDT M1.k5.x3.h60).

[interpretation] Why this row is only a ceiling and not a strategy:

1. It keeps the taker run's fills — the open of the next bar, a stop level, a target level — and assumes a resting order would have been filled at each of them every time. A passive buy is filled when the market comes DOWN to it. For a momentum entry that means: filled mostly when the move has already failed, left unfilled when the move runs away. That adverse selection is the whole cost of trading passively and a one-minute bar cannot show it.
2. Stop exits are market orders by nature; they are charged here as if they were passive.
3. No queue position, no partial fill and no missed trade is modelled; the half-spread a maker would EARN is not credited either, because the same fills cannot both be passive and happen on every signal.

So the true maker result lies below this row by an amount bars cannot measure. Even this ceiling is negative for every pair.

## 7. Holdout (2024-01-01 → 2026-10-31)

### 7.1 The pre-registered read: design passers only

[fact] There is no design passer, so the one-shot holdout was not used for any formula. `runs/fastmom_v1/holdout_passers.csv` holds a header and no rows. Outcome under the pre-registration: every formula is DEAD at this cost.

### 7.2 Descriptive table for all 129 pairs — NOT evidence

Computed after `DESIGN_PASSERS.json` was written, at the conductor's instruction, so the owner can see whether 2024–2026 looks different. Nothing in it can promote a formula (see section 13).

| Group | Pairs | Trades | Gross > 0 | Net > 0 | Median gross bp | Median break-even bp/side | Charged bp/side | Best net bp | Gross t >= 3 | Gross t <= -3 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All pairs | 129 | 6,251,540 | 10 (8 %) | 0 (0 %) | -0.48 | -0.24 | 5.07-5.60 | -9.77 | 0 | 58 |
| M1 burst, fixed hold | 108 | 5,279,444 | 10 (9 %) | 0 (0 %) | -0.41 | -0.21 | 5.07-5.60 | -9.77 | 0 | 40 |
| M2 breakout, trailing stop | 12 | 536,844 | 0 (0 %) | 0 (0 %) | -3.07 | -1.53 | 5.07-5.60 | -12.09 | 0 | 12 |
| M3 scalp, target / stop | 9 | 435,252 | 0 (0 %) | 0 (0 %) | -0.59 | -0.29 | 5.07-5.60 | -10.28 | 0 | 6 |
| BTCUSDT | 43 | 2,081,897 | 1 (2 %) | 0 (0 %) | -0.49 | -0.24 | 5.07 | -10.10 | 0 | 24 |
| ETHUSDT | 43 | 2,031,679 | 6 (14 %) | 0 (0 %) | -0.32 | -0.16 | 5.24 | -9.77 | 0 | 14 |
| SOLUSDT | 43 | 2,137,964 | 3 (7 %) | 0 (0 %) | -0.66 | -0.33 | 5.60 | -10.15 | 0 | 20 |

[fact] Positive before costs: 10 / 129; after costs: 0 / 129; under the maker bound: 0 / 129. Pairs that would meet the holdout numbers (mean net > 0 and t ≥ 2): 0. Best gross: SOLUSDT M1.k5.x3.h60 +1.05 bp (t +0.62, 4,823 trades). Best net: ETHUSDT M1.k5.x2.h60 -9.77 bp. Median gross -0.48 bp, median break-even -0.24 bp per side. Gross means with t ≥ 3: 0; with t ≥ 2: 0; with t ≤ −3: 58.

[fact] Did anything change? The rank correlation (Spearman) of the gross means between the two windows is +0.53 over all 129 pairs — most of that is the mechanical ordering of the families (M2 below M3 below M1) — and +0.35 inside the 108 M1 pairs. Of the 33 pairs that were positive before costs in the design window, 7 are still positive in 2024–2026. The five best design pairs by gross:

| Pair | Design gross bp (t) | Holdout gross bp (t) | Holdout net bp |
| :--- | ---: | ---: | ---: |
| ETHUSDT M1.k15.x3.h60 | +3.58 (+1.70) | -1.84 (-1.03) | -12.32 |
| SOLUSDT M1.k15.x1.h60 | +1.99 (+1.68) | -1.19 (-1.92) | -12.39 |
| SOLUSDT M1.k5.x1.h60 | +1.64 (+1.67) | -2.45 (-4.43) | -13.65 |
| ETHUSDT M1.k1.x3.h60 | +1.51 (+1.18) | +0.28 (+0.26) | -10.20 |
| SOLUSDT M1.k1.x2.h60 | +1.36 (+1.07) | +0.19 (+0.24) | -11.01 |

[interpretation] The small positive gross means of the design window were noise around zero: they do not carry over (no gross mean reaches t ≥ 2 in 2024–2026). What does carry over is the sign of the bulk — slightly negative before costs — and the size of the fee.

## 8. Sanity checks

### 8.1 Random-entry control

For every pair, the same number of trades with the same sides and the same holding times (in bars) was entered at uniformly random tradeable minutes of the same window and closed at the open that many bars later (seed 20261110; `control_design.csv`, `control_holdout_descriptive.csv`). Expected: zero before costs, minus the round trip after.

| Window | Trade-weighted control gross bp | Control net bp | Round trip bp (trade-weighted) | z of the 129 control means: mean / sd | abs(z) > 2 (≈ 6 expected) | abs(z) > 3 | Largest z |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Design | -0.0200 | -10.6381 | 10.6181 | -0.14 / 0.97 | 3 | 0 | -2.19 (BTCUSDT M1.k5.x2.h60) |
| Holdout (descriptive) | +0.0088 | -10.6042 | 10.6130 | +0.07 / 0.95 | 5 | 0 | -2.73 (ETHUSDT M1.k1.x3.h5) |

[fact] The control behaves: its gross mean is -0.020 bp (design) and +0.009 bp (holdout) per trade, its net mean -10.64 and -10.60 bp against round trips of 10.62 and 10.61 bp, and the per-pair z-scores are distributed as chance says they should be. The price and cost accounting has no drift of its own. (The control says nothing about look-ahead in the signals; that is what the entry-timing and truncation tests are for.)

### 8.2 Follow versus fade — how much of M2 / M3 is the exit rule, how much the signal

M2 and M3 exit on intrabar rules that are pessimistic by construction (readings R8 and R9), so even a coin-flip direction loses before costs. To separate that from the signal, every actual M2 / M3 entry was also simulated in the OPPOSITE direction with the same exit rule. **Drag** = (follow + fade) / 2 is what the exit rule costs whatever the direction; **edge** = (follow − fade) / 2 is what the direction of the signal adds. Design window, bp per trade before costs:

| Pair | Trades | Follow (the formula) | Fade (opposite side) | Drag of the exit rule | Edge of the direction |
| :--- | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT M2.N30.y1 | 78,384 | -3.24 | -2.11 | -2.67 | -0.56 |
| BTCUSDT M2.N30.y2 | 46,122 | -3.88 | -1.23 | -2.56 | -1.32 |
| BTCUSDT M2.N120.y1 | 33,756 | -3.24 | -2.71 | -2.97 | -0.27 |
| BTCUSDT M2.N120.y2 | 22,393 | -4.96 | -1.89 | -3.43 | -1.53 |
| BTCUSDT M3.a1.b1 | 55,211 | -1.46 | +0.26 | -0.60 | -0.86 |
| BTCUSDT M3.a2.b1 | 44,501 | -1.16 | +0.13 | -0.51 | -0.64 |
| BTCUSDT M3.a1.b2 | 48,510 | -0.92 | +0.76 | -0.08 | -0.84 |
| ETHUSDT M2.N30.y1 | 80,502 | -3.89 | -3.29 | -3.59 | -0.30 |
| ETHUSDT M2.N30.y2 | 45,975 | -3.72 | -1.94 | -2.83 | -0.89 |
| ETHUSDT M2.N120.y1 | 35,631 | -3.81 | -4.21 | -4.01 | +0.20 |
| ETHUSDT M2.N120.y2 | 22,558 | -4.58 | -3.97 | -4.27 | -0.30 |
| ETHUSDT M3.a1.b1 | 54,746 | -1.18 | -0.15 | -0.67 | -0.52 |
| ETHUSDT M3.a2.b1 | 43,869 | -0.60 | -0.17 | -0.39 | -0.21 |
| ETHUSDT M3.a1.b2 | 48,617 | -0.60 | +0.01 | -0.29 | -0.30 |
| SOLUSDT M2.N30.y1 | 81,064 | -5.80 | -6.14 | -5.97 | +0.17 |
| SOLUSDT M2.N30.y2 | 45,258 | -4.97 | -3.25 | -4.11 | -0.86 |
| SOLUSDT M2.N120.y1 | 37,928 | -5.50 | -7.41 | -6.45 | +0.95 |
| SOLUSDT M2.N120.y2 | 22,784 | -6.00 | -5.87 | -5.94 | -0.07 |
| SOLUSDT M3.a1.b1 | 53,887 | -2.19 | +0.63 | -0.78 | -1.41 |
| SOLUSDT M3.a2.b1 | 43,037 | -1.30 | +0.71 | -0.30 | -1.01 |
| SOLUSDT M3.a1.b2 | 48,345 | -1.74 | +0.70 | -0.52 | -1.22 |

[fact] M2: drag -6.45 to -2.56 bp, directional edge -1.53 to +0.95 bp (3 of 12 positive). M3: drag -0.78 to -0.08 bp, edge -1.41 to -0.21 bp (0 of 9 positive). [interpretation] Take the pessimistic exit rule away entirely and the direction of the breakout or of the 5-minute burst is still worth only between -1.53 and +0.95 bp per trade — in M3 it is negative for every pair, i.e. fading the burst did better than following it. Against a 10–11 bp round trip neither is tradeable.

### 8.3 Independent cross-checks and tests

- `scripts/factory/tests/test_fastmom.py` — synthetic bars with hand-computed answers: entry timing (a signal at t cannot use bar t+1), fixed-hold P&L with costs, stop-before-target inside one bar, gap-through fills at the open, one position at a time, σ_k from past bars only (truncation: everything up to bar t is bit-identical when later bars are altered), the day-clustered t against a hand-computed example and against statsmodels, Benjamini–Hochberg on toy vectors, missing / zero-volume bars, the holdout seal, an end-to-end pipeline on synthetic archives. Last run: `50 passed in 154.33s (0:02:34)`.
- An independent minute-by-minute state machine (in the test file) reproduces the simulator trade for trade on random bars and on three slices of the real archive that contain zero-volume runs and the SOL archive holes.
- A separate pandas path (rolling standard deviation, plain sequencing loop) reproduces the frozen ledger's trade count and gross mean of three M1 pairs on the full design window; statsmodels' cluster-robust OLS reproduces the ledger's t-statistics on the real trades of three ETHUSDT pairs (both are tests in the suite).
- Before the design run, 25 deliberately broken versions of the module (look-ahead fill, peeking signal, target before stop, gap filled at the level, cost charged once, unclustered t, seal removed, …) each made at least one test fail (an ad-hoc mutation run during development, not part of the suite).
- `fastmom reproduce` (2026-11-10T19:12:53Z, module sha256 `72b810a95ff76f0d840447d39376a5e907df3a023ad9c0f42c11d86a00ff2d46`, the module that wrote this report): the frozen tables recomputed from the raw zips are byte-identical: `design_ledger.csv` identical, `control_design.csv` identical, `holdout_descriptive.csv` identical, `control_holdout_descriptive.csv` identical.

## 9. Data notes

[fact] 210 files requested, 210 ok; all 210 zips match their published sha256 (`download_manifest.json`; `fastmom verify` re-hashes them offline). Plain scripted GETs, default `python-requests` User-Agent, under 4 requests per second. Timestamps are milliseconds in every file (no microsecond file); every bar's open time lies inside the month named by its file, on the minute grid, strictly increasing (asserted while parsing). Header rows: BTC 24 of 36 design files, ETH 24 of 36 design files, SOL 23 of 36 design files; BTC 35 of 35, ETH 35 of 35, SOL 35 of 35 files of the holdout load. OHLC-inconsistent bars: 0.

| Symbol | Window | Minutes expected | Bars present | Missing | Zero-volume | Tradeable | σ₁ defined | σ₁₅ defined |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTCUSDT | design | 1,576,800 | 1,576,800 | 0 | 241 | 1,576,559 | 1,575,360 | 1,575,346 |
| ETHUSDT | design | 1,576,800 | 1,576,800 | 0 | 145 | 1,576,655 | 1,575,360 | 1,575,346 |
| SOLUSDT | design | 1,576,800 | 1,569,600 | 7,200 | 148 | 1,569,452 | 1,565,280 | 1,565,238 |
| BTCUSDT | holdout | 1,490,400 | 1,488,960 | 1,440 | 126 | 1,488,834 | 1,487,520 | 1,487,506 |
| ETHUSDT | holdout | 1,490,400 | 1,488,960 | 1,440 | 127 | 1,488,833 | 1,487,520 | 1,487,506 |
| SOLUSDT | holdout | 1,490,400 | 1,488,960 | 1,440 | 128 | 1,488,832 | 1,487,520 | 1,487,506 |

Missing runs (bars absent from the archive) and zero-volume runs inside each scored window:

- BTCUSDT design — missing: none; zero-volume: 2021-03-02T01:01Z (59 min); 2022-05-01T22:26Z (29 min); 2022-05-28T16:40Z (35 min); 2023-09-12T08:34Z (19 min); 2023-11-10T15:07Z (99 min)
- ETHUSDT design — missing: none; zero-volume: 2021-03-02T01:01Z (59 min); 2022-05-01T22:26Z (29 min); 2022-05-28T16:40Z (35 min); 2023-09-12T08:34Z (19 min); 2023-11-14T11:39Z (3 min)
- SOLUSDT design — missing: 2022-02-26T00:00Z (4,320 min); 2022-04-01T00:00Z (2,880 min); zero-volume: 2021-01-30T04:42Z (1 min); 2021-03-02T01:01Z (59 min); 2021-03-03T22:32Z (1 min); 2021-04-01T21:25Z (1 min); 2022-05-01T22:26Z (29 min); 2022-05-28T16:40Z (35 min); 2023-09-12T08:34Z (19 min); 2023-11-14T11:39Z (3 min)
- BTCUSDT holdout — missing: 2026-10-28T00:00Z (1,440 min); zero-volume: 2024-10-28T16:21Z (14 min); 2024-10-28T16:36Z (1 min); 2024-10-28T20:00Z (74 min); 2025-01-14T13:32Z (2 min); 2025-01-29T01:23Z (13 min); 2025-01-29T02:41Z (4 min); 2025-08-29T06:19Z (18 min)
- ETHUSDT holdout — missing: 2026-10-28T00:00Z (1,440 min); zero-volume: 2024-10-28T16:21Z (14 min); 2024-10-28T16:36Z (1 min); 2024-10-28T20:00Z (74 min); 2025-01-14T13:32Z (2 min); 2025-01-14T15:01Z (1 min); 2025-01-29T01:23Z (13 min); 2025-01-29T02:41Z (4 min); 2025-08-29T06:19Z (18 min)
- SOLUSDT holdout — missing: 2026-10-28T00:00Z (1,440 min); zero-volume: 2024-10-28T16:21Z (14 min); 2024-10-28T16:36Z (1 min); 2024-10-28T20:00Z (74 min); 2025-01-14T13:32Z (2 min); 2025-01-14T15:01Z (1 min); 2025-01-29T01:23Z (13 min); 2025-01-29T02:41Z (4 min); 2025-08-29T06:18Z (19 min)

[fact] Consequences in the simulation. Design: 265 otherwise-valid signals were not taken because the entry bar had no volume or was missing; 150 time exits fell on a missing or zero-volume bar and were filled at the next available open; 0 trades were dropped at the window end. Holdout (descriptive): 443 and 171. After a hole σ_k is undefined for the next 1,440 + k minutes (R1), so no signal is taken for a day after each hole.
[fact] SOLUSDT has two archive holes in the design window (three days from 2022-02-26, two days from 2022-04-01). A position open when a hole starts is closed at the first bar after it, as the brief requires: 31 trades in 22 pairs were carried across a hole for days. Removing them changes a pair's gross mean by at most 0.17 bp (SOLUSDT M1.k15.x2.h60: -1.77 → -1.60 bp) and turns no pair positive after costs.

## 10. Every open point of the pre-registration and how it was read

Rule followed: where the frozen text leaves a choice, take the reading that is WORSE for the strategy; where neither reading is clearly worse, take the literal one and say so. The sentences are quoted verbatim. Section 11 shows what the main alternatives would have given.

**A1 — σ_k.**
> σ_k = the trailing 1,440-bar (24 h) standard deviation of k-minute returns, known at the signal bar.

Open: overlapping or non-overlapping k-minute returns; whether the window contains the signal bar's own return; the divisor; what happens when bars are missing. [reading R1] The 1,440 OVERLAPPING k-minute simple returns close_i / close_(i−k) − 1 ending at and including the signal bar (the brief said "using bars up to and including the signal bar"), sample standard deviation (n − 1) about the window mean; all 1,440 must exist, otherwise no signal. Including the signal bar's own return makes a burst inflate its own threshold (fewer signals); the alternative is sensitivity S1.

**A2 — one position at a time.**
> One position at a time per formula-symbol; signals during an open position are ignored.

Open: a signal at the close of the bar just before an exit open coincides with the exit print. [reading R3] The position is still open at that close, so the signal is ignored; the first usable signal is the one at the close of the exit bar. Literal reading; direction of the effect unknown a priori; the alternative is sensitivity S2.

**A3 — M2 stop.**
> exit when price retraces y·σ_5 from the best price since entry, y ∈ {1, 2}, or after 60 minutes. Stops are evaluated on each bar's high/low and filled AT THE STOP LEVEL if the bar opens beyond it, at the open (gap-through is paid).

Open: (i) the second sentence, read word for word, says the stop is filled at its level WHEN the bar opens beyond it. It is read as "filled at the stop level; if the bar opens beyond it, at the open", which is what "gap-through is paid" and the brief ("gap-through fills at the open") say. (ii) y·σ_5 is a return measured from the best price, with σ_5 frozen at the signal bar [R7]. (iii) The text does not say whether a bar's own high may raise the stop that the same bar's low then hits. [reading R8] Bar by bar the worse of the two orders of the bar's high and low is taken, with fills at the stop level in force — the pre-registration's own "pessimistic ordering" of M3 applied to the trail. This is harsher than the usual back-test convention (adverse extreme first, sensitivity S3) but it is not the worst conceivable path (a fill at the bar's low).

**A4 — M3 levels.**
> exit at +a·σ_5 (take-profit) or −b·σ_5 (stop-loss) or after 30 minutes, (a, b) ∈ {(1, 1), (2, 1), (1, 2)}. If a bar's range touches both levels, the STOP is assumed to fill first (pessimistic ordering).

Open: what the levels are measured from; gap-through is written for M2 only; a favourable gap through the target. [reading R9] Levels are returns from the entry price with σ_5 at the signal bar. A stop on a bar that opens beyond it pays the open (worse). A take-profit is always filled at its level, never at a better open (worse). A bar that opens beyond the target and also trades through the stop is booked as a stop (literal, worse).

**A5 — zero-volume and missing bars.**
> Zero-volume bars are no-trade bars.

[reading R4] No entry on a zero-volume or missing bar (the signal is dropped, counted); a time exit due on one is filled at the next bar with volume (counted); stops and targets are evaluated on bars with volume only. A signal may still be COMPUTED at a zero-volume bar that exists in the archive (its close is the last traded price). Signals need complete history (R1, R6), so nothing is traded for a day after a hole.

**A6 — costs.**
> Per side: taker fee 5.0 bp + half-spread BTC 0.07 / ETH 0.24 / SOL 0.60 bp.

[reading R5] Additive on entry notional: net = side × (exit / entry − 1) − 2 × cost. Charging the exit on exit notional would change a trade by less than 0.01 bp.

**A7 — statistics.**
> number of trades, win rate, mean and median net return per trade (bp), mean gross per trade (bp), breakeven cost per side (bp), total net return, Sharpe of the daily P&L (a day with no trade = 0), and a t-statistic of the mean net per trade clustered by UTC day.

[readings R12–R15] Win rate on NET returns (worse; the gross win rate is in the ledger). Total net return = the sum of per-trade net returns on a fixed notional (the compounded figure is also in the ledger). A trade belongs to the UTC day of its entry. Daily Sharpe over every calendar day of the window, annualised by √365. Clustered t = cluster-robust (CR1) t of an intercept, clusters = entry days.

**A8 — the multiple-testing step.**
> mean net per trade > 0 with day-clustered t ≥ 3.0 AND the Benjamini–Hochberg test at q = 10 % over all 129 pairs rejects it.

Open: which p-value. [reading R16] A pair must be rejected under BOTH the one-sided p (alternative: mean > 0) and the two-sided p, each from Student-t with (trading days − 1) degrees of freedom. The one-sided reading is the binding one here: the two-sided test rejects all 129 pairs for being significantly NEGATIVE, which would have made the step vacuous for a positive candidate.

**A9 — window edges.**
> Design window 2021-01-01 → 2023-12-31. Holdout 2024-01-01 → 2026-10-31, read once, only for formulas that pass the design rule.

[reading R11] A trade belongs to the window of its entry bar and must be able to finish inside it (no entry whose time limit falls after the window's last bar), so the design run never needs a 2024 bar. The holdout run loads December 2023 only to warm up σ and the N-bar extremes. "Read once, only for formulas that pass": see section 13 for the descriptive table.

**Not open, stated for completeness.** M1 exits at the open h minutes after the entry open (R2). M2 breakout = close above the highest HIGH (below the lowest LOW) of the previous N bars, the current bar excluded, all N present (R6). Time exits of M2 / M3 are at the open 60 / 30 minutes after the entry open (R10).

**No formula was impossible to run as written.** All 43 ran on all three symbols; the only textual defect is the garbled stop sentence of A3 (i).

## 11. Does the verdict depend on those readings? (design window; not part of the decision rule)

The same pairs re-run under the reading that was NOT chosen, one at a time, after the passers were frozen. These rows cannot promote anything; they only show whether section 1 hangs on a choice of mine.

| Reading | What changes | Pairs | Trades | Gross > 0 | Net > 0 | Maker bound > 0 | Median gross bp | Best net bp (pair) | Largest change of a gross mean bp |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | the registered readings R1-R16 (must equal design_ledger.csv) | 129 | 6,400,436 | 33 | 0 | 0 | -0.36 | -6.90 (ETHUSDT M1.k15.x3.h60) | +0.00 |
| S1 | sigma_k from the 1,440 returns ending at t-1, so a burst does not inflate its own threshold | 129 | 6,407,835 | 33 | 0 | 0 | -0.37 | -6.73 (ETHUSDT M1.k15.x3.h60) | +0.27 |
| S2 | a signal at the close just before an exit open may be filled at that same open | 129 | 7,995,652 | 35 | 0 | 0 | -0.43 | -6.59 (ETHUSDT M1.k15.x3.h60) | -2.33 |
| S3 | M2 only: inside a bar the adverse extreme always comes first (no same-bar ratchet stop) | 12 | 437,178 | 4 | 0 | 0 | -0.82 | -10.80 (SOLUSDT M2.N120.y1) | +6.24 |

[fact] Under every alternative reading the number of pairs with a positive net mean is 0; the best net mean over all readings is -6.59 bp (ETHUSDT M1.k15.x3.h60, reading S2). With the usual "adverse extreme first" convention (S3) the 12 M2 pairs have a median gross of -0.82 bp and 4 of 12 are positive before costs; their best net mean is -10.80 bp. [interpretation] The verdict does not depend on how the open points were read.

## 12. Limits

- **Funding is ignored** (pre-registration §1). Holding periods are 1–60 minutes; a position pays or receives funding only if it is open across an 8-hourly stamp. Second-order here, and it cannot rescue pairs that are 7–17 bp per trade under water.
- **No market impact, no latency.** The entry is the first print of the next minute. A real order sent when the bar closes arrives later; after a burst it chases the move, so the true entry is probably worse than the open used here (not measured).
- **Bars, not ticks.** The order of the high and the low inside a minute is unknown; M2 and M3 are pessimistic-ordering simulations, not tick replays (section 8.2 measures how much that costs). And a stop "filled at the level" is itself optimistic on a fast move: a stop-market order fills at the next available price, which can be well through the level; only opens beyond the stop are charged for that here.
- **The costs are today's, on another venue.** Taker 5.0 bp is the Kraken Derivatives EEA entry tier and the half-spreads are one top-of-book snapshot of 2026-11-10 (`landscape/venues.json`), applied to Binance prices of 2021–2026. No historical spread was measured and Kraken's book is not Binance's. If spreads were wider in 2021–2023 — likely, above all for SOL, but unverified here — the real cost was higher than the one charged.
- **The maker row is a ceiling**, not a result (section 6).
- **The 129 pairs are not independent tests**: formulas share signals and trades (the three M3 pairs enter on the same bars as M1.k5.x2.*), and the three symbols move together. The clustered t handles dependence inside a day, not across pairs; this matters only for how surprising a positive result would have been, and there is none.
- **Day clustering assumes days are independent.** Volatility regimes last longer than a day. The t-statistics of the net means run from -362.2 to -3.3 (median -40), all negative; a longer dependence horizon would shrink them towards zero but cannot change a sign, and the pass rule needs a positive mean first.
- **The random-entry control checks the accounting, not the signals**; look-ahead in the signals is excluded by the entry-timing and truncation tests and by the reference simulator.
- **Archive holes** (SOLUSDT 2022-02-26 → 28 and 2022-04-01 → 02; all three symbols 2026-10-28) are holes in the public archive, not in trading. Nothing is traded for a day after a hole and a few positions are carried across one (section 9).
- **Fixed notional, no account effects**: no minimum order size, no margin, no liquidation, no compounding.

## 13. Deviations and disclosures

1. **Descriptive holdout for all pairs.** The pre-registration says the holdout is "read once, only for formulas that pass the design rule". The conductor's brief additionally asked for the holdout statistics of ALL pairs in a clearly separate file, after the passers were frozen. That was done (`holdout_descriptive.csv`), in that order, enforced in code. It is outside the letter of the pre-registration; it is labelled descriptive everywhere and no formula can be promoted from it. With zero passers the pre-registered read itself was never used.
2. **Four raw holdout rows were displayed before the freeze.** While probing the archive format (header row, timestamp unit) before any code existed, the first two and last two CSV rows of `SOLUSDT-1m-2026-10.zip` were printed. No statistic was computed from them, the design rule is mechanical, and the design run parses no file after 2023-12; it is recorded here because "never look at a holdout number before the passers exist" was the rule, and four raw prices are four numbers.
3. **Sensitivity rows and the follow/fade and random-entry controls are additions** to what the pre-registration lists. They are diagnostics on the same 129 pairs, run on the design window (the controls also on the descriptive holdout), and none of them enters the pass rule. "Nothing else is run" is respected in the sense that matters: no further formula was tried and nothing was tuned.
4. **Order of work as executed:** download and checksum verification → tests → design ledger (2026-11-10T18:41:32Z) → `DESIGN_PASSERS.json` (2026-11-10T18:44:54Z) → `holdout_passers.csv` (empty) → `holdout_descriptive.csv` (2026-11-10T18:46:18Z) → sensitivity, reproduction check, this report. The design ledger was written once and never re-run with `--force-redesign` (flag recorded false in its meta).
5. The module was extended after the freeze (sensitivity switches that default to the registered behaviour, the reproduce stage, this report). `fastmom reproduce` shows the frozen tables are regenerated byte for byte by the final code (section 8.3).

## 14. Files

- Spec (frozen): `research/factory/FASTMOM_PREREGISTRATION.md`
- Code: `scripts/factory/fastmom.py`; tests: `scripts/factory/tests/test_fastmom.py`
- Raw data: `research/factory/data/raw/binance/futures_um/archive_klines_1m/<SYMBOL>/<SYMBOL>-1m-YYYY-MM.zip` (+ `.zip.CHECKSUM`)
- Run directory `research/factory/runs/fastmom_v1/`:

| File | sha256 |
| :--- | ---: |
| `design_ledger.csv` | `cc852fbc1ccb92a090141ee7434c79a030ad05a87c2c15ed0ec5f1031e9f09ce` |
| `design_ledger.json` | `ba86383b24474080bed2a3db4482f67133e2f753ef3be35d3be2044eca4aee31` |
| `DESIGN_PASSERS.json` | `2a8e0f670c65a8f46a3ceac769e957fcd8e7f8896e586609be6e789e51cd5d32` |
| `DESIGN_PASSERS.sha256` | `10b2cf66ef3bf19b97d07baa41cf3aaa56782457206c78bb3ab143b0efa06c8a` |
| `holdout_passers.csv` | `cf20ac0e86d7d502eb2137b3941528bb4d5bda0ce488ab287845a4ab2976a677` |
| `holdout_passers.json` | `5b3427a45350e771d717ae8142d195b991547eea390f8764b1cae2c15ec3ff92` |
| `holdout_descriptive.csv` | `d185621e265fc628a22d66395ba3f85d59560094dafa76c396d51e432bf3969c` |
| `holdout_descriptive.json` | `a833933745d86050bd02148420c4aa8c214be805f6ef7bdd897c9a48534e0947` |
| `control_design.csv` | `1ed99cd89269c8b2d66505296e0bf70ca90bf56830259ac30d008cf832510ff7` |
| `control_holdout_descriptive.csv` | `3091cd4bf8713392870e1a4bcf83d6588ac77eaa0c392468f8f4a6d35ba98c93` |
| `sensitivity_design.csv` | `4a5ce2c45d4e2cc5b92025a59ac4e2e2bd02be058ce17ec20e0ecb2ccfe60c23` |
| `sensitivity_design.json` | `874d689d9b39389ef5233140469ea3f3a1bd2706097534b13aa9c152b6c6a76e` |
| `data_report_design.json` | `e65d179afde9f431e565be58f13225e853c66a04829fc3db94dd2c4e34f7fb9c` |
| `data_report_holdout.json` | `c75c13d5798e120cb7d224d0e6d96c99353158da93c15c75ee7e1f60b47e5a29` |
| `download_manifest.json` | `9f414fcbc77d7ead7ea015fd5629417dba370790599a3a6fb79a4e97ab78efb6` |
| `REPRODUCTION.json` | `0e0701eba8c6886e5ecd34991aef0555e18a681c8fcc2517b37053347b7a24de` |

Reproduce: `cd /home/anont/meme && research/factory/.venv/bin/python -m scripts.factory.fastmom <download | verify | design | passers | holdout | descriptive | sensitivity | reproduce | report>` and `research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_fastmom.py -q`.
