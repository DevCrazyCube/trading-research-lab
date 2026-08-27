# T33 — daily Alpaca US-options chain forward collection (goal universe)

**Date stood up:** 2026-08-25 (03:00 CEST durable tick, CHUNK B).
**Task:** `T33_us_options_forward_collector` (agenda, queued by STRATEGIST 2026-08-25 00:00).
**Status at write time:** collector built, off-hours format check passed, cron installed, protocol
frozen. **No forward snapshot exists yet** — the first one is taken by the cron run today at
15:45 ET (2026-08-25). This document and its `.sha256` are written BEFORE that snapshot.

## What this is

T31 forward-collects Deribit BTC/ETH option quotes so that bought convexity — the one surviving
strategy *shape* from the invention rounds — becomes testable in months instead of never. The
programme's goal names US equities/ETFs, and T32 proved (13/13 clean RTH pulls) that Alpaca's free
`/v1beta1/options/snapshots/{underlying}` endpoint returns full chains with bid/ask under the paper
keys. This is the same collector, in the goal universe. It creates a dataset; it is not a sweep.

- **Source:** `data.alpaca.markets/v1beta1/options/snapshots/{underlying}` (default feed as served;
  `latestQuote` bid/ask/size/timestamp, `latestTrade`, `impliedVolatility` + `greeks` where served,
  `dailyBar`), `limit=1000` + `page_token`, 429 backoff, ≤ 170 req/min. Underlying spot from
  `/v2/stocks/snapshots` (one request). Market-open check from paper-api `/v2/clock`.
  **Quotes only. No orders of any kind, paper or otherwise.**
- **Universe (FROZEN now, before the first snapshot; 14 underlyings, none trimmed):**
  `SPY QQQ IWM TLT HYG GLD XLE XLF NVDA TSLA AAPL AMZN MSFT AMD`.
- **Expiries per underlying:** every listed expiry with DTE ≤ 45, plus the next two standard
  monthlies (3rd Friday; Thursday fallback on a Friday holiday) beyond that window.
- **Snapshot clock:** **15:45 America/New_York** on every trading day — inside RTH so quotes are
  live, before the closing crush. The cron line fires at 20:45 Europe/Amsterdam and the script waits
  until 15:45 ET (max 2 h), so the weeks where US and EU DST differ (2026-10-25 → 11-01,
  2027-03-14 → 03-28) cannot push the capture past the close. (The agenda's draft said `45 21`;
  that clock would land at 16:45 ET during the mismatch weeks — changed for that reason only; the
  capture time itself is unchanged.) Non-t4 user crontab line:
  `45 20 * * 1-5 /usr/bin/python3 /home/anont/meme/scripts/trading_bot/t33_us_options_collect.py >> /home/anont/meme/research/data/us_options_forward/cron.log 2>&1`
- **Archive:** `research/data/us_options_forward/snapshots/snapshot_YYYY-MM-DD.csv.gz` (ET trading
  date), 30 columns: contract metadata (OCC-parsed root/expiration/DTE/type/strike), bid/ask/size/
  quote timestamp, last trade, IV + greeks as served, day bar, underlying spot + timestamp, capture
  timestamp. Per-day sha256 + counts + per-underlying stats + spots in `manifest.json`; completeness
  ledger in `ledger.json` (`--status`); failed captures kept under `partial/`, never counted clean;
  market-closed days recorded as `market_closed` and excluded from the attempted/clean denominators.
- **Clean-day rule (in code):** market open at capture; all 14 underlyings returned; each with
  ≥ 200 contracts and ≥ 70 % of rows carrying a two-sided quote stamped on the capture ET date.
- **Idempotent:** a re-run on an already-clean day is a no-op. A launch > 2 h before 15:45 ET is
  refused and logged as a failed day (so a broken clock cannot silently produce off-hours data).

## Off-hours format check (2026-08-24 21:03 ET, market closed; NOT a snapshot, nothing ledgered)

| underlying | contracts | expiries | pages | two-sided | quote stamped on session date | IV/greeks served |
|---|---|---|---|---|---|---|
| SPY | 6,934 | 17 (window 08-24 → 10-08 + monthlies 10-16, 11-20) | 9 | 6,200 | 89.4 % | 5,128 (74 %) |
| AMD | 3,730 | 12 (same window + both monthlies) | 6 | 3,041 | 81.5 % | 1,606 (43 %) |

Extrapolated full run: ~50k rows, ~80 requests, well under a minute at the throttle. IV and greeks
are served for roughly the traded/quoted core of each chain and are missing on far wings — the
bid/ask is what the convexity claim is priced on, so that is acceptable and recorded as-served.
Spot came from `/v2/stocks/snapshots` (SPY 763.65 at 20:16 UTC).

## Frozen decision rules (restated verbatim from the agenda, frozen 2026-08-25 00:00 —
## BEFORE any forward snapshot existed)

> KILL-CONDITION (frozen now): >=95% clean days over the first 30 trading days or fix/kill; NO
> strategy number read before +120 calendar days (~2026-12-23); the convexity design is
> pre-registered jointly with T31 (see T35) before the panel is opened.

Protocol, frozen now:

1. **Collector gate** at the 30th trading day (≈ 2026-10-07): `ledger.summary.days_clean /
   days_attempted ≥ 0.95`, where every scheduled trading day counts as attempted (a silent cron
   death is a failed day — the gate tick reconciles the ledger against the exchange calendar).
   Below that: one bounded fix tick; if still below, the collector is killed and the US-options
   convexity escape is recorded as closed-for-lack-of-data.
