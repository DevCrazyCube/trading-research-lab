# B6a — Measured Capture Volume and Retention

Run: 2026-07-27, approximately 11:50–12:00 UTC. Author: Claude.
Measured over consecutive finalized blocks near slots 435,531,953 and 435,531,995.

Read-only mainnet RPC. No keys, no signing, no transactions.
Script: `scripts/b6a_volume_estimate.py`.

Purpose: convert the owner's stated 75–100 GB disk budget into a retention window using
measurement rather than estimate, and determine whether full-fidelity capture is affordable.

## Measured traffic

| | per slot |
|---|---:|
| All transactions | 1,362 |
| Touching Pump or PumpSwap | 210 |
| Touching Pump | 125–179 (varies by window) |

Slot rate assumed 216,000/day (400 ms target). Solana's real slot time runs slightly above target,
so day figures are marginally conservative.

## Measured bytes, Pump-touching transactions only

| Component | KB/slot | GB/day |
|---|---:|---:|
| Raw transaction wire bytes (base64-decoded) | 201.2 | **41.5** |
| Transaction metadata as JSON (upper bound) | 635.5 | 130.9 |

Metadata dominates, which is expected: it carries inner instructions, and the self-CPI event
payloads that F5/F11 established as the decode path live there. **Metadata cannot be discarded.**

Total, by assumption about how well protobuf compresses the metadata against its JSON form:

| Assumption | GB/day | 75 GB | 100 GB |
|---|---:|---:|---:|
| Metadata at JSON size (worst case) | 172.4 | 0.4 days | 0.6 days |
| Metadata at 40% of JSON (protobuf estimate) | 93.8 | 0.8 days | **1.1 days** |
| Metadata at 25% of JSON (optimistic) | 74.2 | 1.0 days | 1.3 days |

## F20 — Full-fidelity capture does not fit the budget (verified fact)

**100 GB buys roughly one day** of undifferentiated Pump capture. The planned 72-hour pilot at
full breadth would require **≈220–280 GB** — two to three times the entire budget.

This is not a marginal overshoot that compression closes. Even at an optimistic 4× compression
ratio the 72-hour pilot needs ~55–70 GB, consuming most of the budget for three days of data and
leaving nothing for ongoing operation.

## F21 — Decoded events are ~50× smaller (verified fact)

Measured `TradeEvent` traffic: ≈14 events/slot at 366–381 bytes of payload. With a generous
200-byte provenance envelope per record:

```
14 events/slot x ~580 B = ~8 KB/slot = ~1.7 GB/day
```

Call it **~2 GB/day** including other event types. At that rate 100 GB holds **months**.

The gap between 94 GB/day and 2 GB/day is the entire decision.

## Recommendation — tiered retention

Full "capture raw, decode later" is unaffordable at this budget, and silently abandoning it would
be worse. Bound it in time instead:

- **Tier 1 — rolling raw frames.** Everything, byte-identical, aged out on a fixed window.
  ~60 GB holds roughly 2–3 days compressed. A decoder bug discovered inside this window is fully
  repairable by replay, which is the property the principle exists to protect.
- **Tier 2 — permanent decoded events.** ~2 GB/day, kept indefinitely. This is the long-horizon
  research dataset.

**The honest cost:** a decoder defect discovered *after* a record ages out of Tier 1 is
unrecoverable for that record. That raises the stakes on decoder-correctness gates and on the
`unknown`-frame alarm rate — those move from good practice to the thing standing between the
project and permanent silent data loss. It should be stated in any future report built on Tier 2
data that pre-dates the Tier 1 window.

## Limitations

- Five to six blocks in one window on one day. Pump traffic is demonstrably non-stationary (F9),
  so these rates will move; the pilot must re-measure rather than treat this as fixed.
- The protobuf-versus-JSON metadata ratio is an **assumption**, not a measurement — nothing here
  actually observed a Geyser protobuf frame. The pilot's first real job is to replace that
  assumption with a number.
- Compression ratios are assumed, not measured.
- Excludes account updates, which a Geyser subscription may also deliver and which would add
  volume beyond these figures.
