# B7d — Exhaustive Historical `CreateEvent` Enumeration

**Status:** implementation validated on a fixed historical pilot; scaling not yet measured  
**Access date:** 2026-07-27  
**Program/version scope:** Pump program `6EF8…F6P`, pinned IDL
`research/pump_idl_9c82f61.json`  
**Sources:** Helius Solana mainnet JSON-RPC for primary retrieval; public Solana mainnet RPC for
independent skipped-slot verification; official Pump IDL pinned from
`https://github.com/pump-fun/pump-public-docs`

## Purpose

B7c failed because it selected currently active tokens by affordable history size. Mature launches
must instead be selected at `CreateEvent` from an explicit old slot window. B7d implements that
gating capability without filtering on any outcome or later activity.

## Implementation

`scripts/b7d_create_enumerator.py` uses a SQLite checkpoint database and a half-open slot window.
It provides:

- exact pinned-IDL decoding from Anchor self-CPI inner instructions;
- canonical coordinates `(slot, transaction_index, outer_instruction_index,
  inner_instruction_index)` and deterministic export order;
- original event payload bytes retained as base64;
- an explicit row for every requested slot;
- idempotent crash recovery and strict database metadata matching;
- exact reconciliation of successful `create`/`create_v2` instructions to `CreateEvent`s;
- visible decode/reconciliation/RPC failures that block export;
- `getBlocks` verification for RPC `-32009` (“skipped or missing”) ambiguity;
- no credential persistence (`endpoint_ref` only).

The export includes all `CreateEvent` fields, so launch-time Mayhem, cashback, quote mint, creator,
user, reserves, token program, and bonding curve are available without future information.

## Fixed pilot

Window: **`[430,000,000, 430,000,500)`**, spanning 2026-07-01 02:08:09–02:11:27 UTC in retrieved
blocks. This window is an engineering pilot and is burned from future model training, validation,
and test selection.

| Check | Result |
|---|---:|
| Requested slots | 500 |
| Retrieved blocks | 496 |
| Ledger-skipped slots | 4 |
| Unexplained RPC gaps | **0** |
| Successful create instructions | **63** |
| Exactly decoded `CreateEvent`s | **63** |
| Distinct launch mints | **63** |
| Decode failures | **0** |
| Reconciliation failures | **0** |
| SQLite integrity check | `ok` |

Slots 430,000,012–430,000,015 returned `-32009` from both Helius and the public endpoint. An
independent public `getBlocks(430000008, 430000020)` result omitted precisely those four while
listing surrounding blocks, establishing ledger skips rather than archival loss.

The JSONL export is byte-identical between v1 and reconciliation-enabled v2 runs, and a no-pending
rerun made zero block requests. Final v2 JSONL SHA-256:
`f86aadbddf695cad4af877f5fbcc9183e1db9ae5f1cbda7389ff9830c5d3a2c5`.

## Observations, not population rates

- **Verified fact for this window:** 31/63 launches were Mayhem; 32/63 were non-Mayhem.
- **Verified fact for this window:** 62/63 used native SOL and one used USDC as `quote_mint`.
- **Verified fact for this window:** 13/63 non-Mayhem launches had cashback enabled; no sampled
  Mayhem launch did.
- **Working hypothesis:** launch composition changes materially by calendar regime. This pilot's
  49% Mayhem share differs sharply from B7a's later 10% window and must not be generalized.

The window is only about 198 seconds and is not a launch-rate or attribute-distribution study.

## Remaining work

Run a preregistered older launch window large enough to supply a mature cohort, then feed its
bonding-curve or mint histories into a TradeEvent-only lifecycle pipeline. `D_dead` remains unset;
B7d solves cohort discovery, not inactivity-threshold selection.

## Reproduction

```bash
set -a; source .env; set +a
python scripts/b7d_create_enumerator.py \
  --start-slot 430000000 --end-slot 430000500 \
  --database research/b7d_create_430000000_430000500_v2.sqlite \
  --export-jsonl research/b7d_create_430000000_430000500_v2.jsonl \
  --workers 4
```