2. **No strategy number is read from the forward panel before +120 calendar days (≈ 2026-12-23).**
   Until then the only numbers read are manifest/ledger integrity counts and format checks like the
   one above.
3. The strategy test is the **joint T31/T33 pre-registration** (`CONVEXITY_PREREGISTRATION.md`, task
   T35): trigger family stated once (≤ 3 pre-named designs), one bar and one multiple-testing cost
   pooled over both universes, kill-condition, earliest-open date. Written before the panel is opened.

## Honest expectation, stated before the data

The variance premium in US index/ETF options is real and powered in this programme's own data
(T21 §4b, +4σ): selling convexity earns carry, so *buying* it has negative expected carry by default.
A bought-wing design on this panel survives only if a conditional trigger beats that carry after its
multiple-testing cost — and a ~120-day panel contains a handful of stress days at most. The likeliest
verdict, written now, is that bought convexity is dead at the honest bar in this universe as well.
Value of the panel regardless: it is the first US-options dataset in the programme with real
executable quotes, it costs nothing but calendar time, and it settles the question with prices
instead of assumptions.

## Ops notes

- `partial/` should stay empty; a file there is the first thing to inspect on a failed day.
- If Alpaca changes the default feed or starts refusing pagination, the per-underlying `pages` and
  `fresh_frac` in the manifest are the tell; raise `MIN_INTERVAL` before anything else.
- The machine must be awake at 20:45–21:45 local on trading days; a sleeping host is a failed day
  by design (same rule as T30/T31), not an excuse.

## Amendment v2 — 2026-08-26 00:00 CEST (STRATEGIST tick; the protocol's "fix" branch, taken on day 1)

**What happened.** The first scheduled capture (2026-08-25 15:45 ET) returned all 14 underlyings,
37,883 rows, 0 transport errors, 71 s — and was ledgered **`failed`** under the v1 clean-day rule
because two underlyings missed the 70 % freshness floor: `HYG 0.626`, `XLE 0.700` (exact 795/1136 =
0.69982). Rows kept under `partial/partial_2026-08-25_194500.csv.gz`. Per the ops note, the partial
was the first thing inspected (integrity counts only — no price, IV or strategy number was read):

| underlying | contracts | fresh (all) | fresh, \|strike/spot−1\| ≤ 15 % | fresh, > 15 % | note |
|---|---|---|---|---|---|
| HYG | 620 | **0.626** | **0.647** | 0.519 | strikes 45–105 on spot 79.9; staleness is structural, not far-wing only |
| XLE | 1,136 | **0.700** | 0.905 | 0.495 | 124 rows carry a 2025-12-04 quote stamp (dead series served as last-quote) |
| XLF | 1,334 | 0.733 | 0.802 | 0.599 | marginal by the same mechanism |
| TLT | 1,115 | 0.778 | 0.834 | 0.614 | |
| SPY / QQQ / IWM / GLD | 3.4k–6.6k | 0.85–0.89 | 0.91–0.94 | 0.72–0.81 | |
| NVDA TSLA AAPL AMZN MSFT AMD | 1.2k–3.5k | 0.82–0.92 | 0.95–1.00 | 0.73–0.89 | |

**Diagnosis.** Freshness is a property of each underlying's option market (far wings and dead
series are quoted stale by the venue), not of the collector. HYG would have failed the v1 day-rule
on every trading day by construction, so the collector was on track to die at the day-30 gate for a
threshold-calibration reason — the same class of self-inflicted process bug as the BASKET1
re-freezes. The frozen protocol names this branch ("≥ 95 % clean days … **or fix/kill**"); the fix is
taken now, on day 1, rather than after 29 more certain failures.

**Rule v2 (in code, sha below), effective from the 2026-08-26 capture:**
- Clean-day rule = market open at capture; all 14 underlyings returned; each ≥ 200 contracts.
  (Collector health only.)
- `MIN_FRESH_FRAC = 0.70` is unchanged but is now a **per-underlying eligibility flag**: each
  underlying's `fresh_frac`/`fresh_ok` is written to `manifest.json`, and the day's ledger entry
  carries `fresh_fail: [...]` (empty on a fully-fresh day). Nothing about the capture, universe,
  clock, expiries or columns changes.
- **Eligibility gate (written now, evaluated at the day-30 gate ≈ 2026-10-07, before any design
  is opened):** an underlying enters the December convexity design only if `fresh_ok` on ≥ 95 % of
  clean days. Stated expectation: **HYG is excluded**, XLE/XLF are at risk; the design (T35) must
  be written on the 14-name universe with this exclusion rule, not on the survivors after peeking.
- **2026-08-25 stays `failed` in the ledger.** It is not retro-classified (the rule that failed it
  was the rule in force). Its complete 14/14 partial is retained; it is **excluded** from the
  December panel by default, and may be admitted only if the T35 pre-registration says so before
  the panel is opened. Consequence acknowledged: the day-30 gate (`days_clean/days_attempted ≥
  0.95` over 30 trading days) now has **zero slack** — one more failed day drops it to 28/30 and
  invokes the gate's one bounded fix tick.

**Hashes.** v1 (frozen 2026-08-25 03:00 CEST): doc `9468cc743484875be2d222c1090bdef5af08f203b486301937186dfe054ae481`,
script `8ba91ccc557b82e78a8ff6b48fd4f78d738901bf572841ac9adaf00ea0014926`. v2 script:
`2cbe5ebd2d58131f452883dc865dec7d593003bc748225b52688c3ba64758c4c` (diff: 6 hunks, classification
only; `record()` gains `fresh_fail`, `--preflight` reports `fresh_fail`). The `.sha256` file is
re-pinned to v2 by this amendment; the v1 hashes above are the audit trail.
