# B6g — Reproducible Free `logsSubscribe` Audit

Run: 2026-07-27 against `wss://api.mainnet-beta.solana.com`, no account or key.
Scripts: `scripts/b6g_logs_probe.py`, `scripts/b6g_analyze_raw.py`.

## Reproducibility correction

B6f's committed probe implemented only `blockSubscribe`; its 70-second `logsSubscribe` method and
raw output were absent. B6g persists every received WebSocket message byte-for-byte in a simple
length-framed file plus an atomic JSON summary.

## Independent live samples

| Metric | Confirmed, 30 s | Processed, 30 s |
|---|---:|---:|
| Notifications | 2,671 | 16,286 |
| Notifications/s | 88.5 | 537.2 |
| Unique signatures | 2,671 | 16,286 |
| Successful | 688 | 1,079 |
| Failed | 1,983 (74.2%) | 15,207 (93.4%) |
| TradeEvent payloads | 610 | 1,071 |
| Successful notifications with ≥1 TradeEvent | 606 | 1,015 |
| Successful notifications without TradeEvent | 82 | 64 |
| Explicit truncation markers | 0 | 0 |
| Bytes | 4.30 MB | 17.74 MB |

The windows are not simultaneous, so their rates and failure percentages must not be interpreted
as a commitment-level comparison. They do verify that the free endpoint accepts both commitments
and can push several hundred Pump-related notifications per second.

## Metric corrections

`TradeEvents / successful transactions` is **not event coverage**: one transaction can emit more
than one TradeEvent. B6f's 94.9% was calculated with incompatible units. The correct transaction
metric is notifications containing at least one TradeEvent: 606/688 (88.1%) confirmed and
1,015/1,079 (94.1%) processed in these windows.

The missing-event transactions were overwhelmingly legitimate non-trades: cashback claims,
volume-accumulator initialization/closure, creator-fee collection, fee distribution, and migration
operations. Therefore `successful transaction without TradeEvent` is not itself truncation.

B6f also treated some `Program data:` lines as malformed base64. Solana log-data lines may contain
multiple space-separated base64 fields. Decoding each field separately produced zero malformed
fields in both persisted samples.

## Client audit

The minimal WebSocket client now validates `Sec-WebSocket-Accept`, rejects RSV extensions it did
not negotiate, rejects masked server frames, and enforces control-frame finality/size. Raw message
payloads remain unchanged when returned to the recorder.

## Conclusion

Free `logsSubscribe` is a viable research transport and removes any immediate need to purchase
Geyser. It provides real-time signatures, slots, errors, logs, and TradeEvent payloads, including
failed attempts. It does not provide complete transaction metadata, account writes, orphan/dead
slot status, or a guarantee against undetectable provider-side loss. Selective `getTransaction`
backfill remains necessary for fees, compute, account keys, and balance deltas.

Next, subscribe to processed and confirmed concurrently and correlate identical signatures using
local monotonic timestamps. That measures observed confirmation delay without confusing different
traffic windows. Then integrate the raw feed with session/crash framing and reconnect gaps.
