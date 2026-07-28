# B6h — Logs Adapter Integration and Concurrent Commitment-Latency Measurement

> **Superseded measurement warning (Codex audit, 2026-07-27):** F36–F38 below are not
> valid as stated. The two readers began and ended on independent clocks, with no common
> acknowledgement barrier or right-edge confirmation grace. This creates startup/shutdown
> correlation bias; `confirmed-only` cannot be called a provider miss without a completeness
> oracle. Corrected implementation and live evidence are in `B6I_COMMITMENT_AUDIT.md`.
> F34 is scoped to byte-identical WebSocket *application message payloads*, excluding RFC 6455
> framing/control bytes. F39 describes Pump-mentioning ecosystem attempts, not our bot's future
> landing probability.

Run: 2026-07-27, approximately 14:10–14:25 UTC. Author: Claude.
Endpoint: `wss://api.mainnet-beta.solana.com` (free public, no account, no key).

Read-only. No keys, no signing, no transactions.
Scripts: `scripts/recorder.py run-logs`, `scripts/b6h_commitment_correlator.py`.

Executes Codex's Seq-28 handoff: integrate the raw logs feed with the recorder, then measure
processed→confirmed delay by concurrent subscription rather than separate windows.

## Part 1 — Logs adapter against frozen spec v0.2

90-second run, `commitment: confirmed`:

| Metric | Value |
|---|---:|
| Notifications | 15,164 (168.0/s) |
| **Reconnects** | **0** |
| Succeeded / failed | 1,080 / 14,084 (**92.9% failed**) |
| TradeEvents | 1,002 in **999 event-bearing transactions** |
| Event-bearing transaction coverage | **92.5%** of successful txs *(transaction units)* |
| Explicit truncation markers | 0 |
| Bandwidth | 15.63 MB → **14.6 GB/day** |
| Segment integrity | 15,165 records, clean, SHA-256 **OK** |

Coverage is reported in **transaction units**, per Codex's Seq-28 correction of B6f's mixed
event/transaction denominator. Successful transactions without a TradeEvent are **not** treated
as truncation — the truncation detector fires only on an explicit `log truncated` marker, and
raises a `gap` row with `detected_by = log_truncated` when it does.

**F34 — raw-frame fidelity is closed for this adapter (verified by construction).**
The payload written to the segment is the exact byte string returned by `WebSocket.recv()`, with
no parse-and-reserialize step. This is the gap Codex raised in Seq 22 about the polling adapter,
whose payloads are reconstructed and correctly carry the `b6-lite-normalized-v1` label. The logs
adapter records `payload_fidelity: verbatim`.

A round-trip check found only 1 of 400 payloads differing from our own compact re-serialization —
that is **weak** corroboration, because the server also emits compact JSON, so the two usually
coincide. Fidelity here rests on the code path, not on that test.

**F35 — compression on this stream is 9.4× (zlib-6) / 11.4× (lzma-1), and that changes the codec
argument.** On RPC block JSON, F27 measured lzma-1 at 27.03× against zlib-6's 10.15× — a 2.8×
advantage. On this stream lzma's advantage collapses to **1.21×**. Given lzma's materially higher
CPU cost, zlib is the better default for this transport. Retention constants still stay unfixed;
this is one more reason not to have set them earlier.

At 9.4×, 14.6 GB/day becomes **~1.6 GB/day**, so 166 GB holds roughly **three months**.

## Part 2 — Concurrent commitment latency

Two WebSocket connections in one process, subscribed simultaneously at `processed` and
`confirmed`, correlating identical signatures on a single monotonic clock (so the delta carries no
cross-host clock skew). 100 seconds.

| | processed | confirmed |
|---|---:|---:|
| Notifications | 72,621 | 72,919 |
| Unique signatures | 72,621 | 72,919 |
| Failed | 93.8% | 93.8% |

**Correlated at both commitments: 72,621 signatures.**

### F36 — processed→confirmed observation delay (verified fact)

| Percentile | Delay (ms) |
|---|---:|
| min | −612.2 |
| p10 | 63.9 |
| **median** | **173.7** |
| p90 | 331.3 |
| p99 | 784.5 |
| max | 937.7 |
| mean | 193.5 |

**This partially recovers what C3 wanted from a paid Geyser feed, at zero cost.** I had recorded
that observation-latency modelling was impossible without Geyser. For the processed→confirmed
interval — the dominant term in decision-time visibility — that was too strong. It is measurable
now, and the median is ~174 ms, i.e. roughly 0.4 of a slot.

What this measures is **our observation delta on a free public endpoint**, including provider
fanout and local network path. That is not the cluster-internal commitment interval — and for
execution modelling it is the more relevant quantity, because it is the visibility a local
strategy would actually have.

### F37 — cross-subscription ordering is not guaranteed (verified fact)

**3,126 of 72,621 deltas (4.3%) were negative** — the confirmed stream delivered a signature
before the processed stream did. Two independent subscriptions are not mutually ordered, so:

- the **distribution** above is meaningful;
- an **individual** delta is not a reliable per-transaction latency and must not be used as one.

This is exactly the kind of ordering hazard `AGENTS.md` warns about, and it argues for the
canonical-ordering rule being enforced on chain coordinates rather than arrival order.

### F38 — the processed stream misses 0.4% of confirmed signatures

298 signatures appeared at `confirmed` having never been seen at `processed`. Real visibility
misses, not correlation failures. Small, but it means a processed subscription is not a complete
view of pre-confirmation traffic and its incompleteness is measurable.

### F39 — failure rate 93.8% at both commitments, n≈145,000

Both streams independently reported 93.8% failed over 100 seconds. This is by far the largest
sample the project has (F9: 36.7% and 85.0% on few-slot windows; F33: 88.0% on 70 s; Codex's
audit: 74.2% confirmed / 93.4% processed on 30 s). The spread across measurements is 74–94%, so
the quantity is high and volatile — still not a base rate, but the direction is consistent and the
landing-reliability hypothesis keeps strengthening.

## Limitations

- Single 90 s and 100 s windows on one day; Pump traffic is non-stationary (F9).
- Latency reflects one endpoint from one network location; another host or provider would differ.
- Zero reconnects in 90 s says nothing about hours. Long-run stability, host sleep, and reconnect
  gap accounting remain unexercised.
- Still absent regardless of commitment: dead-slot notification, account updates, orphan
  derivation (R2), fees paid, compute units, tips, account keys.
- Compression measured on 21.6 MB of one stream.

## Follow-ups

1. Long-run stability run with reconnect and host-sleep gap accounting.
2. Selective `getTransaction` backfill for cost and account-key fields; measure a sampling rate
   that stays inside free rate limits.
3. Audit the successful-but-no-event remainder against `getTransaction` to confirm it is ordinary
   non-trade traffic, as Codex's audit indicated.
4. Repeat the latency measurement at a different time of day before treating ~174 ms as typical.
