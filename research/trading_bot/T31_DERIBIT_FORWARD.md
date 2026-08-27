# T31 — daily Deribit BTC/ETH option-chain forward collection

**Date stood up:** 2026-08-24 (15:00 CEST durable tick, CHUNK B).
**Task:** `T31_deribit_forward_collector` (agenda, queued by STRATEGIST 2026-08-24 00:00, ordered
for this tick by STRATEGIST 12:00).
**Status:** collector built, cron installed, first clean snapshot on disk and verified consumable.

## What this is

The convexity-wall finding (`free-data-convexity-wall`): bought convexity — the one surviving
strategy *shape* from the invention rounds — cannot be tested because historical option quotes
are not free (9 first-of-month Tardis samples under `research/data/deribit_free_samples/` is all
that exists). The named escape is to forward-collect the quotes now so that the test becomes
possible in months. This is that collector. It creates a dataset; it is not a sweep.

- **Source:** Deribit public REST v2 only — `get_instruments`, `get_book_summary_by_currency`
  (full chain), `get_order_book` depth=1 for every instrument with DTE ≤ 14 (bid/ask size,
  bid_iv/ask_iv, exchange greeks), `get_delivery_prices` (08:00 UTC settlement prints).
  No account, no keys, no orders.
- **Snapshots:** `research/data/deribit_forward/snapshots/snapshot_YYYY-MM-DD.csv.gz`, one per
  UTC day, written in the **Tardis `options_chain` column layout** (+ trailing extras `source,
  volume, volume_usd, interest_rate, index_price`) so the existing
  `deribit_wing_estimator.py --snapshot <file>` reads forward and historical files identically.
  Verified 2026-08-24: the estimator ran on the first forward snapshot unchanged and selected the
  ~15-delta 28AUG26 wings for both coins.
- **Outcomes:** `delivery_prices.json` accumulates Deribit's daily settlement prints
  (`btc_usd`, `eth_usd`; 40 days back-filled on day 0, 2026-07-16 → 2026-08-24). Together with the
  daily chain this is what makes an expiry-crossing P&L reconstructable later.
- **Integrity:** per-day sha256 + row counts + per-currency enrichment stats in `manifest.json`;
  completeness ledger in `ledger.json` (`--status`); failed/incomplete captures kept under
  `partial/` for forensics, never counted clean.
- **Clean-day rule (in code):** each currency ≥ 300 summary rows **and** ≥ 95 % of its DTE ≤ 14
  instruments enriched from the order book. Anything less is a failed day.
- **Schedule:** daily **02:15 Europe/Amsterdam** = 00:15 UTC in summer (01:15 UTC in winter),
  chosen to match the clock of the 9 historical Tardis samples (`_m15` = 00:15 UTC) so the two
  panels can be pooled on one snapshot time. Non-t4 user crontab line:
  `15 2 * * * /usr/bin/python3 /home/anont/meme/scripts/trading_bot/t31_deribit_collect.py >> /home/anont/meme/research/data/deribit_forward/cron.log 2>&1`
  The day-0 snapshot (2026-08-24) was taken off-clock at 13:06 UTC by the build tick; consumers
  should filter on `local_timestamp` hour if snapshot-time homogeneity matters.
- **Rate use:** ~670 order-book calls per run at ≤ 8 req/s (Deribit public limit 20/s), 112 s
  wall-clock on day 0. Idempotent: a re-run on an already-clean day is a no-op.

## First clean snapshot (day 0)

| | |
|---|---|
| file | `snapshots/snapshot_2026-08-24.csv.gz` |
| sha256 | `c8cee19fec15583e654eb4bec59781372f0d5962cfed9c3278bde2421933d166` (79,570 bytes) |
| rows | 1,752 (BTC 932 listed / 932 summary / 332 of 332 near-expiry enriched; ETH 820 / 820 / 332 of 332) |
| expiries | 11 per coin (dailies, weeklies, monthlies, quarterlies out to Jun-2027) |
| settlement prints | +80 (40 per index) |
| ledger | days attempted 1, clean 1, failed 0 |

## Frozen decision rules (restated verbatim from the agenda, frozen 2026-08-24 00:00 —
## BEFORE any forward snapshot existed)

> KILL-CONDITION: >=95% clean-snapshot days over the first 30 or the collector is fixed/killed;
> the convexity STRATEGY test gets its own pre-registration no earlier than +120 days of data —
> do NOT test early.

Protocol, frozen now:

1. **Collector gate** at the 30th calendar day (≈ 2026-09-23): `ledger.summary.days_clean /
   days_attempted ≥ 0.95` (with `days_attempted` = calendar days since day 0, so silent cron
   death counts as failure). Below that: one bounded fix tick; if still below, the collector is
   killed and the convexity escape is recorded as closed-for-lack-of-data.
2. **No strategy number is read from the forward panel before +120 days (≈ 2026-12-22).** Until
   then the only numbers anyone reads are the manifest/ledger integrity counts and estimator
   *compatibility* checks like today's. The wing-estimator output above is a format check, not a
   result, and is not to be cited as one.
3. The strategy test, when it comes, is its own pre-registration (design, bar, multiple-testing
   cost, kill-condition) written **before** the +120-day panel is opened, and it pools the 9
   historical samples only where the snapshot clock matches (00:15 UTC).

## Honest expectation, stated before the data

The historical free samples already showed the entry side is expensive: wing spreads 2–18 %
relative, fee ~5–8 % of premium, break-even moves 5.6–12 % inside ~4 DTE. A forward panel does
not make that cheaper; it only makes the *payoff* side measurable. The likeliest outcome, stated
now, is that bought weekly convexity has negative expectancy net of spread and fee except in
cascade regimes that a free panel of ~120 days will contain only a handful of. Value of the
panel regardless: it is the first dataset in this programme that can settle a convexity claim
with real quotes instead of assumptions, and it costs nothing but calendar time.

## Ops notes

- The order-book enrichment is the only rate-sensitive part; if Deribit tightens public limits,
  raise `MIN_INTERVAL` — a slow clean run beats a fast partial one.
- `partial/` should stay empty; a file there is the first thing to inspect on a failed day.
- `cron.log` is append-only; the tick that runs the collector gate reads `--status`.
