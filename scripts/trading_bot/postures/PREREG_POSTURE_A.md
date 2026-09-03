# PRE-REGISTRATION — POSTURE A "OWN THE BASKET"
Frozen 2026-09-03 BEFORE any effect was computed. Seed 20260903. Data: research/data/t23_cache/panel/
perp_daily.csv sha256 afd242bdaa5e8f5ee453e33920fbfe3aa1cf1255653f276ec3544a2fbbbe1628,
funding.csv sha256 aa4c06a1be8f18956a2c43988c777f7da8a160db18aefd550d88fe86d0b5413b

## GATE 1 — COVERAGE (minimums declared before counting)
G1a >= 1,000 trading days on which the liquid set (qv >= $1M on the prior day) holds >= 20 names.
G1b >= 300 distinct symbols enter the liquid set at least once.
G1c funding.csv covers >= 80% of held symbol-days (else funding drag is unmeasurable and the perp
    basket cannot be costed honestly -> STOP).
G1d panel is survivorship-complete: delisted symbols present. Terminal (delist) events must be
    handled as forced exits at last close, never dropped.

## GATE 2 — POWER (computed before reading any effect)
Test: one-sided H1 mean net daily basket return > 0, alpha = 0.05, power = 0.80.
Unit = one basket-day. Clustering unit = DATE. The basket series has exactly one observation per
date, so the date-clustered design effect is 1 + (m-1)*ICC with m = 1 => DEFF = 1.0 regardless of
ICC = 0.3. The ICC 0.3 penalty is applied where it bites: the symbol-day panel statistics
(mean-vs-median replication), where m = mean names/day.
MDE(basket) = (z_0.95 + z_0.80) * sd_daily / sqrt(n_days) = 2.4865 * sd/sqrt(n).
KILL LINE (declared now): if the point estimate of the net-of-cost mean daily return is BELOW the
MDE, the result is underpowered and must be reported as NOT ESTABLISHED, not as a win.

## GATE 3 — EFFECT
Cluster bootstrap by DATE, 5,000 draws, seed 20260903, on the net-of-cost daily series.
PASS requires CI-lo(mean net daily return) > 0.

## ECONOMICS / PRODUCT LINE (declared now)
Cost: 24.1 bp round trip = 12.05 bp per leg, charged as one_way_turnover * 24.1 bp where
one_way_turnover_t = 0.5 * sum_i |w_target - w_drifted|.
Funding: a long perp basket PAYS funding when the rate is positive. Charged from funding.csv.
PRODUCT LINE: "own the basket" is worth capital only if, net of cost and funding, it clears
BOTH (a) annualised Sharpe >= 0.50 and (b) max drawdown <= 50%. Anything worse is crypto beta
with a worse drawdown than a stock index and is DEAD as a product.

## OVERLAY (exactly one, pre-registered, no selection)
Flat when the basket's own net equity curve closes below its 100-day simple moving average;
re-enter when it closes back above. Transition charged 12.05 bp per leg. Lookback = 100 fixed.
A sensitivity sweep over other lookbacks is reported as DIAGNOSTIC ONLY and may not be used to
pick the reported overlay. Prior: this repo's crash filter cut DD -84.9% -> -69.5% but lost return
on 9 of 10 lookbacks. Expected outcome: FAIL.

## CONTROL RULE
No cross-sectional median benchmark. Benchmarks are EW-mean of an investable universe, BTCUSDT
alone, and a top-20-by-trailing-quote-volume cap proxy.
