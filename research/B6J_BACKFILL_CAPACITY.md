# B6j — Free-Endpoint Backfill Capacity, and the Corrected Commitment Delta

Run: 2026-07-27, approximately 14:35–14:50 UTC. Author: Claude.
Endpoint: `https://api.mainnet-beta.solana.com` and `wss://` equivalent (free public).

Read-only. No keys, no signing, no transactions.
Scripts: `scripts/b6j_backfill_capacity.py`, `scripts/b6h_commitment_correlator.py` (Codex's
corrected barrier/grace version).

## Part 1 — Corrected commitment delta, replacing F36–F38

Codex's audit was right on every point. Re-run with a shared acknowledgement barrier before the
capture window and a 5-second right-edge grace:

| | my biased run | corrected run |
|---|---:|---:|
| median delta | 173.7 ms | **131.5 ms** |
| p90 | 331.3 ms | 235.4 ms |
| p99 | 784.5 ms | 433.8 ms |
| negative arrivals | 4.3% | **4.96%** |
| processed cohort unmatched after grace | (not measured) | **0 of 48,581** |

**F36 is superseded.** My median was biased ~32% high by startup/shutdown correlation bias.
The corrected client-observed arrival delta is **131.5 ms median**.

**F38 is withdrawn entirely.** I reported "0.4% of confirmed signatures never seen at processed"
as a real visibility miss. With a proper window and grace, **0 of 48,581** cohort members went
unmatched — it was window censoring, not provider loss. The 79 confirmed-core signatures without
a processed observation remain a diagnostic only: as Codex noted, independent public-RPC fanout
has no completeness oracle, so "miss" was never a claim the method could support.

**F37 survives.** Negative arrivals persist at 4.96%, so cross-subscription ordering is genuinely
not guaranteed and individual deltas remain unusable as per-transaction latency.

Scope corrections also accepted: F34's byte-identity covers WebSocket **application message
payloads**, not RFC 6455 framing or control bytes. And F39's ~92–94% describes **Pump-mentioning
ecosystem attempts** — largely other people's racing bots — **not** a forecast of our own landing
probability. I had let that distinction blur.

## Part 2 — `getTransaction` backfill capacity

The logs feed carries `TradeEvent` but not fees paid, compute units, tips, account keys, or
balance deltas. Cost reconstruction therefore needs a `getTransaction` per transaction of
interest. Ramping concurrency against the free endpoint:

| Concurrency | ok | ok/s | rate-limited | p50 ms | p90 ms | KB/tx |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 16 | 0.82 | 0 | 1237 | 1699 | 9.7 |
| 2 | 34 | 1.78 | 7 | 1141 | 1517 | 9.6 |
| 4 | 29 | 1.45 | 65 | 744 | 1202 | 9.9 |
| 8 | 48 | 2.51 | 74 | 1108 | 1946 | 10.3 |
| 16 | 52 | 2.52 | 134 | 1478 | 2718 | 10.8 |

**F40 — the free endpoint sustains ~2.5 `getTransaction`/s, and throughput saturates immediately
(verified fact).** Rate limiting begins at concurrency 2 and dominates by 16 (134 of 186 attempts
rejected). Adding concurrency past 8 buys nothing — the ceiling is server-side, not client-side.

Against measured demand from the B6h logs run:

| Demand | Rate | Coverage at 2.5/s |
|---|---:|---:|
| Successful Pump transactions | 12.0/s | **21.0%** |
| All Pump-mentioning transactions | 168.5/s | **1.5%** |

**F41 — full cost reconstruction is impossible on the free path (verified fact).**
Only about one successful trade in five can be enriched with its cost and account fields in real
time. `PLAN.md`'s success criterion of "complete auditability from raw observation through
decision and outcome" **cannot be met market-wide for free**.

## What this actually decides: cohort scope, quantified

This does not block the research — it sizes it. 2.5 tx/s is **~216,000 transactions/day** of
backfill capacity. Spent market-wide it buys a 21% sample of everything; spent on a **cohort** it
buys *complete* histories for a bounded set of tokens.

If a typical bonding-curve token's full lifetime is on the order of hundreds to a few thousand
transactions, 216k transactions/day supports **complete cost-level reconstruction for roughly
100–1,000 tokens per day**, and the event-level record from the logs feed stays complete for
*everything* regardless.

That is the concrete argument for cohort-scoped research, now with a number attached rather than
an intuition. It also preserves the leakage rule: cohort membership must be fixed **at launch**
and exhaustive within the chosen window, never selected on outcome.

## Limitations

- One endpoint, one time of day, ~18 s per concurrency step. Public rate limits are undocumented
  and may be per-IP, time-varying, or burst-tolerant in ways this ramp did not explore.
- A free *registered* tier (Chainstack/Helius) was not tested and may lift the ceiling materially
  at zero cost — this is the single cheapest thing that could change F40/F41.
- The token-lifetime figure used for the cohort estimate is an assumption, not a measurement.
  It needs measuring before any cohort size is committed.
- Demand figures come from the single B6h 90-second window; Pump traffic is non-stationary (F9).

## Follow-ups

1. Measure actual per-token lifetime transaction counts, to replace the assumption in the cohort
   sizing above.
2. Test a free registered RPC tier's `getTransaction` ceiling — cheapest possible lever on F40.
3. Design cohort selection: launch-time, exhaustive-in-window, with the selection rule recorded
   before any outcome is observed.
