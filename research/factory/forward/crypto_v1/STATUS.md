# FORWARD-CRYPTO v1 — status

Generated 2026-11-11T01:20:35Z by `scripts/factory/forward_crypto.py` (run). A paper LOGGER: no orders, no keys, no account; every P&L figure below is hypothetical.

- Pre-registration sha256 `9942631a16b37c76…`, frozen 2026-11-10T18:13:17Z; forward-start row **2026-11-11** 00:00 UTC (first fill at its 01:00 UTC print).
- Last run: **APPENDED** — appended 10 rows for 2026-11-11; 0 earlier rows reproduced
- Panel: frozen through 2026-11-10, extended through **2026-11-11**; forward rows in the ledger: **1** (10 ledger rows, last hash `6ed04ceddfce985b…`).
- Continuity with the frozen lane (2026-08-13 → 2026-11-10, 90 rows rebuilt from Binance REST): **EXACT** — prices 0/62280, volume_quote 0/62280, exec_prices 0/62370, exec_prices_alt 0/62370, live_at_print 0/62370, carry 0/62370, funding_obs 0/62370, settlement_row 0/62370, universe_mask 0/62370 cells differ.
- Runs on file: 4; failed or refused: 0.
- Incidents: 0.

## Accounts

Equity in USD (every account starts at 5,597). Exposure is after the last row's trade. Costs = fees + half-spread paid so far, the one-off entry of the whole book included; bp / year annualises them over the rows so far, so it is far too high in the first weeks. Operational figures, not performance.

| arm | account | rows | equity | since start | gross | net | positions | turnover | costs USD | costs bp/yr | funding USD | Kraken cannot hold (last / mean) | state |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A60 | IDEAL | 1 | 5,595.29 | -0.03 % | 0.44 | -0.28 | 30 | 0.44 | 1.71 | 1,117 | 0.00 | – | live |
| A60 | KRAKEN-5K | 1 | 5,595.33 | -0.03 % | 0.43 | -0.28 | 23 | 0.43 | 1.67 | 1,088 | 0.00 | 1.6 % / 1.6 % | live |
| A30 | IDEAL | 1 | 5,592.16 | -0.09 % | 1.24 | -0.83 | 30 | 1.24 | 4.84 | 3,162 | 0.00 | – | live |
| A30 | KRAKEN-5K | 1 | 5,592.23 | -0.09 % | 1.22 | -0.83 | 23 | 1.22 | 4.77 | 3,111 | 0.00 | 1.3 % / 1.3 % | live |
| A120 | IDEAL | 1 | 5,595.35 | -0.03 % | 0.42 | -0.29 | 30 | 0.42 | 1.65 | 1,077 | 0.00 | – | live |
| A120 | KRAKEN-5K | 1 | 5,595.39 | -0.03 % | 0.41 | -0.29 | 22 | 0.41 | 1.61 | 1,049 | 0.00 | 1.9 % / 1.9 % | live |
| A0 | IDEAL | 1 | 5,596.03 | -0.02 % | 0.25 | -0.17 | 30 | 0.25 | 0.97 | 633 | 0.00 | – | live |
| A0 | KRAKEN-5K | 1 | 5,596.07 | -0.02 % | 0.24 | -0.17 | 22 | 0.24 | 0.93 | 608 | 0.00 | 2.2 % / 2.2 % | live |
| C252 | IDEAL | 1 | 5,593.24 | -0.07 % | 0.96 | 0.64 | 18 | 0.96 | 3.76 | 2,455 | 0.00 | – | live |
| C252 | KRAKEN-5K | 1 | 5,593.45 | -0.06 % | 0.91 | 0.69 | 12 | 0.91 | 3.55 | 2,317 | 0.00 | 5.5 % / 5.5 % | live |

Operational parity (KRAKEN-5K minus its IDEAL twin, return since start): A60 +0.00 %; A30 +0.00 %; A120 +0.00 %; A0 +0.00 %; C252 +0.00 %.

Orders since the forward start (from this run's re-simulation): A60/IDEAL 30 sent, 0 inside the band; A60/KRAKEN-5K 23 sent, 0 inside the band, 0 rounded to zero by the lot size, 0 prints cut by the 2x cap; A30/IDEAL 30 sent, 0 inside the band; A30/KRAKEN-5K 23 sent, 0 inside the band, 0 rounded to zero by the lot size, 0 prints cut by the 2x cap; A120/IDEAL 30 sent, 0 inside the band; A120/KRAKEN-5K 22 sent, 0 inside the band, 1 rounded to zero by the lot size, 0 prints cut by the 2x cap; A0/IDEAL 30 sent, 0 inside the band; A0/KRAKEN-5K 22 sent, 0 inside the band, 1 rounded to zero by the lot size, 0 prints cut by the 2x cap; C252/IDEAL 18 sent, 0 inside the band; C252/KRAKEN-5K 12 sent, 0 inside the band, 0 rounded to zero by the lot size, 0 prints cut by the 2x cap.

## What the books target on the panel's last row

| arm | row | target gross | target net | instruments | share Kraken cannot hold today |
|---|---|---:|---:|---:|---:|
| A60 | 2026-11-11 | 0.437 | -0.276 | 30 | 1.6 % |
| A30 | 2026-11-11 | 1.236 | -0.826 | 30 | 1.3 % |
| A120 | 2026-11-11 | 0.422 | -0.286 | 30 | 1.9 % |
| A0 | 2026-11-11 | 0.248 | -0.174 | 30 | 2.2 % |
| C252 | 2026-11-11 | 0.960 | 0.641 | 18 | 5.5 % |

## Performance (prereg §3: nothing before 60 rows; a reading at 60 and every further 30)

- **A60**: n < 60: no performance statement
- **A30**: n < 60: no performance statement
- **A120**: n < 60: no performance statement
- **A0**: n < 60: no performance statement
- **C252**: n < 60: no performance statement

## Kraken against Binance (informational, never in P&L)

Instruments held by a KRAKEN-5K account after the last row's trade. Kraken mark from the tickers snapshot against the latest Binance 1h close in the store; the two prints are not simultaneous (seconds apart in the last column).

| instrument | Kraken | Binance print | Kraken mark | gap bp | Kraken later by (s) |
|---|---|---:|---:|---:|---:|
| 1000PEPEUSDT | PF_PEPEUSD | 0.0053945 | 0.00548222 | 162.6 | 1,970 |
| AAVEUSDT | PF_AAVEUSD | 124.17 | 124.606 | 35.1 | 1,970 |
| ADAUSDT | PF_ADAUSD | 0.1747 | 0.175502 | 45.9 | 1,970 |
| AVAXUSDT | PF_AVAXUSD | 8.419 | 8.44921 | 35.9 | 1,970 |
| BNBUSDT | PF_BNBUSD | 680.28 | 682.098 | 26.7 | 1,970 |
| BTCUSDT | PF_XBTUSD | 73514.4 | 73777.9 | 35.8 | 1,970 |
| DOGEUSDT | PF_DOGEUSD | 0.06825 | 0.0685414 | 42.7 | 1,970 |
| ENAUSDT | PF_ENAUSD | 0.15191 | 0.153649 | 114.5 | 1,970 |
| ETHUSDT | PF_ETHUSD | 2049.19 | 2056.81 | 37.2 | 1,970 |
| FILUSDT | PF_FILUSD | 0.7565 | 0.761877 | 71.1 | 1,970 |
| HYPEUSDT | PF_HYPEUSD | 71.954 | 72.2073 | 35.2 | 1,970 |
| INJUSDT | PF_INJUSD | 8.061 | 8.19269 | 163.4 | 1,970 |
| LINKUSDT | PF_LINKUSD | 10.324 | 10.3958 | 69.5 | 1,970 |
| NEARUSDT | PF_NEARUSD | 3.628 | 3.68875 | 167.5 | 1,970 |
| PUMPUSDT | PF_PUMPUSD | 0.003554 | 0.00358275 | 80.9 | 1,970 |
| SOLUSDT | PF_SOLUSD | 83.12 | 83.5351 | 49.9 | 1,970 |
| STRKUSDT | PF_STRKUSD | 0.03787 | 0.0381541 | 75.0 | 1,970 |
| SUIUSDT | PF_SUIUSD | 0.8261 | 0.832718 | 80.1 | 1,970 |
| TAOUSDT | PF_TAOUSD | 219.1 | 220.53 | 65.2 | 1,970 |
| UNIUSDT | PF_UNIUSD | 6.693 | 6.76202 | 103.1 | 1,970 |
| WLDUSDT | PF_WLDUSD | 0.3112 | 0.312743 | 49.6 | 1,970 |
| XRPUSDT | PF_XRPUSD | 1.0514 | 1.05576 | 41.4 | 1,970 |
| ZECUSDT | PF_ZECUSD | 1032.72 | 1034.2 | 14.3 | 1,970 |
